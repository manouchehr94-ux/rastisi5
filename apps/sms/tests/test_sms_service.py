from django.test import TestCase

from apps.core.models import ShopSettings
from apps.sms.events import SmsEvent
from apps.sms.models import SmsLog, SmsTemplate
from apps.sms.services.sms_service import (
    SmsTemplateError,
    get_backend,
    send_event_sms,
    send_test_sms,
    validate_template_body,
)
from apps.sms.services.backends import ConsoleBackend, MelipayamakBackend


class ValidateTemplateBodyTests(TestCase):
    def test_allowed_variable_passes(self):
        validate_template_body(SmsEvent.WELCOME, "{customer_name} خوش آمدید به {shop_name}")

    def test_unknown_variable_raises_clear_error(self):
        with self.assertRaises(SmsTemplateError) as ctx:
            validate_template_body(SmsEvent.WELCOME, "کد شما {otp_code} است")
        self.assertIn("otp_code", str(ctx.exception))

    def test_body_without_variables_is_valid(self):
        validate_template_body(SmsEvent.WELCOME, "متن ساده بدون متغیر")


class GetBackendTests(TestCase):
    def test_console_is_default(self):
        self.assertIsInstance(get_backend(), ConsoleBackend)

    def test_melipayamak_selected_when_configured(self):
        shop = ShopSettings.load()
        shop.sms_backend = ShopSettings.SmsBackend.MELIPAYAMAK
        shop.save()
        self.assertIsInstance(get_backend(), MelipayamakBackend)


class SendEventSmsTests(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()

    def test_creates_sent_log_via_console_backend(self):
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"})
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertIn("سارا", log.message)
        self.assertEqual(log.recipient, "09121234567")

    def test_disabled_system_sends_nothing_and_logs_nothing(self):
        shop = ShopSettings.load()
        shop.sms_enabled = False
        shop.save()
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"})

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_inactive_template_sends_nothing(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        template.is_active = False
        template.save()
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"})

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_missing_template_sends_nothing(self):
        SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).delete()
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"})
        self.assertIsNone(result)

    def test_corrupted_template_never_raises_and_creates_no_log(self):
        """اگر (خارج از اعتبارسنجی فرم) یک قالب با متغیر ناشناخته در دیتابیس باشد، ارسال نباید کرش کند."""
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        SmsTemplate.objects.filter(pk=template.pk).update(body="{this_is_not_allowed}")
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"})

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_context_missing_a_variable_does_not_crash(self):
        """اگر فراخوان یک متغیر مجاز را پاس ندهد، رندر باید با مقدار خالی جایگزین شود نه کرش."""
        log = send_event_sms(SmsEvent.ORDER_SHIPPED, "09121234567", {"customer_name": "سارا", "order_code": "DM-1"})
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_shop_name_always_comes_from_shop_settings(self):
        shop = ShopSettings.load()
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا", "shop_name": "نام جعلی"})
        self.assertIn(shop.name, log.message)
        self.assertNotIn("نام جعلی", log.message)


class SendTestSmsTests(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()

    def test_sends_regardless_of_global_disable(self):
        shop = ShopSettings.load()
        shop.sms_enabled = False
        shop.save()

        log = send_test_sms(event_key=SmsEvent.WELCOME, phone="09121234567")
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_sends_even_if_template_is_inactive(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.OTP)
        template.is_active = False
        template.save()

        log = send_test_sms(event_key=SmsEvent.OTP, phone="09121234567")
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertIn("۱۲۳۴۵۶", log.message)

    def test_missing_template_raises_clear_error(self):
        SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).delete()
        with self.assertRaises(SmsTemplateError):
            send_test_sms(event_key=SmsEvent.WELCOME, phone="09121234567")
