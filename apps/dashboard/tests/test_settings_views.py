import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import ShopSettings
from apps.orders.models import PaymentGateway, ShippingMethod

User = get_user_model()


class SettingsViewsTestCase(TestCase):
    def setUp(self):
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-sv", is_active=True)
        self.shipping = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-sv", is_active=True)
        self.staff = User.objects.create_user(username="09121192001", password="pass12345", is_staff=True)
        self.client.login(username="09121192001", password="pass12345")


class SettingsHomeViewTests(SettingsViewsTestCase):
    def test_renders_settings_page(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "زرین‌پال")
        self.assertContains(response, "پست پیشتاز")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)


class SettingsShopInfoViewTests(SettingsViewsTestCase):
    def test_valid_post_updates_shop_settings(self):
        response = self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "فروشگاه جدید", "tagline": "شعار جدید", "contact_phone": "021-1111",
            "contact_email": "new@example.com", "contact_address": "آدرس جدید", "description": "توضیح",
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "فروشگاه جدید")
        self.assertEqual(shop.contact_email, "new@example.com")

    def test_updated_name_appears_on_storefront(self):
        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "دیجی‌مارکت ویژه", "tagline": "", "contact_phone": "", "contact_email": "",
            "contact_address": "", "description": "",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "دیجی‌مارکت ویژه")

    def test_invalid_email_rejected(self):
        response = self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "فروشگاه", "tagline": "", "contact_phone": "", "contact_email": "not-an-email",
            "contact_address": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)


class SettingsFinanceViewTests(SettingsViewsTestCase):
    def test_valid_post_updates_tax_and_threshold(self):
        response = self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "۷", "free_shipping_threshold": "۷۰۰۰۰۰",
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        shop = ShopSettings.load()
        self.assertEqual(shop.tax_percent, Decimal("7"))
        self.assertEqual(shop.free_shipping_threshold, Decimal("700000"))

    def test_updated_tax_percent_affects_pricing_service(self):
        from decimal import Decimal as D

        from apps.cart.models import Cart, CartItem
        from apps.cart.services.pricing import cart_totals
        from apps.catalog.models import Category, Product, Vendor

        self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "5", "free_shipping_threshold": "1000000",
        })
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-sf")
        category = Category.objects.create(name="دسته", slug="cat-sf")
        product = Product.objects.create(
            vendor=vendor, category=category, name="کالا", slug="prod-sf",
            sku="SKU-SF1", price=D("100000"),
        )
        cart = Cart.objects.create(session_key="guest-sf")
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=product.final_price)
        totals = cart_totals(cart, shipping_method=self.shipping)
        self.assertEqual(totals["tax"], D("5000"))

    def test_out_of_range_tax_percent_rejected(self):
        response = self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "150", "free_shipping_threshold": "500000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حداکثر")


class SettingsGatewayToggleViewTests(SettingsViewsTestCase):
    def test_toggle_flips_is_active_and_persists(self):
        response = self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertEqual(response.status_code, 204)
        self.gateway.refresh_from_db()
        self.assertFalse(self.gateway.is_active)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("غیرفعال", trigger["toast"]["message"])

    def test_disabled_gateway_disappears_from_checkout_options(self):
        from apps.orders.services.checkout_service import active_payment_gateways

        self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertNotIn(self.gateway, active_payment_gateways())

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertEqual(response.status_code, 405)


class SettingsShippingToggleViewTests(SettingsViewsTestCase):
    def test_toggle_flips_is_active(self):
        response = self.client.post(reverse("dashboard:settings-shipping-toggle", args=[self.shipping.pk]))
        self.assertEqual(response.status_code, 204)
        self.shipping.refresh_from_db()
        self.assertFalse(self.shipping.is_active)

    def test_disabled_method_disappears_from_checkout_options(self):
        from apps.orders.services.checkout_service import active_shipping_methods

        self.client.post(reverse("dashboard:settings-shipping-toggle", args=[self.shipping.pk]))
        self.assertNotIn(self.shipping, active_shipping_methods())
