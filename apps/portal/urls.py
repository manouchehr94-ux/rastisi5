from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    # Public marketing site (Section A)
    path("", views.home, name="home"),
    path("features/", views.features, name="features"),
    path("plans/", views.plans, name="plans"),
    path("help/", views.help_center, name="help"),
    path("contact/", views.contact, name="contact"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    # Owner identity (Section B/3) — phone+OTP is the primary flow.
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("verify/", views.otp_verify, name="otp-verify"),
    path("logout/", views.logout_view, name="logout"),
    # Legacy email+password — kept for existing accounts/platform-superuser
    # recovery, not linked from the primary nav (Section 3).
    path("register-email/", views.register_email, name="register-email"),
    path("login-email/", views.login_email, name="login-email"),
    path("reset-password/", views.password_reset_request, name="password-reset-request"),
    path("reset-password/<uidb64>/<token>/", views.password_reset_confirm, name="password-reset-confirm"),
    # Owner account portal (Section E/F/G/D)
    path("app/", views.app_home, name="app-home"),
    path("app/stores/new/", views.store_create, name="store-create"),
    path("app/stores/<uuid:store_public_id>/onboarding/", views.onboarding, name="onboarding"),
    path(
        "app/stores/<uuid:store_public_id>/onboarding/identity/",
        views.onboarding_identity, name="onboarding-identity",
    ),
    path(
        "app/stores/<uuid:store_public_id>/onboarding/industry/",
        views.onboarding_industry, name="onboarding-industry",
    ),
    path(
        "app/stores/<uuid:store_public_id>/onboarding/branding/",
        views.onboarding_branding, name="onboarding-branding",
    ),
    path(
        "app/stores/<uuid:store_public_id>/onboarding/review/",
        views.onboarding_review, name="onboarding-review",
    ),
    path("app/stores/<uuid:store_public_id>/created/", views.store_created, name="store-created"),
    path("app/stores/<uuid:store_public_id>/enter-admin/", views.enter_admin, name="enter-admin"),
    # Platform billing — subscription purchase (Section 8/9)
    path("app/stores/<uuid:store_public_id>/billing/", views.billing_plans, name="billing-plans"),
    path(
        "app/stores/<uuid:store_public_id>/billing/checkout/<int:plan_version_id>/",
        views.billing_checkout, name="billing-checkout",
    ),
    path(
        "app/stores/<uuid:store_public_id>/billing/step-up/",
        views.billing_step_up_verify, name="billing-step-up",
    ),
    path(
        "billing/dev-provider/<str:attempt_public_id>/",
        views.billing_dev_provider, name="billing-dev-provider",
    ),
    path(
        "app/stores/<uuid:store_public_id>/billing/invoices/<str:invoice_public_id>/",
        views.billing_return, name="billing-return",
    ),
    # Permanent Store handle claim (Section 11)
    path("app/stores/<uuid:store_public_id>/handle/", views.claim_handle, name="claim-handle"),
    path(
        "app/stores/<uuid:store_public_id>/handle/step-up/",
        views.claim_handle_step_up, name="claim-handle-step-up",
    ),
    # Custom domain — DNS verification and activation (Section 12)
    path("app/stores/<uuid:store_public_id>/domains/", views.custom_domains, name="custom-domains"),
    path(
        "app/stores/<uuid:store_public_id>/domains/<int:domain_id>/begin-verify/",
        views.custom_domain_begin_verify, name="custom-domain-begin-verify",
    ),
    path(
        "app/stores/<uuid:store_public_id>/domains/<int:domain_id>/check/",
        views.custom_domain_check, name="custom-domain-check",
    ),
    path(
        "app/stores/<uuid:store_public_id>/domains/<int:domain_id>/activate/",
        views.custom_domain_activate, name="custom-domain-activate",
    ),
    path(
        "app/stores/<uuid:store_public_id>/domains/activate/step-up/",
        views.custom_domain_activate_step_up, name="custom-domain-activate-step-up",
    ),
    # Store deletion — soft, typed confirmation, step-up gated (Section 14)
    path(
        "app/stores/<uuid:store_public_id>/delete/",
        views.request_store_deletion, name="request-store-deletion",
    ),
    path(
        "app/stores/<uuid:store_public_id>/delete/step-up/",
        views.store_deletion_step_up, name="store-deletion-step-up",
    ),
    path(
        "app/stores/<uuid:store_public_id>/delete/cancel/",
        views.cancel_store_deletion, name="cancel-store-deletion",
    ),
]
