"""ظ¾ظ„ ظˆط±ظˆط¯ ط§ط² ظ¾ط±طھط§ظ„ ظ…ط§ظ„ع© ط¨ظ‡ ظ…غŒط²ط¨ط§ظ† ظ…ط¬ط²ط§غŒ ظ¾ظ†ظ„ ظ…ط¯غŒط±غŒطھ ظ‡ط± ظپط±ظˆط´ع¯ط§ظ‡ (ADR-98).

``SESSION_COOKIE_DOMAIN`` ط¯ط± ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط¹ظ…ط¯ط§ظ‹ طھظ†ط¸غŒظ… ظ†ط´ط¯ظ‡ (ع©ظˆع©غŒâ€Œظ‡ط§غŒ host-only)
â€” ظ¾ط³ ظ†ط´ط³طھظگ ظˆط§ط±ط¯ط´ط¯ظ‡â€ŒغŒ ظ…ط§ظ„ع© ط±ظˆغŒ ظ…غŒط²ط¨ط§ظ† ظ¾ط±طھط§ظ„ (ظ…ط«ظ„ط§ظ‹ app.rastisi.ir) ط±ظˆغŒ
ظ…غŒط²ط¨ط§ظ†ظگ ظ…طھظپط§ظˆطھظگ ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`` ظˆط¬ظˆط¯
ظ†ط¯ط§ط±ط¯. ط§غŒظ† ظ…ط§عکظˆظ„ غŒع© ط¨ظ„غŒطھظگ ع©ظˆطھط§ظ‡â€Œط¹ظ…ط± ظˆ غŒع©ط¨ط§ط±ظ…طµط±ظپ ظ…غŒâ€Œط³ط§ط²ط¯ ع©ظ‡ ظˆغŒظˆغŒ ط³ظ…طھظگ
ظ…غŒط²ط¨ط§ظ†ظگ ظ…ط¯غŒط±غŒطھ (``apps.dashboard.views.consume_admin_handoff``) ظ…طµط±ظپ ظ…غŒâ€Œع©ظ†ط¯
ظˆ ط¨ظ„ط§ظپط§طµظ„ظ‡ ``login()`` ظˆط§ظ‚ط¹غŒظگ ط¬ظ†ع¯ظˆ ط±ط§ ط¨ط±ط§غŒ ظ‡ظ…ط§ظ† ظ…غŒط²ط¨ط§ظ† طµط¯ط§ ظ…غŒâ€Œط²ظ†ط¯."""

from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.stores.authorization import get_active_membership
from apps.stores.models import Store

from ..models import AdminHandoffTicket

TICKET_TTL_SECONDS = 600

#: Section 4 â€” how long a signed "return to Merchant Admin after central
#: login" token stays valid. Short window: this only needs to survive one
#: OTP round-trip, not a browsing session.
ADMIN_RETURN_TOKEN_MAX_AGE_SECONDS = 600
_ADMIN_RETURN_SALT = "portal.admin_return_token"


class HandoffError(Exception):
    """طµط¯ظˆط± غŒط§ ظ…طµط±ظپظگ ط¨ظ„غŒطھظگ ظˆط±ظˆط¯ ط¨ظ‡ ظ¾ظ†ظ„ ظ…ط¯غŒط±غŒطھ ظ…ظ…ع©ظ† ظ†غŒط³طھ."""


def build_admin_return_token(*, admin_subdomain: str, destination_path: str) -> str:
    """غŒع© طھظˆع©ظ†ظگ ط§ظ…ط¶ط§ط´ط¯ظ‡ (HMACطŒ ``django.core.signing``) ظ…غŒâ€Œط³ط§ط²ط¯ ع©ظ‡ ظ¾ط³ ط§ط² ظˆط±ظˆط¯ظگ
    ظ…ط±ع©ط²غŒطŒ ظ…ط³غŒط±ظگ ط¨ط§ط²ع¯ط´طھ ط¨ظ‡ ط¯ظ‚غŒظ‚ط§ظ‹ ظ‡ظ…غŒظ† (admin_subdomain, destination_path)
    ط±ط§ ط¨ط¯ظˆظ†ظگ ظ‚ط§ط¨ظ„ظگâ€Œط¯ط³طھع©ط§ط±غŒâ€Œط¨ظˆط¯ظ† ط­ظ…ظ„ ظ…غŒâ€Œع©ظ†ط¯ (Section 4).

    غŒع© URL ط®ط§ظ… ظ†غŒط³طھ â€” غŒع© payload ط§ظ…ط¶ط§ط´ط¯ظ‡ ط§ط³طھ â€” ظ¾ط³ ظ‡ط±ع¯ط² ظ†ظ…غŒâ€Œطھظˆط§ظ†ط¯ ط¨ظ‡ غŒع©
    ظ…ظ‚طµط¯ظگ ط¯ظ„ط®ظˆط§ظ‡ظگ ط¨غŒط±ظˆظ†غŒ (open redirect) ط§ط´ط§ط±ظ‡ ع©ظ†ط¯: ظ…طµط±ظپâ€Œع©ظ†ظ†ط¯ظ‡
    (``apps.portal.views``) ظ‡ظ…غŒط´ظ‡ ط®ظˆط¯ط´ ``https://{admin_subdomain}.
    {RASTISI_ADMIN_DOMAIN_SUFFIX}/...`` ط±ط§ ظ…غŒâ€Œط³ط§ط²ط¯طŒ ظ†ظ‡ ط§غŒظ†ع©ظ‡ غŒع© URL ط±ط§ ط§ط²
    طھظˆع©ظ† ظ…ط³طھظ‚غŒظ…ط§ظ‹ ط¨ط®ظˆط§ظ†ط¯."""
    signer = signing.TimestampSigner(salt=_ADMIN_RETURN_SALT)
    return signer.sign_object({"admin_subdomain": admin_subdomain, "destination_path": destination_path})


