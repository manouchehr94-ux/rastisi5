from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ShippingMethod(TimeStampedModel):
    name = models.CharField("نام روش ارسال", max_length=100)
    slug = models.SlugField("اسلاگ", max_length=120, unique=True, allow_unicode=True)
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

    def __str__(self):
        return self.name


class PaymentGateway(TimeStampedModel):
    name = models.CharField("نام درگاه", max_length=100)
    slug = models.SlugField("اسلاگ", max_length=120, unique=True, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    fee_percent = models.DecimalField("کارمزد (٪)", max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "درگاه پرداخت"
        verbose_name_plural = "درگاه‌های پرداخت"
        ordering = ["name"]

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
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.PROTECT, related_name="orders"
    )
    vendor = models.ForeignKey(
        "catalog.Vendor", verbose_name="فروشنده", on_delete=models.PROTECT, related_name="orders"
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

    def __str__(self):
        return self.code


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
