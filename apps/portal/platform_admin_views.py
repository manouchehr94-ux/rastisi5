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

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import StoreSubscription

from .forms import OwnerLoginForm, PlatformConfigurationForm
from .models import PlatformAuditLogEntry
from .services.platform_config_service import get_platform_configuration, record_platform_audit_event
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


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def configuration(request):
    config = get_platform_configuration()
    if request.method == "POST":
        form = PlatformConfigurationForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            before = {name: getattr(config, name) for name in form.changed_data}
            form.save()
            from django.core.cache import cache

            cache.delete("portal:platform_configuration")
            record_platform_audit_event(
                actor=request.user, action_code="platform_configuration.updated",
                object_type="PlatformConfiguration", object_id=1,
                before=before, after={name: form.cleaned_data[name] for name in form.changed_data},
            )
            messages.success(request, "تنظیمات پلتفرم به‌روزرسانی شد.")
            return redirect("portal_platform_admin:configuration")
    else:
        form = PlatformConfigurationForm(instance=config)
    return render(request, "portal/platform_admin/configuration.html", {"form": form})


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def stores(request):
    """جست‌وجو/فهرستِ فروشگاه‌ها (Section 13) — همان چیزی که docstring این
    ماژول از ابتدا به‌عنوانِ خلأِ صریح («Store search/detail») اعلام کرده
    بود."""
    query = (request.GET.get("q") or "").strip()
    queryset = Store.objects.all().order_by("-created_at")
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(slug__icontains=query)
            | Q(platform_code__icontains=query) | Q(admin_subdomain__icontains=query)
        )
    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/stores.html", {"page": page, "query": query})


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_detail(request, store_public_id):
    store = get_object_or_404(Store, public_id=store_public_id)
    domains = store.domains.all().order_by("-is_primary", "-created_at")
    memberships = store.memberships.select_related("user").order_by("-status", "role")
    current_subscription = store.subscriptions.filter(is_current=True).select_related("plan_version__plan").first()
    invoices = store.platform_invoices.order_by("-created_at")[:20]
    audit_entries = store.audit_log_entries.order_by("-created_at")[:20]
    return render(request, "portal/platform_admin/store_detail.html", {
        "store": store, "domains": domains, "memberships": memberships,
        "current_subscription": current_subscription, "invoices": invoices, "audit_entries": audit_entries,
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def audit_log(request):
    """تاریخچه‌ی رخدادهای حسابرسیِ سطحِ پلتفرم (Section 13) — رخدادهای
    مختصِ یک Store (مثلِ ``store.handle_claimed``) هم این‌جا ثبت می‌شوند چون
    ``record_audit_event`` جداگانه (Store-owned) است؛ این صفحه فقط
    ``PlatformAuditLogEntry`` (تنظیماتِ سراسری/پلن/دسترسیِ خودِ Platform
    Admin) را نشان می‌دهد — نگاه کنید به جزئیاتِ همان Store در
    ``store_detail`` برایِ رخدادهای Store-owned آن."""
    entries = PlatformAuditLogEntry.objects.select_related("actor").order_by("-created_at")
    action_code = (request.GET.get("action_code") or "").strip()
    if action_code:
        entries = entries.filter(action_code=action_code)
    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/audit_log.html", {"page": page, "action_code": action_code})
