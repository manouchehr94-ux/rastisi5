import json

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.cart.models import CartItem
from apps.cart.services.cart_service import get_cart

from .forms import CheckoutAddressForm
from .services import checkout_service


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
def checkout_address_save(request):
    cart = get_cart(request, create=True)
    form = CheckoutAddressForm(request.POST)
    if form.is_valid():
        checkout_service.save_address(request, form.cleaned_data)
        return _dynamic_response(
            request, cart,
            toast_message="اطلاعات گیرنده ذخیره شد — درگاه پرداخت در مرحله‌ی بعد تکمیل می‌شود",
            address_form=CheckoutAddressForm(initial=form.cleaned_data),
        )
    return _dynamic_response(
        request, cart,
        toast_message="لطفاً خطاهای فرم را برطرف کنید", toast_type="err",
        address_form=form,
    )


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
