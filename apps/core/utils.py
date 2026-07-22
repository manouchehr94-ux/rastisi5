_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_digits(value: str) -> str:
    """ارقام فارسی/عربی را به ارقام لاتین تبدیل می‌کند تا اعتبارسنجی فرم‌ها مستقل از صفحه‌کلید کار کند."""
    if value is None:
        return ""
    return str(value).translate(_FA_TO_EN)


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
