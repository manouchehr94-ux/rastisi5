"""سرویس مدیریت کاتالوگ از پنل مدیریت — محصولات و دسته‌بندی‌ها.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۲. تولید اسلاگ یکتا و
حذف امن دسته‌بندی (بدون یتیم‌شدن محصول/زیرگروه) اینجا متمرکز شده‌اند تا در
ویو تکرار نشوند.

همه‌ی توابع این ماژول ``store`` را صریح می‌گیرند — Category/Brand/Vendor/Product
اکنون مالکیت مستقیم Store دارند؛ هیچ‌کدام از این توابع هرگز خودشان Store را
از Host یا حالت سازگاری حدس نمی‌زنند (فراخوان — ویو/فرم — مسئول resolve
کردن Store است).
"""

from django.db import models
from django.db.models import Count, Q, Sum
from django.utils.text import slugify

from apps.catalog.models import Category, Product, Vendor

LOW_STOCK_THRESHOLD = 10


class CategoryDeleteError(Exception):
    """دسته‌بندی به دلیل داشتن کالا یا زیرگروه قابل حذف نیست."""


class BulkActionError(Exception):
    """اکشن فله‌ای نامعتبر یا غیرمجاز — پیام آن برای نمایش مستقیم به کاربر امن است."""


def generate_unique_slug(model, name: str, *, store, instance=None) -> str:
    """اسلاگ یکتا در محدوده‌ی همین Store می‌سازد — دو Store مختلف می‌توانند
    اسلاگ یکسان داشته باشند، اما یک Store هرگز نمی‌تواند دو رکورد با یک
    اسلاگ داشته باشد."""
    base = slugify(name, allow_unicode=True) or "item"
    slug = base
    counter = 2
    qs = model.objects.filter(store=store)
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def default_vendor(store):
    """فروشنده‌ی پیش‌فرض همین Store برای اختصاص به کالای تازه.

    اگر Store هنوز هیچ فروشنده‌ای نداشته باشد — حالتِ معمولِ یک فروشگاهِ
    تک‌فروشنده‌ای، که هنوز پنلِ مدیریتِ فروشنده (Vendor CRUD) ندارد — یک
    فروشنده‌ی پیش‌فرض به‌صورت خودکار ساخته می‌شود که نمایانگرِ خودِ Store
    است (owner همان کاربرِ دارایِ نقشِ OWNER). ایجادِ کالا هرگز نباید صرفاً
    به‌خاطرِ نبودِ Vendor شکست بخورد؛ انتخابِ فروشنده‌ی دیگر فقط برایِ
    حالتِ آینده‌یِ چندفروشنده‌ای/مارکت‌پلیس لازم خواهد بود (ADR-1)."""
    vendor = Vendor.objects.filter(store=store, is_active=True).first() or Vendor.objects.filter(store=store).first()
    return vendor or _create_default_vendor(store)


