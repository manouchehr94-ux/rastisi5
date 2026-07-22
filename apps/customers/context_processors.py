from .forms import LoginForm, SignupForm
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


def auth_forms(request):
    """فرم‌های خالی ورود/ثبت‌نام برای مودال سراسری — تا هر صفحه بدون کار اضافه آن را داشته باشد."""
    return {"login_form": LoginForm(), "signup_form": SignupForm(), "active_tab": "in"}
