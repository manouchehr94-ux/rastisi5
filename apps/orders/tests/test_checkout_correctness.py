"""Checkout revalidation, idempotency, and inventory-locking tests (PR23).

Covers requirements not already exercised by
apps.orders.tests.test_checkout_integrity.py:

* order-time revalidation of Product publication/status and Variant
  activity (previously only checked once, at cart-add time — a Product
  could be unpublished after being added to cart and still be orderable);
* checkout idempotency (a real mechanism now exists — Cart.checkout_token —
  replacing the old "random code + .exists()" non-mechanism);
* the stock TOCTOU race close (select_for_update + conditional decrement);
* OrderItem snapshot fields (sku, variant_label) surviving later
  Product/Variant changes.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.catalog.services.variant_service import create_variant
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.orders.services.checkout_service import get_or_create_checkout_token
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class _OrderCreationFixture(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cc")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-cc")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="هدفون", slug="headphone-cc", sku="SKU-CC1",
            price=Decimal("500000"), stock=10, status=Product.Status.ACTIVE,
        )
        user = User.objects.create_user(username="cc-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121230080")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121230080",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-cc", cost=Decimal("10000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-cc")

    def _cart_with_item(self, quantity=1, variant=None):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product, variant=variant, quantity=quantity,
            unit_price=self.product.final_price,
        )
        return cart

    def _create(self, cart, **kwargs):
        return create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store, **kwargs
        )


class ProductRevalidationTests(_OrderCreationFixture):
    def test_product_deactivated_after_cart_add_is_rejected_at_order_time(self):
        cart = self._cart_with_item()
        self.product.status = Product.Status.INACTIVE
        self.product.save(update_fields=["status"])

        with self.assertRaises(ValueError):
            self._create(cart)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # unchanged

    def test_product_set_to_draft_after_cart_add_is_rejected_at_order_time(self):
        cart = self._cart_with_item()
        self.product.status = Product.Status.DRAFT
        self.product.save(update_fields=["status"])

        with self.assertRaises(ValueError):
            self._create(cart)
        self.assertEqual(Order.objects.count(), 0)

    def test_active_product_still_orderable(self):
        cart = self._cart_with_item()
        order = self._create(cart)
        self.assertEqual(order.items.count(), 1)


class VariantRevalidationTests(_OrderCreationFixture):
    def setUp(self):
        super().setUp()
        self.variant = create_variant(self.product, attribute="رنگ", value="قرمز")

    def test_variant_deactivated_after_cart_add_is_rejected_at_order_time(self):
        cart = self._cart_with_item(variant=self.variant)
        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])

        with self.assertRaises(ValueError):
            self._create(cart)
        self.assertEqual(Order.objects.count(), 0)

    def test_active_variant_still_orderable_and_snapshotted(self):
        cart = self._cart_with_item(variant=self.variant)
        order = self._create(cart)
        item = order.items.first()
        self.assertEqual(item.variant_id, self.variant.pk)
        self.assertEqual(item.variant_label, "رنگ: قرمز")
        self.assertEqual(item.sku, self.product.sku)


class OrderSnapshotSurvivesLaterChangesTests(_OrderCreationFixture):
    def setUp(self):
        super().setUp()
        self.variant = create_variant(self.product, attribute="رنگ", value="سبز", sku="VAR-CC-GREEN")

    def test_sku_and_variant_label_survive_product_and_variant_changes(self):
        cart = self._cart_with_item(variant=self.variant)
        order = self._create(cart)
        item = order.items.first()
        original_sku = item.sku
        original_label = item.variant_label
        self.assertEqual(original_sku, "SKU-CC1")
        self.assertEqual(original_label, "رنگ: سبز")

        # Change the live Product/Variant after the order was placed.
        self.product.sku = "SKU-CC1-RENAMED"
        self.product.name = "هدفون جدید"
        self.product.save(update_fields=["sku", "name"])
        self.variant.value = "بنفش"
        self.variant.save()

        item.refresh_from_db()
        self.assertEqual(item.sku, original_sku)
        self.assertEqual(item.variant_label, original_label)
        self.assertEqual(item.product_name, "هدفون")  # snapshot, not "هدفون جدید"

    def test_order_survives_product_deletion(self):
        cart = self._cart_with_item(variant=self.variant)
        order = self._create(cart)
        item = order.items.first()
        self.product.delete()
        item.refresh_from_db()
        self.assertIsNone(item.product_id)
        self.assertEqual(item.product_name, "هدفون")
        self.assertEqual(item.sku, "SKU-CC1")


class InsufficientStockLockedPathTests(_OrderCreationFixture):
    def test_insufficient_stock_rejects_order_creation_and_does_not_decrement(self):
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        cart = self._cart_with_item(quantity=5)

        with self.assertRaises(ValueError):
            self._create(cart)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    def test_stock_decremented_exactly_once(self):
        cart = self._cart_with_item(quantity=3)
        self._create(cart)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_stock_never_goes_negative(self):
        self.product.stock = 2
        self.product.save(update_fields=["stock"])
        cart = self._cart_with_item(quantity=2)
        self._create(cart)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_rollback_on_downstream_failure_restores_stock(self):
        """If something fails after the per-item stock decrement but before
        the transaction commits, the whole atomic block rolls back — stock
        is restored to its original value, not left partially decremented."""
        cart = self._cart_with_item(quantity=2)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                order = self._create(cart)
                self.assertEqual(order.items.count(), 1)
                raise RuntimeError("simulated failure after order creation")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)


class CheckoutIdempotencyServiceTests(_OrderCreationFixture):
    def test_second_call_with_same_token_returns_first_order_not_a_new_one(self):
        cart = self._cart_with_item(quantity=1)
        token = get_or_create_checkout_token(cart)

        order1 = self._create(cart, idempotency_key=token)
        # Re-add an item (simulating the cart being reused, though normally
        # finalize_order deletes items after success) and call again with
        # the SAME token.
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        order2 = self._create(cart, idempotency_key=token)

        self.assertEqual(order1.pk, order2.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.filter(order=order1).count(), 1)

    def test_second_call_does_not_decrement_stock_again(self):
        cart = self._cart_with_item(quantity=2)
        token = get_or_create_checkout_token(cart)
        self._create(cart, idempotency_key=token)
        self.product.refresh_from_db()
        stock_after_first = self.product.stock

        CartItem.objects.create(cart=cart, product=self.product, quantity=2, unit_price=self.product.final_price)
        self._create(cart, idempotency_key=token)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_after_first)

    def test_different_tokens_create_different_orders(self):
        cart = self._cart_with_item(quantity=1)
        order1 = self._create(cart, idempotency_key="token-one")
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        order2 = self._create(cart, idempotency_key="token-two")
        self.assertNotEqual(order1.pk, order2.pk)
        self.assertEqual(Order.objects.count(), 2)

    def test_concurrent_race_simulated_via_preexisting_conflicting_order(self):
        """Simulates the true-concurrency race deterministically: an Order
        with the same idempotency_key already exists (as if a parallel
        request won the race) by the time this call reaches the database
        INSERT — the IntegrityError-and-refetch path must return that
        existing Order instead of raising, creating a duplicate, or
        double-decrementing stock."""
        cart = self._cart_with_item(quantity=2)
        token = "race-token"
        winner = Order.objects.create(
            code="DM-RACEWIN", store=self.store, customer=self.customer, vendor=self.vendor,
            idempotency_key=token, address={}, shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("500000"),
        )
        OrderItem.objects.create(
            order=winner, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=self.product.final_price, line_total=self.product.final_price * 2,
        )
        # The winner already "decremented" stock in this simulation.
        stock_before_loser_attempt = self.product.stock

        loser_result = self._create(cart, idempotency_key=token)

        self.assertEqual(loser_result.pk, winner.pk)
        self.assertEqual(Order.objects.filter(idempotency_key=token).count(), 1)
        self.assertEqual(OrderItem.objects.filter(order=winner).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_before_loser_attempt)


class CheckoutIdempotencyHttpTests(_OrderCreationFixture):
    """Sequential double-submission through the real HTTP checkout view —
    the double-click / browser-retry scenario."""

    def setUp(self):
        super().setUp()
        self.client.login(username="cc-user", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.payload = {
            "receiver_name": "مشتری", "phone": "09121230080", "province": "تهران",
            "city": "تهران", "postal_code": "1111111111",
            "full_address": "خیابان آزادی", "note": "",
        }

    def test_duplicate_submission_creates_exactly_one_order(self):
        resp1 = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertIn("HX-Redirect", resp1.headers)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()

        # Second POST — same session/cart, cart already emptied by the
        # first successful submission (simulating a double-click/retry
        # arriving after the first request already completed).
        resp2 = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertEqual(Order.objects.count(), 1)
        self.assertIn(order.code, resp2.headers.get("HX-Redirect", ""))
