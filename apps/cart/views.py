import json

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product, ProductVariant

from apps.stores.resolution import resolve_store_for_service

from .models import CartItem
from .services.cart_service import add_item_to_cart, get_cart
from .services.pricing import cart_totals


def _cart_context(request, cart):
    if cart is None:
        totals = {
            "items_total": 0, "product_discount": 0, "coupon_discount": 0,
            "shipping_cost": 0, "free_shipping": False, "tax": 0, "grand_total": 0,
        }
        item_count = 0
    else:
        store = resolve_store_for_service(request)
        totals = cart_totals(cart, store=store)
        item_count = sum(item.quantity for item in cart.items.all())
    return {"cart": cart, "totals": totals, "item_count": item_count}


def cart_detail(request):
    cart = get_cart(request, create=True)
    return render(request, "cart/cart_detail.html", _cart_context(request, cart))


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product, slug=slug, status=Product.Status.ACTIVE)

    variant = None
    variant_id = request.POST.get("variant_id", "").strip()
    if variant_id:
        variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    cart = get_cart(request, create=True)
    add_item_to_cart(cart, product, variant, quantity)

    response = render(request, "cart/partials/header_counts_oob.html", _header_counts_context(request))
    response["HX-Trigger"] = json.dumps(
        {"toast": {"message": f"«{product.name}» به سبد خرید اضافه شد", "type": "ok"}}
    )
    return response


@require_POST
def cart_item_update(request, item_id):
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

    return render(request, "cart/partials/cart_page_body.html", _cart_context(request, cart))


@require_POST
def cart_item_remove(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return render(request, "cart/partials/cart_page_body.html", _cart_context(request, cart))


def _header_counts_context(request):
    from apps.cart.context_processors import cart_badge

    return cart_badge(request)
