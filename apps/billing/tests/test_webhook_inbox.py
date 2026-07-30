"""Checkpoint 5B commit 4 (ADR-76): webhook inbox + signature verification.
Adversarial coverage: invalid/missing signature, replay/duplicate, expired
timestamp, modified payload, oversized payload, foreign provider, redaction,
and the endpoint's status codes."""

import hashlib
import hmac
import json
import time

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import BillingWebhookEvent
from apps.billing.providers.base import BillingProviderError, WebhookVerificationError
from apps.billing.providers.manual import SIGNATURE_HEADER, TIMESTAMP_HEADER
from apps.billing.services import webhook_service

SECRET = "wh-secret"


def _sign(body: bytes, *, ts=None, secret=SECRET):
    ts = str(ts if ts is not None else int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {SIGNATURE_HEADER: sig, TIMESTAMP_HEADER: ts}


def _event_body(event_id="evt-1", event_type="payment.succeeded", **extra):
    payload = {"event_id": event_id, "event_type": event_type}
    payload.update(extra)
    return json.dumps(payload).encode()


@override_settings(RASTISI_BILLING_WEBHOOK_SECRET=SECRET, RASTISI_BILLING_PROVIDER="manual")
class WebhookIngestTests(TestCase):
    def test_valid_event_stored(self):
        body = _event_body()
        event = webhook_service.ingest_webhook(provider_code="manual", headers=_sign(body), body=body)
        self.assertTrue(event.signature_valid)
        self.assertEqual(event.processing_status, BillingWebhookEvent.ProcessingStatus.RECEIVED)
        self.assertEqual(event.external_event_id, "evt-1")
        self.assertTrue(event.payload_hash)

    def test_invalid_signature_stores_nothing(self):
        body = _event_body()
        headers = _sign(body)
        headers[SIGNATURE_HEADER] = "bad"
        with self.assertRaises(WebhookVerificationError):
            webhook_service.ingest_webhook(provider_code="manual", headers=headers, body=body)
        self.assertEqual(BillingWebhookEvent.objects.count(), 0)

    def test_missing_signature_stores_nothing(self):
        body = _event_body()
        with self.assertRaises(WebhookVerificationError):
            webhook_service.ingest_webhook(provider_code="manual", headers={}, body=body)
        self.assertEqual(BillingWebhookEvent.objects.count(), 0)

    def test_expired_timestamp_rejected(self):
        body = _event_body()
        with self.assertRaises(WebhookVerificationError):
            webhook_service.ingest_webhook(
                provider_code="manual", headers=_sign(body, ts=int(time.time()) - 99999), body=body,
            )

    def test_modified_payload_rejected(self):
        body = _event_body(event_id="evt-a")
        headers = _sign(body)
        tampered = _event_body(event_id="evt-b")
        with self.assertRaises(WebhookVerificationError):
            webhook_service.ingest_webhook(provider_code="manual", headers=headers, body=tampered)

    def test_duplicate_delivery_idempotent(self):
        body = _event_body(event_id="dup-1")
        first = webhook_service.ingest_webhook(provider_code="manual", headers=_sign(body), body=body)
        second = webhook_service.ingest_webhook(provider_code="manual", headers=_sign(body), body=body)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BillingWebhookEvent.objects.count(), 1)

    def test_oversized_payload_rejected(self):
        with override_settings(RASTISI_BILLING_MAX_WEBHOOK_BYTES=10):
            body = _event_body(event_id="big", junk="x" * 100)
            with self.assertRaises(webhook_service.WebhookTooLarge):
                webhook_service.ingest_webhook(provider_code="manual", headers=_sign(body), body=body)

    def test_foreign_provider_rejected(self):
        body = _event_body()
        with self.assertRaises(BillingProviderError):
            webhook_service.ingest_webhook(provider_code="nonexistent", headers=_sign(body), body=body)

    def test_sensitive_keys_redacted(self):
        body = _event_body(event_id="redact-1", card_number="6037991122334455", secret="topsecret")
        event = webhook_service.ingest_webhook(provider_code="manual", headers=_sign(body), body=body)
        self.assertEqual(event.sanitized_payload.get("card_number"), "***")
        self.assertEqual(event.sanitized_payload.get("secret"), "***")
        self.assertEqual(event.sanitized_payload.get("event_id"), "redact-1")


@override_settings(RASTISI_BILLING_WEBHOOK_SECRET=SECRET, RASTISI_BILLING_PROVIDER="manual", ALLOWED_HOSTS=["testserver"])
class WebhookEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("billing:webhook", args=["manual"])

    def _post(self, body, headers):
        extra = {}
        for key, value in headers.items():
            extra["HTTP_" + key.upper().replace("-", "_")] = value
        return self.client.post(self.url, data=body, content_type="application/json", **extra)

    def test_valid_webhook_returns_200(self):
        body = _event_body(event_id="ep-1")
        resp = self._post(body, _sign(body))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(BillingWebhookEvent.objects.filter(external_event_id="ep-1").exists())

    def test_bad_signature_returns_400(self):
        body = _event_body(event_id="ep-2")
        headers = _sign(body)
        headers[SIGNATURE_HEADER] = "bad"
        resp = self._post(body, headers)
        self.assertEqual(resp.status_code, 400)

    def test_bad_content_type_returns_400(self):
        body = _event_body(event_id="ep-3")
        extra = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in _sign(body).items()}
        resp = self.client.post(self.url, data=body, content_type="text/plain", **extra)
        self.assertEqual(resp.status_code, 400)

    def test_get_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_oversized_returns_413(self):
        with override_settings(RASTISI_BILLING_MAX_WEBHOOK_BYTES=10):
            body = _event_body(event_id="ep-big", junk="y" * 200)
            resp = self._post(body, _sign(body))
            self.assertEqual(resp.status_code, 413)
