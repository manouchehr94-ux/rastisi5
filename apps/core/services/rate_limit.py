"""محدودیت نرخ ساده‌ی مبتنی‌بر cache — برای فرم‌های عمومیِ سایت (ثبت‌نام،
ورود، درخواستِ OTP، فرم تماس). یک پنجره‌ی لغزانِ کوتاه‌مدت کافی است، پس از
``django.core.cache`` استفاده می‌شود — بدونِ صف/تسکِ پس‌زمینه.

در ``apps.core`` است (نه ``apps.portal``) چون مصرف‌کننده‌هایش هم لایه‌ی
پلتفرم‌اند (``apps.portal.services.owner_otp_service``) هم لایه‌ی
مستأجر/فروشگاه (``apps.sms.services.otp_service``) — و ``apps.sms`` نباید
به‌عقب به ``apps.portal`` وابسته شود."""

from django.core.cache import cache

_CACHE_PREFIX = "ratelimit"


class RateLimitExceeded(Exception):
    """این کنش برای این شناسه بیش از حدِ مجاز در بازه‌ی اخیر تکرار شده است."""


def enforce_rate_limit(action: str, identifier: str, *, max_attempts: int, window_seconds: int) -> None:
    """اگر تعداد فراخوانی‌های اخیر ``action``+``identifier`` از ``max_attempts``
    در ``window_seconds`` ثانیه‌ی اخیر بیشتر باشد، ``RateLimitExceeded`` می‌دهد؛
    وگرنه شمارنده را یکی افزایش می‌دهد (اولین فراخوان، پنجره را با TTL می‌سازد)."""
    key = f"{_CACHE_PREFIX}:{action}:{identifier}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    if count > max_attempts:
        raise RateLimitExceeded(f"تعداد تلاش برای «{action}» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید")
