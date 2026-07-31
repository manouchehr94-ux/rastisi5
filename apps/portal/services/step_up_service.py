"""تأییدِ گام‌دومی (step-up OTP) برایِ عملیاتِ حساس (Section 10).

هر عملیاتِ حساس یک ``action`` از ``apps.portal.models.STEP_UP_ACTION_KEYS``
و یک ``target`` (معمولاً ``store.public_id``ی همان Store) دارد.
``PlatformConfiguration.step_up_actions`` تعیین می‌کند کدام عملیات نیازِ
تأییدِ گام‌دوم دارند (ADR-102). تأییدِ موفق در ``request.session`` با یک
انقضایِ کوتاه ذخیره می‌شود — نه یک کوکیِ دائمی، و نه یک فلگِ سراسری: فقط
همان (action, target) تا زمانِ انقضا معتبر است، پس تأییدِ خریدِ یک Store
هرگز عملیاتِ حساسِ Storeی دیگر را باز نمی‌کند.

فقط ``subscription_purchase_confirm`` تا این مرحله واقعاً به یک ویو وصل
شده (Section 9)؛ بقیه‌ی کلیدهایِ ``STEP_UP_ACTION_CHOICES`` هنوز ویوی
مربوطه‌شان ساخته نشده (Section 11/12/14/15) — همین سرویس، بدونِ تغییر،
برایِ آن‌ها هم قابلِ استفاده خواهد بود."""

from django.utils import timezone

from apps.portal.models import OwnerOtpChallenge
from apps.portal.services import owner_otp_service
from apps.portal.services.owner_otp_service import OtpRateLimitError  # re-exported for callers
from apps.portal.services.platform_config_service import get_platform_configuration

_SESSION_VERIFIED_KEY = "portal_step_up_verified"
_SESSION_PENDING_KEY = "portal_step_up_pending"
VERIFIED_TTL_SECONDS = 900


def is_step_up_required(action: str) -> bool:
    config = get_platform_configuration()
    return bool(config.step_up_actions.get(action, False))


def is_verified(request, *, action: str, target: str = "") -> bool:
    """آیا (action, target) در همین نشست، اخیراً با موفقیت تأیید شده؟"""
    entry = request.session.get(_SESSION_VERIFIED_KEY, {}).get(f"{action}:{target}")
    if not entry:
        return False
    return timezone.now().timestamp() < entry.get("expires_at", 0)


def _mark_verified(request, *, action: str, target: str) -> None:
    verified = request.session.get(_SESSION_VERIFIED_KEY, {})
    verified[f"{action}:{target}"] = {"expires_at": timezone.now().timestamp() + VERIFIED_TTL_SECONDS}
    request.session[_SESSION_VERIFIED_KEY] = verified
    request.session.modified = True


def begin_challenge(request, *, action: str, target: str, phone: str, message: str, client_ip: str) -> None:
    """کدِ تأیید می‌فرستد و قصدِ در-انتظارِ همین (action, target, phone) را
    در نشست ذخیره می‌کند تا ویوی تأیید بداند چه چیزی را دارد تأیید می‌کند —
    کاربر خودش هیچ‌کدام از این مقادیر را در فرم ارسال نمی‌کند (غیرِ قابلِ
    دستکاری)."""
    owner_otp_service.request_otp(
        phone=phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP, client_ip=client_ip, message=message,
    )
    request.session[_SESSION_PENDING_KEY] = {"action": action, "target": target, "phone": phone}
    request.session.modified = True


def pending_challenge(request) -> dict | None:
    return request.session.get(_SESSION_PENDING_KEY)


def confirm_challenge(request, *, code: str) -> bool:
    """کدِ واردشده را برایِ همان چالشِ در-انتظارِ همین نشست تأیید می‌کند. در
    موفقیت، (action, target) را تأییدشده علامت می‌زند و چالشِ در-انتظار را
    پاک می‌کند."""
    pending = request.session.get(_SESSION_PENDING_KEY)
    if not pending:
        return False
    ok = owner_otp_service.verify_otp(phone=pending["phone"], purpose=OwnerOtpChallenge.Purpose.STEP_UP, code=code)
    if not ok:
        return False
    _mark_verified(request, action=pending["action"], target=pending["target"])
    del request.session[_SESSION_PENDING_KEY]
    request.session.modified = True
    return True
