from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ بروزرسانی", auto_now=True)

    class Meta:
        abstract = True


class ShopSettings(TimeStampedModel):
    """تنظیمات سراسری فروشگاه — رکورد تکی (singleton).

    منبع واحد حقیقت برای هویت فروشگاه و قواعد قیمت‌گذاری؛ هم پنل مدیریت
    (مرحله‌ی ۱۴) این رکورد را ویرایش می‌کند، هم سرویس pricing (مرحله‌ی ۲) و
    context processor سراسری سایت همین رکورد را می‌خوانند — نه یک عدد جدا.
    """

    name = models.CharField("نام فروشگاه", max_length=150, default="فروشگاه اینترنتی")
    tagline = models.CharField("شعار فروشگاه", max_length=200, blank=True)
    description = models.TextField("توضیحات فروشگاه (درباره ما)", blank=True)
    contact_phone = models.CharField("شماره تماس", max_length=30, blank=True)
    contact_email = models.EmailField("ایمیل فروشگاه", blank=True)
    contact_address = models.CharField("آدرس", max_length=300, blank=True)

    tax_percent = models.DecimalField("نرخ مالیات (٪)", max_digits=5, decimal_places=2, default=9)
    free_shipping_threshold = models.DecimalField(
        "آستانه‌ی ارسال رایگان (تومان)", max_digits=12, decimal_places=0, default=500_000
    )

    class SmsBackend(models.TextChoices):
        CONSOLE = "console", "کنسول (فقط لاگ، برای توسعه)"
        MELIPAYAMAK = "melipayamak", "ملی‌پیامک"

    sms_enabled = models.BooleanField("فعال‌سازی سیستم پیامک", default=True)
    sms_backend = models.CharField(
        "درگاه پیامک", max_length=20, choices=SmsBackend.choices, default=SmsBackend.CONSOLE
    )
    sms_sender_number = models.CharField("شماره‌ی فرستنده", max_length=20, blank=True)
    melipayamak_username = models.CharField("نام کاربری ملی‌پیامک", max_length=100, blank=True)
    melipayamak_password = models.CharField("رمز عبور ملی‌پیامک", max_length=100, blank=True)

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

    def __str__(self):
        return self.name

    @classmethod
    def load(cls) -> "ShopSettings":
        """رکورد تکی تنظیمات را برمی‌گرداند؛ در اولین فراخوانی از روی settings.py بوت‌استرپ می‌شود."""
        from django.conf import settings

        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            "name": getattr(settings, "SHOP_NAME", "فروشگاه اینترنتی"),
            "tagline": getattr(settings, "SHOP_TAGLINE", ""),
            "contact_phone": getattr(settings, "SHOP_CONTACT_PHONE", ""),
            "contact_email": getattr(settings, "SHOP_CONTACT_EMAIL", ""),
            "contact_address": getattr(settings, "SHOP_CONTACT_ADDRESS", ""),
            "tax_percent": getattr(settings, "SHOP_TAX_PERCENT", 9),
            "free_shipping_threshold": getattr(settings, "SHOP_FREE_SHIPPING_THRESHOLD", 500_000),
        })
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
