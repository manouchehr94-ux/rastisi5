"""ارسال پیامکِ سطحِ پلتفرم — گیت‌وی مرکزیِ راستیسی. از همان کلاس‌هایِ
backend موجودِ ``apps.sms.services.backends`` استفاده می‌کند (بدونِ
پیاده‌سازیِ تکراری)؛ فقط انتخاب/پیکربندیِ backend سطحِ پلتفرم است.

این ماژول اکنون دو مصرف‌کننده دارد: OTP هویتِ مالک/کارمندِ پلتفرم
(بدونِ تغییر)، و — پس از جداسازیِ زیرساختِ پیامک از پنلِ مدیریتِ فروشگاه
— هر ارسالِ پیامکِ Store هم (``apps.sms.services.sms_service.get_backend``)
از همین تابع استفاده می‌کند، مگر وقتی Store گیت‌وی اندرویدِ SmsRasti را
(دستگاهِ فیزیکیِ خودش، نه زیرساختِ پلتفرم) صریحاً انتخاب کرده باشد.

اولویتِ منبعِ پیکربندی: ``PlatformConfiguration`` (پایگاه‌داده، ویرایش از
Platform Admin) → در نبودِ آن، ``settings.RASTISI_OWNER_SMS_*`` (env، برایِ
سازگاریِ عقب‌رو با استقرارهایی که هنوز از env استفاده می‌کنند)."""

import logging

from django.conf import settings

from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsBackend, SmsSendResult

logger = logging.getLogger(__name__)


def get_platform_sms_backend() -> SmsBackend:
    from apps.portal.services.platform_config_service import get_platform_configuration

    config = get_platform_configuration()
    if config.sms_backend and config.sms_backend != "console":
        credentials = config.get_sms_credentials()
        if config.sms_backend == "melipayamak":
            return MelipayamakBackend(
                username=credentials.get("melipayamak_username", ""),
                password=credentials.get("melipayamak_password", ""),
                sender=config.sms_sender_number,
            )
        if config.sms_backend == "kavenegar":
            return KavenegarBackend(
                api_key=credentials.get("kavenegar_api_key", ""),
                sender=config.sms_sender_number,
            )

    # سازگاریِ عقب‌رو: هنوز چیزی در PlatformConfiguration پیکربندی نشده —
    # به تنظیماتِ env قبلی (مالکِ پلتفرم) برمی‌گردد.
    if settings.RASTISI_OWNER_SMS_BACKEND == "melipayamak":
        return MelipayamakBackend(
            username=settings.RASTISI_OWNER_SMS_USERNAME,
            password=settings.RASTISI_OWNER_SMS_PASSWORD,
            sender=settings.RASTISI_OWNER_SMS_SENDER,
        )
    if settings.RASTISI_OWNER_SMS_BACKEND == "kavenegar":
        return KavenegarBackend(
            api_key=settings.RASTISI_OWNER_SMS_API_KEY,
            sender=settings.RASTISI_OWNER_SMS_SENDER,
        )
    return ConsoleBackend()


def send_platform_sms(*, to: str, text: str) -> SmsSendResult:
    """هرگز Exception پرتاب نمی‌کند — مطابق قراردادِ ``SmsBackend.send`` — و
    هرگز متنِ حساس (شاملِ کدِ OTP) را در سطحِ INFO لاگ نمی‌کند."""
    backend = get_platform_sms_backend()
    result = backend.send(to=to, text=text)
    if not result.success:
        logger.warning("platform SMS send failed: to=%s error=%s", to, result.error_message)
    return result
