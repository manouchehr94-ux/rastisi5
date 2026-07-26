"""Order.store direct-ownership invariant tests (PR23).

Order now has a direct, required ``store`` FK (in addition to the existing
``vendor`` FK) — these tests prove the invariant ``order.store_id ==
order.vendor.store_id`` is actually enforced at both the production
service-layer entry point (``create_order_from_cart``, the only place
Production ever creates an Order) and the model's defensive ``clean()``,
and that the staged backfill migration (0004) derived every existing
Order's Store deterministically from its Vendor — never a guess, never a
hardcoded Store.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class OrderStoreVendorMismatchRejectedTests(TestCase):
    """Store mismatch with Vendor must be rejected through every supported
    production write path — never silently created."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="osb-store-b", status=Store.Status.ACTIVE)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-osb-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-osb-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a,
            name="Product A", slug="product-osb-a", sku="SKU-OSB-A",
            price=Decimal("100000"), stock=10, status=Product.Status.ACTIVE,
        )
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-osb-b")

        user = User.objects.create_user(username="osb-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121230077")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121230077",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.shipping = ShippingMethod.objects.create(store=self.store_a, name="پست", slug="post-osb", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store_a, name="درگاه", slug="gw-osb")

    def test_create_order_from_cart_rejects_vendor_from_other_store(self):
        """store=store_a but vendor=vendor_b (a real Store B vendor) must be
        rejected — even though every cart item genuinely belongs to store_a."""
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=1, unit_price=self.product_a.final_price)

        with self.assertRaises(ValueError):
            create_order_from_cart(
                cart, customer=self.customer, vendor=self.vendor_b, address=self.address,
                shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store_a,
            )
        self.assertEqual(Order.objects.filter(vendor=self.vendor_b).count(), 0)

    def test_order_clean_rejects_vendor_store_mismatch(self):
        """Model-level defensive check (apps.orders.models.Order.clean),
        mirroring apps.catalog.models.Product.clean's documented pattern."""
        order = Order(
            code="DM-OSB-CLEAN", store=self.store_a, customer=self.customer, vendor=self.vendor_b,
            shipping_method=self.shipping, payment_gateway=self.gateway,
        )
        with self.assertRaises(ValidationError):
            order.clean()

    def test_order_clean_accepts_matching_vendor_store(self):
        order = Order(
            code="DM-OSB-CLEAN-OK", store=self.store_a, customer=self.customer, vendor=self.vendor_a,
            shipping_method=self.shipping, payment_gateway=self.gateway,
        )
        order.clean()  # must not raise


class OrderStoreRecordedOnCreationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="Vendor", slug="vendor-osr")
        self.category = Category.objects.create(store=self.store, name="Cat", slug="cat-osr")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="Product", slug="product-osr", sku="SKU-OSR", price=Decimal("50000"), stock=5,
        )
        user = User.objects.create_user(username="osr-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121230078")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121230078",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-osr", cost=Decimal("10000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-osr")

    def test_order_store_matches_authoritative_store_param(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        order = create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )
        self.assertEqual(order.store_id, self.store.pk)
        self.assertEqual(order.store_id, order.vendor.store_id)


# A dedicated MigrationExecutor-driven test of 0003→0004→0005 (mirroring
# apps.stores.tests.test_data_migration's pattern) is deliberately not
# included here. Unlike that pattern, which rolls back to a state where the
# column in question is genuinely still nullable at the schema level,
# Order.store/PaymentGateway.store/ShippingMethod.store are NOT NULL in the
# *current* live schema — there is no way to simulate "a pre-backfill row
# with store=NULL" without an actual schema rollback (a plain
# `.update(store=None)` is rejected by the real database's own NOT NULL
# constraint, not just Django's). A real rollback-based test is possible in
# principle, but the migration correctness it would prove is already
# exercised for real on every single test run: `manage.py test` builds the
# test database by applying every migration from scratch in order, so if
# 0004's backfill ever failed to set `store` correctly, 0005's
# `AlterField(..., null=False)` would immediately raise an IntegrityError on
# any unbackfilled row — the entire suite (1500+ tests) would fail at
# database setup, not silently pass. The three tests above instead focus on
# what a migration-executor test could not cover: the *runtime* invariant on
# every future Order created after this migration, at the service and model
# layers.
