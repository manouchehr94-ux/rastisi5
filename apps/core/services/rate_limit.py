"""محدودیت نرخ ساده‌ی مبتنی‌بر cache — برای فرم‌های عمومیِ سایت (ثبت‌نام،
ورود، درخواستِ OTP، فرم تماس). یک پنجره‌ی لغزانِ کوتاه‌مدت کافی است، پس از
یک alias اختصاصیِ ``django.core.cache`` (``rate_limit``، نه ``default``)
استفاده می‌شود — بدونِ صف/تسکِ پس‌زمینه.

در ``apps.core`` است (نه ``apps.portal``) چون مصرف‌کننده‌هایش هم لایه‌ی
پلتفرم‌اند (``apps.portal.services.owner_otp_service``) هم لایه‌ی
مستأجر/فروشگاه (``apps.sms.services.otp_service``) — و ``apps.sms`` نباید
به‌عقب به ``apps.portal`` وابسته شود."""

import ipaddress

from django.conf import settings
from django.core.cache import caches

_CACHE_PREFIX = "ratelimit"
_RATE_LIMIT_CACHE_ALIAS = "rate_limit"


class RateLimitExceeded(Exception):
    """این کنش برای این شناسه بیش از حدِ مجاز در بازه‌ی اخیر تکرار شده است."""


def enforce_rate_limit(action: str, identifier: str, *, max_attempts: int, window_seconds: int) -> None:
    """اگر تعداد فراخوانی‌های اخیر ``action``+``identifier`` از ``max_attempts``
    در ``window_seconds`` ثانیه‌ی اخیر بیشتر باشد، ``RateLimitExceeded`` می‌دهد؛
    وگرنه شمارنده را یکی افزایش می‌دهد.

    ``cache.add()`` (اتمیک در LocMem و Redis هر دو - SETNX در Redis) پیش از
    ``cache.incr()`` فراخوانی می‌شود، نه الگویِ قدیمیِ
    ``try: incr() except ValueError: set(1)``: آن الگو زیرِ بیش از یک
    worker/پردازش هم‌زمان یک مسابقه‌ی واقعی دارد - اگر دو درخواستِ اول برایِ
    یک شناسه‌ی تازه *دقیقاً* هم‌زمان برسند، هر دو ``incr`` را با کلیدِ نبودنی
    می‌بینند، هر دو ``ValueError`` می‌گیرند، و هر دو با ``set(key, 1, ...)``
    شمارنده را به ۱ برمی‌گردانند - یکی از دو تلاش گم می‌شود و پنجره عملاً
    ``max_attempts + 1`` تلاش را اجازه می‌دهد. ``add()`` این مسابقه را از
    بین می‌برد: فقط یکی از دو فراخوانِ هم‌زمان موفق به ساختِ کلید (با مقدارِ
    ۰ و TTLِ پنجره) می‌شود؛ فراخوانِ دیگر ``add`` را false می‌بیند اما کلید
    را از قبل موجود می‌یابد - در هر دو حالت، ``incr()``یِ بعدی که هر دو
    فراخوان انجام می‌دهند، شمارنده را به‌درستی و بدونِ گم‌شدنِ هیچ تلاشی
    افزایش می‌دهد. ``incr`` نه در LocMem نه در Redis به TTLِ کلید دست
    نمی‌زند (فقط مقدار را عوض می‌کند) - پس ``add``یِ اول TTLِ پنجره را
    برایِ کلِ عمرِ این پنجره‌ی ثابت (fixed-window) تثبیت می‌کند."""
    cache = caches[_RATE_LIMIT_CACHE_ALIAS]
    key = f"{_CACHE_PREFIX}:{action}:{identifier}"
    cache.add(key, 0, timeout=window_seconds)
    count = cache.incr(key)
    if count > max_attempts:
        raise RateLimitExceeded(f"تعداد تلاش برای «{action}» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید")


