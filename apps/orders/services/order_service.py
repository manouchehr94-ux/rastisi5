"""لایه‌ی سرویس سفارش‌ها — ساخت سفارش از سبد و مدیریت گردش وضعیت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۷ تا ۹.
"""

import random

from django.db import transaction
from django.db.models import F

from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Product
from apps.core.utils import format_toman
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.sms.events import SmsEvent
from apps.sms.services.sms_service import send_event_sms

ORDER_CODE_PREFIX = "DM"

# رویداد پیامکی متناظر با هر وضعیت مقصد سفارش (پردازش/ارسال/تحویل/لغو).
STATUS_SMS_EVENTS = {
    Order.Status.PROCESSING: SmsEvent.ORDER_PROCESSING,
    Order.Status.SHIPPED: SmsEvent.ORDER_SHIPPED,
    Order.Status.DELIVERED: SmsEvent.ORDER_DELIVERED,
    Order.Status.CANCELED: SmsEvent.ORDER_CANCELED,
}


def _order_sms_context(order: Order) -> dict:
    return {
        "customer_name": order.customer.full_name,
        "order_code": order.code,
        "amount": format_toman(order.grand_total, with_unit=False),
        "tracking_code": order.tracking_code,
    }

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

    for item in items:
        if item.quantity > item.product.stock:
            raise ValueError(f"موجودی «{item.product.name}» کافی نیست")

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
        Product.objects.filter(pk=item.product_id).update(stock=F("stock") - item.quantity)

    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=order.status, note="سفارش ثبت شد"
    )

    if coupon is not None and totals["coupon_applied"]:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    transaction.on_commit(
        lambda: send_event_sms(SmsEvent.ORDER_PLACED, order.customer.phone, _order_sms_context(order))
    )

    return order


@transaction.atomic
def change_order_status(
    order: Order, to_status: str, *, by=None, note: str = "", tracking_code: str = ""
) -> Order:
    """وضعیت سفارش را تغییر می‌دهد و حتماً یک رکورد OrderStatusHistory می‌سازد.

    tracking_code فقط برای گذار به «ارسال شده» معنا دارد و روی سفارش ذخیره
    می‌شود تا در پیامک اطلاع‌رسانی درج شود.
    """
    from_status = order.status

    if from_status in FINAL_STATUSES:
        raise ValueError(f"سفارش در وضعیت نهایی «{order.get_status_display()}» است و قابل تغییر نیست")

    if to_status == from_status:
        raise ValueError("وضعیت جدید با وضعیت فعلی یکسان است")

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"گذار از «{from_status}» به «{to_status}» مجاز نیست")

    update_fields = ["status", "updated_at"]
    order.status = to_status
    if to_status == Order.Status.SHIPPED and tracking_code:
        order.tracking_code = tracking_code
        update_fields.append("tracking_code")
    order.save(update_fields=update_fields)

    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=to_status, changed_by=by, note=note
    )

    sms_event = STATUS_SMS_EVENTS.get(to_status)
    if sms_event:
        transaction.on_commit(
            lambda: send_event_sms(sms_event, order.customer.phone, _order_sms_context(order))
        )

    return order
