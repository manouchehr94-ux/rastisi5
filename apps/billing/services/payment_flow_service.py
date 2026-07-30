"""جریانِ hosted-payment و پردازشِ رخدادِ Webhookِ تأییدشده (ADR-77).

- ``start_payment``: یک تلاش می‌سازد، جلسه‌ی Provider را ایجاد و فاکتور را به
  ``payment_pending`` می‌برد، سپس اطلاعاتِ redirect را برمی‌گرداند.
- ``process_webhook_event``: یک ``BillingWebhookEvent`` تأییدشده را به
  ``confirmation_service`` وصل می‌کند (idempotent). بازگشتِ مرورگر هرگز مدرکِ
  پرداخت نیست — فقط این مسیر یا اقدامِ صریحِ مدیر پرداخت را تأیید می‌کند."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingWebhookEvent,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.providers import registry
from apps.billing.services import attempt_service, webhook_service
from apps.billing.services.confirmation_service import ConfirmationError, confirm_payment


class PaymentFlowError(Exception):
    """خطای قابل‌نمایش هنگام شروعِ پرداخت."""


@transaction.atomic
def start_payment(invoice, *, return_url, actor=None, idempotency_key="", now=None):
    """یک تلاشِ پرداخت و جلسه‌ی Provider برایِ یک فاکتورِ قابلِ‌پرداخت می‌سازد و
    فاکتور را به ``payment_pending`` می‌برد. ``(attempt, session)`` را برمی‌گرداند."""
    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if not locked.is_payable:
        raise PaymentFlowError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")

    attempt = attempt_service.create_attempt(locked, idempotency_key=idempotency_key, actor=actor, now=now)
    provider = registry.get_provider(attempt.provider)
    session = provider.create_payment_session(attempt=attempt, invoice=locked, return_url=return_url)

    attempt.provider_session_id = session.session_id
    attempt.status = SubscriptionPaymentAttempt.Status.PENDING
    attempt.save(update_fields=["provider_session_id", "status", "updated_at"])

    if locked.status in (SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAST_DUE):
        locked.status = SubscriptionInvoice.Status.PAYMENT_PENDING
        locked.save(update_fields=["status", "updated_at"])
    return attempt, session


def process_webhook_event(event, *, actor=None, now=None):
    """یک رخدادِ Webhookِ ذخیره‌شده (امضا-تأییدشده) را پردازش می‌کند. idempotent:
    رخدادِ از قبل پردازش‌شده دوباره اعمال نمی‌شود."""
    now = now or timezone.now()
    if event.processing_status == BillingWebhookEvent.ProcessingStatus.PROCESSED:
        return event

    payload = event.sanitized_payload or {}
    event_type = event.event_type or payload.get("event_type", "")
    if event_type != "payment.succeeded":
        # رخدادِ غیرِ موفقیت — ثبت به‌عنوانِ نادیده‌گرفته‌شده (بدونِ تغییرِ مالی).
        event.processing_status = BillingWebhookEvent.ProcessingStatus.IGNORED
        event.processed_at = now
        event.save(update_fields=["processing_status", "processed_at", "updated_at"])
        return event

    session_id = str(payload.get("session_id", ""))
    provider_payment_id = str(payload.get("provider_payment_id", ""))
    currency = str(payload.get("currency", ""))
    try:
        amount = Decimal(str(payload.get("amount", "")))
    except (InvalidOperation, ValueError):
        return webhook_service.mark_failed(event, error="مبلغِ رخداد نامعتبر است.", now=now)

    attempt = SubscriptionPaymentAttempt.objects.filter(
        provider=event.provider, provider_session_id=session_id,
    ).first()
    if attempt is None:
        return webhook_service.mark_failed(event, error="تلاشِ پرداختِ مرتبط یافت نشد.", now=now)

    event.related_payment_attempt = attempt
    event.related_invoice_id = attempt.invoice_id
    event.save(update_fields=["related_payment_attempt", "related_invoice", "updated_at"])

    try:
        confirm_payment(
            attempt=attempt, amount=amount, currency=currency,
            provider_payment_id=provider_payment_id, actor=actor, now=now,
        )
    except ConfirmationError as exc:
        return webhook_service.mark_failed(event, error=str(exc), now=now)
    return webhook_service.mark_processed(event, now=now)
