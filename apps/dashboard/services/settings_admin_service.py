"""سرویس پنل مدیریت برای صفحه‌ی تنظیمات.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تغییر نرخ مالیات/آستانه‌ی
ارسال رایگان همان رکورد apps.core.models.ShopSettings را می‌نویسد که سرویس
pricing (مرحله‌ی ۲) و context processor سراسری سایت می‌خوانند؛ فعال/غیرفعال
کردن درگاه یا روش ارسال همان فیلد is_active واقعی را تغییر می‌دهد که
apps.orders.services.checkout_service برای فهرست گزینه‌های تسویه‌حساب استفاده
می‌کند — هیچ مقدار جدا و بی‌اثری اینجا ساخته نشده.
"""

from django.shortcuts import get_object_or_404

from apps.orders.models import PaymentGateway, ShippingMethod


def active_gateways_context(*, store):
    return PaymentGateway.objects.filter(store=store).order_by("name")


def shipping_methods_context(*, store):
    return ShippingMethod.objects.filter(store=store).order_by("cost")


def toggle_gateway(pk: int, *, store) -> PaymentGateway:
    """۴۰۴ استاندارد (نه استثنای بدون‌مدیریت) برای درگاه متعلق به Store دیگر."""
    gateway = get_object_or_404(PaymentGateway, pk=pk, store=store)
    gateway.is_active = not gateway.is_active
    gateway.save(update_fields=["is_active", "updated_at"])
    return gateway


def toggle_shipping_method(pk: int, *, store) -> ShippingMethod:
    """۴۰۴ استاندارد (نه استثنای بدون‌مدیریت) برای روش ارسال متعلق به Store دیگر."""
    method = get_object_or_404(ShippingMethod, pk=pk, store=store)
    method.is_active = not method.is_active
    method.save(update_fields=["is_active", "updated_at"])
    return method
