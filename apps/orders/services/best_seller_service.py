"""رتبه‌بندیِ «پرفروش‌ترین» — تنها الگوریتمِ مجاز در کل کدبیس برایِ این
مفهوم؛ هم داشبورد (``dashboard_service.top_selling_products``،
``report_service.top_products_report``) و هم سازنده بصری (Storefront
Builder Phase C — منبعِ داده‌یِ «پرفروش‌ترین» بخشِ محصول) از همین‌جا
عبور می‌کنند.

همیشه به‌صورتِ زنده از ``OrderItem``هایِ واقعیِ یک بازه‌ی اخیر محاسبه
می‌شود (سفارش‌هایِ لغوشده مستثنا)، **هرگز** از ``Product.sold_count`` —
طبقِ ممیزیِ فازِ A (``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md``
بخشِ ۸)، آن فیلد هیچ writer‌ای در کلِ کدبیس ندارد (فقط در دیتایِ seed/
تست مقداردهی می‌شود) و در محیطِ واقعی همیشه صفر می‌ماند."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.orders.models import Order, OrderItem

DEFAULT_WINDOW_DAYS = 30


def best_selling_totals(store, *, limit: int, days: int = DEFAULT_WINDOW_DAYS) -> list[tuple[int, int]]:
    """جفت‌هایِ ``(product_id, total_sold)`` این Store، به ترتیبِ نزولیِ
    تعدادِ واقعیِ فروخته‌شده در ``days`` روزِ اخیر (سفارش‌هایِ لغوشده
    مستثنا). تنها کوئریِ تجمیعیِ مجاز برایِ این مفهوم — مصرف‌کننده‌ای
    نباید این محاسبه را دوباره پیاده‌سازی کند، فقط از این تابع (یا
    ``best_selling_product_ids``) عبور کند."""
    since = timezone.now() - timedelta(days=days)
    rows = (
        OrderItem.objects.filter(order__store=store, order__created_at__gte=since, product__isnull=False)
        .exclude(order__status=Order.Status.CANCELED)
        .values("product_id")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold", "product_id")[:limit]
    )
    return [(row["product_id"], row["total_sold"]) for row in rows]


def best_selling_product_ids(store, *, limit: int, days: int = DEFAULT_WINDOW_DAYS) -> list[int]:
    """فقط شناسه‌ها، به همان ترتیب — برایِ مصرف‌کننده‌هایی که فقط به
    ترتیبِ رتبه نیاز دارند (نه عددِ فروش)، مثلِ رندرِ سازنده بصری."""
    return [product_id for product_id, _ in best_selling_totals(store, limit=limit, days=days)]
