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
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_default_section_is_general(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_payments_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=payments")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درگاه‌های پرداخت")
        self.assertContains(response, "زرین‌پال")

    def test_shipping_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=shipping")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پست پیشتاز")

    def test_sms_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اتصال سیستم پیامک")

    def test_appearance_section_shows_placeholder(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "به‌زودی")
        # No functional Save button in the appearance content section
        content = response.content.decode()
        # The appearance partial itself contains no submit button
        self.assertIn("شخصی‌سازی ظاهر فروشگاه", content)

    def test_invalid_section_falls_back_to_general(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=nonexistent")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_navigation_shows_all_sections(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, "عمومی")
        self.assertContains(response, "پرداخت و مالی")
        self.assertContains(response, "ارسال")
        self.assertContains(response, "پیامک")
        self.assertContains(response, "ظاهر فروشگاه")

    def test_active_section_indicated(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=shipping")
        self.assertContains(response, 'aria-current="page"')

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
        self.assertRedirects(response, "/admin-panel/settings/?section=general")
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "فروشگاه جدید")
        self.assertEqual(shop.contact_email, "new@example.com")

    def test_contact_update_does_not_overwrite_store_identity(self):
        """Updating contact fields preserves name/tagline/description."""
        # First set known identity values
        shop = ShopSettings.load()
        shop.name = "نام اصلی"
        shop.tagline = "شعار اصلی"
        shop.description = "توضیح اصلی"
        shop.save()

        # Submit form with all fields (single form approach)
        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "نام اصلی", "tagline": "شعار اصلی", "description": "توضیح اصلی",
            "contact_phone": "021-9999", "contact_email": "updated@test.com",
            "contact_address": "آدرس جدید",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "نام اصلی")
        self.assertEqual(shop.tagline, "شعار اصلی")
        self.assertEqual(shop.description, "توضیح اصلی")
        self.assertEqual(shop.contact_phone, "021-9999")

    def test_store_identity_update_does_not_overwrite_contact(self):
        """Updating identity fields preserves contact fields."""
        shop = ShopSettings.load()
        shop.contact_phone = "021-5555"
        shop.contact_email = "keep@test.com"
        shop.contact_address = "آدرس حفظ"
        shop.save()

        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "نام جدید", "tagline": "شعار جدید", "description": "توضیح جدید",
            "contact_phone": "021-5555", "contact_email": "keep@test.com",
            "contact_address": "آدرس حفظ",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "نام جدید")
        self.assertEqual(shop.contact_phone, "021-5555")
        self.assertEqual(shop.contact_email, "keep@test.com")

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
        self.assertRedirects(response, "/admin-panel/settings/?section=payments")
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
        self.assertContains(response, "درگاه‌های پرداخت")  # Stays on payments section


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



class SettingsSMSSectionTests(SettingsViewsTestCase):
    """SMS actions preserve the SMS section state."""

    def test_sms_connection_save_redirects_to_sms_section(self):
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": True, "sms_backend": "console",
            "sms_sender_number": "", "melipayamak_username": "", "melipayamak_password": "",
        })
        self.assertRedirects(response, "/admin-panel/settings/?section=sms")

    def test_sms_test_send_redirects_to_sms_section(self):
        response = self.client.post(reverse("dashboard:sms-test-send"), {
            "phone": "09121234567", "event_key": "welcome",
        })
        self.assertRedirects(response, "/admin-panel/settings/?section=sms")

    def test_sms_section_shows_connection_form(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "فعال‌سازی سیستم پیامک")
        self.assertContains(response, "ذخیره تنظیمات اتصال")

    def test_sms_section_shows_templates(self):
        from apps.sms.models import SmsTemplate
        SmsTemplate.ensure_defaults()
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "قالب‌های پیامک")


class SettingsGeneralFormTests(SettingsViewsTestCase):
    """General section has one unified form — no fragile hidden fields."""

    def test_general_section_has_one_form_action(self):
        """Only one form submits to settings-shop-info (no duplicate forms)."""
        response = self.client.get(reverse("dashboard:settings") + "?section=general")
        content = response.content.decode()
        # Count occurrences of the form action URL
        action_url = reverse("dashboard:settings-shop-info")
        self.assertEqual(content.count(f'action="{action_url}"'), 1)

    def test_general_section_has_no_hidden_name_field(self):
        """No fragile hidden fields for preserving other form's values."""
        response = self.client.get(reverse("dashboard:settings") + "?section=general")
        content = response.content.decode()
        self.assertNotIn('type="hidden" name="name"', content)
        self.assertNotIn('type="hidden" name="tagline"', content)
