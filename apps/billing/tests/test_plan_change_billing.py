"""Checkpoint 5B commit 8 (ADR-80): plan-change billing without fake proration.
Upgrade requires a paid plan-change invoice before the plan version switches;
downgrade is scheduled for the next period; stale-preview protection retained."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    invoice_service,
    plan_change_billing_service as pcb,
    renewal_service,
)
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import subscription_service as sub_svc


def _published(code, *, price):
    plan = Plan.objects.create(code=code, name=code, is_publicly_selectable=True)
    return PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
    )


class UpgradeBillingTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="up-store", admin_subdomain="up-store")
        self.cheap = _published("up-cheap", price="100000")
        self.pricey = _published("up-pricey", price="300000")
        sub = sub_svc.create_subscription(self.store, self.cheap)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)

    def test_upgrade_creates_invoice_and_does_not_switch_until_paid(self):
        kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=self._token())
        self.assertEqual(kind, "invoice")
        self.assertEqual(invoice.kind, SubscriptionInvoice.Kind.PLAN_CHANGE)
        self.assertEqual(invoice.grand_total, Decimal("300000"))
        # Plan version NOT switched yet.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.cheap.pk)

    def test_upgrade_switches_plan_after_payment(self):
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=self._token())
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.pricey.pk)

    def test_stale_token_rejected(self):
        with self.assertRaises(pcs.StalePreviewError):
            pcb.start_plan_change(self.sub, self.pricey, preview_token="stale")

    def test_preview_reports_upgrade(self):
        preview = pcb.preview(self.sub, self.pricey)
        self.assertTrue(preview["is_upgrade"])
        self.assertEqual(preview["payable_amount"], Decimal("300000"))


class DowngradeBillingTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="dn-store", admin_subdomain="dn-store")
        self.pricey = _published("dn-pricey", price="300000")
        self.cheap = _published("dn-cheap", price="100000")
        sub = sub_svc.create_subscription(self.store, self.pricey)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=1))
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.cheap)

    def test_downgrade_is_scheduled_no_immediate_switch(self):
        kind, scheduled = pcb.start_plan_change(self.sub, self.cheap, preview_token=self._token())
        self.assertEqual(kind, "scheduled")
        self.assertIsInstance(scheduled, ScheduledPlanChange)
        # Still on the pricey plan until next period.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.pricey.pk)
        self.assertEqual(pcb.preview(self.sub, self.cheap)["payable_amount"], Decimal("0"))

    def test_scheduled_downgrade_applied_at_renewal(self):
        pcb.start_plan_change(self.sub, self.cheap, preview_token=self._token())
        renewal_service.generate_renewals(lead_days=3)
        ent.clear_entitlement_cache()
        # Renewal applied the downgrade: now on cheap, scheduled record cleared.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.cheap.pk)
        self.assertFalse(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())
        invoice = SubscriptionInvoice.objects.get(subscription=self.sub, kind=SubscriptionInvoice.Kind.RENEWAL)
        self.assertEqual(invoice.grand_total, Decimal("100000"))
