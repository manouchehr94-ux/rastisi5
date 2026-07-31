from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from django.conf import settings

from apps.catalog.models import IndustryTemplate
from apps.stores.models import Store, StoreDomain, StoreMembership, StoreOwnershipTransfer
from apps.stores.services import deletion_service, domain_verification_service, handle_service, ownership_transfer_service
from apps.subscriptions.models import Plan, PlanVersion, PlatformInvoice, PlatformPaymentAttempt, StoreSubscription
from apps.subscriptions.services import billing_service

from .decorators import owner_required
from .forms import (
    ContactForm,
    CreateStoreForm,
    OnboardingBrandingForm,
    OnboardingIdentityForm,
    OnboardingIndustryForm,
    OwnerLoginForm,
    OwnerOtpVerifyForm,
    OwnerPhoneRequestForm,
    OwnerRegisterForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from .models import ContactMessage, OwnerOtpChallenge
from .phone import InvalidPhoneError, normalize_iranian_phone
from .services import handoff_service, owner_auth_service, owner_otp_service, provisioning_service, step_up_service
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit

_STORE_CREATE_TOKEN_SESSION_KEY = "portal_store_create_token"
DEFAULT_TRIAL_STORE_NAME = "فروشگاه من"
_OTP_SESSION_PHONE_KEY = "portal_otp_phone"
_OTP_SESSION_PURPOSE_KEY = "portal_otp_purpose"
_OTP_SESSION_FULL_NAME_KEY = "portal_otp_full_name"
_OTP_SESSION_NEXT_KEY = "portal_otp_next"
_OTP_SESSION_ADMIN_RETURN_KEY = "portal_otp_admin_return"

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


def _request_otp_and_go_to_verify(
    request, *, phone_raw: str, full_name: str, purpose: str, next_url: str = "", admin_return: str = "",
):
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
    request.session[_OTP_SESSION_ADMIN_RETURN_KEY] = admin_return
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
    """Section 4: this is also where an unauthenticated Merchant Admin
    request lands (``apps.dashboard.decorators.staff_required``'s
    ``admin_return`` signed token) — Rastisi employees/owners always
    authenticate centrally, never via a per-Store login form."""
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    admin_return = request.GET.get("admin_return") or request.POST.get("admin_return") or ""
    if request.method == "POST":
        form = OwnerPhoneRequestForm(request.POST)
        if form.is_valid():
            phone, error = _request_otp_and_go_to_verify(
                request, phone_raw=form.cleaned_data["phone"], full_name="",
                purpose=OwnerOtpChallenge.Purpose.LOGIN, next_url=next_url, admin_return=admin_return,
            )
            if error:
                form.add_error(None, error)
            else:
                return redirect("portal:otp-verify")
    else:
        form = OwnerPhoneRequestForm()
    return render(
        request, "portal/public/login.html",
        {"form": form, "next": next_url, "admin_return": admin_return},
    )


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
                admin_return = request.session.get(_OTP_SESSION_ADMIN_RETURN_KEY, "")
                for key in (
                    _OTP_SESSION_PHONE_KEY, _OTP_SESSION_PURPOSE_KEY,
                    _OTP_SESSION_FULL_NAME_KEY, _OTP_SESSION_NEXT_KEY,
                    _OTP_SESSION_ADMIN_RETURN_KEY,
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

                if admin_return:
                    # Section 4: this login was triggered by an
                    # unauthenticated Merchant Admin request
                    # (staff_required's signed admin_return token) — complete
                    # the loop back to that exact host+path via the existing
                    # single-use handoff ticket mechanism (ADR-98), never a
                    # bare redirect (no shared session cookie across hosts).
                    decoded = handoff_service.decode_admin_return_token(admin_return)
                    if decoded is not None:
                        admin_subdomain, destination_path = decoded
                        target_store = Store.objects.filter(admin_subdomain=admin_subdomain).first()
                        if target_store is not None:
                            try:
                                ticket = handoff_service.issue_ticket(
                                    user=user, store=target_store, destination_path=destination_path,
                                )
                            except handoff_service.HandoffError:
                                messages.error(request, "شما عضوِ فعالِ آن فروشگاه نیستید.")
                            else:
                                admin_host = f"{admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
                                return redirect(
                                    f"{request.scheme}://{admin_host}/admin-portal/handoff/{ticket.token}/"
                                )

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
    next_path = request.POST.get("next") or "/admin-portal/"
    if not next_path.startswith("/admin-portal/"):
        next_path = "/admin-portal/"
    try:
        ticket = handoff_service.issue_ticket(user=request.user, store=store, destination_path=next_path)
    except handoff_service.HandoffError:
        raise Http404
    admin_host = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    return redirect(f"{request.scheme}://{admin_host}/admin-portal/handoff/{ticket.token}/")


def _get_owned_store_or_404(request, store_public_id) -> Store:
    """فروشگاهی که کاربرِ جاری عضوِ فعالش است، وگرنه ``Http404`` — بدونِ افشای
    اینکه آیا اصلاً چنین Storeای وجود دارد (همان الگوی بقیه‌ی ویوهای پرتال)."""
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    return membership.store


# Section 5 — order of the onboarding wizard's stages. ``Store.onboarding_stage``
# always holds one of these; the dispatcher below sends the owner to wherever
# they left off (save-progress), but every stage remains freely revisitable —
# this is a memory of where to resume, not a hard sequential gate.
_ONBOARDING_STAGE_ORDER = [
    Store.OnboardingStage.IDENTITY,
    Store.OnboardingStage.INDUSTRY,
    Store.OnboardingStage.BRANDING,
    Store.OnboardingStage.REVIEW,
]
_ONBOARDING_STAGE_URL_NAMES = {
    Store.OnboardingStage.IDENTITY: "portal:onboarding-identity",
    Store.OnboardingStage.INDUSTRY: "portal:onboarding-industry",
    Store.OnboardingStage.BRANDING: "portal:onboarding-branding",
    Store.OnboardingStage.REVIEW: "portal:onboarding-review",
}


def _advance_onboarding_stage(store, *, completed: str) -> None:
    """پس از تکمیلِ موفقِ یک مرحله، ``onboarding_stage`` را فقط رو به جلو
    می‌برد (هرگز عقب) — بازدیدِ دوباره‌ی یک مرحله‌ی قبلی هرگز پیشرفتِ
    ثبت‌شده را از دست نمی‌دهد."""
    current_index = _ONBOARDING_STAGE_ORDER.index(store.onboarding_stage) if (
        store.onboarding_stage in _ONBOARDING_STAGE_ORDER
    ) else -1
    completed_index = _ONBOARDING_STAGE_ORDER.index(completed)
    if completed_index >= current_index:
        next_index = completed_index + 1
        store.onboarding_stage = (
            _ONBOARDING_STAGE_ORDER[next_index] if next_index < len(_ONBOARDING_STAGE_ORDER)
            else Store.OnboardingStage.REVIEW
        )
        store.save(update_fields=["onboarding_stage", "updated_at"])


@owner_required
def onboarding(request, store_public_id):
    """نقطه‌ی ورودِ ویزاردِ آنبوردینگ (Section 5): مالک را به همان مرحله‌ای
    که رها کرده هدایت می‌کند (save-progress، ``Store.onboarding_stage``)."""
    store = _get_owned_store_or_404(request, store_public_id)
    if store.onboarding_stage == Store.OnboardingStage.DONE or store.onboarding_completed_at:
        return redirect("portal:store-created", store_public_id=store.public_id)
    stage = store.onboarding_stage if store.onboarding_stage in _ONBOARDING_STAGE_URL_NAMES else (
        Store.OnboardingStage.IDENTITY
    )
    return redirect(_ONBOARDING_STAGE_URL_NAMES[stage], store_public_id=store.public_id)


@owner_required
def onboarding_identity(request, store_public_id):
    """مرحله‌ی ۱: معرفیِ فروشگاه — نام، شعار، توضیحات، اطلاعاتِ تماس
    (``ShopSettings``، همان مدلی که پنلِ مدیریت هم ویرایش می‌کند)."""
    from apps.core.models import ShopSettings

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)

    if request.method == "POST":
        form = OnboardingIdentityForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            store.name = data["name"]
            store.save(update_fields=["name", "updated_at"])
            shop_settings.name = data["name"]
            shop_settings.tagline = data["tagline"]
            shop_settings.description = data["description"]
            shop_settings.contact_phone = data["contact_phone"]
            shop_settings.contact_email = data["contact_email"]
            shop_settings.contact_address = data["contact_address"]
            shop_settings.save()
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.IDENTITY)
            return redirect("portal:onboarding-industry", store_public_id=store.public_id)
    else:
        form = OnboardingIdentityForm(initial={
            "name": store.name, "tagline": shop_settings.tagline,
            "description": shop_settings.description, "contact_phone": shop_settings.contact_phone,
            "contact_email": shop_settings.contact_email, "contact_address": shop_settings.contact_address,
        })

    return render(request, "portal/app/onboarding_identity.html", {"store": store, "form": form})


