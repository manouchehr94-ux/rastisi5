from pathlib import Path
from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry
from apps.storefront_builder import global_region_registry as global_regions
from apps.storefront_builder import layout_preset_registry as presets
from apps.storefront_builder import section_registry


class PremiumLeatherShokolatiV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.preset = presets.get_layout_preset("premium_leather")
        self.home = self.preset.pages["home"]

    def test_identity_and_shell(self):
        self.assertEqual(self.preset.version, "2")
        self.assertEqual(self.preset.default_palette_slug, "chocolate-ice")
        self.assertEqual(self.preset.header["header_variant"], "chocolate_centered_search")
        self.assertEqual(self.preset.footer["footer_variant"], "chocolate_dark_columns")

    def test_palette_and_variants_registered(self):
        self.assertIsNotNone(appearance_registry.get_palette("chocolate-ice"))
        self.assertIsNotNone(global_regions.get_global_variant(global_regions.GLOBAL_HEADER_REGION, "chocolate_centered_search"))
        self.assertIsNotNone(global_regions.get_global_variant(global_regions.GLOBAL_FOOTER_REGION, "chocolate_dark_columns"))
        self.assertIn("chocolate_retail", section_registry.CARD_STYLE_CHOICES)
        self.assertIn("chocolate_story", section_registry.CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("chocolate_badges", section_registry.CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("chocolate_carousel", section_registry.HERO_STYLE_CHOICES)

    def test_chocolate_palette_uses_warm_neutral_page_and_card_surfaces(self):
        palette = appearance_registry.get_palette("chocolate-ice")
        self.assertEqual(palette.colors["background"], "#F7F1E8")
        self.assertEqual(palette.colors["surface"], "#FFFDF9")
        self.assertEqual(palette.colors["border"], "#E6D9CC")
        self.assertEqual(palette.theme_roles["card_bg"], "#FFFDF9")
        self.assertNotEqual(palette.colors["background"], "#EDF6FF")

    def test_chocolate_header_has_explicit_hover_contrast_and_warm_search_surface(self):
        root = Path(__file__).resolve().parents[3]
        css = (root / "apps/storefront_builder/static/css/storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn("RASTISI_PREMIUM_LEATHER_HEADER_PALETTE_FIX_BEGIN", css)
        self.assertIn(".gh-chocolate-nav-links a:hover", css)
        self.assertIn("background:#7B4518!important;color:#fff!important", css)
        self.assertIn("background:#FFF9F0", css)
        self.assertIn("max-width:520px", css)
    def test_home_reference_silhouette(self):
        keys = [entry.section_key for entry in self.home]
        self.assertEqual(keys[0:3], ["category_grid", "hero_banner", "category_grid"])
        self.assertEqual(self.home[0].settings["display_mode"], "chocolate_story")
        self.assertEqual(self.home[2].settings["display_mode"], "chocolate_badges")
        self.assertGreaterEqual(keys.count("product_section"), 4)
        self.assertGreaterEqual(keys.count("multi_banner"), 2)

    def test_home_product_rows_use_chocolate_card_and_four_desktop_columns(self):
        rows = [entry for entry in self.home if entry.section_key == "product_section"]
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row.settings["card"]["card_style"], "chocolate_retail")
            self.assertEqual(row.settings["responsive"]["desktop_columns"], 4)
            self.assertEqual(row.settings["responsive"]["mobile_columns"], 2)

    def test_no_reference_brand_assets_or_template_branch_in_new_templates(self):
        root = Path(__file__).resolve().parents[3]
        targets = [
            root / "apps/storefront_builder/templates/storefront_builder/partials/global_header/chocolate_centered_search.html",
            root / "apps/storefront_builder/templates/storefront_builder/partials/global_footer/chocolate_dark_columns.html",
            root / "apps/storefront_builder/templates/storefront_builder/sections/hero_banner_chocolate.html",
        ]
        merged = "\n".join(path.read_text(encoding="utf-8") for path in targets).lower()
        self.assertNotIn("shokolati", merged)
        self.assertNotIn("premium_leather", merged)
        self.assertNotIn("snapp", merged)
        self.assertNotIn("enamad", merged)
