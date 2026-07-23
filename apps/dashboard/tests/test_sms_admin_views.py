import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import ShopSettings
from apps.sms.events import SmsEvent
from apps.sms.models import SmsLog, SmsTemplate

User = get_user_model()


class SmsAdminViewsTestCase(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()
        self.staff = User.objects.create_user(username="09121193001", password="pass12345", is_staff=True)
        self.client.login(username="09121193001", password="pass12345")


class SettingsSmsConnectionViewTests(SmsAdminViewsTestCase):
    def test_valid_post_updates_shop_settings(self):
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": "on", "sms_backend": ShopSettings.SmsBackend.MELIPAYAMAK,
            "sms_sender_number": "10001", "melipayamak_username": "user1", "melipayamak_password": "pass1",
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        shop = ShopSettings.load()
        self.assertTrue(shop.sms_enabled)
        self.assertEqual(shop.sms_backend, ShopSettings.SmsBackend.MELIPAYAMAK)
        self.assertEqual(shop.melipayamak_username, "user1")

    def test_unchecked_box_disables_sms(self):
        self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_backend": ShopSettings.SmsBackend.CONSOLE, "sms_sender_number": "",
            "melipayamak_username": "", "melipayamak_password": "",
        })
        self.assertFalse(ShopSettings.load().sms_enabled)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {})
        self.assertRedirects(response, reverse("catalog:home"))


class SmsTemplateFormViewTests(SmsAdminViewsTestCase):
    def setUp(self):
        super().setUp()
        self.template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)

    def test_get_prefills_current_body(self):
        response = self.client.get(reverse("dashboard:sms-template-edit", args=[self.template.pk]))
        self.assertContains(response, self.template.body)
        self.assertContains(response, "customer_name")

    def test_valid_edit_updates_body(self):
        response = self.client.post(
            reverse("dashboard:sms-template-edit", args=[self.template.pk]),
            {"body": "{customer_name} سلام، متن تازه از {shop_name}"},
        )
        self.assertEqual(response.status_code, 200)
        self.template.refresh_from_db()
        self.assertIn("متن تازه", self.template.body)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_unknown_variable_rejected_with_clear_error(self):
        response = self.client.post(
            reverse("dashboard:sms-template-edit", args=[self.template.pk]),
            {"body": "کد شما {otp_code} است"},
        )
        self.assertContains(response, "متغیر ناشناخته")
        self.template.refresh_from_db()
        self.assertNotIn("otp_code", self.template.body)

    def test_empty_body_rejected(self):
        original_body = self.template.body
        response = self.client.post(reverse("dashboard:sms-template-edit", args=[self.template.pk]), {"body": "  "})
        self.assertContains(response, "این فیلد لازم است")
        self.template.refresh_from_db()
        self.assertEqual(self.template.body, original_body)


class SmsTemplateToggleViewTests(SmsAdminViewsTestCase):
    def test_toggle_flips_is_active(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        self.assertTrue(template.is_active)
        response = self.client.post(reverse("dashboard:sms-template-toggle", args=[template.pk]))
        self.assertEqual(response.status_code, 204)
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_disabled_template_stops_sending(self):
        from apps.sms.services.sms_service import send_event_sms

        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        self.client.post(reverse("dashboard:sms-template-toggle", args=[template.pk]))
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "test"})
        self.assertIsNone(result)


class SmsTestSendViewTests(SmsAdminViewsTestCase):
    def test_valid_phone_sends_and_redirects(self):
        response = self.client.post(reverse("dashboard:sms-test-send"), {
            "phone": "09121234567", "event_key": SmsEvent.WELCOME,
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        self.assertTrue(SmsLog.objects.filter(recipient="09121234567").exists())

    def test_invalid_phone_does_not_send(self):
        self.client.post(reverse("dashboard:sms-test-send"), {"phone": "123", "event_key": SmsEvent.WELCOME})
        self.assertFalse(SmsLog.objects.exists())


class SmsLogListViewTests(SmsAdminViewsTestCase):
    def setUp(self):
        super().setUp()
        SmsLog.objects.create(
            event_key=SmsEvent.WELCOME, recipient="09121111111", message="پیام ۱", status=SmsLog.Status.SENT,
        )
        SmsLog.objects.create(
            event_key=SmsEvent.OTP, recipient="09122222222", message="پیام ۲", status=SmsLog.Status.FAILED,
            error_message="خطای اتصال",
        )

    def test_renders_all_logs(self):
        response = self.client.get(reverse("dashboard:sms-log-list"))
        self.assertContains(response, "09121111111")
        self.assertContains(response, "09122222222")

    def test_filter_by_status(self):
        response = self.client.get(reverse("dashboard:sms-log-table"), {"status": SmsLog.Status.FAILED})
        self.assertContains(response, "09122222222")
        self.assertNotContains(response, "09121111111")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:sms-log-list"))
        self.assertRedirects(response, reverse("catalog:home"))
