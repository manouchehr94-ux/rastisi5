from django.test import TestCase

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.section_registry import (
    ALL_PAGE_TYPES,
    COLUMN_AWARE_SECTION_KEYS,
    COLUMN_VISUAL_SECTION_KEYS,
    DESTINATION_AWARE_SECTION_KEYS,
    MOTION_AWARE_SECTION_KEYS,
    MOTION_CHOICES,
    PAGE_TYPE_CART,
    PAGE_TYPE_COLLECTION,
    PAGE_TYPE_HOME,
    PAGE_TYPE_LISTING,
    PAGE_TYPE_PRODUCT_DETAIL,
    PAGE_TYPE_SEARCH,
    SECTION_LIBRARY_CATEGORIES,
    SECTION_REGISTRY,
    DestinationSettingsError,
    MotionSettingsError,
    NewsletterSettingsError,
    ProductSectionSettingsError,
    ResponsiveSettingsError,
    UnknownSectionTypeError,
    default_destination_settings,
    default_motion_settings,
    default_responsive_settings,
    get_definition,
    is_section_allowed_on_page,
    is_valid_section_key,
    list_definitions,
    list_library_groups,
    validate_destination_settings,
    validate_motion_settings,
    validate_responsive_settings,
)

EXPECTED_KEYS = {
    "announcement_bar", "hero_banner", "image_slider", "single_banner",
    "multi_banner", "category_grid", "featured_products", "newest_products",
    "best_sellers", "discounted_products", "amazing_offers", "brand_carousel",
    "promo_cards", "rich_text", "image_text", "product_section", "trust_features",
    "collection_tiles", "quick_links", "faq", "testimonials", "video_section",
    # story_rail is a deliberate, intentional addition (Phase 5 Family
    # Implementation checkpoint) — dedicated coverage already exists in
    # test_shared_capabilities.py::StoryRailSectionTests (registered,
    # definition attributes, family-default wiring) and this file's own
    # SectionRegistryTests already exercises story_rail indirectly via
    # list_definitions()/ResponsiveIntegrationAcrossRegistryTests. This
    # fixture was simply never updated when story_rail was added.
    "story_rail",
    # newsletter — Phase 3 (Home page reusable blocks), dedicated coverage
    # in test_views.py::NewsletterSectionTests and apps.content's own
    # NewsletterSubscriber/subscribe_to_newsletter/view tests.
    "newsletter",
    # Phase 5 — context-aware product_detail-only section types, dedicated
    # coverage in test_render_service.py/test_page_shell.py.
    "product_main", "product_description", "product_video", "related_products",
    # Phase 5 — context-aware listing+search section type.
    "product_listing",
    # Phase 5 — context-aware collection-only section types.
    "collection_header", "collection_products",
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
        # hero_banner دیگر singleton نیست (چکپوینتِ اسلایدرِ اصلی) — یک
        # مرچنت باید بتواند چند نمونه‌ی مستقل از اسلایدر داشته باشد.
        for key in ("announcement_bar", "trust_features"):
            definition = get_definition(key)
            self.assertEqual(definition.max_instances, 1)
            self.assertFalse(definition.duplicable)

    def test_hero_banner_is_now_duplicable(self):
        """اسلایدر اصلی باید بتواند چند نمونه‌ی مستقل (با اسلایدهای
        متفاوت) داشته باشد — نگاه کنید به ``HeroSlide.section``."""
        definition = get_definition("hero_banner")
        self.assertTrue(definition.duplicable)
        self.assertIsNone(definition.max_instances)

    def test_announcement_bar_is_hidden_from_add_section_library(self):
        """چکپوینتِ ۹: نوارِ اعلانِ section (متنِ سخت‌کدشده، بدونِ تنظیماتِ
        واقعی) با تنظیماتِ نوارِ اعلانِ هدر (متن/فعال‌بودنِ واقعاً
        قابل‌تنظیم) هم‌پوشانی داشت — امکانِ ساختِ نمونه‌ی *جدید* از این
        نوع پنهان شده تا مرچنت به‌جایش از تنظیماتِ هدر استفاده کند؛
        نمونه‌های قدیمیِ موجود هم‌چنان کاملاً کار می‌کنند (تغییر نکرده)."""
        definition = get_definition("announcement_bar")
        self.assertTrue(definition.hidden_from_library)
        self.assertTrue(definition.removable)
        # منطقِ render/validate/default دست‌نخورده مانده — فقط از کتابخانه پنهان است
        self.assertEqual(definition.validate_settings({"foo": "bar"})["foo"], "bar")

    def test_most_sections_are_not_hidden_from_library(self):
        definitions = list_definitions()
        visible = [d for d in definitions if not d.hidden_from_library]
        self.assertGreater(len(visible), len(definitions) - 2)

    def test_every_registered_definition_has_a_valid_library_category(self):
        for definition in list_definitions():
            self.assertIn(
                definition.category_fa, SECTION_LIBRARY_CATEGORIES,
                f"{definition.key} has an unregistered category_fa: {definition.category_fa!r}",
            )

    def test_library_groups_cover_every_visible_definition_exactly_once(self):
        groups = list_library_groups()
        category_names = [name for name, _members in groups]
        self.assertEqual(category_names, sorted(category_names, key=SECTION_LIBRARY_CATEGORIES.index))

        seen_keys = []
        for _category, members in groups:
            seen_keys.extend(d.key for d in members)
        visible_keys = {d.key for d in list_definitions() if not d.hidden_from_library}
        self.assertEqual(set(seen_keys), visible_keys)
        self.assertEqual(len(seen_keys), len(set(seen_keys)))  # هیچ کلیدی دوبار ظاهر نمی‌شود

    def test_library_groups_never_include_hidden_types(self):
        groups = list_library_groups()
        all_keys = {d.key for _category, members in groups for d in members}
        self.assertNotIn("announcement_bar", all_keys)

    def test_library_groups_never_render_an_empty_category(self):
        for _category, members in list_library_groups():
            self.assertGreater(len(members), 0)

    def test_validate_settings_rejects_non_dict(self):
        definition = get_definition("announcement_bar")
        with self.assertRaises(ValueError):
            definition.validate_settings("not a dict")

    def test_validate_settings_accepts_dict(self):
        """از فازِ D به بعد، خروجیِ هر validate_settings همیشه یک بلوکِ
        ``responsive`` پیش‌فرض (نمایان همه‌جا) هم دارد — بدونِ تغییرِ
        رفتارِ خودِ منطقِ passthrough."""
        definition = get_definition("announcement_bar")
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


class CategoryGridSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("category_grid")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["category_ids"], [])
        self.assertEqual(cleaned["display_mode"], "grid")
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_category_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"category_ids": [5, 3, 5, 3, 8]})
        self.assertEqual(cleaned["category_ids"], [5, 3, 8])

    def test_non_positive_ids_dropped(self):
        cleaned = self.definition.validate_settings({"category_ids": [0, -1, 4]})
        self.assertEqual(cleaned["category_ids"], [4])

    def test_invalid_display_mode_falls_back_to_grid(self):
        cleaned = self.definition.validate_settings({"display_mode": "not-a-real-mode"})
        self.assertEqual(cleaned["display_mode"], "grid")

    def test_carousel_display_mode_accepted(self):
        cleaned = self.definition.validate_settings({"display_mode": "carousel"})
        self.assertEqual(cleaned["display_mode"], "carousel")

    def test_title_trimmed_and_capped(self):
        cleaned = self.definition.validate_settings({"title": "  " + ("ط" * 100) + "  "})
        self.assertEqual(len(cleaned["title"]), 60)
        self.assertFalse(cleaned["title"].startswith(" "))

    def test_category_grid_is_per_instance_duplicable(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class BrandCarouselSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("brand_carousel")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["brand_ids"], [])
        self.assertEqual(cleaned["display_mode"], "grid")
        self.assertFalse(cleaned["show_view_all"])
        # عضوِ DESTINATION_AWARE_SECTION_KEYS است — بلوکِ destination هم باید حاضر باشد
        self.assertEqual(cleaned["destination"]["destination_type"], "none")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_brand_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"brand_ids": [7, 2, 7]})
        self.assertEqual(cleaned["brand_ids"], [7, 2])

    def test_show_view_all_accepts_true(self):
        cleaned = self.definition.validate_settings({"show_view_all": True})
        self.assertTrue(cleaned["show_view_all"])

    def test_brand_carousel_is_per_instance_duplicable(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class CollectionTilesSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("collection_tiles")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["collection_ids"], [])
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_collection_ids_deduplicated_preserving_order(self):
        cleaned = self.definition.validate_settings({"collection_ids": [9, 1, 9]})
        self.assertEqual(cleaned["collection_ids"], [9, 1])

    def test_duplicable_and_unbounded(self):
        self.assertTrue(self.definition.duplicable)
        self.assertIsNone(self.definition.max_instances)


class QuickLinksSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("quick_links")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertIsNone(cleaned["menu_id"])
        self.assertEqual(cleaned["title"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_menu_id_accepted(self):
        cleaned = self.definition.validate_settings({"menu_id": 7})
        self.assertEqual(cleaned["menu_id"], 7)

    def test_non_positive_menu_id_becomes_none(self):
        cleaned = self.definition.validate_settings({"menu_id": -3})
        self.assertIsNone(cleaned["menu_id"])

    def test_invalid_menu_id_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"menu_id": "not-a-number"})


class FaqSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("faq")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["items"], [])
        self.assertEqual(cleaned["title"], "سوالات متداول")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_items_with_both_fields_kept(self):
        cleaned = self.definition.validate_settings({"items": [{"question": "س", "answer": "پ"}]})
        self.assertEqual(cleaned["items"], [{"question": "س", "answer": "پ"}])

    def test_items_missing_a_field_dropped(self):
        cleaned = self.definition.validate_settings({"items": [{"question": "س", "answer": ""}]})
        self.assertEqual(cleaned["items"], [])

    def test_non_list_items_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"items": "not a list"})

    def test_items_capped_at_twenty(self):
        raw_items = [{"question": f"س{i}", "answer": f"پ{i}"} for i in range(30)]
        cleaned = self.definition.validate_settings({"items": raw_items})
        self.assertEqual(len(cleaned["items"]), 20)


class TestimonialsSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("testimonials")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["items"], [])
        self.assertEqual(cleaned["title"], "نظرات مشتریان")

    def test_items_requires_name_and_quote_role_optional(self):
        cleaned = self.definition.validate_settings({"items": [{"name": "علی", "quote": "عالی بود", "role": ""}]})
        self.assertEqual(cleaned["items"], [{"name": "علی", "quote": "عالی بود", "role": ""}])

    def test_items_missing_quote_dropped(self):
        cleaned = self.definition.validate_settings({"items": [{"name": "علی", "quote": ""}]})
        self.assertEqual(cleaned["items"], [])


class VideoSectionSettingsTests(TestCase):
    def setUp(self):
        self.definition = get_definition("video_section")

    def test_defaults_when_empty(self):
        cleaned = self.definition.validate_settings({})
        self.assertEqual(cleaned["video_url"], "")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings("not a dict")

    def test_valid_youtube_url_accepted(self):
        cleaned = self.definition.validate_settings({"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        self.assertIn("youtube.com", cleaned["video_url"])

    def test_unrecognized_url_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"video_url": "https://example.com/not-a-video"})

    def test_dangerous_scheme_rejected(self):
        with self.assertRaises(ValueError):
            self.definition.validate_settings({"video_url": "javascript:alert(1)//youtube.com/watch?v=dQw4w9WgXcQ"})

    def test_empty_url_allowed_not_configured_yet(self):
        cleaned = self.definition.validate_settings({"video_url": ""})
        self.assertEqual(cleaned["video_url"], "")


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

    def test_search_type_accepted_and_needs_no_id(self):
        cleaned = validate_destination_settings({"destination_type": "search"})
        self.assertEqual(cleaned["destination_type"], "search")
        self.assertIsNone(cleaned["destination_id"])

    def test_cart_type_accepted_and_needs_no_id(self):
        cleaned = validate_destination_settings({"destination_type": "cart"})
        self.assertEqual(cleaned["destination_type"], "cart")
        self.assertIsNone(cleaned["destination_id"])

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


