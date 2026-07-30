"""Checkpoint 5B commit 1 (ADR-73/74): StoreBillingAccount (one per store,
snapshot, tenant-scoped, editable) and SubscriptionInvoice model constraints
(non-negative amounts, amount_paid <= grand_total, one renewal per period,
unique number)."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import StoreBillingAccount, SubscriptionInvoice
from apps.billing.services import account_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc


def _store(slug):
    return Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)


def _subscription(store):
    plan = Plan.objects.create(code=f"pl-{store.slug}", name="P")
    version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
    sub = sub_svc.create_subscription(store, version)
    sub_svc.activate_subscription(sub)
    return sub, version


class BillingAccountTests(TestCase):
    def setUp(self):
        self.store = _store("ba-store")

    def test_get_or_create_is_idempotent(self):
        a = account_service.get_or_create_billing_account(self.store)
        b = account_service.get_or_create_billing_account(self.store)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(StoreBillingAccount.objects.filter(store=self.store).count(), 1)

    def test_update_editable_fields_and_snapshot(self):
        account = account_service.update_billing_account(
            self.store, legal_name="شرکتِ نمونه", billing_email="b@example.com", city="تهران",
        )
        self.assertEqual(account.legal_name, "شرکتِ نمونه")
        snap = account.snapshot()
        self.assertEqual(snap["legal_name"], "شرکتِ نمونه")
        self.assertEqual(snap["city"], "تهران")
        self.assertIn("currency", snap)

    def test_currency_not_changed_via_update(self):
        account = account_service.update_billing_account(self.store, currency="USD", legal_name="X")
        # currency is not an editable field → stays default.
        self.assertEqual(account.currency, "IRT")

    def test_one_account_per_store(self):
        StoreBillingAccount.objects.create(store=self.store)
        with self.assertRaises(IntegrityError):
            StoreBillingAccount.objects.create(store=self.store)


class BillingAccountIsolationTests(TestCase):
    def test_accounts_are_store_scoped(self):
        store_a = _store("ba-iso-a")
        store_b = _store("ba-iso-b")
        account_service.update_billing_account(store_a, legal_name="A-Corp")
        account_service.update_billing_account(store_b, legal_name="B-Corp")
        self.assertEqual(account_service.get_billing_account(store_a).legal_name, "A-Corp")
        self.assertEqual(account_service.get_billing_account(store_b).legal_name, "B-Corp")


class InvoiceConstraintTests(TestCase):
    def setUp(self):
        self.store = _store("inv-store")
        self.sub, self.version = _subscription(self.store)

    def _invoice(self, number, **kwargs):
        defaults = dict(
            store=self.store, subscription=self.sub, plan_version=self.version,
            number=number, currency="IRT",
        )
        defaults.update(kwargs)
        return SubscriptionInvoice.objects.create(**defaults)

    def test_unique_number(self):
        self._invoice("INV-1")
        with self.assertRaises(IntegrityError):
            self._invoice("INV-1")

    def test_negative_amount_rejected(self):
        with self.assertRaises(IntegrityError):
            self._invoice("INV-NEG", grand_total=Decimal("-1"))

    def test_amount_paid_cannot_exceed_grand_total(self):
        with self.assertRaises(IntegrityError):
            self._invoice("INV-OVER", grand_total=Decimal("100"), amount_paid=Decimal("101"))

    def test_one_renewal_invoice_per_period(self):
        period_start = timezone.now()
        self._invoice("INV-R1", kind=SubscriptionInvoice.Kind.RENEWAL, billing_period_start=period_start)
        with self.assertRaises(IntegrityError):
            self._invoice("INV-R2", kind=SubscriptionInvoice.Kind.RENEWAL, billing_period_start=period_start)

    def test_plan_change_invoice_not_blocked_by_renewal_constraint(self):
        period_start = timezone.now()
        self._invoice("INV-R", kind=SubscriptionInvoice.Kind.RENEWAL, billing_period_start=period_start)
        # A plan-change invoice in the same period is allowed (constraint is
        # scoped to renewal invoices only).
        pc = self._invoice("INV-PC", kind=SubscriptionInvoice.Kind.PLAN_CHANGE, billing_period_start=period_start)
        self.assertEqual(pc.kind, SubscriptionInvoice.Kind.PLAN_CHANGE)

    def test_recompute_amount_due(self):
        inv = self._invoice("INV-DUE", grand_total=Decimal("500"), amount_paid=Decimal("200"))
        inv.recompute_amount_due()
        self.assertEqual(inv.amount_due, Decimal("300"))
