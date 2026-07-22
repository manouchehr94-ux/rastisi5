"""سرویس پنل مدیریت برای مشتریان.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تعداد سفارش و مجموع خرید
همیشه زنده از روی Order واقعی محاسبه می‌شود (نه فیلدهای ایستای
Customer.orders_count/total_spent که فقط دستور seed آن‌ها را پر می‌کند و در
جریان واقعی چک‌اوت به‌روز نمی‌شوند) — مشابه تصمیم مرحله‌ی ۱۱ برای پرفروش‌ترین‌ها.
"""

from django.db.models import Count, Q, Sum

from apps.customers.models import Customer
from apps.orders.models import Order


def annotated_customers(q: str = ""):
    qs = Customer.objects.select_related("user").annotate(
        order_count=Count("orders", distinct=True),
        paid_total=Sum("orders__grand_total", filter=Q(orders__payment_status=Order.PaymentStatus.PAID)),
    ).order_by("-created_at")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(city__icontains=q))
    return qs


def customer_orders(customer: Customer):
    return Order.objects.filter(customer=customer).order_by("-created_at")


def customer_paid_total(orders_qs):
    return orders_qs.filter(payment_status=Order.PaymentStatus.PAID).aggregate(
        total=Sum("grand_total")
    )["total"] or 0
