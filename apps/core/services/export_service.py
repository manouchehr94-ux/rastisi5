"""سرویسِ صادراتِ CSV — پنج نوع صادرات (کالا/تنوع/موجودی/مشتری/سفارش)، همه
Store-scoped. نگاه کنید به ADR-52 در ``SAAS_DOMAIN_DECISIONS.md``.

این کدبیس هیچ صفِ کارِ پس‌زمینه‌ای ندارد؛ بنابراین ``run_export`` کل کار
(نوشتنِ CSV + ذخیره‌ی فایل) را همگام و در همان درخواست انجام می‌دهد — وضعیت‌های
``pending``/``processing``/``completed`` بیشتر برای تاریخچه/UI معنا دارند تا
یک صفِ واقعی. اگر بعداً صفِ کارِ واقعی اضافه شد، فقط کافی‌ست این تابع را از
یک تسکِ async فراخوانی کرد — امضای آن تغییر نمی‌کند.

هر ردیف پیش از نوشتن از ``apps.core.services.csv_utils.write_csv_rows`` عبور
می‌کند (محافظتِ تزریقِ فرمولِ CSV، نگاه کنید به ADR-51). هیچ تابعی در این
ماژول مستقیماً ``csv.writer`` صدا نمی‌زند.
"""

import io

from django.core.files.base import ContentFile
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from apps.core.models import AuditLogEntry, ExportJob
from apps.core.services.audit_service import record_audit_event
from apps.core.services.csv_utils import write_csv_rows

EXPORT_RETENTION_DAYS = 7


class ExportError(Exception):
    """خطای قابل‌نمایشِ مستقیم به کاربر هنگامِ ساختِ یک صادرات."""


def _variant_option_summary(variant) -> str:
    """خلاصه‌ی محورهای تنوعِ یک ``ProductVariant`` را به یک رشته‌ی صریح و
    بدونِ ابهام تبدیل می‌کند — هرگز مقادیرِ چندمحوره را در یک ستونِ ساده
    بدونِ برچسبِ محور آن‌ها ادغام نمی‌کند (هر جفت به‌صورتِ
    ``محور=مقدار`` و جفت‌ها با ``|`` جدا می‌شوند، تا خودِ سلول هم برای
    انسان و هم برای واردات بعدی صریح/قابل‌تجزیه بماند)."""
    axis_pairs = list(
        variant.option_values.select_related("option", "option_value").values_list(
            "option__label", "option_value__label",
        )
    )
    if axis_pairs:
        return "|".join(f"{axis}={value}" for axis, value in axis_pairs)
    if variant.attribute or variant.value:
        return f"{variant.attribute}={variant.value}"
    return ""


def _products_rows(store, filters):
    from apps.catalog.models import Product

    qs = (
        Product.objects.filter(store=store)
        .select_related("brand", "category", "tax_class")
        .order_by("pk")
    )
    status = (filters or {}).get("status")
    if status:
        qs = qs.filter(status=status)
    category_id = (filters or {}).get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    header = [
        "شناسه", "نام", "اسلاگ", "SKU", "بارکد", "وضعیت", "برند", "دسته‌بندی",
        "قیمت", "موجودی", "وزن (گرم)", "نیاز به ارسال", "دسته‌ی مالیاتی",
        "عنوان سئو", "توضیحات سئو", "تاریخ ایجاد", "تاریخ به‌روزرسانی",
    ]

    def rows():
        for p in qs.iterator(chunk_size=500):
            yield [
                p.pk, p.name, p.slug, p.sku, p.barcode, p.get_status_display(),
                p.brand.name if p.brand_id else "", p.category.name if p.category_id else "",
                p.price, p.stock, p.weight_grams or "", "بله" if p.requires_shipping else "خیر",
                p.tax_class.name if p.tax_class_id else "",
                p.seo_title, p.seo_description,
                p.created_at.isoformat(), p.updated_at.isoformat(),
            ]

    return header, rows()


