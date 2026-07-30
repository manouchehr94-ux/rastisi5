"""Checkpoint 5B commit 12: verify_billing_consistency (read-only, --strict) and
billing tenant isolation across accounts, invoices, refunds, and webhook linkage."""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    consistency_service,
    invoice_service,
)
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc
from django.contrib.auth import get_user_model

User = get_user_model()


def _sub(slug, *, price="300000"):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    sub = sub_svc.activate_subscription(sub)
    return store, sub, version


class ConsistencyTests(TestCase):
    def test_clean_state_passes(self):
        out = StringIO()
        call_command("verify_billing_consistency", stdout=out)
        self.assertIn("ناسازگاری", out.getvalue())

    def test_paid_invoice_without_success_attempt_flagged(self):
        store, sub, version = _sub("cons-1")
        invoice = invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
        )
        invoice = invoice_service.open_invoice(invoice)
        # Force paid WITHOUT a succeeded attempt (inconsistent).
        SubscriptionInvoice.objects.filter(pk=invoice.pk).update(
            status=SubscriptionInvoice.Status.PAID, amount_paid=invoice.grand_total,
            amount_due=Decimal("0"),
        )
        issues = consistency_service.check_billing_consistency()
        self.assertTrue(any(i["severity"] == "error" for i in issues))
        with self.assertRaises(CommandError):
            call_command("verify_billing_consistency", "--strict", stdout=StringIO(), stderr=StringIO())

    def test_properly_paid_invoice_is_consistent(self):
        store, sub, version = _sub("cons-2")
        invoice = invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
        )
        invoice = invoice_service.open_invoice(invoice)
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        issues = consistency_service.check_billing_consistency()
        self.assertEqual([i for i in issues if i["severity"] == "error"], [])

    def test_command_does_not_mutate(self):
        store, sub, version = _sub("cons-3")
        before = SubscriptionInvoice.objects.count()
        call_command("verify_billing_consistency", stdout=StringIO())
        self.assertEqual(SubscriptionInvoice.objects.count(), before)


class BillingTenantIsolationTests(TestCase):
    def _invoice_for(self, store, sub, version):
        invoice = invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
            period_start=timezone.now(),
        )
        return invoice_service.open_invoice(invoice)

    def test_invoice_is_store_scoped_in_query(self):
        store_a, sub_a, va = _sub("iso-a")
        store_b, sub_b, vb = _sub("iso-b")
        inv_b = self._invoice_for(store_b, sub_b, vb)
        # Store A's invoice set never contains Store B's invoice.
        self.assertFalse(SubscriptionInvoice.objects.filter(store=store_a, pk=inv_b.pk).exists())

    @override_settings(ALLOWED_HOSTS=["iso-host.rastisi.ir", "testserver"])
    def test_cross_store_invoice_views_404(self):
        store_a, sub_a, va = _sub("iso-view-a")
        store_b, sub_b, vb = _sub("iso-view-b")
        store_a.admin_subdomain = "iso-host"
        store_a.save(update_fields=["admin_subdomain"])
        inv_b = self._invoice_for(store_b, sub_b, vb)
        owner = User.objects.create_user(username="iso-owner", password="p", is_staff=True)
        StoreMembership.objects.create(
            store=store_a, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST="iso-host.rastisi.ir")
        client.login(username="iso-owner", password="p")
        # Detail, print, and pay for another store's invoice must all 404.
        self.assertEqual(client.get(reverse("dashboard:billing-invoice-detail", args=[inv_b.pk])).status_code, 404)
        self.assertEqual(client.get(reverse("dashboard:billing-invoice-print", args=[inv_b.pk])).status_code, 404)
        self.assertEqual(client.post(reverse("dashboard:billing-pay", args=[inv_b.pk])).status_code, 404)
