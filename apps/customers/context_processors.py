from .models import Wishlist


def wishlist_membership(request):
    """مجموعه‌ی شناسه‌ی کالاهای علاقه‌مندی کاربر واردشده — برای نمایش حالت قلب در کارت محصول."""
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        ids = set(
            Wishlist.objects.filter(customer=request.user.customer_profile).values_list("product_id", flat=True)
        )
    else:
        ids = set()
    return {"wishlisted_product_ids": ids}
