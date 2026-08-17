"""اینترفیس انتزاعی ارسال پیامک و پیاده‌سازی‌ها.

افزودن ارائه‌دهنده‌ی جدید فقط یعنی یک زیرکلاس تازه از SmsBackend با متد send؛
sms_service.get_backend() بر اساس ShopSettings.sms_backend تصمیم می‌گیرد کدام
کلاس ساخته شود — بقیه‌ی سیستم هیچ‌وقت مستقیماً یک بک‌اند خاص را نمی‌شناسد.
"""

import logging

from abc import ABC, abstractmethod
from dataclasses import dataclass
from django.conf import settings
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class SmsSendResult:
    success: bool
    provider_ref_id: str = ""
    error_message: str = ""
    provider: str = ""


class SmsBackend(ABC):
    @abstractmethod
    def send(self, *, to: str, text: str) -> SmsSendResult:
        """پیامک را ارسال می‌کند. هرگز نباید Exception پرتاب کند — همیشه SmsSendResult برمی‌گرداند."""


class UnavailableBackend(SmsBackend):
    """Provider انتخاب شده ولی غیرفعال/غیرقابل استفاده است؛ هرگز fake-success نمی‌دهد."""

    def __init__(self, *, provider_code: str, error_message: str):
        self.provider_code = provider_code
        self.error_message = error_message

    def send(self, *, to: str, text: str) -> SmsSendResult:
        return SmsSendResult(
            success=False, error_message=self.error_message, provider=self.provider_code,
        )


class ConsoleBackend(SmsBackend):
    provider_code = "console"
    """Backend غیرواقعی برای تست/توسعه.

    قانون امنیتی سخت: متن پیام (که ممکن است OTP باشد) نه چاپ می‌شود و نه
    حتی در DEBUG log می‌شود. فقط متادیتای غیرحساس ثبت می‌شود.
    """

    def send(self, *, to: str, text: str) -> SmsSendResult:
        logger.debug(
            "[SMS:console] suppressed real send: to=%s chars=%s",
            to, len(text or ""),
        )
        return SmsSendResult(success=True, provider_ref_id="console")


class MelipayamakBackend(SmsBackend):
    provider_code = "melipayamak"
    """ملی‌پیامک: ارسال متنی + Pattern/BodyId خدماتی برای هر رویداد پیکربندی‌شده."""

    SEND_URL = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
    PATTERN_URL = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"

    def __init__(self, *, username: str, password: str, sender: str):
        self.username = username
        self.password = password
        self.sender = sender

    @staticmethod
    def _pattern_text(variables: dict, variables_order: str) -> str:
        order = [
            item.strip()
            for item in str(variables_order or "").replace(";", ",").split(",")
            if item.strip()
        ]
        if not order:
            order = ["otp_code"]
        return ";".join(str(variables.get(key, "")) for key in order)

    def send_pattern(
        self, *, to: str, body_id: str, variables: dict,
        variables_order: str = "otp_code",
    ) -> SmsSendResult:
        """ارسال خدماتی BaseServiceNumber بدون افشای OTP در log."""
        if not self.username or not self.password:
            return SmsSendResult(
                success=False,
                error_message="نام کاربری/رمز ملی‌پیامک برای Pattern کامل نیست",
            )
        body_id = str(body_id or "").strip()
        if not body_id.isdigit():
            return SmsSendResult(
                success=False,
                error_message="BodyId الگوی ملی‌پیامک تنظیم نشده یا نامعتبر است",
            )
        if not to:
            return SmsSendResult(success=False, error_message="شماره گیرنده خالی است")

        import requests

        payload = {
            "username": self.username,
            "password": self.password,
            "text": self._pattern_text(variables, variables_order),
            "to": to,
            "bodyId": int(body_id),
        }
        try:
            response = requests.post(
                self.PATTERN_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning(
                "melipayamak pattern send failed: to=%s error=%s", to, exc,
            )
            return SmsSendResult(success=False, error_message=str(exc))

        if data.get("RetStatus") == 1:
            return SmsSendResult(
                success=True, provider_ref_id=str(data.get("Value", "")),
            )
        value = str(data.get("Value", ""))
        message = data.get("StrRetStatus") or "خطای نامشخص ملی‌پیامک"
        return SmsSendResult(
            success=False,
            error_message=f"{value}: {message}" if value else str(message),
        )

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
    provider_code = "kavenegar"
    """کاوه‌نگار: ارسال متنی + VerifyLookup برای OTP رزرو.

    برخلافِ پیاده‌سازیِ مرجع در ``reference_imports`` (که فقط نبودِ
    Exception را «موفقیت» می‌دانست)، اینجا ``return.status`` واقعیِ پاسخ
    بررسی می‌شود — کاوه‌نگار حتیِ خطاهایی مثلِ کلید نامعتبر یا گیرنده‌ی
    نامعتبر را هم با بدنه‌ی JSON معتبر برمی‌گرداند، نه یک Exception."""

    SEND_URL_TEMPLATE = "https://api.kavenegar.com/v1/{api_key}/sms/send.json"
    VERIFY_URL_TEMPLATE = "https://api.kavenegar.com/v1/{api_key}/verify/lookup.json"

    def __init__(self, *, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    def send_verify_lookup(self, *, to: str, token: str, template: str) -> SmsSendResult:
        """OTP رزرو با VerifyLookup؛ sender لازم نیست."""
        if not self.api_key or not template:
            return SmsSendResult(
                success=False,
                error_message="کلید API/Template کاوه‌نگار برای OTP کامل نیست",
            )
        import requests

        url = self.VERIFY_URL_TEMPLATE.format(api_key=self.api_key)
        payload = {"receptor": to, "token": str(token), "template": template}
        try:
            response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            data = response.json()
        except Exception as exc:
            safe_message = str(exc).replace(self.api_key, "***")
            logger.warning(
                "kavenegar VerifyLookup failed: to=%s error=%s", to, safe_message,
            )
            return SmsSendResult(success=False, error_message=safe_message)

        status = (data.get("return") or {}).get("status")
        if status == 200:
            entries = data.get("entries") or [{}]
            return SmsSendResult(
                success=True,
                provider_ref_id=str(entries[0].get("messageid", "")),
            )
        return SmsSendResult(
            success=False,
            error_message=(data.get("return") or {}).get(
                "message", "خطای نامشخص کاوه‌نگار"
            ),
        )

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
    provider_code = "smsrasti"
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
