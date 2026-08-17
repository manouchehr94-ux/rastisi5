from pathlib import Path

from django.conf import settings as django_settings
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry, section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase37HeroMerchantControlTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.page.containers.all().delete()

    def test_slider_default_preserves_historical_side(self):
        self.assertEqual(section_registry.default_slider_settings()["text_position"], "end")

    def test_slider_position_is_saved_from_merchant_form(self):
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="hero_banner",
            order=0,
            settings=section_registry.default_slider_settings(),
        )
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "autoplay": "on",
                "interval_ms": "4500",
                "show_arrows": "on",
                "show_dots": "on",
                "loop": "on",
                "text_position": "start",
            },
        )
        # Successful section-settings saves follow the Builder's existing
        # POST/redirect contract; validation errors stay on the form with 200.
        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["text_position"], "start")

    def test_slider_form_exposes_position_control(self):
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="hero_banner",
            order=0,
            settings=section_registry.default_slider_settings(),
        )
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        self.assertContains(response, "جای متن روی تصویر")
        self.assertContains(response, "سمت راست")
        self.assertContains(response, "وسط")
        self.assertContains(response, "سمت چپ")


class Phase37ReferenceTopPresetTests(StorefrontBuilderViewsTestCase):
    def test_reference_preset_uses_right_copy_and_seven_categories(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        hero = preset.pages["home"][1]
        category = preset.pages["home"][2]
        self.assertEqual(hero.settings["text_position"], "start")
        self.assertEqual(category.settings["display_mode"], "image_strip")
        self.assertEqual(category.settings["item_limit"], 7)


class Phase37GenericCssContractTests(StorefrontBuilderViewsTestCase):
    def test_top_fidelity_css_is_generic(self):
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/catalog/static/css/home.css").read_text(encoding="utf-8")
        self.assertIn('.hero-inner[data-text-position="start"]', css)
        self.assertIn(".product-section--spotlight", css)
        self.assertIn("repeat(auto-fit,minmax(112px,1fr))", css)
        self.assertNotIn("v5_golden_homepage", css)
        self.assertNotIn("golden-hero-row", css)
