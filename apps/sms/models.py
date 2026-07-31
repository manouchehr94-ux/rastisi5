from django.db import models

from apps.core.models import TimeStampedModel

from .events import DEFAULT_TEMPLATES, SmsEvent


class SmsTemplate(TimeStampedModel):
    """قالب پیامک هر رویداد — یک رکورد به‌ازای هر کد رویداد، مستقلاً قابل فعال/غیرفعال‌سازی."""

    event_key = models.CharField(
        "رویداد", max_length=30, choices=SmsEvent.choices, unique=True
    )
    title = models.CharField("عنوان", max_length=150)
    body = models.TextField("متن قالب")
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "قالب پیامک"
        verbose_name_plural = "قالب‌های پیامک"
        ordering = ["event_key"]

    def __str__(self):
        return self.title

    @classmethod
    def ensure_defaults(cls) -> None:
        """برای هر رویداد تعریف‌شده که هنوز قالبی ندارد، یک قالب پیش‌فرض می‌سازد (بوت‌استرپ، مثل ShopSettings.load)."""
        existing = set(cls.objects.values_list("event_key", flat=True))
        missing = [event for event in SmsEvent.values if event not in existing]
        cls.objects.bulk_create([
            cls(event_key=event, title=SmsEvent(event).label, body=DEFAULT_TEMPLATES[event])
            for event in missing
        ])


class SmsLog(TimeStampedModel):
    """تاریخچه‌ی هر تلاش برای ارسال پیامک — برای پیگیری و رفع اشکال."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    event_key = models.CharField("رویداد", max_length=30, choices=SmsEvent.choices)
    recipient = models.CharField("گیرنده", max_length=15)
    message = models.TextField("متن نهایی")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField("پیام خطا", blank=True)
    provider_ref_id = models.CharField("شناسه‌ی ارجاع سرویس", max_length=100, blank=True)
    attempt_count = models.PositiveIntegerField("تعداد تلاش", default=0)
    sent_at = models.DateTimeField("زمان ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "گزارش پیامک"
        verbose_name_plural = "گزارش پیامک‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_event_key_display()} → {self.recipient} ({self.get_status_display()})"


class OtpCode(TimeStampedModel):
    """کد یکبار مصرف پیامکی — برای ورود و تأیید شماره موبایل در خرید مهمان.

    ``code_hash`` — نه متنِ خامِ کد — ذخیره می‌شود (با همان هَشرِ رمزِ عبورِ
    جنگو، ``django.contrib.auth.hashers``)، دقیقاً مثلِ ``apps.portal.
    models.OwnerOtpChallenge``؛ حتی دسترسیِ خواندنی به دیتابیس کدِ فعال را
    فاش نمی‌کند (یکپارچه‌سازیِ احرازِ هویت — پیش از این نسخه، ``code``
    متنِ خام بود)."""

    phone = models.CharField("موبایل", max_length=15, db_index=True)
    code_hash = models.CharField("هَشِ کد", max_length=200)
    expires_at = models.DateTimeField("زمان انقضا")
    attempt_count = models.PositiveIntegerField("تعداد تلاش تأیید", default=0)
    is_used = models.BooleanField("مصرف‌شده", default=False)

    class Meta:
        verbose_name = "کد یکبار مصرف"
        verbose_name_plural = "کدهای یکبار مصرف"
        ordering = ["-created_at"]

    def __str__(self):
        status = "مصرف‌شده" if self.is_used else "فعال"
        return f"{self.phone} — {status}"
