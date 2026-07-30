"""Checkpoint 5B commit 3 (ADR-75): payment provider abstraction (manual
provider webhook HMAC verification + event parsing) and SubscriptionPaymentAttempt
creation/retry/idempotency."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

from django.test import TestCase

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.billing.providers.base import WebhookVerificationError
from apps.billing.providers.manual import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    ManualProvider,
)
from apps.billing.services import attempt_service, invoice_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

SECRET = "test-webhook-secret"


def _open_invoice(slug, *, price="300000"):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    sub_svc.activate_subscription(sub)
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
    )
    return invoice_service.open_invoice(invoice)


def _signed_headers(body: bytes, *, timestamp=None, secret=SECRET):
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    message = timestamp.encode() + b"." + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {SIGNATURE_HEADER: sig, TIMESTAMP_HEADER: timestamp}


class ManualProviderWebhookTests(TestCase):
    def setUp(self):
        self.provider = ManualProvider()

    def test_valid_signature_accepted(self):
        body = json.dumps({"event_id": "e1", "event_type": "payment.succeeded"}).encode()
        self.assertTrue(self.provider.verify_webhook(headers=_signed_headers(body), body=body, secret=SECRET))

    def test_invalid_signature_rejected(self):
        body = b'{"event_id":"e1"}'
        headers = _signed_headers(body)
        headers[SIGNATURE_HEADER] = "deadbeef"
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers=headers, body=body, secret=SECRET)

    def test_missing_signature_rejected(self):
        body = b'{"event_id":"e1"}'
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers={}, body=body, secret=SECRET)

    def test_expired_timestamp_rejected(self):
        body = b'{"event_id":"e1"}'
        headers = _signed_headers(body, timestamp=int(time.time()) - 9999)
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers=headers, body=body, secret=SECRET)

    def test_modified_payload_rejected(self):
        body = b'{"event_id":"e1"}'
        headers = _signed_headers(body)
        tampered = b'{"event_id":"e2"}'  # signed for a different body
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers=headers, body=tampered, secret=SECRET)

    def test_no_secret_rejected(self):
        body = b'{"event_id":"e1"}'
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers=_signed_headers(body), body=body, secret="")

    def test_parse_event(self):
        body = json.dumps({
            "event_id": "evt_1", "event_type": "payment.succeeded",
            "provider_payment_id": "pay_1", "amount": "300000", "currency": "IRT",
        }).encode()
        event = self.provider.parse_webhook_event(body=body)
        self.assertEqual(event.event_id, "evt_1")
        self.assertTrue(event.succeeded)
        self.assertEqual(event.amount, Decimal("300000"))
        self.assertEqual(event.provider_payment_id, "pay_1")

    def test_parse_non_success_event(self):
        body = json.dumps({"event_id": "evt_2", "event_type": "payment.failed"}).encode()
        event = self.provider.parse_webhook_event(body=body)
        self.assertFalse(event.succeeded)


class ProviderRegistryTests(TestCase):
    def test_default_provider_is_manual(self):
        self.assertEqual(registry.active_provider_code(), "manual")
        self.assertIsInstance(registry.get_provider(), ManualProvider)

    def test_unknown_provider_raises(self):
        from apps.billing.providers.base import BillingProviderError

        with self.assertRaises(BillingProviderError):
            registry.get_provider("nonexistent")

    def test_manual_provider_does_not_auto_capture(self):
        self.assertFalse(registry.get_provider().supports_automatic_capture)


class PaymentAttemptTests(TestCase):
    def setUp(self):
        self.invoice = _open_invoice("attempt-store")

    def test_create_attempt_uses_invoice_amount(self):
        attempt = attempt_service.create_attempt(self.invoice)
        self.assertEqual(attempt.amount, self.invoice.amount_due)
        self.assertEqual(attempt.currency, "IRT")
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, SubscriptionPaymentAttempt.Status.CREATED)
        self.assertTrue(attempt.public_token)

    def test_retry_creates_new_attempt(self):
        first = attempt_service.create_attempt(self.invoice)
        second = attempt_service.create_attempt(self.invoice)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.attempt_number, 2)

    def test_idempotency_key_returns_same_attempt(self):
        first = attempt_service.create_attempt(self.invoice, idempotency_key="idem-1")
        second = attempt_service.create_attempt(self.invoice, idempotency_key="idem-1")
        self.assertEqual(first.pk, second.pk)

    def test_cannot_attempt_non_payable_invoice(self):
        # Mark invoice paid → no longer payable.
        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(
            status=SubscriptionInvoice.Status.PAID,
        )
        self.invoice.refresh_from_db()
        with self.assertRaises(attempt_service.PaymentAttemptError):
            attempt_service.create_attempt(self.invoice)

    def test_provider_payment_id_unique_when_present(self):
        from django.db import IntegrityError

        a1 = attempt_service.create_attempt(self.invoice, idempotency_key="k1")
        SubscriptionPaymentAttempt.objects.filter(pk=a1.pk).update(provider_payment_id="pay-x")
        a2 = attempt_service.create_attempt(self.invoice, idempotency_key="k2")
        with self.assertRaises(IntegrityError):
            SubscriptionPaymentAttempt.objects.filter(pk=a2.pk).update(provider_payment_id="pay-x")
