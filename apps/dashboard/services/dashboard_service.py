"""سرویس داده‌ی داشبورد پنل مدیریت — همه‌چیز از دیتابیس، بدون داده‌ی هاردکد.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۱: کارت‌های آمار، نمودار
فروش (روزانه/ماهانه)، نمودار دایره‌ای وضعیت سفارش‌ها، پرفروش‌ترین‌های ۳۰ روز
اخیر (از OrderItem واقعی، نه فیلد استاتیک sold_count)، آخرین سفارش‌ها و
هشدار موجودی کم.

Phase 1B fix: every function here now takes an explicit ``store`` and scopes
its query to it. Before this PR, only the Product-based figures
(``stat_cards``'s ``low_stock_count``, ``low_stock_products``,
``nav_product_count``) were Store-scoped — the Order/Customer-based ones
(``sales_chart_data``, ``order_status_breakdown``, ``recent_orders``,
``top_selling_products``, ``nav_pending_order_count``, and the sales/order
counts inside ``stat_cards``) queried across *every* Store's orders
unconditionally. That was accurate when this module was first written
(``Order`` had no ``store`` FK yet), but ``Order.store`` has existed as a
direct, mandatory field since the "Order Boundary and Checkout Integrity"
PR (see ``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §11.5) — this
module was simply never updated to use it, so the dashboard home page was
silently mixing every Store's sales/order/customer figures together on any
merchant's screen. Customer scoping reuses the exact relation-based pattern
``apps.dashboard.services.customers_admin_service.annotated_customers``
already established (``Customer`` has no direct ``store`` FK by deliberate
ADR-pending decision; scope via ``orders__store``)."""

from datetime import timedelta

import jdatetime
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.utils import to_fa_digits
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.orders.services import best_seller_service

LOW_STOCK_THRESHOLD = 10

