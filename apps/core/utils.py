import re

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
# ارقام فارسی (Extended Arabic-Indic، ۰۱۲۳۴۵۶۷۸۹) و ارقام عربی (Arabic-Indic، ٠١٢٣٤٥٦٧٨٩)
# هر دو باید به لاتین تبدیل شوند؛ صفحه‌کلید کاربر ممکن است هرکدام را تولید کند.
_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹" + "٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_AR_TO_FA_LETTERS = str.maketrans({"ي": "ی", "ك": "ک"})
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_digits(value: str) -> str:
    """ارقام فارسی/عربی را به ارقام لاتین تبدیل می‌کند تا اعتبارسنجی فرم‌ها مستقل از صفحه‌کلید کار کند."""
    if value is None:
        return ""
    return str(value).translate(_FA_TO_EN)


def normalize_text(value: str) -> str:
    """ارقام فارسی/عربی را لاتین، حروف عربی رایج (ي/ك) را فارسی، و فاصله‌های اضافه را یکدست می‌کند.

    برای مقایسه‌ی متن‌های ورودی مدیر فروشگاه (نام/مقدار تنوع) استفاده می‌شود تا
    تفاوت صرفاً در صفحه‌کلید یا فاصله باعث ثبت رکورد تکراری نشود.
    """
    if value is None:
        return ""
    text = normalize_digits(value).translate(_AR_TO_FA_LETTERS)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalization_key(value: str) -> str:
    """کلید نرمال‌شده برای مقایسه‌ی بدون‌حساسیت به بزرگی/کوچکی حروف (مقادیر لاتین) و فاصله."""
    return normalize_text(value).lower()


def to_fa_digits(value) -> str:
    """ارقام لاتین را به ارقام فارسی تبدیل می‌کند: 123 -> ۱۲۳"""
    if value is None:
        return ""
    return "".join(_FA_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(value))


def format_toman(value, with_unit: bool = True) -> str:
    """مبلغ را با جداکننده‌ی هزارگان و ارقام فارسی برمی‌گرداند؛ با پرچم with_unit واحد «تومان» هم اضافه می‌شود."""
    if value is None:
        return ""
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        return to_fa_digits(value)
    formatted = to_fa_digits(f"{amount:,}".replace(",", "٬"))
    return f"{formatted} تومان" if with_unit else formatted
