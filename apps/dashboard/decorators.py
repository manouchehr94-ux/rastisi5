from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect

from apps.stores.authorization import user_can_access_dashboard, user_has_permission
from apps.stores.resolution import StoreResolutionError, resolve_store_for_service


def _resolve_store_or_none(request):
    """Resolve the active Store for an admin-panel request, never raising.

    Uses the same authoritative resolver every dashboard service call goes
    through (``apps.stores.resolution.resolve_store_for_service``), so the
    Store this decorator authorizes against is exactly the Store the view
    body will act on — never re-derived independently.
    """
    try:
        return resolve_store_for_service(request)
    except StoreResolutionError:
        return None


def staff_required(view_func):
    """دسترسی به پنل مدیریت را فقط به اعضای فعال همان فروشگاه می‌دهد.

    ``user.is_staff`` به‌تنهایی هرگز کافی نیست: کاربر باید یک
    ``StoreMembership`` با وضعیت ``ACTIVE`` دقیقاً برای Storeای که این
    درخواست از طریق Host به آن resolve شده داشته باشد (نگاه کنید به
    ``apps.stores.authorization``). عضویت در Store دیگر، یا نبود Store
    resolve‌شده، دسترسی نمی‌دهد.

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
        store = _resolve_store_or_none(request)
        if not request.user.is_staff or not user_can_access_dashboard(request.user, store):
            return redirect("catalog:home")
        request.store = store
        return view_func(request, *args, **kwargs)

    return wrapper


def permission_required(permission):
    """Additional per-action gate on top of ``staff_required``.

    Must be applied *inside* (i.e. closer to the view than)
    ``staff_required``, since it assumes ``request.store`` is already the
    authorized, resolved Store. Denies with the same ``catalog:home``
    redirect as a failed ``staff_required`` check — this never leaks
    whether the underlying object/action exists to a member who simply
    lacks the role for it.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            store = getattr(request, "store", None)
            if not user_has_permission(request.user, store, permission):
                return redirect("catalog:home")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
