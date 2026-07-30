"""تأییدِ تراکنشیِ پرداختِ اشتراک (ADR-77).

تنها مسیرِ مجاز برایِ «پرداخت انجام شد» — نه در View. قفلِ تلاش و فاکتور،
بررسیِ مبلغ/ارز/Provider، علامتِ یک‌بارِ موفقیت، اعمالِ یک‌بارِ پرداخت، پرداخت‌
شدنِ فاکتور، فعال‌سازی/تمدیدِ اشتراک، ثبتِ SubscriptionEvent و Audit — همه
idempotent در برابرِ تحویلِ تکراریِ Webhook."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import invoice_service
from apps.billing.services.period_utils import next_period_end
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc

ZERO = Decimal("0")


class ConfirmationError(Exception):
    """خطای قابل‌نمایش هنگام تأییدِ پرداخت (مبلغ/ارز/Provider نامطابق)."""


@transaction.atomic
def confirm_payment(*, attempt, amount, currency, provider_payment_id="", actor=None, now=None):
    """پرداختِ یک تلاش را تأیید و اعمال می‌کند — idempotent. مبلغ/ارزِ نامطابق
    را رد می‌کند. تلاشِ از قبل موفق را دوباره پردازش نمی‌کند."""
    now = now or timezone.now()
    locked_attempt = SubscriptionPaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=locked_attempt.invoice_id)

    # idempotency: تلاشِ از قبل موفق ⇒ بدونِ اعمالِ دوباره.
    if locked_attempt.status == SubscriptionPaymentAttempt.Status.SUCCEEDED:
        return locked_attempt
    if invoice.status == SubscriptionInvoice.Status.PAID:
        # فاکتور از قبل پرداخت‌شده (مثلاً تلاشِ دیگری موفق بود) — این تلاش را
        # هم موفق علامت می‌زنیم اگر لازم باشد، اما پرداختِ دوباره اعمال نمی‌شود.
        return locked_attempt

    amount = Decimal(amount)
    # بررسی‌هایِ امنیتی: Provider، ارز، مبلغ باید بخوانند.
    if currency != invoice.currency:
        raise ConfirmationError("ارزِ پرداخت با فاکتور نمی‌خواند.")
    if amount != invoice.amount_due:
        raise ConfirmationError("مبلغِ پرداخت با مبلغِ باقی‌مانده‌ی فاکتور نمی‌خواند.")

    # علامتِ یک‌بارِ موفقیتِ تلاش.
    locked_attempt.status = SubscriptionPaymentAttempt.Status.SUCCEEDED
    if provider_payment_id:
        locked_attempt.provider_payment_id = provider_payment_id
    locked_attempt.completed_at = now
    locked_attempt.save(update_fields=["status", "provider_payment_id", "completed_at", "updated_at"])

    # اعمالِ یک‌بارِ پرداخت رویِ فاکتور.
    invoice.amount_paid = invoice.amount_paid + amount
    invoice.recompute_amount_due()
    if invoice.amount_due <= ZERO:
        invoice.status = SubscriptionInvoice.Status.PAID
        invoice.paid_at = now
        invoice.provider_reference = provider_payment_id or invoice.provider_reference
    invoice.save(update_fields=[
        "amount_paid", "amount_due", "status", "paid_at", "provider_reference", "updated_at",
    ])
    record_audit_event(
        store=invoice.store, actor=actor, action_code="billing.payment_confirmed",
        object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
        after={"amount": str(amount), "status": invoice.status},
    )

    if invoice.status == SubscriptionInvoice.Status.PAID:
        _activate_or_renew(invoice, actor=actor, now=now)
    return locked_attempt


def _activate_or_renew(invoice, *, actor, now):
    """پس از پرداختِ کاملِ فاکتور، اشتراک را فعال یا تمدید می‌کند. تغییرِ پلن
    (kind=plan_change) در commit 8 مدیریت می‌شود."""
    subscription = StoreSubscription.objects.select_for_update().get(pk=invoice.subscription_id)
    interval = invoice.plan_version.billing_interval
    period_start = invoice.billing_period_start or now
    period_end = invoice.billing_period_end or next_period_end(period_start, interval)
    idem = f"invoice-{invoice.pk}"

    if invoice.kind == SubscriptionInvoice.Kind.INITIAL:
        # پرداختِ اولین فاکتور: pending/trialing → active (هرگز پیش از تأیید).
        if subscription.status in (StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING):
            sub_svc.activate_subscription(subscription, actor=actor, period_end=period_end, idempotency_key=idem)
    elif invoice.kind == SubscriptionInvoice.Kind.RENEWAL:
        sub_svc.renew_subscription(
            subscription, period_start=period_start, period_end=period_end, actor=actor, idempotency_key=idem,
        )
    ent.clear_entitlement_cache()
