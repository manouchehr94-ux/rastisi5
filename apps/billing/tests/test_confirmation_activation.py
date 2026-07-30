"""Checkpoint 5B commit 5 (ADR-77): transactional payment confirmation and
subscription activation/renewal. Covers idempotency, amount/currency mismatch
rejection, trial/pending → active on first paid invoice, renewal period
extension, and the end-to-end signed-webhook → activation path."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import (
    BillingWebhookEvent,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.providers.manual import SIGNATURE_HEADER, TIMESTAMP_HEADER
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    invoice_service,
    payment_flow_service,
)
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc

SECRET = "confirm-secret"


def _setup(slug, *, price="400000", start_status="trialing", kind=None):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
        trial_days=14,
    )
    sub = sub_svc.create_subscription(store, version)
    if start_status == "trialing":
        sub = sub_svc.start_trial(sub)
    elif start_status == "active":
        sub = sub_svc.activate_subscription(sub)
    invoice = invoice_service.create_invoice(
        sub, kind=kind or SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)],
    )
    invoice = invoice_service.open_invoice(invoice)
    return store, sub, version, invoice


class ConfirmPaymentTests(TestCase):
    def test_confirm_marks_paid_and_activates_from_trial(self):
        store, sub, version, invoice = _setup("cf-1", start_status="trialing",
                                              kind=SubscriptionInvoice.Kind.INITIAL)
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(
            attempt=attempt, amount=invoice.amount_due, currency="IRT", provider_payment_id="pay-1",
        )
        invoice.refresh_from_db()
        attempt.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(attempt.status, SubscriptionPaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertIsNotNone(sub.current_period_end)

    def test_confirmation_is_idempotent(self):
        store, sub, version, invoice = _setup("cf-2", kind=SubscriptionInvoice.Kind.INITIAL)
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        invoice.refresh_from_db()
        # Paid exactly once — amount_paid never doubled.
        self.assertEqual(invoice.amount_paid, Decimal("400000"))

    def test_amount_mismatch_rejected(self):
        store, sub, version, invoice = _setup("cf-3")
        attempt = attempt_service.create_attempt(invoice)
        with self.assertRaises(confirmation_service.ConfirmationError):
            confirmation_service.confirm_payment(attempt=attempt, amount=Decimal("1"), currency="IRT")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.OPEN)

    def test_currency_mismatch_rejected(self):
        store, sub, version, invoice = _setup("cf-4")
        attempt = attempt_service.create_attempt(invoice)
        with self.assertRaises(confirmation_service.ConfirmationError):
            confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="USD")

    def test_renewal_extends_period(self):
        store, sub, version, invoice = _setup("cf-5", start_status="active",
                                              kind=SubscriptionInvoice.Kind.RENEWAL)
        sub.refresh_from_db()
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertIsNotNone(sub.current_period_end)
        self.assertTrue(
            StoreSubscription.objects.get(pk=sub.pk).events.filter(event_type="renewed").exists()
        )


@override_settings(RASTISI_BILLING_WEBHOOK_SECRET=SECRET, RASTISI_BILLING_PROVIDER="manual",
                   ALLOWED_HOSTS=["testserver"])
class WebhookToActivationTests(TestCase):
    def test_signed_webhook_activates_subscription(self):
        store, sub, version, invoice = _setup("wh-act", start_status="trialing",
                                              kind=SubscriptionInvoice.Kind.INITIAL)
        attempt, session = payment_flow_service.start_payment(
            invoice, return_url="https://example.test/return",
        )
        # The provider (manual) never auto-succeeds; a signed webhook confirms.
        body = json.dumps({
            "event_id": "wh-evt-1", "event_type": "payment.succeeded",
            "session_id": session.session_id, "provider_payment_id": "pay-xyz",
            "amount": str(attempt.amount), "currency": "IRT",
        }).encode()
        ts = str(int(time.time()))
        sig = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        resp = Client().post(
            reverse("billing:webhook", args=["manual"]), data=body, content_type="application/json",
            **{"HTTP_" + SIGNATURE_HEADER.upper().replace("-", "_"): sig,
               "HTTP_" + TIMESTAMP_HEADER.upper().replace("-", "_"): ts},
        )
        self.assertEqual(resp.status_code, 200)
        invoice.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        event = BillingWebhookEvent.objects.get(external_event_id="wh-evt-1")
        self.assertEqual(event.processing_status, BillingWebhookEvent.ProcessingStatus.PROCESSED)

    def test_duplicate_webhook_does_not_double_apply(self):
        store, sub, version, invoice = _setup("wh-dup", kind=SubscriptionInvoice.Kind.INITIAL)
        attempt, session = payment_flow_service.start_payment(
            invoice, return_url="https://example.test/return",
        )
        body = json.dumps({
            "event_id": "wh-dup-1", "event_type": "payment.succeeded",
            "session_id": session.session_id, "provider_payment_id": "pay-dup",
            "amount": str(attempt.amount), "currency": "IRT",
        }).encode()
        ts = str(int(time.time()))
        sig = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        headers = {"HTTP_" + SIGNATURE_HEADER.upper().replace("-", "_"): sig,
                   "HTTP_" + TIMESTAMP_HEADER.upper().replace("-", "_"): ts}
        url = reverse("billing:webhook", args=["manual"])
        Client().post(url, data=body, content_type="application/json", **headers)
        Client().post(url, data=body, content_type="application/json", **headers)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, invoice.grand_total)
        self.assertEqual(BillingWebhookEvent.objects.filter(external_event_id="wh-dup-1").count(), 1)
