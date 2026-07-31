"""اینترفیس انتزاعی ارسال پیامک و پیاده‌سازی‌ها.

افزودن ارائه‌دهنده‌ی جدید فقط یعنی یک زیرکلاس تازه از SmsBackend با متد send؛
sms_service.get_backend() بر اساس ShopSettings.sms_backend تصمیم می‌گیرد کدام
کلاس ساخته شود — بقیه‌ی سیستم هیچ‌وقت مستقیماً یک بک‌اند خاص را نمی‌شناسد.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class SmsSendResult:
    success: bool
    provider_ref_id: str = ""
    error_message: str = ""


class SmsBackend(ABC):
    @abstractmethod
    def send(self, *, to: str, text: str) -> SmsSendResult:
        """پیامک را ارسال می‌کند. هرگز نباید Exception پرتاب کند — همیشه SmsSendResult برمی‌گرداند."""


class ConsoleBackend(SmsBackend):
    """برای توسعه — پیامک واقعی ارسال نمی‌کند، فقط در لاگ ثبت می‌کند.

    در سطح DEBUG لاگ می‌شود، نه INFO — چون ``text`` می‌تواند شامل کد OTP یا
    سایر محتوای حساس رویداد باشد؛ INFO پیش‌فرض Production است (تنظیمات
    ``DJANGO_LOG_LEVEL``)، پس این پیام هرگز نباید در لاگ Production ظاهر
    شود. برای دیدنش در توسعه‌ی محلی ``DJANGO_LOG_LEVEL=DEBUG`` تنظیم کنید."""

    def send(self, *, to: str, text: str) -> SmsSendResult:
        logger.debug("[SMS:console] to=%s text=%s", to, text)
        return SmsSendResult(success=True, provider_ref_id="console")


class MelipayamakBackend(SmsBackend):
    """پیاده‌سازی واقعی ملی‌پیامک (REST API سرویس SendSMS)."""

    SEND_URL = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"

    def __init__(self, *, username: str, password: str, sender: str):
        self.username = username
        self.password = password
        self.sender = sender

    def send(self, *, to: str, text: str) -> SmsSendResult:
        if not self.username or not self.password or not self.sender:
            return SmsSendResult(success=False, error_message="تنظیمات اتصال ملی‌پیامک کامل نیست")

        import requests

        payload = {
            "username": self.username,
            "password": self.password,
            "to": to,
            "from": self.sender,
            "text": text,
            "isFlash": False,
        }
        try:
            response = requests.post(self.SEND_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # هیچ خطای شبکه/HTTP/JSON نباید جریان اصلی را بشکند
            logger.warning("melipayamak send failed: %s", exc)
            return SmsSendResult(success=False, error_message=str(exc))

        ref_id = str(data.get("Value", ""))
        # ملی‌پیامک کد وضعیت را در RetStatus برمی‌گرداند؛ ۱ یعنی ارسال موفق به صف.
        if data.get("RetStatus") == 1:
            return SmsSendResult(success=True, provider_ref_id=ref_id)
        return SmsSendResult(success=False, error_message=data.get("StrRetStatus", "خطای نامشخص ملی‌پیامک"))


class KavenegarBackend(SmsBackend):
    """پیاده‌سازی واقعی کاوه‌نگار (REST API ``sms/send``).

    برخلافِ پیاده‌سازیِ مرجع در ``reference_imports`` (که فقط نبودِ
    Exception را «موفقیت» می‌دانست)، اینجا ``return.status`` واقعیِ پاسخ
    بررسی می‌شود — کاوه‌نگار حتیِ خطاهایی مثلِ کلید نامعتبر یا گیرنده‌ی
    نامعتبر را هم با بدنه‌ی JSON معتبر برمی‌گرداند، نه یک Exception."""

    SEND_URL_TEMPLATE = "https://api.kavenegar.com/v1/{api_key}/sms/send.json"

    def __init__(self, *, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    def send(self, *, to: str, text: str) -> SmsSendResult:
        if not self.api_key or not self.sender:
            return SmsSendResult(success=False, error_message="تنظیمات اتصال کاوه‌نگار کامل نیست")

        import requests

        url = self.SEND_URL_TEMPLATE.format(api_key=self.api_key)
        payload = {"receptor": to, "sender": self.sender, "message": text}
        try:
            response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            data = response.json()
        except Exception as exc:  # هیچ خطای شبکه/HTTP/JSON نباید جریان اصلی را بشکند
            # کلیدِ API بخشی از خودِ URL است — پیامِ کتابخانه‌ی requests (مثلِ
            # ConnectionError) معمولاً URL کامل را در متنِ خطا می‌آورد؛ پیش از
            # لاگ‌کردن یا برگرداندن، حتماً باید حذف شود.
            safe_message = str(exc).replace(self.api_key, "***")
            logger.warning("kavenegar send failed: %s", safe_message)
            return SmsSendResult(success=False, error_message=safe_message)

        status = (data.get("return") or {}).get("status")
        if status == 200:
            entries = data.get("entries") or [{}]
            ref_id = str(entries[0].get("messageid", ""))
            return SmsSendResult(success=True, provider_ref_id=ref_id)
        error_message = (data.get("return") or {}).get("message", "خطای نامشخص کاوه‌نگار")
        return SmsSendResult(success=False, error_message=error_message)


class SmsRastiBackend(SmsBackend):
    """گیت‌وی اندرویدِ SmsRasti — Store-scoped، هرگز برایِ OTP هویتِ
    مالک/کارمندِ پلتفرم استفاده نمی‌شود (``apps.portal.services.
    owner_sms_service`` اصلاً موردی برایِ این backend ندارد، پس حتی با
    تنظیمِ اشتباهِ env هم قابلِ انتخاب نیست).

    ارسال اینجا sync نیست: پیام در صفِ ``SmsOutboxItem`` همان Store ذخیره
    می‌شود و بعداً با poll/ack دستگاهِ اندروید وضعیتِ واقعی مشخص می‌شود؛
    ``success=True`` اینجا فقط یعنی «با موفقیت صف شد»، نه «تحویل داده شد»
    — دقیقاً مثلِ رفتارِ فرستنده‌های sync دیگر که success یعنی «درگاه
    پذیرفت»، نه «تضمینِ تحویل»."""

    def __init__(self, *, store, device_token: str):
        self.store = store
        self.device_token = device_token

    def send(self, *, to: str, text: str) -> SmsSendResult:
        if not self.device_token:
            return SmsSendResult(success=False, error_message="دستگاه اسمس‌راستی برای این فروشگاه پیکربندی نشده است")

        from ..models import SmsOutboxItem

        item = SmsOutboxItem.objects.create(store=self.store, phone=to, message=text)
        return SmsSendResult(success=True, provider_ref_id=str(item.pk))
