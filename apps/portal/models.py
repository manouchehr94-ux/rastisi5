import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class OwnerProfile(TimeStampedModel):
    """Portal-only profile data for a Store-owner ``User``.

    Deliberately separate from ``apps.customers.models.Customer`` (ADR-93):
    an owner registering through the portal never gets a ``Customer`` row as
    a side effect, and a storefront customer never gets an ``OwnerProfile``.
    Both are optional one-to-one extensions of the same plain ``auth.User``
    table — a person can hold either, both, or neither.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="owner_profile",
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField(
        "موبایل", max_length=15, unique=True, null=True, blank=True,
        help_text="فرمتِ متعارف ۰۹xxxxxxxxx — شناسه‌ی اصلیِ ورودِ OTP (Section 3).",
    )

    class Meta:
        verbose_name = "پروفایل مالک"
        verbose_name_plural = "پروفایل‌های مالک"

    def __str__(self):
        return self.full_name or self.phone or self.user.email


class OwnerOtpChallenge(TimeStampedModel):
    """کدِ یکبارمصرفِ ورود/ثبت‌نامِ مالک با موبایل (Section 3).

    ``code_hash`` — نه متنِ خامِ کد — ذخیره می‌شود (با همان هَشرِ رمزِ عبورِ
    جنگو، ``django.contrib.auth.hashers``)؛ حتی دسترسیِ خواندنی به دیتابیس
    کدِ OTP فعال را فاش نمی‌کند."""

    class Purpose(models.TextChoices):
        REGISTER = "register", "ثبت‌نام"
        LOGIN = "login", "ورود"

    phone = models.CharField("موبایل", max_length=15, db_index=True)
    purpose = models.CharField("هدف", max_length=10, choices=Purpose.choices)
    code_hash = models.CharField("هَشِ کد", max_length=200)
    attempt_count = models.PositiveSmallIntegerField("تعداد تلاشِ تأیید", default=0)
    expires_at = models.DateTimeField("زمان انقضا")
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)

    class Meta:
        verbose_name = "کدِ یکبارمصرفِ مالک"
        verbose_name_plural = "کدهای یکبارمصرفِ مالک"
        indexes = [
            models.Index(fields=["phone", "purpose", "created_at"], name="idx_owner_otp_phone_purpose"),
        ]

    def __str__(self):
        return f"OTP:{self.phone}:{self.purpose}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired


def _generate_handoff_token() -> str:
    return secrets.token_urlsafe(32)


class AdminHandoffTicket(TimeStampedModel):
    """Single-use, short-lived ticket bridging owner-portal auth to a Store's
    distinct Merchant Admin host (ADR-98).

    ``SESSION_COOKIE_DOMAIN`` is unset in this project (host-only cookies by
    design), so a logged-in owner on the portal host has no session on
    ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}``. This ticket is
    issued only for a (user, store) pair with an active ``StoreMembership``,
    is valid for a short window, and is consumed exactly once (atomically) by
    the admin-host handoff view, which then calls Django's own ``login()``
    for that host. It grants no authorization by itself — every subsequent
    admin-portal request still goes through the existing ``staff_required``/
    membership checks unchanged.
    """

    token = models.CharField("توکن", max_length=64, unique=True, default=_generate_handoff_token, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    destination_path = models.CharField("مسیر مقصد", max_length=200, default="/admin-portal/")
    expires_at = models.DateTimeField("زمان انقضا")
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)

    class Meta:
        verbose_name = "بلیت ورود به پنل مدیریت"
        verbose_name_plural = "بلیت‌های ورود به پنل مدیریت"
        indexes = [
            models.Index(fields=["token", "consumed_at"], name="idx_handoff_token_consumed"),
        ]

    def __str__(self):
        return f"handoff:{self.user_id}->{self.store_id}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired


#: Sensitive owner actions that MAY require fresh step-up OTP verification
#: (spec §3.20). This is the whitelist enforced on
#: ``PlatformConfiguration.step_up_actions`` — an arbitrary key can never be
#: added via the edit form, only these. Not every key is wired to an actual
#: enforcement point yet; ``step_up_service`` (a later slice) is the single
#: place that reads this list at the moment a sensitive action needs it.
STEP_UP_ACTION_CHOICES = (
    ("subscription_purchase_confirm", "تأیید خرید اشتراک"),
    ("permanent_handle_claim", "ثبت نهاییِ نام دائمی فروشگاه"),
    ("custom_domain_activate", "فعال‌سازی دامنه‌ی اختصاصی"),
    ("store_delete", "حذف فروشگاه"),
    ("store_ownership_transfer", "انتقال مالکیت فروشگاه"),
    ("owner_email_change", "تغییر ایمیل مالک"),
    ("owner_phone_change", "تغییر شماره موبایل مالک"),
    ("owner_security_change", "تغییر امنیتی حساب مالک"),
    ("staff_high_privilege_add", "افزودن عضو تیم با دسترسی بالا"),
    ("staff_owner_remove", "حذف یک مالک دیگر"),
    ("payment_method_change", "تغییر روش پرداخت"),
    ("platform_superuser_change", "تغییرات حساس مدیر پلتفرم"),
)
STEP_UP_ACTION_KEYS = frozenset(key for key, _label in STEP_UP_ACTION_CHOICES)

#: Defaults chosen conservatively: every irreversible/high-impact action
#: starts protected; low-risk ones start off so the platform owner opts in.
DEFAULT_STEP_UP_ACTIONS = {
    "subscription_purchase_confirm": True,
    "permanent_handle_claim": True,
    "custom_domain_activate": True,
    "store_delete": True,
    "store_ownership_transfer": True,
    "owner_email_change": True,
    "owner_phone_change": True,
    "owner_security_change": True,
    "staff_high_privilege_add": True,
    "staff_owner_remove": True,
    "payment_method_change": False,
    "platform_superuser_change": True,
}


class PlatformConfiguration(TimeStampedModel):
    """Singleton, platform-wide editable configuration (spec §Section 2).

    Exactly one row ever exists (``pk=1``, enforced by ``save()``). Read via
    ``apps.portal.services.platform_config_service.get_platform_
    configuration()`` — cached, never queried per-template-render directly.
    Edited only through Platform Admin, by a superuser, with every change
    audited (``PlatformAuditLogEntry``).
    """

    default_trial_days = models.PositiveIntegerField("روزهای پیش‌فرض دوره‌ی آزمایشی", default=30)
    deletion_retention_days = models.PositiveIntegerField(
        "روزهای نگهداریِ داده پس از درخواست حذف", default=365,
        help_text="بین ۱۸۰ تا ۳۶۵ روز (۶ تا ۱۲ ماه).",
    )
    primary_brand_color = models.CharField("رنگ اصلی برند", max_length=7, default="#10a37a")
    secondary_brand_color = models.CharField("رنگ ثانویه برند", max_length=7, default="#e0a72e")
    temporary_logo_text = models.CharField(
        "نشان موقت برند (متنی)", max_length=20, default="راستیسی",
        help_text="تا زمانی‌که لوگوی نهایی آپلود نشده، همین‌جا نمایش داده می‌شود.",
    )
    logo = models.ImageField("لوگوی نهایی", upload_to="platform/", null=True, blank=True)
    support_contact_phone = models.CharField("تلفن پشتیبانی", max_length=20, blank=True, default="")
    support_contact_email = models.EmailField("ایمیل پشتیبانی", blank=True, default="")
    step_up_actions = models.JSONField(
        "سیاست تأیید مجدد (Step-up OTP)", default=dict,
        help_text="نگاشتِ کلیدِ عملیات به روشن/خاموش — فقط کلیدهای STEP_UP_ACTION_CHOICES مجازند.",
    )
    default_payment_provider = models.CharField("درگاه پرداخت پیش‌فرض", max_length=40, default="manual")
    enabled_payment_providers = models.JSONField(
        "درگاه‌های پرداخت فعال", default=list,
        help_text="فهرستِ کدهای درگاه فعال — نمایش‌دادنی در تسویه‌حساب اشتراک.",
    )

    class Meta:
        verbose_name = "تنظیمات پلتفرم"
        verbose_name_plural = "تنظیمات پلتفرم"

    def __str__(self):
        return "تنظیمات پلتفرم راستیسی"

    def save(self, *args, **kwargs):
        self.pk = 1
        if not self.step_up_actions:
            self.step_up_actions = dict(DEFAULT_STEP_UP_ACTIONS)
        if not self.enabled_payment_providers:
            self.enabled_payment_providers = [self.default_payment_provider]
        super().save(*args, **kwargs)


class PlatformAuditLogEntry(models.Model):
    """Platform-level audit trail — same shape/intent as
    ``apps.core.models.AuditLogEntry`` (ADR-36), but for events that are not
    owned by exactly one Store (editing global platform configuration, Plan
    definitions, a superuser's own access to Platform Admin, ...). Store-
    scoped superuser actions (trial adjustment on a specific Store, a
    deletion/transfer decision) still use the existing Store-owned
    ``AuditLogEntry`` — this model is additive, not a replacement.
    """

    class ResultStatus(models.TextChoices):
        SUCCESS = "success", "موفق"
        FAILURE = "failure", "ناموفق"

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="platform_audit_log_entries",
    )
    action_code = models.CharField("کد عملیات", max_length=60, db_index=True)
    object_type = models.CharField("نوع شیء", max_length=60, blank=True, default="")
    object_id = models.CharField("شناسه‌ی شیء", max_length=40, blank=True, default="")
    object_label = models.CharField("برچسبِ شیء", max_length=200, blank=True, default="")
    before_summary = models.TextField("خلاصه‌ی پیش از تغییر", blank=True, default="")
    after_summary = models.TextField("خلاصه‌ی پس از تغییر", blank=True, default="")
    metadata = models.JSONField("متادیتا", default=dict, blank=True)
    result = models.CharField(
        "نتیجه", max_length=10, choices=ResultStatus.choices, default=ResultStatus.SUCCESS,
    )

    class Meta:
        verbose_name = "رخداد حسابرسی پلتفرم"
        verbose_name_plural = "رخدادهای حسابرسی پلتفرم"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action_code", "created_at"], name="idx_pf_audit_action_created"),
        ]

    def __str__(self):
        return f"{self.action_code} @ {self.created_at:%Y-%m-%d %H:%M}"


class ContactMessage(TimeStampedModel):
    """پیامِ ثبت‌شده از فرم «تماس با ما»ی سایت عمومی راستیسی.

    فقط ذخیره می‌کند — بدون صف/ارسال پیامک/ایمیل خودکار. بازبینیِ این پیام‌ها
    بخشی از پنل مدیریت پلتفرم (Section M) است."""

    full_name = models.CharField("نام", max_length=150)
    email = models.EmailField("ایمیل")
    subject = models.CharField("موضوع", max_length=200, blank=True, default="")
    message = models.TextField("پیام")
    is_reviewed = models.BooleanField("بررسی‌شده", default=False)

    class Meta:
        verbose_name = "پیام تماس"
        verbose_name_plural = "پیام‌های تماس"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"