def _variants_rows(store, filters):
    from apps.catalog.models import ProductVariant

    qs = (
        ProductVariant.objects.filter(store=store)
        .select_related("product")
        .prefetch_related("option_values__option", "option_values__option_value")
        .order_by("product_id", "display_order", "pk")
    )
    product_id = (filters or {}).get("product_id")
    if product_id:
        qs = qs.filter(product_id=product_id)

    header = [
        "شناسه‌ی کالا", "شناسه‌ی تنوع", "کلیدِ ترکیب", "محورهای تنوع", "SKU",
        "بارکد", "تغییرِ قیمت", "قیمتِ مقایسه‌ای", "بهایِ تمام‌شده", "موجودی",
        "وزن (گرم)", "فعال", "پیش‌فرض", "منسوخ",
    ]

    def rows():
        for v in qs.iterator(chunk_size=500):
            yield [
                v.product_id, v.pk, v.combination_key, _variant_option_summary(v),
                v.sku, v.barcode, v.extra_price, v.compare_at_price or "", v.cost or "",
                v.stock, v.weight_grams or "",
                "بله" if v.is_active else "خیر", "بله" if v.is_default else "خیر",
                "بله" if v.is_obsolete else "خیر",
            ]

    return header, rows()


def _inventory_rows(store, filters):
    from apps.catalog.models import WarehouseInventory
    from apps.catalog.services.inventory_service import get_available_quantity

    qs = (
        WarehouseInventory.objects.filter(store=store)
        .select_related("warehouse", "product", "variant")
        .order_by("warehouse_id", "product_id")
    )
    warehouse_id = (filters or {}).get("warehouse_id")
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    header = [
        "انبار", "شناسه‌ی کالا", "کالا", "شناسه‌ی تنوع", "SKU", "بارکد",
        "موجودیِ این انبار (on hand)",
        "رزروِ فعال (کل فروشگاه، نه فقط این انبار)",
        "موجودیِ در دسترس (کل فروشگاه، نه فقط این انبار)",
        "آستانه‌ی هشدارِ کمبود", "آخرین به‌روزرسانی",
    ]

    def rows():
        for balance in qs.iterator(chunk_size=500):
            available = get_available_quantity(product=balance.product, variant=balance.variant)
            on_hand_total = balance.variant.stock if balance.variant_id else balance.product.stock
            reserved_total = on_hand_total - available
            yield [
                balance.warehouse.name, balance.product_id, balance.product.name,
                balance.variant_id or "",
                balance.variant.sku if balance.variant_id else balance.product.sku,
                balance.variant.barcode if balance.variant_id else balance.product.barcode,
                balance.on_hand, reserved_total, available,
                balance.low_stock_threshold if balance.low_stock_threshold is not None else "",
                balance.updated_at.isoformat(),
            ]

    return header, rows()


def _customers_rows(store, filters):
    from apps.customers.models import Customer
    from apps.orders.models import Order

    qs = (
        Customer.objects.filter(orders__store=store)
        .distinct()
        .annotate(
            order_count=Count("orders", filter=Q(orders__store=store), distinct=True),
            paid_total=Sum(
                "orders__grand_total",
                filter=Q(orders__store=store, orders__payment_status=Order.PaymentStatus.PAID),
            ),
            last_order_at=Max("orders__created_at", filter=Q(orders__store=store)),
        )
        .order_by("-created_at")
    )
    customer_ids = (filters or {}).get("customer_ids")
    if customer_ids:
        qs = qs.filter(pk__in=customer_ids)

    header = [
        "شناسه", "نام", "ایمیل", "موبایل", "تعداد سفارش (این فروشگاه)",
        "مجموع خرید (این فروشگاه)", "آخرین سفارش", "تاریخ عضویت",
    ]

    def rows():
        for c in qs.iterator(chunk_size=500):
            yield [
                c.pk, c.full_name, c.email, c.phone,
                c.order_count, c.paid_total or 0,
                c.last_order_at.isoformat() if c.last_order_at else "",
                c.created_at.isoformat(),
            ]

    return header, rows()


def _orders_rows(store, filters):
    from apps.orders.models import Order, Refund, ReturnRequest

    qs = (
        Order.objects.filter(store=store)
        .select_related("customer", "shipping_method")
        .order_by("-created_at")
    )
    status = (filters or {}).get("status")
    if status:
        qs = qs.filter(status=status)
    payment_status = (filters or {}).get("payment_status")
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    refund_totals = dict(
        Refund.objects.filter(store=store, status=Refund.Status.SUCCEEDED)
        .values("order_id").annotate(total=Sum("approved_amount")).values_list("order_id", "total")
    )
    return_status_by_order = dict(
        ReturnRequest.objects.filter(store=store).order_by("order_id", "-created_at")
        .values_list("order_id", "status")
    )

    header = [
        "شماره‌ی سفارش", "وضعیتِ سفارش", "وضعیتِ پرداخت", "مشتری", "تاریخ ایجاد",
        "جمعِ کالاها", "تخفیف", "هزینه‌ی ارسال", "مالیاتِ ارسال", "مالیات",
        "مبلغِ نهایی", "ارز", "روشِ ارسال (اسنپ‌شات)", "انبارِ تأمین‌کننده",
        "مجموعِ استردادِ موفق", "وضعیتِ آخرینِ مرجوعی",
    ]

    def rows():
        for o in qs.iterator(chunk_size=500):
            fulfillment_warehouse_name = (
                o.items.exclude(fulfillment_warehouse__isnull=True)
                .values_list("fulfillment_warehouse__name", flat=True).first() or ""
            )
            yield [
                o.code, o.get_status_display(), o.get_payment_status_display(),
                o.customer.full_name, o.created_at.isoformat(),
                o.items_total, o.product_discount + o.coupon_discount,
                o.shipping_cost, o.shipping_tax, o.tax, o.grand_total,
                # Order has no ``currency`` field — this platform supports
                # only Toman (see ``Refund.currency`` default/ShippingRateRule.CURRENCY).
                "IRT",
                o.shipping_method_name, fulfillment_warehouse_name,
                refund_totals.get(o.pk, 0) or 0,
                return_status_by_order.get(o.pk, ""),
            ]

    return header, rows()


