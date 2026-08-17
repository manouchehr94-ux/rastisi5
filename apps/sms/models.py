from django.conf import settings
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
    melipayamak_body_id = models.CharField(
        "BodyId ملی‌پیامک", max_length=30, blank=True, default="",
        help_text="شناسه الگوی تاییدشده در وب‌سرویس خدماتی ملی‌پیامک.",
    )
    melipayamak_variables_order = models.CharField(
        "ترتیب متغیرهای ملی‌پیامک", max_length=255, blank=True, default="otp_code",
        help_text="نام متغیرها به ترتیب Pattern؛ مثال: otp_code,expire_minutes",
    )
    kavenegar_template = models.CharField(
        "Template کاوه‌نگار", max_length=100, blank=True, default="",
        help_text="نام قالب VerifyLookup برای پیام‌های OTP.",
    )

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


class SmsBillingPolicy(TimeStampedModel):
    """سیاست سراسری قیمت‌گذاری و اعتبار پیامک در سطح پلتفرم.

    فقط رکورد pk=1 توسط پنل مالک پلتفرم استفاده می‌شود. هر ``chars_per_credit``
    کاراکتر یک واحد اعتبار محسوب می‌شود؛ قیمت هر واحد و سقف بدهی OTP نیز
    همین‌جا قابل ویرایش‌اند.
    """

    chars_per_credit = models.PositiveIntegerField("کاراکتر در هر اعتبار", default=70)
    price_per_credit_toman = models.PositiveIntegerField("قیمت هر اعتبار (تومان)", default=205)
    otp_overdraft_limit = models.PositiveIntegerField("سقف بدهی OTP", default=10)

    class Meta:
        verbose_name = "سیاست هزینه پیامک"
        verbose_name_plural = "سیاست هزینه پیامک"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"هر {self.chars_per_credit} کاراکتر = {self.price_per_credit_toman} تومان"


class SmsLog(TimeStampedModel):
    """تاریخچه‌ی هر تلاش برای ارسال پیامک — برای پیگیری و رفع اشکال.

    ``store`` عمداً ``null=True`` است: ردیف‌های پیش از افزودنِ این فیلد
    Store‌شان قابلِ بازسازی نیست (هیچ‌جا ذخیره نشده بود) — به‌جایِ حدس‌زدن یا
    نسبت‌دادنِ نادرست، آن ردیف‌های قدیمی «بی‌صاحب» می‌مانند و
    ``sms_admin_service.filtered_logs`` با فیلترِ الزامیِ Store به‌طورِ
    خودکار از دیدِ همه‌ی داشبوردها کنار گذاشته می‌شوند (ایزوله‌سازیِ
    چندمستأجری — پیش از این فیلد، لاگِ هر Store برایِ همه‌ی Store‌های دیگر
    هم قابلِ دیدن بود، شاملِ متنِ کاملِ پیامکِ OTP)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="sms_logs", null=True, blank=True,
    )
    event_key = models.CharField("رویداد", max_length=30, choices=SmsEvent.choices)
    recipient = models.CharField("گیرنده", max_length=15)
    message = models.TextField("متن نهایی")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField("پیام خطا", blank=True)
    provider_ref_id = models.CharField("شناسه‌ی ارجاع سرویس", max_length=100, blank=True)
    provider = models.CharField("شرکت پیامکی", max_length=20, blank=True, default="")
    character_count = models.PositiveIntegerField("تعداد کاراکتر", default=0)
    billable_units = models.PositiveIntegerField("تعداد اعتبار مصرفی", default=0)
    unit_price_toman = models.PositiveIntegerField("قیمت هر اعتبار (تومان)", default=0)
    cost_toman = models.PositiveBigIntegerField("هزینه نهایی (تومان)", default=0)
    balance_before = models.IntegerField("اعتبار قبل", null=True, blank=True)
    balance_after = models.IntegerField("اعتبار بعد", null=True, blank=True)
    attempt_count = models.PositiveIntegerField("تعداد تلاش", default=0)
    sent_at = models.DateTimeField("زمان ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "گزارش پیامک"
        verbose_name_plural = "گزارش پیامک‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_event_key_display()} → {self.recipient} ({self.get_status_display()})"


class SmsOutboxItem(TimeStampedModel):
    """صفِ پیامک‌های در انتظارِ ارسال توسط گیت‌وی اندرویدِ SmsRasti یک Store.

    برخلافِ ``SmsLog`` (که فقط تاریخچه‌ی یک تلاشِ همزمان است)، این مدل
    چرخه‌ی عمرِ واقعیِ ارسال را دنبال می‌کند: ``pending`` → ``sending``
    (poll شده توسطِ دستگاه، هنوز تأییدنشده) → ``sent``/``failed`` (فقط با
    ack صریحِ دستگاه). هرگز صرفِ poll‌شدن را «ارسال‌شده» علامت نمی‌زند —
    برخلافِ نسخه‌ی باگ‌دارِ مرجع (``reference_imports/.../gateway_api.py``)
    که این کار را می‌کرد؛ اینجا از الگویِ بهترِ نسخه‌ی جایگزین‌شده‌ی همان
    مرجع (``sms_gateway.py``) پیروی شده: claim فقط ``sending`` می‌کند."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENDING = "sending", "در حالِ ارسال"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_outbox_items",
    )
    phone = models.CharField("گیرنده", max_length=15)
    message = models.TextField("متن پیامک")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_ref_id = models.CharField("شناسه‌ی ارجاعِ گیت‌وی", max_length=100, blank=True)
    error_message = models.TextField("پیامِ خطا", blank=True)
    attempt_count = models.PositiveIntegerField("تعدادِ claim", default=0)
    claimed_at = models.DateTimeField("زمانِ claim", null=True, blank=True)
    sent_at = models.DateTimeField("زمانِ ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "پیامِ صفِ SmsRasti"
        verbose_name_plural = "پیام‌هایِ صفِ SmsRasti"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.phone} ({self.get_status_display()})"


