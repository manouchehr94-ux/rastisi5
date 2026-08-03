"""تجمیعِ همه‌ی قالب‌های صنفِ seed — نگاه کنید به بخش ۲۸ پرامپت فاز ۱F.

هر فایل این پکیج فقط یک صنف یا گروه منطقی از صنایع مرتبط را نگه می‌دارد
(به‌جای یک دیکشنری غول‌پیکر واحد)؛ این ماژول فقط آن‌ها را در یک فهرست
واحد و قطعی برای دستور ``seed_industry_templates`` کنار هم می‌گذارد.
افزودن صنف جدید = افزودن یک فایل جدید (یا یک ورودی به فایل گروهیِ مرتبط)
+ اضافه‌کردن آن به ``_TEMPLATE_MODULES`` زیر."""

from apps.catalog.industry_templates import (
    approved_catalog,
    auto_hardware,
    beauty_health,
    family,
    fashion_extra,
    home_living,
    lifestyle,
)
from apps.catalog.seed_data.industry_templates import INDUSTRY_TEMPLATES as FOUNDING_TEMPLATES

_TEMPLATE_MODULES = [
    fashion_extra,
    family,
    beauty_health,
    auto_hardware,
    home_living,
    lifestyle,
]

#: صنف‌هایِ منسوخ‌شده‌یِ فاز پیشین که یک‌به‌یک با یکی از ۱۰۰ صنفِ تأییدشده
#: مطابقت نداشتند (نگاه کنید به بخشِ ۱ پرامپت این فاز) — دیگر برایِ نصبِ
#: جدید پیشنهاد نمی‌شوند، اما رکوردشان (و هر نصبِ موجود) حذف نمی‌شود.
DEPRECATED_LEGACY_SLUGS = [
    "clothing-fashion",
    "food-grocery",
    "haircare",
    "toys-children",
    "baby-products",
    "pet-supplies",
]

ALL_INDUSTRY_TEMPLATES = [
    *FOUNDING_TEMPLATES,
    *[entry for module in _TEMPLATE_MODULES for entry in module.INDUSTRY_TEMPLATES],
    *approved_catalog.APPROVED_CATALOG_TEMPLATES,
]
