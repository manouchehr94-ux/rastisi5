"""پوششِ تست برایِ گامِ اجباریِ تعیینِ رمزِ عبور پس از ثبت‌نامِ موبایلی
(Section 3.F — تکمیلِ احرازِ هویتِ مالک). مالکِ تازه پس از تأییدِ OTP دیگر
بلافاصله فروشگاه نمی‌گیرد؛ باید اول رمز تعیین کند."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"
_STRONG_PASSWORD = "Str0ng!Passw0rd"


def _fixed_code(test_case):
    import apps.portal.services.owner_otp_service as svc

    original = svc._generate_code
    svc._generate_code = lambda: "222333"
    test_case.addCleanup(setattr, svc, "_generate_code", original)
    return "222333"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegistrationReachesPasswordSetupTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_new_mobile_registration_redirects_to_password_setup_after_otp(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "New Owner", "phone": "09300000001"}, HTTP_HOST=_HOST)
        response = self.client.post("/verify/", {"phone": "09300000001", "code": code}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/register/set-password/", response["Location"])

        user = User.objects.get(username="09300000001")
        self.assertFalse(user.has_usable_password())
        # Authenticated already (OTP itself is the identity proof) —
        # otherwise the password-setup page couldn't even be reached.
        self.assertIn("_auth_user_id", self.client.session)
        # No Store yet — provisioning is deferred until after password setup.
        self.assertFalse(StoreMembership.objects.filter(user=user).exists())

    def test_weak_password_is_rejected(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Weak Pw", "phone": "09300000002"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000002", "code": code}, HTTP_HOST=_HOST)

        response = self.client.post(
            "/register/set-password/", {"password": "123", "password_confirm": "123"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "p-error")
        user = User.objects.get(username="09300000002")
        self.assertFalse(user.has_usable_password())

    def test_mismatched_confirmation_is_rejected(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Mismatch", "phone": "09300000003"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000003", "code": code}, HTTP_HOST=_HOST)

        response = self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": "SomethingElse!123"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="09300000003")
        self.assertFalse(user.has_usable_password())

    def test_valid_password_is_stored_hashed_and_usable(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Valid Pw", "phone": "09300000004"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000004", "code": code}, HTTP_HOST=_HOST)

        response = self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="09300000004")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(_STRONG_PASSWORD))
        self.assertNotIn(_STRONG_PASSWORD, user.password)  # hashed, not stored raw

    def test_password_never_appears_in_session_before_being_set(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "No Session Pw", "phone": "09300000005"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000005", "code": code}, HTTP_HOST=_HOST)

        session_values = [str(v) for v in self.client.session.items()]
        self.assertFalse(any(_STRONG_PASSWORD in v for v in session_values))

    def test_provisioning_happens_exactly_once(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Once", "phone": "09300000006"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000006", "code": code}, HTTP_HOST=_HOST)
        response = self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/onboarding/", response["Location"])

        user = User.objects.get(username="09300000006")
        self.assertEqual(
            StoreMembership.objects.filter(
                user=user, status=StoreMembership.MembershipStatus.ACTIVE,
            ).count(),
            1,
        )
        self.assertEqual(Store.objects.filter(name="فروشگاه من").count(), 1)

    def test_refresh_after_completion_does_not_create_a_second_store(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Refresh", "phone": "09300000007"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000007", "code": code}, HTTP_HOST=_HOST)
        self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )

        # Simulates hitting back/refresh on the (now stale) password-setup
        # page — GET must not re-render the form, and definitely must not
        # allow a second POST to create a second Store.
        get_response = self.client.get("/register/set-password/", HTTP_HOST=_HOST)
        self.assertEqual(get_response.status_code, 302)

        user = User.objects.get(username="09300000007")
        self.assertEqual(StoreMembership.objects.filter(user=user).count(), 1)

    def test_completed_phone_registration_can_logout_and_login_with_mobile_and_password(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Logout Login", "phone": "09300000008"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000008", "code": code}, HTTP_HOST=_HOST)
        self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.client.post("/logout/", HTTP_HOST=_HOST)

        response = self.client.post(
            "/login/password/",
            {"identifier": "09300000008", "password": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_completed_phone_registration_can_still_login_with_otp(self):
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Still OTP", "phone": "09300000009"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000009", "code": code}, HTTP_HOST=_HOST)
        self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.client.post("/logout/", HTTP_HOST=_HOST)

        import apps.portal.services.owner_otp_service as svc

        svc._generate_code = lambda: "999888"
        self.client.post("/login/", {"phone": "09300000009"}, HTTP_HOST=_HOST)
        response = self.client.post("/verify/", {"phone": "09300000009", "code": "999888"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_password_setup_page_requires_authentication(self):
        response = self.client.get("/register/set-password/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_owner_with_existing_usable_password_hitting_setup_url_is_redirected_not_reprompted(self):
        """A returning owner who somehow lands on this URL (e.g. a stale
        bookmark) must never be asked to overwrite their real password —
        the DB-truth guard (``has_usable_password()``) redirects them away
        before the form is even rendered."""
        code = _fixed_code(self)
        self.client.post("/register/", {"full_name": "Returning", "phone": "09300000010"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09300000010", "code": code}, HTTP_HOST=_HOST)
        self.client.post(
            "/register/set-password/",
            {"password": _STRONG_PASSWORD, "password_confirm": _STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )

        response = self.client.get("/register/set-password/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/onboarding/", response["Location"])
