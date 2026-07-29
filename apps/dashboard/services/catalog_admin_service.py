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
    """فروشنده‌ی پیش‌فرض همین Store برای اختصاص به کالای تازه — یا ``None``
    اگر هنوز هیچ فروشنده‌ای برای این Store ساخته نشده باشد (فراخوان باید
    این حالت را صریح مدیریت کند، نه این‌که بی‌صدا کالا بدون فروشنده بماند)."""
    return Vendor.objects.filter(store=store, is_active=True).first() or Vendor.objects.filter(store=store).first()


def leaf_categories(store):
    """فقط زیرگروه‌های همین Store (دسته‌هایی که والد دارند) — چون کالا باید به زیرگروه وصل شود."""
    return (
        Category.objects.filter(store=store, parent__isnull=False)
        .select_related("parent")
        .order_by("parent__order", "parent__name", "order", "name")
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


def filtered_products(store, *, q: str = "", category_id: str = "", status: str = "", brand_id: str = "", sort: str = ""):
    qs = (
        Product.objects.filter(store=store)
        .select_related("category", "category__parent", "brand")
        .prefetch_related("images")
        .annotate(
            variant_count=Count("variants", distinct=True),
            active_variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True),
            active_variant_stock=Sum("variants__stock", filter=Q(variants__is_active=True)),
        )
    )
    if q:
        qs = qs.filter(models.Q(name__icontains=q) | models.Q(sku__icontains=q))
    if category_id:
        qs = qs.filter(
            models.Q(category_id=category_id) | models.Q(category__parent_id=category_id)
        )
    if brand_id:
        qs = qs.filter(brand_id=brand_id)
    if status == "out":
        qs = qs.filter(stock=0)
    elif status:
        qs = qs.filter(status=status)

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
    category = Category.objects.filter(store=store, pk=category_id, parent__isnull=False).first()
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
    if category is None:
        return "—"
    if category.parent:
        return f"{category.parent.name} › {category.name}"
    return category.name


def category_tree_context(store):
    """درخت دوسطحی دسته‌بندی‌های همین Store با شمار زیرگروه و کالا، برای صفحه‌ی دسته‌بندی‌ها."""
    mains = list(Category.objects.filter(store=store, parent__isnull=True).order_by("order", "name"))
    children_by_parent = {}
    for child in Category.objects.filter(store=store, parent__isnull=False).order_by("order", "name"):
        children_by_parent.setdefault(child.parent_id, []).append(child)

    product_counts = dict(
        Product.objects.filter(store=store)
        .values("category_id").annotate(total=models.Count("id")).values_list("category_id", "total")
    )

    rows = []
    for main in mains:
        subs = children_by_parent.get(main.id, [])
        sub_ids = [s.id for s in subs]
        prod_count = product_counts.get(main.id, 0) + sum(product_counts.get(sid, 0) for sid in sub_ids)
        rows.append({
            "category": main,
            "subs": [{"category": s, "product_count": product_counts.get(s.id, 0)} for s in subs],
            "product_count": prod_count,
        })

    return {
        "rows": rows,
        "main_count": len(mains),
        "sub_count": sum(len(r["subs"]) for r in rows),
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
