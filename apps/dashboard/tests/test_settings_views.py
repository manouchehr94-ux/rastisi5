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

    def test_appearance_section_shows_visual_identity_form(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هویت بصری")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "رنگ اصلی")

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



class VisualIdentityTests(SettingsViewsTestCase):
    """Tests for visual identity settings: colors, logo, favicon."""

    def test_valid_colors_save(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#1F2937",
            "accent_color": "#C59A45",
        })
        self.assertRedirects(response, "/admin-panel/settings/?section=appearance")
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#1F2937")
        self.assertEqual(shop.accent_color, "#C59A45")

    def test_lowercase_hex_normalized_to_uppercase(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#aabbcc",
            "accent_color": "#112233",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#AABBCC")
        self.assertEqual(shop.accent_color, "#112233")

    def test_short_hex_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFF",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#RRGGBB")

    def test_non_hex_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "red",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#RRGGBB")

    def test_css_function_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "rgb(255,0,0)",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)

    def test_script_payload_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "<script>",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        # Malicious value not stored
        shop = ShopSettings.load()
        self.assertNotEqual(shop.primary_color, "<script>")

    def test_appearance_save_redirects_to_appearance_section(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9",
            "accent_color": "#FF4D77",
        })
        self.assertRedirects(response, "/admin-panel/settings/?section=appearance")

    def test_appearance_validation_error_stays_on_appearance(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "invalid",
            "accent_color": "invalid",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "رنگ‌بندی")

    def test_storefront_uses_configured_colors(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#112233",
            "accent_color": "#445566",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-primary:#112233")
        self.assertContains(response, "--brand-accent:#445566")

    def test_empty_logo_uses_fallback(self):
        """When no logo is set, storefront uses the SVG mark fallback."""
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "class=\"mark\"")

    def test_empty_favicon_uses_static_fallback(self):
        """When no favicon is set, static favicon.ico is referenced."""
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "favicon.ico")

    def test_default_colors_are_valid(self):
        shop = ShopSettings.load()
        import re
        self.assertRegex(shop.primary_color, r"^#[0-9A-Fa-f]{6}$")
        self.assertRegex(shop.accent_color, r"^#[0-9A-Fa-f]{6}$")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#000000", "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)



class ContrastAndSafetyTests(SettingsViewsTestCase):
    """Tests for foreground contrast calculation and safe color rendering."""

    def test_dark_primary_gets_white_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#1F2937", "accent_color": "#000000",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-primary-fg:#FFFFFF")

    def test_light_primary_gets_black_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFFFFF", "accent_color": "#FFFF00",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-primary-fg:#000000")
        self.assertContains(response, "--brand-accent-fg:#000000")

    def test_invalid_stored_color_uses_default(self):
        """If invalid data reaches the DB (e.g. legacy), safe default is rendered."""
        shop = ShopSettings.load()
        # Bypass form validation to simulate legacy invalid data
        ShopSettings.objects.filter(pk=1).update(primary_color="invalid", accent_color="")
        response = self.client.get(reverse("catalog:home"))
        # Should use defaults, not render 'invalid'
        self.assertContains(response, "--brand-primary:#6D28D9")
        self.assertNotContains(response, "invalid")

    def test_model_validator_rejects_invalid_color(self):
        """Model-level validator prevents invalid data."""
        from django.core.exceptions import ValidationError
        from apps.core.models import validate_hex_color
        with self.assertRaises(ValidationError):
            validate_hex_color("red")
        with self.assertRaises(ValidationError):
            validate_hex_color("#FFF")
        with self.assertRaises(ValidationError):
            validate_hex_color("rgb(0,0,0)")

    def test_brand_colors_consumed_by_storefront_tokens(self):
        """Configured colors are actually consumed via CSS custom properties."""
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#AA1122", "accent_color": "#33BB44",
        })
        response = self.client.get(reverse("catalog:home"))
        # Colors are set as brand variables
        self.assertContains(response, "--brand-primary:#AA1122")
        self.assertContains(response, "--brand-accent:#33BB44")



import os
import tempfile
import shutil

from django.test import override_settings

_TEMP_MEDIA_DIR = tempfile.mkdtemp()


def _make_image(fmt='PNG', size=(100, 100)):
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    buf = BytesIO()
    img = Image.new('RGBA' if fmt == 'PNG' else 'RGB', size, (255, 0, 0))
    img.save(buf, format=fmt)
    ext = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[fmt]
    ct = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[fmt]
    return SimpleUploadedFile(f'test.{ext}', buf.getvalue(), content_type=ct)


