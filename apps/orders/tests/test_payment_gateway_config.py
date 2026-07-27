"""Tests for PaymentGatewayConfig model, encryption, and gateway adapters.

Covers:
- Gateway config creation and uniqueness
- Tenant isolation
- Credential encryption/decryption
- Encrypted secret is not stored as plaintext
- Incomplete gateway cannot be activated
- Adapter contract (validate_credentials, create_payment, verify_payment)
- Zibal adapter with mocked HTTP
- COD adapter
- Payment attempt model and state transitions
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.encryption import (
    CredentialEncryptionError,
    decrypt_credential,
    encrypt_credential,
    mask_credential,
    reset_fernet,
)
from apps.orders.gateways import GATEWAY_CHOICES, get_adapter
from apps.orders.gateways.base import (
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    GatewayVerificationError,
)
from apps.orders.gateways.cod import CodAdapter
from apps.orders.gateways.zibal import ZibalAdapter
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGateway,
    PaymentGatewayConfig,
    ShippingMethod,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _make_order(store):
    user = User.objects.create_user(username="testpay", password="pass12345")
    customer = Customer.objects.create(user=user, full_name="تست", phone="09120000000")
    vendor = Vendor.objects.create(store=store, name="فروشنده", slug="vendor-test-pay")
    shipping = ShippingMethod.objects.create(store=store, name="پست", slug="post-test-pay", cost=Decimal("30000"))
    gateway = PaymentGateway.objects.create(store=store, name="زیبال", slug="zibal")
    return Order.objects.create(
        code="DM-99901", store=store, customer=customer, vendor=vendor, address={},
        shipping_method=shipping, payment_gateway=gateway,
        items_total=Decimal("100000"), grand_total=Decimal("130000"),
    )


# ===========================================================================
# Encryption tests
# ===========================================================================


class EncryptionTests(TestCase):
    def setUp(self):
        reset_fernet()

    def tearDown(self):
        reset_fernet()

    def test_encrypt_decrypt_round_trip(self):
        plaintext = "merchant-abc-123"
        ciphertext = encrypt_credential(plaintext)
        self.assertNotEqual(ciphertext, plaintext)
        self.assertEqual(decrypt_credential(ciphertext), plaintext)

    def test_empty_input_returns_empty(self):
        self.assertEqual(encrypt_credential(""), "")
        self.assertEqual(encrypt_credential(None), "")
        self.assertEqual(decrypt_credential(""), "")
        self.assertEqual(decrypt_credential(None), "")

    def test_encrypted_value_is_not_plaintext(self):
        plaintext = "super-secret-merchant-id"
        ciphertext = encrypt_credential(plaintext)
        self.assertNotIn(plaintext, ciphertext)

    def test_different_plaintexts_produce_different_ciphertexts(self):
        c1 = encrypt_credential("merchant-1")
        c2 = encrypt_credential("merchant-2")
        self.assertNotEqual(c1, c2)

    def test_decrypt_with_wrong_data_raises_error(self):
        with self.assertRaises(CredentialEncryptionError):
            decrypt_credential("not-a-valid-fernet-token")

    def test_mask_credential_hides_most_characters(self):
        self.assertEqual(mask_credential("merchant-abc-123"), "************-123")
        self.assertEqual(mask_credential("ab"), "**")
        self.assertEqual(mask_credential(""), "")

    @override_settings(DEBUG=False, PAYMENT_CREDENTIAL_KEY="", _PAYMENT_DEV_KEY_ALLOWED=False)
    def test_missing_key_in_production_raises_error(self):
        reset_fernet()
        with self.assertRaises(CredentialEncryptionError):
            encrypt_credential("test")

    @override_settings(PAYMENT_CREDENTIAL_KEY="invalid-not-base64")
    def test_invalid_key_raises_error(self):
        reset_fernet()
        with self.assertRaises(CredentialEncryptionError):
            encrypt_credential("test")


# ===========================================================================
# PaymentGatewayConfig model tests
# ===========================================================================


class PaymentGatewayConfigModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        reset_fernet()

    def tearDown(self):
        reset_fernet()

    def test_create_zibal_config(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store,
            gateway_code=PaymentGatewayConfig.GatewayCode.ZIBAL,
        )
        self.assertEqual(config.gateway_code, "zibal")
        self.assertFalse(config.is_active)
        self.assertEqual(config.effective_title, "زیبال")

    def test_create_cod_config(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store,
            gateway_code=PaymentGatewayConfig.GatewayCode.COD,
        )
        self.assertEqual(config.gateway_code, "cod")
        self.assertTrue(config.is_configured)  # COD needs no creds

    def test_uniqueness_per_store_and_gateway(self):
        PaymentGatewayConfig.objects.create(
            store=self.store,
            gateway_code="zibal",
        )
        with self.assertRaises(IntegrityError):
            PaymentGatewayConfig.objects.create(
                store=self.store,
                gateway_code="zibal",
            )

    def test_different_stores_can_have_same_gateway(self):
        store2 = Store.objects.create(name="Store2", slug="store2", status="active")
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal")
        config2 = PaymentGatewayConfig.objects.create(store=store2, gateway_code="zibal")
        self.assertEqual(config2.store, store2)

    def test_set_and_get_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        config.set_credentials({"merchant": "my-merchant-id"})
        config.save()
        config.refresh_from_db()
        creds = config.get_credentials()
        self.assertEqual(creds["merchant"], "my-merchant-id")

    def test_credentials_stored_encrypted(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        config.set_credentials({"merchant": "secret-merchant-xyz"})
        config.save()
        config.refresh_from_db()
        # Raw DB field should NOT contain the plaintext
        self.assertNotIn("secret-merchant-xyz", config.encrypted_credentials)
        self.assertNotEqual(config.encrypted_credentials, "")

    def test_empty_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        config.set_credentials({})
        self.assertEqual(config.encrypted_credentials, "")
        self.assertEqual(config.get_credentials(), {})

    def test_is_configured_false_without_merchant(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        self.assertFalse(config.is_configured)

    def test_is_configured_true_with_merchant(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        config.set_credentials({"merchant": "test-merchant"})
        config.save()
        self.assertTrue(config.is_configured)

    def test_can_activate_false_without_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        self.assertFalse(config.can_activate)

    def test_can_activate_true_with_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal"
        )
        config.set_credentials({"merchant": "valid-merchant"})
        config.save()
        self.assertTrue(config.can_activate)

    def test_cod_always_configured(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="cod"
        )
        self.assertTrue(config.is_configured)
        self.assertTrue(config.can_activate)

    def test_display_title_custom(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", display_title="درگاه سفارشی"
        )
        self.assertEqual(config.effective_title, "درگاه سفارشی")

    def test_tenant_isolation_query(self):
        store2 = Store.objects.create(name="Other", slug="other-store", status="active")
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal")
        PaymentGatewayConfig.objects.create(store=store2, gateway_code="zibal")
        configs_store1 = PaymentGatewayConfig.objects.filter(store=self.store)
        self.assertEqual(configs_store1.count(), 1)


# ===========================================================================
# PaymentAttempt model tests
# ===========================================================================


class PaymentAttemptModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.order = _make_order(self.store)
        self.config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True
        )
        self.config.set_credentials({"merchant": "test"})
        self.config.save()
        reset_fernet()

    def tearDown(self):
        reset_fernet()

    def test_create_attempt_generates_public_id(self):
        attempt = PaymentAttempt.objects.create(
            store=self.store,
            order=self.order,
            gateway_config=self.config,
            amount=self.order.grand_total,
            currency="TOMAN",
        )
        self.assertTrue(attempt.public_id)
        self.assertEqual(len(attempt.public_id), 32)

    def test_amount_is_immutable_snapshot(self):
        attempt = PaymentAttempt.objects.create(
            store=self.store,
            order=self.order,
            gateway_config=self.config,
            amount=Decimal("130000"),
            currency="TOMAN",
        )
        # If order amount changes, attempt amount stays the same
        self.order.grand_total = Decimal("200000")
        self.order.save()
        attempt.refresh_from_db()
        self.assertEqual(attempt.amount, Decimal("130000"))

    def test_initial_status_is_created(self):
        attempt = PaymentAttempt.objects.create(
            store=self.store,
            order=self.order,
            gateway_config=self.config,
            amount=self.order.grand_total,
            currency="TOMAN",
        )
        self.assertEqual(attempt.status, PaymentAttempt.Status.CREATED)
        self.assertFalse(attempt.is_final)

    def test_final_statuses(self):
        attempt = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
        )
        for status in [PaymentAttempt.Status.SUCCEEDED, PaymentAttempt.Status.FAILED,
                       PaymentAttempt.Status.CANCELED, PaymentAttempt.Status.EXPIRED]:
            attempt.status = status
            self.assertTrue(attempt.is_final)

    def test_non_final_statuses(self):
        attempt = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
        )
        for status in [PaymentAttempt.Status.CREATED, PaymentAttempt.Status.REQUESTING,
                       PaymentAttempt.Status.REDIRECT_READY, PaymentAttempt.Status.PENDING]:
            attempt.status = status
            self.assertFalse(attempt.is_final)

    def test_idempotency_key_uniqueness(self):
        PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
            idempotency_key="key-123",
        )
        with self.assertRaises(IntegrityError):
            PaymentAttempt.objects.create(
                store=self.store, order=self.order, gateway_config=self.config,
                amount=self.order.grand_total, currency="TOMAN",
                idempotency_key="key-123",
            )

    def test_empty_idempotency_keys_allowed_multiple(self):
        """Empty idempotency keys should not conflict."""
        a1 = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
            idempotency_key="",
        )
        a2 = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
            idempotency_key="",
        )
        self.assertNotEqual(a1.pk, a2.pk)

    def test_multiple_attempts_for_one_order(self):
        a1 = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.FAILED,
        )
        a2 = PaymentAttempt.objects.create(
            store=self.store, order=self.order, gateway_config=self.config,
            amount=self.order.grand_total, currency="TOMAN",
        )
        self.assertEqual(self.order.payment_attempts.count(), 2)


# ===========================================================================
# Gateway adapter tests
# ===========================================================================


class GatewayRegistryTests(TestCase):
    def test_registered_codes(self):
        codes = [code for code, _ in GATEWAY_CHOICES]
        self.assertIn("zibal", codes)
        self.assertIn("cod", codes)

    def test_get_zibal_adapter(self):
        adapter = get_adapter("zibal")
        self.assertIsInstance(adapter, ZibalAdapter)
        self.assertEqual(adapter.code, "zibal")
        self.assertTrue(adapter.is_online)

    def test_get_cod_adapter(self):
        adapter = get_adapter("cod")
        self.assertIsInstance(adapter, CodAdapter)
        self.assertEqual(adapter.code, "cod")
        self.assertFalse(adapter.is_online)

    def test_unknown_code_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_adapter("nonexistent")


class CodAdapterTests(TestCase):
    def setUp(self):
        self.adapter = CodAdapter()

    def test_validate_credentials_always_empty(self):
        self.assertEqual(self.adapter.validate_credentials({}), [])
        self.assertEqual(self.adapter.validate_credentials({"any": "thing"}), [])

    def test_create_payment_returns_synthetic_track_id(self):
        result = self.adapter.create_payment(
            amount=Decimal("100000"),
            currency="TOMAN",
            callback_url="http://example.com/callback",
            credentials={},
            order_code="DM-12345",
        )
        self.assertIn("DM-12345", result.track_id)
        self.assertIsNone(result.gateway_url)

    def test_verify_payment_returns_not_success(self):
        result = self.adapter.verify_payment(
            track_id="cod-DM-12345",
            expected_amount=Decimal("100000"),
            currency="TOMAN",
            credentials={},
            callback_data={},
        )
        self.assertFalse(result.success)

    def test_build_redirect_url_empty(self):
        self.assertEqual(self.adapter.build_redirect_url("any"), "")


class ZibalAdapterTests(TestCase):
    def setUp(self):
        self.adapter = ZibalAdapter()
        self.credentials = {"merchant": "test-merchant-id"}

    def test_validate_credentials_empty_merchant(self):
        errors = self.adapter.validate_credentials({})
        self.assertEqual(len(errors), 1)
        self.assertIn("مرچنت", errors[0])

    def test_validate_credentials_valid(self):
        errors = self.adapter.validate_credentials({"merchant": "abc"})
        self.assertEqual(errors, [])

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 12345678}
        mock_post.return_value = mock_response

        result = self.adapter.create_payment(
            amount=Decimal("50000"),
            currency="TOMAN",
            callback_url="https://example.com/callback/abc",
            credentials=self.credentials,
            order_code="DM-10001",
        )

        self.assertEqual(result.track_id, "12345678")
        self.assertIn("12345678", result.gateway_url)

        # Verify the API was called with Rial amount (50000 Toman = 500000 Rial)
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(payload["amount"], 500000)
        self.assertEqual(payload["merchant"], "test-merchant-id")

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_sandbox_uses_zibal_merchant(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 99999}
        mock_post.return_value = mock_response

        self.adapter.create_payment(
            amount=Decimal("10000"),
            currency="TOMAN",
            callback_url="https://example.com/cb",
            credentials=self.credentials,
            order_code="DM-10002",
            sandbox=True,
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(payload["merchant"], "zibal")

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_connection_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("refused")

        with self.assertRaises(GatewayConnectionError):
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials=self.credentials,
                order_code="DM-ERR1",
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_timeout(self, mock_post):
        import requests as req
        mock_post.side_effect = req.Timeout("timed out")

        with self.assertRaises(GatewayConnectionError) as ctx:
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials=self.credentials,
                order_code="DM-ERR2",
            )
        self.assertEqual(ctx.exception.code, "timeout")

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_malformed_json(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        with self.assertRaises(GatewayResponseError):
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials=self.credentials,
                order_code="DM-ERR3",
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_missing_result_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"trackId": 123}  # missing 'result'
        mock_post.return_value = mock_response

        with self.assertRaises(GatewayResponseError):
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials=self.credentials,
                order_code="DM-ERR4",
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_payment_rejected_by_gateway(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 102, "message": "Merchant not found"}
        mock_post.return_value = mock_response

        with self.assertRaises(GatewayPaymentError):
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials=self.credentials,
                order_code="DM-ERR5",
            )

    def test_create_payment_no_merchant_raises_credential_error(self):
        with self.assertRaises(GatewayCredentialError):
            self.adapter.create_payment(
                amount=Decimal("10000"), currency="TOMAN",
                callback_url="http://x.com/cb", credentials={},
                order_code="DM-ERR6",
            )

    def test_build_redirect_url(self):
        url = self.adapter.build_redirect_url("987654")
        self.assertEqual(url, "https://gateway.zibal.ir/start/987654")

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 100,
            "amount": 500000,  # 50000 Toman in Rial
            "status": 1,
            "refNumber": "REF123456",
            "cardNumber": "6037-99XX-XXXX-1234",
            "message": "Paid",
        }
        mock_post.return_value = mock_response

        result = self.adapter.verify_payment(
            track_id="12345",
            expected_amount=Decimal("50000"),
            currency="TOMAN",
            credentials=self.credentials,
            callback_data={"trackId": "12345", "success": "1"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "REF123456")
        self.assertIn("1234", result.card_number)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_amount_mismatch(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 100,
            "amount": 200000,  # Different amount
            "status": 1,
            "refNumber": "REF999",
        }
        mock_post.return_value = mock_response

        with self.assertRaises(GatewayVerificationError) as ctx:
            self.adapter.verify_payment(
                track_id="12345",
                expected_amount=Decimal("50000"),  # Expected 500000 Rial
                currency="TOMAN",
                credentials=self.credentials,
                callback_data={},
            )
        self.assertEqual(ctx.exception.code, "amount_mismatch")

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_failed_result(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 202,
            "status": -1,
            "message": "Payment canceled",
        }
        mock_post.return_value = mock_response

        result = self.adapter.verify_payment(
            track_id="12345",
            expected_amount=Decimal("50000"),
            currency="TOMAN",
            credentials=self.credentials,
            callback_data={},
        )
        self.assertFalse(result.success)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_already_verified(self, mock_post):
        """Result code 201 means already verified — still success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 201,
            "amount": 500000,
            "status": 2,
            "refNumber": "REF-DUP",
        }
        mock_post.return_value = mock_response

        result = self.adapter.verify_payment(
            track_id="12345",
            expected_amount=Decimal("50000"),
            currency="TOMAN",
            credentials=self.credentials,
            callback_data={},
        )
        self.assertTrue(result.success)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_timeout(self, mock_post):
        import requests as req
        mock_post.side_effect = req.Timeout("verify timed out")

        with self.assertRaises(GatewayConnectionError):
            self.adapter.verify_payment(
                track_id="12345",
                expected_amount=Decimal("50000"),
                currency="TOMAN",
                credentials=self.credentials,
                callback_data={},
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_network_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("network")

        with self.assertRaises(GatewayConnectionError):
            self.adapter.verify_payment(
                track_id="12345",
                expected_amount=Decimal("50000"),
                currency="TOMAN",
                credentials=self.credentials,
                callback_data={},
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_payment_malformed_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("bad")
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        with self.assertRaises(GatewayResponseError):
            self.adapter.verify_payment(
                track_id="12345",
                expected_amount=Decimal("50000"),
                currency="TOMAN",
                credentials=self.credentials,
                callback_data={},
            )
