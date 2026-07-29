import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ShopSettingsNotProvisionedError(Exception):
    """Raised by ``ShopSettings.load(store=...)`` when the given Store has
    no ``ShopSettings`` row yet.

    Provisioning is an explicit, separate step (``ShopSettings.provision_for``),
    never a silent read-time side effect — this is raised instead of
    auto-creating a row on read, so a missing row is a visible error, not a
    quietly-materializing default.
    """


def validate_hex_color(value):
    """اعتبارسنجی رنگ #RRGGBB در سطح مدل."""
    if not HEX_COLOR_RE.match(value):
        raise ValidationError("رنگ باید به فرمت #RRGGBB باشد")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ بروزرسانی", auto_now=True)

    class Meta:
        abstract = True


class ShopSettings(TimeStampedModel):
    """تنظیمات هر فروشگاه — دقیقاً یک رکورد به‌ازای هر Store.

    منبع واحد حقیقت برای هویت فروشگاه و قواعد قیمت‌گذاریِ همان Store؛ هم پنل
    مدیریت این رکورد را ویرایش می‌کند، هم سرویس pricing و context processor
    سراسری سایت همین رکورد را می‌خوانند — نه یک عدد جدا.

    ``store`` یک ``OneToOneField`` است: دقیقاً یک ``ShopSettings`` به ازای هر
    Store، نه یک رکورد تکی برای کل پلتفرم. برندینگ/تم (رنگ‌ها، لوگو، فاوآیکون)
    و اطلاعات اتصال پیامک عمداً همچنان همین‌جا هستند — جداسازی این حوزه‌ها به
    مدل‌های اختصاصی یک تصمیم معماری جداگانه‌ی بعدی است، نه بخشی از این مرحله
    (نگاه کنید به ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-10).
    """

    store = models.OneToOneField(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="shop_settings",
    )

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

    # --- هویت بصری ---
    logo = models.ImageField("لوگوی فروشگاه", upload_to="shop/branding/", blank=True)
    favicon = models.ImageField("فاوآیکون", upload_to="shop/branding/", blank=True)
    primary_color = models.CharField("رنگ اصلی", max_length=7, default="#6D28D9", validators=[validate_hex_color])
    accent_color = models.CharField("رنگ مکمل", max_length=7, default="#FF4D77", validators=[validate_hex_color])
    secondary_color = models.CharField("رنگ ثانویه", max_length=7, default="#7C3AED", validators=[validate_hex_color])
    background_color = models.CharField(
        "رنگ پس‌زمینه‌ی صفحه", max_length=7, default="#F7F5FC", validators=[validate_hex_color]
    )
    surface_color = models.CharField(
        "رنگ پس‌زمینه‌ی کارت‌ها", max_length=7, default="#FFFFFF", validators=[validate_hex_color]
    )
    text_color = models.CharField("رنگ متن اصلی", max_length=7, default="#241C3A", validators=[validate_hex_color])
    muted_text_color = models.CharField(
        "رنگ متن کم‌رنگ", max_length=7, default="#8B86A3", validators=[validate_hex_color]
    )

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

    def __str__(self):
        return self.name

    @classmethod
    def load(cls, store=None) -> "ShopSettings":
        """تنظیمات یک Store مشخص، یا در حالت سازگاری موقت، تنظیمات Akhlaghi.

        ``store`` مشخص شود: فقط همان Store برگردانده می‌شود؛ اگر هنوز
        provision نشده باشد ``ShopSettingsNotProvisionedError`` raise
        می‌شود — هرگز تنظیمات یک Store دیگر را برنمی‌گرداند و رکورد جدید هم
        در زمان خواندن ساخته نمی‌شود (provisioning یک قدم صریح و جداست، نه
        اثر جانبی خواندن).

        ``store`` مشخص نشود (حالت سازگاری موقت): فقط وقتی دقیقاً یک Store
        فعال با اسلاگ ``"akhlaghi"`` در کل دیتابیس وجود داشته باشد کار
        می‌کند؛ در غیر این صورت — صفر یا بیش از یک Store — با
        ``apps.stores.resolution.CompatibilityFallbackUnavailableError``
        fail-closed می‌شود (به جای حدس زدن). همان قانون fail-closed منبع
        واحدی دارد که با تحلیل میزبان HTTP هم مشترک است
        (``apps.stores.resolution.resolve_compatibility_store``).
        """
        if store is not None:
            try:
                return cls.objects.get(store=store)
            except cls.DoesNotExist as exc:
                raise ShopSettingsNotProvisionedError(
                    f"Store {store.slug!r} has no ShopSettings row yet; "
                    "provision it explicitly via ShopSettings.provision_for(store)."
                ) from exc

        from apps.stores.resolution import resolve_compatibility_store

        compat_store = resolve_compatibility_store()
        try:
            return cls.objects.get(store=compat_store)
        except cls.DoesNotExist as exc:
            raise ShopSettingsNotProvisionedError(
                f"Store {compat_store.slug!r} has no ShopSettings row yet; "
                "provision it explicitly via ShopSettings.provision_for(store)."
            ) from exc

    @classmethod
    def provision_for(cls, store) -> "ShopSettings":
        """رکورد ShopSettings یک Store را می‌سازد؛ اگر از قبل وجود داشته باشد
        دست‌نخورده برمی‌گردد (idempotent) — هرگز مقادیر تاجر را بازنویسی
        نمی‌کند. مقادیر پیش‌فرض اولیه از settings.py فقط در اولین ساخت
        اعمال می‌شوند (رفتار قبلیِ ``load()`` برای رکورد تکی، اکنون به‌ازای
        هر Store).
        """
        from django.conf import settings as django_settings

        obj, _ = cls.objects.get_or_create(
            store=store,
            defaults={
                "name": getattr(django_settings, "SHOP_NAME", "فروشگاه اینترنتی"),
                "tagline": getattr(django_settings, "SHOP_TAGLINE", ""),
                "contact_phone": getattr(django_settings, "SHOP_CONTACT_PHONE", ""),
                "contact_email": getattr(django_settings, "SHOP_CONTACT_EMAIL", ""),
                "contact_address": getattr(django_settings, "SHOP_CONTACT_ADDRESS", ""),
                "tax_percent": getattr(django_settings, "SHOP_TAX_PERCENT", 9),
                "free_shipping_threshold": getattr(
                    django_settings, "SHOP_FREE_SHIPPING_THRESHOLD", 500_000
                ),
            },
        )
        return obj


