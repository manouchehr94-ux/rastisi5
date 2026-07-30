"""ساختِ ``SubscriptionPaymentAttempt`` — هر Retry یک ردیفِ تازه (ADR-75/77).

این سرویس فقط تلاش را *می‌سازد*؛ تأییدِ پرداخت (علامت‌زدنِ succeeded و اعمالِ
پرداخت رویِ فاکتور) در ``confirmation_service`` انجام می‌شود، تراکنشی و
idempotent (ADR-77)."""

import secrets

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.core.services.audit_service import record_audit_event


class PaymentAttemptError(Exception):
    """خطای قابل‌نمایش هنگام ساختِ تلاشِ پرداخت."""


def _new_token() -> str:
    return secrets.token_urlsafe(24)[:40]


@transaction.atomic
def create_attempt(invoice, *, provider=None, idempotency_key="", actor=None, now=None):
    """یک تلاشِ پرداختِ تازه برایِ یک فاکتورِ قابلِ‌پرداخت می‌سازد. idempotent
    روی ``idempotency_key``. مبلغ/ارز از خودِ فاکتور می‌آید (نه از مرورگر)."""
    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if not locked.is_payable:
        raise PaymentAttemptError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")

    if idempotency_key:
        existing = SubscriptionPaymentAttempt.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
    else:
        idempotency_key = f"attempt-{locked.pk}-{secrets.token_hex(8)}"

    provider_code = provider or registry.active_provider_code()
    attempt_number = SubscriptionPaymentAttempt.objects.filter(invoice=locked).count() + 1

    attempt = SubscriptionPaymentAttempt.objects.create(
        store=locked.store, invoice=locked, provider=provider_code,
        status=SubscriptionPaymentAttempt.Status.CREATED,
        amount=locked.amount_due, currency=locked.currency,
        public_token=_new_token(), idempotency_key=idempotency_key,
        attempt_number=attempt_number, started_at=now,
    )
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.payment_attempt_created",
        object_type="SubscriptionPaymentAttempt", object_id=attempt.pk, object_label=attempt.public_token,
        after={"invoice": locked.number, "amount": str(attempt.amount), "provider": provider_code},
    )
    return attempt