@owner_required
def onboarding_industry(request, store_public_id):
    """مرحله‌ی ۲: انتخابِ صنف — اختیاری و رد-شدنی، اما فقط یک‌بار قابلِ نصب
    (``apps.catalog.services.industry_template_service``، ADR-25). اگر
    Store از قبل یک قالب نصب کرده، این مرحله فقط اطلاعِ همان نصب را نشان
    می‌دهد؛ هرگز دوباره نصب صدا زده نمی‌شود (idempotent-safe در برابرِ
    GET/POST مکرر یا دکمه‌ی back مرورگر)."""
    from apps.catalog.models import StoreIndustryInstallation
    from apps.catalog.services.industry_template_service import IndustryInstallationError, install_industry_template

    store = _get_owned_store_or_404(request, store_public_id)
    installation = StoreIndustryInstallation.objects.select_related("industry_template").filter(store=store).first()
    templates = provisioning_service.latest_offerable_industry_templates()

    if request.method == "POST" and installation is None:
        action = request.POST.get("action")
        if action == "skip":
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
            return redirect("portal:onboarding-branding", store_public_id=store.public_id)

        form = OnboardingIndustryForm(request.POST)
        if form.is_valid() and form.cleaned_data["industry_template_id"]:
            template = get_object_or_404(IndustryTemplate, pk=form.cleaned_data["industry_template_id"])
            try:
                install_industry_template(store, template)
            except IndustryInstallationError as exc:
                messages.error(request, str(exc))
            else:
                _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
                return redirect("portal:onboarding-branding", store_public_id=store.public_id)
    elif request.method == "POST":
        # از قبل نصب‌شده — POST دیگری اینجا معنایی ندارد جز عبور به مرحله‌ی بعد.
        _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
        return redirect("portal:onboarding-branding", store_public_id=store.public_id)

    return render(request, "portal/app/onboarding_industry.html", {
        "store": store, "templates": templates, "installation": installation,
    })


