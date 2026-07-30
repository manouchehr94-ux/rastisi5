"""Checkpoint 5B commit 7 (ADR-79/80): dunning schedule progression (grace ->
... -> suspension), no duplicate advance, paid/void invoices skipped, and
cancellation billing (void unpaid invoices, preserve paid ones)."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import (
    SubscriptionDunningState,
    SubscriptionInvoice,
)
from apps.billing.services import cancellation_service, dunning_service, invoice_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc


def _sub_with_open_invoice(slug, *, price="500000", due_days_ago=1):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
    )
    sub = sub_svc.create_subscription(store, version)
    sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
        period_start=timezone.now(),
    )
    due = timezone.now() - timedelta(days=due_days_ago)
    invoice = invoice_service.open_invoice(invoice, due_at=due)
    return store, sub, version, invoice


@override_settings(RASTISI_BILLING_DUNNING_SCHEDULE="0,3,7,14")
class DunningTests(TestCase):
    def test_first_tick_past_dues_invoice_and_grace_subscription(self):
        store, sub, version, invoice = _sub_with_open_invoice("dn-1", due_days_ago=1)
        dunning_service.process_dunning()
        invoice.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAST_DUE)
        self.assertEqual(sub.status, StoreSubscription.Status.GRACE_PERIOD)
        state = SubscriptionDunningState.objects.get(invoice=invoice)
        self.assertEqual(state.attempt_count, 1)

    def test_no_duplicate_advance_before_next_retry(self):
        store, sub, version, invoice = _sub_with_open_invoice("dn-2", due_days_ago=1)
        dunning_service.process_dunning()
        # Immediately running again must not advance (next_retry_at is in future).
        dunning_service.process_dunning()
        state = SubscriptionDunningState.objects.get(invoice=invoice)
        self.assertEqual(state.attempt_count, 1)

    def test_final_stage_suspends_and_marks_uncollectible(self):
        store, sub, version, invoice = _sub_with_open_invoice("dn-3", due_days_ago=20)
        # Run repeatedly at "now" far past due; each run advances one stage until final.
        for _ in range(5):
            dunning_service.process_dunning()
        invoice.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.UNCOLLECTIBLE)
        self.assertEqual(sub.status, StoreSubscription.Status.SUSPENDED)
        state = SubscriptionDunningState.objects.get(invoice=invoice)
        self.assertEqual(state.status, SubscriptionDunningState.Status.EXHAUSTED)

    def test_paid_invoice_not_dunned(self):
        store, sub, version, invoice = _sub_with_open_invoice("dn-4", due_days_ago=1)
        SubscriptionInvoice.objects.filter(pk=invoice.pk).update(
            status=SubscriptionInvoice.Status.PAID, amount_paid=invoice.grand_total, amount_due=Decimal("0"),
        )
        result = dunning_service.process_dunning()
        self.assertEqual(result["scanned"], 0)

    def test_command_runs(self):
        _sub_with_open_invoice("dn-cmd", due_days_ago=1)
        out = StringIO()
        call_command("process_subscription_dunning", stdout=out)
        self.assertIn("بررسی‌شده", out.getvalue())


class CancellationBillingTests(TestCase):
    def test_immediate_cancel_voids_unpaid_preserves_paid(self):
        store, sub, version, unpaid = _sub_with_open_invoice("cn-1", due_days_ago=0)
        # A separately paid invoice must be preserved.
        paid = invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)],
        )
        paid = invoice_service.open_invoice(paid)
        SubscriptionInvoice.objects.filter(pk=paid.pk).update(
            status=SubscriptionInvoice.Status.PAID, amount_paid=paid.grand_total, amount_due=Decimal("0"),
        )
        cancellation_service.cancel_subscription_billing(sub, immediate=True)
        unpaid.refresh_from_db()
        paid.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(unpaid.status, SubscriptionInvoice.Status.VOID)
        self.assertEqual(paid.status, SubscriptionInvoice.Status.PAID)  # preserved
        self.assertEqual(sub.status, StoreSubscription.Status.CANCELLED)

    def test_cancel_at_period_end_keeps_active_and_voids_unpaid(self):
        store, sub, version, unpaid = _sub_with_open_invoice("cn-2", due_days_ago=0)
        cancellation_service.cancel_subscription_billing(sub, immediate=False)
        unpaid.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(unpaid.status, SubscriptionInvoice.Status.VOID)
        self.assertTrue(sub.cancel_at_period_end)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)

    def test_cannot_void_paid_invoice(self):
        store, sub, version, invoice = _sub_with_open_invoice("cn-3", due_days_ago=0)
        SubscriptionInvoice.objects.filter(pk=invoice.pk).update(status=SubscriptionInvoice.Status.PAID)
        invoice.refresh_from_db()
        with self.assertRaises(invoice_service.InvoiceError):
            invoice_service.void_invoice(invoice)
