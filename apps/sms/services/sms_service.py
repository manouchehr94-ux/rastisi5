"""لایه‌ی سرویس ارسال پیامک — رندر امن قالب، ارسال، و ثبت در SmsLog.

قاعده‌ی سخت‌گیرانه‌ی این ماژول: send_event_sms هرگز نباید Exception پرتاب کند.
هر مسیر خطا (قالب غیرفعال، متغیر ناشناخته، خطای شبکه‌ی بک‌اند) یا بی‌صدا
نادیده گرفته می‌شود یا در SmsLog با status=failed ثبت می‌شود — جریان اصلی
(ثبت‌نام، ثبت سفارش، تغییر وضعیت) هیچ‌وقت به‌خاطر پیامک نباید متوقف شود.
"""

import logging
import re

from django.utils import timezone

from apps.core.models import ShopSettings

from ..events import EVENT_VARIABLES
from ..models import SmsLog, SmsTemplate
from .backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsBackend

logger = logging.getLogger(__name__)

VARIABLE_RE = re.compile(r"\{(\w+)\}")


class SmsTemplateError(Exception):
    """قالب پیامک نامعتبر است (مثلاً شامل متغیر ناشناخته)."""


def validate_template_body(event_key: str, body: str) -> None:
    """اگر متن قالب متغیری خارج از فهرست مجاز آن رویداد داشته باشد، خطای واضح می‌دهد."""
    allowed = EVENT_VARIABLES.get(event_key, {})
    used = set(VARIABLE_RE.findall(body))
    unknown = used - set(allowed.keys())
    if unknown:
        allowed_list = "، ".join(f"{{{k}}}" for k in allowed) or "—"
        raise SmsTemplateError(
            f"متغیر ناشناخته در قالب: {{{'، '.join(sorted(unknown))}}}. "
            f"متغیرهای مجاز این رویداد: {allowed_list}"
        )


def get_backend(*, store) -> SmsBackend:
    """بر اساس ShopSettings.sms_backend همان Store، پیاده‌سازی درست را می‌سازد."""
    shop = ShopSettings.load(store=store)
    if shop.sms_backend == ShopSettings.SmsBackend.MELIPAYAMAK:
        return MelipayamakBackend(
            username=shop.melipayamak_username,
            password=shop.melipayamak_password,
            sender=shop.sms_sender_number,
        )
    if shop.sms_backend == ShopSettings.SmsBackend.KAVENEGAR:
        return KavenegarBackend(
            api_key=shop.kavenegar_api_key,
            sender=shop.sms_sender_number,
        )
    return ConsoleBackend()


def _render(template: SmsTemplate, context: dict, shop_name: str) -> str:
    validate_template_body(template.event_key, template.body)
    defaults = dict.fromkeys(EVENT_VARIABLES.get(template.event_key, {}), "")
    full_context = {**defaults, **context, "shop_name": shop_name}
    return template.body.format(**full_context)


def _dispatch(*, event_key: str, phone: str, message: str, store) -> SmsLog:
    log = SmsLog.objects.create(
        event_key=event_key, recipient=phone, message=message, status=SmsLog.Status.PENDING,
    )
    result = get_backend(store=store).send(to=phone, text=message)
    log.attempt_count = 1
    if result.success:
        log.status = SmsLog.Status.SENT
        log.provider_ref_id = result.provider_ref_id
        log.sent_at = timezone.now()
    else:
        log.status = SmsLog.Status.FAILED
        log.error_message = result.error_message
    log.save(update_fields=["status", "provider_ref_id", "error_message", "attempt_count", "sent_at", "updated_at"])
    return log


def send_event_sms(event_key: str, phone: str, context: dict | None = None, *, store) -> SmsLog | None:
    """پیامک یک رویداد واقعی را برای Store مشخص ارسال می‌کند.

    ``store`` الزامی و صریح است — این تابع خودش هرگز از حالت سازگاری موقت
    (Akhlaghi) یا هر Store دیگری استفاده نمی‌کند؛ فراخوان (view/سرویس)
    مسئول resolve کردن Store همان درخواست/رویداد است، نه این تابع.

    اگر سیستم/رویداد غیرفعال یا قالب نامعتبر باشد، یا Store هنوز
    ShopSettings نداشته باشد، بی‌صدا None برمی‌گرداند و خطا را فقط لاگ
    می‌کند — این تابع هرگز نباید Exception پرتاب کند (جریان اصلی کسب‌وکار
    هیچ‌وقت نباید به‌خاطر پیامک متوقف شود)."""
    if store is None:
        logger.error(
            "send_event_sms called with store=None for event=%s phone=%s — "
            "the caller must resolve an authoritative Store before sending; "
            "no SMS is sent and no Akhlaghi/compatibility fallback is used here",
            event_key, phone,
        )
        return None
    try:
        shop = ShopSettings.load(store=store)
        if not shop.sms_enabled:
            return None

        template = SmsTemplate.objects.filter(event_key=event_key, is_active=True).first()
        if template is None:
            return None

        message = _render(template, context or {}, shop.name)
        return _dispatch(event_key=event_key, phone=phone, message=message, store=store)
    except Exception:
        logger.exception("send_event_sms failed for event=%s phone=%s store=%s", event_key, phone, store.slug)
        return None


DUMMY_TEST_CONTEXT = {
    "customer_name": "کاربر آزمایشی", "order_code": "TEST-00000",
    "amount": "۱۰۰٬۰۰۰", "tracking_code": "TEST-TRACK-123", "otp_code": "۱۲۳۴۵۶",
}


def send_test_sms(*, event_key: str, phone: str, store) -> SmsLog:
    """ارسال آزمایشی از پنل مدیریت برای Store مشخص — صرف‌نظر از فعال/غیرفعال
    بودن رویداد یا کل سیستم، برای تست واقعی اتصال به درگاه همان Store."""
    template = SmsTemplate.objects.filter(event_key=event_key).first()
    if template is None:
        raise SmsTemplateError("قالبی برای این رویداد یافت نشد")

    shop = ShopSettings.load(store=store)
    message = _render(template, DUMMY_TEST_CONTEXT, shop.name)
    return _dispatch(event_key=event_key, phone=phone, message=message, store=store)
