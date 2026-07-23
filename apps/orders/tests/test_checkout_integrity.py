"""Regression tests for checkout integrity remediations.

These tests prove:
1. Atomic rollback — no orphan Address/Order on failure
2. Unexpected exception — graceful Persian error, no 500
3. New-phone guest Cart ownership — cart merged to new customer
4. Existing-phone OTP regression — still works correctly
5. Authenticated customer regression — full purchase chain
6. SMS isolation — SMS failure does not block checkout/payment
7. Validation error — specific business errors preserved
"""

import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user, get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod, Transaction
from apps.orders.services.checkout_service import SESSION_KEY
from apps.sms.models import OtpCode, SmsLog, SmsTemplate
from apps.sms.services.backends import SmsSendResult

User = get_user_model()


class _CheckoutFixture(TestCase):
    """Shared setup for checkout integrity tests."""

    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ci")
        self.category = Category.objects.create(name="دیجیتال", slug="digital-ci")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category,
            name="هدفون بلوتوثی", slug="headphone-ci", sku="SKU-CI",
            price=Decimal("500000"), discount_percent=10, stock=10,
        )
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-ci", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="درگاه", slug="gw-ci")
        self.address_payload = {
            "receiver_name": "تست کاربر", "phone": "09121111111",
            "province": "تهران", "city": "تهران",
            "postal_code": "1415873920",
            "full_address": "تهران، خیابان ولیعصر، پلاک ۱", "note": "",
        }


class AtomicRollbackTests(_CheckoutFixture):
    """When create_order_from_cart fails, no Address/Order/OrderItem persists."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="09121111111", password="pass12345")
        self.customer = Customer.objects.create(
            user=self.user, full_name="کاربر تست", phone="09121111111"
        )
        self.client.login(username="09121111111", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 3})

    def test_no_orphan_address_on_stock_failure(self):
        """Insufficient stock rolls back Address creation atomically."""
        self.product.stock = 1
        self.product.save(update_fields=["stock"])

        addr_before = Address.objects.filter(customer=self.customer).count()
        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        # Business error shown
        self.assertEqual(resp.status_code, 200)
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertIn("کافی نیست", trigger["toast"]["message"])

        # No orphan Address
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), addr_before)

        # No Order or OrderItem
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        # Stock unchanged
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

        # Cart preserved
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.first().quantity, 3)

        # Session checkout data preserved
        self.assertIn(SESSION_KEY, self.client.session)

    def test_existing_address_not_deleted_on_failure(self):
        """Pre-existing Address rows remain untouched when finalization fails."""
        existing_addr = Address.objects.create(
            customer=self.customer, receiver_name="قبلی", phone="09121111111",
            province="تهران", city="تهران", full_address="آدرس قبلی", is_default=True,
        )

        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        # Pre-existing address still exists
        existing_addr.refresh_from_db()
        self.assertEqual(existing_addr.receiver_name, "قبلی")

        # No extra address created
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), 1)

    def test_cart_delete_failure_rolls_back_order_and_address(self):
        """If an error occurs after Order creation inside the atomic block, everything rolls back.

        This verifies the transaction boundary covers the full block: a DatabaseError
        or RuntimeError after create_order_from_cart but before commit will roll back
        Order, Address, OrderItems, and stock mutations.
        """
        from apps.orders.services import checkout_service
        from apps.orders.services.checkout_service import finalize_order, SESSION_KEY as SK

        # Prepare session with address data (normally done by save_address)
        session = self.client.session
        session[SK] = {"address": self.address_payload}
        session.save()

        cart = Cart.objects.get(customer=self.customer)

        # Patch cart.items.all().delete to raise INSIDE the atomic block
        original_delete = cart.items.all().delete

        call_count = [0]

        def exploding_delete(*args, **kwargs):
            # This runs inside transaction.atomic() after Order is created
            raise RuntimeError("simulated DB failure during cart clearing")

        with patch.object(
            cart.items.all().__class__, 'delete', side_effect=exploding_delete
        ):
            # Call finalize_order directly to test the service layer
            from django.test import RequestFactory
            from django.contrib.sessions.middleware import SessionMiddleware
            from django.contrib.auth.middleware import AuthenticationMiddleware

            factory = RequestFactory()
            request = factory.post("/checkout/pay/")
            SessionMiddleware(lambda r: None).process_request(request)
            request.session.update(session)
            request.session.save()
            request.user = self.user

            with self.assertRaises(RuntimeError):
                finalize_order(request, cart, self.customer)

        # Everything rolled back
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), 0)

        # Stock unchanged
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

        # Cart items preserved (delete was attempted but transaction rolled back)
        cart.refresh_from_db()
        self.assertEqual(cart.items.count(), 1)


class UnexpectedExceptionTests(_CheckoutFixture):
    """Unexpected exceptions produce graceful error, not raw 500."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="09121111111", password="pass12345")
        self.customer = Customer.objects.create(
            user=self.user, full_name="کاربر تست", phone="09121111111"
        )
        self.client.login(username="09121111111", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})

    @patch("apps.orders.services.order_service.create_order_from_cart")
    def test_unexpected_error_returns_htmx_error_not_500(self, mock_create):
        mock_create.side_effect = RuntimeError("forced checkout failure")

        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        # NOT a 500 — graceful response
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Redirect", resp.headers)

        # Persian generic error
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertIn("مشکلی رخ داد", trigger["toast"]["message"])
        self.assertEqual(trigger["toast"]["type"], "err")

    @patch("apps.orders.services.order_service.create_order_from_cart")
    def test_unexpected_error_preserves_cart_and_session(self, mock_create):
        mock_create.side_effect = RuntimeError("forced checkout failure")

        self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        # Cart preserved
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 1)

        # Session preserved
        self.assertIn(SESSION_KEY, self.client.session)

    @patch("apps.orders.services.order_service.create_order_from_cart")
    def test_unexpected_error_no_orphan_address(self, mock_create):
        mock_create.side_effect = RuntimeError("forced checkout failure")

        self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        # No orphan Address (rolled back by transaction.atomic)
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), 0)

    @patch("apps.orders.services.order_service.create_order_from_cart")
    def test_unexpected_error_is_logged(self, mock_create):
        mock_create.side_effect = RuntimeError("forced checkout failure")

        with self.assertLogs("apps.orders.views", level="ERROR") as cm:
            self.client.post(reverse("orders:checkout-pay"), self.address_payload)

        self.assertTrue(any("forced checkout failure" in msg for msg in cm.output))


