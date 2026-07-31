"""صندوقِ پایدارِ اعلان‌ها (Section 16) — درون‌برنامه‌ای/پیامک/ایمیل، همه از
یک صفِ واحد. هر اعلان یک ردیفِ ``PENDING`` است تا واقعاً تحویل داده شود
(``deliver_pending``) — پس یک خطای گذرا در ارسالِ پیامک هرگز خودِ اعلان را
گم نمی‌کند، فقط آن را ``FAILED`` می‌کند و بعداً قابلِ ری‌تلاش است.

اعلان‌هایِ امنیتی (``is_security=True``) هیچ مکانیزمِ opt-out‌ی ندارند —
``notify_security_event`` تنها مسیرِ ساختِ آن‌هاست و همیشه صف می‌کند."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationOutbox(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "درون‌برنامه‌ای"
        SMS = "sms", "پیامک"
        EMAIL = "email", "ایمیل"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظارِ ارسال"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    channel = models.CharField("کانال", max_length=10, choices=Channel.choices)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="گیرنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications",
    )
    recipient_phone = models.CharField("موبایلِ گیرنده", max_length=15, blank=True, default="")
    recipient_email = models.EmailField("ایمیلِ گیرنده", blank=True, default="")
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        null=True, blank=True, related_name="notifications",
    )
    subject = models.CharField("موضوع", max_length=200, blank=True, default="")
    body = models.TextField("متن")
    is_security = models.BooleanField("اعلانِ امنیتی (غیرِقابلِ‌غیرفعال‌سازی)", default=False)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField("تعدادِ تلاش", default=0)
    last_error = models.TextField("آخرین خطا", blank=True, default="")
    sent_at = models.DateTimeField("زمانِ ارسال", null=True, blank=True)
    read_at = models.DateTimeField("زمانِ خوانده‌شدن", null=True, blank=True)
    metadata = models.JSONField("فراداده", default=dict, blank=True)

    class Meta:
        verbose_name = "اعلان"
        verbose_name_plural = "اعلان‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_user", "channel", "-created_at"], name="idx_notif_user_channel"),
            models.Index(fields=["status", "channel"], name="idx_notif_status_channel"),
        ]

    def __str__(self):
        return f"{self.get_channel_display()} → {self.recipient_user or self.recipient_phone or self.recipient_email}"
