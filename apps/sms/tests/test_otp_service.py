from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.sms.models import OtpCode, SmsLog, SmsTemplate
from apps.sms.services import otp_service
from apps.stores.models import Store

TEST_IP = "1.2.3.4"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _fixed_code(code="392017"):
    """Monkeypatches otp_service._generate_code so tests know the real
    code without ever reading it back from storage (code_hash only stores
    a hash, matching apps.portal.models.OwnerOtpChallenge's pattern)."""
    original = otp_service._generate_code
    otp_service._generate_code = lambda: code
    return original


class RequestOtpTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()
        cache.clear()

    def test_creates_hashed_code_with_two_minute_expiry(self):
        original = _fixed_code("123456")
        self.addCleanup(setattr, otp_service, "_generate_code", original)
        otp = otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)
        self.assertNotEqual(otp.code_hash, "123456")
        self.assertTrue(check_password("123456", otp.code_hash))
        expected_expiry = timezone.now() + timedelta(seconds=otp_service.OTP_TTL_SECONDS)
        self.assertAlmostEqual(otp.expires_at.timestamp(), expected_expiry.timestamp(), delta=5)

    def test_sends_otp_sms_and_logs_it(self):
        otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)
        log = SmsLog.objects.filter(recipient="09121234567").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_rate_limit_after_three_requests_in_window(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)
        with self.assertRaises(otp_service.OtpRateLimitError):
            otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)

    def test_rate_limit_is_per_phone(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)
        # شماره‌ی دیگر باید بدون مشکل کد بگیرد
        otp_service.request_otp("09129999999", store=self.store, ip_address=TEST_IP)

    def test_old_requests_outside_window_do_not_count(self):
        for _ in range(otp_service.MAX_REQUESTS_PER_WINDOW):
            otp = otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)
            OtpCode.objects.filter(pk=otp.pk).update(
                created_at=timezone.now() - timedelta(seconds=otp_service.REQUEST_WINDOW_SECONDS + 60)
            )
        otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)  # نباید خطا بدهد

    def test_ip_rate_limit_across_different_phones(self):
        """محدودیتِ IP مستقل از محدودیتِ شماره است — با شماره‌های متفاوت هم
        باید پس از IP_MAX_REQUESTS درخواست، رد شود (جلوگیری از پیامک‌بمب‌گذاریِ
        شماره‌های زیاد از یک IP واحد)."""
        for i in range(otp_service.IP_MAX_REQUESTS):
            otp_service.request_otp(f"0912000{i:04d}", store=self.store, ip_address=TEST_IP)
        with self.assertRaises(otp_service.OtpRateLimitError):
            otp_service.request_otp("09120009999", store=self.store, ip_address=TEST_IP)

    def test_ip_rate_limit_is_independent_per_ip(self):
        for i in range(otp_service.IP_MAX_REQUESTS):
            otp_service.request_otp(f"0912000{i:04d}", store=self.store, ip_address=TEST_IP)
        # یک IP دیگر باید بدون مشکل کد بگیرد
        otp_service.request_otp("09121119999", store=self.store, ip_address="9.9.9.9")

    def test_ip_rate_limit_rejects_before_creating_any_otp_row(self):
        for i in range(otp_service.IP_MAX_REQUESTS):
            otp_service.request_otp(f"0912000{i:04d}", store=self.store, ip_address=TEST_IP)
        count_before = OtpCode.objects.count()
        with self.assertRaises(otp_service.OtpRateLimitError):
            otp_service.request_otp("09120009999", store=self.store, ip_address=TEST_IP)
        self.assertEqual(OtpCode.objects.count(), count_before)


class VerifyOtpTests(TestCase):
    CODE = "654321"

    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()
        cache.clear()
        original = _fixed_code(self.CODE)
        self.addCleanup(setattr, otp_service, "_generate_code", original)
        self.otp = otp_service.request_otp("09121234567", store=self.store, ip_address=TEST_IP)

    def test_correct_code_succeeds_and_marks_used(self):
        result = otp_service.verify_otp("09121234567", self.CODE)
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
            otp_service.verify_otp("09121234567", self.CODE)

    def test_already_used_code_cannot_be_reused(self):
        otp_service.verify_otp("09121234567", self.CODE)
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", self.CODE)

    def test_too_many_attempts_invalidate_code(self):
        for _ in range(otp_service.MAX_VERIFY_ATTEMPTS):
            with self.assertRaises(otp_service.OtpInvalidError):
                otp_service.verify_otp("09121234567", "000000")
        with self.assertRaises(otp_service.OtpInvalidError):
            otp_service.verify_otp("09121234567", self.CODE)

    def test_code_is_never_stored_in_plaintext(self):
        self.assertNotEqual(self.otp.code_hash, self.CODE)
