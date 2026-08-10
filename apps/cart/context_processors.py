from django.db.models import Sum

from apps.cart.models import Cart
from apps.customers.models import Wishlist


def cart_badge(request):
    """شمارنده‌ی زنده‌ی سبد و علاقه‌مندی — بدون ساخت سبد جدید، فقط برای نمایش."""
    cart_count = 0
    wishlist_count = 0

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        customer = request.user.customer_profile
        cart = Cart.objects.filter(customer=customer).first()
        wishlist_count = Wishlist.objects.filter(customer=customer).count()
    else:
        session_key = request.session.session_key
        cart = Cart.objects.filter(session_key=session_key, customer=None).first() if session_key else None

    if cart is not None:
        cart_count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0

    # تعیینِ حالتِ پیش‌نمایشِ سبد بر اساسِ خانواده‌ی فعال — heritage_premium
    # به‌صورتِ پیش‌فرض mini_cart دارد، بقیه count_link.
    cart_preview_mode = "count_link"
    appearance_version = getattr(request, "storefront_appearance_version", None)
    if appearance_version is not None:
        config = getattr(appearance_version, "effective_appearance_config", lambda: {})()
        family_slug = config.get("family_slug")
        if family_slug == "heritage_premium":
            cart_preview_mode = "mini_cart"

    result = {"cart_count": cart_count, "wishlist_count": wishlist_count, "cart_preview_mode": cart_preview_mode}

    # در حالتِ mini_cart، اطلاعاتِ اقلام هم ارائه شود
    if cart_preview_mode == "mini_cart" and cart is not None and cart_count > 0:
        from apps.cart.services.cart_preview import get_cart_preview_data

        preview_data = get_cart_preview_data(request, mode="mini_cart")
        result.update(preview_data)
    else:
        result["cart_items_preview"] = []
        result["cart_total"] = 0
        result["cart_is_empty"] = cart_count == 0

    return result
