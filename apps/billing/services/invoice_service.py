"""ساخت/بازکردن/محاسبه‌ی فاکتورهایِ اشتراک (ADR-74).

قواعد کلیدی:
- فاکتور در وضعیتِ ``draft`` ساخته می‌شود؛ ردیف‌ها فقط در حالتِ draft قابلِ
  افزودن‌اند. با ``open_invoice`` فاکتور به ``open`` می‌رود، ``issued_at`` ست
  می‌شود و از آن پس ردیف‌ها و مبالغِ مالیِ تاریخی تغییرناپذیرند.
- مبالغ فقط ``Decimal``‌اند؛ جمع‌ها از ردیف‌ها محاسبه می‌شوند، نه از ورودیِ
  مرورگر.
- شماره‌ی فاکتور از ``numbering_service`` (race-safe) می‌آید.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionInvoiceLine
from apps.billing.services import numbering_service
from apps.billing.services.account_service import get_or_create_billing_account
from apps.core.services.audit_service import record_audit_event

ZERO = Decimal("0")


class InvoiceError(Exception):
    """خطای قابل‌نمایش هنگام ساخت/تغییرِ فاکتور."""


def plan_version_snapshot(plan_version) -> dict:
    """اسنپ‌شاتِ تغییرناپذیر از شرایطِ نسخه‌ی پلن برایِ درج در فاکتور."""
    return {
        "plan_code": plan_version.plan.code,
        "plan_name": plan_version.plan.name,
        "version_number": plan_version.version_number,
        "currency": plan_version.currency,
        "billing_interval": plan_version.billing_interval,
        "display_price": str(plan_version.display_price),
    }


def plan_line_spec(plan_version, *, period_start=None, period_end=None, description="") -> dict:
    """یک ردیفِ «پلن» برایِ مبلغِ نسخه‌ی پلن می‌سازد."""
    return {
        "line_type": SubscriptionInvoiceLine.LineType.PLAN,
        "description": description or f"اشتراکِ {plan_version.plan.name} (نسخه {plan_version.version_number})",
        "quantity": Decimal("1"),
        "unit_amount": Decimal(plan_version.display_price),
        "discount": ZERO,
        "tax": ZERO,
        "plan_code_snapshot": plan_version.plan.code,
        "plan_version_snapshot": plan_version_snapshot(plan_version),
        "service_period_start": period_start,
        "service_period_end": period_end,
        "metadata": {},
    }


def _build_line(invoice, spec) -> SubscriptionInvoiceLine:
    quantity = Decimal(spec.get("quantity", Decimal("1")))
    unit_amount = Decimal(spec.get("unit_amount", ZERO))
    discount = Decimal(spec.get("discount", ZERO))
    tax = Decimal(spec.get("tax", ZERO))
    subtotal = quantity * unit_amount
    total = subtotal - discount + tax
    return SubscriptionInvoiceLine(
        invoice=invoice,
        line_type=spec.get("line_type", SubscriptionInvoiceLine.LineType.PLAN),
        description=spec.get("description", ""),
        quantity=quantity, unit_amount=unit_amount, subtotal=subtotal,
        discount=discount, tax=tax, total=total,
        plan_code_snapshot=spec.get("plan_code_snapshot", ""),
        plan_version_snapshot=spec.get("plan_version_snapshot", {}),
        service_period_start=spec.get("service_period_start"),
        service_period_end=spec.get("service_period_end"),
        metadata=spec.get("metadata", {}),
    )


def recompute_totals(invoice):
    """جمع‌هایِ فاکتور را از ردیف‌هایش بازمحاسبه می‌کند (منبعِ حقیقت: ردیف‌ها)."""
    lines = list(invoice.lines.all())
    invoice.subtotal = sum((line.subtotal for line in lines), ZERO)
    invoice.discount_total = sum((line.discount for line in lines), ZERO)
    invoice.tax_total = sum((line.tax for line in lines), ZERO)
    invoice.grand_total = sum((line.total for line in lines), ZERO)
    invoice.recompute_amount_due()


@transaction.atomic
def create_invoice(subscription, *, kind, lines, plan_version=None, currency=None,
                   period_start=None, period_end=None, idempotency_key="", now=None, actor=None):
    """یک فاکتورِ draft با ردیف‌هایِ داده‌شده می‌سازد و جمع‌ها را محاسبه می‌کند.
    idempotent روی ``idempotency_key`` (به‌ازایِ فروشگاه)."""
    now = now or timezone.now()
    store = subscription.store
    plan_version = plan_version or subscription.plan_version
    currency = currency or plan_version.currency

    if idempotency_key:
        existing = SubscriptionInvoice.objects.filter(
            store=store, idempotency_key=idempotency_key,
        ).first()
        if existing is not None:
            return existing

    account = get_or_create_billing_account(store, currency=currency)

    invoice = SubscriptionInvoice(
        store=store, subscription=subscription, plan_version=plan_version,
        plan_code_snapshot=plan_version.plan.code,
        plan_version_snapshot=plan_version_snapshot(plan_version),
        billing_account_snapshot=account.snapshot(),
        number=numbering_service.next_invoice_number(now=now),
        kind=kind, status=SubscriptionInvoice.Status.DRAFT, currency=currency,
        billing_period_start=period_start, billing_period_end=period_end,
        idempotency_key=idempotency_key,
    )
    invoice.save()

    for spec in lines:
        _build_line(invoice, spec).save()
    recompute_totals(invoice)
    invoice.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    record_audit_event(
        store=store, actor=actor, action_code="billing.invoice_created",
        object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
        after={"kind": kind, "grand_total": str(invoice.grand_total), "currency": currency},
    )
    return invoice


@transaction.atomic
def open_invoice(invoice, *, due_at=None, now=None, actor=None):
    """فاکتور را از draft به open می‌برد و صدور را ثبت می‌کند. idempotent؛ روی
    فاکتورِ غیرِ draft خطا نمی‌دهد اگر از قبل open/در ادامه‌ی چرخه باشد."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != SubscriptionInvoice.Status.DRAFT:
        return locked  # از قبل صادر/در چرخه‌ی بعد — idempotent
    now = now or timezone.now()
    locked.status = SubscriptionInvoice.Status.OPEN
    locked.issued_at = now
    locked.due_at = due_at or now
    recompute_totals(locked)
    locked.save(update_fields=[
        "status", "issued_at", "due_at", "subtotal", "discount_total",
        "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.invoice_opened",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        after={"grand_total": str(locked.grand_total), "due_at": str(locked.due_at)},
    )
    return locked


@transaction.atomic
def add_line(invoice, spec, *, actor=None):
    """یک ردیف به فاکتورِ *draft* اضافه می‌کند و جمع‌ها را بازمحاسبه می‌کند.
    فاکتورِ غیرِ draft تغییرناپذیرِ مالی است و خطا می‌دهد."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != SubscriptionInvoice.Status.DRAFT:
        raise InvoiceError("فاکتورِ صادرشده تغییرناپذیر است؛ ردیفِ تازه نمی‌پذیرد.")
    _build_line(locked, spec).save()
    recompute_totals(locked)
    locked.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    return locked
