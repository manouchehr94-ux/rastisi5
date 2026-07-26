"""سرویس پنل مدیریت برای مشتریان.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تعداد سفارش و مجموع خرید
همیشه زنده از روی Order واقعی محاسبه می‌شود (نه فیلدهای ایستای
Customer.orders_count/total_spent که فقط دستور seed آن‌ها را پر می‌کند و در
جریان واقعی چک‌اوت به‌روز نمی‌شوند) — مشابه تصمیم مرحله‌ی ۱۱ برای پرفروش‌ترین‌ها.

Store scoping (PR23): ``Customer`` عمداً هیچ فیلد ``store`` ندارد — یکتاییِ
سراسریِ ``Customer.phone`` یک محدودیت شناخته‌شده و به‌تعویق‌افتاده‌ی SaaS
است (نگاه کنید به ADR در docs/architecture/SAAS_DOMAIN_DECISIONS.md)، نه
چیزی که این PR آن را حل می‌کند. در عوض، دید داشبورد هر Store به مشتریانی
محدود می‌شود که حداقل یک Order در همان Store دارند — نه با افزودن یک ستون
جدید به Customer، بلکه با فیلتر روی رابطه‌ی موجود Order.store. یک مشتری که
از هر دو Store خرید کرده می‌تواند به‌درستی در هر دو داشبورد دیده شود، اما
جمع/تعداد سفارش‌هایش در هر داشبورد فقط شامل همان Store است."""

from django.db.models import Count, Q, Sum

from apps.customers.models import Customer
from apps.orders.models import Order


def annotated_customers(*, store, q: str = ""):
    qs = Customer.objects.filter(orders__store=store).distinct().select_related("user").annotate(
        order_count=Count("orders", filter=Q(orders__store=store), distinct=True),
        paid_total=Sum(
            "orders__grand_total",
            filter=Q(orders__store=store, orders__payment_status=Order.PaymentStatus.PAID),
        ),
    ).order_by("-created_at")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(city__icontains=q))
    return qs


def customer_orders(customer: Customer, *, store):
    return Order.objects.filter(customer=customer, store=store).order_by("-created_at")


def customer_paid_total(orders_qs):
    return orders_qs.filter(payment_status=Order.PaymentStatus.PAID).aggregate(
        total=Sum("grand_total")
    )["total"] or 0
