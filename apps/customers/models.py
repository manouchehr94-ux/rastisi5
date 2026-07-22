from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Customer(TimeStampedModel):
    """پروفایل مشتری — گسترش کاربر جنگو."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="customer_profile"
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField("موبایل", max_length=15, unique=True)
    email = models.EmailField("ایمیل", blank=True)
    city = models.CharField("شهر", max_length=80, blank=True)
    is_vip = models.BooleanField("مشتری ویژه (VIP)", default=False)
    orders_count = models.PositiveIntegerField("تعداد سفارش‌ها", default=0)
    total_spent = models.DecimalField("مجموع خرید (تومان)", max_digits=14, decimal_places=0, default=0)

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name

    @property
    def joined_at(self):
        return self.created_at


class Address(TimeStampedModel):
    customer = models.ForeignKey(Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="addresses")
    receiver_name = models.CharField("نام گیرنده", max_length=150)
    phone = models.CharField("موبایل گیرنده", max_length=15)
    province = models.CharField("استان", max_length=80)
    city = models.CharField("شهر", max_length=80)
    postal_code = models.CharField("کد پستی", max_length=10, blank=True)
    full_address = models.TextField("آدرس پستی کامل")
    is_default = models.BooleanField("آدرس پیش‌فرض", default=False)

    class Meta:
        verbose_name = "آدرس"
        verbose_name_plural = "آدرس‌ها"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.receiver_name} — {self.city}"


class Wishlist(TimeStampedModel):
    customer = models.ForeignKey(
        Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(
        "catalog.Product", verbose_name="کالا", on_delete=models.CASCADE, related_name="wishlisted_by"
    )

    class Meta:
        verbose_name = "علاقه‌مندی"
        verbose_name_plural = "علاقه‌مندی‌ها"
        unique_together = ("customer", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} ♥ {self.product}"
