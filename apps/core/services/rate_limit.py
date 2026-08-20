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
from django.core.cache.backends.redis import RedisCache

_CACHE_PREFIX = "ratelimit"
_RATE_LIMIT_CACHE_ALIAS = "rate_limit"

# اسکریپتِ Lua برای شمارشِ اتمیکِ پنجره‌ی ثابت روی Redis — نگاه کنید به
# ``_redis_incr_with_ttl`` برای اینکه چرا این لازم است (Djangoِ
# RedisCache.incr() به‌تنهایی اتمیک نیست).
_LUA_INCR_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RateLimitExceeded(Exception):
    """این کنش برای این شناسه بیش از حدِ مجاز در بازه‌ی اخیر تکرار شده است."""


# یک کلاینتِ خام و مستقلِ redis-py به‌ازایِ هر location — نه هر فراخوان.
# redis-py خودش connection pooling می‌کند؛ کلاینت‌ها برایِ استفاده‌ی مجدد در
# طولِ عمرِ پردازش ساخته می‌شوند. RastiSi تولید با Gunicornِ sync-worker
# (نه threaded) اجرا می‌شود، پس رقابتِ نخی روی این دیکشنری در عمل رخ
# نمی‌دهد؛ حتی اگر رخ دهد، بدترین حالت ساختِ یک کلاینتِ اضافیِ بی‌ضرر است،
# نه یک باگِ درستی.
_raw_redis_clients: dict[str, object] = {}


def _raw_redis_client(location: str):
    """کلاینتِ خامِ redis-py را برای اجرایِ اتمیکِ Lua script برمی‌گرداند —
    فقط با API عمومیِ پکیجِ ``redis`` (``from_url``/``eval``)، نه با هیچ
    جزئیاتِ خصوصیِ Djangoِ ``RedisCache`` (نگاه کنید به
    ``_redis_incr_with_ttl`` برای دلیلِ اینکه چرا کلاینتِ داخلیِ Django
    برایِ این عملیات کافی نیست و چرا از آن استفاده نمی‌شود). ``redis``
    عمداً اینجا (نه بالایِ فایل) import می‌شود: این ماژول در هر پردازشی
    import می‌شود، حتی وقتی alias ``rate_limit`` هنوز LocMem است و هرگز
    این مسیر اجرا نمی‌شود — نصب‌نبودنِ پکیجِ ``redis`` در چنین محیطی نباید
    باعثِ شکستِ import شود."""
    client = _raw_redis_clients.get(location)
    if client is None:
        import redis

        client = redis.Redis.from_url(location)
        _raw_redis_clients[location] = client
    return client