class NewPhoneGuestCartTests(TestCase):
    """New-phone guest: Cart merged, account created, order correct."""

    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ng")
        self.category = Category.objects.create(name="دیجیتال", slug="digital-ng")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category,
            name="ماوس", slug="mouse-ng", sku="SKU-NG",
            price=Decimal("300000"), stock=10,
        )
        ShippingMethod.objects.create(name="پست", slug="post-ng", cost=Decimal("45000"))
        PaymentGateway.objects.create(name="درگاه", slug="gw-ng")

    def test_guest_cart_merged_to_new_customer(self):
        # Add to cart as guest
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        session_key = self.client.session.session_key
        self.assertTrue(Cart.objects.filter(session_key=session_key, customer__isnull=True).exists())

        # Checkout with new phone
        payload = {
            "receiver_name": "مهمان جدید", "phone": "09199999999",
            "province": "اصفهان", "city": "اصفهان",
            "postal_code": "8100000000",
            "full_address": "اصفهان، خیابان چهارباغ", "note": "",
        }
        resp = self.client.post(reverse("orders:checkout-pay"), payload)
        self.assertIn("HX-Redirect", resp.headers)

        # Account created
        customer = Customer.objects.get(phone="09199999999")
        self.assertEqual(customer.full_name, "مهمان جدید")

        # User authenticated
        self.assertTrue(get_user(self.client).is_authenticated)

        # Guest cart merged (deleted) — no orphan cart with customer=NULL
        self.assertFalse(
            Cart.objects.filter(session_key=session_key, customer__isnull=True).exists()
        )

        # Customer now owns a cart (from merge)
        self.assertTrue(Cart.objects.filter(customer=customer).exists())

        # Cart is empty after successful order
        customer_cart = Cart.objects.get(customer=customer)
        self.assertEqual(customer_cart.items.count(), 0)

        # Order belongs to new customer
        order = Order.objects.get()
        self.assertEqual(order.customer, customer)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 2)

    def test_guest_cart_no_orphan_on_success(self):
        """After successful checkout, no unintended customer=NULL carts remain."""
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})

        payload = {
            "receiver_name": "کاربر جدید", "phone": "09188888888",
            "province": "تهران", "city": "تهران",
            "postal_code": "1415873920",
            "full_address": "آدرس تست", "note": "",
        }
        self.client.post(reverse("orders:checkout-pay"), payload)

        # No orphan carts
        self.assertEqual(Cart.objects.filter(customer__isnull=True).count(), 0)


