"""بررسیِ سازگاریِ صورتحساب — فقط *می‌خواند* و فهرستِ مشکلات را برمی‌گرداند
(هرگز چیزی نمی‌نویسد). برایِ ``verify_billing_consistency`` (ADR-77/78)."""

from decimal import Decimal

from django.db.models import Count, Sum

from apps.billing.models import (
    SubscriptionDunningState,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
    SubscriptionRefund,
)
from apps.subscriptions.models import StoreSubscription

ZERO = Decimal("0")


def check_billing_consistency() -> list:
    """مشکلاتِ سازگاری را به‌صورتِ فهرستی از dict (severity + message) برمی‌گرداند."""
    issues = []

    # ۱) فاکتورِ اضافه‌پرداخت‌شده / موجودیِ منفی (قید هم جلویش را می‌گیرد).
    for inv in SubscriptionInvoice.objects.filter(amount_paid__gt=0).iterator(chunk_size=300):
        if inv.amount_paid > inv.grand_total:
            issues.append({"severity": "error",
                           "message": f"فاکتور {inv.number} اضافه‌پرداخت شده (paid>total)."})
        if inv.amount_due < ZERO or inv.amount_paid < ZERO:
            issues.append({"severity": "error", "message": f"فاکتور {inv.number} موجودیِ منفی دارد."})

    # ۲) فاکتورِ پرداخت‌شده بدونِ هیچ تلاشِ موفق.
    paid_invoices = SubscriptionInvoice.objects.filter(status=SubscriptionInvoice.Status.PAID)
    for inv in paid_invoices.iterator(chunk_size=300):
        has_success = inv.payment_attempts.filter(
            status=SubscriptionPaymentAttempt.Status.SUCCEEDED,
        ).exists()
        if not has_success:
            issues.append({"severity": "error",
                           "message": f"فاکتورِ پرداخت‌شده {inv.number} هیچ تلاشِ موفق/نشانه‌ی دستی ندارد."})
        # ارز باید بخواند.
        mismatch = inv.payment_attempts.filter(
            status=SubscriptionPaymentAttempt.Status.SUCCEEDED,
        ).exclude(currency=inv.currency).exists()
        if mismatch:
            issues.append({"severity": "error",
                           "message": f"ارزِ تلاشِ پرداختِ فاکتور {inv.number} با فاکتور نمی‌خواند."})

    # ۳) پرداختِ موفقِ فاکتورِ اولیه اما اشتراکِ هنوز فعال‌نشده.
    for inv in paid_invoices.filter(kind=SubscriptionInvoice.Kind.INITIAL).select_related("subscription"):
        if inv.subscription.status in (
            StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING,
        ):
            issues.append({"severity": "error",
                           "message": f"فاکتورِ اولیه‌ی {inv.number} پرداخت شده اما اشتراک فعال نشده."})

    # ۴) بازپرداختِ بیش از مبلغِ پرداخت‌شده.
    refund_totals = (
        SubscriptionRefund.objects.filter(status=SubscriptionRefund.Status.SUCCEEDED)
        .values("invoice").annotate(total=Sum("amount"))
    )
    invoice_map = {i.pk: i for i in SubscriptionInvoice.objects.filter(
        pk__in=[r["invoice"] for r in refund_totals])}
    for row in refund_totals:
        inv = invoice_map.get(row["invoice"])
        if inv and (row["total"] or ZERO) > inv.amount_paid:
            issues.append({"severity": "error",
                           "message": f"بازپرداختِ فاکتور {inv.number} از مبلغِ پرداخت‌شده بیشتر است."})

    # ۵) فاکتورِ باز برایِ اشتراکِ نهایی‌شده.
    open_terminal = SubscriptionInvoice.objects.filter(
        status__in=(
            SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAYMENT_PENDING,
            SubscriptionInvoice.Status.PAST_DUE,
        ),
        subscription__status__in=StoreSubscription.TERMINAL_STATUSES,
    )
    for inv in open_terminal.iterator(chunk_size=300):
        issues.append({"severity": "warning",
                       "message": f"فاکتورِ بازِ {inv.number} برایِ اشتراکِ نهایی‌شده."})

    # ۶) وضعیتِ Dunningِ فعال اما فاکتورِ پرداخت‌شده/باطل.
    stale_dunning = SubscriptionDunningState.objects.filter(
        status=SubscriptionDunningState.Status.ACTIVE,
        invoice__status__in=(
            SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.VOID,
        ),
    )
    for state in stale_dunning.select_related("invoice").iterator(chunk_size=300):
        issues.append({"severity": "warning",
                       "message": f"Dunningِ فعال رویِ فاکتورِ حل‌شده‌ی {state.invoice.number}."})

    # ۷) فاکتورِ تمدیدِ تکراری در یک دوره (قید هم جلویش را می‌گیرد).
    dupes = (
        SubscriptionInvoice.objects.filter(kind=SubscriptionInvoice.Kind.RENEWAL)
        .values("subscription", "billing_period_start").annotate(n=Count("id")).filter(n__gt=1)
    )
    for row in dupes:
        issues.append({"severity": "error",
                       "message": f"فاکتورِ تمدیدِ تکراری برایِ اشتراک {row['subscription']}."})

    return issues
