from pathlib import Path

from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase34NaturalHeightAndAnnouncementTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)

    def test_builder_cells_use_natural_height_instead_of_stretched_frames(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        phase = css[css.index("Phase 3.4 — natural cell frames"):]
        self.assertIn("align-items: start !important", phase)
        self.assertIn("height: max-content !important", phase)
        self.assertIn("align-self: start !important", phase)
        self.assertIn("background: transparent !important", phase)
        self.assertNotIn("align-items: stretch !important", phase)

    def test_announcement_links_accept_internal_external_and_phone_toggle(self):
        cleaned = layout_service.validate_header_config({
            "show_search": True,
            "show_account": True,
            "show_cart": True,
            "show_wishlist": True,
            "sticky": True,
            "announcement_enabled": True,
            "announcement_text": "پیام",
            "announcement_links": [
                {"label": "پیگیری", "url": "/track/"},
                {"label": "راهنما", "url": "https://example.com/help"},
            ],
            "announcement_show_phone": False,
        })
        self.assertEqual(cleaned["announcement_links"][0], {"label": "پیگیری", "url": "/track/"})
        self.assertEqual(cleaned["announcement_links"][1]["label"], "راهنما")
        self.assertFalse(cleaned["announcement_show_phone"])

    def test_announcement_rejects_unsafe_link_scheme(self):
        with self.assertRaises(layout_service.HeaderConfigValidationError):
            layout_service.validate_header_config({
                "show_cart": True,
                "announcement_links": [{"label": "بد", "url": "javascript:alert(1)"}],
            })

    def test_header_editor_persists_announcement_text_links_and_phone_toggle(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-header"),
            {
                "show_search": "on",
                "show_account": "on",
                "show_cart": "on",
                "show_wishlist": "on",
                "sticky": "on",
                "announcement_enabled": "on",
                "announcement_text": "ارسال امروز",
                "announcement_link_label": ["پیگیری سفارش", "سوالات"],
                "announcement_link_url": ["/track/", "/faq/"],
                "announcement_show_phone": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["announcement_text"], "ارسال امروز")
        self.assertEqual(
            self.draft.header_config["announcement_links"],
            [
                {"label": "پیگیری سفارش", "url": "/track/"},
                {"label": "سوالات", "url": "/faq/"},
            ],
        )
        self.assertTrue(self.draft.header_config["announcement_show_phone"])

    def test_preview_renders_configured_announcement_and_direct_edit_control(self):
        self.draft.header_config = {
            **self.draft.effective_header_config(),
            "announcement_enabled": True,
            "announcement_text": "اعلان قابل ویرایش",
            "announcement_links": [
                {"label": "رهگیری من", "url": "/my-track/"},
                {"label": "کمک", "url": "#help"},
            ],
            "announcement_show_phone": False,
        }
        self.draft.save(update_fields=["header_config", "updated_at"])

        response = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home"
        )
        html = response.content.decode("utf-8")
        self.assertIn("اعلان قابل ویرایش", html)
        self.assertIn('href="/my-track/"', html)
        self.assertIn(">رهگیری من</a>", html)
        self.assertNotIn('class="sfb-announcement-phone"', html)
        self.assertIn("data-open-header-settings", html)
        self.assertIn("ویرایش نوار اعلان", html)

    def test_editor_can_open_header_settings_from_preview_message(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-editor") + "?page=home"
        )
        html = response.content.decode("utf-8")
        self.assertIn("sfb:openHeaderSettings", html)
        self.assertIn("هدر فروشگاه", html)

    def test_header_panel_exposes_announcement_link_editor(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-header"),
            HTTP_HX_REQUEST="true",
        )
        html = response.content.decode("utf-8")
        self.assertIn("announcement_link_label", html)
        self.assertIn("announcement_link_url", html)
        self.assertIn("announcement_show_phone", html)
        self.assertIn("لینک‌های نوار اعلان", html)
