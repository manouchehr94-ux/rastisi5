from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def staff_required(view_func):
    """دسترسی به پنل مدیریت را فقط به کاربران staff/admin می‌دهد."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, "برای دسترسی به پنل مدیریت ابتدا وارد حساب کاربری خود شوید")
            return redirect("catalog:home")
        if not request.user.is_staff:
            messages.error(request, "شما به پنل مدیریت دسترسی ندارید")
            return redirect("catalog:home")
        return view_func(request, *args, **kwargs)

    return wrapper