@owner_required
def onboarding_branding(request, store_public_id):
    """مرحله‌ی ۳: هویتِ بصری — لوگو و رنگ‌های اصلی (اختیاری، رد-شدنی؛
    ``ShopSettings`` از قبل مقادیرِ پیش‌فرضِ معتبر دارد - ``provision_for``)."""
    from apps.core.models import ShopSettings

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)

    if request.method == "POST":
        if request.POST.get("action") == "skip":
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.BRANDING)
            return redirect("portal:onboarding-review", store_public_id=store.public_id)

        form = OnboardingBrandingForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("logo"):
                shop_settings.logo = data["logo"]
            if data.get("primary_color"):
                shop_settings.primary_color = data["primary_color"]
            if data.get("accent_color"):
                shop_settings.accent_color = data["accent_color"]
            try:
                shop_settings.full_clean()
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
            else:
                shop_settings.save()
                _advance_onboarding_stage(store, completed=Store.OnboardingStage.BRANDING)
                return redirect("portal:onboarding-review", store_public_id=store.public_id)
    else:
        form = OnboardingBrandingForm(initial={
            "primary_color": shop_settings.primary_color, "accent_color": shop_settings.accent_color,
        })

    return render(request, "portal/app/onboarding_branding.html", {
        "store": store, "form": form, "shop_settings": shop_settings,
    })


@owner_required
def onboarding_review(request, store_public_id):
    """مرحله‌ی ۴ (نهایی): بازبینی و انتشار. تنها همین POST است که
    ``Store.onboarding_completed_at`` را مقداردهی می‌کند — پیش از آن،
    فروشگاه برای بازدیدکنندهٔ ناشناس همیشه خصوصی می‌ماند (Section 6)."""
    from apps.core.models import ShopSettings
    from apps.catalog.models import StoreIndustryInstallation

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)
    installation = StoreIndustryInstallation.objects.select_related("industry_template").filter(store=store).first()
    trial_domain = store.domains.filter(is_primary=True).first()

    if request.method == "POST":
        store.onboarding_completed_at = timezone.now()
        store.onboarding_stage = Store.OnboardingStage.DONE
        store.save(update_fields=["onboarding_completed_at", "onboarding_stage", "updated_at"])
        messages.success(request, "فروشگاه شما منتشر شد!")
        return redirect("portal:store-created", store_public_id=store.public_id)

    return render(request, "portal/app/onboarding_review.html", {
        "store": store, "shop_settings": shop_settings, "installation": installation, "trial_domain": trial_domain,
    })


