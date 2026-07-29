"""استردادِ سفارش — برنامه‌ریزی و اجرا با یکپارچگیِ مالیِ کامل (ADR-33).

مبالغِ قابل‌استرداد همیشه از رویِ اسنپ‌شاتِ غیرقابل‌تغییرِ ``Order``
(``grand_total``/``shipping_cost``/``OrderItem.unit_price``) محاسبه
می‌شوند — هرگز از رویِ قیمتِ فعلیِ ``Product``. هیچ درگاه پرداختِ واقعیِ
این پلتفرم اجرای واقعیِ استرداد را ندارد؛ ``execute_order_refund`` فقط
روشِ ``MANUAL`` را واقعاً اجرا می‌کند (ثبتِ صادقانه‌ی واریزِ خارج از سیستم
توسط مدیر) و برای ``GATEWAY`` صراحتاً خطا می‌دهد — نگاه کنید به ADR-33.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.services.inventory_service import (
    ReturnItemAlreadyRestockedError,
    restock_refund_item,
)
from apps.core.services.audit_service import record_audit_event
from apps.orders.models import Order, OrderItem, Refund, RefundItem


class RefundError(Exception):
    """خطای قابل‌نمایش هنگام برنامه‌ریزی یا اجرای استرداد."""


def _active_refunds(order):
    """استردادهایی که در محاسبه‌ی «قبلاً استرداد شده» شرکت می‌کنند — همه به‌جز
    آن‌هایی که نهایتاً هرگز اتفاق نمی‌افتند (ناموفق/لغوشده)."""
    return order.refunds.exclude(status__in=(Refund.Status.FAILED, Refund.Status.CANCELLED))


def paid_amount(order: Order) -> Decimal:
    """مبلغِ واقعاً پرداخت‌شده‌ی این سفارش — این کدبیس پرداختِ جزئی را در سطح
    Order مدل نمی‌کند، پس این مقدار یا صفر است یا کل ``grand_total``."""
    if order.payment_status in (Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED):
        return order.grand_total
    return Decimal("0")


def refunded_total(order: Order) -> Decimal:
    total = Decimal("0")
    for refund in _active_refunds(order):
        total += refund.approved_amount if refund.approved_amount is not None else refund.requested_amount
    return total


def refundable_amount(order: Order) -> Decimal:
    return max(Decimal("0"), paid_amount(order) - refunded_total(order))


def refunded_shipping_total(order: Order) -> Decimal:
    total = Decimal("0")
    for refund in _active_refunds(order):
        total += refund.shipping_refund_amount
    return total


def refunded_shipping_tax_total(order: Order) -> Decimal:
    total = Decimal("0")
    for refund in _active_refunds(order):
        total += refund.shipping_tax_refund_amount
    return total


def _refunded_quantity_for_item(order_item: OrderItem) -> int:
    total = 0
    for refund_item in RefundItem.objects.filter(order_item=order_item).exclude(
        refund__status__in=(Refund.Status.FAILED, Refund.Status.CANCELLED)
    ):
        total += refund_item.quantity
    return total


def _refunded_tax_for_item(order_item: OrderItem) -> Decimal:
    """مجموعِ مالیاتِ قبلاً استردادشده‌ی این قلم — نگاه کنید به ADR-33/checkpoint
    3B §17: مالیات هرگز دوبار استرداد نمی‌شود، دقیقاً مثلِ خودِ مبلغِ کالا."""
    total = Decimal("0")
    for refund_item in RefundItem.objects.filter(order_item=order_item).exclude(
        refund__status__in=(Refund.Status.FAILED, Refund.Status.CANCELLED)
    ):
        total += refund_item.tax_amount
    return total


@dataclass
class RefundLinePlan:
    order_item: OrderItem
    quantity: int
    max_quantity: int
    amount: Decimal
    tax_amount: Decimal = Decimal("0")


@dataclass
class RefundPlan:
    order: Order
    lines: list = field(default_factory=list)
    shipping_amount: Decimal = Decimal("0")
    max_shipping: Decimal = Decimal("0")
    shipping_tax_amount: Decimal = Decimal("0")
    max_shipping_tax: Decimal = Decimal("0")
    items_total: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    max_refundable: Decimal = Decimal("0")


def plan_order_refund(order: Order, *, store, line_requests: list[dict], shipping_amount: Decimal = Decimal("0")) -> RefundPlan:
    """محاسبه‌ی خالص (بدونِ نوشتن چیزی در دیتابیس) یک استردادِ پیشنهادی —
    برای نمایشِ «حداکثرِ قابل‌استرداد» و اعتبارسنجیِ پیش از ثبت.

    ``line_requests``: فهرستی از ``{"order_item_id": int, "quantity": int}``.
    """
    if order.store_id != store.pk:
        raise RefundError("این سفارش متعلق به این فروشگاه نیست.")

    max_refundable = refundable_amount(order)
    max_shipping = max(Decimal("0"), order.shipping_cost - refunded_shipping_total(order))
    max_shipping_tax = max(Decimal("0"), order.shipping_tax - refunded_shipping_tax_total(order))

    if shipping_amount < 0:
        raise RefundError("مبلغِ استردادِ ارسال نمی‌تواند منفی باشد.")
    if shipping_amount > max_shipping:
        raise RefundError("مبلغِ استردادِ ارسال از هزینه‌ی باقی‌مانده‌ی ارسال بیشتر است.")

    # مالیاتِ ارسال متناسب با نسبتِ استردادِ درخواستی از خودِ هزینه‌ی ارسال
    # مشتق می‌شود (نه یک ورودیِ جداگانه از کلاینت) — دقیقاً همان قاعده‌ای که
    # این کدبیس همه‌جا برای مقادیرِ مشتق‌شده اعمال می‌کند: هرگز به یک عددِ
    # اضافیِ کلاینت اعتماد نکن، وقتی می‌توان آن را از دادهٔ موثقِ سفارش
    # محاسبه کرد. سقف با ``max_shipping_tax`` تضمین می‌کند مالیاتِ ارسال هرگز
    # دوبار استرداد نشود.
    shipping_tax_amount = Decimal("0")
    if order.shipping_cost > 0 and shipping_amount > 0:
        shipping_tax_amount = min(
            max_shipping_tax,
            (shipping_amount * order.shipping_tax / order.shipping_cost).quantize(Decimal("1")),
        )

    lines = []
    items_total = Decimal("0")
    tax_amount = Decimal("0")
    for entry in line_requests:
        order_item = OrderItem.objects.filter(pk=entry["order_item_id"], order=order).first()
        if order_item is None:
            raise RefundError("این قلمِ سفارش متعلق به این سفارش نیست.")
        quantity = int(entry["quantity"])
        if quantity <= 0:
            raise RefundError("تعدادِ استرداد باید مثبت باشد.")

        already_refunded = _refunded_quantity_for_item(order_item)
        max_quantity = order_item.quantity - already_refunded
        if quantity > max_quantity:
            raise RefundError(
                f"برای «{order_item.product_name}» حداکثر {max_quantity} عدد قابل‌استرداد است."
            )

        amount = (order_item.unit_price * quantity).quantize(Decimal("1"))
        # مالیاتِ این ردیف متناسب با تعدادِ استردادشده از اسنپ‌شاتِ
        # ``OrderItem.unit_tax`` مشتق می‌شود — هرگز از نرخِ مالیاتِ فعلی
        # بازمحاسبه نمی‌شود (نگاه کنید به ADR-47: مالیاتِ استرداد همیشه از
        # روی اسنپ‌شاتِ تاریخیِ سفارش است، نه پیکربندیِ فعلیِ مالیات).
        already_refunded_tax = _refunded_tax_for_item(order_item)
        remaining_tax = max(Decimal("0"), order_item.total_tax - already_refunded_tax)
        line_tax_amount = min(remaining_tax, order_item.unit_tax * quantity)

        items_total += amount
        tax_amount += line_tax_amount
        lines.append(RefundLinePlan(
            order_item=order_item, quantity=quantity, max_quantity=max_quantity,
            amount=amount, tax_amount=line_tax_amount,
        ))

    total_amount = items_total + tax_amount + shipping_amount + shipping_tax_amount
    if total_amount <= 0:
        raise RefundError("مبلغِ استرداد باید بیشتر از صفر باشد.")
    if total_amount > max_refundable:
        raise RefundError(
            f"مبلغِ استرداد ({total_amount}) از مبلغِ قابل‌استردادِ باقی‌مانده ({max_refundable}) بیشتر است."
        )

    return RefundPlan(
        order=order, lines=lines, shipping_amount=shipping_amount, max_shipping=max_shipping,
        shipping_tax_amount=shipping_tax_amount, max_shipping_tax=max_shipping_tax,
        items_total=items_total, tax_amount=tax_amount,
        total_amount=total_amount, max_refundable=max_refundable,
    )


@transaction.atomic
def execute_order_refund(
    order: Order, *, store, actor, line_requests: list[dict], shipping_amount: Decimal = Decimal("0"),
    reason: str = Refund.Reason.CUSTOMER_REQUEST, merchant_note: str = "",
    refund_method: str = Refund.Method.MANUAL, restock: bool = False, idempotency_key: str = "",
) -> Refund:
    """یک استردادِ جدید می‌سازد و (فقط برای ``MANUAL``) بلافاصله اجرایش می‌کند.

    ``idempotency_key``: اگر استردادی با همین کلید از قبل ساخته شده، همان را
    برمی‌گرداند — بدون ساختنِ استردادِ تکراری."""
    if idempotency_key:
        existing = Refund.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if refund_method == Refund.Method.GATEWAY:
        raise RefundError(
            "اجرای خودکارِ استرداد از طریق درگاهِ پرداخت هنوز پیاده‌سازی نشده؛ "
            "فقط روشِ دستی (واریزِ خارج از سیستم) در دسترس است."
        )

    plan = plan_order_refund(order, store=store, line_requests=line_requests, shipping_amount=shipping_amount)

    refund = Refund.objects.create(
        store=store, order=order, requested_amount=plan.total_amount, approved_amount=plan.total_amount,
        shipping_refund_amount=shipping_amount, shipping_tax_refund_amount=plan.shipping_tax_amount,
        reason=reason, merchant_note=merchant_note,
        status=Refund.Status.SUCCEEDED, refund_method=refund_method, restock=restock,
        actor=actor, completed_at=timezone.now(), idempotency_key=idempotency_key,
    )
    for line in plan.lines:
        refund_item = RefundItem.objects.create(
            refund=refund, order_item=line.order_item, quantity=line.quantity,
            amount=line.amount, tax_amount=line.tax_amount,
        )
        if restock:
            try:
                restock_refund_item(store=store, refund_item=refund_item, actor=actor)
            except ReturnItemAlreadyRestockedError:
                pass  # idempotent no-op — already restocked by a prior (retried) call

    if order.payment_status == Order.PaymentStatus.PAID and refundable_amount(order) == Decimal("0"):
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=["payment_status", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="refund.completed",
        object_type="Refund", object_id=refund.pk, object_label=f"استرداد #{refund.pk} — {order.code}",
        after={"amount": str(refund.approved_amount), "method": refund_method, "restock": restock},
        request_id=idempotency_key,
    )
    return refund


def record_refund_result(refund: Refund, *, status: str, gateway_transaction_ref: str = "", failure_reason: str = "") -> Refund:
    """وضعیتِ یک استردادِ در حالِ اجرا را به‌روزرسانی می‌کند — برای یکپارچگیِ
    آینده با یک درگاهِ واقعی. پس از رسیدن به یک وضعیتِ نهایی
    (``Refund.FINAL_STATUSES``)، هیچ فیلدِ مالی‌ای دیگر قابل‌تغییر نیست."""
    if refund.status in Refund.FINAL_STATUSES:
        raise RefundError("این استرداد به وضعیتِ نهایی رسیده و دیگر قابل‌تغییر نیست.")

    refund.status = status
    if gateway_transaction_ref:
        refund.gateway_transaction_ref = gateway_transaction_ref
    if failure_reason:
        refund.failure_reason = failure_reason
    if status in Refund.FINAL_STATUSES:
        refund.completed_at = timezone.now()
    refund.save(update_fields=["status", "gateway_transaction_ref", "failure_reason", "completed_at", "updated_at"])
    return refund
