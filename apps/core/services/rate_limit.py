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


def client_ip_or_unknown(request) -> str:
    """``REMOTE_ADDR`` را برمی‌گرداند — اما با یک تفاوتِ عمدی نسبت به
    ``request.META.get("REMOTE_ADDR", "unknown")`` ساده: اگر ``REMOTE_ADDR``
    *وجود دارد ولی رشته‌ی خالی است* (نه غایب) هم به‌جایِ برگرداندنِ همان رشته‌ی
    خالی، صریحاً «unknown» می‌دهد.

    این تفاوت مهم است چون Gunicorn پشتِ یک Unix socket (توپولوژیِ واقعیِ
    RastiSi: Nginx -> Unix socket -> Gunicorn) طبقِ رفتارِ مستندِ خودش
    ``REMOTE_ADDR`` را برایِ هر درخواست رشته‌ی خالی می‌گذارد، نه غایب — پس
    الگویِ ``.get(key, default)`` هرگز به آن default نمی‌رسد و همه‌ی
    کاربرانِ واقعی زیرِ یک کلیدِ یکسان (رشته‌ی خالی) جمع می‌شدند.

    این تابع عمداً به هیچ هدرِ ارسالی از سمتِ کلاینت (``X-Forwarded-For``،
    ``X-Real-IP``) اعتماد نمی‌کند — چون این کدبیس هنوز هیچ مکانیزمِ trusted-proxy
    ندارد و اعتماد کورکورانه به چنین هدری یعنی مهاجم می‌تواند IPِ دلخواه جعل
    کند. نتیجه‌ی این تابع («unknown» یا REMOTE_ADDRِ واقعی) هنوز هم می‌تواند
    بینِ کاربرانِ واقعیِ پشتِ یک پراکسی مشترک باشد — محافظتِ per-identifier
    (نگاه کنید به فراخوان‌های ``enforce_rate_limit`` که علاوه بر IP، با
    شناسه‌ی حساب هم قفل می‌شوند) خطِ دفاعِ واقعی در برابرِ brute-force است، نه
    این تابع؛ این تابع فقط از تبدیلِ خاموشِ «IP خالی» به یک سطلِ مشترکِ
    غیرِعمدی جلوگیری می‌کند."""
    return request.META.get("REMOTE_ADDR") or "unknown"