@owner_required
def store_created(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    trial_domain = store.domains.filter(is_primary=True).first()
    if trial_domain is None:
        raise Http404
    return render(request, "portal/app/store_created.html", {"store": store, "trial_domain": trial_domain})


# ---------------------------------------------------------------------------
# Platform billing — subscription purchase (Section 8/9)
# ---------------------------------------------------------------------------
#
# NOTE (honest limitation, not hidden): only the "dev" payment provider is
# actually implemented (apps.subscriptions.services.payment_providers) — a
# same-app fake "bank page" the owner clicks through, no real gateway
# integration exists yet. Checkout below always uses "dev" directly rather
# than reading PlatformConfiguration.default_payment_provider/
# enabled_payment_providers (whose default, "manual", has no real provider
# behind it) — wiring true multi-provider selection is future work.
#
# Also not yet wired here: Section 10's step-up OTP re-confirmation before a
# purchase (PlatformConfiguration.step_up_actions already lists
# "subscription_purchase", but nothing on this path enforces it yet).


@owner_required
def billing_plans(request, store_public_id):
    """فهرستِ پلن‌هایِ پولیِ قابلِ‌خرید برایِ این Store — فقط نسخه‌هایِ
    منتشرشده و پولی (Section 9)."""
    store = _get_owned_store_or_404(request, store_public_id)
    current_subscription = store.subscriptions.filter(is_current=True).first()

    offerable_versions = []
    for plan in Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order"):
        version = (
            plan.versions.filter(status=PlanVersion.Status.PUBLISHED)
            .exclude(billing_interval=PlanVersion.BillingInterval.NONE)
            .filter(display_price__gt=0)
            .order_by("-version_number")
            .first()
        )
        if version is not None:
            offerable_versions.append(version)

    return render(request, "portal/app/billing_plans.html", {
        "store": store, "plan_versions": offerable_versions, "current_subscription": current_subscription,
    })


_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE = "subscription_purchase_confirm"
_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY = "portal_pending_purchase_plan_version_id"


def _start_purchase(request, *, store, plan_version):
    """هسته‌ی مشترکِ خرید — چه بلافاصله (وقتی نیازی به تأییدِ گام‌دوم نیست)
    چه پس از تأییدِ موفقِ OTP گام‌دوم فراخوانی می‌شود."""
    try:
        invoice = billing_service.create_invoice(store=store, plan_version=plan_version, actor=request.user)
        _attempt, redirect_url = billing_service.start_payment_attempt(invoice=invoice, provider_code="dev")
    except billing_service.BillingError as exc:
        messages.error(request, str(exc))
        return redirect("portal:billing-plans", store_public_id=store.public_id)
    return redirect(redirect_url)


@owner_required
@require_POST
def billing_checkout(request, store_public_id, plan_version_id):
    """فاکتور می‌سازد، تلاشِ پرداخت را با درگاهِ dev/test شروع می‌کند، و به
    صفحه‌ی همان درگاه هدایت می‌کند — مگر اینکه سیاستِ پلتفرم برایِ
    ``subscription_purchase_confirm`` تأییدِ گام‌دومِ OTP بخواهد (Section 10)
    و این نشست هنوز آن را برایِ همین Store تأیید نکرده باشد، که در آن
    صورت ابتدا به مرحله‌ی تأییدِ کد هدایت می‌شود."""
    store = _get_owned_store_or_404(request, store_public_id)
    plan_version = get_object_or_404(PlanVersion, pk=plan_version_id, status=PlanVersion.Status.PUBLISHED)

    target = str(store.public_id)
    if step_up_service.is_step_up_required(_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE) and not step_up_service.is_verified(
        request, action=_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE, target=target,
    ):
        phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
        if not phone:
            messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
            return redirect("portal:billing-plans", store_public_id=store.public_id)
        try:
            step_up_service.begin_challenge(
                request, action=_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE, target=target, phone=phone,
                message="کدِ تأییدِ خریدِ اشتراک در راستیسی: {code}",
                client_ip=request.META.get("REMOTE_ADDR", ""),
            )
        except step_up_service.OtpRateLimitError as exc:
            messages.error(request, str(exc))
            return redirect("portal:billing-plans", store_public_id=store.public_id)
        request.session[_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY] = plan_version.pk
        return redirect("portal:billing-step-up", store_public_id=store.public_id)

    return _start_purchase(request, store=store, plan_version=plan_version)


@owner_required
def billing_step_up_verify(request, store_public_id):
    """صفحه‌ی تأییدِ کدِ گام‌دوم پیش از ادامه‌ی خرید (Section 10). فقط برایِ
    چالشی که خودِ ``billing_checkout`` در همین نشست ایجاد کرده معنا دارد —
    شناسه‌ی نسخه‌ی پلن از session خوانده می‌شود، نه از ورودیِ کاربر."""
    store = _get_owned_store_or_404(request, store_public_id)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:billing-plans", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            plan_version_id = request.session.pop(_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY, None)
            plan_version = PlanVersion.objects.filter(pk=plan_version_id).first() if plan_version_id else None
            if plan_version is None:
                messages.error(request, "درخواستِ خرید یافت نشد؛ دوباره تلاش کنید.")
                return redirect("portal:billing-plans", store_public_id=store.public_id)
            return _start_purchase(request, store=store, plan_version=plan_version)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
def billing_dev_provider(request, attempt_public_id):
    """صفحه‌ی «بانکِ جعلیِ» درگاهِ dev/test — هرگز تراکنشِ واقعی ندارد؛ مالک
    آشکارا «پرداختِ موفق» یا «پرداختِ ناموفق» را انتخاب می‌کند. تلاشی که به
    وضعیتِ نهایی رسیده، مستقیماً به صفحه‌ی نتیجه هدایت می‌شود — دوباره قابلِ
    ارسال نیست (بازپخش‌امن، نگاه کنید به ``billing_service.confirm_payment_attempt``)."""
    attempt = get_object_or_404(
        PlatformPaymentAttempt.objects.select_related("invoice", "invoice__store"), public_id=attempt_public_id,
    )
    store = attempt.invoice.store
    has_membership = StoreMembership.objects.filter(
        store=store, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    ).exists()
    if not has_membership:
        raise Http404

    if attempt.is_final:
        return redirect("portal:billing-return", store_public_id=store.public_id, invoice_public_id=attempt.invoice.public_id)

    if request.method == "POST":
        success = request.POST.get("action") == "pay"
        billing_service.confirm_payment_attempt(attempt=attempt, success=success, actor=request.user)
        return redirect("portal:billing-return", store_public_id=store.public_id, invoice_public_id=attempt.invoice.public_id)

    return render(request, "portal/app/billing_dev_provider.html", {"attempt": attempt, "invoice": attempt.invoice})


@owner_required
def billing_return(request, store_public_id, invoice_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    invoice = get_object_or_404(PlatformInvoice, public_id=invoice_public_id, store=store)
    return render(request, "portal/app/billing_return.html", {"store": store, "invoice": invoice})


# ---------------------------------------------------------------------------
# Permanent Store handle claim (Section 11)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_HANDLE_CLAIM = "permanent_handle_claim"
_SESSION_PENDING_HANDLE_LABEL_KEY = "portal_pending_handle_label"


@owner_required
def claim_handle(request, store_public_id):
    """صفحه‌ی ثبتِ نامِ دائمی — فقط برایِ فروشگاهی که اشتراکِ پولیِ فعال
    دارد و هنوز نامِ دائمی ثبت نکرده (Section 11). ثبت غیرقابلِ بازگشت
    است — این هشدار در قالب هم آشکارا نمایش داده می‌شود."""
    store = _get_owned_store_or_404(request, store_public_id)
    already_claimed = handle_service.has_claimed_handle(store)
    current_subscription = store.subscriptions.filter(is_current=True).first()
    can_claim = (
        not already_claimed
        and current_subscription is not None
        and current_subscription.status == StoreSubscription.Status.ACTIVE
    )

    if request.method == "POST" and can_claim:
        label = (request.POST.get("label") or "").strip()
        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_HANDLE_CLAIM) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_HANDLE_CLAIM, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_HANDLE_CLAIM, target=target, phone=phone,
                    message="کدِ تأییدِ ثبتِ نامِ دائمیِ فروشگاه: {code}",
                    client_ip=request.META.get("REMOTE_ADDR", ""),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_HANDLE_LABEL_KEY] = label
            return redirect("portal:claim-handle-step-up", store_public_id=store.public_id)

        try:
            handle_service.claim_platform_handle(store=store, label=label, actor=request.user)
        except handle_service.HandleError as exc:
            messages.error(request, str(exc))
            return redirect("portal:claim-handle", store_public_id=store.public_id)
        messages.success(request, "نامِ دائمیِ فروشگاه با موفقیت ثبت شد.")
        return redirect("portal:claim-handle", store_public_id=store.public_id)

    claimed_domain = StoreDomain.objects.filter(
        store=store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN, is_primary=True,
    ).first()
    return render(request, "portal/app/claim_handle.html", {
        "store": store, "already_claimed": already_claimed, "can_claim": can_claim,
        "claimed_domain": claimed_domain, "current_subscription": current_subscription,
    })