class ExistingPhoneOTPRegressionTests(TestCase):
    """Existing-phone OTP path still works after the fix."""

    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-otp")
        self.category = Category.objects.create(name="دیجیتال", slug="digital-otp")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category,
            name="کیبورد", slug="keyboard-otp", sku="SKU-OTP",
            price=Decimal("800000"), stock=8,
        )
        ShippingMethod.objects.create(name="پست", slug="post-otp", cost=Decimal("45000"))
        PaymentGateway.objects.create(name="درگاه", slug="gw-otp")
        self.owner = User.objects.create_user(username="09121111111", password="Pass12345!")
        self.existing_customer = Customer.objects.create(
            user=self.owner, full_name="صاحب حساب", phone="09121111111"
        )

    def test_otp_flow_completes_order_on_existing_account(self):
        # Add to cart as guest
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})

        # Checkout triggers OTP
        payload = {
            "receiver_name": "گیرنده", "phone": "09121111111",
            "province": "تهران", "city": "تهران",
            "postal_code": "1415873920",
            "full_address": "تهران، خیابان آزادی", "note": "",
        }
        resp = self.client.post(reverse("orders:checkout-pay"), payload)
        self.assertContains(resp, "تأیید شماره")
        self.assertEqual(Order.objects.count(), 0)

        # Verify OTP
        otp = OtpCode.objects.filter(phone="09121111111").latest("created_at")
        resp = self.client.post(reverse("orders:checkout-otp-verify"), {"code": otp.code})
        self.assertIn("HX-Redirect", resp.headers)

        # Correct customer
        self.assertTrue(get_user(self.client).is_authenticated)
        order = Order.objects.get()
        self.assertEqual(order.customer, self.existing_customer)

        # Guest cart merged
        self.assertFalse(Cart.objects.filter(customer__isnull=True).exists())

        # Payment flow
        resp = self.client.get(reverse("orders:payment-start", args=[order.code]), follow=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PROCESSING)


class AuthenticatedCustomerRegressionTests(_CheckoutFixture):
    """Authenticated customer full purchase chain still works."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="09121111111", password="pass12345")
        self.customer = Customer.objects.create(
            user=self.user, full_name="علی رضایی", phone="09121111111"
        )
        self.client.login(username="09121111111", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})

    def test_full_authenticated_purchase_chain(self):
        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        self.assertIn("HX-Redirect", resp.headers)

        order = Order.objects.get()
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 2)

        # Address created
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), 1)

        # Stock reduced
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

        # Cart empty
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 0)

        # Session checkout data cleared
        self.assertNotIn(SESSION_KEY, self.client.session)

        # Payment chain
        resp = self.client.get(reverse("orders:payment-start", args=[order.code]), follow=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertContains(resp, "پرداخت با موفقیت انجام شد")

    def test_cart_cleared_only_after_success(self):
        """Cart items deleted only inside the successful atomic block."""
        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        self.assertIn("HX-Redirect", resp.headers)

        # After success: cart is empty
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 0)
        self.assertEqual(Order.objects.count(), 1)


class SMSIsolationTests(_CheckoutFixture):
    """SMS failure does not block checkout or payment."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="09121111111", password="pass12345")
        self.customer = Customer.objects.create(
            user=self.user, full_name="تست", phone="09121111111"
        )
        self.client.login(username="09121111111", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        SmsTemplate.ensure_defaults()

    @patch("apps.sms.services.sms_service.get_backend")
    def test_sms_failure_does_not_block_order_creation(self, mock_backend):
        mock_backend.return_value.send.return_value = SmsSendResult(
            success=False, error_message="provider down"
        )

        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        self.assertIn("HX-Redirect", resp.headers)

        order = Order.objects.get()
        self.assertEqual(order.customer, self.customer)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)

    @patch("apps.sms.services.sms_service.get_backend")
    def test_sms_failure_does_not_block_payment(self, mock_backend):
        mock_backend.return_value.send.return_value = SmsSendResult(
            success=False, error_message="provider down"
        )

        self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        order = Order.objects.get()

        resp = self.client.get(reverse("orders:payment-start", args=[order.code]), follow=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(order.transactions.count(), 1)
        self.assertEqual(order.transactions.first().status, Transaction.Status.OK)


class ValidationErrorTests(_CheckoutFixture):
    """Known business errors remain specific, not replaced by generic message."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="09121111111", password="pass12345")
        self.customer = Customer.objects.create(
            user=self.user, full_name="تست", phone="09121111111"
        )
        self.client.login(username="09121111111", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 5})

    def test_insufficient_stock_shows_specific_persian_error(self):
        self.product.stock = 2
        self.product.save(update_fields=["stock"])

        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        trigger = json.loads(resp.headers["HX-Trigger"])

        # Specific business error, not generic
        self.assertIn("کافی نیست", trigger["toast"]["message"])
        self.assertNotIn("مشکلی رخ داد", trigger["toast"]["message"])

    def test_empty_cart_shows_specific_error(self):
        # Remove all items
        Cart.objects.get(customer=self.customer).items.all().delete()

        resp = self.client.post(reverse("orders:checkout-pay"), self.address_payload)
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertIn("خالی", trigger["toast"]["message"])
