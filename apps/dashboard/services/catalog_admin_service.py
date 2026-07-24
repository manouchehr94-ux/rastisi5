"""سرویس مدیریت کاتالوگ از پنل مدیریت — محصولات و دسته‌بندی‌ها.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۲. تولید اسلاگ یکتا و
حذف امن دسته‌بندی (بدون یتیم‌شدن محصول/زیرگروه) اینجا متمرکز شده‌اند تا در
ویو تکرار نشوند.
"""

from django.db import models
from django.db.models import Count, Q, Sum
from django.utils.text import slugify

from apps.catalog.models import Category, Product, Vendor

LOW_STOCK_THRESHOLD = 10


class CategoryDeleteError(Exception):
    """دسته‌بندی به دلیل داشتن کالا یا زیرگروه قابل حذف نیست."""


def generate_unique_slug(model, name: str, *, instance=None) -> str:
    base = slugify(name, allow_unicode=True) or "item"
    slug = base
    counter = 2
    qs = model.objects.all()
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def default_vendor():
    return Vendor.objects.filter(is_active=True).first() or Vendor.objects.first()


def leaf_categories():
    """فقط زیرگروه‌ها (دسته‌هایی که والد دارند) — چون کالا باید به زیرگروه وصل شود."""
    return (
        Category.objects.filter(parent__isnull=False)
        .select_related("parent")
        .order_by("parent__order", "parent__name", "order", "name")
    )


PRODUCT_STATUS_FILTERS = [
    ("", "همه وضعیت‌ها"),
    (Product.Status.ACTIVE, "فعال"),
    (Product.Status.INACTIVE, "غیرفعال"),
    ("out", "ناموجود"),
]


def filtered_products(*, q: str = "", category_id: str = "", status: str = ""):
    qs = (
        Product.objects.select_related("category", "category__parent")
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


def category_tree_context():
    """درخت دوسطحی دسته‌بندی‌ها با شمار زیرگروه و کالای هر گروه اصلی، برای صفحه‌ی دسته‌بندی‌ها."""
    mains = list(Category.objects.filter(parent__isnull=True).order_by("order", "name"))
    children_by_parent = {}
    for child in Category.objects.filter(parent__isnull=False).order_by("order", "name"):
        children_by_parent.setdefault(child.parent_id, []).append(child)

    product_counts = dict(
        Product.objects.values("category_id").annotate(total=models.Count("id")).values_list("category_id", "total")
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
        "categorized_product_count": Product.objects.count(),
    }


def can_delete_category(category) -> None:
    """اگر دسته کالا یا زیرگروه داشته باشد، خطای قابل‌نمایش می‌دهد (بدون یتیم‌شدن داده)."""
    if category.children.exists():
        raise CategoryDeleteError(
            f"گروه «{category.name}» دارای زیرگروه است؛ ابتدا زیرگروه‌ها را حذف کنید."
        )
    if Product.objects.filter(category=category).exists():
        raise CategoryDeleteError(
            f"دسته‌ی «{category.name}» دارای کالا است و قابل حذف نیست."
        )
