"""Pure registry contract for ``dense_marketplace`` v2 / Beraito.

The Ready Template deliberately reuses the pre-existing generic
``v5_golden_homepage`` composition instead of creating a Beraito-specific
renderer. These tests lock the visual/data contract and cross-family
isolation without touching a database.
"""

from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry, layout_preset_registry as presets


class DenseMarketplaceBeraitoV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.preset = presets.get_layout_preset("dense_marketplace")
        self.golden = presets.get_layout_preset("v5_golden_homepage")

    def test_identity_palette_and_registered_shell(self):
        self.assertEqual(self.preset.version, "2")
        self.assertEqual(self.preset.default_palette_slug, "marketplace-spectrum")
        self.assertNotEqual(self.preset.default_palette_slug, self.golden.default_palette_slug)
        palette = appearance_registry.get_palette(self.preset.default_palette_slug)
        self.assertIsNotNone(palette)
        self.assertEqual(len(palette.section_tones), 5)
        self.assertEqual(self.preset.header["header_variant"], "marketplace_search_first")
        self.assertEqual(self.preset.footer["footer_variant"], "marketplace_dense")
        self.assertEqual(self.preset.appearance["content_width"], 1500)
        self.assertEqual(self.preset.appearance["grid_density"], 6)
        self.assertEqual(self.preset.appearance["image_fit"], "contain")

    def test_home_reuses_the_proven_generic_dense_commerce_composition(self):
        golden_home = self.golden.pages["home"]
        home = self.preset.pages["home"]
        self.assertEqual(len(home), len(golden_home) + 2)

        # Beraito reuses the Golden composition structurally, with one
        # semantics-preserving normalization: the row titled as best-sellers
        # must use the real ``best_sellers`` source (not ``most_viewed``).
        # This keeps the generic empty-section/public-shell contract intact
        # without changing the internal pre-U10 Golden preset.
        for actual, golden in zip(home[:len(golden_home)], golden_home):
            if (
                golden.section_key == "product_section"
                and golden.settings
                and golden.settings.get("title") == "پرفروش‌ترین‌های هفته"
            ):
                self.assertEqual(actual.settings["data_source"], "best_sellers")
                normalized_actual = {**actual.settings, "data_source": golden.settings["data_source"]}
                self.assertEqual(actual.section_key, golden.section_key)
                self.assertEqual(actual.row_key, golden.row_key)
                self.assertEqual(actual.row_span, golden.row_span)
                self.assertEqual(actual.container_settings, golden.container_settings)
                self.assertEqual(normalized_actual, golden.settings)
            else:
                self.assertEqual(actual, golden)

    def test_first_fold_matches_dense_commerce_structure(self):
        home = self.preset.pages["home"]
        hero_offer = home[0]
        hero = home[1]
        discovery = home[2]
        services = home[3]

        self.assertEqual(hero_offer.section_key, "product_section")
        self.assertEqual(hero_offer.row_key, hero.row_key)
        self.assertEqual(hero_offer.row_span, 3)
        self.assertEqual(hero.section_key, "hero_banner")
        self.assertEqual(hero.row_span, 9)
        self.assertEqual(discovery.section_key, "category_grid")
        self.assertEqual(discovery.settings["display_mode"], "image_strip")
        self.assertEqual(services.section_key, "trust_features")

    def test_dense_product_rows_are_real_store_data_and_compact(self):
        rows = [e for e in self.preset.pages["home"] if e.section_key == "product_section"]
        self.assertGreaterEqual(len(rows), 10)
        allowed_sources = {"newest", "discounted", "best_sellers", "most_viewed"}
        for row in rows:
            self.assertIn(row.settings["data_source"], allowed_sources)
            self.assertEqual(row.settings["card"]["card_style"], "compact")
            self.assertNotIn("source_id", row.settings)
            self.assertNotIn("product_ids", row.settings)

    def test_reference_coloured_merchandising_rows_use_generic_palette_roles(self):
        coloured = [
            e for e in self.preset.pages["home"]
            if e.section_key == "product_section"
            and (e.settings or {}).get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertGreaterEqual(len(coloured), 5)
        roles = {(e.settings or {})["background"]["palette_role"] for e in coloured}
        self.assertTrue({"tone-1", "tone-2", "tone-3", "tone-4", "tone-5"}.issubset(roles))
        for row in coloured:
            self.assertEqual(row.settings["background"]["pattern_slug"], "commerce-doodle")
            self.assertEqual(row.settings["responsive"]["desktop_columns"], 6)
            self.assertEqual(row.settings["responsive"]["mobile_columns"], 2)

    def test_other_reference_families_keep_their_versions_and_variants(self):
        expected = {
            "fashion_promo_catalog": ("7", "promo_search_nav"),
            "warm_boutique": ("2", "beauty_search_nav"),
            "premium_leather": ("2", "chocolate_centered_search"),
        }
        for key, (version, header_variant) in expected.items():
            sibling = presets.get_layout_preset(key)
            self.assertEqual(sibling.version, version, key)
            self.assertEqual(sibling.header["header_variant"], header_variant, key)
    def test_home_closes_with_generic_brand_and_blog_discovery(self):
        home = self.preset.pages["home"]
        self.assertEqual(home[-2].section_key, "brand_carousel")
        self.assertEqual(home[-2].settings["brand_ids"], [])
        self.assertEqual(home[-1].section_key, "blog_posts")
        self.assertEqual(home[-1].settings["item_limit"], 6)

    def test_marketplace_footer_uses_editable_footer_theme_role(self):
        from pathlib import Path
        css_path = Path(__file__).resolve().parents[1] / "static" / "css" / "storefront_builder.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".gf--marketplace{", css)
        self.assertIn("--gf-bg:var(--theme-footer-bg", css)
        self.assertIn("--gf-ink:var(--theme-footer-text", css)