@override_settings(MEDIA_ROOT=_TEMP_MEDIA_DIR)
class LogoUploadTests(SettingsViewsTestCase):
    """Complete logo upload lifecycle tests with isolated media."""

    def tearDown(self):
        # Clean temp files after each test
        for f in os.listdir(_TEMP_MEDIA_DIR):
            path = os.path.join(_TEMP_MEDIA_DIR, f)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    def test_valid_png_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        self.assertRedirects(resp, "/admin-panel/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_valid_jpeg_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("JPEG"),
        })
        self.assertRedirects(resp, "/admin-panel/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_valid_webp_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("WEBP"),
        })
        self.assertRedirects(resp, "/admin-panel/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_oversized_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("big.png", b"x" * (3 * 1024 * 1024), content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": big,
        })
        self.assertEqual(resp.status_code, 200)

    def test_fake_content_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile("fake.png", b"not-image", content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": fake,
        })
        self.assertEqual(resp.status_code, 200)

    def test_svg_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        svg = SimpleUploadedFile("logo.svg", b"<svg></svg>", content_type="image/svg+xml")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": svg,
        })
        self.assertEqual(resp.status_code, 200)

    def test_empty_upload_preserves_current(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        old = ShopSettings.load().logo.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
        })
        self.assertEqual(ShopSettings.load().logo.name, old)

    def test_replacement_saves_new(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        old = ShopSettings.load().logo.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("JPEG"),
        })
        new = ShopSettings.load().logo.name
        self.assertNotEqual(old, new)

    def test_explicit_removal(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        self.assertTrue(ShopSettings.load().logo)
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "remove_logo": "on",
        })
        self.assertFalse(ShopSettings.load().logo)

    def test_simultaneous_upload_and_remove_replacement_wins(self):
        """When both upload and remove are submitted, replacement wins."""
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "logo": _make_image("PNG"), "remove_logo": "on",
        })
        # Replacement wins — logo is set
        self.assertTrue(ShopSettings.load().logo)


@override_settings(MEDIA_ROOT=_TEMP_MEDIA_DIR)
class FaviconUploadTests(SettingsViewsTestCase):
    """Complete favicon upload lifecycle tests with isolated media."""

    def tearDown(self):
        for f in os.listdir(_TEMP_MEDIA_DIR):
            path = os.path.join(_TEMP_MEDIA_DIR, f)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    def _fav(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = BytesIO()
        Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(buf, "PNG")
        return SimpleUploadedFile("fav.png", buf.getvalue(), content_type="image/png")

    def test_valid_png_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        self.assertRedirects(resp, "/admin-panel/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().favicon)

    def test_oversized_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("big.png", b"x" * (600 * 1024), content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": big,
        })
        self.assertEqual(resp.status_code, 200)

    def test_fake_content_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile("fake.png", b"not-image", content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": fake,
        })
        self.assertEqual(resp.status_code, 200)

    def test_svg_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        svg = SimpleUploadedFile("f.svg", b"<svg></svg>", content_type="image/svg+xml")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": svg,
        })
        self.assertEqual(resp.status_code, 200)

    def test_empty_upload_preserves_current(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        old = ShopSettings.load().favicon.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
        })
        self.assertEqual(ShopSettings.load().favicon.name, old)

    def test_replacement_saves_new(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        old = ShopSettings.load().favicon.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        new = ShopSettings.load().favicon.name
        self.assertNotEqual(old, new)

    def test_explicit_removal(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        self.assertTrue(ShopSettings.load().favicon)
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "remove_favicon": "on",
        })
        self.assertFalse(ShopSettings.load().favicon)

    def test_simultaneous_upload_and_remove_replacement_wins(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "favicon": self._fav(), "remove_favicon": "on",
        })
        self.assertTrue(ShopSettings.load().favicon)

    def test_configured_favicon_in_html(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, 'rel="icon"')
        self.assertContains(resp, "shop/branding/")

    def test_fallback_favicon_when_not_set(self):
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "favicon.ico")


class ContrastAndSafetyTests(SettingsViewsTestCase):
    """Contrast calculation, model validation, and safe rendering tests."""

    def test_dark_primary_gets_white_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#1F2937", "accent_color": "#000000",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary-fg:#FFFFFF")

    def test_light_primary_gets_black_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFFFFF", "accent_color": "#FFFF00",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary-fg:#000000")
        self.assertContains(resp, "--brand-accent-fg:#000000")

    def test_invalid_stored_color_uses_default(self):
        ShopSettings.objects.filter(pk=1).update(primary_color="invalid", accent_color="")
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary:#6D28D9")
        self.assertNotContains(resp, "invalid")

    def test_model_validator_rejects_invalid(self):
        from django.core.exceptions import ValidationError
        from apps.core.models import validate_hex_color
        with self.assertRaises(ValidationError):
            validate_hex_color("red")
        with self.assertRaises(ValidationError):
            validate_hex_color("#FFF")

    def test_brand_colors_in_storefront(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#AA1122", "accent_color": "#33BB44",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary:#AA1122")
        self.assertContains(resp, "--brand-accent:#33BB44")

    def test_layout_css_uses_foreground_vars(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "core", "static", "css", "layout.css"
        )
        with open(css_path) as f:
            css = f.read()
        self.assertIn("var(--brand-primary-fg", css)
        self.assertIn("var(--brand-accent-fg", css)

    def test_default_gradients_preserved(self):
        """Default brand colors preserve existing gradient depth via --violet-2 and --violet-3."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "core", "static", "css", "tokens.css"
        )
        with open(css_path) as f:
            css = f.read()
        # --violet-2 and --violet-3 remain fixed (not overridden by brand-primary)
        self.assertIn("--violet-2:#7c3aed", css)
        self.assertIn("--violet-3:#8b5cf6", css)