def _valid_real_ip(raw) -> str | None:
    """``raw`` را به یک IPv4/IPv6 معتبرِ تک (نه لیست/رشته‌ی کاما-جدا) تبدیل
    می‌کند، وگرنه ``None``. ``ipaddress.ip_address`` هر مقداری غیر از یک
    آدرسِ تکی را رد می‌کند - پس یک X-Real-IP جعلیِ کاما-جدا (مثلِ
    ``"1.2.3.4, 5.6.7.8"``) به‌طورِ طبیعی نامعتبر شناخته می‌شود، بدونِ
    نیاز به بررسیِ جداگانه‌ی کاما."""
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def client_ip_or_unknown(request) -> str:
    """تنها نقطه‌ی استخراجِ IPِ کلاینت در کلِ کدبیس - همه‌ی محل‌هایی که IP را
    برایِ rate limit یا verification استفاده می‌کنند باید از همین تابع
    استفاده کنند، نه از ``request.META`` مستقیم.

    دو حالت، بسته به ``settings.RASTISI_TRUST_PROXY_CLIENT_IP`` (پیش‌فرض
    False):

    * **False (پیش‌فرض - dev/تست/دیپلویِ مستقیم بدونِ پراکسیِ معتبر)**:
      فقط ``REMOTE_ADDR`` برگردانده می‌شود؛ هیچ هدرِ ارسالی از سمتِ کلاینت
      (``X-Forwarded-For``، ``X-Real-IP``) هرگز خوانده نمی‌شود - چون بدونِ
      یک پراکسیِ شناخته‌شده که این هدر را overwrite کند، اعتماد به آن یعنی
      مهاجم می‌تواند IPِ دلخواه جعل کند و rate limit را دور بزند. اگر
      ``REMOTE_ADDR`` غایب یا رشته‌ی خالی باشد (رفتارِ مستندِ Gunicorn پشتِ
      یک Unix socket - توپولوژیِ واقعیِ RastiSi)، «unknown» برگردانده
      می‌شود، نه رشته‌ی خالی - وگرنه همه‌ی کاربرانِ واقعی زیرِ یک کلیدِ
      یکسان جمع می‌شدند.

    * **True (فقط برایِ دیپلویی که پراکسیِ آن ``X-Real-IP`` را برایِ *هر*
      درخواست overwrite می‌کند - نگاه کنید به
      ``docs/deployment/PRODUCTION_CONFIGURATION.md``)**: فقط
      ``X-Real-IP`` خوانده می‌شود، هرگز ``X-Forwarded-For`` - چون Nginxِ
      تولیدِ RastiSi صراحتاً ``X-Real-IP = $remote_addr`` می‌گذارد (کاملاً
      overwrite، نه append)، در حالی که ``X-Forwarded-For`` می‌تواند
      زنجیره‌ای باشد که کلاینت پیش از رسیدن به Nginx خودش نوشته - استفاده‌ی
      کورکورانه از اولین عضوِ آن یعنی اعتماد به مقداری که کلاینت ساخته.
      مقدار با ``ipaddress`` معتبرسنجی می‌شود (IPv4 و IPv6 هر دو پذیرفته
      می‌شوند)؛ اگر هدر غایب یا نامعتبر باشد (شاملِ مقادیرِ کاما-جدا)،
      «unknown» برگردانده می‌شود - بدونِ fallback به ``REMOTE_ADDR``، چون
      در این حالت ``REMOTE_ADDR`` خودِ آدرسِ پراکسی/Unix socket است، نه
      کلاینتِ واقعی.

    در هر دو حالت، نتیجه («unknown» یا IPِ واقعی) هنوز هم می‌تواند بینِ
    کاربرانِ واقعیِ پشتِ یک پراکسیِ مشترک یکسان باشد - محافظتِ
    per-identifier (نگاه کنید به فراخوان‌های ``enforce_rate_limit`` که
    علاوه بر IP، با شناسه‌ی حساب/شماره هم قفل می‌شوند) خطِ دفاعِ واقعی در
    برابرِ brute-force است، نه این تابع؛ این تابع فقط IPِ درست را - وقتی
    واقعاً قابلِ اعتماد است - به آن لایه‌ها می‌دهد."""
    if getattr(settings, "RASTISI_TRUST_PROXY_CLIENT_IP", False):
        return _valid_real_ip(request.META.get("HTTP_X_REAL_IP")) or "unknown"
    return request.META.get("REMOTE_ADDR") or "unknown"
