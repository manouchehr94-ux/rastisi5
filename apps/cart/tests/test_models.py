from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.stores.models import Store

from apps.cart.models import Cart, CartItem, Coupon

User = get_user_model()


class CartModelsTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-c")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-c")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هودی", slug="hoodie-c",
            sku="SKU-C1", price=Decimal("1500000"),
        )

    def test_cart_for_guest(self):
        cart = Cart.objects.create(session_key="guest-session-1")
        self.assertIsNone(cart.customer)

    def test_cart_item_snapshot_price(self):
        cart = Cart.objects.create(session_key="guest-session-2")
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=2, unit_price=self.product.price)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(item.quantity * item.unit_price, Decimal("3000000"))

    def test_coupon_code_uppercased_and_unique(self):
        coupon = Coupon.objects.create(code="welcome10", type=Coupon.Type.PERCENT, value=10, label="۱۰٪ تخفیف")
        self.assertEqual(coupon.code, "WELCOME10")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Coupon.objects.create(code="WELCOME10", type=Coupon.Type.FIXED, value=50_000)
