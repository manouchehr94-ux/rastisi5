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

    return {"cart_count": cart_count, "wishlist_count": wishlist_count}