def _redis_incr_with_ttl(cache, key: str, window_seconds: int) -> int:
    """نسخه‌ی Redis از «افزایشِ اتمیکِ شمارنده، با TTL درست چه در ساختِ اول
    چه در افزایش‌های بعدی» — با یک Lua script که Redis آن را یک‌پارچه و
    بدون امکانِ interleave با هیچ فرمانِ دیگری اجرا می‌کند (تضمینِ خودِ
    Redis برایِ اسکریپت‌ها، نه فرضی از طرفِ این کد).

    چرا این لازم است — چرا ``cache.add()`` + ``cache.incr()`` (نسخه‌ی
    قبلی) کافی نبود:

    Djangoِ 5.2 ``RedisCache.incr()`` (نگاه کنید به
    ``django/core/cache/backends/redis.py``، ``RedisCacheClient.incr``)
    این‌طور پیاده‌سازی شده:

        if not client.exists(key):
            raise ValueError(...)
        return client.incr(key, delta)

    ``EXISTS`` و ``INCR`` دو فرمانِ *جداگانه*‌ی Redis‌اند — نه یک تراکنشِ
    اتمیک. یک مسابقه‌ی واقعی روی مرزِ انقضا وجود دارد:

    1. کلیدِ یک پنجره‌ی موجود به انقضا نزدیک است (چند میلی‌ثانیه مانده).
    2. ``cache.add(...)`` چون کلید هنوز موجود است False برمی‌گرداند —
       این قسمت مشکلی ندارد.
    3. ``cache.incr()``یِ Django فراخوانده می‌شود؛ ``client.exists(key)``
       را اجرا می‌کند و True می‌بیند (کلید هنوز — درست همان لحظه — موجود
       است).
    4. بینِ همین بررسیِ ``exists`` و فرمانِ بعدی، کلید در Redis منقضی و
       حذف می‌شود.
    5. Django فرمانِ ``INCR`` را روی همان کلید اجرا می‌کند؛ طبقِ رفتارِ
       مستندِ Redis، ``INCR``/``INCRBY`` روی کلیدِ نبودنی، کلید را از صفر
       می‌سازد — اما **بدونِ TTL** (کلیدِ جدید دائمی/persistent است، چون
       ``INCR`` هیچ TTLای تنظیم نمی‌کند).

    نتیجه: یک شمارنده‌ی *دائمی و بدونِ TTL* که هرگز خودش ریست نمی‌شود —
    یک باگِ درستیِ واقعی (نه صرفاً کاهشِ دقت): یک کاربرِ واقعی می‌تواند
    برایِ همیشه (تا restart سرویس) قفل بماند، چون این کلید دیگر هرگز منقضی
    نمی‌شود. این مسابقه مخصوصِ بهم‌ریختنِ TTL است؛ روی *شمارشِ* درست اثر
    ندارد (INCR خودش درست می‌شمارد)، اما درستیِ کاملِ الگوریتمِ پنجره‌ی ثابت
    نیاز به *هر دو* — شمارشِ درست و TTLِ درست — دارد.

    این تابع با یک Lua script (اجرا با ``EVAL``، تضمینِ اتمیک‌بودنِ خودِ
    Redis برایِ اسکریپت‌ها) هر دو مسابقه را از بین می‌برد:

    * مسابقه‌ی «ساختِ اولِ هم‌زمان» (نگرانیِ نسخه‌ی قبلی): چون Redis
      اسکریپت‌ها را تک‌رشته‌ای و پشتِ‌سرِهم اجرا می‌کند، اگر دو فراخوانِ
      هم‌زمان روی یک کلیدِ تازه برسند، Redis آن‌ها را سریالی اجرا می‌کند —
      اولی ``INCR`` می‌گیرد count=1 (پس ``EXPIRE`` هم می‌گذارد)، دومی
      count=2 می‌گیرد (پس ``EXPIRE`` نمی‌گذارد، چون قبلاً تنظیم شده) — دقیقاً
      یک برنده، بدونِ گم‌شدنِ هیچ تلاشی.
    * مسابقه‌ی مرزِ انقضا (این تابع): چون ``INCR`` و شرطِ ``count == 1`` و
      ``EXPIRE`` همه در یک اسکریپتِ اتمیک‌اند، هیچ فرمانِ دیگری — از جمله
      خودِ انقضایِ Redis — نمی‌تواند بینِ آن‌ها فاصله بیفتد. اگر کلید همین
      الان منقضی شده باشد، ``INCR`` آن را از صفر می‌سازد، ``count == 1``
      می‌شود، و همان اسکریپت بلافاصله ``EXPIRE`` تازه می‌گذارد — یک شمارنده‌ی
      بدونِ TTL هرگز ممکن نیست.

    کلید با ``cache.make_key()`` (API عمومیِ Django، نه چیزِ خصوصی) ساخته
    می‌شود تا همان کلیدی باشد که Djangoِ ``cache.get()``/``incr()`` هم
    می‌سازند — خواندنِ همان مقدار از دو مسیر (این تابع، یا API معمولیِ
    cache) سازگار می‌ماند."""
    full_key = cache.make_key(key)
    location = settings.CACHES[_RATE_LIMIT_CACHE_ALIAS]["LOCATION"]
    client = _raw_redis_client(location)
    return client.eval(_LUA_INCR_WITH_TTL, 1, full_key, window_seconds)


