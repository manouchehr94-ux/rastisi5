from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.stores.models import StoreMembership
from apps.subscriptions.models import Plan, PlanVersion

from .decorators import owner_required
from .forms import (
    ContactForm,
    OwnerLoginForm,
    OwnerRegisterForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from .models import ContactMessage
from .services import owner_auth_service
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit

# ---------------------------------------------------------------------------
# Public marketing pages (Section A)
# ---------------------------------------------------------------------------


def home(request):
    return render(request, "portal/public/home.html")


def features(request):
    return render(request, "portal/public/features.html")


def plans(request):
    plan_rows = []
    for plan in Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order", "code"):
        version = plan.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first()
        if version is not None:
            plan_rows.append({"plan": plan, "version": version})
    return render(request, "portal/public/plans.html", {"plan_rows": plan_rows})


def help_center(request):
    return render(request, "portal/public/help.html")


def terms(request):
    return render(request, "portal/public/terms.html")


def privacy(request):
    return render(request, "portal/public/privacy.html")


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        try:
            enforce_rate_limit(
                "contact", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=5, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد ارسال پیام بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/contact.html", {"form": form})
        if form.is_valid():
            ContactMessage.objects.create(**form.cleaned_data)
            messages.success(request, "پیام شما دریافت شد؛ به‌زودی با شما تماس می‌گیریم.")
            return redirect("portal:contact")
    else:
        form = ContactForm()
    return render(request, "portal/public/contact.html", {"form": form})


# ---------------------------------------------------------------------------
# Owner identity (Section B)
# ---------------------------------------------------------------------------


def register(request):
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    if request.method == "POST":
        form = OwnerRegisterForm(request.POST)
        try:
            enforce_rate_limit(
                "register", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=10, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد تلاش ثبت‌نام بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/register.html", {"form": form})
        if form.is_valid():
            try:
                user = owner_auth_service.register_owner(**form.cleaned_data)
            except owner_auth_service.OwnerAuthError as exc:
                form.add_error(None, str(exc))
            else:
                auth_login(request, user)
                return redirect("portal:app-home")
    else:
        form = OwnerRegisterForm()
    return render(request, "portal/public/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = OwnerLoginForm(request.POST)
        try:
            enforce_rate_limit(
                "login", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=15, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/login.html", {"form": form, "next": next_url})
        if form.is_valid():
            user = owner_auth_service.authenticate_owner(
                request, email=form.cleaned_data["email"], password=form.cleaned_data["password"],
            )
            if user is None:
                form.add_error(None, "ایمیل یا رمز عبور نادرست است")
            else:
                auth_login(request, user)
                if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect("portal:app-home")
    else:
        form = OwnerLoginForm()
    return render(request, "portal/public/login.html", {"form": form, "next": next_url})


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("portal:home")


def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        try:
            enforce_rate_limit(
                "password_reset", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=5, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد درخواست بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/password_reset_request.html", {"form": form})
        if form.is_valid():
            base_url = f"{request.scheme}://{request.get_host()}"
            owner_auth_service.request_password_reset(email=form.cleaned_data["email"], base_url=base_url)
            messages.success(request, "اگر این ایمیل ثبت‌نام کرده باشد، پیوند بازیابی رمز برای آن ارسال شد.")
            return redirect("portal:login")
    else:
        form = PasswordResetRequestForm()
    return render(request, "portal/public/password_reset_request.html", {"form": form})


def password_reset_confirm(request, uidb64, token):
    user = owner_auth_service.get_user_from_reset_link(uidb64=uidb64, token=token)
    if user is None:
        return render(request, "portal/public/password_reset_invalid.html", status=400)

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            owner_auth_service.set_new_password(user=user, password=form.cleaned_data["password"])
            messages.success(request, "رمز عبور با موفقیت تغییر کرد؛ اکنون می‌توانید وارد شوید.")
            return redirect("portal:login")
    else:
        form = PasswordResetConfirmForm()
    return render(request, "portal/public/password_reset_confirm.html", {"form": form})


# ---------------------------------------------------------------------------
# Owner account portal (Section E/F — My Stores; provisioning/onboarding
# lands in a later slice, so today this is a real, honest empty/list state)
# ---------------------------------------------------------------------------


def not_found(request, exception=None):
    """``handler404`` for ``shop_core.urls_platform`` (ADR-97) — the global
    ``templates/404.html`` extends the Store-scoped ``base.html`` (catalog/
    cart/customers nav links), which does not exist under this urlconf, so
    it cannot be reused here. Self-contained within ``portal/base_
    platform.html`` instead, which only ever references ``portal:*`` names."""
    return render(request, "portal/public/404.html", status=404)


@owner_required
def app_home(request):
    memberships = (
        StoreMembership.objects.filter(
            user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        .select_related("store")
        .order_by("store__name")
    )
    return render(request, "portal/app/my_stores.html", {"memberships": memberships})
