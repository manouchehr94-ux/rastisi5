from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.sms.models import OtpCode, SmsLog, SmsTemplate
from apps.sms.services import otp_service
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RequestOtpTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()

    def test_creates_six_digit_code_with_two_minute_expiry(self):
        otp = otp_service.request_otp("09121234567", store=self.store)
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())
        expected_expiry = timezone.now() + timedelta(seconds=otp_service.OTP_TTL_SECONDS)
        self.assertAlmostEqual(otp.expires_at.timestamp(), expected_expiry.timestamp(), delta=5)

    def test_sends_otp_sms_and_logs_it(self):
        otp_service.request_otp("09121234567", store=self.store)
        log = SmsLog.objects.filter(recipient="09121234567").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_rate_limit_after_three_requests_in_window(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp_service.request_otp("09121234567", store=self.store)
        with self.assertRaises(otp_service.OtpRateLimitError):
            otp_service.request_otp("09121234567", store=self.store)

    def test_rate_limit_is_per_phone(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp_service.request_otp("09121234567", store=self.store)
        # شماره‌ی دیگر باید بدون مشکل کد بگیرد
        otp_service.request_otp("09129999999", store=self.store)

    def test_old_requests_outside_window_do_not_count(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp = otp_service.request_otp("09121234567", store=self.store)
            OtpCode.objects.filter(pk=otp.pk).update(
                created_at=timezone.now() - timedelta(seconds=otp_service.REQUEST_WINDOW_SECONDS + 60)
            )
        otp_service.request_otp("09121234567", store=self.store)  # نباید خطا بدهد


class VerifyOtpTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()
        self.otp = otp_service.request_otp("09121234567", store=self.store)

    def test_correct_code_succeeds_and_marks_used(self):
        result = otp_service.verify_otp("09121234567", self.otp.code)
        self.assertTrue(result.is_used)

    def test_wrong_code_raises_and_increments_attempt_count(self):
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", "000000")
        self.otp.refresh_from_db()
        self.assertEqual(self.otp.attempt_count, 1)

    def test_no_code_for_phone_raises(self):
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09120000000", "123456")

    def test_expired_code_raises(self):
        self.otp.expires_at = timezone.now() - timedelta(seconds=1)
        self.otp.save()
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", self.otp.code)

    def test_already_used_code_cannot_be_reused(self):
        otp_service.verify_otp("09121234567", self.otp.code)
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", self.otp.code)

    def test_too_many_attempts_invalidate_code(self):
        for _ in range(otp_service.MAX_VERIFY_ATTEMPTS):
            with self.assertRaises(otp_service.OtpInvalidError):
                otp_service.verify_otp("09121234567", "000000")
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", self.otp.code)
