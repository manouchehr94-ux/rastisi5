"""سرویس پنل مدیریت برای صفحه‌ی تنظیمات.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تغییر نرخ مالیات/آستانه‌ی
ارسال رایگان همان رکورد apps.core.models.ShopSettings را می‌نویسد که سرویس
pricing (مرحله‌ی ۲) و context processor سراسری سایت می‌خوانند؛ فعال/غیرفعال
کردن درگاه یا روش ارسال همان فیلد is_active واقعی را تغییر می‌دهد که
apps.orders.services.checkout_service برای فهرست گزینه‌های تسویه‌حساب استفاده
می‌کند — هیچ مقدار جدا و بی‌اثری اینجا ساخته نشده.
"""

from apps.orders.models import PaymentGateway, ShippingMethod


def active_gateways_context():
    return PaymentGateway.objects.order_by("name")


def shipping_methods_context():
    return ShippingMethod.objects.order_by("cost")


def toggle_gateway(pk: int) -> PaymentGateway:
    gateway = PaymentGateway.objects.get(pk=pk)
    gateway.is_active = not gateway.is_active
    gateway.save(update_fields=["is_active", "updated_at"])
    return gateway


def toggle_shipping_method(pk: int) -> ShippingMethod:
    method = ShippingMethod.objects.get(pk=pk)
    method.is_active = not method.is_active
    method.save(update_fields=["is_active", "updated_at"])
    return method
