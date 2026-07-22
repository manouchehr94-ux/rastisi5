"""لایه‌ی سرویس تسویه‌حساب — مرحله‌ی ۱ (سبد و آدرس).

انتخاب روش ارسال/پرداخت، کد تخفیف و اطلاعات گیرنده برای کاربر مهمان یا واردشده
در session نگه‌داری می‌شود (سفارش واقعی در مرحله‌ی بعد از روی همین داده ساخته
می‌شود). محاسبه‌ی مبالغ همیشه از طریق apps.cart.services.pricing.cart_totals
انجام می‌گیرد؛ این ماژول فقط انتخاب‌های کاربر را حل و کانتکست صفحه را می‌سازد.
"""

from decimal import Decimal

from apps.cart.models import Coupon
from apps.cart.services.pricing import cart_totals, coupon_is_applicable
from apps.orders.models import PaymentGateway, ShippingMethod

SESSION_KEY = "checkout"

ADDRESS_FIELDS = ["receiver_name", "phone", "province", "city", "postal_code", "full_address", "note"]

EMPTY_TOTALS = {
    "items_total": Decimal("0"),
    "product_discount": Decimal("0"),
    "coupon_discount": Decimal("0"),
    "shipping_cost": Decimal("0"),
    "free_shipping": False,
    "tax": Decimal("0"),
    "grand_total": Decimal("0"),
    "coupon_applied": False,
}


def _state(request) -> dict:
    return request.session.setdefault(SESSION_KEY, {})


def get_address(request) -> dict:
    return _state(request).get("address", {})


def save_address(request, cleaned_data) -> None:
    state = _state(request)
    state["address"] = {field: cleaned_data.get(field, "") for field in ADDRESS_FIELDS}
    request.session.modified = True


def active_shipping_methods():
    return list(ShippingMethod.objects.filter(is_active=True))


def active_payment_gateways():
    return list(PaymentGateway.objects.filter(is_active=True))


def get_selected_shipping_method(request):
    methods = active_shipping_methods()
    if not methods:
        return None
    selected_id = _state(request).get("shipping_method_id")
    for method in methods:
        if method.pk == selected_id:
            return method
    return methods[0]


def set_shipping_method(request, method_id) -> None:
    method = ShippingMethod.objects.filter(pk=method_id, is_active=True).first()
    if method:
        _state(request)["shipping_method_id"] = method.pk
        request.session.modified = True


def get_selected_payment_gateway(request):
    gateways = active_payment_gateways()
    if not gateways:
        return None
    selected_id = _state(request).get("payment_gateway_id")
    for gateway in gateways:
        if gateway.pk == selected_id:
            return gateway
    return gateways[0]


def set_payment_gateway(request, gateway_id) -> None:
    gateway = PaymentGateway.objects.filter(pk=gateway_id, is_active=True).first()
    if gateway:
        _state(request)["payment_gateway_id"] = gateway.pk
        request.session.modified = True


def get_applied_coupon(request, cart):
    """کد تخفیف فعلی نشست را برمی‌گرداند؛ اگر دیگر معتبر نباشد از نشست پاک می‌شود."""
    code = _state(request).get("coupon_code")
    if not code:
        return None
    coupon = Coupon.objects.filter(code=code).first()
    totals = cart_totals(cart)
    if coupon is None or not coupon_is_applicable(coupon, totals["items_total"]):
        _state(request).pop("coupon_code", None)
        request.session.modified = True
        return None
    return coupon


def apply_coupon(request, cart, code: str) -> tuple[bool, str]:
    code = (code or "").strip().upper()
    if not code:
        return False, "لطفاً کد تخفیف را وارد کنید"
    coupon = Coupon.objects.filter(code=code).first()
    totals = cart_totals(cart)
    if coupon is None or not coupon_is_applicable(coupon, totals["items_total"]):
        return False, "کد تخفیف نامعتبر است یا منقضی شده"
    _state(request)["coupon_code"] = coupon.code
    request.session.modified = True
    label = coupon.label or coupon.get_type_display()
    return True, f"کد «{coupon.code}» با موفقیت اعمال شد — {label}"


def remove_coupon(request) -> None:
    _state(request).pop("coupon_code", None)
    request.session.modified = True


def build_context(request, cart) -> dict:
    """کانتکست کامل صفحه‌ی تسویه‌حساب مرحله‌ی ۱ را می‌سازد."""
    is_empty = cart is None or not cart.items.exists()

    shipping_methods = active_shipping_methods()
    payment_gateways = active_payment_gateways()
    selected_shipping = None if is_empty else get_selected_shipping_method(request)
    selected_payment = None if is_empty else get_selected_payment_gateway(request)
    coupon = None if is_empty else get_applied_coupon(request, cart)

    if is_empty:
        totals = dict(EMPTY_TOTALS)
        item_count = 0
    else:
        totals = cart_totals(cart, coupon=coupon, shipping_method=selected_shipping)
        item_count = sum(item.quantity for item in cart.items.all())

    shipping_rows = [
        {
            "method": method,
            "selected": bool(selected_shipping and method.pk == selected_shipping.pk),
            "free": totals["free_shipping"],
        }
        for method in shipping_methods
    ]
    payment_rows = [
        {"gateway": gateway, "selected": bool(selected_payment and gateway.pk == selected_payment.pk)}
        for gateway in payment_gateways
    ]

    return {
        "cart": cart,
        "is_empty": is_empty,
        "item_count": item_count,
        "address": get_address(request),
        "shipping_rows": shipping_rows,
        "payment_rows": payment_rows,
        "coupon": coupon,
        "totals": totals,
        "savings": totals["product_discount"] + totals["coupon_discount"],
    }