PERSIAN_WEEKDAYS = ["شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

ORDER_STATUS_BADGE = {
    Order.Status.PENDING: "b-amber",
    Order.Status.PROCESSING: "b-blue",
    Order.Status.SHIPPED: "b-cyan",
    Order.Status.DELIVERED: "b-green",
    Order.Status.CANCELED: "b-red",
}
PAYMENT_STATUS_BADGE = {
    Order.PaymentStatus.PENDING: "b-amber",
    Order.PaymentStatus.PAID: "b-green",
    Order.PaymentStatus.FAILED: "b-red",
    Order.PaymentStatus.REFUNDED: "b-purple",
}


def _to_jalali(date_obj):
    return jdatetime.date.fromgregorian(date=date_obj)


def _add_months(date_obj, delta: int):
    """اولین روز ماه را delta ماه جابه‌جا می‌کند (میلادی، برای گروه‌بندی صحیح بدون وابستگی به طول ماه)."""
    month_index = date_obj.month - 1 + delta
    year = date_obj.year + month_index // 12
    month = month_index % 12 + 1
    return date_obj.replace(year=year, month=month, day=1)


def _pct_change(current, previous):
    """درصد تغییر؛ اگر مقدار پایه صفر باشد، عددی گمراه‌کننده تولید نمی‌کند."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def _trend(current, previous):
    """خروجی آماده‌ی نمایش: درصد تغییر (رشته‌ی فارسی آماده) + جهت، یا None اگر قابل مقایسه نباشد."""
    pct = _pct_change(current, previous)
    if pct is None:
        return None
    display = to_fa_digits(f"{abs(pct):.1f}".replace(".", "٫"))
    return {"pct_display": display, "up": pct >= 0}


def _paid_totals_by_day(store, start_date, end_date):
    rows = (
        Order.objects.filter(
            store=store, payment_status=Order.PaymentStatus.PAID,
            created_at__date__gte=start_date, created_at__date__lte=end_date,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("grand_total"))
    )
    return {row["day"]: row["total"] for row in rows}


def _paid_totals_by_month(store, start_date):
    rows = (
        Order.objects.filter(store=store, payment_status=Order.PaymentStatus.PAID, created_at__date__gte=start_date)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("grand_total"))
    )
    return {row["month"].date(): row["total"] for row in rows}


def sales_chart_data(store, range_key: str = "month"):
    """داده و برچسب‌های نمودار روند فروش را برای بازه‌ی هفته/ماه/سال، مخصوص همین Store برمی‌گرداند."""
    today = timezone.localdate()

    if range_key == "week":
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        totals = _paid_totals_by_day(store, days[0], days[-1])
        data = [float(totals.get(d, 0) or 0) for d in days]
        labels = [PERSIAN_WEEKDAYS[_to_jalali(d).weekday()] for d in days]
        return data, labels

    if range_key == "year":
        first_month = _add_months(today.replace(day=1), -11)
        totals = _paid_totals_by_month(store, first_month)
        months = [_add_months(first_month, i) for i in range(12)]
        data = [float(totals.get(m, 0) or 0) for m in months]
        labels = [PERSIAN_MONTHS[_to_jalali(m).month - 1] for m in months]
        return data, labels

    # پیش‌فرض: ۳۰ روز گذشته
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    totals = _paid_totals_by_day(store, days[0], days[-1])
    data = [float(totals.get(d, 0) or 0) for d in days]
    labels = [to_fa_digits(_to_jalali(d).day) for d in days]
    return data, labels


def order_status_breakdown(store):
    """تعداد سفارش‌های همین Store به تفکیک وضعیت، در ماه جاری."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    counts = dict.fromkeys(Order.Status.values, 0)
    rows = (
        Order.objects.filter(store=store, created_at__date__gte=month_start)
        .values("status").annotate(total=Count("id"))
    )
    for row in rows:
        counts[row["status"]] = row["total"]
    return counts


def stat_cards(store):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)

    today_sales = float(_paid_totals_by_day(store, today, today).get(today, 0) or 0)
    yesterday_sales = float(_paid_totals_by_day(store, yesterday, yesterday).get(yesterday, 0) or 0)

    today_orders = Order.objects.filter(store=store, created_at__date=today).count()
    yesterday_orders = Order.objects.filter(store=store, created_at__date=yesterday).count()

    # Customer has no direct store FK (ADR-pending, see module docstring) —
    # scope via the same orders__store relation customers_admin_service uses.
    store_customers = Customer.objects.filter(orders__store=store).distinct()
    customers_total = store_customers.count()
    customers_new_this_month = store_customers.filter(created_at__date__gte=month_start).count()
    customers_before = customers_total - customers_new_this_month

    low_stock_count = Product.objects.filter(
        store=store, status=Product.Status.ACTIVE, stock__lte=LOW_STOCK_THRESHOLD,
    ).count()

    return {
        "today_sales": today_sales,
        "today_sales_trend": _trend(today_sales, yesterday_sales),
        "today_orders": today_orders,
        "today_orders_trend": _trend(today_orders, yesterday_orders),
        "customers_total": customers_total,
        "customers_new_this_month": customers_new_this_month,
        "customers_trend": _trend(customers_new_this_month, customers_before),
        "low_stock_count": low_stock_count,
    }


def product_health_counts(store):
    """شمارش‌های سلامتِ داده برایِ کارت‌های داشبورد — هرکدام به فهرستِ کالاهایِ
    فیلترشده‌ی متناظرش وصل می‌شود (نگاه کنید به
    ``catalog_admin_service.filtered_products``'s ``health=`` و ``status=``).

    «کالاهای بدونِ دسته‌بندی» عمداً این‌جا نیست: ``Product.category`` یک
    فیلدِ الزامی است (نه nullable) — هیچ کالایی بدونِ دسته‌بندی نمی‌تواند
    اصلاً ساخته شود، پس این شاخص در این معماری همیشه صفر و بی‌معناست."""
    from django.db.models import Count, Q

    base = Product.objects.filter(store=store, is_draft_placeholder=False)
    return {
        "active": base.filter(status=Product.Status.ACTIVE).count(),
        "draft": base.filter(status=Product.Status.DRAFT).count(),
        "out_of_stock": base.filter(stock=0).count(),
        "no_images": base.annotate(image_count=Count("images", distinct=True)).filter(image_count=0).count(),
        "no_seo": base.filter(
            Q(seo_title="") | Q(seo_title__isnull=True), Q(seo_description="") | Q(seo_description__isnull=True),
        ).count(),
        "missing_variants": base.annotate(variant_count=Count("variants", distinct=True)).filter(
            product_type=Product.ProductType.VARIABLE, variant_count=0,
        ).count(),
    }