class AuditLogEntry(models.Model):
    """رخداد حسابرسیِ Store-owned — یک ردیفِ تغییرناپذیر به‌ازای هر عملیاتِ
    حساس (نگاه کنید به ADR-36 در ``SAAS_DOMAIN_DECISIONS.md``).

    فقط ``created_at`` دارد، نه ``updated_at`` — یک رخداد حسابرسی هرگز پس از
    ثبت ویرایش نمی‌شود؛ اگر لازم شود، یک رخداد اصلاحیِ جدید ثبت می‌شود، نه
    ویرایشِ رکورد قدیمی. ``object_type``/``object_id`` عمداً رشته/عدد ساده‌اند
    (نه ``ContentType`` جنگو) تا این مدل به هیچ اپ دیگری کوپل نشود و بتواند
    رخدادهایی که اصلاً به یک ردیفِ دیتابیسی خاص اشاره نمی‌کنند (مثلاً ورود
    ناموفق) را هم ثبت کند.

    ``ip_address``/``user_agent`` عمداً وجود ندارند: این کدبیس تاکنون هیچ
    سیاست حریم خصوصیِ مصوبی برای نگه‌داریِ IP/User-Agent کاربران ندارد
    (نگاه کنید به ADR-36) — افزودنِ این فیلدها بدون چنین تصمیمی، جمع‌آوریِ
    دادهٔ شخصیِ بی‌سیاست خواهد بود.
    """

    class ResultStatus(models.TextChoices):
        SUCCESS = "success", "موفق"
        FAILURE = "failure", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="audit_log_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_log_entries",
    )
    action_code = models.CharField("کد عملیات", max_length=60, db_index=True)
    object_type = models.CharField("نوع شیء", max_length=60, blank=True, default="")
    object_id = models.CharField("شناسه‌ی شیء", max_length=40, blank=True, default="")
    object_label = models.CharField("برچسبِ قابل‌خواندنِ شیء", max_length=200, blank=True, default="")
    before_summary = models.TextField("خلاصه‌ی پیش از تغییر", blank=True, default="")
    after_summary = models.TextField("خلاصه‌ی پس از تغییر", blank=True, default="")
    metadata = models.JSONField("فراداده", blank=True, default=dict)
    request_id = models.CharField("شناسه‌ی درخواست/idempotency", max_length=100, blank=True, default="")
    result = models.CharField(
        "نتیجه", max_length=10, choices=ResultStatus.choices, default=ResultStatus.SUCCESS,
    )
    created_at = models.DateTimeField("زمان", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "رخداد حسابرسی"
        verbose_name_plural = "گزارش رخدادها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "-created_at"], name="idx_audit_store_created"),
            models.Index(fields=["store", "action_code", "-created_at"], name="idx_audit_store_action"),
        ]

    def __str__(self):
        return f"{self.action_code} — {self.object_label or self.object_type} ({self.get_result_display()})"
