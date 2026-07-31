from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render

from apps.stores.authorization import get_active_membership, membership_has_permission
from apps.stores.resolution import resolve_store_for_admin_request


def _resolve_admin_store_or_404(request):
    """Resolve the Store this admin-portal request is for, or raise ``Http404``.

    Uses ``apps.stores.resolution.resolve_store_for_admin_request`` — the
    Phase 1C admin-host-aware resolver — so a request that arrives on a
    Store's *public* storefront domain (or any host that isn't a real
    ``admin_subdomain`` match or an approved local-dev/test host) never
    reaches any merchant-admin view at all, authenticated or not. A plain
    404 (not a redirect, not a 403) is used deliberately: it reveals
    nothing about whether *any* Store's admin portal exists on this host,
    matching the same fail-closed, non-existence-revealing policy the rest
    of the codebase already uses for cross-Store object lookups (see
    ``00_PROJECT_MASTER_REFERENCE.md`` §9.2).
    """
    store = resolve_store_for_admin_request(request)
    if store is None:
        raise Http404
    return store


def admin_host_required(view_func):
    """Gate for admin-portal views that don't yet have an authenticated user
    to check membership for (currently only ``admin_login``). Rejects with
    404 exactly like ``staff_required`` does, before any authentication or
    membership check — a disallowed host must 404 regardless of whether the
    visitor is logged in, staff, or a member of any Store."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        _resolve_admin_store_or_404(request)
        return view_func(request, *args, **kwargs)

    return wrapper


def staff_required(view_func):
    """دسترسی به پنل مدیریت را فقط به اعضای فعال همان فروشگاه، از طریق میزبان مدیریت مجاز، می‌دهد.

    به ترتیب:

    1. میزبان درخواست باید به یک Store معتبر resolve شود — از طریق
       ``Store.admin_subdomain`` واقعی، یا (فقط برای توسعه/تست) میزبان
       تأییدشده‌ی محلی (نگاه کنید به ``apps.stores.resolution.resolve_store_for_admin_request``).
       در غیر این صورت ``404`` بدون توجه به وضعیت ورود کاربر — دامنه‌ی
       عمومی فروشگاه هرگز نباید پنل مدیریت را افشا کند.
    2. کاربر باید احراز هویت شده باشد؛ در غیر این صورت به ورودِ مرکزیِ
       راستیسی (Section 4) هدایت می‌شود — نه صفحه‌ی محلیِ قدیمیِ
       ``/admin-portal/login/`` (که فقط برایِ بازیابی/سازگاری نگه داشته
       شده، مثلِ ایمیل+رمزِ عبورِ مالک). مقصدِ بازگشت با یک توکنِ امضاشده
       (``handoff_service.build_admin_return_token``) حمل می‌شود، نه یک
       URL خام — پس نه open-redirect ممکن است، نه دستکاری/بازپخش
       (replay؛ توکن کوتاه‌عمر و متصل به همین admin_subdomain است).
    3. ``user.is_staff`` به‌تنهایی هرگز کافی نیست: کاربر باید یک
       ``StoreMembership`` با وضعیت ``ACTIVE`` دقیقاً برای همان Store
       داشته باشد (نگاه کنید به ``apps.stores.authorization``).

    Caches the resolved membership on ``request.store_membership`` so
    ``permission_required`` (and templates, via
    ``apps.dashboard.context_processors.merchant_permissions``) don't repeat
    the same query for the rest of this request.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        store = _resolve_admin_store_or_404(request)

        if not request.user.is_authenticated:
            from apps.portal.services.handoff_service import build_admin_return_token

            token = build_admin_return_token(
                admin_subdomain=store.admin_subdomain, destination_path=request.get_full_path(),
            )
            params = urlencode({"admin_return": token})
            central_login = f"{request.scheme}://{settings.RASTISI_PLATFORM_PRIMARY_HOST}/login/"
            return redirect(f"{central_login}?{params}")

        membership = get_active_membership(request.user, store)
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
