"""Checkpoint 5B commit 6 (ADR-78): renewal invoice generation — one per
period, idempotent, respects cancel-at-period-end, skips terminal/none-interval
subscriptions, freezes amount/currency, store filter."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import renewal_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc


def _active_sub(slug, *, price="500000", interval=PlanVersion.BillingInterval.MONTHLY, period_end_in_days=1):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT", billing_interval=interval,
    )
    sub = sub_svc.create_subscription(store, version)
    period_end = timezone.now() + timedelta(days=period_end_in_days)
    sub = sub_svc.activate_subscription(sub, period_end=period_end)
    return store, sub, version


class RenewalGenerationTests(TestCase):
    def test_generates_one_renewal_near_period_end(self):
        store, sub, version = _active_sub("rn-1", period_end_in_days=1)
        result = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(result["created"], 1)
        invoice = SubscriptionInvoice.objects.get(subscription=sub, kind=SubscriptionInvoice.Kind.RENEWAL)
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.OPEN)
        self.assertEqual(invoice.grand_total, Decimal("500000"))
        self.assertEqual(invoice.currency, "IRT")
        self.assertEqual(invoice.billing_period_start, sub.current_period_end)

    def test_idempotent_no_duplicate(self):
        store, sub, version = _active_sub("rn-2", period_end_in_days=1)
        renewal_service.generate_renewals(lead_days=3)
        second = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped_existing"], 1)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(subscription=sub, kind=SubscriptionInvoice.Kind.RENEWAL).count(), 1
        )

    def test_far_from_period_end_not_generated(self):
        store, sub, version = _active_sub("rn-3", period_end_in_days=30)
        result = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(result["scanned"], 0)

    def test_cancel_at_period_end_skipped(self):
        store, sub, version = _active_sub("rn-4", period_end_in_days=1)
        sub_svc.cancel_at_period_end(sub)
        result = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(result["scanned"], 0)

    def test_terminal_subscription_skipped(self):
        store, sub, version = _active_sub("rn-5", period_end_in_days=1)
        sub_svc.cancel_immediately(sub)
        result = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(result["scanned"], 0)

    def test_none_interval_skipped(self):
        store, sub, version = _active_sub("rn-6", interval=PlanVersion.BillingInterval.NONE, period_end_in_days=1)
        result = renewal_service.generate_renewals(lead_days=3)
        self.assertEqual(result["scanned"], 0)

    def test_store_filter(self):
        store_a, sub_a, _ = _active_sub("rn-a", period_end_in_days=1)
        store_b, sub_b, _ = _active_sub("rn-b", period_end_in_days=1)
        renewal_service.generate_renewals(lead_days=3, store=store_a)
        self.assertTrue(SubscriptionInvoice.objects.filter(subscription=sub_a).exists())
        self.assertFalse(SubscriptionInvoice.objects.filter(subscription=sub_b).exists())

    def test_command_runs(self):
        _active_sub("rn-cmd", period_end_in_days=1)
        out = StringIO()
        call_command("generate_subscription_renewals", "--lead-days", "3", stdout=out)
        self.assertIn("ساخته‌شده", out.getvalue())
