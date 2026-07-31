"""ارسال پیامک سطحِ پلتفرم (نه Store) — فقط برایِ OTP هویتِ مالک/کارمند
(Section 3). از همان کلاس‌هایِ backend موجودِ ``apps.sms.services.backends``
استفاده می‌کند (بدونِ پیاده‌سازیِ تکراری)؛ فقط انتخاب/پیکربندیِ backend
سطحِ پلتفرم است، نه Store-scoped."""

import logging

from django.conf import settings

from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsBackend, SmsSendResult

logger = logging.getLogger(__name__)


def get_platform_sms_backend() -> SmsBackend:
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
