"""لایه‌ی سرویس ارسال پیامک — رندر امن قالب، ارسال، و ثبت در SmsLog.

قاعده‌ی سخت‌گیرانه‌ی این ماژول: send_event_sms هرگز نباید Exception پرتاب کند.
هر مسیر خطا (قالب غیرفعال، متغیر ناشناخته، خطای شبکه‌ی بک‌اند) یا بی‌صدا
نادیده گرفته می‌شود یا در SmsLog با status=failed ثبت می‌شود — جریان اصلی
(ثبت‌نام، ثبت سفارش، تغییر وضعیت) هیچ‌وقت به‌خاطر پیامک نباید متوقف شود.
"""

import logging
import re
import secrets

from django.utils import timezone

from apps.core.models import ShopSettings

from ..events import EVENT_VARIABLES, SmsEvent
from ..models import SmsLog, SmsOutboxItem, SmsTemplate
from .backends import SmsBackend, SmsRastiBackend

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
    """درگاهِ ارسالِ این Store را می‌سازد.

    زیرساختِ ارسال (ارائه‌دهنده/کلید/شماره‌ی فرستنده) دیگر Store-scoped
    نیست — همان درگاهِ مرکزیِ پلتفرم استفاده می‌شود (نگاه کنید به
    ``apps.portal.services.owner_sms_service.get_platform_sms_backend``)،
    مگر وقتی Store گیت‌وی اندرویدِ SmsRasti (دستگاهِ فیزیکیِ خودش) را صریحاً
    انتخاب کرده باشد — تنها استثنا، چون آن دستگاه زیرساختِ پلتفرم نیست."""
    shop = ShopSettings.load(store=store)
    if shop.sms_backend == ShopSettings.SmsBackend.SMSRASTI:
        return SmsRastiBackend(store=store, device_token=shop.smsrasti_device_token or "")

    from apps.portal.services.owner_sms_service import get_platform_sms_backend

    return get_platform_sms_backend()


def regenerate_smsrasti_device_token(*, store) -> str:
    """توکنِ جدید و منحصربه‌فردی برای گیت‌وی اندرویدِ این Store می‌سازد و
    ذخیره می‌کند؛ توکنِ قبلی بلافاصله باطل می‌شود — دستگاهِ قدیمی دیگر
    نمی‌تواند poll/ack کند (چرخشِ اعتبارنامه، نه افزودنِ دستگاهِ دوم)."""
    shop = ShopSettings.load(store=store)
    shop.smsrasti_device_token = secrets.token_urlsafe(32)
    shop.save(update_fields=["smsrasti_device_token", "updated_at"])
    return shop.smsrasti_device_token


def _render(template: SmsTemplate, context: dict, shop_name: str) -> str:
    validate_template_body(template.event_key, template.body)
    defaults = dict.fromkeys(EVENT_VARIABLES.get(template.event_key, {}), "")
    full_context = {**defaults, **context, "shop_name": shop_name}
    return template.body.format(**full_context)


def _dispatch(*, event_key: str, phone: str, message: str, store) -> SmsLog:
    log = SmsLog.objects.create(
        store=store, event_key=event_key, recipient=phone, message=message, status=SmsLog.Status.PENDING,
    )
    backend = get_backend(store=store)
    if event_key == SmsEvent.OTP and isinstance(backend, SmsRastiBackend):
        # اسمس‌راستی صف‌بندی‌شده و وابسته به poll دستگاهِ اندروید است — با
        # نیازِ ارسالِ فوریِ OTP (بخشِ اولویتِ ارسال) ناسازگار است؛ هرگز
        # بی‌صدا صف نمی‌شود، همیشه شکستِ واضح با دلیلِ روشن ثبت می‌شود تا
        # مدیرِ فروشگاه فوراً بفهمد و درگاهِ دیگری برای OTP انتخاب کند.
        log.status = SmsLog.Status.FAILED
        log.error_message = "درگاهِ اسمس‌راستی برای ارسالِ رمزِ یک‌بارمصرف مناسب نیست؛ درگاهِ دیگری برای این فروشگاه انتخاب کنید"
        log.save(update_fields=["status", "error_message", "updated_at"])
        return log
    result = backend.send(to=phone, text=message)
    log.attempt_count = 1
    if result.success:
        log.status = SmsLog.Status.SENT
        log.provider_ref_id = result.provider_ref_id
        log.sent_at = timezone.now()
        from .balance_service import deduct_credit

        deduct_credit(store=store)
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


class RetryNotEligibleError(Exception):
    """رکورد در وضعیتی نیست که بتوان دوباره تلاش کرد (فقط failed قابل retry است)."""


def retry_failed_log(*, log_id: int, store) -> SmsLog:
    """همان متنِ رندرشده‌ی قبلی را دوباره به backend فعلیِ Store می‌فرستد —
    قالب را دوباره رندر نمی‌کند (تنظیماتِ رویداد ممکن است از آن زمان تغییر
    کرده باشد، اما پیامی که کاربر انتظارش را داشته همانی است که در ابتدا
    ساخته شده). ``store`` فیلترِ Get_object_or_404-مانند است — یک Store
    هرگز نمی‌تواند لاگِ Store دیگر را retry کند."""
    try:
        log = SmsLog.objects.get(pk=log_id, store=store)
    except SmsLog.DoesNotExist as exc:
        raise RetryNotEligibleError("گزارشی با این شناسه برای این فروشگاه یافت نشد") from exc
    if log.status != SmsLog.Status.FAILED:
        raise RetryNotEligibleError("فقط پیامک‌های ناموفق قابل ارسالِ دوباره‌اند")

    backend = get_backend(store=store)
    if log.event_key == SmsEvent.OTP and isinstance(backend, SmsRastiBackend):
        log.error_message = "درگاهِ اسمس‌راستی برای ارسالِ رمزِ یک‌بارمصرف مناسب نیست؛ درگاهِ دیگری برای این فروشگاه انتخاب کنید"
        log.save(update_fields=["error_message", "updated_at"])
        return log

    result = backend.send(to=log.recipient, text=log.message)
    log.attempt_count += 1
    if result.success:
        log.status = SmsLog.Status.SENT
        log.provider_ref_id = result.provider_ref_id
        log.error_message = ""
        log.sent_at = timezone.now()
    else:
        log.status = SmsLog.Status.FAILED
        log.error_message = result.error_message
    log.save(update_fields=["status", "provider_ref_id", "error_message", "attempt_count", "sent_at", "updated_at"])
    return log


def retry_smsrasti_outbox_item(*, item_id: int, store) -> SmsOutboxItem:
    """آیتمِ ناموفقِ صفِ SmsRasti را دوباره ``pending`` می‌کند تا دستگاه در
    poll بعدی آن را claim کند — خودِ این تابع چیزی ارسال نمی‌کند."""
    try:
        item = SmsOutboxItem.objects.get(pk=item_id, store=store)
    except SmsOutboxItem.DoesNotExist as exc:
        raise RetryNotEligibleError("آیتمی با این شناسه برای این فروشگاه یافت نشد") from exc
    if item.status != SmsOutboxItem.Status.FAILED:
        raise RetryNotEligibleError("فقط آیتم‌های ناموفق قابل صف‌شدنِ دوباره‌اند")

    item.status = SmsOutboxItem.Status.PENDING
    item.error_message = ""
    item.claimed_at = None
    item.save(update_fields=["status", "error_message", "claimed_at", "updated_at"])
    return item