def decode_admin_return_token(token: str):
    """طھظˆع©ظ† ط±ط§ ط±ظ…ط²ع¯ط´ط§غŒغŒ ظ…غŒâ€Œع©ظ†ط¯ ط§ع¯ط± ظ…ط¹طھط¨ط±/طھط§ط²ظ‡ ط¨ط§ط´ط¯طŒ ظˆع¯ط±ظ†ظ‡ ``None`` â€”
    ظ‡ط±ع¯ط² Exception ظ¾ط±طھط§ط¨ ظ†ظ…غŒâ€Œع©ظ†ط¯ (ظˆط±ظˆط¯غŒظگ ع©ط§ط±ط¨ط± ط§ط³طھطŒ ظ‡ظ…غŒط´ظ‡ ظ…غŒâ€Œطھظˆط§ظ†ط¯ ظ†ط§ظ…ط¹طھط¨ط±
    ط¨ط§ط´ط¯)."""
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
    """ظپظ‚ط· ط¨ط±ط§غŒ (user, store)ط§غŒ ع©ظ‡ ط¹ط¶ظˆغŒطھظگ ظپط¹ط§ظ„ ط¯ط§ط±ط¯ ط¨ظ„غŒطھ طµط§ط¯ط± ظ…غŒâ€Œع©ظ†ط¯ â€”
    ظ‡ط±ع¯ط² ط¨ط±ط§غŒ ظپط±ظˆط´ع¯ط§ظ‡غŒ ع©ظ‡ ع©ط§ط±ط¨ط± ط¹ط¶ظˆط´ ظ†غŒط³طھ."""
    membership = get_active_membership(user, store)
    if membership is None:
        raise HandoffError("ط´ظ…ط§ ط¹ط¶ظˆظگ ظپط¹ط§ظ„ظگ ط§غŒظ† ظپط±ظˆط´ع¯ط§ظ‡ ظ†غŒط³طھغŒط¯")

    return AdminHandoffTicket.objects.create(
        user=user, store=store, destination_path=destination_path,
        expires_at=timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS),
    )


@transaction.atomic
def consume_ticket(token: str, *, store: Store):
    """ط¨ظ„غŒطھ ط±ط§ ط§طھظ…غŒع© ظ…غŒâ€Œط®ظˆط§ظ†ط¯ ظˆ ط¨ظ„ط§ظپط§طµظ„ظ‡ ظ…طµط±ظپâ€Œط´ط¯ظ‡ ط¹ظ„ط§ظ…طھ ظ…غŒâ€Œط²ظ†ط¯ (select_for_update
    طھط§ ط¯ظˆ ظ…طµط±ظپظگ ظ‡ظ…â€Œط²ظ…ط§ظ† ظ‡ط±ع©ط¯ط§ظ… غŒع© ظ†ط³ط®ظ‡â€ŒغŒ ظ‚ط¯غŒظ…غŒ ظ†ط®ظˆط§ظ†ظ†ط¯)طŒ ظˆ ع©ط§ط±ط¨ط±ظگ ظ…طھط¹ظ„ظ‚ ط¨ظ‡ ط¢ظ†
    ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯. ``store`` ط¨ط§غŒط¯ ط¯ظ‚غŒظ‚ط§ظ‹ ظ‡ظ…ط§ظ† Storeط§غŒ ط¨ط§ط´ط¯ ع©ظ‡ ط¨ظ„غŒطھ ط¨ط±ط§غŒط´
    طµط§ط¯ط± ط´ط¯ظ‡ â€” غŒع© ط¨ظ„غŒطھظگ ظپط±ظˆط´ع¯ط§ظ‡ظگ ط¯غŒع¯ط±طŒ ط­طھغŒ ظ…ط¹طھط¨ط± ظˆ ظ…طµط±ظپâ€Œظ†ط´ط¯ظ‡طŒ ط§غŒظ†ط¬ط§ ط±ط¯
    ظ…غŒâ€Œط´ظˆط¯. ط¨ظ„غŒطھظگ ظ†ط§ظ…ط¹طھط¨ط±/ظ…ظ†ظ‚ط¶غŒ/ظ…طµط±ظپâ€Œط´ط¯ظ‡/ظپط±ظˆط´ع¯ط§ظ‡ظگ ظ†ط§ط¯ط±ط³طھ None ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯."""
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

