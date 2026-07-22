from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.cart.models import CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.orders.models import PaymentGateway, ShippingMethod


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


class CheckoutAddressSaveTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cas")
        category = Category.objects.create(name="دیجیتال", slug="digital-cas")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-cas",
            sku="SKU-CAS1", price=Decimal("200000"),
        )
        ShippingMethod.objects.create(name="پست پیشتاز", slug="post-cas", cost=45_000)
        PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-cas")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.valid_payload = {
            "receiver_name": "علی رضایی", "phone": "09123456789", "province": "تهران",
            "city": "تهران", "postal_code": "1415873920",
            "full_address": "تهران، خیابان ولیعصر، پلاک ۱", "note": "",
        }

    def test_valid_address_is_saved_to_session(self):
        response = self.client.post(reverse("orders:checkout-address-save"), self.valid_payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["checkout"]["address"]["receiver_name"], "علی رضایی")
        self.assertContains(response, "علی رضایی")

    def test_invalid_phone_shows_field_error(self):
        payload = dict(self.valid_payload, phone="12345")
        response = self.client.post(reverse("orders:checkout-address-save"), payload)
        self.assertContains(response, "شماره موبایل معتبر نیست")
        self.assertNotIn("address", self.client.session.get("checkout", {}))

    def test_missing_required_field_fails(self):
        payload = dict(self.valid_payload, full_address="")
        response = self.client.post(reverse("orders:checkout-address-save"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("address", self.client.session.get("checkout", {}))


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
