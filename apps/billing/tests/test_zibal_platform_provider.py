"""Phase 3 — Zibal provider for RastiSi platform subscription billing
(apps.billing, NOT apps.orders' merchant-checkout Zibal gateway). Covers:
provider registration, credential encryption/masking, request/verify HTTP
calls (mocked — no real network), currency conversion (Toman<->Rial, single
boundary), amount-mismatch rejection, idempotent duplicate verification,
failed/cancelled verify leaves the subscription unchanged, and that browser
return alone never confirms payment."""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests as req
from django.core.cache import cache
from django.test import TestCase

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError, ProviderConnectionError, ProviderResponseError
from apps.billing.providers.zibal import ZibalBillingProvider
from apps.billing.services import attempt_service, invoice_service
from apps.billing.services.confirmation_service import ConfirmationError
from apps.billing.services.payment_flow_service import confirm_from_provider_verification
from apps.portal.models import PlatformConfiguration
from apps.portal.services.platform_config_service import get_platform_configuration
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc


def _open_invoice(slug, *, price="150000"):
    store = Store.objects.create(name="فروشگاهِ زیبال", slug=slug, admin_subdomain=slug)
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


def _configure_zibal(case, *, merchant="platform-merchant-1", sandbox=False):
    """Activates the Zibal platform-billing provider for one test. Always
    registers a cache-clear cleanup — the cached PlatformConfiguration
    singleton is process-wide (unlike the DB, it survives each test's
    transaction rollback), so leaving it pointed at "zibal" would make an
    unrelated later test in the same process attempt a real network call."""
    case.addCleanup(cache.clear)
    cache.clear()
    config = get_platform_configuration()
    config.default_payment_provider = "zibal"
    config.zibal_sandbox_mode = sandbox
    config.set_zibal_credentials(merchant=merchant)
    config.save()
    cache.clear()
    return config


class ZibalProviderRegistrationTests(TestCase):
    def test_registered_in_registry(self):
        provider = registry.get_provider("zibal")
        self.assertIsInstance(provider, ZibalBillingProvider)
        self.assertTrue(provider.supports_automatic_capture)

    def test_active_provider_code_reads_platform_configuration(self):
        _configure_zibal(self)
        self.assertEqual(registry.active_provider_code(), "zibal")

    def test_defaults_to_manual_when_not_configured(self):
        cache.clear()
        self.assertEqual(registry.active_provider_code(), "manual")


class ZibalCredentialStorageTests(TestCase):
    def test_merchant_encrypted_at_rest(self):
        config = _configure_zibal(self, merchant="super-secret-merchant-id")
        raw = PlatformConfiguration.objects.get(pk=1).encrypted_zibal_credentials
        self.assertNotIn("super-secret-merchant-id", raw)
        self.assertEqual(config.get_zibal_credentials()["merchant"], "super-secret-merchant-id")

    def test_blank_merchant_preserves_existing(self):
        _configure_zibal(self, merchant="original-merchant")
        config = get_platform_configuration()
        config.set_zibal_credentials(merchant="")
        config.save()
        config.refresh_from_db()
        self.assertEqual(config.get_zibal_credentials()["merchant"], "original-merchant")


class CreatePaymentSessionTests(TestCase):
    def setUp(self):
        _configure_zibal(self, merchant="platform-merchant-1")
        self.invoice = _open_invoice("zibal-create")
        self.attempt = attempt_service.create_attempt(self.invoice, provider="zibal")

    def test_not_configured_raises(self):
        self.addCleanup(cache.clear)
        cache.clear()
        config = get_platform_configuration()
        config.default_payment_provider = "zibal"
        config.zibal_sandbox_mode = False
        config.set_zibal_credentials(merchant="")
        config.save()
        cache.clear()
        provider = registry.get_provider("zibal")
        with self.assertRaises(BillingProviderError):
            provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_success_converts_toman_to_rial_and_builds_redirect_url(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 4242, "message": "ok"}
        mock_post.return_value = mock_response

        provider = registry.get_provider("zibal")
        session = provider.create_payment_session(
            attempt=self.attempt, invoice=self.invoice, return_url="https://rastisi.ir/billing/result/",
        )
        self.assertEqual(session.session_id, "4242")
        self.assertEqual(session.redirect_url, "https://gateway.zibal.ir/start/4242")

        sent_payload = mock_post.call_args.kwargs["json"]
        # invoice/attempt amount is 150000 Toman -> must be sent as 1,500,000 Rial.
        self.assertEqual(sent_payload["amount"], 1_500_000)
        self.assertEqual(sent_payload["merchant"], "platform-merchant-1")
        self.assertEqual(sent_payload["callbackUrl"], "https://rastisi.ir/billing/result/")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (10, 30))

    @patch("apps.billing.providers.zibal.requests.post")
    def test_sandbox_uses_sandbox_merchant_even_when_real_merchant_configured(self, mock_post):
        _configure_zibal(self, merchant="platform-merchant-1", sandbox=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 1}
        mock_post.return_value = mock_response

        provider = registry.get_provider("zibal")
        provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")
        self.assertEqual(mock_post.call_args.kwargs["json"]["merchant"], "zibal")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_rejected_result_raises_response_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 102, "message": "merchant not found"}
        mock_post.return_value = mock_response

        provider = registry.get_provider("zibal")
        with self.assertRaises(ProviderResponseError):
            provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = req.Timeout("timed out")
        provider = registry.get_provider("zibal")
        with self.assertRaises(ProviderConnectionError):
            provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_connection_error_raises_provider_connection_error(self, mock_post):
        mock_post.side_effect = req.ConnectionError("no route")
        provider = registry.get_provider("zibal")
        with self.assertRaises(ProviderConnectionError):
            provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_bad_json_raises_response_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_response.status_code = 502
        mock_post.return_value = mock_response
        provider = registry.get_provider("zibal")
        with self.assertRaises(ProviderResponseError):
            provider.create_payment_session(attempt=self.attempt, invoice=self.invoice, return_url="https://x/r")


