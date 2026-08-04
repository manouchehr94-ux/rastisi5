from django.test import TestCase

from apps.storefront_builder.section_registry import (
    SECTION_REGISTRY,
    UnknownSectionTypeError,
    get_definition,
    is_valid_section_key,
    list_definitions,
)

EXPECTED_KEYS = {
    "announcement_bar", "hero_banner", "image_slider", "single_banner",
    "multi_banner", "category_grid", "featured_products", "newest_products",
    "best_sellers", "discounted_products", "amazing_offers", "brand_carousel",
    "promo_cards", "rich_text", "image_text", "trust_features",
}


class SectionRegistryTests(TestCase):
    def test_all_required_keys_registered(self):
        self.assertEqual(set(SECTION_REGISTRY.keys()), EXPECTED_KEYS)

    def test_get_definition_valid(self):
        definition = get_definition("hero_banner")
        self.assertEqual(definition.key, "hero_banner")
        self.assertTrue(definition.template_name.startswith("storefront_builder/sections/"))

    def test_get_definition_unknown_key_rejected(self):
        with self.assertRaises(UnknownSectionTypeError):
            get_definition("<script>alert(1)</script>")

    def test_get_definition_unknown_key_never_returns_template(self):
        """A bogus key must never resolve to any template path."""
        try:
            get_definition("not_a_real_section")
        except UnknownSectionTypeError as exc:
            self.assertIn("not_a_real_section", str(exc))
        else:
            self.fail("expected UnknownSectionTypeError")

    def test_is_valid_section_key(self):
        self.assertTrue(is_valid_section_key("category_grid"))
        self.assertFalse(is_valid_section_key("totally_made_up"))

    def test_list_definitions_matches_registry_size(self):
        self.assertEqual(len(list_definitions()), len(SECTION_REGISTRY))

    def test_singleton_sections_capped_at_one(self):
        for key in ("announcement_bar", "hero_banner", "trust_features"):
            definition = get_definition(key)
            self.assertEqual(definition.max_instances, 1)
            self.assertFalse(definition.duplicable)

    def test_validate_settings_rejects_non_dict(self):
        definition = get_definition("hero_banner")
        with self.assertRaises(ValueError):
            definition.validate_settings("not a dict")

    def test_validate_settings_accepts_dict(self):
        definition = get_definition("hero_banner")
        result = definition.validate_settings({"foo": "bar"})
        self.assertEqual(result, {"foo": "bar"})
