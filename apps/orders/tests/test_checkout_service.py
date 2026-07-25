from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, Vendor
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.orders.services import checkout_service
from apps.stores.models import Store


class CheckoutServiceTestCase(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-chk")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-chk")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-chk",
            sku="SKU-CHK1", price=Decimal("400000"), discount_percent=10, stock=10,
        )
        self.cheap_shipping = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-chk", cost=45_000)
        self.expensive_shipping = ShippingMethod.objects.create(name="پیک موتوری", slug="peyk-chk", cost=80_000)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-chk")
        self.coupon = Coupon.objects.create(code="TESTCOUP", type=Coupon.Type.PERCENT, value=Decimal("10"))

        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.get("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        return request

    def _cart_with_item(self, quantity=1):
        cart = Cart.objects.create(session_key="chk-session")
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity, unit_price=self.product.final_price)
        return cart


class ShippingSelectionTests(CheckoutServiceTestCase):
    def test_default_shipping_is_cheapest_active_method(self):
        request = self._request()
        selected = checkout_service.get_selected_shipping_method(request)
        self.assertEqual(selected, self.cheap_shipping)

    def test_set_shipping_method_persists_selection(self):
        request = self._request()
        checkout_service.set_shipping_method(request, self.expensive_shipping.pk)
        selected = checkout_service.get_selected_shipping_method(request)
        self.assertEqual(selected, self.expensive_shipping)

    def test_set_shipping_method_ignores_inactive_or_unknown_id(self):
        request = self._request()
        checkout_service.set_shipping_method(request, 999999)
        selected = checkout_service.get_selected_shipping_method(request)
        self.assertEqual(selected, self.cheap_shipping)


class CouponServiceTests(CheckoutServiceTestCase):
    def test_apply_valid_coupon_succeeds_and_persists(self):
        request = self._request()
        cart = self._cart_with_item(quantity=2)
        ok, message = checkout_service.apply_coupon(request, cart, "testcoup")
        self.assertTrue(ok)
        self.assertIn("TESTCOUP", message)
        self.assertEqual(checkout_service.get_applied_coupon(request, cart), self.coupon)

    def test_apply_unknown_coupon_fails(self):
        request = self._request()
        cart = self._cart_with_item()
        ok, message = checkout_service.apply_coupon(request, cart, "NOPE")
        self.assertFalse(ok)
        self.assertIsNone(checkout_service.get_applied_coupon(request, cart))

    def test_apply_blank_coupon_fails_with_hint_message(self):
        request = self._request()
        cart = self._cart_with_item()
        ok, message = checkout_service.apply_coupon(request, cart, "   ")
        self.assertFalse(ok)
        self.assertIn("وارد کنید", message)

    def test_remove_coupon_clears_session(self):
        request = self._request()
        cart = self._cart_with_item()
        checkout_service.apply_coupon(request, cart, "TESTCOUP")
        checkout_service.remove_coupon(request)
        self.assertIsNone(checkout_service.get_applied_coupon(request, cart))

    def test_coupon_no_longer_applicable_is_dropped_automatically(self):
        request = self._request()
        cart = self._cart_with_item(quantity=1)
        checkout_service.apply_coupon(request, cart, "TESTCOUP")
        self.coupon.min_order = Decimal("999999999")
        self.coupon.save(update_fields=["min_order"])
        self.assertIsNone(checkout_service.get_applied_coupon(request, cart))


class BuildContextTests(CheckoutServiceTestCase):
    def test_empty_cart_marks_is_empty(self):
        request = self._request()
        cart = Cart.objects.create(session_key="chk-empty")
        context = checkout_service.build_context(request, cart)
        self.assertTrue(context["is_empty"])
        self.assertEqual(context["totals"]["grand_total"], 0)

    def test_context_totals_use_pricing_service(self):
        request = self._request()
        cart = self._cart_with_item(quantity=2)
        context = checkout_service.build_context(request, cart)
        self.assertFalse(context["is_empty"])
        self.assertEqual(context["totals"]["items_total"], Decimal("720000"))
        self.assertEqual(context["item_count"], 2)

    def test_free_shipping_flag_applies_to_all_shipping_rows(self):
        self.product.price = Decimal("600000")
        self.product.discount_percent = 0
        self.product.save(update_fields=["price", "discount_percent"])
        request = self._request()
        cart = self._cart_with_item(quantity=1)
        context = checkout_service.build_context(request, cart)
        self.assertTrue(context["totals"]["free_shipping"])
        self.assertTrue(all(row["free"] for row in context["shipping_rows"]))
