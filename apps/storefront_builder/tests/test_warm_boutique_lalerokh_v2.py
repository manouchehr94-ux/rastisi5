"""Reference-driven warm_boutique v2 (laleRokh family) architecture tests.

The goal of this suite is isolation, not screenshot approval: the new visual
identity must be expressed through registered generic palette/header/footer/
section/card choices while the already-completed fashion_promo_catalog remains
unchanged.  Real visual acceptance still happens through the preview/browser QA
pipeline on the merchant machine.
"""

from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry as appearance
from apps.storefront_builder import global_region_registry as global_regions
from apps.storefront_builder import layout_preset_registry as presets
from apps.storefront_builder import section_registry


_REPO_ROOT = Path(__file__).resolve().parents[3]


class WarmBoutiqueV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.preset = presets.get_layout_preset("warm_boutique")

    def test_version_palette_and_global_variants(self):
        self.assertEqual(self.preset.version, "2")
        self.assertEqual(self.preset.default_palette_slug, "beauty-magenta")
        self.assertEqual(self.preset.header["header_variant"], "beauty_search_nav")
        self.assertEqual(self.preset.footer["footer_variant"], "beauty_retail_columns")

    def test_beauty_palette_has_magenta_identity_and_green_commerce_accent(self):
        palette = appearance.get_palette("beauty-magenta")
        self.assertIsNotNone(palette)
        self.assertEqual(palette.colors["primary"], "#8A007A")
        self.assertEqual(palette.colors["accent"], "#63CF70")
        self.assertEqual(palette.colors["background"], "#FFFFFF")
        # Keep the official Ready Template on the established plain-palette
        # contract; the beauty card intentionally uses primary for price.
        self.assertFalse(palette.theme_roles)

    def test_home_uses_reference_driven_registered_primitives(self):
        home = self.preset.pages["home"]
        keys = [entry.section_key for entry in home]
        self.assertEqual(keys[0], "hero_banner")
        self.assertEqual(home[0].settings["hero_style"], "beauty_editorial")
        self.assertIn("category_grid", keys)
        self.assertEqual(keys.count("product_section"), 3)
        self.assertEqual(keys.count("multi_banner"), 2)
        banners = [entry for entry in home if entry.section_key == "multi_banner"]
        self.assertEqual(banners[0].settings["layout_variant"], "promo-4")
        self.assertEqual(keys.count("catalog_product_wall"), 2)
        self.assertIn("brand_carousel", keys)
        self.assertEqual(keys[-1], "newsletter")

        category = next(entry for entry in home if entry.section_key == "category_grid")
        self.assertEqual(category.settings["display_mode"], "beauty_icons")
        brands = next(entry for entry in home if entry.section_key == "brand_carousel")
        self.assertEqual(brands.settings["display_mode"], "beauty_tabs")

    def test_all_explicit_home_product_rows_use_beauty_retail_card(self):
        rows = [e for e in self.preset.pages["home"] if e.section_key == "product_section"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row.settings["card"]["card_style"], "beauty_retail")
            self.assertEqual(row.settings["responsive"]["mobile_columns"], 2)
        campaign_rows = [row for row in rows if row.settings["display_mode"] == "campaign_band"]
        self.assertEqual(len(campaign_rows), 2)
        self.assertTrue(all(row.settings["item_limit"] == 4 for row in campaign_rows))
        self.assertTrue(all(row.settings["responsive"]["desktop_columns"] == 4 for row in campaign_rows))
        final_row = rows[-1]
        self.assertEqual(final_row.settings["data_source"], "most_viewed")
        self.assertEqual(final_row.settings["responsive"]["desktop_columns"], 5)

    def test_product_walls_reuse_id_free_store_runtime_resolution(self):
        walls = [e for e in self.preset.pages["home"] if e.section_key == "catalog_product_wall"]
        self.assertEqual([wall.settings["layout_mode"] for wall in walls], ["group_columns", "featured_row"])
        self.assertTrue(all("source_id" not in wall.settings for wall in walls))
        self.assertEqual(walls[0].settings["source_mode"], "categories_then_collections")
        self.assertEqual(walls[0].settings["card"]["card_style"], "retail_list")
        self.assertEqual(walls[0].settings["max_groups"], 3)
        self.assertEqual(walls[1].settings["source_mode"], "visible_collections")
        self.assertEqual(walls[1].settings["card"]["card_style"], "beauty_retail")
        self.assertEqual(walls[1].settings["responsive"]["desktop_columns"], 5)

    def test_beauty_choices_are_real_registered_generic_options(self):
        self.assertIn("beauty_retail", section_registry.CARD_STYLE_CHOICES)
        self.assertIn("retail_list", section_registry.CARD_STYLE_CHOICES)
        self.assertEqual(
            section_registry.CATALOG_PRODUCT_WALL_LAYOUT_MODES,
            ("rows", "group_columns", "featured_row"),
        )
        self.assertIn("beauty_icons", section_registry.CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("beauty_tabs", section_registry.BRAND_CAROUSEL_DISPLAY_MODES)
        self.assertIn("campaign_band", section_registry.PRODUCT_SECTION_DISPLAY_MODES)
        self.assertIsNotNone(global_regions.get_global_variant(global_regions.GLOBAL_HEADER_REGION, "beauty_search_nav"))
        self.assertIsNotNone(global_regions.get_global_variant(global_regions.GLOBAL_FOOTER_REGION, "beauty_retail_columns"))


class WarmBoutiqueIsolationTests(SimpleTestCase):
    def test_only_warm_boutique_opts_into_new_beauty_identity(self):
        ready = [p for p in presets.list_layout_presets() if p.is_ready_template]
        for preset in ready:
            home = preset.pages.get("home", ())
            card_styles = {
                (entry.settings or {}).get("card", {}).get("card_style")
                for entry in home
                if entry.section_key in {"product_section", "catalog_product_wall"}
            }
            category_modes = {
                (entry.settings or {}).get("display_mode")
                for entry in home
                if entry.section_key == "category_grid"
            }
            if preset.key == "warm_boutique":
                self.assertEqual(preset.header["header_variant"], "beauty_search_nav")
                self.assertEqual(preset.footer["footer_variant"], "beauty_retail_columns")
                self.assertEqual(preset.default_palette_slug, "beauty-magenta")
                self.assertIn("beauty_retail", card_styles)
                self.assertIn("beauty_icons", category_modes)
            else:
                self.assertNotEqual(preset.header.get("header_variant"), "beauty_search_nav")
                self.assertNotEqual(preset.footer.get("footer_variant"), "beauty_retail_columns")
                self.assertNotEqual(preset.default_palette_slug, "beauty-magenta")
                self.assertNotIn("beauty_retail", card_styles)
                self.assertNotIn("beauty_icons", category_modes)

    def test_completed_ibolak_template_contract_stays_frozen(self):
        fashion = presets.get_layout_preset("fashion_promo_catalog")
        self.assertEqual(fashion.version, "7")
        self.assertEqual(fashion.header["header_variant"], "promo_search_nav")
        self.assertEqual(fashion.footer["footer_variant"], "promo_columns")
        self.assertEqual(fashion.default_palette_slug, "magenta-pop")

    def test_new_renderer_sources_have_no_template_or_store_branching(self):
        paths = [
            _REPO_ROOT / "apps/storefront_builder/templates/storefront_builder/partials/global_header/beauty_search_nav.html",
            _REPO_ROOT / "apps/storefront_builder/templates/storefront_builder/partials/global_footer/beauty_retail_columns.html",
        ]
        forbidden = ("template_key", "warm_boutique", "store.slug", "store.pk", "rasti-mode-demo", "lalerokh")
        for path in paths:
            source = path.read_text().lower()
            for token in forbidden:
                self.assertNotIn(token.lower(), source, f"{token} leaked into {path.name}")

    def test_batch_one_does_not_override_listing_or_pdp_composition(self):
        # Home is the first implementation batch. Listing/PDP remain the U10
        # standard composition until their own reference-driven passes.
        warm = presets.get_layout_preset("warm_boutique")
        self.assertEqual([e.section_key for e in warm.pages["listing"]], ["product_listing"])
        self.assertEqual(
            [e.section_key for e in warm.pages["product_detail"]],
            ["product_main", "product_description", "related_products"],
        )
