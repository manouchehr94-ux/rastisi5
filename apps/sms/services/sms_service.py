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
from .backends import ConsoleBackend, MelipayamakBackend, SmsBackend

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


def get_backend() -> SmsBackend:
    """بر اساس ShopSettings.sms_backend، پیاده‌سازی درست را می‌سازد."""
    shop = ShopSettings.load()
    if shop.sms_backend == ShopSettings.SmsBackend.MELIPAYAMAK:
        return MelipayamakBackend(
            username=shop.melipayamak_username,
            password=shop.melipayamak_password,
            sender=shop.sms_sender_number,
        )
    return ConsoleBackend()


def _render(template: SmsTemplate, context: dict, shop_name: str) -> str:
    validate_template_body(template.event_key, template.body)
    defaults = dict.fromkeys(EVENT_VARIABLES.get(template.event_key, {}), "")
    full_context = {**defaults, **context, "shop_name": shop_name}
    return template.body.format(**full_context)


def _dispatch(*, event_key: str, phone: str, message: str) -> SmsLog:
    log = SmsLog.objects.create(
        event_key=event_key, recipient=phone, message=message, status=SmsLog.Status.PENDING,
    )
    result = get_backend().send(to=phone, text=message)
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


def send_event_sms(event_key: str, phone: str, context: dict | None = None) -> SmsLog | None:
    """پیامک یک رویداد واقعی را ارسال می‌کند. اگر سیستم/رویداد غیرفعال یا قالب نامعتبر باشد، بی‌صدا None برمی‌گرداند."""
    try:
        shop = ShopSettings.load()
        if not shop.sms_enabled:
            return None

        template = SmsTemplate.objects.filter(event_key=event_key, is_active=True).first()
        if template is None:
            return None

        message = _render(template, context or {}, shop.name)
        return _dispatch(event_key=event_key, phone=phone, message=message)
    except Exception:
        logger.exception("send_event_sms failed for event=%s phone=%s", event_key, phone)
        return None


DUMMY_TEST_CONTEXT = {
    "customer_name": "کاربر آزمایشی", "order_code": "TEST-00000",
    "amount": "۱۰۰٬۰۰۰", "tracking_code": "TEST-TRACK-123", "otp_code": "۱۲۳۴۵۶",
}


def send_test_sms(*, event_key: str, phone: str) -> SmsLog:
    """ارسال آزمایشی از پنل مدیریت — صرف‌نظر از فعال/غیرفعال بودن رویداد یا کل سیستم، برای تست واقعی اتصال به درگاه."""
    template = SmsTemplate.objects.filter(event_key=event_key).first()
    if template is None:
        raise SmsTemplateError("قالبی برای این رویداد یافت نشد")

    shop = ShopSettings.load()
    message = _render(template, DUMMY_TEST_CONTEXT, shop.name)
    return _dispatch(event_key=event_key, phone=phone, message=message)
