"""سازگاریِ رو-به-عقب: منطقِ «مرا به خاطر بسپار» به ``apps.core.services.
session_service`` منتقل شده (یکپارچه‌سازیِ احرازِ هویت — هم ``apps.portal``
هم ``apps.customers`` باید بتوانند بدونِ وابستگیِ برعکس از آن استفاده
کنند). این ماژول فقط دوباره صادر می‌کند تا importهایِ موجود بدونِ تغییر
کار کنند."""

from apps.core.services.session_service import apply_remember_me

__all__ = ["apply_remember_me"]
