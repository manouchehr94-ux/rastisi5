"""Cart/order catalog tenant-boundary tests — PR21 Step 11.

PR#20 propagated explicit Store context into pricing/order services but
deliberately added no Store FK to Cart/Order (out of scope for that PR).
These tests prove that boundary still holds now that catalog models
(Product/Category/Brand/Vendor/ProductVariant) are Store-scoped:

* ``cart:add`` can never attach another Store's product to a cart (real
  Host-based two-Store setup, no mocking).
* ``create_order_from_cart`` refuses to build an Order out of a cart line
  that references another Store's Product — even if something upstream of
  the normal ``cart_add`` view path put it there — and does so atomically
  (no partial Order/OrderItem rows survive the rejection).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store, StoreDomain

HOST_A = "cob-a.example.com"
HOST_B = "cob-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class CartAddCrossStoreTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="cob-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-cob-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-cob-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a,
            name="Product A", slug="product-cob-a", sku="SKU-COB-A",
            price=Decimal("100000"), stock=10, status=Product.Status.ACTIVE,
        )

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-cob-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-cob-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b,
            name="Product B", slug="product-cob-b", sku="SKU-COB-B",
            price=Decimal("200000"), stock=10, status=Product.Status.ACTIVE,
        )

    def test_cart_add_own_store_product_succeeds(self):
        response = self.client.post(
            reverse("cart:add", args=[self.product_a.slug]), {"quantity": 1}, HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.filter(product=self.product_a).count(), 1)

    def test_cart_add_other_stores_product_slug_returns_404(self):
        """Store A's host must never be able to add Store B's product to a cart."""
        response = self.client.post(
            reverse("cart:add", args=[self.product_b.slug]), {"quantity": 1}, HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_cart_add_other_stores_product_slug_returns_404_reverse_direction(self):
        response = self.client.post(
            reverse("cart:add", args=[self.product_a.slug]), {"quantity": 1}, HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CartItem.objects.count(), 0)


class CreateOrderFromCartCrossStoreProductTests(TestCase):
    """Direct service-layer test: even if a Cart line somehow referenced
    another Store's Product (bypassing the already-scoped ``cart_add``
    view), order creation must still refuse it — the last line of defense
    documented in ``order_service.create_order_from_cart``."""

    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="cob-svc-store-b", status=Store.Status.ACTIVE)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-cobsvc-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-cobsvc-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a,
            name="Product A", slug="product-cobsvc-a", sku="SKU-COBSVC-A",
            price=Decimal("100000"), stock=10, status=Product.Status.ACTIVE,
        )

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-cobsvc-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-cobsvc-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b,
            name="Product B", slug="product-cobsvc-b", sku="SKU-COBSVC-B",
            price=Decimal("200000"), stock=10, status=Product.Status.ACTIVE,
        )

        User = get_user_model()
        self.user = User.objects.create_user(username="cobsvc-user", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری", phone="09121230099")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121230099",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.shipping = ShippingMethod.objects.create(store=self.store_a, name="پست", slug="post-cobsvc", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store_a, name="زرین‌پال", slug="zarin-cobsvc")

    def test_order_creation_rejects_cart_line_from_another_store(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product_b, quantity=1, unit_price=self.product_b.final_price
        )
        with self.assertRaises(ValueError):
            create_order_from_cart(
                cart, customer=self.customer, vendor=self.vendor_a, address=self.address,
                shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store_a,
            )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_mixed_store_cart_lines_reject_whole_order_atomically(self):
        """A cart with one correct-Store line and one cross-Store line must
        create nothing at all — not a partial Order with only the valid line."""
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product_a, quantity=1, unit_price=self.product_a.final_price
        )
        CartItem.objects.create(
            cart=cart, product=self.product_b, quantity=1, unit_price=self.product_b.final_price
        )
        with self.assertRaises(ValueError):
            create_order_from_cart(
                cart, customer=self.customer, vendor=self.vendor_a, address=self.address,
                shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store_a,
            )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_correct_store_order_creates_valid_snapshot(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product_a, quantity=2, unit_price=self.product_a.final_price
        )
        order = create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor_a, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store_a,
        )
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        self.assertEqual(item.product_id, self.product_a.pk)
        self.assertEqual(item.quantity, 2)
