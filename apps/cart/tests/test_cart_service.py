from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.cart.models import Cart
from apps.cart.services.cart_service import add_item_to_cart, get_cart
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.stores.models import Store

User = get_user_model()


class GetCartTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _guest_request(self):
        request = self.factory.get("/")
        from django.contrib.sessions.middleware import SessionMiddleware

        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        return request

    def _customer_request(self, user):
        request = self.factory.get("/")
        from django.contrib.sessions.middleware import SessionMiddleware

        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = user
        return request

    def test_guest_get_cart_without_create_returns_none(self):
        request = self._guest_request()
        self.assertIsNone(get_cart(request))

    def test_guest_get_cart_with_create_creates_session_cart(self):
        request = self._guest_request()
        cart = get_cart(request, create=True)
        self.assertIsNotNone(cart)
        self.assertIsNone(cart.customer)
        self.assertEqual(cart.session_key, request.session.session_key)

    def test_guest_get_cart_is_idempotent_for_same_session(self):
        request = self._guest_request()
        cart1 = get_cart(request, create=True)
        cart2 = get_cart(request, create=True)
        self.assertEqual(cart1.pk, cart2.pk)
        self.assertEqual(Cart.objects.count(), 1)

    def test_logged_in_customer_get_cart_creates_customer_cart(self):
        user = User.objects.create_user(username="cart_user1", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="کاربر تست", phone="09121110011")
        request = self._customer_request(user)
        cart = get_cart(request, create=True)
        self.assertEqual(cart.customer, customer)
        self.assertEqual(cart.session_key, "")

    def test_logged_in_customer_reuses_same_cart(self):
        user = User.objects.create_user(username="cart_user2", password="pass12345")
        Customer.objects.create(user=user, full_name="کاربر تست ۲", phone="09121110012")
        request = self._customer_request(user)
        cart1 = get_cart(request, create=True)
        cart2 = get_cart(request, create=True)
        self.assertEqual(cart1.pk, cart2.pk)


class AddItemToCartTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cs")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-cs")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-cs",
            sku="SKU-CS1", price=Decimal("200000"), discount_percent=10,
        )
        self.cart = Cart.objects.create(session_key="test-session-cs")

    def test_add_new_item_snapshots_final_price(self):
        item = add_item_to_cart(self.cart, self.product, None, 2)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("180000"))

    def test_add_same_product_twice_increments_quantity(self):
        add_item_to_cart(self.cart, self.product, None, 1)
        item = add_item_to_cart(self.cart, self.product, None, 2)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(self.cart.items.count(), 1)

    def test_add_variant_with_absolute_price_snapshots_variant_price_not_product_price(self):
        """قیچیِ ایرانی/ایتالیایی: قیمتِ سبد باید قیمتِ *تنوعِ* انتخاب‌شده باشد،
        نه قیمتِ پایه‌ی کالا — رگرسیونی که پیش از این وصله وجود داشت
        (add_item_to_cart قبلاً همیشه product.final_price را snapshot می‌کرد)."""
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"),
        )
        item = add_item_to_cart(self.cart, self.product, variant, 1)
        self.assertEqual(item.unit_price, Decimal("800000"))
        self.assertNotEqual(item.unit_price, self.product.final_price)

    def test_add_variant_with_legacy_delta_price_still_works(self):
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="طول", value="بلند", extra_price=Decimal("20000"),
        )
        item = add_item_to_cart(self.cart, self.product, variant, 1)
        # (200000 + 20000) * 0.9 = 198000
        self.assertEqual(item.unit_price, Decimal("198000"))
