"""سازگاریِ رو-به-عقب: منطقِ نرمال‌سازیِ شماره موبایل به ``apps.core.phone``
منتقل شده (یکپارچه‌سازیِ احرازِ هویت — تنها منبعِ حقیقتِ این منطق در کل
کدبیس، نه یک نسخه‌ی جداگانه به‌ازایِ هر اپ). این ماژول فقط دوباره صادر
می‌کند تا importهایِ موجود (``from .phone import normalize_iranian_phone``)
بدونِ تغییر کار کنند."""

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone

__all__ = ["InvalidPhoneError", "normalize_iranian_phone"]
