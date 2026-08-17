from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.sms.events import SmsEvent
from apps.sms.models import SmsBalance, SmsBillingPolicy, SmsLog, SmsTemplate
from apps.sms.services.backends import SmsSendResult
from apps.sms.services.billing_policy_service import quote_message
from apps.sms.services.sms_service import send_event_sms
from apps.stores.models import Store


def store():
    return Store.objects.get(slug="akhlaghi")


class SmsBillingPolicyTests(TestCase):
    def test_defaults_and_character_pricing(self):
        policy = SmsBillingPolicy.load()
        self.assertEqual((policy.chars_per_credit, policy.price_per_credit_toman, policy.otp_overdraft_limit), (70, 205, 10))
        self.assertEqual(quote_message("x" * 70).billable_units, 1)
        quote = quote_message("x" * 71)
        self.assertEqual(quote.billable_units, 2)
        self.assertEqual(quote.cost_toman, 410)


class SmsCreditGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = store()
        SmsTemplate.ensure_defaults()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})

    def test_normal_sms_is_blocked_at_zero_without_provider_call(self):
        with patch("apps.sms.services.sms_service.get_backend") as backend:
            log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        backend.assert_not_called()  # اعتبار قبل از resolve/تماس Provider کنترل می‌شود
        self.assertEqual(log.status, SmsLog.Status.FAILED)
        self.assertIn("اعتبار", log.error_message)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 0)
        self.assertEqual(log.attempt_count, 0)

    @override_settings(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=True)
    def test_otp_can_overdraft_to_minus_ten_but_not_minus_eleven(self):
        for _ in range(10):
            log = send_event_sms(SmsEvent.OTP, "09121234567", {"otp_code": "864209"}, store=self.store)
            self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, -10)
        blocked = send_event_sms(SmsEvent.OTP, "09121234567", {"otp_code": "864209"}, store=self.store)
        self.assertEqual(blocked.status, SmsLog.Status.FAILED)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, -10)

    def test_71_characters_cost_two_credits_and_410_toman(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        template.body = "x" * 71
        template.save()
        SmsBalance.objects.filter(store=self.store).update(credits=5)
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {}, store=self.store)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertEqual((log.character_count, log.billable_units, log.cost_toman), (71, 2, 410))
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 3)


    @patch("apps.sms.services.sms_service.get_backend")
    def test_non_otp_melipayamak_body_id_uses_pattern_route(self, get_backend):
        from apps.sms.services.backends import MelipayamakBackend

        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        template.body = "سلام {customer_name} از {shop_name}"
        template.melipayamak_body_id = "778899"
        template.melipayamak_variables_order = "customer_name,shop_name"
        template.save()
        SmsBalance.objects.filter(store=self.store).update(credits=5)

        backend = MelipayamakBackend(username="u", password="p", sender="1000")
        backend.send_pattern = Mock(return_value=SmsSendResult(success=True, provider_ref_id="pattern-1"))
        get_backend.return_value = backend

        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)

        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertEqual(log.provider, "melipayamak")
        backend.send_pattern.assert_called_once()
        kwargs = backend.send_pattern.call_args.kwargs
        self.assertEqual(kwargs["body_id"], "778899")
        self.assertEqual(kwargs["variables_order"], "customer_name,shop_name")
        self.assertEqual(kwargs["variables"]["customer_name"], "سارا")
        self.assertTrue(kwargs["variables"]["shop_name"])

    @patch("apps.sms.services.sms_service.get_backend")
    def test_provider_failure_refunds_reserved_credit(self, get_backend):
        backend = get_backend.return_value
        backend.provider_code = "melipayamak"
        backend.send.return_value = SmsSendResult(success=False, error_message="down", provider="melipayamak")
        SmsBalance.objects.filter(store=self.store).update(credits=2)
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        self.assertEqual(log.status, SmsLog.Status.FAILED)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 2)
        self.assertEqual(log.cost_toman, 0)


