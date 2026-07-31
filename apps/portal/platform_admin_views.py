"""Platform Admin (Section M) — host-isolated, staff/superuser-only, no
tenant resolution. Only ever reachable on a Host listed in ``settings.
RASTISI_PLATFORM_ADMIN_HOSTS`` (``apps.portal.middleware.
PlatformHostRoutingMiddleware``); every other Host 404s before this module
is even consulted, since ``request.urlconf`` never points here.

This is an intentionally minimal first slice: real, query-backed summary
counts (not mocked), a real branded login gate — but not yet the full
operational tooling (Store search/detail, billing overrides, ...) the wider
program describes. Extending it is additive, later work.
"""

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render

from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import StoreSubscription

from .forms import OwnerLoginForm
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit


def _is_platform_staff(user):
    return user.is_authenticated and user.is_staff and user.is_superuser


def login_view(request):
    if _is_platform_staff(request.user):
        return redirect("portal_platform_admin:home")

    if request.method == "POST":
        form = OwnerLoginForm(request.POST)
        try:
            enforce_rate_limit(
                "platform_admin_login", request.META.get("REMOTE_ADDR", "unknown"),
                max_attempts=10, window_seconds=600,
            )
        except RateLimitExceeded:
            form.add_error(None, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/platform_admin/login.html", {"form": form})
        if form.is_valid():
            user = authenticate(
                request, username=form.cleaned_data["email"].strip().lower(),
                password=form.cleaned_data["password"],
            )
            if user is not None and _is_platform_staff(user):
                auth_login(request, user)
                return redirect("portal_platform_admin:home")
            form.add_error(None, "ایمیل، رمز عبور، یا دسترسی نامعتبر است")
    else:
        form = OwnerLoginForm()
    return render(request, "portal/platform_admin/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    return redirect("portal_platform_admin:login")


def not_found(request, exception=None):
    """``handler404`` for ``shop_core.urls_platform_admin`` — self-contained
    within ``portal/platform_admin/base.html``, same reasoning as ``apps.
    portal.views.not_found`` (ADR-97)."""
    return render(request, "portal/platform_admin/404.html", status=404)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def home(request):
    context = {
        "store_count": Store.objects.count(),
        "active_store_count": Store.objects.filter(status=Store.Status.ACTIVE).count(),
        "owner_count": StoreMembership.objects.filter(
            role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        ).values("user_id").distinct().count(),
        "trialing_count": StoreSubscription.objects.filter(
            status=StoreSubscription.Status.TRIALING, is_current=True,
        ).count(),
    }
    return render(request, "portal/platform_admin/home.html", context)
