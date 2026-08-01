"""لایه‌ی سرویس تنوع کالا — تجزیه‌ی ورودی دسته‌ای، ایجاد/ویرایش/حذف مقدار تنوع،
تغییر ترتیب، کپی ساختار تنوع بین کالاها، و قواعد ایمن تغییر نوع کالا (ساده/دارای تنوع).

هیچ محاسبه یا اعتبارسنجی مهم نباید در view یا template تکرار شود؛ همه از
همین توابع عبور می‌کنند.
"""

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Product, ProductVariant
from apps.core.utils import normalization_key, normalize_digits, normalize_text

_BULK_DELIMITER_RE = re.compile(r"[،,;؛\n\r]+")


class VariantError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت تنوع کالا."""


class ProductTypeError(Exception):
    """خطای قابل‌نمایش هنگام تغییر نوع کالا (ساده/دارای تنوع)."""


def parse_bulk_values(raw: str) -> list[str]:
    """رشته‌ی ورودی سریع را به فهرست مقادیر یکتا و مرتب تبدیل می‌کند.

    از میان کاما فارسی/انگلیسی، سمیکالن فارسی/انگلیسی و خط جدید به‌عنوان
    جداکننده پشتیبانی می‌کند؛ ارقام فارسی/عربی را نرمال، فاصله‌های اضافه را
    حذف، مقادیر خالی را نادیده و مقادیر تکراری (با چشم‌پوشی از فاصله/ارقام) را
    فقط یک‌بار نگه می‌دارد.
    """
    if not raw:
        return []
    normalized = normalize_digits(raw)
    parts = _BULK_DELIMITER_RE.split(normalized)

    seen = set()
    result = []
    for part in parts:
        cleaned = normalize_text(part)
        if not cleaned:
            continue
        key = normalization_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def generate_variant_sku(product: Product, value: str) -> str:
    """کد کالای پیش‌فرض برای یک مقدار تنوع می‌سازد: <SKU کالا>-<مقدار اسلاگ‌شده>، با پسوند عددی در تعارض.

    یکتایی SKU در محدوده‌ی همان Store بررسی می‌شود — دو Store مختلف
    می‌توانند SKU یکسان داشته باشند."""
    base = f"{product.sku}-{slugify(value, allow_unicode=True)}".strip("-").upper()
    if not base:
        base = f"{product.sku}-VAR"
    candidate = base
    counter = 2
    while ProductVariant.objects.filter(store_id=product.store_id, sku=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _next_display_order(product: Product) -> int:
    last = product.variants.order_by("-display_order").first()
    return (last.display_order + 1) if last else 0


def _check_sku_unique(sku: str, *, store, exclude_pk=None):
    if not sku:
        return
    qs = ProductVariant.objects.filter(store=store, sku=sku)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise VariantError(f"کد کالای «{sku}» قبلاً برای یک تنوع دیگر استفاده شده است.")


@transaction.atomic
def create_variant(
    product: Product, *, attribute: str, value: str, stock: int = 0,
    extra_price=0, sku: str = "", value_hex: str = "", is_active: bool = True,
    display_order: int | None = None, _enforce_limit: bool = True,
) -> ProductVariant:
    """یک مقدار تنوع جدید برای کالا می‌سازد؛ اعتبارسنجی و یکتایی کد کالا را رعایت می‌کند.

    گیتِ سقفِ ``catalog.variants`` و وضعیتِ اشتراک اینجا اعمال می‌شود
    (checkpoint 5A، ADR-69/§28). فراخوان‌هایِ فله‌ای (``bulk_create_variants``،
    ``copy_variant_structure``) سقف را یک‌جا رویِ کلِ افزایشِ درخواستی بررسی
    و سپس با ``_enforce_limit=False`` این گیتِ تک‌رکوردی را غیرفعال می‌کنند تا
    سقف دوباره‌شماری نشود.
    """
    if _enforce_limit:
        from apps.subscriptions.services.enforcement import enforce_can_create_variants

        enforce_can_create_variants(product.store)
    sku = normalize_text(sku)
    if not sku:
        sku = generate_variant_sku(product, value)
    else:
        _check_sku_unique(sku, store=product.store)

    if stock < 0:
        raise VariantError("موجودی نمی‌تواند منفی باشد.")

    variant = ProductVariant(
        product=product, store=product.store, attribute=attribute, value=value, stock=stock,
        extra_price=extra_price, sku=sku, value_hex=value_hex, is_active=is_active,
        display_order=display_order if display_order is not None else _next_display_order(product),
    )
    try:
        variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    except ValidationError as exc:
        raise VariantError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    if is_active and ProductVariant.objects.filter(
        product=product, normalized_attribute=normalization_key(attribute),
        normalized_value=normalization_key(value), is_active=True,
    ).exists():
        raise VariantError(f"مقدار «{value}» قبلاً برای تنوع «{attribute}» ثبت شده است.")
    variant.save()
    return variant


@transaction.atomic
def bulk_create_variants(
    product: Product, *, attribute: str, raw_values: str, default_stock: int = 0, default_extra_price=0,
    is_active: bool = True,
) -> tuple[list[ProductVariant], list[str]]:
    """چند مقدار تنوع را یک‌جا از روی ورودی سریع می‌سازد؛ رکوردهای تکراری را رد و پیام می‌دهد.

    خروجی: (فهرست رکوردهای ساخته‌شده، فهرست پیام‌های رد‌شده/خطا)
    """
    attribute = normalize_text(attribute)
    if not attribute:
        raise VariantError("نام تنوع نمی‌تواند خالی باشد.")

    values = parse_bulk_values(raw_values)
    if not values:
        raise VariantError("هیچ مقدار معتبری در ورودی سریع یافت نشد.")

    existing_keys = set(
        product.variants.filter(is_active=True, normalized_attribute=normalization_key(attribute)).values_list(
            "normalized_value", flat=True
        )
    )

    # گیتِ سقف یک‌جا رویِ کلِ افزایشِ درخواستی بررسی می‌شود (§28: «Bulk creation
    # checks total requested increment»)، نه رکورد‌به‌رکورد — تکراری‌هایی که رد
    # می‌شوند صندلی مصرف نمی‌کنند، پس از شمارش کنار گذاشته می‌شوند. اگر سقف نقض
    # شود کلِ تراکنش رد می‌شود و هیچ رکوردی بی‌سروصدا حذف/کوتاه نمی‌گردد.
    to_create_count = sum(
        1 for value in values
        if not (is_active and normalization_key(value) in existing_keys)
    )
    if to_create_count:
        from apps.subscriptions.services.enforcement import enforce_can_create_variants

        enforce_can_create_variants(product.store, count=to_create_count)

    created = []
    skipped = []
    for value in values:
        key = normalization_key(value)
        if is_active and key in existing_keys:
            skipped.append(f"«{value}» تکراری بود و رد شد.")
            continue
        variant = create_variant(
            product, attribute=attribute, value=value,
            stock=default_stock, extra_price=default_extra_price, is_active=is_active,
            _enforce_limit=False,
        )
        if is_active:
            existing_keys.add(key)
        created.append(variant)

    return created, skipped


@transaction.atomic
def update_variant(
    variant: ProductVariant, *, attribute=None, value=None, stock=None,
    extra_price=None, sku=None, value_hex=None, is_active=None,
) -> ProductVariant:
    """یک مقدار تنوع را ویرایش می‌کند؛ یکتایی مقدار و کد کالا را دوباره بررسی می‌کند."""
    if attribute is not None:
        variant.attribute = attribute
    if value is not None:
        variant.value = value
    if stock is not None:
        if stock < 0:
            raise VariantError("موجودی نمی‌تواند منفی باشد.")
        variant.stock = stock
    if extra_price is not None:
        variant.extra_price = extra_price
    if value_hex is not None:
        variant.value_hex = value_hex
    if is_active is not None:
        variant.is_active = is_active
    if sku is not None:
        sku = normalize_text(sku)
        if sku != variant.sku:
            _check_sku_unique(sku, store=variant.product.store, exclude_pk=variant.pk)
        variant.sku = sku

    try:
        variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    except ValidationError as exc:
        raise VariantError("؛ ".join(sum(exc.message_dict.values(), []))) from exc

    if variant.is_active:
        conflict = ProductVariant.objects.filter(
            product=variant.product,
            normalized_attribute=normalization_key(variant.attribute),
            normalized_value=normalization_key(variant.value),
            is_active=True,
        ).exclude(pk=variant.pk)
        if conflict.exists():
            raise VariantError(f"مقدار «{variant.value}» قبلاً برای تنوع «{variant.attribute}» ثبت شده است.")

    variant.save()
    return variant


def duplicate_variant(variant: ProductVariant) -> ProductVariant:
    """یک کپیِ ویرایش‌پذیر از این تنوع می‌سازد — مقدار با پسوندِ «(کپی)» تا با
    قاعده‌ی یکتاییِ product+attribute+value تعارض نکند، SKU تازه به‌صورتِ
    خودکار تولید می‌شود (نه کپیِ SKU اصلی، چون SKU باید در Store یکتا بماند).
    برایِ ساختنِ سریعِ یک تنوعِ مشابه (مثلاً نسخه‌ی «پرمیوم» از رنگِ موجود) و
    سپس ویرایشِ جزئیِ آن."""
    return create_variant(
        variant.product, attribute=variant.attribute, value=f"{variant.value} (کپی)",
        stock=0, extra_price=variant.extra_price, value_hex=variant.value_hex, is_active=False,
    )


def deactivate_variant(variant: ProductVariant) -> ProductVariant:
    """مقدار تنوع را غیرفعال می‌کند (به‌جای حذف قطعی) تا سفارش‌های قبلی معتبر بمانند."""
    if variant.is_active:
        variant.is_active = False
        variant.save(update_fields=["is_active", "updated_at"])
    return variant


def delete_variant(variant: ProductVariant) -> None:
    """مقدار تنوع را حذف می‌کند. اگر در سفارشی استفاده شده باشد، به‌جای حذف باید غیرفعال شود."""
    if variant.order_items.exists():
        raise VariantError(
            "این مقدار تنوع در سفارش‌های ثبت‌شده استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید."
        )
    variant.delete()


@transaction.atomic
def reorder_variants(product: Product, ordered_ids: list[int]) -> None:
    """ترتیب نمایش مقادیر تنوع کالا را طبق فهرست شناسه‌ی ارسالی تنظیم می‌کند.

    فقط تنوع‌هایی که واقعاً متعلق به همین کالا هستند به‌روزرسانی می‌شوند تا
    یک تنوع از کالای دیگر هرگز پذیرفته نشود.
    """
    variants = {v.pk: v for v in product.variants.filter(pk__in=ordered_ids)}
    valid_ids = [variant_id for variant_id in ordered_ids if variant_id in variants]
    updated = []
    for order, variant_id in enumerate(valid_ids):
        variant = variants[variant_id]
        variant.display_order = order
        updated.append(variant)
    if updated:
        ProductVariant.objects.bulk_update(updated, ["display_order"])


@transaction.atomic
def copy_variant_structure(source: Product, target: Product) -> list[ProductVariant]:
    """نام تنوع، مقادیر و ترتیب نمایش را از یک کالا به کالای دیگر کپی می‌کند.

    کد کالا، بارکد و موجودی/تغییر قیمت کپی نمی‌شوند (موجودی صفر و تغییر قیمت
    صفر شروع می‌شوند) تا از سرریز داده‌ی فروش/انبار کالای مبدأ جلوگیری شود.
    کالای مبدأ هرگز تغییر نمی‌کند.
    """
    if source.pk == target.pk:
        raise VariantError("کالای مبدأ و مقصد نمی‌توانند یکسان باشند.")
    if source.store_id != target.store_id:
        raise VariantError("کالای مبدأ و مقصد باید متعلق به یک فروشگاه باشند.")

    source_variants = list(
        source.variants.filter(is_active=True).order_by("display_order", "attribute", "value")
    )
    # سقف یک‌جا رویِ کلِ تنوع‌هایِ کپی‌شونده بررسی می‌شود (§28)، سپس گیتِ
    # تک‌رکوردیِ ``create_variant`` غیرفعال تا دوباره‌شماری نشود.
    if source_variants:
        from apps.subscriptions.services.enforcement import enforce_can_create_variants

        enforce_can_create_variants(target.store, count=len(source_variants))

    created = []
    for source_variant in source_variants:
        variant = create_variant(
            target, attribute=source_variant.attribute, value=source_variant.value,
            stock=0, extra_price=0, value_hex=source_variant.value_hex,
            _enforce_limit=False,
        )
        created.append(variant)
    return created


def can_activate_as_variable(product: Product) -> bool:
    """آیا کالا حداقل یک مقدار تنوع فعال دارد تا بتواند به‌عنوان «دارای تنوع» قابل‌فروش باشد."""
    return product.variants.filter(is_active=True).exists()


@transaction.atomic
def set_product_type(product: Product, product_type: str) -> Product:
    """نوع کالا (ساده/دارای تنوع) را با رعایت قواعد ایمن تغییر می‌دهد.

    ساده → دارای تنوع: همیشه مجاز است (مدیر باید بعداً حداقل یک مقدار تنوع فعال اضافه کند).
    دارای تنوع → ساده: تا وقتی حداقل یک مقدار تنوع (فعال یا غیرفعال) وجود دارد
    مسدود می‌شود تا داده‌ی موجودی/کد کالا بی‌سروصدا از دست نرود؛ مدیر باید
    ابتدا همه‌ی مقادیر تنوع را حذف کند.
    """
    if product_type not in Product.ProductType.values:
        raise ProductTypeError("نوع کالا نامعتبر است.")

    if product_type == Product.ProductType.SIMPLE and product.variants.exists():
        raise ProductTypeError(
            "این کالا دارای مقادیر تنوع است؛ برای تبدیل به کالای ساده ابتدا همه‌ی تنوع‌ها را حذف کنید."
        )

    product.product_type = product_type
    product.save(update_fields=["product_type", "updated_at"])
    return product
