"""دامنه‌ی صورتحساب و پرداختِ SaaS (Checkpoint 5B) — کاملاً جدا از پرداختِ
سفارشِ فروشگاهِ مرچنت (``apps.orders``). نگاه کنید به ADR-73.

این دامنه پاسخ می‌دهد: چه کسی، برایِ کدام فروشگاه، کدام نسخه‌ی پلن، کدام
دوره‌ی صورتحساب، چه مبلغی بدهکار است، چه مبلغی پرداخت شد، کدام Provider آن را
پردازش کرد، کدام Webhook تأییدش کرد، آیا Retry شد، و آیا Credit Note/Refund
صادر شد.

هیچ‌جا داده‌ی خامِ کارت ذخیره نمی‌شود؛ مبالغ فقط ``Decimal`` هستند. واحدِ پول
پیش‌فرض IRT (تومان) است که جزءِ اعشاری ندارد — مانندِ ``PlanVersion.display_price``
با ``decimal_places=0`` مدل می‌شود.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel

#: بیشینه‌ی ارقامِ مبالغِ پولی — هم‌راستا با ``PlanVersion.display_price``.
MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 0
ZERO = Decimal("0")


def _money(**kwargs):
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES,
        default=ZERO, **kwargs,
    )


class StoreBillingAccount(TimeStampedModel):
    """یک حسابِ صورتحسابِ واحد به‌ازایِ هر فروشگاه — «چه کسی/کجا صورتحساب
    می‌شود». فیلدهایش قابلِ ویرایش‌اند، اما فاکتورهایِ تاریخی هنگامِ باز شدن
    یک *اسنپ‌شات* از این حساب می‌گیرند، پس تغییرِ بعدیِ این حساب هرگز فاکتورِ
    گذشته را عوض نمی‌کند (ADR-73/74)."""

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="billing_account",
    )
    legal_name = models.CharField("نام حقوقی/صورتحساب", max_length=200, blank=True, default="")
    billing_email = models.EmailField("ایمیلِ صورتحساب", blank=True, default="")
    billing_phone = models.CharField("تلفنِ صورتحساب", max_length=32, blank=True, default="")

    country = models.CharField("کشور", max_length=64, blank=True, default="")
    region = models.CharField("استان", max_length=100, blank=True, default="")
    city = models.CharField("شهر", max_length=100, blank=True, default="")
    postal_code = models.CharField("کدپستی", max_length=20, blank=True, default="")
    address_line = models.CharField("نشانی", max_length=400, blank=True, default="")

    #: شناسه‌ی مالیاتی (کدِ اقتصادی/شناسه‌ی مالیاتی) — جایی که پشتیبانی شود.
    tax_identifier = models.CharField("شناسه‌ی مالیاتی", max_length=64, blank=True, default="")

    currency = models.CharField("ارز", max_length=8, default="IRT")
    locale = models.CharField("زبان/محلی", max_length=12, default="fa-IR")

    class Meta:
        verbose_name = "حسابِ صورتحسابِ فروشگاه"
        verbose_name_plural = "حساب‌هایِ صورتحسابِ فروشگاه"

    def __str__(self):
        return f"BillingAccount<{self.store.slug}>"

    def snapshot(self) -> dict:
        """یک اسنپ‌شاتِ ساخت‌یافته از فیلدهایِ غیرِحساسِ این حساب برایِ درج در
        فاکتور — تغییرِ بعدیِ حساب این اسنپ‌شات را تغییر نمی‌دهد."""
        return {
            "legal_name": self.legal_name,
            "billing_email": self.billing_email,
            "billing_phone": self.billing_phone,
            "country": self.country,
            "region": self.region,
            "city": self.city,
            "postal_code": self.postal_code,
            "address_line": self.address_line,
            "tax_identifier": self.tax_identifier,
            "currency": self.currency,
            "locale": self.locale,
        }


class SubscriptionInvoice(TimeStampedModel):
    """یک فاکتورِ اشتراک — «برایِ کدام دوره چه مبلغی بدهکار است و چه مبلغی
    پرداخت شد». مبالغ هرگز منفی نیستند و ``amount_paid <= grand_total`` است
    (بدونِ پشتیبانیِ صریح از اضافه‌پرداخت). پس از باز شدن، اسنپ‌شات‌ها و
    مبالغِ مالی تغییرناپذیرند (در سرویس اعمال می‌شود؛ ADR-74)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        OPEN = "open", "باز (بدهکار)"
        PAYMENT_PENDING = "payment_pending", "در انتظارِ پرداخت"
        PAID = "paid", "پرداخت‌شده"
        PAST_DUE = "past_due", "معوق"
        VOID = "void", "باطل‌شده"
        UNCOLLECTIBLE = "uncollectible", "وصول‌ناشدنی"
        REFUNDED = "refunded", "بازپرداخت‌شده"
        PARTIALLY_REFUNDED = "partially_refunded", "بازپرداختِ جزئی"

    #: وضعیت‌هایی که فاکتور «نهایی/مالی‌بسته» محسوب می‌شود (ویرایشِ مالی ممنوع).
    FINANCIALLY_LOCKED_STATUSES = frozenset({
        Status.PAID, Status.VOID, Status.UNCOLLECTIBLE,
        Status.REFUNDED, Status.PARTIALLY_REFUNDED,
    })
    #: وضعیت‌هایی که فاکتور هنوز قابلِ پرداخت است.
    PAYABLE_STATUSES = frozenset({Status.OPEN, Status.PAYMENT_PENDING, Status.PAST_DUE})

    class Kind(models.TextChoices):
        INITIAL = "initial", "اولیه"
        RENEWAL = "renewal", "تمدید"
        PLAN_CHANGE = "plan_change", "تغییرِ پلن"
        MANUAL = "manual", "دستی"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="subscription_invoices",
    )
    subscription = models.ForeignKey(
        "subscriptions.StoreSubscription", verbose_name="اشتراک", on_delete=models.PROTECT,
        related_name="invoices",
    )
    plan_version = models.ForeignKey(
        "subscriptions.PlanVersion", verbose_name="نسخه‌ی پلن", on_delete=models.PROTECT,
        related_name="invoices",
    )
    # اسنپ‌شات‌هایِ تغییرناپذیر (مستقل از تغییرِ بعدیِ پلن/حساب).
    plan_code_snapshot = models.CharField("کدِ پلن (اسنپ‌شات)", max_length=64, blank=True, default="")
    plan_version_snapshot = models.JSONField("اسنپ‌شاتِ نسخه‌ی پلن", blank=True, default=dict)
    billing_account_snapshot = models.JSONField("اسنپ‌شاتِ حسابِ صورتحساب", blank=True, default=dict)

    number = models.CharField("شماره‌ی فاکتور", max_length=40, unique=True)
    kind = models.CharField("نوع", max_length=12, choices=Kind.choices, default=Kind.RENEWAL, db_index=True)
    status = models.CharField("وضعیت", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    currency = models.CharField("ارز", max_length=8, default="IRT")

    billing_period_start = models.DateTimeField("شروعِ دوره", null=True, blank=True)
    billing_period_end = models.DateTimeField("پایانِ دوره", null=True, blank=True)

    issued_at = models.DateTimeField("زمانِ صدور", null=True, blank=True)
    due_at = models.DateTimeField("زمانِ سررسید", null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField("زمانِ پرداخت", null=True, blank=True)
    voided_at = models.DateTimeField("زمانِ ابطال", null=True, blank=True)

    subtotal = _money(verbose_name="جمعِ جزء")
    discount_total = _money(verbose_name="جمعِ تخفیف")
    tax_total = _money(verbose_name="جمعِ مالیات")
    grand_total = _money(verbose_name="مبلغِ کل")
    amount_paid = _money(verbose_name="مبلغِ پرداخت‌شده")
    amount_due = _money(verbose_name="مبلغِ باقی‌مانده")

    provider_reference = models.CharField("ارجاعِ Provider", max_length=120, blank=True, default="")
    idempotency_key = models.CharField("کلیدِ یکتا", max_length=100, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "فاکتورِ اشتراک"
        verbose_name_plural = "فاکتورهایِ اشتراک"
        ordering = ["-created_at"]
        constraints = [
            # یک فاکتورِ تمدید به‌ازایِ هر اشتراک و هر دوره (ADR-78).
            models.UniqueConstraint(
                fields=["subscription", "billing_period_start"],
                condition=models.Q(kind="renewal"),
                name="uniq_renewal_invoice_per_period",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(subtotal__gte=0) & models.Q(discount_total__gte=0)
                    & models.Q(tax_total__gte=0) & models.Q(grand_total__gte=0)
                    & models.Q(amount_paid__gte=0) & models.Q(amount_due__gte=0)
                ),
                name="invoice_amounts_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(amount_paid__lte=models.F("grand_total")),
                name="invoice_amount_paid_within_total",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "status"], name="idx_invoice_store_status"),
            models.Index(fields=["status", "due_at"], name="idx_invoice_status_due"),
            models.Index(fields=["subscription", "status"], name="idx_inv_subscr_status"),
        ]

    def __str__(self):
        return f"Invoice {self.number} ({self.get_status_display()})"

    @property
    def is_financially_locked(self) -> bool:
        return self.status in self.FINANCIALLY_LOCKED_STATUSES

    @property
    def is_payable(self) -> bool:
        return self.status in self.PAYABLE_STATUSES

    def recompute_amount_due(self):
        """``amount_due`` را از ``grand_total - amount_paid`` بازمحاسبه می‌کند
        (هرگز منفی)."""
        self.amount_due = max(self.grand_total - self.amount_paid, ZERO)


class SubscriptionInvoiceLine(TimeStampedModel):
    """یک ردیفِ فاکتور. پس از باز شدنِ فاکتور ردیف‌ها تغییرناپذیرند (در سرویس
    اعمال می‌شود). فقط انواعِ واقعاً پیاده‌شده استفاده می‌شوند (ADR-74)."""

    class LineType(models.TextChoices):
        PLAN = "plan", "پلن"
        PRORATION_CREDIT = "proration_credit", "اعتبارِ تناسبی"
        PRORATION_CHARGE = "proration_charge", "هزینه‌ی تناسبی"
        DISCOUNT = "discount", "تخفیف"
        TAX = "tax", "مالیات"
        MANUAL_ADJUSTMENT = "manual_adjustment", "تعدیلِ دستی"

    invoice = models.ForeignKey(
        SubscriptionInvoice, verbose_name="فاکتور", on_delete=models.CASCADE, related_name="lines",
    )
    line_type = models.CharField("نوعِ ردیف", max_length=20, choices=LineType.choices, default=LineType.PLAN)
    description = models.CharField("شرح", max_length=300, blank=True, default="")

    quantity = models.DecimalField("تعداد", max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_amount = _money(verbose_name="مبلغِ واحد")
    subtotal = _money(verbose_name="جمعِ جزء")
    discount = _money(verbose_name="تخفیف")
    tax = _money(verbose_name="مالیات")
    total = _money(verbose_name="جمعِ ردیف")

    plan_code_snapshot = models.CharField("کدِ پلن (اسنپ‌شات)", max_length=64, blank=True, default="")
    plan_version_snapshot = models.JSONField("اسنپ‌شاتِ نسخه‌ی پلن", blank=True, default=dict)
    service_period_start = models.DateTimeField("شروعِ دوره‌ی خدمت", null=True, blank=True)
    service_period_end = models.DateTimeField("پایانِ دوره‌ی خدمت", null=True, blank=True)
    metadata = models.JSONField("فراداده", blank=True, default=dict)

    class Meta:
        verbose_name = "ردیفِ فاکتورِ اشتراک"
        verbose_name_plural = "ردیف‌هایِ فاکتورِ اشتراک"
        ordering = ["invoice", "id"]

    def __str__(self):
        return f"{self.get_line_type_display()} — {self.total}"


class BillingSequence(models.Model):
    """شمارنده‌یِ ماندگارِ race-safe برایِ شماره‌گذاریِ اسناد (فاکتور/Credit
    Note/…). یکتاییِ شماره از این شمارنده می‌آید، نه از شمارشِ ردیف‌هایِ جدول
    (ADR-74) — تحتِ ``select_for_update`` افزایش می‌یابد."""

    key = models.CharField("کلید", max_length=64, unique=True)
    last_value = models.PositiveBigIntegerField("آخرین مقدار", default=0)
    updated_at = models.DateTimeField("زمانِ به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "شمارنده‌ی صورتحساب"
        verbose_name_plural = "شمارنده‌هایِ صورتحساب"

    def __str__(self):
        return f"{self.key}={self.last_value}"
