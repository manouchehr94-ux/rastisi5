"""صورتحسابِ تغییرِ پلن — بدونِ پروریشنِ جعلی (ADR-80).

سیاستِ صادقانه:
- **ارتقا** (قیمتِ هدف > قیمتِ فعلی): نیازمندِ پرداخت. یک فاکتورِ «تغییرِ پلن»
  برایِ مبلغِ کاملِ نسخه‌ی هدف ساخته و باز می‌شود؛ نسخه‌ی پلنِ اشتراک تا
  *پرداختِ کاملِ* آن فاکتور عوض نمی‌شود (تأیید در ``confirmation_service``).
- **تنزل / قیمتِ برابر**: در دوره‌ی بعد اثر می‌کند. یک ``ScheduledPlanChange``
  ثبت می‌شود که هنگامِ تولیدِ فاکتورِ تمدید اعمال می‌گردد؛ هیچ مبلغی گرفته و
  هیچ Entitlementی بلافاصله کم نمی‌شود.

محافظت در برابرِ پیش‌نمایشِ کهنه (5A) حفظ می‌شود."""

from decimal import Decimal

from django.db import transaction

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.services import plan_change_service as pcs


class PlanChangeBillingError(Exception):
    """خطای قابل‌نمایش هنگام صورتحسابِ تغییرِ پلن."""


def is_upgrade(current_version, target_version) -> bool:
    return Decimal(target_version.display_price) > Decimal(current_version.display_price)


def preview(subscription, target_version) -> dict:
    """پیش‌نمایشِ 5A را با اطلاعاتِ صورتحساب (ارتقا/تنزل + مبلغِ قابلِ‌پرداخت)
    غنی می‌کند."""
    base = pcs.preview_plan_change(subscription.store, target_version)
    upgrade = is_upgrade(base["current_version"], target_version)
    base["is_upgrade"] = upgrade
    base["billing_effect"] = "upgrade_requires_payment" if upgrade else "downgrade_next_period"
    base["payable_amount"] = Decimal(target_version.display_price) if upgrade else Decimal("0")
    return base


@transaction.atomic
def start_plan_change(subscription, target_version, *, preview_token, actor=None, now=None):
    """تغییرِ پلن را آغاز می‌کند. برایِ ارتقا ``("invoice", invoice)`` و برایِ
    تنزل ``("scheduled", scheduled_change)`` برمی‌گرداند. توکنِ کهنه رد می‌شود."""
    current = pcs.ent.get_current_subscription(subscription.store)
    if current is None:
        raise PlanChangeBillingError("اشتراکِ جاری یافت نشد.")
    # محافظتِ پیش‌نمایشِ کهنه (همان توکنِ 5A).
    expected = pcs._preview_token(current, target_version)
    if not preview_token or preview_token != expected:
        raise pcs.StalePreviewError("پیش‌نمایش دیگر معتبر نیست؛ دوباره پیش‌نمایش بگیرید.")

    if is_upgrade(current.plan_version, target_version):
        # ارتقا: فاکتورِ تغییرِ پلن؛ نسخه‌ی پلن تا پرداخت عوض نمی‌شود.
        invoice = invoice_service.create_invoice(
            current, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=target_version,
            currency=target_version.currency,
            lines=[invoice_service.plan_line_spec(
                target_version, description=f"ارتقا به {target_version.plan.name}",
            )],
            now=now,
        )
        invoice = invoice_service.open_invoice(invoice, now=now)
        record_audit_event(
            store=current.store, actor=actor, action_code="billing.plan_change_invoiced",
            object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
            after={"target_version": target_version.pk, "amount": str(invoice.grand_total)},
        )
        return "invoice", invoice

    # تنزل/برابر: زمان‌بندی برایِ دوره‌ی بعد.
    scheduled, _created = ScheduledPlanChange.objects.update_or_create(
        subscription=current,
        defaults={"store": current.store, "target_plan_version": target_version},
    )
    record_audit_event(
        store=current.store, actor=actor, action_code="billing.plan_change_scheduled",
        object_type="ScheduledPlanChange", object_id=scheduled.pk, object_label=target_version.plan.code,
        after={"target_version": target_version.pk, "effective": "next_period"},
    )
    return "scheduled", scheduled
