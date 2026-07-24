"""تست‌های جامع قابلیت «تنظیمات فوتر» — مدل، داشبورد، و رندر فروشگاه."""

from io import BytesIO

from PIL import Image

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.content.models import (
    FooterPaymentLogo,
    FooterSettings,
    FooterTrustBadge,
)

User = get_user_model()


def _make_image(name="test.png", size=(10, 10), fmt="PNG"):
    """ساخت تصویر ساختگی برای تست."""
    buf = BytesIO()
    Image.new("RGB", size).save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


# ---------------------------------------------------------------- FooterSettings Model


class FooterSettingsSingletonTests(TestCase):
    """تست‌های singleton بودن FooterSettings."""

    def test_load_creates_instance(self):
        self.assertEqual(FooterSettings.objects.count(), 0)
        fs = FooterSettings.load()
        self.assertEqual(fs.pk, 1)
        self.assertEqual(FooterSettings.objects.count(), 1)

    def test_repeated_load_returns_same_row(self):
        fs1 = FooterSettings.load()
        fs2 = FooterSettings.load()
        self.assertEqual(fs1.pk, fs2.pk)
        self.assertEqual(FooterSettings.objects.count(), 1)

    def test_defaults(self):
        fs = FooterSettings.load()
        self.assertTrue(fs.is_enabled)
        self.assertTrue(fs.show_branding)
        self.assertTrue(fs.show_logo)
        self.assertTrue(fs.show_contact)
        self.assertTrue(fs.show_navigation)
        self.assertTrue(fs.show_social_links)
        self.assertFalse(fs.show_newsletter)
        self.assertFalse(fs.show_trust_badges)
        self.assertFalse(fs.show_payment_logos)
        self.assertEqual(fs.description, "")
        self.assertEqual(fs.copyright_text, "")

    def test_save_forces_pk_1(self):
        fs = FooterSettings(pk=99, description="test")
        fs.save()
        self.assertEqual(fs.pk, 1)
        self.assertEqual(FooterSettings.objects.count(), 1)

    def test_str(self):
        fs = FooterSettings.load()
        self.assertEqual(str(fs), "تنظیمات فوتر")


# ---------------------------------------------------------------- FooterTrustBadge Model


class FooterTrustBadgeTests(TestCase):
    """تست‌های مدل FooterTrustBadge."""

    def test_valid_creation(self):
        badge = FooterTrustBadge.objects.create(
            title="اینماد",
            image=_make_image("enamad.png"),
            destination_url="https://enamad.ir",
            display_order=1,
        )
        self.assertEqual(badge.title, "اینماد")
        self.assertTrue(badge.is_active)
        self.assertEqual(str(badge), "اینماد")

    def test_title_required(self):
        badge = FooterTrustBadge(title="", image=_make_image())
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_image_required(self):
        badge = FooterTrustBadge(title="test")
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_dangerous_url_rejected(self):
        badge = FooterTrustBadge(
            title="XSS", image=_make_image(),
            destination_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError) as cm:
            badge.full_clean()
        self.assertIn("destination_url", cm.exception.message_dict)

    def test_protocol_relative_url_rejected(self):
        badge = FooterTrustBadge(
            title="Protocol", image=_make_image(),
            destination_url="//evil.com/phish",
        )
        with self.assertRaises(ValidationError) as cm:
            badge.full_clean()
        self.assertIn("destination_url", cm.exception.message_dict)

    def test_blank_url_allowed(self):
        badge = FooterTrustBadge(title="NoLink", image=_make_image(), destination_url="")
        badge.full_clean()  # should not raise

    def test_ordering(self):
        FooterTrustBadge.objects.create(title="B", image=_make_image("b.png"), display_order=2)
        FooterTrustBadge.objects.create(title="A", image=_make_image("a.png"), display_order=1)
        badges = list(FooterTrustBadge.objects.values_list("title", flat=True))
        self.assertEqual(badges, ["A", "B"])


# ---------------------------------------------------------------- FooterPaymentLogo Model