class MotionSettingsTests(TestCase):
    """Phase 3 (کتابخانه‌ی بلوک‌های صفحه اصلی) — بلوکِ مشترکِ «حرکت»."""

    def test_default_is_none(self):
        self.assertEqual(default_motion_settings(), {"style": "none"})

    def test_none_raw_defaults(self):
        self.assertEqual(validate_motion_settings(None), default_motion_settings())

    def test_valid_styles_accepted(self):
        for style in MOTION_CHOICES:
            self.assertEqual(validate_motion_settings({"style": style}), {"style": style})

    def test_unknown_style_falls_back_to_none(self):
        """برخلافِ destination (که خطا می‌دهد)، سبکِ نامعتبر بی‌صدا به
        none بازمی‌گردد — یک جلوه‌ی صرفاً بصری هرگز نباید کلِ فرمِ
        ذخیره‌سازی را رد کند."""
        self.assertEqual(validate_motion_settings({"style": "not-a-real-style"}), {"style": "none"})

    def test_non_dict_rejected(self):
        with self.assertRaises(MotionSettingsError):
            validate_motion_settings("nope")


class MotionAwareIntegrationTests(TestCase):
    def test_motion_aware_keys_get_motion_defaults(self):
        for key in MOTION_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("motion", defaults, key)
            self.assertEqual(defaults["motion"]["style"], "none", key)

    def test_non_motion_aware_keys_have_no_motion_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in MOTION_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("motion", defaults, key)

    def test_existing_settings_without_motion_key_still_validate(self):
        definition = get_definition("category_grid")
        cleaned = definition.validate_settings({"title": "hi"})
        self.assertEqual(cleaned["motion"]["style"], "none")

    def test_motion_round_trips(self):
        definition = get_definition("hero_banner")
        cleaned = definition.validate_settings({"motion": {"style": "fade"}})
        self.assertEqual(cleaned["motion"]["style"], "fade")


class MultiBannerColumnLayoutTests(TestCase):
    """Phase 3 — ``multi_banner`` از ``COLUMN_AWARE`` به ``COLUMN_VISUAL``
    منتقل شد (چیدمانِ گریدِ واقعی، نگاه کنید به multi_banner.html)."""

    def test_multi_banner_is_column_aware_and_visual(self):
        self.assertIn("multi_banner", COLUMN_AWARE_SECTION_KEYS)
        self.assertIn("multi_banner", COLUMN_VISUAL_SECTION_KEYS)

    def test_other_previously_static_types_remain_non_visual(self):
        for key in ("category_grid", "promo_cards", "brand_carousel"):
            self.assertIn(key, COLUMN_AWARE_SECTION_KEYS)
            self.assertNotIn(key, COLUMN_VISUAL_SECTION_KEYS)


class NewsletterSectionRegistryTests(TestCase):
    """Phase 3 — بلوکِ «خبرنامه» در Section Registry."""

    def test_registered_single_instance_only(self):
        definition = get_definition("newsletter")
        self.assertEqual(definition.max_instances, 1)
        self.assertFalse(definition.duplicable)

    def test_default_settings(self):
        defaults = get_definition("newsletter").default_settings()
        self.assertEqual(defaults["title"], "عضویت در خبرنامه")
        self.assertEqual(defaults["button_label"], "عضویت")

    def test_blank_title_and_button_label_falls_back(self):
        cleaned = get_definition("newsletter").validate_settings({"title": "", "button_label": ""})
        self.assertEqual(cleaned["button_label"], "عضویت")
        self.assertEqual(cleaned["title"], "")

    def test_custom_values_round_trip(self):
        cleaned = get_definition("newsletter").validate_settings({
            "title": "عنوانِ من", "subtitle": "زیرعنوانِ من", "button_label": "برو",
        })
        self.assertEqual(cleaned["title"], "عنوانِ من")
        self.assertEqual(cleaned["subtitle"], "زیرعنوانِ من")
        self.assertEqual(cleaned["button_label"], "برو")

    def test_non_dict_rejected(self):
        with self.assertRaises(NewsletterSettingsError):
            get_definition("newsletter").validate_settings("nope")