def _create_default_vendor(store):
    """فروشنده‌ی پیش‌فرضِ خودکار برایِ Store — اسلاگ بر پایه‌ی ``store.slug``
    است تا ``get_or_create`` در برابرِ دو درخواستِ همزمان (race) که هر دو
    نبودِ فروشنده را می‌بینند، ایمن بماند (برخلافِ ``generate_unique_slug``
    که این‌جا لازم نیست، چون هر Store دقیقاً یک فروشنده‌ی پیش‌فرض دارد)."""
    from apps.stores.models import StoreMembership

    owner_membership = (
        StoreMembership.objects.filter(
            store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        .select_related("user")
        .first()
    )
    vendor, _created = Vendor.objects.get_or_create(
        store=store, slug=store.slug,
        defaults={"name": store.name, "owner": owner_membership.user if owner_membership else None},
    )
    return vendor


def leaf_categories(store):
    """فقط برگ‌های واقعیِ درختِ همین Store — دسته‌هایی که هم والد دارند (ریشه/گروه
    نیستند) و هم خودشان هیچ فرزندی ندارند — چون کالا فقط می‌تواند به یک برگ
    وصل شود. با هر عمقی از درخت کار می‌کند (گروه → دسته → زیردسته یا فقط
    گروه → دسته‌ی دوسطحیِ قدیمی)، نه فقط دقیقاً دو سطح."""
    return (
        Category.objects.filter(store=store, parent__isnull=False)
        .annotate(child_count=Count("children"))
        .filter(child_count=0)
        .select_related("parent", "parent__parent")
        .order_by("parent__parent__order", "parent__order", "order", "name")
    )


PRODUCT_STATUS_FILTERS = [
    ("", "همه وضعیت‌ها"),
    (Product.Status.ACTIVE, "فعال"),
    (Product.Status.INACTIVE, "غیرفعال"),
    (Product.Status.DRAFT, "پیش‌نویس"),
    ("out", "ناموجود"),
]

#: query-param value -> (order_by fields, label). Whitelisted deliberately —
#: ``order_by(request.GET["sort"])`` directly would let a crafted query
#: string sort by an arbitrary (or nonexistent) column.
PRODUCT_SORT_OPTIONS = {
    "-created_at": (["-created_at"], "جدیدترین"),
    "created_at": (["created_at"], "قدیمی‌ترین"),
    "name": (["name"], "نام (الف تا ی)"),
    "-name": (["-name"], "نام (ی تا الف)"),
    "price": (["price"], "قیمت (کم به زیاد)"),
    "-price": (["-price"], "قیمت (زیاد به کم)"),
    "stock": (["stock"], "موجودی (کم به زیاد)"),
    "-stock": (["-stock"], "موجودی (زیاد به کم)"),
}
DEFAULT_PRODUCT_SORT = "-created_at"


def _category_and_descendant_ids(store, category_id) -> set:
    """شناسه‌ی خودِ دسته به‌علاوه‌ی همه‌ی نوادگانش، در هر عمقی — برایِ فیلترِ
    «این دسته یا هر زیرشاخه‌اش» روی محصولات (Group یا Category هم اکنون
    می‌توانند بیش از یک سطح فرزند داشته باشند، نه فقط سطحِ مستقیم)."""
    category_id = int(category_id)
    ids = {category_id}
    frontier = {category_id}
    while frontier:
        children = set(
            Category.objects.filter(store=store, parent_id__in=frontier).values_list("pk", flat=True)
        )
        frontier = children - ids
        ids |= children
    return ids


#: مقادیرِ مجازِ پارامترِ ``health`` — هرکدام یک شاخصِ سلامتِ داده برایِ
#: کارت‌های داشبورد (نگاه کنید به ``dashboard_service.product_health_counts``).
PRODUCT_HEALTH_FILTERS = {"no_images", "no_seo", "missing_variants"}


def filtered_products(
    store, *, q: str = "", category_id: str = "", status: str = "", brand_id: str = "", sort: str = "",
    health: str = "", product_type: str = "",
):
    qs = (
        Product.objects.filter(store=store)
        .select_related("category", "category__parent", "brand")
        .prefetch_related("images")
        .annotate(
            variant_count=Count("variants", distinct=True),
            active_variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True),
            active_variant_stock=Sum("variants__stock", filter=Q(variants__is_active=True)),
            image_count=Count("images", distinct=True),
        )
    )
    if q:
        qs = qs.filter(models.Q(name__icontains=q) | models.Q(sku__icontains=q))
    if category_id:
        qs = qs.filter(category_id__in=_category_and_descendant_ids(store, category_id))
    if brand_id:
        qs = qs.filter(brand_id=brand_id)
    if status == "out":
        qs = qs.filter(stock=0)
    elif status:
        qs = qs.filter(status=status)
    if product_type in Product.ProductType.values:
        qs = qs.filter(product_type=product_type)

    if health == "no_images":
        qs = qs.filter(image_count=0)
    elif health == "no_seo":
        qs = qs.filter(
            models.Q(seo_title="") | models.Q(seo_title__isnull=True),
            models.Q(seo_description="") | models.Q(seo_description__isnull=True),
        )
    elif health == "missing_variants":
        qs = qs.filter(product_type=Product.ProductType.VARIABLE, variant_count=0)

    order_fields, _label = PRODUCT_SORT_OPTIONS.get(sort, PRODUCT_SORT_OPTIONS[DEFAULT_PRODUCT_SORT])
    return qs.order_by(*order_fields, "pk")


