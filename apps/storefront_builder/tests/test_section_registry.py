from django.test import TestCase

from apps.storefront_builder.section_registry import (
    COLUMN_AWARE_SECTION_KEYS,
    DESTINATION_AWARE_SECTION_KEYS,
    SECTION_REGISTRY,
    DestinationSettingsError,
    ProductSectionSettingsError,
    ResponsiveSettingsError,
    UnknownSectionTypeError,
    default_destination_settings,
    default_responsive_settings,
    get_definition,
    is_valid_section_key,
    list_definitions,
    validate_destination_settings,
    validate_responsive_settings,
)

EXPECTED_KEYS = {
    "announcement_bar", "hero_banner", "image_slider", "single_banner",
    "multi_banner", "category_grid", "featured_products", "newest_products",
    "best_sellers", "discounted_products", "amazing_offers", "brand_carousel",
    "promo_cards", "rich_text", "image_text", "product_section", "trust_features",
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
        """از فازِ D به بعد، خروجیِ هر validate_settings همیشه یک بلوکِ
        ``responsive`` پیش‌فرض (نمایان همه‌جا) هم دارد — بدونِ تغییرِ
        رفتارِ خودِ منطقِ passthrough."""
        definition = get_definition("hero_banner")
        result = definition.validate_settings({"foo": "bar"})
        self.assertEqual(result["foo"], "bar")
        self.assertEqual(result["responsive"], {
            "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
        })


class ProductSectionSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("product_section")

    def _validate(self, **overrides):
        raw = {"data_source": "newest"} | overrides
        return self.definition.validate_settings(raw)

    def test_defaults_are_already_valid(self):
        cleaned = self.definition.validate_settings(self.definition.default_settings())
        self.assertEqual(cleaned["data_source"], "newest")

    def test_rejects_unknown_data_source(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="totally_made_up")

    def test_rejects_missing_data_source(self):
        with self.assertRaises(ProductSectionSettingsError):
            self.definition.validate_settings({})

    def test_display_mode_falls_back_to_carousel_on_invalid_value(self):
        cleaned = self._validate(display_mode="not_a_mode")
        self.assertEqual(cleaned["display_mode"], "carousel")

    def test_display_mode_grid_is_accepted(self):
        cleaned = self._validate(display_mode="grid")
        self.assertEqual(cleaned["display_mode"], "grid")

    def test_item_limit_clamped_to_safe_range(self):
        self.assertEqual(self._validate(item_limit=0)["item_limit"], 2)
        self.assertEqual(self._validate(item_limit=999)["item_limit"], 24)
        self.assertEqual(self._validate(item_limit=8)["item_limit"], 8)

    def test_item_limit_non_numeric_rejected(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(item_limit="abc")

    def test_title_and_subtitle_trimmed_and_capped(self):
        cleaned = self._validate(title="  عنوان  ", subtitle="  زیرعنوان  ")
        self.assertEqual(cleaned["title"], "عنوان")
        self.assertEqual(cleaned["subtitle"], "زیرعنوان")
        long_title = "الف" * 200
        cleaned = self._validate(title=long_title)
        self.assertEqual(len(cleaned["title"]), 60)

    def test_collection_requires_source_id(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection")

    def test_collection_accepts_positive_source_id(self):
        cleaned = self._validate(data_source="collection", source_id=5)
        self.assertEqual(cleaned["source_id"], 5)
        self.assertEqual(cleaned["product_ids"], [])

    def test_collection_rejects_non_positive_source_id(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection", source_id=0)
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="collection", source_id=-3)

    def test_category_and_brand_also_require_source_id(self):
        for source in ("category", "brand"):
            with self.assertRaises(ProductSectionSettingsError):
                self._validate(data_source=source)
            cleaned = self._validate(data_source=source, source_id=1)
            self.assertEqual(cleaned["source_id"], 1)

    def test_algorithmic_sources_ignore_source_id(self):
        for source in ("newest", "discounted", "best_sellers", "most_viewed"):
            cleaned = self._validate(data_source=source, source_id=999)
            self.assertIsNone(cleaned["source_id"])

    def test_manual_requires_at_least_one_product(self):
        with self.assertRaises(ProductSectionSettingsError):
            self._validate(data_source="manual", product_ids=[])

    def test_manual_deduplicates_and_preserves_order(self):
        cleaned = self._validate(data_source="manual", product_ids=[5, 3, 5, 7])
        self.assertEqual(cleaned["product_ids"], [5, 3, 7])
        self.assertIsNone(cleaned["source_id"])

    def test_manual_drops_non_positive_ids(self):
        cleaned = self._validate(data_source="manual", product_ids=[0, -1, 4])
        self.assertEqual(cleaned["product_ids"], [4])

    def test_manual_product_ids_capped(self):
        cleaned = self._validate(data_source="manual", product_ids=list(range(1, 200)))
        self.assertEqual(len(cleaned["product_ids"]), 60)

    def test_non_manual_source_ignores_product_ids(self):
        cleaned = self._validate(data_source="newest", product_ids=[1, 2, 3])
        self.assertEqual(cleaned["product_ids"], [])

    def test_show_view_all_defaults_true(self):
        self.assertTrue(self._validate()["show_view_all"])

    def test_show_view_all_accepts_false(self):
        self.assertFalse(self._validate(show_view_all=False)["show_view_all"])

    def test_non_dict_rejected(self):
        with self.assertRaises(ProductSectionSettingsError):
            self.definition.validate_settings("not a dict")

    def test_unknown_keys_silently_dropped(self):
        cleaned = self._validate(evil_field="<script>")
        self.assertNotIn("evil_field", cleaned)


class ResponsiveSettingsContractTests(TestCase):
    """اعتبارسنجیِ خودِ ``validate_responsive_settings`` — تابعِ مشترکِ
    فازِ D، مستقل از این‌که کدام نوعِ section از آن استفاده می‌کند."""

    def test_none_input_means_fully_visible_defaults(self):
        cleaned = validate_responsive_settings(None, supports_columns=False)
        self.assertEqual(cleaned, {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False})

    def test_default_responsive_settings_matches_none_input(self):
        self.assertEqual(
            default_responsive_settings(supports_columns=False),
            validate_responsive_settings(None, supports_columns=False),
        )

    def test_non_dict_rejected(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings("not a dict", supports_columns=False)

    def test_booleans_strictly_normalized(self):
        cleaned = validate_responsive_settings(
            {"hide_on_desktop": 1, "hide_on_tablet": 0, "hide_on_mobile": "yes"}, supports_columns=False,
        )
        self.assertEqual(cleaned, {"hide_on_desktop": True, "hide_on_tablet": False, "hide_on_mobile": True})

    def test_unknown_keys_silently_dropped(self):
        cleaned = validate_responsive_settings({"hide_on_desktop": True, "evil": "<script>"}, supports_columns=False)
        self.assertNotIn("evil", cleaned)

    def test_columns_absent_when_not_supported(self):
        cleaned = validate_responsive_settings({"desktop_columns": 3}, supports_columns=False)
        self.assertNotIn("desktop_columns", cleaned)

    def test_columns_default_when_supported(self):
        cleaned = validate_responsive_settings(None, supports_columns=True)
        self.assertEqual(cleaned["desktop_columns"], 4)
        self.assertEqual(cleaned["tablet_columns"], 3)
        self.assertEqual(cleaned["mobile_columns"], 2)

    def test_columns_accept_closed_choices(self):
        cleaned = validate_responsive_settings(
            {"desktop_columns": 6, "tablet_columns": 1, "mobile_columns": 1}, supports_columns=True,
        )
        self.assertEqual(cleaned["desktop_columns"], 6)
        self.assertEqual(cleaned["tablet_columns"], 1)
        self.assertEqual(cleaned["mobile_columns"], 1)

    def test_columns_reject_out_of_range_values(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": 7}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"tablet_columns": 4}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"mobile_columns": 3}, supports_columns=True)

    def test_columns_reject_non_numeric(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": "abc"}, supports_columns=True)

    def test_columns_reject_zero_and_negative(self):
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"mobile_columns": 0}, supports_columns=True)
        with self.assertRaises(ResponsiveSettingsError):
            validate_responsive_settings({"desktop_columns": -1}, supports_columns=True)


class ResponsiveIntegrationAcrossRegistryTests(TestCase):
    """هر ۱۷ تعریفِ Section Registry باید بلوکِ responsive را پشتیبانی
    کند — نه فقط product_section."""

    def test_every_definition_default_settings_has_responsive_block(self):
        for definition in list_definitions():
            defaults = definition.default_settings()
            self.assertIn("responsive", defaults, definition.key)
            self.assertEqual(defaults["responsive"]["hide_on_desktop"], False, definition.key)

    def test_every_definition_has_settings_form(self):
        for definition in list_definitions():
            self.assertTrue(definition.has_settings_form, definition.key)

    def test_column_aware_keys_get_column_defaults(self):
        for key in COLUMN_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("desktop_columns", defaults["responsive"], key)

    def test_non_column_aware_keys_have_no_column_fields(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in COLUMN_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("desktop_columns", defaults["responsive"], key)

    def test_existing_settings_without_responsive_key_still_validate(self):
        """سکشن‌هایِ از‌قبل‌موجود که هرگز از این فرم عبور نکرده‌اند —
        شبیه‌سازیِ ذخیره‌ی مجددِ تنظیماتِ فعلی‌شان بدونِ کلیدِ
        responsive نباید کرش کند و باید پیش‌فرضِ نمایان‌همه‌جا بدهد."""
        definition = get_definition("hero_banner")
        cleaned = definition.validate_settings({})
        self.assertEqual(cleaned["responsive"]["hide_on_desktop"], False)

    def test_product_section_non_dict_still_raises_typed_error(self):
        """اطمینان از این‌که پوششِ responsive نوعِ خطایِ اختصاصیِ
        product_section را با یک ValueError عمومی جایگزین نکرده."""
        definition = get_definition("product_section")
        with self.assertRaises(ProductSectionSettingsError):
            definition.validate_settings("not a dict")


class DestinationSettingsTests(TestCase):
    """قراردادِ مشترکِ بلوکِ ``destination`` — چکپوینتِ استانداردسازیِ لینک."""

    def test_default_is_no_destination(self):
        self.assertEqual(default_destination_settings(), {
            "destination_type": "none",
            "destination_id": None,
            "destination_external_url": "",
            "open_in_new_tab": False,
        })

    def test_none_type_ignores_extra_fields(self):
        cleaned = validate_destination_settings({"destination_type": "none", "destination_id": 5})
        self.assertEqual(cleaned["destination_type"], "none")
        self.assertIsNone(cleaned["destination_id"])

    def test_category_requires_positive_id(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "category", "destination_id": None})
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "category", "destination_id": -1})

    def test_category_accepts_positive_id(self):
        cleaned = validate_destination_settings({"destination_type": "category", "destination_id": "7"})
        self.assertEqual(cleaned["destination_id"], 7)

    def test_collection_type_accepted(self):
        cleaned = validate_destination_settings({"destination_type": "collection", "destination_id": 3})
        self.assertEqual(cleaned["destination_type"], "collection")
        self.assertEqual(cleaned["destination_id"], 3)

    def test_external_requires_safe_url(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "external", "destination_external_url": "javascript:alert(1)"})
        cleaned = validate_destination_settings({"destination_type": "external", "destination_external_url": "https://example.com"})
        self.assertEqual(cleaned["destination_external_url"], "https://example.com")

    def test_unknown_type_rejected(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings({"destination_type": "not-a-real-type"})

    def test_none_raw_defaults(self):
        self.assertEqual(validate_destination_settings(None), default_destination_settings())

    def test_non_dict_rejected(self):
        with self.assertRaises(DestinationSettingsError):
            validate_destination_settings("nope")

    def test_open_in_new_tab_coerced_bool(self):
        cleaned = validate_destination_settings({"destination_type": "none", "open_in_new_tab": 1})
        self.assertIs(cleaned["open_in_new_tab"], True)


class DestinationAwareIntegrationTests(TestCase):
    def test_destination_aware_keys_get_destination_defaults(self):
        for key in DESTINATION_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("destination", defaults, key)
            self.assertEqual(defaults["destination"]["destination_type"], "none", key)

    def test_non_destination_aware_keys_have_no_destination_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in DESTINATION_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("destination", defaults, key)

    def test_existing_settings_without_destination_key_still_validate(self):
        definition = get_definition("image_text")
        cleaned = definition.validate_settings({"title": "hi"})
        self.assertEqual(cleaned["destination"]["destination_type"], "none")

    def test_product_section_destination_round_trips(self):
        definition = get_definition("product_section")
        cleaned = definition.validate_settings({
            "data_source": "newest",
            "destination": {"destination_type": "collection", "destination_id": 4},
        })
        self.assertEqual(cleaned["destination"]["destination_type"], "collection")
        self.assertEqual(cleaned["destination"]["destination_id"], 4)
