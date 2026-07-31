"""نرمال‌سازیِ متعارفِ شماره موبایلِ ایرانی — تنها منبعِ حقیقتِ این منطق در
کل کدبیس (پیش از این، ``apps.portal``/``apps.customers``/
``apps.stores.services.membership_service``/``apps.orders``/
``apps.dashboard`` هرکدام نسخه‌ی جداگانه‌ای داشتند؛ این‌جا آن تکرار برایِ
مسیرهایِ هویت/ورود جمع شده — نگاه کنید به تصمیمِ یکپارچه‌سازیِ احرازِ هویت).

فرمتِ نهایی همیشه ``09xxxxxxxxx`` (۱۱ رقم، با ۰۹ شروع) است.
"""

import re

from django.core.exceptions import ValidationError

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"
_DIGIT_MAP = str.maketrans(_FA_DIGITS + _AR_DIGITS, _ASCII_DIGITS + _ASCII_DIGITS)

_CANONICAL_RE = re.compile(r"^09\d{9}$")


class InvalidPhoneError(ValidationError):
    """شماره موبایل واردشده معتبر نیست."""


def normalize_iranian_phone(raw_value: str) -> str:
    """۰۹xxxxxxxxx / +۹۸۹xxxxxxxxx / ۰۰۹۸۹xxxxxxxxx / ۹xxxxxxxxx (بدونِ صفر)
    را به فرمتِ متعارفِ ``09xxxxxxxxx`` تبدیل می‌کند. ارقامِ فارسی/عربی هم
    پذیرفته می‌شوند. هر ورودیِ نامعتبر ``InvalidPhoneError`` می‌دهد — هرگز
    حدس نمی‌زند."""
    if raw_value is None:
        raise InvalidPhoneError("شماره موبایل الزامی است.", code="phone_required")

    value = str(raw_value).translate(_DIGIT_MAP)
    value = re.sub(r"[\s\-()]", "", value)

    if value.startswith("+98"):
        value = "0" + value[3:]
    elif value.startswith("0098"):
        value = "0" + value[4:]
    elif value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]
    elif value.startswith("9") and len(value) == 10:
        value = "0" + value

    if not _CANONICAL_RE.match(value):
        raise InvalidPhoneError(
            "شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود (مثل ۰۹۱۲۱۲۳۴۵۶۷).",
            code="phone_invalid",
        )
    return value