BULK_STATUS_ACTIONS = {
    "activate": Product.Status.ACTIVE,
    "deactivate": Product.Status.INACTIVE,
    "draft": Product.Status.DRAFT,
}


def bulk_set_product_status(store, product_ids, action: str) -> int:
    """Sets ``status`` on every Product in ``product_ids`` that belongs to
    ``store`` — silently ignoring any id that doesn't (never trust a
    caller-supplied id list without a Store filter). Returns the number of
    rows actually changed."""
    if action not in BULK_STATUS_ACTIONS:
        raise BulkActionError(f"اکشن «{action}» نامعتبر است.")
    return Product.objects.filter(store=store, pk__in=product_ids).update(status=BULK_STATUS_ACTIONS[action])


def bulk_delete_products(store, product_ids) -> int:
    """Deletes every Product in ``product_ids`` that belongs to ``store``.
    Returns the number of rows actually deleted."""
    queryset = Product.objects.filter(store=store, pk__in=product_ids)
    count = queryset.count()
    queryset.delete()
    return count


def bulk_assign_category(store, product_ids, category_id) -> int:
    """Assigns ``category_id`` to every Product in ``product_ids`` that
    belongs to ``store`` — but only if ``category_id`` is itself a
    leaf category owned by the same Store (never attach a Store's products
    to another Store's category, and never to a non-leaf category, matching
    the same rule the product form itself enforces)."""
    category = leaf_categories(store).filter(pk=category_id).first()
    if category is None:
        raise BulkActionError("دسته‌بندی انتخاب‌شده معتبر نیست.")
    return Product.objects.filter(store=store, pk__in=product_ids).update(category=category)


def bulk_assign_tax_class(store, product_ids, tax_class_id, *, actor=None) -> int:
    """دسته‌ی مالیاتیِ ``tax_class_id`` را به هر کالای ``product_ids`` که به
    ``store`` تعلق دارد اختصاص می‌دهد — فقط اگر آن دسته‌ی مالیاتی متعلق به
    همین Store باشد (نگاه کنید به checkpoint 3B، ADR-44 — Product.tax_class
    هرگز نباید به دسته‌ی مالیاتیِ فروشگاه دیگری اشاره کند، حتی از طریقِ
    اکشنِ فله‌ای). ثبتِ رخداد در گزارش رخدادها (checkpoint 4 §28)."""
    from apps.orders.models import TaxClass

    tax_class = TaxClass.objects.filter(store=store, pk=tax_class_id, is_active=True).first()
    if tax_class is None:
        raise BulkActionError("دسته‌ی مالیاتیِ انتخاب‌شده معتبر نیست.")
    updated_ids = list(Product.objects.filter(store=store, pk__in=product_ids).values_list("pk", flat=True))
    count = Product.objects.filter(store=store, pk__in=updated_ids).update(tax_class=tax_class)
    if updated_ids:
        from apps.core.services.audit_service import record_audit_event
        # ``object_id`` روی AuditLogEntry یک CharField(max_length=40) است —
        # برای یک اکشنِ فله‌ای، شناسه‌های کامل در ``metadata`` (JSONField،
        # بدونِ محدودیتِ طول) ثبت می‌شوند، نه در همان فیلدِ کوتاه.
        record_audit_event(
            store=store, actor=actor, action_code="product.bulk_tax_class_assigned",
            object_type="Product", object_id="bulk",
            object_label=f"{count} کالا — دسته‌ی مالیاتیِ «{tax_class.name}»",
            after={"tax_class_id": tax_class.pk, "tax_class_code": tax_class.code, "product_count": count},
            metadata={"product_ids": updated_ids[:200]},
        )
    return count


def bulk_clear_tax_class(store, product_ids, *, actor=None) -> int:
    """دسته‌ی مالیاتیِ اختصاصیِ هر کالای ``product_ids`` را پاک می‌کند — کالا
    به دسته‌ی مالیاتیِ پیش‌فرضِ Store (``ShopSettings.default_tax_class``)
    بازمی‌گردد."""
    updated_ids = list(Product.objects.filter(store=store, pk__in=product_ids).values_list("pk", flat=True))
    count = Product.objects.filter(store=store, pk__in=updated_ids).update(tax_class=None)
    if updated_ids:
        from apps.core.services.audit_service import record_audit_event
        record_audit_event(
            store=store, actor=actor, action_code="product.bulk_tax_class_cleared",
            object_type="Product", object_id="bulk",
            object_label=f"{count} کالا — بازگشت به دسته‌ی مالیاتیِ پیش‌فرض",
            after={"tax_class_id": None, "product_count": count},
            metadata={"product_ids": updated_ids[:200]},
        )
    return count


