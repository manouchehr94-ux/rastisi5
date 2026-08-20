"""بررسی‌های سیستمیِ Django برایِ پیکربندیِ امنیتیِ Phase 1C - نگاه کنید به
``apps.core.services.rate_limit`` (شمارنده‌ی rate limit) و
``shop_core.settings.RASTISI_TRUST_PROXY_CLIENT_IP`` (اعتمادِ IPِ پراکسی).

خطاهایِ نامعتبربودنِ خودِ ``RASTISI_RATE_LIMIT_CACHE_URL`` اینجا بررسی
نمی‌شوند - آن اعتبارسنجی همین حالا هم در
``shop_core.env_config.build_rate_limit_cache_config`` در زمانِ بارگذاریِ
``settings.py`` انجام می‌شود (دقیقاً مثلِ ``DATABASE_URL``) و بلافاصله
``ImproperlyConfigured`` می‌دهد - یعنی یک URL بدشکل هرگز حتی به مرحله‌ی
اجرایِ system checkها نمی‌رسد."""

from django.conf import settings
from django.core.cache import caches
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def rate_limit_backend_check(app_configs, **kwargs):
    """هشدار (نه خطا) وقتی ``DEBUG=False`` است اما cache alias
    ``rate_limit`` هنوز process-local (LocMemCache) است - یعنی هر
    workerِ Gunicorn شمارنده‌ی خودش را جدا نگه می‌دارد، نه یک شمارنده‌ی
    مشترک.

    عمداً Warning، نه Error:

    1. لایه‌ی identifier-محورِ rate limit (شماره/ایمیل/username - نگاه
       کنید به فراخوان‌هایِ ``enforce_rate_limit`` در
       ``apps.customers.views``/``apps.dashboard.views``/
       ``apps.portal.views``) هنوز هم واقعاً کار می‌کند؛ فقط آستانه‌ی
       مؤثرش با LocMemِ چندworkerی به‌جایِ غیرفعال‌شدنِ کامل، تا سقفِ
       تعدادِ workerها (همین حالا در تولید: ۲) بزرگ‌تر می‌شود - یک
       تضعیفِ محدود، نه یک دورزدنِ کاملِ حفاظت.
    2. اگر این بررسی Error بود، ``python manage.py check --deploy``
       (و در نتیجه ``migrate``/``runserver`` با ``--deploy``محور) زیرِ
       پیکربندیِ *همین حالا مستقرشده‌یِ* تولید (۲ workerِ Gunicorn،
       بدونِ Redis، ``DEBUG=False``) بلافاصله با استقرارِ همین کد fail
       می‌شد - پیش از آنکه اپراتور گامِ کنترل‌شده‌ی بعدیِ Part D
       (نصب/پیکربندیِ Redis) را انجام دهد. این دقیقاً همان چیزی است که
       Phase 1C صریحاً ممنوع می‌کند: کدِ این فاز نباید به‌تنهایی تولید را
       بشکند یا آن را به یک سرویسِ Redisِ هنوز-پیکربندی‌نشده وابسته کند.

    Warning در خروجیِ ``check --deploy`` دیده می‌شود اما هیچ دستوری را
    متوقف نمی‌کند - دقیقاً رفتارِ موردنیاز: مرئی برایِ اپراتور، بدونِ
    شکستنِ استقرارِ فعلی."""
    cache = caches["rate_limit"]
    backend_path = f"{type(cache).__module__}.{type(cache).__qualname__}"
    if settings.DEBUG or "locmem" not in backend_path.lower():
        return []
    return [
        Warning(
            "The 'rate_limit' cache is process-local (LocMemCache) while DEBUG=False. "
            "With more than one worker process, rate-limit counters are not shared "
            "across workers, so brute-force/OTP-spam protection is enforced per "
            "worker rather than globally — reduced precision, not disabled protection "
            "(per-identifier limits, e.g. by account/phone, still apply independently).",
            hint=(
                "Set RASTISI_RATE_LIMIT_CACHE_URL to a shared redis://host:port/db "
                "reachable from every worker before relying on precise, globally "
                "shared rate limiting. See docs/deployment/PRODUCTION_CONFIGURATION.md."
            ),
            id="rastisi.core.W001",
        )
    ]


@register()
def trust_proxy_debug_check(app_configs, **kwargs):
    """هشدار وقتی ``RASTISI_TRUST_PROXY_CLIENT_IP=True`` همراه با
    ``DEBUG=True`` تنظیم شده - یعنی هر کلاینتِ محلی می‌تواند با فرستادنِ
    هدرِ ``X-Real-IP`` (مثلاً ``curl -H "X-Real-IP: 1.2.3.4"``) هویتِ
    rate-limitِ خودش را جعل کند، چون در این پیکربندی هیچ پراکسیِ
    شناخته‌شده‌ای تضمین نمی‌کند که این هدر را overwrite می‌کند. عمداً بدونِ
    ``deploy=True`` - یک اشتباهِ رایجِ توسعه/تست (مثلاً کپیِ بی‌دقتِ
    ``.env`` تولید به‌صورتِ محلی)، نه صرفاً یک نگرانیِ آماده‌سازیِ استقرار،
    پس باید در ``check``یِ معمولی هم دیده شود."""
    if not settings.DEBUG or not getattr(settings, "RASTISI_TRUST_PROXY_CLIENT_IP", False):
        return []
    return [
        Warning(
            "RASTISI_TRUST_PROXY_CLIENT_IP=True together with DJANGO_DEBUG=True lets any "
            "local client set X-Real-IP directly and have it trusted for rate-limit "
            "identity, since no reverse proxy is guaranteed to be overwriting it in this "
            "configuration.",
            hint=(
                "Only enable RASTISI_TRUST_PROXY_CLIENT_IP in a deployment where the "
                "reverse proxy unconditionally overwrites X-Real-IP for every request. "
                "Leave it unset for local development. See "
                "docs/deployment/PRODUCTION_CONFIGURATION.md."
            ),
            id="rastisi.core.W002",
        )
    ]
