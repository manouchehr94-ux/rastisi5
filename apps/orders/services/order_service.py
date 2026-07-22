"""لایه‌ی سرویس سفارش‌ها — ساخت سفارش از سبد و مدیریت گردش وضعیت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۷ تا ۹.
"""

import random

from django.db import transaction

from apps.cart.services.pricing import cart_totals
from apps.orders.models import Order, OrderItem, OrderStatusHistory

ORDER_CODE_PREFIX = "DM"

ALLOWED_TRANSITIONS = {
    Order.Status.PENDING: {Order.Status.PROCESSING, Order.Status.CANCELED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED, Order.Status.CANCELED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELED: set(),
}

FINAL_STATUSES = {Order.Status.DELIVERED, Order.Status.CANCELED}


def _generate_order_code() -> str:
    while True:
        code = f"{ORDER_CODE_PREFIX}-{random.randint(10000, 99999)}"
        if not Order.objects.filter(code=code).exists():
            return code


def _snapshot_address(address) -> dict:
    return {
        "receiver_name": address.receiver_name,
        "phone": address.phone,
        "province": address.province,
        "city": address.city,
        "postal_code": address.postal_code,
        "full_address": address.full_address,
    }


@transaction.atomic
def create_order_from_cart(cart, *, customer, vendor, address, shipping_method, payment_gateway, coupon=None, note=""):
    """سفارش را از روی سبد خرید می‌سازد و همه‌ی مبالغ را اسنپ‌شات می‌کند."""
    items = list(cart.items.select_related("product", "variant"))
    if not items:
        raise ValueError("سبد خرید خالی است")

    totals = cart_totals(cart, coupon=coupon, shipping_method=shipping_method)

    order = Order.objects.create(
        code=_generate_order_code(),
        customer=customer,
        vendor=vendor,
        address=_snapshot_address(address),
        shipping_method=shipping_method,
        payment_gateway=payment_gateway,
        coupon=coupon,
        items_total=totals["items_total"],
        product_discount=totals["product_discount"],
        coupon_discount=totals["coupon_discount"],
        shipping_cost=totals["shipping_cost"],
        tax=totals["tax"],
        grand_total=totals["grand_total"],
        note=note,
    )

    for item in items:
        unit_price = item.product.final_price
        OrderItem.objects.create(
            order=order,
            product=item.product,
            variant=item.variant,
            product_name=item.product.name,
            quantity=item.quantity,
            unit_price=unit_price,
            line_total=unit_price * item.quantity,
        )

    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=order.status, note="سفارش ثبت شد"
    )

    if coupon is not None and totals["coupon_applied"]:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    return order


@transaction.atomic
def change_order_status(order: Order, to_status: str, *, by=None, note: str = "") -> Order:
    """وضعیت سفارش را تغییر می‌دهد و حتماً یک رکورد OrderStatusHistory می‌سازد."""
    from_status = order.status

    if from_status in FINAL_STATUSES:
        raise ValueError(f"سفارش در وضعیت نهایی «{order.get_status_display()}» است و قابل تغییر نیست")

    if to_status == from_status:
        raise ValueError("وضعیت جدید با وضعیت فعلی یکسان است")

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"گذار از «{from_status}» به «{to_status}» مجاز نیست")

    order.status = to_status
    order.save(update_fields=["status", "updated_at"])

    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=to_status, changed_by=by, note=note
    )

    return order
