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
    ("out", "ناموجود"),
]


def filtered_products(store, *, q: str = "", category_id: str = "", status: str = ""):
    qs = (
        Product.objects.filter(store=store)
        .select_related("category", "category__parent")
        .prefetch_related("images")
        .annotate(
            variant_count=Count("variants", distinct=True),
            active_variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True),
            active_variant_stock=Sum("variants__stock", filter=Q(variants__is_active=True)),
        )
        .order_by("-created_at")
    )
    if q:
        qs = qs.filter(models.Q(name__icontains=q) | models.Q(sku__icontains=q))
    if category_id:
        qs = qs.filter(
            models.Q(category_id=category_id) | models.Q(category__parent_id=category_id)
        )
    if status == "out":
        qs = qs.filter(stock=0)
    elif status:
        qs = qs.filter(status=status)
    return qs


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
