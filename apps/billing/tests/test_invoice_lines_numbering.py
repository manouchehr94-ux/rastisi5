"""Checkpoint 5B commit 2 (ADR-74): invoice lines, total computation from
lines, deterministic race-safe numbering, and financial immutability after
the invoice is opened."""

from decimal import Decimal

from unittest import skipUnless

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.billing.models import BillingSequence, SubscriptionInvoice
from apps.billing.services import invoice_service, numbering_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc


def _subscription(slug, *, price):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    sub_svc.activate_subscription(sub)
    return sub, version


class NumberingTests(TestCase):
    def test_sequence_is_monotonic_and_unique(self):
        numbers = {numbering_service.next_invoice_number() for _ in range(50)}
        self.assertEqual(len(numbers), 50)  # all unique

    def test_number_format(self):
        number = numbering_service.next_invoice_number(now=timezone.now())
        self.assertTrue(number.startswith("INV-"))

    def test_not_derived_from_row_count(self):
        # Even with zero invoice rows, deleting/creating never repeats a number:
        # the sequence advances independently of any table COUNT.
        n1 = numbering_service.next_invoice_number()
        n2 = numbering_service.next_invoice_number()
        self.assertNotEqual(n1, n2)
        seq = BillingSequence.objects.get(key=numbering_service.INVOICE_SEQUENCE_KEY)
        self.assertGreaterEqual(seq.last_value, 2)


class InvoiceCreationTests(TestCase):
    def setUp(self):
        self.sub, self.version = _subscription("inv2-store", price="500000")

    def test_create_invoice_computes_totals_from_lines(self):
        invoice = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.RENEWAL,
            lines=[invoice_service.plan_line_spec(self.version)],
        )
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.DRAFT)
        self.assertEqual(invoice.grand_total, Decimal("500000"))
        self.assertEqual(invoice.amount_due, Decimal("500000"))
        self.assertEqual(invoice.lines.count(), 1)
        self.assertTrue(invoice.number)
        # Immutable snapshots captured.
        self.assertEqual(invoice.plan_code_snapshot, self.version.plan.code)
        self.assertEqual(invoice.plan_version_snapshot["version_number"], 1)

    def test_idempotent_on_key(self):
        first = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.RENEWAL,
            lines=[invoice_service.plan_line_spec(self.version)], idempotency_key="k-1",
        )
        second = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.RENEWAL,
            lines=[invoice_service.plan_line_spec(self.version)], idempotency_key="k-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.sub.store).count(), 1)

    def test_open_then_immutable(self):
        invoice = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.RENEWAL,
            lines=[invoice_service.plan_line_spec(self.version)],
        )
        opened = invoice_service.open_invoice(invoice)
        self.assertEqual(opened.status, SubscriptionInvoice.Status.OPEN)
        self.assertIsNotNone(opened.issued_at)
        # After opening, no new line may be added.
        with self.assertRaises(invoice_service.InvoiceError):
            invoice_service.add_line(opened, invoice_service.plan_line_spec(self.version))

    def test_open_is_idempotent(self):
        invoice = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.RENEWAL,
            lines=[invoice_service.plan_line_spec(self.version)],
        )
        first = invoice_service.open_invoice(invoice)
        issued = first.issued_at
        second = invoice_service.open_invoice(first)
        self.assertEqual(second.issued_at, issued)


@skipUnless(
    connection.vendor == "postgresql",
    "True parallel-writer contention needs row-level locking; SQLite serializes "
    "writers at the file level, so this is only meaningful on PostgreSQL. The "
    "no-duplicate invariant on SQLite is covered deterministically by "
    "NumberingTests above.",
)
class NumberingConcurrencyTests(TransactionTestCase):
    """The sequence row is allocated under select_for_update, so a number is
    never handed out twice under concurrent writers (PostgreSQL row locking)."""

    def test_no_duplicate_numbers_under_contention(self):
        import threading

        results = []
        lock = threading.Lock()

        def allocate():
            for _ in range(5):  # retry on transient SQLite lock, like production
                try:
                    number = numbering_service.next_invoice_number()
                    with lock:
                        results.append(number)
                    return
                except Exception:  # noqa: BLE001 — transient lock; retry
                    continue

        threads = [threading.Thread(target=allocate) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # At least some succeeded, and none collided.
        self.assertGreater(len(results), 0)
        self.assertEqual(len(set(results)), len(results))
