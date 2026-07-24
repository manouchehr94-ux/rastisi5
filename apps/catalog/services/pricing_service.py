"""سرویس مرجع محاسبه‌ی قیمت نهایی کالا — با/بدون تنوع انتخابی.

تنها منبع حقیقت برای «قیمت نهایی قابل‌پرداخت» یک کالا (با در نظر گرفتن
تغییر قیمت مقدار تنوع و درصد تخفیف کالا). سبد خرید و سفارش باید همیشه از
همین تابع استفاده کنند، نه از محاسبه‌ی مستقل در view/template/جاوااسکریپت.
"""

from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.models import Product, ProductVariant


class PricingError(Exception):
    """خطای قابل‌نمایش هنگام محاسبه‌ی قیمت (مثلاً تنوع متعلق به کالای دیگر)."""


def resolve_effective_price(product: Product, variant: ProductVariant | None = None) -> Decimal:
    """قیمت نهایی = (قیمت پایه‌ی کالا + تغییر قیمت مقدار تنوع) با اعمال درصد تخفیف کالا.

    اگر ``variant`` داده شود، باید متعلق به همین ``product`` باشد — در غیر
    این صورت PricingError صادر می‌شود تا هرگز تنوع کالای دیگری قیمت‌گذاری نشود.
    """
    if variant is not None and variant.product_id != product.pk:
        raise PricingError("این مقدار تنوع متعلق به کالای دیگری است.")

    base = product.price + (variant.extra_price if variant is not None else Decimal("0"))
    factor = (Decimal(100) - product.discount_percent) / Decimal(100)
    return (base * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def is_variant_purchasable(variant: ProductVariant) -> bool:
    """آیا این مقدار تنوع قابل‌خرید است (فعال و موجودی مثبت)."""
    return variant.is_active and variant.stock > 0
