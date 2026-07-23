"""لایه‌ی سرویس کد یکبار مصرف (OTP) — تولید، محدودیت نرخ، و تأیید.

مطابق خواسته: انقضای ۲ دقیقه، حداکثر ۳ درخواست در ۱۰ دقیقه برای هر شماره (تا
اسپم/حدس‌زدن ممکن نباشد)، و محدودیت تعداد تلاش تأیید برای هر کد.
"""

import secrets
from datetime import timedelta

from django.utils import timezone

from ..events import SmsEvent
from ..models import OtpCode
from .sms_service import send_event_sms

OTP_LENGTH = 6
OTP_TTL_SECONDS = 120
MAX_REQUESTS_PER_WINDOW = 3
REQUEST_WINDOW_SECONDS = 600
MAX_VERIFY_ATTEMPTS = 5


class OtpRateLimitError(Exception):
    """تعداد درخواست کد برای این شماره در بازه‌ی زمانی اخیر بیش از حد مجاز بوده است."""


class OtpInvalidError(Exception):
    """کد وارد‌شده معتبر/صحیح نیست."""


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def request_otp(phone: str) -> OtpCode:
    """کد جدید می‌سازد و پیامک می‌کند؛ اگر تعداد درخواست‌های اخیر بیش از حد باشد خطا می‌دهد."""
    window_start = timezone.now() - timedelta(seconds=REQUEST_WINDOW_SECONDS)
    recent_count = OtpCode.objects.filter(phone=phone, created_at__gte=window_start).count()
    if recent_count >= MAX_REQUESTS_PER_WINDOW:
        raise OtpRateLimitError("تعداد درخواست کد بیش از حد مجاز است؛ چند دقیقه‌ی دیگر دوباره تلاش کنید")

    code = _generate_code()
    otp = OtpCode.objects.create(
        phone=phone, code=code, expires_at=timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
    )
    send_event_sms(SmsEvent.OTP, phone, {"otp_code": code})
    return otp


def verify_otp(phone: str, code: str) -> OtpCode:
    """آخرین کد مصرف‌نشده‌ی این شماره را با کد ورودی مقایسه می‌کند؛ در صورت تأیید، مصرف‌شده علامت می‌زند."""
    otp = OtpCode.objects.filter(phone=phone, is_used=False).order_by("-created_at").first()
    if otp is None:
        raise OtpInvalidError("کدی برای این شماره یافت نشد؛ ابتدا درخواست کد کنید")

    if otp.expires_at < timezone.now():
        raise OtpInvalidError("کد منقضی شده است؛ کد جدید درخواست کنید")

    if otp.attempt_count >= MAX_VERIFY_ATTEMPTS:
        raise OtpInvalidError("تعداد تلاش برای این کد بیش از حد مجاز است؛ کد جدید درخواست کنید")

    otp.attempt_count += 1
    otp.save(update_fields=["attempt_count", "updated_at"])

    if otp.code != code.strip():
        raise OtpInvalidError("کد وارد‌شده صحیح نیست")

    otp.is_used = True
    otp.save(update_fields=["is_used", "updated_at"])
    return otp
