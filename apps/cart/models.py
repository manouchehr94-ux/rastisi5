from django.db import models

from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.CASCADE,
        null=True, blank=True, related_name="carts",
    )
    session_key = models.CharField("کلید نشست (مهمان)", max_length=40, blank=True)
    # کلید idempotency تسویه‌حساب — سرور‌محور تولید می‌شود، هیچ‌وقت از ورودی
    # کاربر خوانده نمی‌شود. نگاه کنید به
    # apps.orders.services.checkout_service.get_or_create_checkout_token
    # و apps.orders.services.order_service.create_order_from_cart.
    checkout_token = models.CharField("کلید تسویه‌حساب", max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"
        ordering = ["-created_at"]

    def __str__(self):
        return f"سبد #{self.pk} — {self.customer or 'مهمان'}"


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, verbose_name="سبد خرید", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", verbose_name="کالا", on_delete=models.CASCADE, related_name="cart_items"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", verbose_name="تنوع", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cart_items",
    )
    quantity = models.PositiveIntegerField("تعداد", default=1)
    unit_price = models.DecimalField("قیمت واحد (اسنپ‌شات)", max_digits=12, decimal_places=0)

    # کادوپیچی (toranj_gifting: optional_addon_checkbox_updates_total) — یک
    # افزونه‌ی سطحِ قلم، نه سطحِ سبد: هر قلم می‌تواند مستقل از بقیه کادوپیچی
    # شود. ``gift_wrap_unit_price`` همیشه یک اسنپ‌شاتِ سمتِ سرور از
    # ``ShopSettings.gift_wrap_price`` در لحظه‌ی انتخاب است (دقیقاً همان
    # الگویِ ``unit_price`` خودِ این مدل) — هرگز از ورودیِ کلاینت خوانده
    # نمی‌شود؛ نگاه کنید به ``apps.cart.services.gift_wrap_service``.
    gift_wrap_selected = models.BooleanField("کادوپیچی انتخاب شده", default=False)
    gift_wrap_unit_price = models.DecimalField(
        "هزینه‌ی کادوپیچی (اسنپ‌شات)", max_digits=12, decimal_places=0, default=0,
    )

    class Meta:
        verbose_name = "قلم سبد خرید"
        verbose_name_plural = "اقلام سبد خرید"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

    @property
    def gift_wrap_line_total(self):
        """جمعِ هزینه‌ی کادوپیچیِ این قلم = تعداد × قیمتِ واحدِ کادوپیچی —
        وقتی انتخاب نشده باشد صفر است، نه ``gift_wrap_unit_price`` تنها
        (که ممکن است از انتخاب‌های قبلی مقدار داشته باشد)."""
        if not self.gift_wrap_selected:
            return 0
        return self.gift_wrap_unit_price * self.quantity


class Coupon(TimeStampedModel):
    """کد تخفیف — Store-owned (ADR-32): هر کد فقط در همان فروشگاهی که
    ساخته شده معتبر است؛ دو فروشگاه می‌توانند مستقل از هم کد یکسان
    داشته باشند. پیش از ADR-32، این مدل هیچ فیلد ``store`` نداشت و یک
    کد در سراسر پلتفرم سراسری/به‌اشتراک‌گذاشته‌شده بود — یک نشتِ واقعیِ
    ایزولاسیونِ چندمستأجری که در گزارش تکمیل پنل مدیریت مستند شده بود."""

    class Type(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"
        FREE_SHIP = "free_ship", "ارسال رایگان"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="coupons",
    )
    code = models.CharField("کد تخفیف", max_length=30)
    type = models.CharField("نوع", max_length=10, choices=Type.choices)
    value = models.DecimalField("مقدار", max_digits=12, decimal_places=0, default=0)
    label = models.CharField("برچسب نمایشی", max_length=150, blank=True)
    min_order = models.DecimalField("حداقل مبلغ سفارش", max_digits=12, decimal_places=0, default=0)
    usage_limit = models.PositiveIntegerField("سقف استفاده", null=True, blank=True)
    used_count = models.PositiveIntegerField("تعداد استفاده‌شده", default=0)
    expires_at = models.DateTimeField("تاریخ انقضا", null=True, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_coupon_code_per_store"),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)
