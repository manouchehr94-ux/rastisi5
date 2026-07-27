from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ShippingMethod(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="shipping_methods",
    )
    name = models.CharField("نام روش ارسال", max_length=100)
    slug = models.SlugField("اسلاگ", max_length=120, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    cost = models.DecimalField("هزینه (تومان)", max_digits=12, decimal_places=0, default=0)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    free_over = models.DecimalField(
        "آستانه‌ی ارسال رایگان (تومان)", max_digits=12, decimal_places=0, default=500_000
    )

    class Meta:
        verbose_name = "روش ارسال"
        verbose_name_plural = "روش‌های ارسال"
        ordering = ["cost"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_shippingmethod_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class PaymentGateway(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="payment_gateways",
    )
    name = models.CharField("نام درگاه", max_length=100)
    slug = models.SlugField("اسلاگ", max_length=120, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    fee_percent = models.DecimalField("کارمزد (٪)", max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "درگاه پرداخت"
        verbose_name_plural = "درگاه‌های پرداخت"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_paymentgateway_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSING = "processing", "در حال پردازش"
        SHIPPED = "shipped", "ارسال شده"
        DELIVERED = "delivered", "تحویل داده شده"
        CANCELED = "canceled", "لغو شده"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        FAILED = "failed", "ناموفق"
        REFUNDED = "refunded", "مسترد شده"

    code = models.CharField("شناسه‌ی سفارش", max_length=20, unique=True)
    # مالکیت Store مستقیم و صریح — نه فقط از طریق vendor.store. هر Order باید
    # دقیقاً یک Store داشته باشد که با vendor.store یکی است (این عدم‌تطابق در
    # لایه‌ی سرویس/فرم بررسی می‌شود؛ CheckConstraint نمی‌تواند بین دو جدول
    # مقایسه کند — نگاه کنید به clean() پایین‌تر و
    # apps.orders.services.order_service.create_order_from_cart).
    # on_delete=PROTECT (نه CASCADE مثل کاتالوگ) چون سفارش یک رکورد مالی/
    # تاریخی است؛ حذف یک Store هرگز نباید سفارش‌های آن را هم بی‌صدا حذف کند.
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="orders"
    )
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.PROTECT, related_name="orders"
    )
    vendor = models.ForeignKey(
        "catalog.Vendor", verbose_name="فروشنده", on_delete=models.PROTECT, related_name="orders"
    )

    # کلید یکتای درخواست تسویه‌حساب — برای idempotency ثبت سفارش (بخش ۸ مرحله‌ی
    # ۳). خالی یعنی «بدون کلید» (مثلاً ساخت مستقیم از تست/مهاجرت)؛ یکتایی فقط
    # وقتی مقدار دارد اجرا می‌شود (uniq_order_idempotency_key_when_set پایین‌تر) —
    # دقیقاً همان الگوی ProductVariant.sku (uniq_variant_sku_when_set).
    idempotency_key = models.CharField(
        "کلید یکتای درخواست تسویه‌حساب", max_length=64, blank=True, default=""
    )

    address = models.JSONField("آدرس (اسنپ‌شات)", default=dict)
    shipping_method = models.ForeignKey(
        ShippingMethod, verbose_name="روش ارسال", on_delete=models.PROTECT, related_name="orders"
    )
    payment_gateway = models.ForeignKey(
        PaymentGateway, verbose_name="درگاه پرداخت", on_delete=models.PROTECT, related_name="orders"
    )
    coupon = models.ForeignKey(
        "cart.Coupon", verbose_name="کد تخفیف", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="orders",
    )

    status = models.CharField("وضعیت سفارش", max_length=12, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(
        "وضعیت پرداخت", max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    items_total = models.DecimalField("جمع کالاها", max_digits=14, decimal_places=0, default=0)
    product_discount = models.DecimalField("تخفیف کالاها", max_digits=14, decimal_places=0, default=0)
    coupon_discount = models.DecimalField("تخفیف کد تخفیف", max_digits=14, decimal_places=0, default=0)
    shipping_cost = models.DecimalField("هزینه‌ی ارسال", max_digits=12, decimal_places=0, default=0)
    tax = models.DecimalField("مالیات", max_digits=12, decimal_places=0, default=0)
    grand_total = models.DecimalField("مبلغ نهایی", max_digits=14, decimal_places=0, default=0)

    note = models.TextField("توضیحات سفارش", blank=True)
    tracking_code = models.CharField("کد رهگیری مرسوله", max_length=60, blank=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_order_idempotency_key_when_set",
            ),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        """سفارش باید دقیقاً هم‌راستا با Store فروشنده‌اش باشد.

        این یک بررسی سطح دیتابیس نیست (CheckConstraint نمی‌تواند بین دو جدول
        Order و Vendor مقایسه کند) — دقیقاً همان محدودیت مستندشده در
        ``apps.catalog.models.Product.clean()``. اجرای واقعی و قطعی این
        عدم‌تطابق در لایه‌ی سرویس است
        (``apps.orders.services.order_service.create_order_from_cart``) که
        تنها مسیر تولید Order در Production است؛ این متد لایه‌ی دومِ دفاعی
        برای فرم/Admin/بررسی صریح است."""
        from django.core.exceptions import ValidationError

        if self.vendor_id and self.store_id and self.vendor.store_id != self.store_id:
            raise ValidationError({"vendor": "این فروشنده متعلق به فروشگاه دیگری است."})


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", verbose_name="کالا", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", verbose_name="تنوع", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_items",
    )
    product_name = models.CharField("نام کالا (اسنپ‌شات)", max_length=220)
    # اسنپ‌شات‌های اضافی (بخش ۱۰) — تا حذف/تغییر Product یا ProductVariant
    # اصلی هرگز نمایش تاریخی این ردیف را عوض نکند. خالی یعنی «بدون تنوع» یا
    # «SKU نداشت» (هر دو معتبر و مورد انتظارند، نه یک حالت خطا).
    sku = models.CharField("کد کالا (SKU) (اسنپ‌شات)", max_length=64, blank=True, default="")
    variant_label = models.CharField("تنوع انتخاب‌شده (اسنپ‌شات)", max_length=150, blank=True, default="")
    quantity = models.PositiveIntegerField("تعداد", default=1)
    unit_price = models.DecimalField("قیمت واحد", max_digits=12, decimal_places=0)
    line_total = models.DecimalField("جمع ردیف", max_digits=12, decimal_places=0)

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class OrderStatusHistory(TimeStampedModel):
    order = models.ForeignKey(
        Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        "از وضعیت", max_length=12, choices=Order.Status.choices, blank=True
    )
    to_status = models.CharField("به وضعیت", max_length=12, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="تغییردهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_status_changes",
    )
    note = models.TextField("توضیحات", blank=True)

    class Meta:
        verbose_name = "تاریخچه‌ی وضعیت سفارش"
        verbose_name_plural = "تاریخچه‌ی وضعیت سفارش‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.code}: {self.from_status or '—'} → {self.to_status}"


class Transaction(TimeStampedModel):
    class Status(models.TextChoices):
        OK = "ok", "موفق"
        PENDING = "pending", "در انتظار"
        FAIL = "fail", "ناموفق"
        REFUND = "refund", "مسترد"

    code = models.CharField("شناسه‌ی تراکنش", max_length=20, unique=True)
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="transactions")
    gateway = models.ForeignKey(
        PaymentGateway, verbose_name="درگاه", on_delete=models.PROTECT, related_name="transactions"
    )
    amount = models.DecimalField("مبلغ", max_digits=14, decimal_places=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    ref_id = models.CharField("شماره ارجاع بانکی", max_length=60, blank=True)

    class Meta:
        verbose_name = "تراکنش"
        verbose_name_plural = "تراکنش‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code



# ===========================================================================
# Payment Domain Foundation — PR1
# ===========================================================================


class PaymentGatewayConfig(TimeStampedModel):
    """Per-store configuration for a payment gateway.

    This is the operational configuration — merchant credentials, activation
    state, sandbox mode — while the existing ``PaymentGateway`` model remains
    the order-level record (what the customer chose at checkout time).

    Each store can have at most ONE configuration per gateway code
    (UniqueConstraint below). Credentials are stored encrypted via
    apps.orders.encryption.

    Relationship to PaymentGateway:
        PaymentGatewayConfig is the source of truth for "which gateways are
        available and configured for this store." When a customer selects a
        payment method at checkout, the Order references the legacy
        PaymentGateway for backwards compatibility. PaymentAttempt references
        this config for the actual payment lifecycle.
    """

    class GatewayCode(models.TextChoices):
        ZIBAL = "zibal", "زیبال"
        COD = "cod", "پرداخت در محل"

    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="gateway_configs",
    )
    gateway_code = models.CharField(
        "کد درگاه",
        max_length=30,
        choices=GatewayCode.choices,
    )
    display_title = models.CharField(
        "عنوان نمایشی",
        max_length=150,
        blank=True,
        help_text="عنوان نمایش‌داده‌شده در صفحه‌ی تسویه‌حساب (اختیاری — اگر خالی باشد از نام پیش‌فرض درگاه استفاده می‌شود)",
    )
    is_active = models.BooleanField("فعال", default=False)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_sandbox = models.BooleanField(
        "حالت آزمایشی (Sandbox)",
        default=False,
        help_text="فقط برای درگاه‌هایی که حالت آزمایشی پشتیبانی می‌کنند",
    )

    # Encrypted credentials stored as a single JSON-like text field.
    # Format: Fernet-encrypted JSON string of credential key/value pairs.
    # Empty string means "no credentials set."
    encrypted_credentials = models.TextField(
        "اعتبارنامه‌ی رمزنگاری‌شده",
        blank=True,
        default="",
        help_text="مقدار رمزنگاری‌شده — هرگز مستقیم خوانده نمی‌شود",
    )

    class Meta:
        verbose_name = "پیکربندی درگاه پرداخت"
        verbose_name_plural = "پیکربندی‌های درگاه پرداخت"
        ordering = ["display_order", "gateway_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "gateway_code"],
                name="uniq_gateway_config_per_store",
            ),
        ]

    def __str__(self):
        return f"{self.get_gateway_code_display()} — {self.store.name}"

    @property
    def effective_title(self) -> str:
        """Display title for checkout UI — custom title or gateway default."""
        if self.display_title:
            return self.display_title
        return self.get_gateway_code_display()

    def get_credentials(self) -> dict:
        """Decrypt and return credentials as a dict. Empty dict if none stored."""
        import json
        from .encryption import decrypt_credential

        if not self.encrypted_credentials:
            return {}
        plaintext = decrypt_credential(self.encrypted_credentials)
        if not plaintext:
            return {}
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_credentials(self, credentials: dict) -> None:
        """Encrypt and store a credentials dict."""
        import json
        from .encryption import encrypt_credential

        if not credentials:
            self.encrypted_credentials = ""
            return
        # Remove empty values
        clean = {k: v for k, v in credentials.items() if v}
        if not clean:
            self.encrypted_credentials = ""
            return
        plaintext = json.dumps(clean, ensure_ascii=False)
        self.encrypted_credentials = encrypt_credential(plaintext)

    @property
    def is_configured(self) -> bool:
        """Whether this gateway has all required credentials filled."""
        from .gateways import get_adapter

        try:
            adapter = get_adapter(self.gateway_code)
        except KeyError:
            return False
        if not adapter.required_credentials:
            return True  # COD needs no credentials
        creds = self.get_credentials()
        return all(creds.get(key) for key in adapter.required_credentials)

    @property
    def can_activate(self) -> bool:
        """Whether this config is eligible for activation (credentials complete)."""
        from .gateways import get_adapter

        try:
            adapter = get_adapter(self.gateway_code)
        except KeyError:
            return False
        errors = adapter.validate_credentials(self.get_credentials())
        return len(errors) == 0

    @property
    def is_online(self) -> bool:
        """Whether this is an online payment gateway."""
        from .gateways import get_adapter

        try:
            return get_adapter(self.gateway_code).is_online
        except KeyError:
            return False


class PaymentAttempt(TimeStampedModel):
    """A single payment attempt for an order.

    An Order may have multiple PaymentAttempts (failed attempt → retry).
    Each attempt is an independent, immutable record of what was sent to
    the gateway and what came back.

    State machine:
        CREATED → REQUESTING → REDIRECT_READY → PENDING → SUCCEEDED
                                                        → FAILED
                                                        → CANCELED
                                                        → EXPIRED

    Once in SUCCEEDED, FAILED, CANCELED, or EXPIRED, the attempt is final.
    """

    class Status(models.TextChoices):
        CREATED = "created", "ایجادشده"
        REQUESTING = "requesting", "در حال درخواست"
        REDIRECT_READY = "redirect_ready", "آماده‌ی هدایت"
        PENDING = "pending", "در انتظار"
        SUCCEEDED = "succeeded", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELED = "canceled", "لغوشده"
        EXPIRED = "expired", "منقضی‌شده"

    FINAL_STATUSES = frozenset({
        Status.SUCCEEDED,
        Status.FAILED,
        Status.CANCELED,
        Status.EXPIRED,
    })

    # --- Relationships ---
    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    gateway_config = models.ForeignKey(
        PaymentGatewayConfig,
        verbose_name="پیکربندی درگاه",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )

    # --- Immutable snapshots ---
    public_id = models.CharField(
        "شناسه‌ی عمومی",
        max_length=32,
        unique=True,
        editable=False,
        help_text="شناسه‌ی غیرترتیبی برای URLها و لاگ‌ها",
    )
    amount = models.DecimalField(
        "مبلغ (اسنپ‌شات)",
        max_digits=14,
        decimal_places=0,
        help_text="مبلغ دقیقاً در لحظه‌ی ایجاد تلاش — تغییرناپذیر",
    )
    currency = models.CharField(
        "واحد پول (اسنپ‌شات)",
        max_length=10,
        default="TOMAN",
        help_text="واحد پولی دقیقاً در لحظه‌ی ایجاد",
    )

    # --- Status ---
    status = models.CharField(
        "وضعیت",
        max_length=15,
        choices=Status.choices,
        default=Status.CREATED,
    )

    # --- Gateway interaction ---
    gateway_track_id = models.CharField(
        "شناسه‌ی پیگیری درگاه",
        max_length=100,
        blank=True,
        default="",
        help_text="trackId یا معادل آن از سمت درگاه",
    )
    gateway_ref_id = models.CharField(
        "شماره ارجاع بانکی",
        max_length=100,
        blank=True,
        default="",
    )
    idempotency_key = models.CharField(
        "کلید یکتایی",
        max_length=64,
        blank=True,
        default="",
        help_text="برای جلوگیری از ایجاد تلاش‌های تکراری",
    )

    # --- Failure info (safe to log/display) ---
    failure_code = models.CharField(
        "کد خطا",
        max_length=50,
        blank=True,
        default="",
    )
    failure_message = models.CharField(
        "پیام خطا (امن)",
        max_length=300,
        blank=True,
        default="",
        help_text="پیام امن بدون اطلاعات حساس — قابل نمایش به مدیر",
    )

    # --- Timestamps ---
    initiated_at = models.DateTimeField(
        "زمان ارسال درخواست",
        null=True,
        blank=True,
    )
    verified_at = models.DateTimeField(
        "زمان تأیید",
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField(
        "زمان انقضا",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "تلاش پرداخت"
        verbose_name_plural = "تلاش‌های پرداخت"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_payment_attempt_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["gateway_track_id"],
                condition=~models.Q(gateway_track_id=""),
                name="uniq_payment_attempt_track_id",
            ),
        ]
        indexes = [
            models.Index(fields=["order", "-created_at"], name="idx_attempt_order_date"),
            models.Index(fields=["store", "status"], name="idx_attempt_store_status"),
        ]

    def __str__(self):
        return f"PaymentAttempt {self.public_id} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.public_id:
            import secrets
            self.public_id = secrets.token_hex(16)
        super().save(*args, **kwargs)

    @property
    def is_final(self) -> bool:
        """Whether this attempt has reached a terminal state."""
        return self.status in self.FINAL_STATUSES

    @property
    def is_successful(self) -> bool:
        return self.status == self.Status.SUCCEEDED
