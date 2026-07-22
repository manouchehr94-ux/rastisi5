import json

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cart.models import CartItem
from apps.cart.services.cart_service import get_cart

from .forms import CheckoutAddressForm
from .models import Order
from .services import checkout_service
from .services.payment_service import simulate_payment


def _get_own_order(request, code, queryset=None):
    if not (request.user.is_authenticated and hasattr(request.user, "customer_profile")):
        raise Http404
    queryset = Order.objects.all() if queryset is None else queryset
    order = queryset.filter(code=code, customer=request.user.customer_profile).first()
    if order is None:
        raise Http404
    return order


def _render_body(request, cart, *, address_form=None, coupon_input="", coupon_error=""):
    context = checkout_service.build_context(request, cart)
    context["address_form"] = address_form or CheckoutAddressForm(initial=context["address"])
    context["coupon_input"] = coupon_input
    context["coupon_error"] = coupon_error
    return render(request, "orders/partials/checkout_body.html", context)


def _dynamic_response(request, cart, *, toast_message=None, toast_type="ok", **extra):
    response = _render_body(request, cart, **extra)
    if toast_message:
        response["HX-Trigger"] = json.dumps({"toast": {"message": toast_message, "type": toast_type}})
    return response


def checkout_step1(request):
    cart = get_cart(request, create=True)
    context = checkout_service.build_context(request, cart)
    context["address_form"] = CheckoutAddressForm(initial=context["address"])
    context["coupon_input"] = ""
    return render(request, "orders/checkout_step1.html", context)


@require_POST
def checkout_pay(request):
    """اعتبارسنجی آدرس + ساخت سفارش از سبد + هدایت به شروع پرداخت.

    اگر کاربر مهمان باشد (Order.customer الزامی است)، آدرس در session ذخیره
    و مودال ورود باز می‌شود؛ ادامه‌ی پرداخت پس از ورود ممکن است.
    """
    cart = get_cart(request, create=True)
    form = CheckoutAddressForm(request.POST)
    if not form.is_valid():
        return _dynamic_response(
            request, cart,
            toast_message="لطفاً خطاهای فرم را برطرف کنید", toast_type="err",
            address_form=form,
        )

    checkout_service.save_address(request, form.cleaned_data)

    if not (request.user.is_authenticated and hasattr(request.user, "customer_profile")):
        response = _render_body(request, cart, address_form=CheckoutAddressForm(initial=form.cleaned_data))
        response["HX-Trigger"] = json.dumps({
            "toast": {"message": "برای تکمیل خرید ابتدا وارد حساب کاربری شوید", "type": "info"},
            "open-login": {},
        })
        return response

    try:
        order = checkout_service.finalize_order(request, cart, request.user.customer_profile)
    except checkout_service.CheckoutError as exc:
        return _dynamic_response(
            request, cart, toast_message=str(exc), toast_type="err",
            address_form=CheckoutAddressForm(initial=form.cleaned_data),
        )

    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse("orders:payment-start", args=[order.code])
    return response


def payment_start(request, code):
    """نقطه‌ی شروع پرداخت — جای اتصال درگاه واقعی بانکی در آینده.

    فعلاً مستقیم به callback با نتیجه‌ی موفق هدایت می‌شود؛ وقتی درگاه واقعی
    وصل شود، این ویو باید کاربر را به آدرس درگاه بانکی هدایت کند و درگاه پس
    از پرداخت به payment_callback برمی‌گردد.
    """
    order = _get_own_order(request, code)
    if order.payment_status != Order.PaymentStatus.PENDING:
        return redirect("customers:account-order-detail", code=order.code)
    return redirect("orders:payment-callback", code=order.code, status="success")


def payment_callback(request, code, status):
    """نقطه‌ی بازگشت درگاه پرداخت — بعداً درگاه واقعی با امضای معتبر به همین آدرس برمی‌گردد.

    پردازش idempotent است: اگر سفارش قبلاً پردازش شده باشد، فقط به صفحه‌ی
    نتیجه هدایت می‌شود بدون ثبت تراکنش تکراری.
    """
    order = _get_own_order(request, code)
    if order.payment_status == Order.PaymentStatus.PENDING:
        simulate_payment(order, status == "success")
    return redirect("orders:payment-result", code=order.code)


def payment_result(request, code):
    order = _get_own_order(
        request, code,
        queryset=Order.objects.select_related("shipping_method", "payment_gateway").prefetch_related(
            "items", "transactions"
        ),
    )
    return render(request, "orders/payment_result.html", {"order": order})


@require_POST
def checkout_item_update(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)
    if item.product.stock > 0:
        quantity = min(quantity, item.product.stock)

    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return _dynamic_response(request, cart)


@require_POST
def checkout_item_remove(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return _dynamic_response(request, cart, toast_message="کالا از سبد حذف شد", toast_type="info")


@require_POST
def checkout_set_shipping(request, method_id):
    cart = get_cart(request, create=True)
    checkout_service.set_shipping_method(request, method_id)
    return _dynamic_response(request, cart)


@require_POST
def checkout_set_payment(request, gateway_id):
    cart = get_cart(request, create=True)
    checkout_service.set_payment_gateway(request, gateway_id)
    return _dynamic_response(request, cart)


@require_POST
def checkout_apply_coupon(request):
    cart = get_cart(request, create=True)
    code = request.POST.get("code", "")
    ok, message = checkout_service.apply_coupon(request, cart, code)
    return _dynamic_response(
        request, cart, toast_message=message, toast_type="ok" if ok else "err",
        coupon_input="" if ok else code,
        coupon_error="" if ok else message,
    )


@require_POST
def checkout_remove_coupon(request):
    cart = get_cart(request, create=True)
    checkout_service.remove_coupon(request)
    return _dynamic_response(request, cart, toast_message="کد تخفیف حذف شد", toast_type="info")
