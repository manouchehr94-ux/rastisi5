from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from django.conf import settings

from apps.catalog.models import IndustryTemplate
from apps.stores.models import StoreMembership
from apps.subscriptions.models import Plan, PlanVersion

from .decorators import owner_required
from .forms import (
    ContactForm,
    CreateStoreForm,
    OwnerLoginForm,
    OwnerOtpVerifyForm,
    OwnerPhoneRequestForm,
    OwnerRegisterForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from .models import ContactMessage, OwnerOtpChallenge
from .phone import InvalidPhoneError, normalize_iranian_phone
from .services import handoff_service, owner_auth_service, owner_otp_service, provisioning_service
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit

_STORE_CREATE_TOKEN_SESSION_KEY = "portal_store_create_token"
DEFAULT_TRIAL_STORE_NAME = "فروشگاه من"
_OTP_SESSION_PHONE_KEY = "portal_otp_phone"
_OTP_SESSION_PURPOSE_KEY = "portal_otp_purpose"
_OTP_SESSION_FULL_NAME_KEY = "portal_otp_full_name"
_OTP_SESSION_NEXT_KEY = "portal_otp_next"

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


def _is_safe_next(next_url: str) -> bool:
    return bool(next_url) and next_url.startswith("/") and not next_url.startswith("//")


def _request_otp_and_go_to_verify(request, *, phone_raw: str, full_name: str, purpose: str, next_url: str = ""):
    try:
        phone = normalize_iranian_phone(phone_raw)
    except InvalidPhoneError as exc:
        return None, str(exc.messages[0] if exc.messages else exc)

    try:
        owner_otp_service.request_otp(
            phone=phone, purpose=purpose, client_ip=request.META.get("REMOTE_ADDR", "unknown"),
        )
    except owner_otp_service.OtpRateLimitError as exc:
        return None, str(exc)

    request.session[_OTP_SESSION_PHONE_KEY] = phone
    request.session[_OTP_SESSION_PURPOSE_KEY] = purpose
    request.session[_OTP_SESSION_FULL_NAME_KEY] = full_name
    request.session[_OTP_SESSION_NEXT_KEY] = next_url
    return phone, None


def register(request):
    """Section 3: primary owner registration is phone + OTP, not email +
    password (that flow is kept, not deleted — see register_email/
    login_email — for existing accounts and platform-superuser recovery)."""
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    if request.method == "POST":
        form = OwnerPhoneRequestForm(request.POST)
        if form.is_valid():
            phone, error = _request_otp_and_go_to_verify(
                request, phone_raw=form.cleaned_data["phone"],
                full_name=form.cleaned_data.get("full_name", ""), purpose=OwnerOtpChallenge.Purpose.REGISTER,
            )
            if error:
                form.add_error(None, error)
            else:
                return redirect("portal:otp-verify")
    else:
        form = OwnerPhoneRequestForm()
    return render(request, "portal/public/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = OwnerPhoneRequestForm(request.POST)
        if form.is_valid():
            phone, error = _request_otp_and_go_to_verify(
                request, phone_raw=form.cleaned_data["phone"], full_name="",
                purpose=OwnerOtpChallenge.Purpose.LOGIN, next_url=next_url,
            )
            if error:
                form.add_error(None, error)
            else:
                return redirect("portal:otp-verify")
    else:
        form = OwnerPhoneRequestForm()
    return render(request, "portal/public/login.html", {"form": form, "next": next_url})


def otp_verify(request):
    phone = request.session.get(_OTP_SESSION_PHONE_KEY)
    purpose = request.session.get(_OTP_SESSION_PURPOSE_KEY)
    if not phone or not purpose:
        return redirect("portal:login")

    if request.method == "POST":
        form = OwnerOtpVerifyForm(request.POST)
        if form.is_valid() and form.cleaned_data["phone"] == phone:
            ok = owner_otp_service.verify_otp(phone=phone, purpose=purpose, code=form.cleaned_data["code"])
            if not ok:
                form.add_error(None, "کد نادرست یا منقضی‌شده است.")
            else:
                full_name = request.session.get(_OTP_SESSION_FULL_NAME_KEY, "")
                next_url = request.session.get(_OTP_SESSION_NEXT_KEY, "")
                for key in (
                    _OTP_SESSION_PHONE_KEY, _OTP_SESSION_PURPOSE_KEY,
                    _OTP_SESSION_FULL_NAME_KEY, _OTP_SESSION_NEXT_KEY,
                ):
                    request.session.pop(key, None)
                user, created = owner_auth_service.get_or_create_owner_by_phone(
                    phone=phone, full_name=full_name,
                )
                auth_login(request, user)

                if created:
                    # Section 3.1 ("onboarding mode C"): registration
                    # provisions exactly one trial Store automatically —
                    # the owner never sees an empty My Stores page or a
                    # separate "create store" click on their very first visit.
                    try:
                        store = provisioning_service.provision_trial_store(
                            owner=user, name=DEFAULT_TRIAL_STORE_NAME,
                        )
                    except provisioning_service.ProvisioningError:
                        pass
                    else:
                        return redirect("portal:onboarding", store_public_id=store.public_id)

                if _is_safe_next(next_url):
                    return redirect(next_url)
                return redirect("portal:app-home")
    else:
        form = OwnerOtpVerifyForm(initial={"phone": phone})
    return render(request, "portal/public/otp_verify.html", {"form": form, "phone": phone})


def register_email(request):
    """Legacy email+password registration — kept for existing accounts and
    platform-superuser recovery (Section 3), not the primary flow anymore."""
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    if request.method == "POST":
        form = OwnerRegisterForm(request.POST)
        try:
            enforce_rate_limit(
                "register_email", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=10, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد تلاش ثبت‌نام بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/register_email.html", {"form": form})
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
    return render(request, "portal/public/register_email.html", {"form": form})


def login_email(request):
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = OwnerLoginForm(request.POST)
        try:
            enforce_rate_limit(
                "login_email", request.META.get("REMOTE_ADDR", "unknown"), max_attempts=15, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/login_email.html", {"form": form, "next": next_url})
        if form.is_valid():
            user = owner_auth_service.authenticate_owner(
                request, email=form.cleaned_data["email"], password=form.cleaned_data["password"],
            )
            if user is None:
                form.add_error(None, "ایمیل یا رمز عبور نادرست است")
            else:
                auth_login(request, user)
                if _is_safe_next(next_url):
                    return redirect(next_url)
                return redirect("portal:app-home")
    else:
        form = OwnerLoginForm()
    return render(request, "portal/public/login_email.html", {"form": form, "next": next_url})


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
            return redirect("portal:login-email")
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
            return redirect("portal:login-email")
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
@require_POST
def enter_admin(request, store_public_id):
    """Section H: issues a short-lived handoff ticket for a Store the
    caller actively belongs to and redirects to that Store's own admin
    host to consume it — never the portal's own session cookie, which has
    no meaning on that other host (ADR-98)."""
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    store = membership.store
    try:
        ticket = handoff_service.issue_ticket(user=request.user, store=store)
    except handoff_service.HandoffError:
        raise Http404
    admin_host = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    return redirect(f"{request.scheme}://{admin_host}/admin-portal/handoff/{ticket.token}/")


@owner_required
def onboarding(request, store_public_id):
    """Section 5 (minimal first slice — a single required step, not the
    full multi-stage wizard the program describes): confirm the Store's
    real display name, then publish it. Until this runs,
    ``Store.onboarding_completed_at`` stays NULL and the storefront 403s
    for anonymous visitors (Section 6, ``publication_service``) even
    though the trial subscription is active — only the owner (via ``{%
    owner_required %}``-gated portal pages) can see anything about it."""
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    store = membership.store
    trial_domain = store.domains.filter(is_primary=True).first()

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if name:
            store.name = name
        store.onboarding_completed_at = timezone.now()
        store.save(update_fields=["name", "onboarding_completed_at", "updated_at"])
        messages.success(request, "فروشگاه شما منتشر شد!")
        return redirect("portal:store-created", store_public_id=store.public_id)

    return render(request, "portal/app/onboarding.html", {"store": store, "trial_domain": trial_domain})


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