class FetchPaymentStatusTests(TestCase):
    def setUp(self):
        _configure_zibal(self, merchant="platform-merchant-1")
        self.provider = registry.get_provider("zibal")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_success_converts_rial_back_to_toman(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "amount": 1_500_000, "message": "ok", "refNumber": "R1"}
        mock_post.return_value = mock_response

        status = self.provider.fetch_payment_status(provider_payment_id="4242")
        self.assertTrue(status.succeeded)
        self.assertEqual(status.amount, Decimal("150000"))
        self.assertEqual(status.currency, "IRT")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_already_verified_counts_as_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 201, "amount": 1_500_000}
        mock_post.return_value = mock_response
        status = self.provider.fetch_payment_status(provider_payment_id="4242")
        self.assertTrue(status.succeeded)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_not_paid_yet_is_not_success_and_does_not_raise(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 202, "message": "not paid"}
        mock_post.return_value = mock_response
        status = self.provider.fetch_payment_status(provider_payment_id="4242")
        self.assertFalse(status.succeeded)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_invalid_trackid_is_not_success_and_does_not_raise(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 203, "message": "invalid trackId"}
        mock_post.return_value = mock_response
        status = self.provider.fetch_payment_status(provider_payment_id="does-not-exist")
        self.assertFalse(status.succeeded)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_network_error_raises(self, mock_post):
        mock_post.side_effect = req.ConnectionError("down")
        with self.assertRaises(ProviderConnectionError):
            self.provider.fetch_payment_status(provider_payment_id="4242")

    def test_verify_webhook_always_unsupported(self):
        from apps.billing.providers.base import WebhookVerificationError

        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_webhook(headers={}, body=b"{}", secret="x")

    def test_refund_returns_manual_not_succeeded(self):
        result = self.provider.refund_payment(
            provider_payment_id="4242", amount=Decimal("1000"), currency="IRT", idempotency_key="k1",
        )
        self.assertFalse(result.succeeded)
        self.assertTrue(result.raw_summary.get("manual"))


class ConfirmFromProviderVerificationTests(TestCase):
    """The browser-return integration point: real server-side verify (mocked
    HTTP) feeding into the same confirm_payment() every other provider uses."""

    def setUp(self):
        _configure_zibal(self, merchant="platform-merchant-1")
        self.invoice = _open_invoice("zibal-confirm", price="150000")
        self.attempt = attempt_service.create_attempt(self.invoice, provider="zibal")
        self.attempt.provider_session_id = "9001"
        self.attempt.status = SubscriptionPaymentAttempt.Status.PENDING
        self.attempt.save(update_fields=["provider_session_id", "status", "updated_at"])

    @patch("apps.billing.providers.zibal.requests.post")
    def test_verified_success_activates_and_marks_invoice_paid(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "amount": 1_500_000, "refNumber": "REF-1"}
        mock_post.return_value = mock_response

        result = confirm_from_provider_verification(self.attempt)
        self.assertEqual(result.status, SubscriptionPaymentAttempt.Status.SUCCEEDED)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_amount_mismatch_rejected_and_invoice_unchanged(self, mock_post):
        mock_response = MagicMock()
        # Zibal reports a different (tampered/short) amount than the invoice expects.
        mock_response.json.return_value = {"result": 100, "amount": 1_000_000}
        mock_post.return_value = mock_response

        with self.assertRaises(ConfirmationError):
            confirm_from_provider_verification(self.attempt)
        self.invoice.refresh_from_db()
        self.assertNotEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_not_yet_paid_leaves_attempt_and_subscription_unchanged(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 202, "message": "not paid"}
        mock_post.return_value = mock_response

        subscription_before = StoreSubscription.objects.get(pk=self.invoice.subscription_id).status
        result = confirm_from_provider_verification(self.attempt)
        self.assertEqual(result.status, SubscriptionPaymentAttempt.Status.PENDING)
        self.assertEqual(
            StoreSubscription.objects.get(pk=self.invoice.subscription_id).status, subscription_before,
        )

    @patch("apps.billing.providers.zibal.requests.post")
    def test_duplicate_verification_is_idempotent(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "amount": 1_500_000}
        mock_post.return_value = mock_response

        confirm_from_provider_verification(self.attempt)
        call_count_after_first = mock_post.call_count
        self.attempt.refresh_from_db()
        # Second call (e.g. user refreshing the browser-return page) must not
        # re-verify with Zibal again nor double-apply the payment.
        confirm_from_provider_verification(self.attempt)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("150000"))
        self.assertEqual(mock_post.call_count, call_count_after_first)

    def test_provider_unavailable_raises_and_does_not_falsely_succeed(self):
        with patch("apps.billing.providers.zibal.requests.post") as mock_post:
            mock_post.side_effect = req.ConnectionError("down")
            with self.assertRaises(ProviderConnectionError):
                confirm_from_provider_verification(self.attempt)
        self.attempt.refresh_from_db()
        self.assertNotEqual(self.attempt.status, SubscriptionPaymentAttempt.Status.SUCCEEDED)

    def test_manual_provider_attempt_is_never_auto_confirmed(self):
        manual_invoice = _open_invoice("zibal-manual-untouched", price="90000")
        manual_attempt = attempt_service.create_attempt(manual_invoice, provider="manual")
        result = confirm_from_provider_verification(manual_attempt)
        self.assertEqual(result.status, SubscriptionPaymentAttempt.Status.CREATED)