_EXPORT_ROW_BUILDERS = {
    ExportJob.ExportType.PRODUCTS: _products_rows,
    ExportJob.ExportType.VARIANTS: _variants_rows,
    ExportJob.ExportType.INVENTORY: _inventory_rows,
    ExportJob.ExportType.CUSTOMERS: _customers_rows,
    ExportJob.ExportType.ORDERS: _orders_rows,
}


def run_export(store, export_type: str, *, requested_by, filters: dict | None = None) -> ExportJob:
    """یک ``ExportJob`` می‌سازد و بلافاصله (همگام) اجرا می‌کند — نگاه کنید به
    توضیحِ بالای این ماژول درباره‌ی نبودِ صفِ کارِ پس‌زمینه‌ای. هرگز رخدادِ
    این عملیات را بدون ثبت در گزارشِ رخدادها رها نمی‌کند، چه موفق چه ناموفق."""
    if export_type not in _EXPORT_ROW_BUILDERS:
        raise ExportError(f"نوعِ صادراتِ «{export_type}» پشتیبانی نمی‌شود.")

    job = ExportJob.objects.create(
        store=store, export_type=export_type, status=ExportJob.Status.PROCESSING,
        requested_by=requested_by, filters=filters or {},
        started_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=EXPORT_RETENTION_DAYS),
    )

    try:
        header, rows = _EXPORT_ROW_BUILDERS[export_type](store, filters)
        buffer = io.StringIO()
        row_count = write_csv_rows(buffer, header=header, rows=rows)
        job.file.save(f"{export_type}.csv", ContentFile(buffer.getvalue().encode("utf-8")), save=False)
        job.row_count = row_count
        job.status = ExportJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["file", "row_count", "status", "completed_at"])
        record_audit_event(
            store=store, actor=requested_by, action_code="export.completed",
            object_type="ExportJob", object_id=str(job.pk),
            object_label=f"صادراتِ {job.get_export_type_display()} — {row_count} ردیف",
            after={"export_type": export_type, "row_count": row_count, "filters": filters or {}},
        )
    except Exception as exc:
        job.status = ExportJob.Status.FAILED
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at"])
        record_audit_event(
            store=store, actor=requested_by, action_code="export.failed",
            object_type="ExportJob", object_id=str(job.pk),
            object_label=f"صادراتِ {job.get_export_type_display()} ناموفق",
            metadata={"error": str(exc)}, result=AuditLogEntry.ResultStatus.FAILURE,
        )
        raise
    return job


def mark_expired_jobs(store=None, *, now=None):
    """هر ``ExportJob`` کامل‌شده‌ای که ``expires_at`` آن گذشته را ``expired``
    می‌کند و فایلِ آن را از دیسک حذف می‌کند (آزادسازیِ فضا) — منطقِ اصلیِ
    ``cleanup_expired_exports`` که هم از دستورِ مدیریتی و هم (اگر لازم شد)
    مستقیماً قابلِ فراخوانی است. هرگز کل جدول را در حافظه بارگذاری نمی‌کند
    (``iterator``)."""
    now = now or timezone.now()
    qs = ExportJob.objects.filter(status=ExportJob.Status.COMPLETED, expires_at__lt=now)
    if store is not None:
        qs = qs.filter(store=store)

    count = 0
    for job in qs.iterator(chunk_size=200):
        if job.file:
            job.file.delete(save=False)
        job.status = ExportJob.Status.EXPIRED
        job.save(update_fields=["status", "file"])
        count += 1
    return count
