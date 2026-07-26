"""سرویس پنل مدیریت برای سفارش‌ها، فاکتورها و تراکنش‌ها.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۳: فیلتر/جستجوی سفارش‌ها،
تغییر وضعیت از طریق سرویس مرحله‌ی ۲ (apps.orders.services.order_service)،
فاکتور بر مبنای همان کد سفارش (بدون شماره‌گذاری جعلی)، و فهرست تراکنش‌ها.
"""

from django.db.models import Count, Q

from apps.orders.models import Order, Transaction
from apps.orders.services.order_service import ALLOWED_TRANSITIONS, FINAL_STATUSES

ORDER_STATUS_FILTERS = [("", "همه")] + list(Order.Status.choices)
INVOICE_STATUS_FILTERS = [("", "همه")] + list(Order.PaymentStatus.choices)
TRANSACTION_STATUS_FILTERS = [("", "همه وضعیت‌ها")] + list(Transaction.Status.choices)

TRANSACTION_STATUS_BADGE = {
    Transaction.Status.OK: "b-green",
    Transaction.Status.PENDING: "b-amber",
    Transaction.Status.FAIL: "b-red",
    Transaction.Status.REFUND: "b-purple",
}


def filtered_orders(*, store, q: str = "", status: str = ""):
    qs = Order.objects.filter(store=store).select_related("customer").order_by("-created_at")
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(customer__full_name__icontains=q) | Q(customer__phone__icontains=q))
    if status:
        qs = qs.filter(status=status)
    return qs


def order_status_counts(*, store) -> dict:
    """شمارش سفارش‌های همین Store به تفکیک وضعیت؛ کلید «» (رشته‌ی خالی) برابر با مجموع همه است."""
    counts = dict.fromkeys(Order.Status.values, 0)
    counts[""] = 0
    rows = Order.objects.filter(store=store).values("status").annotate(total=Count("id"))
    for row in rows:
        counts[row["status"]] = row["total"]
        counts[""] += row["total"]
    return counts


def next_status_options(order: Order):
    """وضعیت‌های مجاز بعدی برای گذار سفارش، طبق ALLOWED_TRANSITIONS سرویس مرحله‌ی ۲."""
    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    return [(value, label) for value, label in Order.Status.choices if value in allowed]


def order_is_final(order: Order) -> bool:
    return order.status in FINAL_STATUSES


ORDER_TIMELINE_STEPS = [
    Order.Status.PENDING,
    Order.Status.PROCESSING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
]


def order_status_steps(order: Order):
    """گام‌های خط‌زمانی سفارش (بدون در نظر گرفتن لغو) به همراه علامت انجام‌شده/بعدی."""
    labels = dict(Order.Status.choices)
    idx = -1 if order.status == Order.Status.CANCELED else ORDER_TIMELINE_STEPS.index(order.status)
    return [
        (status, labels[status], i <= idx, i == idx + 1)
        for i, status in enumerate(ORDER_TIMELINE_STEPS)
    ]


def filtered_invoices(*, store, q: str = "", status: str = ""):
    qs = filtered_orders(store=store, q=q)
    if status:
        qs = qs.filter(payment_status=status)
    return qs


def invoice_totals(orders_qs):
    count = orders_qs.count()
    total = sum((order.grand_total for order in orders_qs), start=0)
    return count, total


def filtered_transactions(*, store, status: str = ""):
    qs = Transaction.objects.filter(order__store=store).select_related(
        "order", "order__customer", "gateway"
    ).order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs
