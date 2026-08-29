"""بازیابیِ رمزِ عبور با موبایل+OTP (تکمیلِ احرازِ هویتِ مالک، پس از Batch 1).

عمداً جدا از ``step_up_service`` است، هرچند الگویِ مجوزِ کوتاه‌مدت/تک‌مصرف/
سمت‌سرور را از همان‌جا وام گرفته: تفاوتِ کلیدی این‌ست که تأییدِ OTP اینجا
هرگز ``auth_login()`` صدا نمی‌زند و هرگز معنایِ «این کاربر واردِ حساب شد»
ندارد — فقط یک مجوزِ محدود «اکنون اجازه داری رمزِ همین کاربرِ مشخص را عوض
کنی» در نشست ثبت می‌کند. اگر این را با ``step_up_service`` یکی می‌کردیم،
یک تأییدِ بازیابیِ رمز می‌توانست به اشتباه به‌عنوانِ تأییدِ یک عملیاتِ حساسِ
دیگر (یا برعکس) خوانده شود — وضعیتِ امنیتیِ مبهم که صراحتاً باید نبود.

Enumeration-safety: ``request_reset_otp`` برایِ شماره‌ی ناشناس یا
غیرفعال، هیچ ``OwnerOtpChallenge``ای نمی‌سازد و هیچ پیامکی ارسال
نمی‌کند — اما همان خروجیِ «شماره‌ی معتبر پذیرفته شد» را برمی‌گرداند که
برایِ شماره‌ی شناخته‌شده/فعال برمی‌گرداند؛ تماس‌گیرنده (ویو) همیشه همان
صفحه‌ی تأیید را نشان می‌دهد، صرف‌نظر از این‌که شماره واقعاً حساب دارد یا نه.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.portal.models import OwnerOtpChallenge, OwnerProfile
from apps.portal.services import owner_otp_service
from apps.portal.services.owner_otp_service import OtpRateLimitError  # re-exported for callers

User = get_user_model()

_SESSION_PENDING_PHONE_KEY = "portal_mobile_reset_pending_phone"
_SESSION_AUTHORIZED_KEY = "portal_mobile_reset_authorized"
AUTHORIZED_TTL_SECONDS = 900


def request_reset_otp(*, phone_raw: str, client_ip: str) -> tuple[str | None, str | None]:
    """شماره را نرمال می‌کند؛ در صورتِ نامعتبربودنِ فرمت، خطایِ نمایش‌پذیر
    برمی‌گرداند (این یکی enumeration نیست — فرمِ فرمت مستقلِ وجودِ حساب
    است، دقیقاً مثلِ رفتارِ ``_request_otp_and_go_to_verify``ی ورود/
    ثبت‌نام). وگرنه ``(phone, None)`` برمی‌گرداند — برایِ شماره‌ی ناشناس/
    غیرفعال بی‌صدا هیچ کدی نمی‌سازد/نمی‌فرستد، ولی خروجی یکسان می‌ماند."""
    try:
        phone = normalize_iranian_phone(phone_raw)
    except InvalidPhoneError as exc:
        return None, str(exc.messages[0] if exc.messages else exc)

    profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
    if profile is not None and profile.user.is_active:
        try:
            owner_otp_service.request_otp(
                phone=phone, purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET, client_ip=client_ip,
            )
        except owner_otp_service.OtpRateLimitError:
            # همان الزامِ enumeration-safe: حتی «این شماره به سقفِ درخواست
            # رسیده» نباید از «این شماره اصلاً وجود ندارد» قابلِ تشخیص
            # باشد — بی‌صدا نادیده گرفته می‌شود، خروجیِ ویو برای هر دو یکی است.
            pass
    return phone, None


def begin_pending(request, *, phone: str) -> None:
    request.session[_SESSION_PENDING_PHONE_KEY] = phone
    request.session.modified = True


def pending_phone(request) -> str | None:
    return request.session.get(_SESSION_PENDING_PHONE_KEY)


def clear_pending(request) -> None:
    request.session.pop(_SESSION_PENDING_PHONE_KEY, None)
    request.session.modified = True


def verify_reset_otp(request, *, phone: str, code: str) -> bool:
    """کد را تأیید می‌کند. هرگز واردِ حساب نمی‌کند. در موفقیت، مجوزِ
    کوتاه‌مدت را برایِ کاربری که خودش (نه ورودیِ کاربر) از رویِ
    ``OwnerProfile.phone`` پیدا می‌کند، در نشست ثبت می‌کند."""
    ok = owner_otp_service.verify_otp(
        phone=phone, purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET, code=code,
    )
    if not ok:
        return False

    profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
    if profile is None or not profile.user.is_active:
        # عملاً رخ نمی‌دهد — request_reset_otp برایِ چنین شماره‌ای هرگز
        # OTP واقعی نساخته، پس verify_otp بالا همیشه False می‌داد؛ این فقط
        # یک محافظِ دفاعی-در-عمق است.
        return False

    request.session[_SESSION_AUTHORIZED_KEY] = {
        "user_id": profile.user_id,
        "expires_at": timezone.now().timestamp() + AUTHORIZED_TTL_SECONDS,
    }
    request.session.modified = True
    return True


def get_authorized_user(request):
    """کاربرِ مجاز برایِ تغییرِ رمز را فقط از رویِ وضعیتِ سمتِ‌سرورِ نشست
    برمی‌گرداند — هرگز از رویِ یک شناسه‌ی ورودیِ کاربر. مجوزِ منقضی‌شده یا
    کاربرِ اکنون غیرفعال، هر دو ``None``."""
    entry = request.session.get(_SESSION_AUTHORIZED_KEY)
    if not entry:
        return None
    if timezone.now().timestamp() >= entry.get("expires_at", 0):
        return None
    user = User.objects.filter(pk=entry["user_id"]).first()
    if user is None or not user.is_active:
        return None
    return user


def clear_authorization(request) -> None:
    request.session.pop(_SESSION_AUTHORIZED_KEY, None)
    request.session.modified = True
