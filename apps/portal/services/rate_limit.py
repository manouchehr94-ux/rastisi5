"""محدودیت نرخ ساده‌ی مبتنی‌بر cache برای فرم‌های عمومیِ سایت/پرتال (ثبت‌نام،
ورود، فرم تماس) — بر خلافِ ``apps.sms.services.otp_service`` (که برای دوامِ
تاریخی از یک مدلِ دیتابیسی استفاده می‌کند)، این‌جا فقط یک پنجره‌ی لغزانِ
کوتاه‌مدت لازم است، پس از ``django.core.cache`` استفاده می‌شود — بدونِ صف/تسکِ
پس‌زمینه، هماهنگ با بقیه‌ی پروژه.
"""

from django.core.cache import cache

_CACHE_PREFIX = "portal:ratelimit"


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