class PageTypeConstantsMatchModelTests(TestCase):
    """Phase 5: چون ``section_registry.py`` عمداً به ``models.py`` وابسته
    نیست (فلسفه‌ی «دیکشنری ثابت پایتونی» بالا)، ثابت‌های ``PAGE_TYPE_*``
    اینجا مستقل تکرار شده‌اند — این تست تضمین می‌کند اگر روزی
    ``StorefrontPage.PageType`` تغییر کند، این فایل خاموش از هماهنگی
    نمی‌افتد."""

    def test_all_page_types_matches_model_enum_exactly(self):
        self.assertEqual(ALL_PAGE_TYPES, frozenset(StorefrontPage.PageType.values))

    def test_individual_constants_match_model_values(self):
        self.assertEqual(
            {PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING, PAGE_TYPE_COLLECTION, PAGE_TYPE_SEARCH, PAGE_TYPE_CART},
            set(StorefrontPage.PageType.values),
        )


class PageTypeAllowlistTests(TestCase):
    #: انواعِ context-aware (Phase 5) عمداً از تستِ «همه‌جا مجاز» مستثنی‌اند —
    #: page_types محدودشان اینجا، در ``test_context_aware_types_restricted_to_their_own_page``
    #: به‌ازایِ هرکدام جداگانه اثبات می‌شود.
    _CONTEXT_AWARE_PAGE_TYPES = {
        "product_main": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_description": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_video": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "related_products": frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
        "product_listing": frozenset({PAGE_TYPE_LISTING, PAGE_TYPE_SEARCH}),
        "collection_header": frozenset({PAGE_TYPE_COLLECTION}),
        "collection_products": frozenset({PAGE_TYPE_COLLECTION}),
    }

    def test_existing_section_types_default_to_all_pages(self):
        """۱۷ نوعِ محتواییِ عمومیِ موجود از پیش نباید با این چکپوینت رفتار
        تغییر کنند — پیش‌فرض یعنی «همه‌جا مجاز»."""
        for key in EXPECTED_KEYS - set(self._CONTEXT_AWARE_PAGE_TYPES):
            definition = get_definition(key)
            self.assertEqual(definition.page_types, ALL_PAGE_TYPES, key)
            for page_type in StorefrontPage.PageType.values:
                self.assertTrue(is_section_allowed_on_page(key, page_type), f"{key} on {page_type}")

    def test_context_aware_types_restricted_to_their_own_page(self):
        for key, expected_pages in self._CONTEXT_AWARE_PAGE_TYPES.items():
            definition = get_definition(key)
            self.assertEqual(definition.page_types, expected_pages, key)
            for page_type in StorefrontPage.PageType.values:
                allowed = is_section_allowed_on_page(key, page_type)
                self.assertEqual(allowed, page_type in expected_pages, f"{key} on {page_type}")

    def test_unknown_section_key_never_allowed_on_any_page(self):
        for page_type in StorefrontPage.PageType.values:
            self.assertFalse(is_section_allowed_on_page("does_not_exist", page_type))

    def test_list_library_groups_unfiltered_includes_page_restricted_types_too(self):
        """بدونِ ``page_type``، فیلتری اعمال نمی‌شود — کتابخانه‌ی نامحدود
        شاملِ حتی انواعِ محدودشده (مثلِ product_main) هم می‌شود."""
        unfiltered_keys = {d.key for _c, members in list_library_groups() for d in members}
        self.assertIn("product_main", unfiltered_keys)

    def test_list_library_groups_can_be_scoped_to_a_page_type(self):
        cart_keys = {d.key for _c, members in list_library_groups(page_type=PAGE_TYPE_CART) for d in members}
        product_detail_keys = {
            d.key for _c, members in list_library_groups(page_type=PAGE_TYPE_PRODUCT_DETAIL) for d in members
        }
        context_aware = {"product_main", "product_description", "product_video", "related_products"}
        # کتابخانه‌ی product_detail دقیقاً همان ۴ نوعِ context-aware را
        # نسبت به کتابخانه‌ی cart بیشتر دارد — بقیه (همه‌ی انواعِ عمومی)
        # روی هر دو صفحه یکسان‌اند.
        self.assertEqual(product_detail_keys - cart_keys, context_aware)
        self.assertTrue(context_aware <= product_detail_keys)
        self.assertFalse(context_aware & cart_keys)