@owner_required
def claim_handle_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:claim-handle", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            label = request.session.pop(_SESSION_PENDING_HANDLE_LABEL_KEY, "")
            try:
                handle_service.claim_platform_handle(store=store, label=label, actor=request.user)
            except handle_service.HandleError as exc:
                messages.error(request, str(exc))
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            messages.success(request, "نامِ دائمیِ فروشگاه با موفقیت ثبت شد.")
            return redirect("portal:claim-handle", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


# ---------------------------------------------------------------------------
# Custom domain — DNS verification and activation (Section 12)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_DOMAIN_ACTIVATE = "custom_domain_activate"
_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY = "portal_pending_activate_domain_id"


def _domains_view_context(store):
    domains = store.domains.filter(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).order_by("-created_at")
    rows = []
    for domain in domains:
        record_name = domain_verification_service.verification_record_name(domain.hostname) if domain.verification_token else ""
        expected_value = (
            f"{domain_verification_service.VERIFICATION_VALUE_PREFIX}{domain.verification_token}"
            if domain.verification_token else ""
        )
        rows.append({"domain": domain, "record_name": record_name, "expected_value": expected_value})
    return rows


@owner_required
def custom_domains(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)

    if request.method == "POST" and request.POST.get("action") == "add":
        hostname = (request.POST.get("hostname") or "").strip()
        try:
            domain_verification_service.request_custom_domain(store=store, hostname=hostname, actor=request.user)
        except domain_verification_service.DomainVerificationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "دامنه ثبت شد؛ اکنون می‌توانید تأییدِ DNS را شروع کنید.")
        return redirect("portal:custom-domains", store_public_id=store.public_id)

    return render(request, "portal/app/custom_domains.html", {
        "store": store, "rows": _domains_view_context(store),
    })