class FooterPaymentLogoTests(TestCase):
    """تست‌های مدل FooterPaymentLogo."""

    def test_valid_creation(self):
        logo = FooterPaymentLogo.objects.create(
            title="زرین‌پال", image=_make_image("zp.png"), display_order=0,
        )
        self.assertEqual(logo.title, "زرین‌پال")
        self.assertTrue(logo.is_active)
        self.assertEqual(str(logo), "زرین‌پال")

    def test_title_required(self):
        logo = FooterPaymentLogo(title="", image=_make_image())
        with self.assertRaises(ValidationError):
            logo.full_clean()

    def test_image_required(self):
        logo = FooterPaymentLogo(title="test")
        with self.assertRaises(ValidationError):
            logo.full_clean()

    def test_ordering(self):
        FooterPaymentLogo.objects.create(title="Second", image=_make_image("s.png"), display_order=5)
        FooterPaymentLogo.objects.create(title="First", image=_make_image("f.png"), display_order=1)
        logos = list(FooterPaymentLogo.objects.values_list("title", flat=True))
        self.assertEqual(logos, ["First", "Second"])


# ---------------------------------------------------------------- Dashboard Access


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class DashboardAccessTests(TestCase):
    """تست‌های دسترسی داشبورد فوتر."""

    def setUp(self):
        self.staff = User.objects.create_user(username="admin", password="pass123", is_staff=True)
        self.user = User.objects.create_user(username="normal", password="pass123", is_staff=False)

    def test_anonymous_redirect(self):
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_non_staff_rejected(self):
        self.client.login(username="normal", password="pass123")
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_staff_allowed(self):
        self.client.login(username="admin", password="pass123")
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------- Dashboard CRUD


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class DashboardFooterCRUDTests(TestCase):
    """تست‌های CRUD داشبورد فوتر."""

    def setUp(self):
        self.staff = User.objects.create_user(username="admin", password="pass123", is_staff=True)
        self.client.login(username="admin", password="pass123")

    def test_settings_save(self):
        url = reverse("dashboard:footer-settings")
        resp = self.client.post(url, {
            "is_enabled": "on",
            "show_branding": "on",
            "show_contact": "on",
            "show_navigation": "on",
            "show_social_links": "on",
            "copyright_text": "My Copyright",
            "phone": "021-12345",
            "address": "Tehran",
        })
        self.assertEqual(resp.status_code, 302)
        fs = FooterSettings.load()
        self.assertEqual(fs.copyright_text, "My Copyright")
        self.assertEqual(fs.phone, "021-12345")
        self.assertEqual(fs.address, "Tehran")

    def test_badge_create(self):
        url = reverse("dashboard:footer-trust-badge-add")
        resp = self.client.post(url, {
            "title": "TestBadge",
            "image": _make_image("badge.png"),
            "display_order": "1",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterTrustBadge.objects.count(), 1)
        self.assertEqual(FooterTrustBadge.objects.first().title, "TestBadge")

    def test_badge_edit(self):
        badge = FooterTrustBadge.objects.create(title="Old", image=_make_image("old.png"))
        url = reverse("dashboard:footer-trust-badge-edit", args=[badge.pk])
        resp = self.client.post(url, {
            "title": "New",
            "display_order": "2",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        badge.refresh_from_db()
        self.assertEqual(badge.title, "New")

    def test_badge_delete(self):
        badge = FooterTrustBadge.objects.create(title="Del", image=_make_image("del.png"))
        url = reverse("dashboard:footer-trust-badge-delete", args=[badge.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterTrustBadge.objects.count(), 0)

    def test_badge_toggle(self):
        badge = FooterTrustBadge.objects.create(title="Toggle", image=_make_image("t.png"), is_active=True)
        url = reverse("dashboard:footer-trust-badge-toggle", args=[badge.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        badge.refresh_from_db()
        self.assertFalse(badge.is_active)

    def test_logo_create(self):
        url = reverse("dashboard:footer-payment-logo-add")
        resp = self.client.post(url, {
            "title": "ZarinPal",
            "image": _make_image("zp.png"),
            "display_order": "0",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterPaymentLogo.objects.count(), 1)

    def test_logo_edit(self):
        logo = FooterPaymentLogo.objects.create(title="Old", image=_make_image("old.png"))
        url = reverse("dashboard:footer-payment-logo-edit", args=[logo.pk])
        resp = self.client.post(url, {
            "title": "Updated",
            "display_order": "3",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        logo.refresh_from_db()
        self.assertEqual(logo.title, "Updated")

    def test_logo_delete(self):
        logo = FooterPaymentLogo.objects.create(title="Del", image=_make_image("del.png"))
        url = reverse("dashboard:footer-payment-logo-delete", args=[logo.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterPaymentLogo.objects.count(), 0)

    def test_logo_toggle(self):
        logo = FooterPaymentLogo.objects.create(title="Toggle", image=_make_image("t.png"), is_active=True)
        url = reverse("dashboard:footer-payment-logo-toggle", args=[logo.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        logo.refresh_from_db()
        self.assertFalse(logo.is_active)


# ---------------------------------------------------------------- Storefront Rendering


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class StorefrontFooterRenderTests(TestCase):
    """تست‌های رندر فوتر در فروشگاه."""

    def setUp(self):
        self.fs = FooterSettings.load()

    def _get_home(self):
        return self.client.get("/")

    def test_footer_enabled(self):
        self.fs.is_enabled = True
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "<footer")

    def test_footer_disabled(self):
        self.fs.is_enabled = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        # Footer tag exists but content is empty (guarded by is_enabled)
        self.assertNotIn("copy", content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else "")

    def test_branding_toggle_off(self):
        self.fs.show_branding = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        # The "about" class div shouldn't be in the footer
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="about"', footer_html)

    def test_contact_toggle_off(self):
        self.fs.show_contact = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("تماس با ما", footer_html)

    def test_contact_with_phone(self):
        self.fs.show_contact = True
        self.fs.phone = "021-9999"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "tel:021-9999")

    def test_contact_with_email(self):
        self.fs.show_contact = True
        self.fs.email = "info@test.ir"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "mailto:info@test.ir")

    def test_navigation_toggle_off(self):
        self.fs.show_navigation = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("NAV_FOOTER", footer_html)

    def test_social_toggle_off(self):
        self.fs.show_social_links = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="socials"', footer_html)

    def test_newsletter_toggle_on(self):
        self.fs.show_newsletter = True
        self.fs.newsletter_title = "خبرنامه تست"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "خبرنامه تست")
        self.assertContains(resp, "به‌زودی")

    def test_newsletter_toggle_off(self):
        self.fs.show_newsletter = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="news"', footer_html)

    def test_trust_badges_render(self):
        self.fs.show_trust_badges = True
        self.fs.save()
        FooterTrustBadge.objects.create(
            title="Enamad", image=_make_image("enamad.png"),
            destination_url="https://enamad.ir", is_active=True,
        )
        resp = self._get_home()
        self.assertContains(resp, "trust-badges")
        self.assertContains(resp, "https://enamad.ir")

    def test_payment_logos_render(self):
        self.fs.show_payment_logos = True
        self.fs.save()
        FooterPaymentLogo.objects.create(
            title="ZarinPal", image=_make_image("zp.png"), is_active=True,
        )
        resp = self._get_home()
        self.assertContains(resp, "payment-logos")

    def test_empty_trust_badges_not_shown(self):
        self.fs.show_trust_badges = True
        self.fs.save()
        # No badges exist
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("trust-badges", footer_html)

    def test_empty_payment_logos_not_shown(self):
        self.fs.show_payment_logos = True
        self.fs.save()
        # No logos exist
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("payment-logos", footer_html)

    def test_no_href_hash_in_footer(self):
        """فوتر نباید لینک‌های بی‌مقصد (href="#") داشته باشد."""
        self.fs.show_contact = True
        self.fs.phone = "021-1234"
        self.fs.email = "a@b.com"
        self.fs.address = "Test Address"
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('href="#"', footer_html)

    def test_copyright_custom_text(self):
        self.fs.copyright_text = "Custom (c) 2025"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "Custom (c) 2025")

    def test_copyright_default_uses_shop_name(self):
        self.fs.copyright_text = ""
        self.fs.save()
        resp = self._get_home()
        # Default uses SHOP_NAME from settings
        self.assertContains(resp, "دیجی‌مارکت")
