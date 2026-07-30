"""رفتارِ صورتحساب هنگامِ لغوِ اشتراک (ADR-79/80).

- «لغو در پایانِ دوره»: اشتراک تا پایانِ دوره فعال می‌ماند؛ فاکتورِ تمدیدِ
  آینده‌ی پرداخت‌نشده (اگر ساخته شده) باطل می‌شود.
- «لغوِ فوری»: اشتراک بلافاصله لغو می‌شود؛ همه‌ی فاکتورهایِ پرداخت‌نشده‌ی این
  اشتراک باطل می‌شوند. فاکتورهایِ *پرداخت‌شده* هرگز حذف/باطل نمی‌شوند و
  بازپرداختِ خودکار رخ نمی‌دهد (مگر صریح؛ commit 9). هیچ رکوردِ فاکتور/تلاش
  بی‌سروصدا حذف نمی‌شود."""

from django.db import transaction

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.subscriptions.services import subscription_service as sub_svc

_UNPAID_STATUSES = (
    SubscriptionInvoice.Status.DRAFT,
    SubscriptionInvoice.Status.OPEN,
    SubscriptionInvoice.Status.PAYMENT_PENDING,
    SubscriptionInvoice.Status.PAST_DUE,
)


def _void_unpaid_invoices(subscription, *, actor, reason):
    voided = 0
    invoices = SubscriptionInvoice.objects.filter(
        subscription=subscription, status__in=_UNPAID_STATUSES,
    )
    for invoice in invoices.iterator(chunk_size=200):
        invoice_service.void_invoice(invoice, actor=actor, reason=reason)
        voided += 1
    return voided


@transaction.atomic
def cancel_subscription_billing(subscription, *, immediate=False, actor=None):
    """لغو را (فوری یا پایانِ دوره) اعمال می‌کند و فاکتورهایِ پرداخت‌نشده را
    باطل می‌کند. تعدادِ فاکتورهایِ باطل‌شده را برمی‌گرداند."""
    if immediate:
        sub_svc.cancel_immediately(subscription, actor=actor)
        voided = _void_unpaid_invoices(subscription, actor=actor, reason="لغوِ فوریِ اشتراک")
    else:
        sub_svc.cancel_at_period_end(subscription, actor=actor)
        # فاکتورِ تمدیدِ آینده‌ی پرداخت‌نشده دیگر لازم نیست.
        voided = _void_unpaid_invoices(subscription, actor=actor, reason="لغو در پایانِ دوره")
    return voided