def category_chain(category):
    """زنجیره‌ی کاملِ اجداد این دسته، از ریشه تا خودش — با هر عمقی از درخت کار
    می‌کند (نه فقط دو سطح)، مثل «لوازم جانبی › کیف و کاور › کیف چرمی»."""
    if category is None:
        return "—"
    names = [category.name]
    current = category
    seen_ids = {current.pk}
    while current.parent_id and current.parent_id not in seen_ids:
        current = current.parent
        names.append(current.name)
        seen_ids.add(current.pk)
    return " › ".join(reversed(names))


def category_tree_context(store):
    """درختِ کاملِ دسته‌بندی‌هایِ همین Store (گروه → دسته → زیردسته، با هر
    عمقی) با شمارِ فرزند و کالا در هر گره، برای صفحه‌ی دسته‌بندی‌ها. کالا
    فقط به برگ‌هایِ واقعی وصل می‌شود (نگاه کنید به ``leaf_categories``)،
    پس ``product_count`` روی هر گره جمعِ خودش + همه‌ی نوادگانش است."""
    all_categories = list(Category.objects.filter(store=store).order_by("order", "name"))
    children_by_parent: dict = {}
    for cat in all_categories:
        children_by_parent.setdefault(cat.parent_id, []).append(cat)

    product_counts = dict(
        Product.objects.filter(store=store)
        .values("category_id").annotate(total=models.Count("id")).values_list("category_id", "total")
    )

    def build_node(category):
        children = [build_node(c) for c in children_by_parent.get(category.pk, [])]
        product_count = product_counts.get(category.pk, 0) + sum(c["product_count"] for c in children)
        return {
            "category": category,
            "children": children,
            "is_leaf": not children,
            "product_count": product_count,
        }

    rows = [build_node(root) for root in children_by_parent.get(None, [])]

    def count_descendants(nodes):
        total = 0
        for node in nodes:
            total += 1 + count_descendants(node["children"])
        return total

    return {
        "rows": rows,
        "main_count": len(rows),
        "sub_count": sum(count_descendants(node["children"]) for node in rows),
        "categorized_product_count": Product.objects.filter(store=store).count(),
    }


def can_delete_category(category) -> None:
    """اگر دسته کالا یا زیرگروه داشته باشد، خطای قابل‌نمایش می‌دهد (بدون یتیم‌شدن داده).

    ``category`` از قبل باید با Store درخواست‌کننده تطبیق داده شده باشد
    (فراخوان مسئول آن است)؛ این تابع فقط زیرگروه/کالای همان دسته‌ی مشخص را
    بررسی می‌کند، نه کل دیتابیس."""
    if category.children.exists():
        raise CategoryDeleteError(
            f"گروه «{category.name}» دارای زیرگروه است؛ ابتدا زیرگروه‌ها را حذف کنید."
        )
    if Product.objects.filter(category=category).exists():
        raise CategoryDeleteError(
            f"دسته‌ی «{category.name}» دارای کالا است و قابل حذف نیست."
        )


def reorder_categories(store, ordered_ids: list[int]) -> None:
    """ترتیبِ نمایشِ خواهر-و-برادرهای یک والدِ مشترک را طبقِ ``ordered_ids``
    بازنویسی می‌کند — برایِ مرتب‌سازیِ کشاندنی (drag) در درختِ دسته‌بندی‌ها؛
    مثلِ ``brand_service.reorder_brands``، فقط دسته‌بندی‌هایِ همین Store را
    لمس می‌کند."""
    categories = {c.pk: c for c in Category.objects.filter(store=store, pk__in=ordered_ids)}
    valid_ids = [cat_id for cat_id in ordered_ids if cat_id in categories]
    updated = []
    for order, cat_id in enumerate(valid_ids):
        category = categories[cat_id]
        category.order = order
        updated.append(category)
    if updated:
        Category.objects.bulk_update(updated, ["order"])
