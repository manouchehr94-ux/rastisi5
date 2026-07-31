from django.test import TestCase, override_settings

from apps.portal.services.owner_sms_service import get_platform_sms_backend, send_platform_sms
from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsSendResult


class GetPlatformSmsBackendTests(TestCase):
    @override_settings(RASTISI_OWNER_SMS_BACKEND="console")
    def test_console_is_default(self):
        self.assertIsInstance(get_platform_sms_backend(), ConsoleBackend)

    @override_settings(
        RASTISI_OWNER_SMS_BACKEND="melipayamak",
        RASTISI_OWNER_SMS_USERNAME="user1",
        RASTISI_OWNER_SMS_PASSWORD="pass1",
        RASTISI_OWNER_SMS_SENDER="10001",
    )
    def test_melipayamak_selected_when_configured(self):
        backend = get_platform_sms_backend()
        self.assertIsInstance(backend, MelipayamakBackend)
        self.assertEqual(backend.username, "user1")

    @override_settings(
        RASTISI_OWNER_SMS_BACKEND="kavenegar",
        RASTISI_OWNER_SMS_API_KEY="key1",
        RASTISI_OWNER_SMS_SENDER="10001",
    )
    def test_kavenegar_selected_when_configured(self):
        backend = get_platform_sms_backend()
        self.assertIsInstance(backend, KavenegarBackend)
        self.assertEqual(backend.api_key, "key1")


class SendPlatformSmsTests(TestCase):
    @override_settings(RASTISI_OWNER_SMS_BACKEND="console")
    def test_never_raises_and_returns_backend_result(self):
        result = send_platform_sms(to="09121234567", text="کد ورود شما: 123456")
        self.assertIsInstance(result, SmsSendResult)
        self.assertTrue(result.success)

    @override_settings(
        RASTISI_OWNER_SMS_BACKEND="melipayamak",
        RASTISI_OWNER_SMS_USERNAME="", RASTISI_OWNER_SMS_PASSWORD="", RASTISI_OWNER_SMS_SENDER="",
    )
    def test_failed_send_does_not_raise(self):
        result = send_platform_sms(to="09121234567", text="کد ورود شما: 123456")
        self.assertFalse(result.success)
