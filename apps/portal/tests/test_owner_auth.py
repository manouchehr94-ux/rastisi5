from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.customers.models import Customer
from apps.portal.models import OwnerProfile
from apps.portal.services import owner_auth_service

User = get_user_model()

_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnerRegistrationTests(TestCase):
    def test_register_creates_user_and_owner_profile_no_customer(self):
        response = self.client.post(
            "/register-email/",
            {"full_name": "Sara Ahmadi", "email": "Sara@Example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="sara@example.com")
        self.assertTrue(OwnerProfile.objects.filter(user=user).exists())
        self.assertFalse(Customer.objects.filter(user=user).exists())
        self.assertFalse(user.is_staff)

    def test_register_rejects_duplicate_email_case_insensitively(self):
        owner_auth_service.register_owner(full_name="A", email="dup@example.com", password="a-very-strong-pass-1")
        with self.assertRaises(owner_auth_service.OwnerAuthError):
            owner_auth_service.register_owner(full_name="B", email="DUP@Example.com", password="another-strong-pass-2")

    def test_register_enforces_password_validation(self):
        with self.assertRaises(owner_auth_service.OwnerAuthError):
            owner_auth_service.register_owner(full_name="A", email="weak@example.com", password="123")

    def test_owner_registration_never_creates_a_customer_profile(self):
        owner_auth_service.register_owner(full_name="A", email="owneronly@example.com", password="a-very-strong-pass-1")
        user = User.objects.get(username="owneronly@example.com")
        self.assertFalse(hasattr(user, "customer_profile"))


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnerLoginLogoutTests(TestCase):
    def setUp(self):
        self.user = owner_auth_service.register_owner(
            full_name="Login Test", email="login@example.com", password="a-very-strong-pass-1",
        )

    def test_login_with_correct_credentials_succeeds(self):
        response = self.client.post(
            "/login-email/", {"email": "login@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_is_case_insensitive_on_email(self):
        response = self.client.post(
            "/login-email/", {"email": "LOGIN@Example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            "/login-email/", {"email": "login@example.com", "password": "wrong-password"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get("/logout/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 405)

    def test_logout_via_post_clears_session(self):
        self.client.force_login(self.user)
        response = self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_redirect_never_follows_external_next(self):
        response = self.client.post(
            "/login-email/",
            {"email": "login@example.com", "password": "a-very-strong-pass-1", "next": "https://evil.example.com/"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response["Location"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = owner_auth_service.register_owner(
            full_name="Reset Test", email="reset@example.com", password="a-very-strong-pass-1",
        )

    def test_request_for_unknown_email_does_not_error_or_reveal_existence(self):
        response = self.client.post("/reset-password/", {"email": "nobody@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_for_known_email_sends_mail(self):
        response = self.client.post("/reset-password/", {"email": "reset@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)

    def test_full_reset_flow_changes_password(self):
        owner_auth_service.request_password_reset(email="reset@example.com", base_url="https://rastisi.ir")
        body = mail.outbox[0].body
        # extract "/reset-password/<uidb64>/<token>/" from the rendered email body
        path = body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        response = self.client.get(path, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            path, {"password": "brand-new-strong-pass-9", "password_confirm": "brand-new-strong-pass-9"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-strong-pass-9"))

    def test_reused_reset_token_is_rejected(self):
        owner_auth_service.request_password_reset(email="reset@example.com", base_url="https://rastisi.ir")
        path = mail.outbox[0].body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        self.client.post(
            path, {"password": "brand-new-strong-pass-9", "password_confirm": "brand-new-strong-pass-9"},
            HTTP_HOST=_HOST,
        )
        # Token is bound to the password hash (Django's default_token_generator);
        # once the password changed, the same link must no longer work.
        response = self.client.get(path, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 400)
