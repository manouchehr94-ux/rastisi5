"""مدیریتِ یکپارچه‌ی طولِ عمرِ نشست پس از ورود («مرا به خاطر بسپار») —
تنها مسیرِ تنظیمِ انقضایِ نشست پس از ``auth_login`` در کلِ پلتفرم؛ هیچ ویویی
مستقیماً ``request.session.set_expiry`` صدا نمی‌زند (یکپارچه‌سازیِ احرازِ
هویت). امنیتِ نشستِ جنگو (چرخشِ کلید پس از ورود، CSRF، کوکیِ HttpOnly/
Secure/SameSite در Production) دست‌نخورده می‌ماند — این فقط طولِ عمر را
تعیین می‌کند، نه مکانیزمِ خودِ نشست را."""

from django.conf import settings


def apply_remember_me(request, remember: bool) -> None:
    """اگر ``remember`` نادرست باشد، نشست با بستنِ مرورگر منقضی می‌شود
    (یا ``AUTH_SESSION_DEFAULT_EXPIRY_SECONDS`` اگر غیرِصفر تنظیم شده
    باشد)؛ اگر درست باشد، از ``AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS``
    استفاده می‌شود. باید بلافاصله پس از ``django.contrib.auth.login``
    فراخوانی شود (که خودش هم کلیدِ نشست را برایِ جلوگیری از session
    fixation عوض می‌کند)."""
    if remember:
        request.session.set_expiry(settings.AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS)
        return

    default_expiry = settings.AUTH_SESSION_DEFAULT_EXPIRY_SECONDS
    if default_expiry:
        request.session.set_expiry(default_expiry)
    else:
        request.session.set_expiry(0)  # 0 == expire at browser close (Django's own semantics)
