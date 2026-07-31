"""پل ورود از پرتال مالک به میزبان مجزای پنل مدیریت هر فروشگاه (ADR-98).

``SESSION_COOKIE_DOMAIN`` در این پروژه عمداً تنظیم نشده (کوکی‌های host-only)
— پس نشستِ واردشده‌ی مالک روی میزبان پرتال (مثلاً app.rastisi.ir) روی
میزبانِ متفاوتِ ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`` وجود
ندارد. این ماژول یک بلیتِ کوتاه‌عمر و یکبارمصرف می‌سازد که ویوی سمتِ
میزبانِ مدیریت (``apps.dashboard.views.consume_admin_handoff``) مصرف می‌کند
و بلافاصله ``login()`` واقعیِ جنگو را برای همان میزبان صدا می‌زند."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.stores.authorization import get_active_membership
from apps.stores.models import Store

from ..models import AdminHandoffTicket

TICKET_TTL_SECONDS = 60


class HandoffError(Exception):
    """صدور یا مصرفِ بلیتِ ورود به پنل مدیریت ممکن نیست."""


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