def recent_orders(store, limit: int = 6):
    return (
        Order.objects.filter(store=store)
        .select_related("customer")
        .order_by("-created_at")[:limit]
    )


def top_selling_products(store, limit: int = 5, days: int = 30):
    """پرفروش‌ترین‌های واقعی این Store — محاسبه‌ی خودِ رتبه‌بندی از
    ``best_seller_service`` (تنها الگوریتمِ مجاز، به‌اشتراک با سازنده
    بصری) عبور می‌کند؛ اینجا فقط فیلدهایِ نمایشیِ کارتِ داشبورد
    (نام/آیکون/رنگ + درصدِ نوار پیشرفت) به آن ضمیمه می‌شود."""
    totals = best_seller_service.best_selling_totals(store, limit=limit, days=days)
    if not totals:
        return []
    products_by_id = {
        product.pk: product
        for product in Product.objects.filter(store=store, pk__in=[pid for pid, _ in totals])
        .only("id", "name", "icon", "tint")
    }
    max_sold = totals[0][1]
    rows = []
    for product_id, total_sold in totals:
        product = products_by_id.get(product_id)
        if product is None:
            continue
        rows.append({
            "product_id": product_id,
            "product__name": product.name,
            "product__icon": product.icon,
            "product__tint": product.tint,
            "total_sold": total_sold,
            "progress_pct": round(total_sold / max_sold * 100) if max_sold else 0,
        })
    return rows


def category_chain(category):
    if category is None:
        return "—"
    if category.parent:
        return f"{category.parent.name} › {category.name}"
    return category.name


def low_stock_products(store, limit: int = 20):
    products = (
        Product.objects.filter(
            store=store, status=Product.Status.ACTIVE, stock__lte=LOW_STOCK_THRESHOLD,
            is_draft_placeholder=False,
        )
        .select_related("category", "category__parent")
        .order_by("stock")[:limit]
    )
    rows = []
    for product in products:
        if product.stock == 0:
            badge_cls, badge_label = "b-red", "ناموجود"
        elif product.stock <= 5:
            badge_cls, badge_label = "b-red", "بحرانی"
        else:
            badge_cls, badge_label = "b-amber", "رو به اتمام"
        rows.append({
            "product": product,
            "category_chain": category_chain(product.category),
            "badge_cls": badge_cls, "badge_label": badge_label,
        })
    return rows


DONUT_STATUS_ORDER = [
    (Order.Status.DELIVERED, "تحویل شده", "#10b981"),
    (Order.Status.PROCESSING, "در حال پردازش", "#3b82f6"),
    (Order.Status.SHIPPED, "ارسال شده", "#06b6d4"),
    (Order.Status.PENDING, "در انتظار پرداخت", "#f59e0b"),
    (Order.Status.CANCELED, "لغو شده", "#ef4444"),
]


def _today_jalali_display():
    from apps.core.utils import to_fa_digits

    today = timezone.localdate()
    jalali = _to_jalali(today)
    weekday = PERSIAN_WEEKDAYS[jalali.weekday()]
    month = PERSIAN_MONTHS[jalali.month - 1]
    return f"{weekday} {to_fa_digits(jalali.day)} {month} {to_fa_digits(jalali.year)}"


def build_dashboard_context(store):
    from .charts import build_donut_chart_svg, build_line_chart_svg

    cards = stat_cards(store)
    data, labels = sales_chart_data(store, "month")
    status_counts = order_status_breakdown(store)

    donut_items = [
        {"label": label, "value": status_counts.get(status, 0), "color": color}
        for status, label, color in DONUT_STATUS_ORDER
    ]

    return {
        "stat_cards": cards,
        "product_health": product_health_counts(store),
        "sales_chart_svg": build_line_chart_svg(data, labels),
        "donut_svg": build_donut_chart_svg(donut_items),
        "donut_legend": donut_items,
        "recent_orders": recent_orders(store),
        "top_products": top_selling_products(store),
        "low_stock_rows": low_stock_products(store),
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "nav_product_count": Product.objects.filter(store=store, is_draft_placeholder=False).count(),
        "nav_pending_order_count": Order.objects.filter(store=store, status=Order.Status.PENDING).count(),
        "today_jalali": _today_jalali_display(),
        "store_status": store.status,
        "store_status_display": store.get_status_display(),
    }
