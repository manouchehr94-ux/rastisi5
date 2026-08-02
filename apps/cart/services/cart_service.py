"""لایه‌ی سرویس سبد خرید — دسترسی/ساخت سبد برای کاربر مهمان (session) و
کاربر واردشده، و افزودن قلم به سبد.
"""

from apps.cart.models import Cart, CartItem
from apps.catalog.services.pricing_service import resolve_effective_price


def _customer_or_none(request):
    if request.user.is_authenticated:
        return getattr(request.user, "customer_profile", None)
    return None


def get_cart(request, create=False):
    """سبد فعلی کاربر (مهمان بر اساس session یا کاربر واردشده) را برمی‌گرداند.

    اگر create=True باشد و سبدی موجود نباشد، یکی ساخته می‌شود (و در صورت
    نیاز، یک session جدید برای مهمان ایجاد می‌شود).
    """
    customer = _customer_or_none(request)
    if customer is not None:
        if create:
            cart, _ = Cart.objects.get_or_create(customer=customer)
            return cart
        return Cart.objects.filter(customer=customer).first()

    session_key = request.session.session_key
    if not session_key:
        if not create:
            return None
        request.session.create()
        session_key = request.session.session_key

    if create:
        cart, _ = Cart.objects.get_or_create(session_key=session_key, customer=None)
        return cart
    return Cart.objects.filter(session_key=session_key, customer=None).first()


def add_item_to_cart(cart, product, variant, quantity):
    """محصول (و در صورت وجود، تنوع) را به سبد اضافه می‌کند یا تعداد را افزایش می‌دهد.

    قیمتِ واحد همیشه از ``pricing_service.resolve_effective_price`` محاسبه
    می‌شود (نه ``product.final_price`` ساده) تا قیمتِ تنوعِ انتخاب‌شده — چه
    delta-based قدیمی، چه مستقلِ جدید — درست اعمال شود؛ دقیقاً همان تابعی
    که فروشگاه برای نمایشِ قیمت استفاده می‌کند."""
    unit_price = resolve_effective_price(product, variant)
    item = cart.items.filter(product=product, variant=variant).first()
    if item:
        item.quantity += quantity
        item.unit_price = unit_price
        item.save(update_fields=["quantity", "unit_price", "updated_at"])
    else:
        item = CartItem.objects.create(
            cart=cart, product=product, variant=variant, quantity=quantity, unit_price=unit_price
        )
    return item
