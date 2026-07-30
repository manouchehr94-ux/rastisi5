"""صدور/ابطالِ Credit Note (ADR-81). یک سندِ تاریخی؛ مبلغش نمی‌تواند از مبلغِ
پرداخت‌شده‌ی واجدِ‌شرایط (پس از کسرِ Credit Noteهایِ صادرشده‌ی قبلی) بیشتر
باشد. به‌خودیِ‌خود پول بازنمی‌گرداند."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import SubscriptionCreditNote, SubscriptionInvoice
from apps.billing.services import numbering_service
from apps.core.services.audit_service import record_audit_event

ZERO = Decimal("0")


class CreditNoteError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ Credit Note."""


def issued_total(invoice) -> Decimal:
    agg = invoice.credit_notes.filter(
        status=SubscriptionCreditNote.Status.ISSUED,
    ).aggregate(s=Sum("amount"))
    return agg["s"] or ZERO


def eligible_amount(invoice) -> Decimal:
    """مبلغی که هنوز می‌توان برایش Credit Note صادر کرد."""
    return max(invoice.amount_paid - issued_total(invoice), ZERO)


@transaction.atomic
def issue_credit_note(invoice, *, amount, reason="", actor=None, now=None):
    """یک Credit Noteِ صادرشده می‌سازد. مبلغ باید > 0 و ≤ مبلغِ واجدِ‌شرایط باشد."""
    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    amount = Decimal(amount)
    if amount <= ZERO:
        raise CreditNoteError("مبلغِ Credit Note باید بزرگ‌تر از صفر باشد.")
    if amount > eligible_amount(locked):
        raise CreditNoteError("مبلغِ Credit Note از مبلغِ پرداخت‌شده‌ی واجدِ‌شرایط بیشتر است.")

    credit_note = SubscriptionCreditNote.objects.create(
        store=locked.store, invoice=locked, number=numbering_service.next_credit_note_number(now=now),
        status=SubscriptionCreditNote.Status.ISSUED, reason=reason, currency=locked.currency,
        amount=amount, issued_at=now, actor=actor,
    )
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.credit_note_issued",
        object_type="SubscriptionCreditNote", object_id=credit_note.pk, object_label=credit_note.number,
        after={"amount": str(amount), "invoice": locked.number},
    )
    return credit_note


@transaction.atomic
def void_credit_note(credit_note, *, actor=None, now=None):
    """یک Credit Noteِ صادرشده را باطل می‌کند (idempotent روی حالتِ void)."""
    locked = SubscriptionCreditNote.objects.select_for_update().get(pk=credit_note.pk)
    if locked.status == SubscriptionCreditNote.Status.VOID:
        return locked
    now = now or timezone.now()
    locked.status = SubscriptionCreditNote.Status.VOID
    locked.voided_at = now
    locked.save(update_fields=["status", "voided_at", "updated_at"])
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.credit_note_voided",
        object_type="SubscriptionCreditNote", object_id=locked.pk, object_label=locked.number,
    )
    return locked
