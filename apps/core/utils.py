_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_digits(value: str) -> str:
    """ارقام فارسی/عربی را به ارقام لاتین تبدیل می‌کند تا اعتبارسنجی فرم‌ها مستقل از صفحه‌کلید کار کند."""
    if value is None:
        return ""
    return str(value).translate(_FA_TO_EN)
