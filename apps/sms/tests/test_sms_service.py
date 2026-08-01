from django.core.cache import cache
from django.test import TestCase

from apps.core.models import ShopSettings
from apps.sms.events import SmsEvent
from apps.sms.models import SmsLog, SmsTemplate
from apps.sms.services.sms_service import (
    RetryNotEligibleError,
    SmsTemplateError,
    get_backend,
    regenerate_smsrasti_device_token,
    retry_failed_log,
    retry_smsrasti_outbox_item,
    send_event_sms,
    send_test_sms,
    validate_template_body,
)
from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsRastiBackend
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
    """زیرساختِ ارسال (ارائه‌دهنده/اعتبارنامه) دیگر Store-scoped نیست —
    ``ShopSettings.sms_backend/melipayamak_*/kavenegar_api_key`` روی
    انتخابِ backend اثری ندارند مگر مقدارِ SMSRASTI (دستگاهِ خودِ Store)؛
    هر مقدارِ دیگر به درگاهِ مرکزیِ پلتفرم (``PlatformConfiguration``)
    برمی‌گردد — نگاه کنید به ``apps.portal.services.owner_sms_service``."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_console_is_default(self):
        self.assertIsInstance(get_backend(store=self.store), ConsoleBackend)

    def test_store_sms_backend_choice_is_ignored_for_non_smsrasti_values(self):
        """قبلاً این مقدار خودِ ارائه‌دهنده را انتخاب می‌کرد؛ اکنون فقط
        SMSRASTI معنا دارد — بقیه‌ی مقادیر همه به درگاهِ مرکزیِ پلتفرم
        می‌روند، صرف‌نظر از این‌که Store چه مقداری برایِ آن ذخیره کرده."""
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.MELIPAYAMAK
        shop.melipayamak_username = "store-owned-username"
        shop.melipayamak_password = "store-owned-password"
        shop.save()
        # پلتفرم هنوز پیکربندی نشده → پیش‌فرضِ کنسول، نه ملی‌پیامکِ Store.
        self.assertIsInstance(get_backend(store=self.store), ConsoleBackend)

    def test_platform_melipayamak_configuration_is_used(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.sms_backend = "melipayamak"
        config.sms_sender_number = "10001"
        config.set_sms_credentials(melipayamak_username="platform-user", melipayamak_password="platform-pass")
        config.save()

        cache.delete("portal:platform_configuration")

        backend = get_backend(store=self.store)
        self.assertIsInstance(backend, MelipayamakBackend)
        self.assertEqual(backend.username, "platform-user")
        self.assertEqual(backend.password, "platform-pass")

    def test_platform_kavenegar_configuration_is_used(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.sms_backend = "kavenegar"
        config.sms_sender_number = "10001"
        config.set_sms_credentials(kavenegar_api_key="platform-api-key")
        config.save()

        cache.delete("portal:platform_configuration")

        backend = get_backend(store=self.store)
        self.assertIsInstance(backend, KavenegarBackend)
        self.assertEqual(backend.api_key, "platform-api-key")

    def test_smsrasti_selected_when_configured(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()
        self.assertIsInstance(get_backend(store=self.store), SmsRastiBackend)

    def test_smsrasti_stays_store_owned_even_when_platform_uses_a_different_provider(self):
        """SmsRasti تنها استثناست: دستگاهِ فیزیکیِ خودِ Store است، نه
        زیرساختِ پلتفرم — انتخابِ آن هرگز از تنظیماتِ پلتفرم نادیده گرفته
        نمی‌شود."""
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.sms_backend = "melipayamak"
        config.set_sms_credentials(melipayamak_username="u", melipayamak_password="p")
        config.save()

        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()

        self.assertIsInstance(get_backend(store=self.store), SmsRastiBackend)


class SendEventSmsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()

    def test_creates_sent_log_via_console_backend(self):
        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertIn("سارا", log.message)
        self.assertEqual(log.recipient, "09121234567")

    def test_successful_send_deducts_one_credit(self):
        from apps.sms.models import SmsBalance

        SmsBalance.objects.create(store=self.store, credits=5)
        send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 4)

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

    def test_otp_event_rejects_smsrasti_backend_with_clear_failed_log(self):
        """اسمس‌راستی صفی/async است — برای OTP حساس‌به‌تأخیر هرگز استفاده
        نمی‌شود؛ باید شکستی واضح و قابل‌مشاهده برای مدیر ثبت شود، نه صف‌شدنِ
        بی‌صدا (apps.sms.models.SmsOutboxItem هرگز نباید برای رویدادِ OTP
        ساخته شود)."""
        from apps.sms.models import SmsOutboxItem

        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()

        log = send_event_sms(SmsEvent.OTP, "09121234567", {"otp_code": "123456"}, store=self.store)

        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.FAILED)
        self.assertEqual(SmsOutboxItem.objects.count(), 0)

    def test_non_otp_event_is_allowed_through_smsrasti_backend(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()

        log = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=self.store)

        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)


class RetryFailedLogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        SmsTemplate.ensure_defaults()

    def test_retry_resends_and_updates_same_row(self):
        log = SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.WELCOME, recipient="09121234567",
            message="سلام سارا", status=SmsLog.Status.FAILED, error_message="خطای قبلی",
        )
        result = retry_failed_log(log_id=log.pk, store=self.store)
        self.assertEqual(result.pk, log.pk)
        self.assertEqual(result.status, SmsLog.Status.SENT)
        self.assertEqual(result.error_message, "")
        self.assertEqual(result.attempt_count, 1)

    def test_retry_of_sent_log_is_rejected(self):
        log = SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.WELCOME, recipient="09121234567",
            message="سلام", status=SmsLog.Status.SENT,
        )
        with self.assertRaises(RetryNotEligibleError):
            retry_failed_log(log_id=log.pk, store=self.store)

    def test_retry_of_pending_log_is_rejected(self):
        log = SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.WELCOME, recipient="09121234567",
            message="سلام", status=SmsLog.Status.PENDING,
        )
        with self.assertRaises(RetryNotEligibleError):
            retry_failed_log(log_id=log.pk, store=self.store)

    def test_unknown_log_id_is_rejected(self):
        with self.assertRaises(RetryNotEligibleError):
            retry_failed_log(log_id=999999, store=self.store)

    def test_cannot_retry_another_stores_log(self):
        other_store = Store.objects.create(name="Store G", slug="store-g-retry", status=Store.Status.ACTIVE)
        log = SmsLog.objects.create(
            store=other_store, event_key=SmsEvent.WELCOME, recipient="09121234567",
            message="سلام", status=SmsLog.Status.FAILED,
        )
        with self.assertRaises(RetryNotEligibleError):
            retry_failed_log(log_id=log.pk, store=self.store)

    def test_otp_log_retry_still_rejects_smsrasti_backend(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()
        log = SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.OTP, recipient="09121234567",
            message="رمز یک‌بارمصرف: 123456", status=SmsLog.Status.FAILED,
        )
        result = retry_failed_log(log_id=log.pk, store=self.store)
        self.assertEqual(result.status, SmsLog.Status.FAILED)


class RetrySmsrastiOutboxItemTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_retry_requeues_failed_item(self):
        from apps.sms.models import SmsOutboxItem

        item = SmsOutboxItem.objects.create(
            store=self.store, phone="09121234567", message="سلام",
            status=SmsOutboxItem.Status.FAILED, error_message="خطا", claimed_at=None,
        )
        result = retry_smsrasti_outbox_item(item_id=item.pk, store=self.store)
        self.assertEqual(result.status, SmsOutboxItem.Status.PENDING)
        self.assertEqual(result.error_message, "")

    def test_retry_of_pending_item_is_rejected(self):
        from apps.sms.models import SmsOutboxItem

        item = SmsOutboxItem.objects.create(store=self.store, phone="09121234567", message="سلام")
        with self.assertRaises(RetryNotEligibleError):
            retry_smsrasti_outbox_item(item_id=item.pk, store=self.store)

    def test_cannot_retry_another_stores_item(self):
        from apps.sms.models import SmsOutboxItem

        other_store = Store.objects.create(name="Store H", slug="store-h-retry", status=Store.Status.ACTIVE)
        item = SmsOutboxItem.objects.create(
            store=other_store, phone="09121234567", message="سلام", status=SmsOutboxItem.Status.FAILED,
        )
        with self.assertRaises(RetryNotEligibleError):
            retry_smsrasti_outbox_item(item_id=item.pk, store=self.store)


class SendTestSmsTests(TestCase):
    def setUp(self):
        cache.clear()
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


class RegenerateSmsrastiDeviceTokenTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_generates_a_new_unique_token_and_persists_it(self):
        token = regenerate_smsrasti_device_token(store=self.store)
        self.assertTrue(token)
        shop = ShopSettings.load(store=self.store)
        self.assertEqual(shop.smsrasti_device_token, token)

    def test_regenerating_invalidates_the_previous_token(self):
        first = regenerate_smsrasti_device_token(store=self.store)
        second = regenerate_smsrasti_device_token(store=self.store)
        self.assertNotEqual(first, second)
        shop = ShopSettings.load(store=self.store)
        self.assertEqual(shop.smsrasti_device_token, second)


class SmsTwoStoreIsolationTests(TestCase):
    """اثبات این‌که پیامک هر Store دقیقاً از تنظیمات/اعتبارنامه‌ی همان Store
    استفاده می‌کند — با دو Store واقعی، نه فقط mock کردن ``ShopSettings.load()``."""

    def setUp(self):
        cache.clear()
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

    def test_store_a_sms_backend_field_never_leaks_into_store_b(self):
        """Store A دیگر با تنظیمِ فیلدِ ذخیره‌شده‌ی خودش (که پس از جداسازیِ
        زیرساختِ پیامک، دیگر ارائه‌دهنده را تعیین نمی‌کند) نمی‌تواند بر
        Store B اثر بگذارد — هر دو یک درگاهِ مرکزیِ پلتفرمِ یکسان دارند."""
        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.sms_backend = ShopSettings.SmsBackend.MELIPAYAMAK
        shop_a.melipayamak_username = "akhlaghi-secret-user"
        shop_a.melipayamak_password = "akhlaghi-secret-pass"
        shop_a.save()

        backend_b = get_backend(store=self.store_b)
        self.assertIsInstance(backend_b, ConsoleBackend)

    def test_both_stores_share_the_same_platform_sms_backend(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.sms_backend = "melipayamak"
        config.set_sms_credentials(melipayamak_username="platform-user", melipayamak_password="platform-pass")
        config.save()

        cache.delete("portal:platform_configuration")

        backend_a = get_backend(store=self.store_a)
        backend_b = get_backend(store=self.store_b)
        self.assertIsInstance(backend_a, MelipayamakBackend)
        self.assertIsInstance(backend_b, MelipayamakBackend)
        self.assertEqual(backend_a.username, backend_b.username)

    def test_missing_store_b_settings_does_not_fall_back_to_store_a(self):
        """Store B که هنوز ShopSettings ندارد باید بی‌صدا شکست بخورد، نه این‌که به Akhlaghi سقوط کند."""
        store_c = Store.objects.create(name="Store C", slug="store-c", status=Store.Status.ACTIVE)
        count_before = SmsLog.objects.count()
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "سارا"}, store=store_c)
        self.assertIsNone(result)
        self.assertEqual(SmsLog.objects.count(), count_before)
