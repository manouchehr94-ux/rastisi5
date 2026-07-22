import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod

User = get_user_model()


class CheckoutStep1ViewTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cov")
        category = Category.objects.create(name="دیجیتال", slug="digital-cov")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-cov",
            sku="SKU-COV1", price=Decimal("400000"), discount_percent=25, stock=10,
        )
        self.shipping = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-cov", cost=45_000)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-cov")

    def test_empty_cart_shows_empty_state(self):
        response = self.client.get(reverse("orders:checkout-step1"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_cart_with_items_shows_form_and_live_totals(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        response = self.client.get(reverse("orders:checkout-step1"))
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.shipping.name)
        self.assertContains(response, self.gateway.name)
        totals = response.context["totals"]
        self.assertEqual(totals["items_total"], Decimal("600000"))


class CheckoutPayTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cas")
        category = Category.objects.create(name="دیجیتال", slug="digital-cas")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-cas",
            sku="SKU-CAS1", price=Decimal("200000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-cas", cost=45_000)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-cas")
        self.valid_payload = {
            "receiver_name": "علی رضایی", "phone": "09123456789", "province": "تهران",
            "city": "تهران", "postal_code": "1415873920",
            "full_address": "تهران، خیابان ولیعصر، پلاک ۱", "note": "",
        }

    def _login_and_add_to_cart(self, quantity=2):
        # login کلید session را عوض می‌کند؛ برای اینکه سبد آزمون به کاربر
        # واردشده وصل شود، افزودن به سبد باید بعد از ورود انجام شود.
        user = User.objects.create_user(username="09123456789", password="pass12345")
        Customer.objects.create(user=user, full_name="علی رضایی", phone="09123456789")
        self.client.login(username="09123456789", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": quantity})

    def test_invalid_phone_shows_field_error_and_creates_no_order(self):
        self._login_and_add_to_cart()
        payload = dict(self.valid_payload, phone="12345")
        response = self.client.post(reverse("orders:checkout-pay"), payload)
        self.assertContains(response, "شماره موبایل معتبر نیست")
        self.assertEqual(Order.objects.count(), 0)

    def test_missing_required_field_fails(self):
        self._login_and_add_to_cart()
        payload = dict(self.valid_payload, full_address="")
        response = self.client.post(reverse("orders:checkout-pay"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_guest_valid_address_prompts_login_and_creates_no_order(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        response = self.client.post(reverse("orders:checkout-pay"), self.valid_payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("HX-Trigger", response.headers)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("open-login", trigger)
        # address is preserved in session so the user can continue right after logging in
        self.assertEqual(self.client.session["checkout"]["address"]["receiver_name"], "علی رضایی")

    def test_authenticated_valid_address_creates_order_and_redirects(self):
        self._login_and_add_to_cart()
        response = self.client.post(reverse("orders:checkout-pay"), self.valid_payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertIn(order.code, response.headers["HX-Redirect"])

    def test_authenticated_pay_reduces_stock_and_empties_cart(self):
        self._login_and_add_to_cart()
        self.client.post(reverse("orders:checkout-pay"), self.valid_payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        cart = Cart.objects.get(customer__phone="09123456789")
        self.assertEqual(cart.items.count(), 0)

    def test_authenticated_pay_saves_address_book_entry(self):
        self._login_and_add_to_cart()
        self.client.post(reverse("orders:checkout-pay"), self.valid_payload)
        customer = Customer.objects.get(phone="09123456789")
        self.assertEqual(customer.addresses.count(), 1)
        self.assertTrue(customer.addresses.first().is_default)

    def test_insufficient_stock_shows_error_and_creates_no_order(self):
        self._login_and_add_to_cart()
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        response = self.client.post(reverse("orders:checkout-pay"), self.valid_payload)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("کافی نیست", trigger["toast"]["message"])
        self.assertEqual(Order.objects.count(), 0)


class PaymentFlowTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-pf")
        category = Category.objects.create(name="دیجیتال", slug="digital-pf")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-pf",
            sku="SKU-PF1", price=Decimal("200000"), stock=10,
        )
        ShippingMethod.objects.create(name="پست پیشتاز", slug="post-pf", cost=45_000)
        PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-pf")
        user = User.objects.create_user(username="09121110099", password="pass12345")
        Customer.objects.create(user=user, full_name="سارا محمدی", phone="09121110099")
        self.client.login(username="09121110099", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.client.post(reverse("orders:checkout-pay"), {
            "receiver_name": "سارا محمدی", "phone": "09121110099", "province": "تهران",
            "city": "تهران", "postal_code": "1415873920", "full_address": "تهران، خیابان آزادی", "note": "",
        })
        self.order = Order.objects.get()

    def test_payment_start_redirects_to_callback_success(self):
        response = self.client.get(reverse("orders:payment-start", args=[self.order.code]))
        self.assertRedirects(
            response, reverse("orders:payment-callback", args=[self.order.code, "success"]),
            target_status_code=302,
        )

    def test_full_flow_marks_order_paid_and_shows_result(self):
        response = self.client.get(
            reverse("orders:payment-start", args=[self.order.code]), follow=True
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertContains(response, "پرداخت با موفقیت انجام شد")
        self.assertContains(response, self.order.code)

    def test_failed_callback_marks_order_failed(self):
        response = self.client.get(
            reverse("orders:payment-callback", args=[self.order.code, "failed"]), follow=True
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.assertContains(response, "پرداخت ناموفق بود")

    def test_callback_is_idempotent(self):
        self.client.get(reverse("orders:payment-callback", args=[self.order.code, "success"]))
        # second hit should not raise even though the order is already paid
        response = self.client.get(reverse("orders:payment-callback", args=[self.order.code, "success"]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.order.transactions.count(), 1)

    def test_other_users_cannot_view_result(self):
        other = User.objects.create_user(username="09121110098", password="pass12345")
        Customer.objects.create(user=other, full_name="کاربر دیگر", phone="09121110098")
        self.client.logout()
        self.client.login(username="09121110098", password="pass12345")
        response = self.client.get(reverse("orders:payment-result", args=[self.order.code]))
        self.assertEqual(response.status_code, 404)


class CheckoutItemAndSelectionViewTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cis")
        category = Category.objects.create(name="دیجیتال", slug="digital-cis")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-cis",
            sku="SKU-CIS1", price=Decimal("100000"), stock=5,
        )
        self.cheap = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-cis", cost=45_000)
        self.expensive = ShippingMethod.objects.create(name="پیک موتوری", slug="peyk-cis", cost=80_000)
        self.gateway1 = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-cis")
        self.gateway2 = PaymentGateway.objects.create(name="پی‌پینگ", slug="payping-cis")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.item = CartItem.objects.first()

    def test_update_quantity_reflects_in_totals(self):
        response = self.client.post(reverse("orders:checkout-item-update", args=[self.item.id]), {"quantity": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["totals"]["items_total"], Decimal("300000"))

    def test_remove_item_shows_empty_state(self):
        response = self.client.post(reverse("orders:checkout-item-remove", args=[self.item.id]))
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_set_shipping_method_updates_totals_shipping_cost(self):
        self.client.post(reverse("orders:checkout-set-shipping", args=[self.expensive.id]))
        response = self.client.get(reverse("orders:checkout-step1"))
        self.assertEqual(response.context["totals"]["shipping_cost"], Decimal("80000"))

    def test_set_payment_gateway_marks_it_selected(self):
        self.client.post(reverse("orders:checkout-set-payment", args=[self.gateway2.id]))
        response = self.client.get(reverse("orders:checkout-step1"))
        selected = [row for row in response.context["payment_rows"] if row["selected"]][0]
        self.assertEqual(selected["gateway"], self.gateway2)


class CheckoutCouponViewTests(TestCase):
    def setUp(self):
        from apps.cart.models import Coupon

        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ccv")
        category = Category.objects.create(name="دیجیتال", slug="digital-ccv")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-ccv",
            sku="SKU-CCV1", price=Decimal("300000"),
        )
        ShippingMethod.objects.create(name="پست پیشتاز", slug="post-ccv", cost=45_000)
        PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-ccv")
        self.coupon = Coupon.objects.create(code="SAVE10", type=Coupon.Type.PERCENT, value=Decimal("10"))
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})

    def test_apply_valid_coupon_shows_applied_box(self):
        response = self.client.post(reverse("orders:checkout-coupon-apply"), {"code": "save10"})
        self.assertContains(response, "SAVE10")
        self.assertEqual(response.context["totals"]["coupon_discount"], Decimal("30000"))

    def test_apply_invalid_coupon_shows_error(self):
        response = self.client.post(reverse("orders:checkout-coupon-apply"), {"code": "NOPE"})
        self.assertContains(response, "کد تخفیف نامعتبر است")

    def test_remove_coupon_clears_it(self):
        self.client.post(reverse("orders:checkout-coupon-apply"), {"code": "SAVE10"})
        response = self.client.post(reverse("orders:checkout-coupon-remove"))
        self.assertEqual(response.context["totals"]["coupon_discount"], Decimal("0"))
