"""Checkpoint 5B commit 10: Merchant Billing UI — overview, account, invoices,
detail, printable invoice, payment start, payment result, cancellation, and
permission gating (BILLING_VIEW / BILLING_ACCOUNT_MANAGE / BILLING_PAYMENT_MANAGE
/ SUBSCRIPTION_CANCEL)."""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
HOST = f"billui.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BillingViewTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = "billui"
        self.store.save(update_fields=["admin_subdomain"])
        # akhlaghi has a legacy subscription; create an open invoice on it.
        plan = Plan.objects.create(code="billui-plan", name="Plan")
        self.version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("250000"), currency="IRT",
        )
        self.subscription = self.store.subscriptions.filter(is_current=True).first()
        self.invoice = invoice_service.create_invoice(
            self.subscription, kind=SubscriptionInvoice.Kind.RENEWAL, plan_version=self.version,
            lines=[invoice_service.plan_line_spec(self.version)], period_start=timezone.now(),
        )
        self.invoice = invoice_service.open_invoice(self.invoice)
        self.owner = self._member("bill-owner", StoreMembership.Role.OWNER)
        self.client.login(username="bill-owner", password="pass12345")

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        return user

    def _login(self, username, role):
        self._member(username, role)
        self.client.logout()
        self.client.login(username=username, password="pass12345")

    def test_owner_sees_overview(self):
        self.assertEqual(self.client.get(reverse("dashboard:billing-overview")).status_code, 200)

    def test_invoices_and_detail(self):
        self.assertEqual(self.client.get(reverse("dashboard:billing-invoices")).status_code, 200)
        resp = self.client.get(reverse("dashboard:billing-invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.invoice.number)

    def test_printable_invoice(self):
        resp = self.client.get(reverse("dashboard:billing-invoice-print", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.invoice.number)

    def test_account_edit(self):
        resp = self.client.post(reverse("dashboard:billing-account"), {
            "legal_name": "شرکتِ تست", "billing_email": "b@example.com", "city": "تهران",
        })
        self.assertEqual(resp.status_code, 302)
        self.store.billing_account.refresh_from_db()
        self.assertEqual(self.store.billing_account.legal_name, "شرکتِ تست")

    def test_pay_starts_payment_and_redirects(self):
        resp = self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAYMENT_PENDING)

    def test_payment_result_renders(self):
        self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk]))
        resp = self.client.get(reverse("dashboard:billing-payment-result"))
        self.assertEqual(resp.status_code, 200)

    def test_cancel_at_period_end(self):
        resp = self.client.post(reverse("dashboard:billing-cancel"), {"mode": "period_end"})
        self.assertEqual(resp.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)

    def test_content_editor_forbidden(self):
        self._login("bill-editor", StoreMembership.Role.CONTENT_EDITOR)
        self.assertEqual(self.client.get(reverse("dashboard:billing-overview")).status_code, 403)

    def test_analyst_can_view_but_not_pay_or_cancel(self):
        self._login("bill-analyst", StoreMembership.Role.ANALYST)
        self.assertEqual(self.client.get(reverse("dashboard:billing-invoices")).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk])).status_code, 403,
        )
        self.assertEqual(self.client.get(reverse("dashboard:billing-cancel")).status_code, 403)

    def test_administrator_can_pay_but_not_cancel(self):
        self._login("bill-admin", StoreMembership.Role.ADMINISTRATOR)
        # Payment allowed.
        self.assertEqual(
            self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk])).status_code, 302,
        )
        # Cancellation is Owner-only.
        self.assertEqual(self.client.get(reverse("dashboard:billing-cancel")).status_code, 403)

    def test_cross_store_invoice_404(self):
        other = Store.objects.create(name="B", slug="billui-other", admin_subdomain="billui-other")
        oplan = Plan.objects.create(code="other-pl", name="O")
        over = PlanVersion.objects.create(plan=oplan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        osub = sub_svc.create_subscription(other, over)
        sub_svc.activate_subscription(osub)
        oinv = invoice_service.create_invoice(
            osub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(over)],
        )
        # Owner of `akhlaghi` must not see another store's invoice.
        resp = self.client.get(reverse("dashboard:billing-invoice-detail", args=[oinv.pk]))
        self.assertEqual(resp.status_code, 404)
