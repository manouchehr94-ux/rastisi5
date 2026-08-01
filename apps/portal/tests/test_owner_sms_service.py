from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.services.owner_sms_service import get_platform_sms_backend, send_platform_sms
from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsSendResult


class GetPlatformSmsBackendTests(TestCase):
    def setUp(self):
        cache.clear()

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

    @override_settings(RASTISI_OWNER_SMS_BACKEND="kavenegar", RASTISI_OWNER_SMS_API_KEY="env-key")
    def test_platform_configuration_takes_priority_over_env_settings(self):
        """اگر Platform Admin چیزی در PlatformConfiguration تنظیم کرده
        باشد، آن مقدم بر env است — env فقط fallback برایِ استقرارهایی است
        که هنوز از طریقِ Platform Admin پیکربندی نشده‌اند."""
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.sms_backend = "melipayamak"
        config.set_sms_credentials(melipayamak_username="db-user", melipayamak_password="db-pass")
        config.save()
        cache.delete("portal:platform_configuration")

        backend = get_platform_sms_backend()
        self.assertIsInstance(backend, MelipayamakBackend)
        self.assertEqual(backend.username, "db-user")


class SendPlatformSmsTests(TestCase):
    def setUp(self):
        cache.clear()

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
