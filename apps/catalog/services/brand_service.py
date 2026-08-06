"""لایه‌ی سرویس برند (Brand).

مثل ``apps.catalog.services.attribute_service``: ایجاد/ویرایش/غیرفعال‌سازی/
فعال‌سازی/حذف برند باید فقط از این‌جا عبور کند تا اعتبارسنجی و قاعده‌ی
«حذف امن» (برند استفاده‌شده روی کالا قابل حذف نیست، فقط قابل غیرفعال‌سازی)
در view تکرار نشود.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Brand, Product
from apps.core.utils import normalize_text


class BrandError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت برند."""


class BrandInUseError(BrandError):
    """تلاش برای حذف قطعی برندی که هنوز روی حداقل یک کالا استفاده می‌شود."""


class BrandReorderError(BrandError):
    """ورودیِ مرتب‌سازی نامعتبر است (شناسه‌ی تکراری) — هیچ ردیفی تغییر نکرد."""


def _unique_slug(store, name: str, *, exclude_pk=None) -> str:
    base = slugify(name, allow_unicode=True).strip("-") or "brand"
    candidate = base
    counter = 2
    qs = Brand.objects.filter(store=store)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


@transaction.atomic
def create_brand(store, *, name, name_en="", description="", website="", country="", logo=None) -> Brand:
    name = normalize_text(name)
    if not name:
        raise BrandError("نام برند نمی‌تواند خالی باشد.")
    brand = Brand(
        store=store, name=name, name_en=(name_en or "").strip(), description=description,
        website=website, country=country,
        slug=_unique_slug(store, name),
        sort_order=Brand.objects.filter(store=store).count(),
    )
    if logo is not None:
        brand.logo = logo
    try:
        brand.full_clean()
    except ValidationError as exc:
        raise BrandError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    brand.save()
    return brand


@transaction.atomic
def update_brand(brand: Brand, **fields) -> Brand:
    for key, value in fields.items():
        setattr(brand, key, value)
    try:
        brand.full_clean()
    except ValidationError as exc:
        raise BrandError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    brand.save()
    return brand


def archive_brand(brand: Brand) -> Brand:
    """برند را غیرفعال می‌کند (نه حذف) — همیشه امن، حتی اگر روی کالایی استفاده شده باشد."""
    if brand.is_active:
        brand.is_active = False
        brand.save(update_fields=["is_active", "updated_at"])
    return brand


def activate_brand(brand: Brand) -> Brand:
    if not brand.is_active:
        brand.is_active = True
        brand.save(update_fields=["is_active", "updated_at"])
    return brand


def can_delete_brand(brand: Brand) -> None:
    """اگر برند روی کالایی استفاده شده باشد، خطای قابل‌نمایش می‌دهد."""
    if Product.objects.filter(brand=brand).exists():
        raise BrandInUseError(
            f"برند «{brand.name}» روی حداقل یک کالا استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید."
        )


@transaction.atomic
def delete_brand(brand: Brand) -> None:
    can_delete_brand(brand)
    brand.delete()


@transaction.atomic
def reorder_brands(store, ordered_ids: list[int]) -> None:
    """ترتیبِ نمایشِ برندها را طبق ``ordered_ids`` بازنویسی می‌کند — برایِ
    مرتب‌سازیِ کشاندنی (drag) در صفحه‌ی برندها؛ فقط برندهایِ همین Store را
    لمس می‌کند و شناسه‌های نامعتبر/متعلق‌به‌فروشگاهِ‌دیگر را بی‌صدا نادیده
    می‌گیرد (همان الگویِ ``variant_engine_service.reorder_option_values``).

    قرارداد (A4 — رفع بدهیِ اتمیک‌بودنِ شناسایی‌شده در ممیزی):
    - شناسه‌ی تکراری در ``ordered_ids`` کل عملیات را رد می‌کند (هیچ ردیفی
      تغییر نمی‌کند) — ورودی نامعتبر است، نه چیزی که بشود نادیده گرفت.
    - شناسه‌ی نامعتبر/متعلق‌به‌فروشگاهِ‌دیگر بی‌صدا از فهرست حذف می‌شود
      (رفتار قبلی، بدون تغییر).
    - کل عملیات داخل یک تراکنش است: یا ترتیبِ کامل ذخیره می‌شود یا هیچ‌کدام.
    """
    if len(set(ordered_ids)) != len(ordered_ids):
        raise BrandReorderError("فهرست مرتب‌سازی شامل شناسه‌ی تکراری است.")

    valid_id_set = set(Brand.objects.filter(store=store, pk__in=ordered_ids).values_list("pk", flat=True))
    ordered_valid_ids = [brand_id for brand_id in ordered_ids if brand_id in valid_id_set]
    for order, brand_id in enumerate(ordered_valid_ids):
        Brand.objects.filter(pk=brand_id, store=store).update(sort_order=order)
