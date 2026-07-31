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
    path("app/stores/<uuid:store_public_id>/created/", views.store_created, name="store-created"),
    path("app/stores/<uuid:store_public_id>/enter-admin/", views.enter_admin, name="enter-admin"),
]
