"""تست‌های جامع ۱۱ خانواده — Gate 1 و Gate 6 Acceptance.

اثبات:
  - دقیقاً ۱۱ Family در Registry
  - پنج Family قبلی حفظ شده
  - شش Family جدید ثبت شده
  - هر ۱۱ Family دارای Preset معتبر
  - هر ۱۱ Family دارای default_section_keys معتبر
  - هر ۱۱ Family دارای template path های کامل
  - Swatch منحصربه‌فرد
"""
import os
import unittest


EXPECTED_EXISTING = {"modern_fashion", "heritage_premium", "artisan_editorial", "vibrant_catalog", "nordic_living"}
EXPECTED_NEW = {"atlas_catalog", "ava_fashion", "toranj_gifting", "sarv_stock", "sepidar_handmade", "zarrin_jewelry"}
EXPECTED_ALL = EXPECTED_EXISTING | EXPECTED_NEW


class ElevenFamilyRegistryTests(unittest.TestCase):
    """Registry count and completeness."""

    def test_exactly_11_families(self):
        from apps.storefront_builder import family_registry
        self.assertEqual(len(family_registry.list_families()), 11)

    def test_all_expected_slugs_present(self):
        from apps.storefront_builder import family_registry
        slugs = {f.slug for f in family_registry.list_families()}
        self.assertEqual(slugs, EXPECTED_ALL)

    def test_existing_five_preserved(self):
        from apps.storefront_builder import family_registry
        slugs = {f.slug for f in family_registry.list_families()}
        self.assertTrue(EXPECTED_EXISTING.issubset(slugs))

    def test_six_new_registered(self):
        from apps.storefront_builder import family_registry
        slugs = {f.slug for f in family_registry.list_families()}
        self.assertTrue(EXPECTED_NEW.issubset(slugs))

    def test_each_family_has_valid_preset(self):
        from apps.storefront_builder import family_registry, preset_registry
        for family in family_registry.list_families():
            preset = preset_registry.get_preset(family.default_preset_slug)
            self.assertIsNotNone(preset, f"{family.slug}: preset '{family.default_preset_slug}' not found")

    def test_each_family_has_valid_section_keys(self):
        from apps.storefront_builder import family_registry, section_registry
        for family in family_registry.list_families():
            self.assertGreater(len(family.default_section_keys), 2,
                               f"{family.slug} has too few default sections")
            for key in family.default_section_keys:
                self.assertTrue(section_registry.is_valid_section_key(key),
                                f"{family.slug}: section key '{key}' invalid")

    def test_each_family_has_complete_variant_paths(self):
        from apps.storefront_builder import family_registry
        for family in family_registry.list_families():
            self.assertTrue(family.header_variant, f"{family.slug} missing header_variant")
            self.assertTrue(family.hero_variant, f"{family.slug} missing hero_variant")
            self.assertTrue(family.category_variant, f"{family.slug} missing category_variant")
            self.assertTrue(family.footer_variant, f"{family.slug} missing footer_variant")
            self.assertTrue(family.product_card_variant, f"{family.slug} missing product_card_variant")
            self.assertTrue(family.product_page_variant, f"{family.slug} missing product_page_variant")

    def test_distinct_swatches(self):
        from apps.storefront_builder import family_registry
        swatches = [f.swatch for f in family_registry.list_families()]
        self.assertEqual(len(swatches), len(set(swatches)), "Duplicate swatches found")


class ElevenFamilyTemplateFilesTests(unittest.TestCase):
    """Template files exist on disk for all 11 families."""

    def _repo_root(self):
        path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(10):
            if os.path.exists(os.path.join(path, "manage.py")):
                return path
            path = os.path.dirname(path)
        return path

    def test_structural_templates_exist(self):
        root = self._repo_root()
        for slug in EXPECTED_ALL:
            for part in ("header.html", "hero.html", "category.html", "footer.html"):
                path = os.path.join(root, "apps/storefront_builder/templates/storefront_builder/partials/families", slug, part)
                self.assertTrue(os.path.isfile(path), f"Missing: {slug}/{part}")

    def test_product_card_templates_exist(self):
        from apps.storefront_builder import family_registry
        root = self._repo_root()
        for family in family_registry.list_families():
            card_path = os.path.join(root, "apps/catalog/templates", family.product_card_variant)
            self.assertTrue(os.path.isfile(card_path),
                            f"{family.slug}: product card template not found at {family.product_card_variant}")

    def test_product_page_templates_exist(self):
        from apps.storefront_builder import family_registry
        root = self._repo_root()
        for family in family_registry.list_families():
            page_path = os.path.join(root, "apps/catalog/templates", family.product_page_variant)
            self.assertTrue(os.path.isfile(page_path),
                            f"{family.slug}: product page template not found at {family.product_page_variant}")

    def test_css_files_exist(self):
        root = self._repo_root()
        for slug in EXPECTED_ALL:
            css_path = os.path.join(root, "apps/core/static/css/families", f"{slug}.css")
            self.assertTrue(os.path.isfile(css_path), f"Missing CSS: {slug}.css")


class ElevenFamilyPresetTests(unittest.TestCase):
    """Preset configuration integrity."""

    def test_exactly_11_presets(self):
        from apps.storefront_builder import preset_registry
        # At least 11 (might have more if families have multiple presets)
        self.assertGreaterEqual(len(preset_registry.PRESET_REGISTRY), 11)

    def test_each_new_family_preset_has_palette(self):
        from apps.storefront_builder import preset_registry
        for slug in EXPECTED_NEW:
            preset = preset_registry.get_preset(f"{slug}_default")
            self.assertIsNotNone(preset, f"Preset '{slug}_default' not found")
            self.assertTrue(preset.default_palette_slug, f"{slug}: empty palette slug")

    def test_preset_family_slug_matches(self):
        from apps.storefront_builder import preset_registry
        for slug in EXPECTED_ALL:
            preset = preset_registry.get_preset(f"{slug}_default")
            if preset:
                self.assertEqual(preset.family_slug, slug)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    unittest.main()
