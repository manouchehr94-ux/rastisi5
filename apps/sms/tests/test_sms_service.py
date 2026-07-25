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
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


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
    def setUp(self):
        self.store = _akhlaghi()

    def test_console_is_default(self):
        self.assertIsInstance(get_backend(store=self.store), ConsoleBackend)

    def test_melipayamak_selected_when_configured(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.MELIPAYAMAK
        shop.save()
        self.assertIsInstance(get_backend(store=self.store), MelipayamakBackend)


class SendEventSmsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()

    def test_creates_sent_log_via_console_backend(self):
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertIn("سارا", log.message)
        self.assertEqual(log.recipient, "09121234567")

    def test_disabled_system_sends_nothing_and_logs_nothing(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_enabled = False
        shop.save()
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_inactive_template_sends_nothing(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        template.is_active = False
        template.save()
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_missing_template_sends_nothing(self):
        SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).delete()
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        self.assertIsNone(result)

    def test_corrupted_template_never_raises_and_creates_no_log(self):
        """اگر (خارج از اعتبارسنجی فرم) یک قالب با متغیر ناشناخته در دیتابیس باشد، ارسال نباید کرش کند."""
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        SmsTemplate.objects.filter(pk=template.pk).update(body="{this_is_not_allowed}")
        count_before = SmsLog.objects.count()

        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)

        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)

    def test_context_missing_a_variable_does_not_crash(self):
        """اگر فراخوان یک متغیر مجاز را پاس ندهد، رندر باید با مقدار خالی جایگزین شود نه کرش."""
        log = send_event_sms(
            SmsEvent.ORDER_SHIPPED, "09121234567", {"customer_name": "سارا", "order_code": "DM-1"}, store=self.store
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_shop_name_always_comes_from_shop_settings(self):
        shop = ShopSettings.load(store=self.store)
        log = send_event_sms(
            SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا", "shop_name": "نام جعلی"}, store=self.store
        )
        self.assertIn(shop.name, log.message)
        self.assertNotIn("نام جعلی", log.message)

    def test_store_none_sends_nothing_and_never_falls_back(self):
        """``store=None`` صریح هرگز نباید به Akhlaghi یا هر Store دیگری fallback شود."""
        count_before = SmsLog.objects.count()
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=None)
        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)


class SendTestSmsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()

    def test_sends_regardless_of_global_disable(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_enabled = False
        shop.save()

        log = send_test_sms(event_key=SmsEvent.WELCOME, phone="09121234567", store=self.store)
        self.assertEqual(log.status, SmsLog.Status.SENT)

    def test_sends_even_if_template_is_inactive(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.OTP)
        template.is_active = False
        template.save()

        log = send_test_sms(event_key=SmsEvent.OTP, phone="09121234567", store=self.store)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertIn("۱۲۳۴۵۶", log.message)

    def test_missing_template_raises_clear_error(self):
        SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).delete()
        with self.assertRaises(SmsTemplateError):
            send_test_sms(event_key=SmsEvent.WELCOME, phone="09121234567", store=self.store)


class SmsTwoStoreIsolationTests(TestCase):
    """اثبات این‌که پیامک هر Store دقیقاً از تنظیمات/اعتبارنامه‌ی همان Store
    استفاده می‌کند — با دو Store واقعی، نه فقط mock کردن ``ShopSettings.load()``."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        SmsTemplate.ensure_defaults()

        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.name = "فروشگاه آ"
        shop_a.sms_backend = ShopSettings.SmsBackend.CONSOLE
        shop_a.save()

        shop_b = ShopSettings.provision_for(self.store_b)
        shop_b.name = "فروشگاه ب"
        shop_b.sms_backend = ShopSettings.SmsBackend.CONSOLE
        shop_b.save()

    def test_store_a_sms_uses_store_a_shop_name(self):
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store_a)
        self.assertIn("فروشگاه آ", log.message)

    def test_store_b_sms_uses_store_b_shop_name(self):
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store_b)
        self.assertIn("فروشگاه ب", log.message)
        self.assertNotIn("فروشگاه آ", log.message)

    def test_store_b_never_uses_akhlaghi_backend_configuration(self):
        """اگر Store A روی ملی‌پیامک تنظیم شود، Store B نباید تحت تأثیر قرار بگیرد."""
        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.sms_backend = ShopSettings.SmsBackend.MELIPAYAMAK
        shop_a.melipayamak_username = "akhlaghi-secret-user"
        shop_a.melipayamak_password = "akhlaghi-secret-pass"
        shop_a.save()

        backend_b = get_backend(store=self.store_b)
        self.assertIsInstance(backend_b, ConsoleBackend)

    def test_missing_store_b_settings_does_not_fall_back_to_store_a(self):
        """Store B که هنوز ShopSettings ندارد باید بی‌صدا شکست بخورد، نه این‌که به Akhlaghi سقوط کند."""
        store_c = Store.objects.create(name="Store C", slug="store-c", status=Store.Status.ACTIVE)
        count_before = SmsLog.objects.count()
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=store_c)
        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)
