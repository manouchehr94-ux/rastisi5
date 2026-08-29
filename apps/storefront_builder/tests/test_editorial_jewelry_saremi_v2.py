from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry as ar
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.global_region_registry import GLOBAL_HEADER_REGION
from apps.storefront_builder.section_registry import (
    CATEGORY_GRID_DISPLAY_MODES,
    HERO_STYLE_CHOICES,
    MULTI_BANNER_KNOWN_LAYOUT_VARIANTS,
    get_definition,
)
from apps.storefront_builder.variant_contract import resolve_active_variant, resolve_renderer_template


class EditorialJewelrySaremiV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.preset = lpr.get_layout_preset("editorial_jewelry")

    def test_version_palette_and_global_chrome(self):
        self.assertEqual(self.preset.version, "2")
        self.assertEqual(self.preset.default_palette_slug, "atelier-ivory")
        self.assertEqual(self.preset.appearance["content_width"], 1320)
        self.assertEqual(self.preset.header["header_variant"], "atelier_nav")
        self.assertFalse(self.preset.header["announcement_enabled"])
        self.assertEqual(self.preset.footer["footer_variant"], "boutique_editorial")
        self.assertTrue(self.preset.footer["show_copyright"])
        for key in ("show_about", "show_contact", "show_categories", "show_quick_links",
                    "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter"):
            self.assertFalse(self.preset.footer[key], key)

    def test_home_composition_is_editorial_and_data_driven(self):
        entries = self.preset.pages["home"]
        self.assertEqual([e.section_key for e in entries], [
            "hero_banner", "category_grid", "multi_banner", "product_section",
            "product_section", "multi_banner", "multi_banner",
        ])
        self.assertEqual(entries[0].settings["hero_style"], "atelier_triptych")
        self.assertEqual(entries[1].settings["display_mode"], "atelier_mosaic")
        self.assertEqual(entries[1].settings["item_limit"], 12)
        self.assertEqual((entries[2].settings["offset"], entries[2].settings["item_limit"], entries[2].settings["layout_variant"]), (0, 2, "atelier-duo"))
        self.assertEqual((entries[5].settings["offset"], entries[5].settings["item_limit"], entries[5].settings["layout_variant"]), (2, 2, "atelier-duo"))
        self.assertEqual((entries[6].settings["offset"], entries[6].settings["item_limit"], entries[6].settings["layout_variant"]), (4, 1, "atelier-wide"))

    def test_product_rows_use_honest_store_scoped_sources_and_minimal_cards(self):
        rows = [e for e in self.preset.pages["home"] if e.section_key == "product_section"]
        self.assertEqual([r.settings["data_source"] for r in rows], ["newest", "best_sellers"])
        self.assertEqual([r.settings["item_limit"] for r in rows], [8, 4])
        for row in rows:
            self.assertEqual(row.settings["display_mode"], "grid")
            self.assertEqual(row.settings["responsive"]["desktop_columns"], 4)
            card = row.settings["card"]
            self.assertEqual(card["card_style"], "minimal")
            self.assertFalse(card["show_brand"])
            self.assertFalse(card["show_rating"])
            self.assertFalse(card["show_wishlist"])
            self.assertFalse(card["show_badge"])
            self.assertFalse(card["show_quick_add"])

    def test_new_generic_variants_are_registered(self):
        self.assertIn("atelier_triptych", HERO_STYLE_CHOICES)
        self.assertIn("atelier_mosaic", CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("atelier-duo", MULTI_BANNER_KNOWN_LAYOUT_VARIANTS)
        self.assertIn("atelier-wide", MULTI_BANNER_KNOWN_LAYOUT_VARIANTS)
        self.assertIn("atelier_nav", {v.key for v in GLOBAL_HEADER_REGION.variants})
        palette = ar.get_palette("atelier-ivory")
        self.assertIsNotNone(palette)
        self.assertTrue(palette.theme_roles)

    def test_atelier_hero_resolves_through_variant_contract(self):
        definition = get_definition("hero_banner")
        active = resolve_active_variant(definition, {"hero_style": "atelier_triptych"})
        self.assertEqual(
            resolve_renderer_template(definition, active),
            "storefront_builder/sections/hero_banner_atelier.html",
        )

    def test_runtime_templates_do_not_embed_reference_brand_or_template_key_branch(self):
        repo = Path(__file__).resolve().parents[3]
        files = (
            repo / "apps/storefront_builder/templates/storefront_builder/partials/global_header/atelier_nav.html",
            repo / "apps/storefront_builder/templates/storefront_builder/sections/hero_banner_atelier.html",
            repo / "apps/storefront_builder/templates/storefront_builder/sections/category_grid.html",
        )
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("saremi", text, str(path))
            self.assertNotIn("template_key", text, str(path))

    def test_other_accepted_families_keep_their_frozen_versions(self):
        expected = {
            "fashion_promo_catalog": "7",
            "warm_boutique": "2",
            "premium_leather": "2",
            "dense_marketplace": "2",
        }
        for key, version in expected.items():
            self.assertEqual(lpr.get_layout_preset(key).version, version, key)
