from django.db import models

from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.CASCADE,
        null=True, blank=True, related_name="carts",
    )
    session_key = models.CharField("کلید نشست (مهمان)", max_length=40, blank=True)

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

    class Meta:
        verbose_name = "قلم سبد خرید"
        verbose_name_plural = "اقلام سبد خرید"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"


class Coupon(TimeStampedModel):
    class Type(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"
        FREE_SHIP = "free_ship", "ارسال رایگان"

    code = models.CharField("کد تخفیف", max_length=30, unique=True)
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

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)