class PlatformOwnerOtpLogTests(TestCase):
    @patch(
        "apps.portal.services.owner_otp_service.send_platform_otp",
        return_value=SmsSendResult(success=True, provider_ref_id="mp-1", provider="melipayamak"),
    )
    def test_owner_otp_is_logged_without_storing_secret_body(self, _send):
        from apps.portal.services import owner_otp_service

        cache.clear()
        SmsTemplate.ensure_defaults()
        owner_otp_service.request_otp(
            phone="09121234567", purpose="register", client_ip="1.2.3.4",
        )
        log = SmsLog.objects.filter(
            store__isnull=True, event_key=SmsEvent.PLATFORM_OWNER_OTP,
        ).latest("created_at")
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertEqual(log.provider, "melipayamak")
        self.assertEqual(log.message, "")
        self.assertGreater(log.character_count, 0)
        self.assertNotIn("123456", log.message)


class NotificationSmsCreditGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = store()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})

    def test_store_scoped_raw_notification_cannot_bypass_zero_balance(self):
        from apps.sms.services.sms_service import send_raw_sms

        log = send_raw_sms(
            phone="09121234567", message="اعلان امنیتی", store=self.store,
            event_key=SmsEvent.NOTIFICATION,
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.FAILED)
        self.assertEqual(log.attempt_count, 0)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 0)


@override_settings(ALLOWED_HOSTS=["platformadmins.rastisi.localhost", "testserver"])
class SmsControlCenterAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="sms2-admin", email="sms2-admin@example.com", password="strong-password-1",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.user)
        SmsTemplate.ensure_defaults()

    def test_three_control_center_pages_exist(self):
        host = "platformadmins.rastisi.localhost"
        for url in ("/sms/providers/", "/sms/templates/", "/sms/messages/"):
            self.assertEqual(self.client.get(url, HTTP_HOST=host).status_code, 200)

    def test_owner_can_edit_policy(self):
        response = self.client.post("/sms/providers/", {
            "action": "save_policy", "chars_per_credit": "65",
            "price_per_credit_toman": "250", "otp_overdraft_limit": "12",
        }, HTTP_HOST="platformadmins.rastisi.localhost")
        self.assertEqual(response.status_code, 302)
        policy = SmsBillingPolicy.load()
        self.assertEqual((policy.chars_per_credit, policy.price_per_credit_toman, policy.otp_overdraft_limit), (65, 250, 12))

    def test_owner_can_edit_template_provider_ids(self):
        response = self.client.post("/sms/templates/platform_owner_otp/", {
            "action": "save", "title": "OTP مالک",
            "body": "کد: {otp_code} تا {expire_minutes} دقیقه", "is_active": "on",
            "melipayamak_body_id": "778899",
            "melipayamak_variables_order": "otp_code,expire_minutes",
            "kavenegar_template": "RastisiOtp",
        }, HTTP_HOST="platformadmins.rastisi.localhost")
        self.assertEqual(response.status_code, 302)
        template = SmsTemplate.objects.get(event_key=SmsEvent.PLATFORM_OWNER_OTP)
        self.assertEqual(template.melipayamak_body_id, "778899")
        self.assertEqual(template.kavenegar_template, "RastisiOtp")

    def test_messages_page_includes_platform_logs(self):
        SmsLog.objects.create(
            store=None, event_key=SmsEvent.PLATFORM_OWNER_OTP, recipient="09121234567",
            message="", status=SmsLog.Status.SENT, provider="melipayamak",
            character_count=35, billable_units=1, unit_price_toman=205, cost_toman=205,
        )
        response = self.client.get("/sms/messages/", HTTP_HOST="platformadmins.rastisi.localhost")
        self.assertContains(response, "RastiSi")
        self.assertContains(response, "ملی‌پیامک")
        self.assertContains(response, "OTP محافظت‌شده")
    def test_template_rejects_unknown_pattern_variable_order(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.PLATFORM_OWNER_OTP)
        original = template.melipayamak_body_id
        response = self.client.post("/sms/templates/platform_owner_otp/", {
            "action": "save", "title": template.title,
            "body": "کد: {otp_code} تا {expire_minutes} دقیقه", "is_active": "on",
            "melipayamak_body_id": "778899",
            "melipayamak_variables_order": "otp_code,not_allowed",
        }, HTTP_HOST="platformadmins.rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "متغیر نامعتبر")
        template.refresh_from_db()
        self.assertEqual(template.melipayamak_body_id, original)

