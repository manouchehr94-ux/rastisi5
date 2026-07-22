"""قواعد کسب‌وکار قیمت‌گذاری — سبد خرید، کد تخفیف، ارسال رایگان، مالیات.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶. هیچ‌کدام از این محاسبات نباید در
ویو یا تمپلیت تکرار شود؛ همیشه از طریق این توابع خالص انجام شوند.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.utils import timezone

from apps.cart.models import Coupon

DEFAULT_FREE_SHIPPING_THRESHOLD = Decimal("500000")
DEFAULT_TAX_PERCENT = Decimal("9")


def product_final_price(product) -> Decimal:
    """قیمت نهایی کالا = price * (1 - discount_percent/100)، گرد شده."""
    return product.final_price


def _free_shipping_threshold() -> Decimal:
    return Decimal(getattr(settings, "SHOP_FREE_SHIPPING_THRESHOLD", DEFAULT_FREE_SHIPPING_THRESHOLD))


def _tax_percent() -> Decimal:
    return Decimal(getattr(settings, "SHOP_TAX_PERCENT", DEFAULT_TAX_PERCENT))


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def coupon_is_applicable(coupon: Coupon, items_total: Decimal) -> bool:
    """آیا این کد تخفیف در حال حاضر قابل اعمال است (فعال، منقضی‌نشده، سقف استفاده و حداقل سفارش رعایت‌شده)."""
    if coupon is None:
        return False
    if not coupon.is_active:
        return False
    if coupon.expires_at and coupon.expires_at <= timezone.now():
        return False
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return False
    if items_total < coupon.min_order:
        return False
    return True


def cart_totals(cart, coupon: Coupon | None = None, shipping_method=None) -> dict:
    """جمع کامل سبد خرید را طبق قواعد کسب‌وکار محاسبه می‌کند.

    خروجی: items_total, product_discount, coupon_discount, shipping_cost,
    free_shipping (bool), tax, grand_total, coupon_applied (bool)
    """
    items = list(cart.items.select_related("product").all())

    raw_total = Decimal("0")
    items_total = Decimal("0")
    for item in items:
        raw_total += item.product.price * item.quantity
        items_total += product_final_price(item.product) * item.quantity

    product_discount = raw_total - items_total

    coupon_applied = coupon_is_applicable(coupon, items_total)
    coupon_discount = Decimal("0")
    free_shipping_by_coupon = False
    if coupon_applied:
        if coupon.type == Coupon.Type.PERCENT:
            coupon_discount = _round(items_total * coupon.value / Decimal("100"))
        elif coupon.type == Coupon.Type.FIXED:
            coupon_discount = min(coupon.value, items_total)
        elif coupon.type == Coupon.Type.FREE_SHIP:
            free_shipping_by_coupon = True

    after_coupon = items_total - coupon_discount

    free_by_threshold = items_total >= _free_shipping_threshold()
    free_shipping = free_by_threshold or free_shipping_by_coupon

    if free_shipping or shipping_method is None:
        shipping_cost = Decimal("0")
    else:
        shipping_cost = shipping_method.cost

    tax = _round(after_coupon * _tax_percent() / Decimal("100"))
    grand_total = after_coupon + shipping_cost + tax

    return {
        "items_total": items_total,
        "product_discount": product_discount,
        "coupon_discount": coupon_discount,
        "shipping_cost": shipping_cost,
        "free_shipping": free_shipping,
        "tax": tax,
        "grand_total": grand_total,
        "coupon_applied": coupon_applied,
    }
