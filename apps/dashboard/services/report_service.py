"""سرویس گزارش‌های حرفه‌ای پنل مدیریت — همه‌چیز از دیتابیس واقعی.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. نمودار فروش برای بازه‌های
۷/۳۰/۳۶۵ روزه با استفاده مجدد از dashboard_service.sales_chart_data ساخته
می‌شود (تا منطق سطربندی روز/ماه دوباره‌نویسی نشود)؛ فقط بازه‌ی ۹۰ روزه (بدون
معادل در داشبورد) با سطربندی هفتگی جداگانه محاسبه می‌شود.

«نرخ تبدیل بازدید به خرید» عمداً ساخته نشده: سایت هیچ ردیابی بازدید/ترافیک
واقعی ندارد (فقط Product.views_count برای هر کالا)، پس معادل صادقی برای این
شاخص وجود ندارد و ساختنش یعنی عدد بی‌پایه نمایش دادن.
"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.core.utils import to_fa_digits
from apps.orders.models import Order, OrderItem

from .dashboard_service import sales_chart_data as _dashboard_sales_chart_data
from .dashboard_service import top_selling_products

RANGE_DAYS = {"7": 7, "30": 30, "90": 90, "365": 365}
RANGE_FILTERS = [("7", "۷ روز اخیر"), ("30", "۳۰ روز اخیر"), ("90", "۳ ماه اخیر"), ("365", "یک سال اخیر")]
RANGE_LABELS = dict(RANGE_FILTERS)


def _weekly_sales_chart(days: int):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    first_monday = start - timedelta(days=start.weekday())
    week_starts = []
    cursor = first_monday
    while cursor <= today:
        week_starts.append(cursor)
        cursor += timedelta(days=7)

    rows = (
        Order.objects.filter(payment_status=Order.PaymentStatus.PAID, created_at__date__gte=start)
        .annotate(week=TruncWeek("created_at"))
        .values("week")
        .annotate(total=Sum("grand_total"))
    )
    totals = {row["week"].date(): row["total"] for row in rows}
    data = [float(totals.get(w, 0) or 0) for w in week_starts]
    labels = [f"هفته‌ی {to_fa_digits(i + 1)}" for i in range(len(week_starts))]
    return data, labels


def sales_chart_for_range(range_key: str):
    if range_key == "7":
        return _dashboard_sales_chart_data("week")
    if range_key == "365":
        return _dashboard_sales_chart_data("year")
    if range_key == "90":
        return _weekly_sales_chart(RANGE_DAYS["90"])
    return _dashboard_sales_chart_data("month")


def range_summary(range_key: str) -> dict:
    days = RANGE_DAYS.get(range_key, 30)
    start = timezone.localdate() - timedelta(days=days - 1)

    orders_in_range = Order.objects.filter(created_at__date__gte=start)
    paid_orders = orders_in_range.filter(payment_status=Order.PaymentStatus.PAID)

    total_sales = paid_orders.aggregate(s=Sum("grand_total"))["s"] or 0
    order_count = orders_in_range.count()
    paid_count = paid_orders.count()
    avg_order_value = (total_sales / paid_count) if paid_count else 0

    return {
        "total_sales": total_sales,
        "order_count": order_count,
        "avg_order_value": avg_order_value,
    }


def category_sales_breakdown(range_key: str, limit: int = 6):
    days = RANGE_DAYS.get(range_key, 30)
    since = timezone.now() - timedelta(days=days)
    rows = list(
        OrderItem.objects.filter(order__created_at__gte=since, product__isnull=False)
        .exclude(order__status=Order.Status.CANCELED)
        .values("product__category__parent__name")
        .annotate(total=Sum("line_total"))
        .order_by("-total")[:limit]
    )
    grand_total = sum((row["total"] for row in rows), start=0) or 0
    result = []
    for row in rows:
        amount = row["total"] or 0
        result.append({
            "name": row["product__category__parent__name"] or "سایر",
            "amount": amount,
            "pct": round(amount / grand_total * 100) if grand_total else 0,
        })
    return result


def top_products_report(range_key: str, limit: int = 6):
    return top_selling_products(limit=limit, days=RANGE_DAYS.get(range_key, 30))


def top_customers_report(range_key: str, limit: int = 6):
    days = RANGE_DAYS.get(range_key, 30)
    since = timezone.now() - timedelta(days=days)
    return list(
        Order.objects.filter(created_at__gte=since, payment_status=Order.PaymentStatus.PAID)
        .values("customer_id", "customer__full_name", "customer__is_vip")
        .annotate(order_count=Count("id"), total_spent=Sum("grand_total"))
        .order_by("-total_spent")[:limit]
    )


def build_report_context(range_key: str) -> dict:
    from .charts import build_line_chart_svg

    if range_key not in RANGE_DAYS:
        range_key = "30"
    data, labels = sales_chart_for_range(range_key)
    return {
        "range_key": range_key,
        "range_filters": RANGE_FILTERS,
        "range_label": RANGE_LABELS[range_key],
        "summary": range_summary(range_key),
        "sales_chart_svg": build_line_chart_svg(data, labels, color="#7c3aed"),
        "category_breakdown": category_sales_breakdown(range_key),
        "top_products": top_products_report(range_key),
        "top_customers": top_customers_report(range_key),
    }