@owner_required
@require_POST
def custom_domain_begin_verify(request, store_public_id, domain_id):
    store = _get_owned_store_or_404(request, store_public_id)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    try:
        domain_verification_service.begin_dns_verification(domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دستورالعملِ تأییدِ DNS آماده شد؛ رکوردِ TXT زیر را در DNS دامنه‌تان اضافه کنید.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
@require_POST
def custom_domain_check(request, store_public_id, domain_id):
    store = _get_owned_store_or_404(request, store_public_id)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    try:
        verified = domain_verification_service.check_dns_verification(domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        if verified:
            messages.success(request, "دامنه با موفقیت تأیید شد.")
        else:
            messages.error(request, "رکوردِ TXT هنوز پیدا نشد یا مقدارش درست نیست؛ کمی صبر کنید و دوباره بررسی کنید.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
@require_POST
def custom_domain_activate(request, store_public_id, domain_id):
    """فعال‌سازیِ دامنه‌ی تأییدشده به‌عنوانِ دامنه‌ی اصلی — پشتِ تأییدِ گام‌دوم
    (Section 10، action=``custom_domain_activate``)، دقیقاً مثلِ الگویِ
    خریدِ اشتراک/ثبتِ نامِ دائمی."""
    store = _get_owned_store_or_404(request, store_public_id)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    target = str(store.public_id)

    if step_up_service.is_step_up_required(_STEP_UP_ACTION_DOMAIN_ACTIVATE) and not step_up_service.is_verified(
        request, action=_STEP_UP_ACTION_DOMAIN_ACTIVATE, target=target,
    ):
        phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
        if not phone:
            messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        try:
            step_up_service.begin_challenge(
                request, action=_STEP_UP_ACTION_DOMAIN_ACTIVATE, target=target, phone=phone,
                message="کدِ تأییدِ فعال‌سازیِ دامنه‌ی اختصاصی: {code}",
                client_ip=request.META.get("REMOTE_ADDR", ""),
            )
        except step_up_service.OtpRateLimitError as exc:
            messages.error(request, str(exc))
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        request.session[_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY] = domain.pk
        return redirect("portal:custom-domain-activate-step-up", store_public_id=store.public_id)

    try:
        domain_verification_service.activate_custom_domain(store=store, domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دامنه‌ی اختصاصی اکنون دامنه‌ی اصلیِ فروشگاه است.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
def custom_domain_activate_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:custom-domains", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            domain_id = request.session.pop(_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY, None)
            domain = StoreDomain.objects.filter(pk=domain_id, store=store).first() if domain_id else None
            if domain is None:
                messages.error(request, "درخواستِ فعال‌سازی یافت نشد؛ دوباره تلاش کنید.")
                return redirect("portal:custom-domains", store_public_id=store.public_id)
            try:
                domain_verification_service.activate_custom_domain(store=store, domain=domain, actor=request.user)
            except domain_verification_service.DomainVerificationError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "دامنه‌ی اختصاصی اکنون دامنه‌ی اصلیِ فروشگاه است.")
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


# ---------------------------------------------------------------------------
# Store deletion — soft, typed-confirmation, step-up gated (Section 14)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_STORE_DELETE = "store_delete"
_SESSION_PENDING_DELETE_CONFIRMATION_KEY = "portal_pending_delete_confirmation"


@owner_required
def request_store_deletion(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)

    if request.method == "POST":
        typed_confirmation = (request.POST.get("typed_confirmation") or "").strip()
        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_STORE_DELETE) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_STORE_DELETE, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:request-store-deletion", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_STORE_DELETE, target=target, phone=phone,
                    message="کدِ تأییدِ حذفِ فروشگاه: {code}",
                    client_ip=request.META.get("REMOTE_ADDR", ""),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:request-store-deletion", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_DELETE_CONFIRMATION_KEY] = typed_confirmation
            return redirect("portal:store-deletion-step-up", store_public_id=store.public_id)

        try:
            deletion_service.request_deletion(store=store, actor=request.user, typed_confirmation=typed_confirmation)
        except deletion_service.DeletionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "درخواستِ حذفِ فروشگاه ثبت شد.")
        return redirect("portal:request-store-deletion", store_public_id=store.public_id)

    return render(request, "portal/app/request_store_deletion.html", {"store": store})


@owner_required
def store_deletion_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:request-store-deletion", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            typed_confirmation = request.session.pop(_SESSION_PENDING_DELETE_CONFIRMATION_KEY, "")
            try:
                deletion_service.request_deletion(
                    store=store, actor=request.user, typed_confirmation=typed_confirmation,
                )
            except deletion_service.DeletionError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "درخواستِ حذفِ فروشگاه ثبت شد.")
            return redirect("portal:request-store-deletion", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
@require_POST
def cancel_store_deletion(request, store_public_id):
    """لغوِ درخواستِ حذف — یک اقدامِ ایمن است (بازگرداندن، نه ایجادِ خطر)،
    پس نیازِ تأییدِ گام‌دومِ OTP ندارد."""
    store = _get_owned_store_or_404(request, store_public_id)
    try:
        deletion_service.cancel_deletion(store=store, actor=request.user)
    except deletion_service.DeletionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "درخواستِ حذفِ فروشگاه لغو شد.")
    return redirect("portal:request-store-deletion", store_public_id=store.public_id)


