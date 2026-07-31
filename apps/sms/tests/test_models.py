from django.test import TestCase
from django.utils import timezone

from apps.sms.events import SmsEvent
from apps.sms.models import OtpCode, SmsLog, SmsTemplate


class SmsTemplateEnsureDefaultsTests(TestCase):
    def test_creates_one_row_per_event(self):
        SmsTemplate.ensure_defaults()
        self.assertEqual(SmsTemplate.objects.count(), len(SmsEvent.values))
        self.assertTrue(SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).exists())

    def test_is_idempotent_and_does_not_overwrite_edits(self):
        SmsTemplate.ensure_defaults()
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        template.body = "متن ویرایش‌شده توسط مدیر"
        template.save()

        SmsTemplate.ensure_defaults()

        template.refresh_from_db()
        self.assertEqual(template.body, "متن ویرایش‌شده توسط مدیر")
        self.assertEqual(SmsTemplate.objects.count(), len(SmsEvent.values))

    def test_default_templates_are_active(self):
        SmsTemplate.ensure_defaults()
        self.assertTrue(SmsTemplate.objects.filter(event_key=SmsEvent.OTP).first().is_active)


class SmsLogStrTests(TestCase):
    def test_str_contains_event_and_recipient(self):
        log = SmsLog.objects.create(
            event_key=SmsEvent.WELCOME, recipient="09121234567", message="سلام",
        )
        self.assertIn("09121234567", str(log))


class OtpCodeStrTests(TestCase):
    def test_str_contains_phone_but_never_the_raw_code(self):
        """code_hash stores a hash, never the plaintext code - __str__ must
        never leak it either (e.g. via Django admin/shell repr)."""
        from django.contrib.auth.hashers import make_password

        otp = OtpCode.objects.create(
            phone="09121234567", code_hash=make_password("770099"), expires_at=timezone.now(),
        )
        self.assertIn("09121234567", str(otp))
        self.assertNotIn("770099", str(otp))
        self.assertNotIn(otp.code_hash, str(otp))