def _generic_cache_incr_with_ttl(cache, key: str, window_seconds: int) -> int:
    """نسخه‌ی عمومی (LocMem/هر cache-backendِ غیرِ Redis) — بدونِ مسابقه‌ی
    شبکه‌ای چون هیچ round-tripِ شبکه‌ای بینِ ``add()`` و ``incr()`` نیست:
    هر دو فرمانِ Python هستند که زیرِ همان قفلِ داخلیِ پردازشِ Djangoِ
    LocMemCache اجرا می‌شوند (``django.core.cache.backends.locmem.
    LocMemCache._lock``) — نه یک تراکنشِ شبکه‌ایِ چندمرحله‌ای مثلِ Redis.

    این هیچ تضمینِ *بین‌پردازشی* نمی‌دهد — و نباید هم بدهد: LocMem خودش
    ذاتاً process-local است (نگاه کنید به ``apps.core.checks.
    rate_limit_backend_check``)، پس «اتمیک بینِ Gunicorn workerها» اصلاً
    برایِ این backend معنا ندارد؛ فقط برایِ Redis (بالا) لازم و پیاده‌شده
    است.

    ``except ValueError`` فقط برایِ حالتِ نظری‌ای است که کلید دقیقاً بینِ
    ``add()`` و ``incr()`` منقضی شود — با ``window_seconds``یِ واقعیِ این
    کدبیس (۳۰۰ تا ۶۰۰ ثانیه در همه‌ی call siteها) عملاً غیرِممکن است، اما
    یک تلاشِ دوم به‌جایِ یک ``ValueError``ی بی‌صدا/کرش‌کننده امن‌تر و
    قطعی (deterministic) است."""
    cache.add(key, 0, timeout=window_seconds)
    try:
        return cache.incr(key)
    except ValueError:
        cache.add(key, 0, timeout=window_seconds)
        return cache.incr(key)


def enforce_rate_limit(action: str, identifier: str, *, max_attempts: int, window_seconds: int) -> None:
    """اگر تعداد فراخوانی‌های اخیر ``action``+``identifier`` از ``max_attempts``
    در ``window_seconds`` ثانیه‌ی اخیر بیشتر باشد، ``RateLimitExceeded`` می‌دهد؛
    وگرنه شمارنده را یکی افزایش می‌دهد.

    وقتی alias ``rate_limit`` واقعاً Redis است (``RASTISI_RATE_LIMIT_
    CACHE_URL`` تنظیم شده)، از ``_redis_incr_with_ttl`` (Lua script اتمیک)
    استفاده می‌شود — نه ``cache.add``/``cache.incr``ی Django، چون آن دو
    زیرِ Redis یک مسابقه‌ی واقعیِ TTL دارند (نگاه کنید به داکیومنتِ
    ``_redis_incr_with_ttl``). برایِ هر backendِ دیگر (امروز: LocMemِ
    dev/تست) از ``_generic_cache_incr_with_ttl`` استفاده می‌شود.

    **رفتار وقتی Redis در دسترس نیست** (سرویس پایین است یا شبکه قطع است):
    این تابع عمداً استثنایِ ``redis``/``redis-py`` (مثلاً
    ``redis.exceptions.ConnectionError``) را نمی‌گیرد — می‌گذارد بدونِ
    دست‌خوردن بالا برود و از ``enforce_rate_limit`` هم خارج شود. یعنی
    فراخوانِ ویو با یک خطایِ سرور (۵۰۰) شکست می‌خورد، نه اینکه بی‌صدا rate
    limit را نادیده بگیرد و اجازه‌ی عبور بدهد. fail-closed عمدی است: یک
    محدودیتِ نرخِ امنیتی که در نبودِ وابستگی‌اش بی‌صدا خاموش شود، بدتر از
    یک ۵۰۰ِ موقت است."""
    cache = caches[_RATE_LIMIT_CACHE_ALIAS]
    key = f"{_CACHE_PREFIX}:{action}:{identifier}"
    if isinstance(cache, RedisCache):
        count = _redis_incr_with_ttl(cache, key, window_seconds)
    else:
        count = _generic_cache_incr_with_ttl(cache, key, window_seconds)
    if count > max_attempts:
        raise RateLimitExceeded(f"تعداد تلاش برای «{action}» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید")


