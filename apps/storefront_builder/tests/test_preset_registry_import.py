"""Regression test for PresetDefinition field ordering.

This test would FAIL against commit 33a4e580 where ``default_palette_slug``
(a required field with no default) was placed AFTER ``card_image_crossfade``
and ``card_image_zoom`` (both fields with defaults), causing:

    TypeError: non-default argument 'default_palette_slug' follows default argument

The fix reorders fields so all required fields precede all defaulted fields.
"""

import importlib
import sys
from unittest import TestCase


class PresetRegistryImportTest(TestCase):
    """preset_registry must import without TypeError."""

    def test_import_succeeds(self):
        """Importing preset_registry does not raise TypeError."""
        # Force a fresh import (in case it was cached in a broken state)
        module_name = "apps.storefront_builder.preset_registry"
        if module_name in sys.modules:
            del sys.modules[module_name]
        module = importlib.import_module(module_name)
        self.assertTrue(hasattr(module, "PRESET_REGISTRY"))
        self.assertGreater(len(module.PRESET_REGISTRY), 0)

    def test_all_eleven_presets_registered(self):
        """All 11 family presets are registered.

        Originally written when only five families/presets existed (this
        was `test_all_five_presets_registered`). Six more presets
        (atlas_catalog_default, ava_fashion_default, toranj_gifting_default,
        sarv_stock_default, sepidar_handmade_default, zarrin_jewelry_default)
        were registered in a later checkpoint alongside their six new
        families — dedicated coverage for the full eleven-preset contract
        (exact count, each family_slug matches, each has a valid palette)
        already exists in
        apps.storefront_builder.tests.test_eleven_families. This
        assertion's expected set was simply never updated when those six
        presets were added; renamed to match its actual, current
        assertion rather than the historical five-preset checkpoint.
        """
        from apps.storefront_builder.preset_registry import PRESET_REGISTRY

        expected = {
            "modern_fashion_default",
            "artisan_editorial_default",
            "nordic_living_default",
            "heritage_premium_default",
            "vibrant_catalog_default",
            "atlas_catalog_default",
            "ava_fashion_default",
            "toranj_gifting_default",
            "sarv_stock_default",
            "sepidar_handmade_default",
            "zarrin_jewelry_default",
        }
        self.assertEqual(set(PRESET_REGISTRY.keys()), expected)

    def test_each_preset_has_valid_palette_slug(self):
        """Every preset has a non-empty default_palette_slug."""
        from apps.storefront_builder.preset_registry import PRESET_REGISTRY

        for slug, preset in PRESET_REGISTRY.items():
            self.assertTrue(
                preset.default_palette_slug,
                f"Preset '{slug}' has empty/None default_palette_slug",
            )

    def test_preset_image_settings_have_correct_types(self):
        """card_image_crossfade and card_image_zoom are booleans with expected defaults."""
        from apps.storefront_builder.preset_registry import PRESET_REGISTRY

        for slug, preset in PRESET_REGISTRY.items():
            self.assertIsInstance(preset.card_image_crossfade, bool, f"{slug}.card_image_crossfade is not bool")
            self.assertIsInstance(preset.card_image_zoom, bool, f"{slug}.card_image_zoom is not bool")

    def test_modern_fashion_preset_crossfade_true(self):
        """modern_fashion: crossfade=True, zoom=False."""
        from apps.storefront_builder.preset_registry import get_preset

        p = get_preset("modern_fashion_default")
        self.assertTrue(p.card_image_crossfade)
        self.assertFalse(p.card_image_zoom)

    def test_nordic_living_preset_crossfade_true(self):
        """nordic_living: crossfade=True, zoom=False."""
        from apps.storefront_builder.preset_registry import get_preset

        p = get_preset("nordic_living_default")
        self.assertTrue(p.card_image_crossfade)
        self.assertFalse(p.card_image_zoom)

    def test_heritage_premium_preset_defaults(self):
        """heritage_premium: crossfade=False (default), zoom=True (default)."""
        from apps.storefront_builder.preset_registry import get_preset

        p = get_preset("heritage_premium_default")
        self.assertFalse(p.card_image_crossfade)
        self.assertTrue(p.card_image_zoom)

    def test_all_families_still_resolvable(self):
        """All eleven families resolve with matching presets (iterates
        family_registry.list_families() dynamically — this assertion was
        never actually stale, only its docstring wording was outdated)."""
        from apps.storefront_builder import family_registry, preset_registry

        for family in family_registry.list_families():
            preset = preset_registry.get_preset(family.default_preset_slug)
            self.assertIsNotNone(
                preset,
                f"Family '{family.slug}' preset '{family.default_preset_slug}' not found",
            )

    def test_existing_presets_retain_section_layout_default(self):
        """default_section_layout defaults to empty tuple."""
        from apps.storefront_builder.preset_registry import PRESET_REGISTRY

        for slug, preset in PRESET_REGISTRY.items():
            self.assertEqual(
                preset.default_section_layout, (),
                f"Preset '{slug}' has unexpected default_section_layout",
            )