# ---------------------------------------------------------------------------
# Ownership transfer — two-party OTP-gated (Section 15)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_OWNERSHIP_TRANSFER = "store_ownership_transfer"
_SESSION_PENDING_TRANSFER_PHONE_KEY = "portal_pending_transfer_phone"


@owner_required
def initiate_ownership_transfer(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending_transfer = store.ownership_transfers.filter(status=StoreOwnershipTransfer.Status.PENDING).first()

    if request.method == "POST" and pending_transfer is None:
        target_phone_raw = (request.POST.get("target_phone") or "").strip()
        try:
            target_phone = normalize_iranian_phone(target_phone_raw)
        except InvalidPhoneError as exc:
            messages.error(request, str(exc.messages[0] if exc.messages else exc))
            return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_OWNERSHIP_TRANSFER) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_OWNERSHIP_TRANSFER, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_OWNERSHIP_TRANSFER, target=target, phone=phone,
                    message="کدِ تأییدِ انتقالِ مالکیتِ فروشگاه: {code}",
                    client_ip=request.META.get("REMOTE_ADDR", ""),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_TRANSFER_PHONE_KEY] = target_phone
            return redirect("portal:ownership-transfer-step-up", store_public_id=store.public_id)

        try:
            ownership_transfer_service.initiate_transfer(
                store=store, initiated_by=request.user, target_phone=target_phone,
            )
        except ownership_transfer_service.OwnershipTransferError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "درخواستِ انتقالِ مالکیت ثبت شد؛ تا پذیرشِ طرفِ مقابل در انتظار می‌ماند.")
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

    return render(request, "portal/app/ownership_transfer.html", {
        "store": store, "pending_transfer": pending_transfer,
    })


