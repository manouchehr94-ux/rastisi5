from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect, render

from apps.stores.authorization import get_active_membership, membership_has_permission
from apps.stores.resolution import StoreResolutionError, resolve_store_for_service


def _resolve_store_or_none(request):
    """Resolve the active Store for an admin-portal request, never raising.

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

    Caches the resolved membership on ``request.store_membership`` so
    ``permission_required`` (and templates, via
    ``apps.dashboard.context_processors.merchant_permissions``) don't repeat
    the same query for the rest of this request.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = "/admin-portal/login/"
            params = urlencode({"next": request.get_full_path()})
            return redirect(f"{login_url}?{params}")
        store = _resolve_store_or_none(request)
        membership = get_active_membership(request.user, store) if store is not None else None
        if not request.user.is_staff or membership is None:
            return redirect("catalog:home")
        request.store = store
        request.store_membership = membership
        return view_func(request, *args, **kwargs)

    return wrapper


def permission_required(*permissions):
    """Additional per-action gate on top of ``staff_required``.

    Accepts one or more permission keys from ``apps.stores.authorization``;
    access is granted if the membership holds *any* of them (OR semantics) —
    needed for views like ``product_form`` that serve both creation and
    editing behind one endpoint.

    Must be applied *inside* (i.e. closer to the view than)
    ``staff_required``, since it assumes ``request.store``/
    ``request.store_membership`` are already the authorized, resolved Store
    and the requesting user's membership in it. Denies with an actual HTTP
    403 response (``dashboard/403.html``) — this never leaks whether the
    underlying object/action exists to a member who simply lacks the role
    for it, but is explicit (unlike ``staff_required``'s redirect) that the
    user *is* a legitimate dashboard member, just not permitted to do this
    specific thing.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            membership = getattr(request, "store_membership", None)
            if not any(membership_has_permission(membership, p) for p in permissions):
                return render(request, "dashboard/403.html", status=403)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