def _valid_single_ip(raw) -> str | None:
    """``raw`` را به یک IPv4/IPv6 معتبرِ تک (نه لیست/رشته‌ی کاما-جدا، نه
    فقط فاصله) تبدیل می‌کند، وگرنه ``None``. هم برایِ ``X-Real-IP`` (حالتِ
    trusted-proxy) هم برایِ ``REMOTE_ADDR`` (حالتِ پیش‌فرض) استفاده می‌شود
    — Phase 1C صریحاً «اگر مقدارِ انتخاب‌شده غایب یا نامعتبر است، unknown
    برگردان» را برایِ *هر دو* خواسته، نه فقط X-Real-IP.

    ``ipaddress.ip_address`` هر مقداری غیر از یک آدرسِ تکی را رد می‌کند —
    پس یک مقدارِ جعلیِ کاما-جدا (مثلِ ``"1.2.3.4, 5.6.7.8"``) به‌طورِ طبیعی
    نامعتبر شناخته می‌شود، بدونِ نیاز به بررسیِ جداگانه‌ی کاما."""
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
    False) — در **هر دو** حالت، مقدارِ انتخاب‌شده با ``_valid_single_ip``
    معتبرسنجی می‌شود؛ غایب یا نامعتبر (شاملِ کاما-جدا/فقط‌فاصله) همیشه
    «unknown» می‌دهد، نه رشته‌ی خام:

    * **False (پیش‌فرض - dev/تست/دیپلویِ مستقیم بدونِ پراکسیِ معتبر)**:
      فقط ``REMOTE_ADDR`` بررسی می‌شود؛ هیچ هدرِ ارسالی از سمتِ کلاینت
      (``X-Forwarded-For``، ``X-Real-IP``) هرگز خوانده نمی‌شود، حتی برایِ
      معتبرسنجی — چون بدونِ یک پراکسیِ شناخته‌شده که این هدر را overwrite
      کند، اعتماد به آن یعنی مهاجم می‌تواند IPِ دلخواه جعل کند و rate
      limit را دور بزند. اعتبارسنجیِ ``REMOTE_ADDR`` هم مستقل از این ریسک
      لازم است: WSGI تضمین نمی‌کند این مقدار همیشه یک IPِ تک‌ِ معتبر باشد
      (مثلاً رشته‌ی خالیِ مستندِ Gunicorn پشتِ Unix socket — توپولوژیِ واقعیِ
      RastiSi)، و یک مقدارِ نامعتبر نباید بی‌بررسی به‌عنوانِ شناسه‌ی
      rate-limit استفاده شود.

    * **True (فقط برایِ دیپلویی که پراکسیِ آن ``X-Real-IP`` را برایِ *هر*
      درخواست overwrite می‌کند - نگاه کنید به
      ``docs/deployment/PRODUCTION_CONFIGURATION.md``)**: فقط
      ``X-Real-IP`` بررسی می‌شود، هرگز ``X-Forwarded-For`` - چون Nginxِ
      تولیدِ RastiSi صراحتاً ``X-Real-IP = $remote_addr`` می‌گذارد (کاملاً
      overwrite، نه append)، در حالی که ``X-Forwarded-For`` می‌تواند
      زنجیره‌ای باشد که کلاینت پیش از رسیدن به Nginx خودش نوشته - استفاده‌ی
      کورکورانه از اولین عضوِ آن یعنی اعتماد به مقداری که کلاینت ساخته.
      اگر هدر غایب یا نامعتبر باشد، «unknown» برگردانده می‌شود - بدونِ
      fallback به ``REMOTE_ADDR``، چون در این حالت ``REMOTE_ADDR`` خودِ
      آدرسِ پراکسی/Unix socket است، نه کلاینتِ واقعی.

    در هر دو حالت، نتیجه («unknown» یا IPِ واقعی) هنوز هم می‌تواند بینِ
    کاربرانِ واقعیِ پشتِ یک پراکسیِ مشترک یکسان باشد - محافظتِ
    per-identifier (نگاه کنید به فراخوان‌های ``enforce_rate_limit`` که
    علاوه بر IP، با شناسه‌ی حساب/شماره هم قفل می‌شوند) خطِ دفاعِ واقعی در
    برابرِ brute-force است، نه این تابع؛ این تابع فقط IPِ درست را - وقتی
    واقعاً قابلِ اعتماد است - به آن لایه‌ها می‌دهد."""
    if getattr(settings, "RASTISI_TRUST_PROXY_CLIENT_IP", False):
        raw = request.META.get("HTTP_X_REAL_IP")
    else:
        raw = request.META.get("REMOTE_ADDR")
    return _valid_single_ip(raw) or "unknown"
