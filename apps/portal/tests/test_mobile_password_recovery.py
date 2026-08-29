"""پوششِ تست برایِ بازیابیِ رمز با موبایل+OTP (Section 4/E — تکمیلِ احرازِ
هویتِ مالک): درخواست، تأییدِ کد، تعیینِ رمزِ جدید، enumeration-safety،
و رگرسیونِ مسیرِ ایمیلِ موجود."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerOtpChallenge
from apps.portal.services import owner_auth_service

User = get_user_model()
_HOST = "rastisi.localhost"
_STRONG_PASSWORD = "Str0ng!Passw0rd"
_NEW_STRONG_PASSWORD = "Another!Str0ngPass9"


def _fixed_code(test_case, code="445566"):
    import apps.portal.services.owner_otp_service as svc

    original = svc._generate_code
    svc._generate_code = lambda: code
    test_case.addCleanup(setattr, svc, "_generate_code", original)
    return code


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class MobileResetRequestTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.owner, _ = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234700", full_name="Known Owner",
        )

    def test_known_phone_request_redirects_to_otp_verify(self):
        response = self.client.post("/reset-password/", {"identifier": "09121234700"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/verify/", response["Location"])
        self.assertTrue(
            OwnerOtpChallenge.objects.filter(
                phone="09121234700", purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET,
            ).exists()
        )

    def test_unknown_phone_gets_the_same_redirect_as_known_phone(self):
        """Enumeration-safety: the HTTP response for a never-registered
        number must be indistinguishable from a real one — same status
        code, same redirect target — while creating no challenge/SMS."""
        known_response = self.client.post("/reset-password/", {"identifier": "09121234700"}, HTTP_HOST=_HOST)
        self.client.session.flush()
        unknown_response = self.client.post("/reset-password/", {"identifier": "09190000001"}, HTTP_HOST=_HOST)

        self.assertEqual(known_response.status_code, unknown_response.status_code)
        self.assertEqual(
            known_response["Location"].rsplit("?", 1)[0], unknown_response["Location"].rsplit("?", 1)[0],
        )
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone="09190000001").exists())

    def test_unknown_phone_does_not_create_a_user_or_profile(self):
        from apps.portal.models import OwnerProfile

        self.client.post("/reset-password/", {"identifier": "09190000002"}, HTTP_HOST=_HOST)
        self.assertFalse(User.objects.filter(username="09190000002").exists())
        self.assertFalse(OwnerProfile.objects.filter(phone="09190000002").exists())

    def test_inactive_phone_gets_the_same_redirect_as_active_phone_and_creates_no_challenge(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        response = self.client.post("/reset-password/", {"identifier": "09121234700"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/verify/", response["Location"])
        self.assertFalse(
            OwnerOtpChallenge.objects.filter(
                phone="09121234700", purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET,
            ).exists()
        )


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class MobileResetOtpVerifyTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.owner, _ = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234701", full_name="Verify Owner",
        )

    def _start(self, code="445566"):
        _fixed_code(self, code)
        self.client.post("/reset-password/", {"identifier": "09121234701"}, HTTP_HOST=_HOST)

    def test_correct_code_redirects_to_set_password(self):
        self._start()
        response = self.client.post(
            "/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/set/", response["Location"])

    def test_correct_code_does_not_log_the_user_in(self):
        self._start()
        self.client.post("/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_incorrect_code_is_rejected(self):
        self._start()
        response = self.client.post(
            "/reset-password/verify/", {"phone": "09121234701", "code": "000000"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نادرست")

    def test_expired_code_is_rejected(self):
        self._start()
        challenge = OwnerOtpChallenge.objects.get(
            phone="09121234701", purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET,
        )
        challenge.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])

        response = self.client.post(
            "/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نادرست")

    def test_replayed_code_is_rejected(self):
        self._start()
        self.client.post("/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST)
        # Start a fresh pending-verify session (the first one was consumed
        # by the successful verify above), then try the same code again.
        session = self.client.session
        session["portal_mobile_reset_pending_phone"] = "09121234701"
        session.save()
        response = self.client.post(
            "/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نادرست")

    def test_max_attempt_exceeded_invalidates_the_code(self):
        import apps.portal.services.owner_otp_service as svc

        self._start()
        for _ in range(svc.MAX_VERIFY_ATTEMPTS):
            self.client.post(
                "/reset-password/verify/", {"phone": "09121234701", "code": "000000"}, HTTP_HOST=_HOST,
            )
        response = self.client.post(
            "/reset-password/verify/", {"phone": "09121234701", "code": "445566"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نادرست")

    def test_direct_access_without_pending_request_redirects_to_request_page(self):
        response = self.client.get("/reset-password/verify/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response["Location"])

    def test_resend_issues_a_new_code_without_revealing_phone_existence(self):
        self._start()
        response = self.client.post("/reset-password/verify/", {"resend": "1"}, HTTP_HOST=_HOST, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            OwnerOtpChallenge.objects.filter(
                phone="09121234701", purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET,
            ).count(),
            2,
        )


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class MobileResetSetPasswordTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.owner, _ = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234702", full_name="Set Password Owner",
        )

    def _verified_client(self, code="778899"):
        _fixed_code(self, code)
        self.client.post("/reset-password/", {"identifier": "09121234702"}, HTTP_HOST=_HOST)
        self.client.post("/reset-password/verify/", {"phone": "09121234702", "code": code}, HTTP_HOST=_HOST)

    def test_direct_access_without_verification_is_rejected(self):
        response = self.client.get("/reset-password/set/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response["Location"])

    def test_mismatched_confirmation_is_rejected(self):
        self._verified_client()
        response = self.client.post(
            "/reset-password/set/",
            {"password": _NEW_STRONG_PASSWORD, "password_confirm": "somethingelse123!"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.check_password(_NEW_STRONG_PASSWORD))

    def test_weak_password_is_rejected(self):
        self._verified_client()
        response = self.client.post(
            "/reset-password/set/", {"password": "123", "password_confirm": "123"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "p-error")

    def test_valid_new_password_succeeds_and_old_password_stops_working(self):
        owner_auth_service.set_new_password(user=self.owner, password=_STRONG_PASSWORD)
        self._verified_client()
        response = self.client.post(
            "/reset-password/set/",
            {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(_NEW_STRONG_PASSWORD))
        self.assertFalse(self.owner.check_password(_STRONG_PASSWORD))

    def test_reset_state_is_cleared_after_success_and_cannot_be_reused(self):
        self._verified_client()
        self.client.post(
            "/reset-password/set/",
            {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        # Same session, same page, immediately after success — the
        # authorization must already be gone.
        response = self.client.get("/reset-password/set/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response["Location"])

    def test_expired_authorization_is_rejected(self):
        self._verified_client()
        session = self.client.session
        session["portal_mobile_reset_authorized"] = {
            "user_id": self.owner.pk, "expires_at": timezone.now().timestamp() - 1,
        }
        session.save()
        response = self.client.get("/reset-password/set/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response["Location"])

    def test_final_post_derives_the_account_only_from_server_side_session_state(self):
        """The POST body carries no user/phone identifier at all — only
        ``password``/``password_confirm``. Whatever account
        ``portal_mobile_reset_authorized`` names in the session is exactly
        the account whose password changes; there is no client-supplied
        identifier the endpoint could read instead, which is what makes a
        cross-account transfer structurally impossible."""
        other_owner, _ = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234703", full_name="Other Owner",
        )
        self._verified_client()
        session = self.client.session
        session["portal_mobile_reset_authorized"] = {
            "user_id": other_owner.pk, "expires_at": timezone.now().timestamp() + 900,
        }
        session.save()

        self.client.post(
            "/reset-password/set/",
            {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        other_owner.refresh_from_db()
        self.owner.refresh_from_db()
        self.assertTrue(other_owner.check_password(_NEW_STRONG_PASSWORD))
        self.assertFalse(self.owner.check_password(_NEW_STRONG_PASSWORD))

    def test_inactive_owner_cannot_complete_reset_even_with_prior_verification(self):
        self._verified_client()
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        response = self.client.get("/reset-password/set/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response["Location"])

    def test_preexisting_unusable_password_owner_can_establish_first_usable_password(self):
        """A phone-registered owner from before this batch (or one who
        never finished the old flow) has ``set_unusable_password()`` —
        this recovery path must still work for them, with no data
        migration required."""
        self.assertFalse(self.owner.has_usable_password())
        self._verified_client()
        response = self.client.post(
            "/reset-password/set/",
            {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_usable_password())

        login_response = self.client.post(
            "/login/password/", {"identifier": "09121234702", "password": _NEW_STRONG_PASSWORD}, HTTP_HOST=_HOST,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class EmailResetRegressionTests(TestCase):
    """The pre-existing email password-reset flow must keep working
    unchanged after ``PasswordResetRequestForm`` gained a unified
    ``identifier`` field."""

    def setUp(self):
        self.user = owner_auth_service.register_owner(
            full_name="Email Owner", email="emailreset@example.com", password=_STRONG_PASSWORD,
        )

    def test_known_email_still_sends_reset_mail(self):
        response = self.client.post(
            "/reset-password/", {"identifier": "emailreset@example.com"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("emailreset@example.com", mail.outbox[0].to)

    def test_unknown_email_sends_no_mail_and_does_not_error(self):
        response = self.client.post(
            "/reset-password/", {"identifier": "nobody-at-all@example.com"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_full_email_reset_flow_still_changes_password(self):
        owner_auth_service.request_password_reset(
            email="emailreset@example.com", base_url="https://rastisi.ir",
        )
        path = mail.outbox[0].body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        response = self.client.post(
            path, {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_NEW_STRONG_PASSWORD))

    def test_email_reset_token_reuse_is_still_rejected(self):
        owner_auth_service.request_password_reset(
            email="emailreset@example.com", base_url="https://rastisi.ir",
        )
        path = mail.outbox[0].body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        self.client.post(
            path, {"password": _NEW_STRONG_PASSWORD, "password_confirm": _NEW_STRONG_PASSWORD}, HTTP_HOST=_HOST,
        )
        response = self.client.get(path, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 400)