@owner_required
def ownership_transfer_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            target_phone = request.session.pop(_SESSION_PENDING_TRANSFER_PHONE_KEY, "")
            try:
                ownership_transfer_service.initiate_transfer(
                    store=store, initiated_by=request.user, target_phone=target_phone,
                )
            except ownership_transfer_service.OwnershipTransferError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "درخواستِ انتقالِ مالکیت ثبت شد؛ تا پذیرشِ طرفِ مقابل در انتظار می‌ماند.")
            return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
@require_POST
def cancel_ownership_transfer(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    transfer = store.ownership_transfers.filter(status=StoreOwnershipTransfer.Status.PENDING).first()
    if transfer is None:
        messages.error(request, "انتقالِ در-انتظاری برایِ لغو وجود ندارد.")
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
    try:
        ownership_transfer_service.cancel_transfer(transfer=transfer, actor=request.user)
    except ownership_transfer_service.OwnershipTransferError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "درخواستِ انتقالِ مالکیت لغو شد.")
    return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)


def accept_ownership_transfer(request, token):
    """صفحه‌ی عمومیِ پذیرشِ انتقال — طرفِ مقابل ممکن است اصلاً هنوز حسابی
    نداشته باشد، پس ``owner_required`` نیست. تنها با OTPِ خودِ
    ``transfer.target_phone`` (نه نشستِ مالکِ فعلی) قابلِ پذیرش است."""
    transfer = ownership_transfer_service.get_pending_transfer_by_token(token)
    if transfer is None or transfer.is_expired:
        return render(request, "portal/public/ownership_transfer_accept.html", {"transfer": None}, status=404)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "request_code":
            try:
                owner_otp_service.request_otp(
                    phone=transfer.target_phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP,
                    client_ip=request.META.get("REMOTE_ADDR", "unknown"),
                    message="کدِ پذیرشِ مالکیتِ فروشگاه: {code}",
                )
                messages.success(request, "کد ارسال شد.")
            except owner_otp_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
        elif action == "verify_code":
            code = request.POST.get("code", "")
            ok = owner_otp_service.verify_otp(
                phone=transfer.target_phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP, code=code,
            )
            if ok:
                try:
                    _updated, new_owner = ownership_transfer_service.accept_transfer(transfer=transfer)
                except ownership_transfer_service.OwnershipTransferError as exc:
                    messages.error(request, str(exc))
                else:
                    auth_login(request, new_owner)
                    messages.success(request, "مالکیتِ فروشگاه با موفقیت به شما منتقل شد.")
                    return redirect("portal:app-home")
            else:
                messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/public/ownership_transfer_accept.html", {"transfer": transfer})


# ---------------------------------------------------------------------------
# In-app notifications (Section 16)
# ---------------------------------------------------------------------------


@owner_required
def notifications_list(request):
    from apps.notifications.models import NotificationOutbox

    notifications = NotificationOutbox.objects.filter(
        recipient_user=request.user, channel=NotificationOutbox.Channel.IN_APP,
    ).order_by("-created_at")[:100]

    if request.method == "POST":
        NotificationOutbox.objects.filter(
            recipient_user=request.user, channel=NotificationOutbox.Channel.IN_APP, read_at__isnull=True,
        ).update(read_at=timezone.now())
        return redirect("portal:notifications")

    return render(request, "portal/app/notifications.html", {"notifications": notifications})
