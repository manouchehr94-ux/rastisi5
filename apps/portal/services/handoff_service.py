"""پل ورود از پرتال مالک به میزبان مجزای پنل مدیریت هر فروشگاه (ADR-98).

``SESSION_COOKIE_DOMAIN`` در این پروژه عمداً تنظیم نشده (کوکی‌های host-only)
— پس نشستِ واردشده‌ی مالک روی میزبان پرتال (مثلاً app.rastisi.ir) روی
میزبانِ متفاوتِ ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`` وجود
ندارد. این ماژول یک بلیتِ کوتاه‌عمر و یکبارمصرف می‌سازد که ویوی سمتِ
میزبانِ مدیریت (``apps.dashboard.views.consume_admin_handoff``) مصرف می‌کند
و بلافاصله ``login()`` واقعیِ جنگو را برای همان میزبان صدا می‌زند."""

from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.stores.authorization import get_active_membership
from apps.stores.models import Store

from ..models import AdminHandoffTicket

TICKET_TTL_SECONDS = 60

#: Section 4 — how long a signed "return to Merchant Admin after central
#: login" token stays valid. Short window: this only needs to survive one
#: OTP round-trip, not a browsing session.
ADMIN_RETURN_TOKEN_MAX_AGE_SECONDS = 600
_ADMIN_RETURN_SALT = "portal.admin_return_token"


class HandoffError(Exception):
    """صدور یا مصرفِ بلیتِ ورود به پنل مدیریت ممکن نیست."""


def build_admin_return_token(*, admin_subdomain: str, destination_path: str) -> str:
    """یک توکنِ امضاشده (HMAC، ``django.core.signing``) می‌سازد که پس از ورودِ
    مرکزی، مسیرِ بازگشت به دقیقاً همین (admin_subdomain, destination_path)
    را بدونِ قابلِ‌دستکاری‌بودن حمل می‌کند (Section 4).

    یک URL خام نیست — یک payload امضاشده است — پس هرگز نمی‌تواند به یک
    مقصدِ دلخواهِ بیرونی (open redirect) اشاره کند: مصرف‌کننده
    (``apps.portal.views``) همیشه خودش ``https://{admin_subdomain}.
    {RASTISI_ADMIN_DOMAIN_SUFFIX}/...`` را می‌سازد، نه اینکه یک URL را از
    توکن مستقیماً بخواند."""
    signer = signing.TimestampSigner(salt=_ADMIN_RETURN_SALT)
    return signer.sign_object({"admin_subdomain": admin_subdomain, "destination_path": destination_path})


def decode_admin_return_token(token: str):
    """توکن را رمزگشایی می‌کند اگر معتبر/تازه باشد، وگرنه ``None`` —
    هرگز Exception پرتاب نمی‌کند (ورودیِ کاربر است، همیشه می‌تواند نامعتبر
    باشد)."""
    signer = signing.TimestampSigner(salt=_ADMIN_RETURN_SALT)
    try:
        payload = signer.unsign_object(token, max_age=ADMIN_RETURN_TOKEN_MAX_AGE_SECONDS)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    admin_subdomain = payload.get("admin_subdomain")
    destination_path = payload.get("destination_path")
    if not admin_subdomain or not destination_path or not destination_path.startswith("/admin-portal/"):
        return None
    return admin_subdomain, destination_path


def issue_ticket(*, user, store: Store, destination_path: str = "/admin-portal/") -> AdminHandoffTicket:
    """فقط برای (user, store)ای که عضویتِ فعال دارد بلیت صادر می‌کند —
    هرگز برای فروشگاهی که کاربر عضوش نیست."""
    membership = get_active_membership(user, store)
    if membership is None:
        raise HandoffError("شما عضوِ فعالِ این فروشگاه نیستید")

    return AdminHandoffTicket.objects.create(
        user=user, store=store, destination_path=destination_path,
        expires_at=timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS),
    )


@transaction.atomic
def consume_ticket(token: str, *, store: Store):
    """بلیت را اتمیک می‌خواند و بلافاصله مصرف‌شده علامت می‌زند (select_for_update
    تا دو مصرفِ هم‌زمان هرکدام یک نسخه‌ی قدیمی نخوانند)، و کاربرِ متعلق به آن
    را برمی‌گرداند. ``store`` باید دقیقاً همان Storeای باشد که بلیت برایش
    صادر شده — یک بلیتِ فروشگاهِ دیگر، حتی معتبر و مصرف‌نشده، اینجا رد
    می‌شود. بلیتِ نامعتبر/منقضی/مصرف‌شده/فروشگاهِ نادرست None برمی‌گرداند."""
    ticket = (
        AdminHandoffTicket.objects.select_for_update()
        .select_related("user", "store")
        .filter(token=token, store=store)
        .first()
    )
    if ticket is None or not ticket.is_usable:
        return None

    ticket.consumed_at = timezone.now()
    ticket.save(update_fields=["consumed_at", "updated_at"])
    return ticket.user, ticket.destination_path
