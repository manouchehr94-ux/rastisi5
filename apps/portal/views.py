from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from apps.catalog.models import IndustryTemplate
from apps.stores.models import StoreMembership
from apps.subscriptions.models import Plan, PlanVersion

from .decorators import owner_required
from .forms import (
    ContactForm,
    CreateStoreForm,
    OwnerLoginForm,
    OwnerRegisterForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from .models import ContactMessage
from .services import owner_auth_service, provisioning_service
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit

_STORE_CREATE_TOKEN_SESSION_KEY = "portal_store_create_token"

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


@owner_required
def store_create(request):
    """Section D (lite) + Section G: one-step store name + optional industry
    choice, then immediate atomic trial provisioning
    (``provisioning_service.provision_trial_store``). Double-submit
    protection is a per-session, single-use token — a genuine, truly
    concurrent double-submit within the same session is not fully excluded
    (no DB-level mutex), but sequential double-clicks/back-button resubmits
    are: the token is rotated the moment a valid submission is accepted."""
    if request.method == "POST":
        form = CreateStoreForm(request.POST)
        session_token = request.session.get(_STORE_CREATE_TOKEN_SESSION_KEY)
        submitted_token = request.POST.get("submission_token")
        if not session_token or submitted_token != session_token:
            messages.error(request, "این درخواست قبلاً پردازش شده یا نامعتبر است؛ دوباره تلاش کنید.")
            return redirect("portal:store-create")

        if form.is_valid():
            request.session[_STORE_CREATE_TOKEN_SESSION_KEY] = get_random_string(32)
            industry_template = None
            template_id = form.cleaned_data.get("industry_template_id")
            if template_id:
                industry_template = IndustryTemplate.objects.filter(
                    pk=template_id, is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
                ).first()
            try:
                store = provisioning_service.provision_trial_store(
                    owner=request.user, name=form.cleaned_data["name"], industry_template=industry_template,
                )
            except provisioning_service.ProvisioningError as exc:
                messages.error(request, str(exc))
            else:
                return redirect("portal:store-created", store_public_id=store.public_id)
    else:
        request.session[_STORE_CREATE_TOKEN_SESSION_KEY] = get_random_string(32)
        form = CreateStoreForm()

    industry_templates = provisioning_service.latest_offerable_industry_templates()
    return render(
        request, "portal/app/store_create.html",
        {
            "form": form, "industry_templates": industry_templates,
            "submission_token": request.session[_STORE_CREATE_TOKEN_SESSION_KEY],
        },
    )


@owner_required
def store_created(request, store_public_id):
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    store = membership.store
    trial_domain = store.domains.filter(is_primary=True).first()
    if trial_domain is None:
        raise Http404
    return render(request, "portal/app/store_created.html", {"store": store, "trial_domain": trial_domain})
