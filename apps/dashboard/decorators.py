from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect


def staff_required(view_func):
    """دسترسی به پنل مدیریت را فقط به کاربران staff/admin می‌دهد.

    کاربران غیر احراز هویت‌شده به صفحه‌ی ورود اختصاصی پنل مدیریت هدایت
    می‌شوند (نه صفحه‌ی اصلی فروشگاه). پارامتر next مسیر اصلی درخواست‌شده را
    حفظ می‌کند تا پس از ورود موفق، کاربر به همان صفحه بازگردد.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = "/admin-panel/login/"
            params = urlencode({"next": request.get_full_path()})
            return redirect(f"{login_url}?{params}")
        if not request.user.is_staff:
            return redirect("catalog:home")
        return view_func(request, *args, **kwargs)

    return wrapper
