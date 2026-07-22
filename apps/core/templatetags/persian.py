import jdatetime
from django import template

register = template.Library()

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def _to_fa_digits(value: str) -> str:
    return "".join(_FA_DIGITS[int(ch)] if ch.isdigit() else ch for ch in value)


@register.filter
def fa_number(value):
    """اعداد لاتین را به ارقام فارسی تبدیل می‌کند: 123 -> ۱۲۳"""
    if value is None:
        return ""
    return _to_fa_digits(str(value))


@register.filter
def toman(value):
    """قیمت را با جداکننده‌ی هزارگان فارسی و واحد «تومان» نمایش می‌دهد."""
    if value is None:
        return ""
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        return _to_fa_digits(str(value))
    formatted = f"{amount:,}".replace(",", "٬")
    return f"{_to_fa_digits(formatted)} تومان"


@register.filter
def jalali(value, fmt="%Y/%m/%d"):
    """تاریخ میلادی را به تاریخ شمسی (جلالی) با ارقام فارسی تبدیل می‌کند."""
    if not value:
        return ""
    try:
        jd = jdatetime.date.fromgregorian(date=value)
    except (TypeError, ValueError):
        return ""
    return _to_fa_digits(jd.strftime(fmt))