class SmsBalance(TimeStampedModel):
    """اعتبارِ باقی‌مانده‌ی پیامکِ هر Store — منبعِ واحدِ حقیقتِ «چند پیامک
    دیگر می‌تواند بفرستد». هر ارسالِ موفق یک واحد کم می‌کند (نگاه کنید به
    ``apps.sms.services.balance_service``)؛ اعتبار فقط با تکمیلِ یک
    ``SmsPackagePurchase`` افزوده می‌شود.

    ارسال‌های عادی بدون اعتبار کافی مسدود می‌شوند. OTP استثنای ایمنی است و
    می‌تواند تا سقف قابل‌تنظیم ``SmsBillingPolicy.otp_overdraft_limit`` وارد
    اعتبار منفی شود تا مشتری فروشگاه در زمان کمبود اعتبار قفل نشود."""

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_balance",
    )
    credits = models.IntegerField("اعتبارِ باقی‌مانده", default=0)

    class Meta:
        verbose_name = "اعتبارِ پیامکِ فروشگاه"
        verbose_name_plural = "اعتبارهایِ پیامکِ فروشگاه"

    def __str__(self):
        return f"{self.store.name} — {self.credits} اعتبار"


class SmsPackage(TimeStampedModel):
    """بسته‌ی خریدِ اعتبارِ پیامک — تعریف‌شده و مدیریت‌شده توسطِ مالکِ پلتفرم
    (Django Admin، فقط superuser)، نه Store. فروشگاه‌ها فقط بسته‌هایِ
    ``is_active=True`` را در تنظیماتِ پیامکِ خودشان می‌بینند و می‌خرند."""

    name = models.CharField("نام بسته", max_length=100)
    credit_amount = models.PositiveIntegerField("تعدادِ اعتبار")
    price = models.DecimalField("قیمت (تومان)", max_digits=12, decimal_places=0)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیبِ نمایش", default=0)

    class Meta:
        verbose_name = "بسته‌ی پیامک"
        verbose_name_plural = "بسته‌های پیامک"
        ordering = ["display_order", "credit_amount"]

    def __str__(self):
        return f"{self.name} ({self.credit_amount} اعتبار)"


class SmsPackagePurchase(TimeStampedModel):
    """رکوردِ درخواستِ خریدِ یک بسته توسطِ یک Store.

    ``PENDING`` یعنی درخواست ثبت شده اما هنوز اعتباری افزوده نشده —
    تکمیلِ واقعیِ پرداخت و افزودنِ اعتبار فقط از مسیرِ Platform Admin
    (``apps.sms.services.balance_service.complete_purchase``) انجام
    می‌شود، نه خودکار در لحظه‌ی ثبتِ درخواست (اتصالِ کاملِ درگاهِ پرداخت
    برایِ خریدِ بسته هنوز پیاده‌سازی نشده — نگاه کنید به یادداشتِ TODO در
    گزارشِ نهایی)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظارِ تکمیل"
        COMPLETED = "completed", "تکمیل‌شده"
        CANCELED = "canceled", "لغوشده"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_package_purchases",
    )
    package = models.ForeignKey(
        SmsPackage, verbose_name="بسته", on_delete=models.PROTECT, related_name="purchases",
    )
    credit_amount = models.PositiveIntegerField("تعدادِ اعتبار (اسنپ‌شات)")
    price = models.DecimalField("قیمت (اسنپ‌شات، تومان)", max_digits=12, decimal_places=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    completed_at = models.DateTimeField("زمانِ تکمیل", null=True, blank=True)

    class Meta:
        verbose_name = "خریدِ بسته‌ی پیامک"
        verbose_name_plural = "خریدهایِ بسته‌ی پیامک"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.store.name} ← {self.package.name} ({self.get_status_display()})"


class SmsCreditAdjustment(TimeStampedModel):
    """دفترِ تغییراتِ دستیِ اعتبارِ پیامکِ یک Store — هر ردیف یک اصلاحِ
    غیرِخودکار (نه ناشی از خرید/مصرفِ عادی) توسطِ یک مدیرِ پلتفرم است، با
    مقدارِ قبل/تغییر/بعد. تغییرناپذیر است (فقط created_at معنا دارد) — یک
    اصلاحِ اشتباه با یک ردیفِ جبرانیِ تازه درست می‌شود، نه ویرایشِ این رکورد."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_credit_adjustments",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sms_credit_adjustments",
    )
    delta = models.IntegerField("مقدارِ تغییر")
    balance_before = models.IntegerField("اعتبارِ پیش از تغییر")
    balance_after = models.IntegerField("اعتبارِ پس از تغییر")
    reason = models.CharField("دلیل", max_length=200)
    note = models.CharField("یادداشتِ داخلی", max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "اصلاحِ اعتبارِ پیامک"
        verbose_name_plural = "اصلاح‌هایِ اعتبارِ پیامک"
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.store.name}: {sign}{self.delta} ({self.reason})"


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
