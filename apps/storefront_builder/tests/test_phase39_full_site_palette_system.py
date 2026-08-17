from pathlib import Path

from django.conf import settings as django_settings
from django.urls import reverse

from apps.storefront_builder import appearance_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase39FullSitePaletteRegistryTests(StorefrontBuilderViewsTestCase):
    def test_at_least_twelve_dramatic_full_site_themes_exist(self):
        themes = [p for p in appearance_registry.list_palettes() if p.group_fa == "تم کامل"]
        self.assertGreaterEqual(len(themes), 12)
        for palette in themes:
            self.assertEqual(set(palette.theme_roles), set(appearance_registry.THEME_ROLE_KEYS))

    def test_black_gold_is_a_true_dark_theme_with_yellow_text(self):
        palette = appearance_registry.get_palette("theme-black-gold")
        self.assertEqual(palette.colors["background"], "#070707")
        self.assertEqual(palette.colors["surface"], "#151515")
        self.assertEqual(palette.colors["text"], "#FFE76A")
        self.assertEqual(palette.theme_roles["footer_bg"], "#030303")

    def test_manual_text_override_does_not_destroy_rest_of_theme(self):
        base = {
            "palette_slug": "theme-black-gold",
            "color_overrides": {},
            "theme_overrides": {},
        }
        before = appearance_registry.resolve_colors(base)
        after = appearance_registry.resolve_colors({
            **base,
            "color_overrides": {"text": "#FF0000"},
        })
        self.assertEqual(after["text"], "#FF0000")
        self.assertEqual(after["primary"], before["primary"])
        self.assertEqual(after["background"], before["background"])

    def test_region_override_can_change_only_footer(self):
        config = {
            "palette_slug": "theme-midnight-electric",
            "color_overrides": {},
            "theme_overrides": {"footer_bg": "#123456"},
        }
        roles = appearance_registry.resolve_theme_roles(config)
        self.assertEqual(roles["footer_bg"], "#123456")
        self.assertEqual(roles["header_bg"], "#070B18")


class Phase39MerchantPaletteWorkflowTests(StorefrontBuilderViewsTestCase):
    def test_appearance_panel_exposes_full_theme_and_individual_region_colors(self):
        response = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تم کامل")
        self.assertContains(response, "مشکی طلایی")
        self.assertContains(response, "شب الکتریکی")
        self.assertContains(response, "رنگ متن اصلی کل سایت")
        self.assertContains(response, "پس‌زمینه هدر")
        self.assertContains(response, "پس‌زمینه فوتر")
        self.assertContains(response, "رنگ قیمت")

    def test_select_theme_then_override_text_and_footer_independently(self):
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        current = draft.effective_appearance_config()

        response = self.client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {
                "palette_slug": "theme-black-gold",
                "template_slug": current["template_slug"],
            },
        )
        self.assertEqual(response.status_code, 302)

        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config["palette_slug"], "theme-black-gold")
        self.assertEqual(draft.appearance_config["color_overrides"], {})
        self.assertEqual(draft.appearance_config["theme_overrides"], {})

        response = self.client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {
                "palette_slug": "theme-black-gold",
                "template_slug": draft.effective_appearance_config()["template_slug"],
                "color_text": "#FF0000",
                "theme_footer_bg": "#222244",
            },
        )
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config["color_overrides"]["text"], "#FF0000")
        self.assertEqual(draft.appearance_config["theme_overrides"]["footer_bg"], "#222244")
        self.assertNotIn("primary", draft.appearance_config["color_overrides"])


class Phase39GlobalThemeCssContractTests(StorefrontBuilderViewsTestCase):
    def test_theme_css_is_loaded_after_page_extra_css(self):
        root = Path(django_settings.BASE_DIR)
        base = (root / "templates/base.html").read_text(encoding="utf-8")
        extra = base.index("{% block extra_css %}{% endblock %}")
        theme = base.index("css/theme_palette.css")
        self.assertGreater(theme, extra)

    def test_theme_css_covers_all_major_storefront_surfaces(self):
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/core/static/css/theme_palette.css").read_text(encoding="utf-8")
        for needle in (
            ".header{",
            ".nav{",
            ".pcard,.card,.plp-filters",
            ".gallery .main",
            ".top,.stepper-bar",
            ".footer{",
            "--theme-card-bg",
        ):
            self.assertIn(needle, css)

    def test_theme_css_has_no_store_or_preset_specific_branch(self):
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/core/static/css/theme_palette.css").read_text(encoding="utf-8")
        self.assertNotIn("v5_golden_homepage", css)
        self.assertNotIn("golden-hero-row", css)
        self.assertNotIn("rastisi-fashion-test", css)
