from django.test import TestCase

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.section_registry import (
    ALL_PAGE_TYPES,
    BACKGROUND_AWARE_SECTION_KEYS,
    BACKGROUND_MODE_CHOICES,
    CARD_AWARE_SECTION_KEYS,
    COLUMN_AWARE_SECTION_KEYS,
    COLUMN_VISUAL_SECTION_KEYS,
    CONTENT_WIDTH_CHOICES,
    DESTINATION_AWARE_SECTION_KEYS,
    HEIGHT_CHOICES,
    IMAGE_RATIO_CHOICES,
    QUICK_ADD_REVEAL_CHOICES,
    LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
    LAYOUT_WIDTH_AWARE_SECTION_KEYS,
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
    SPACING_AWARE_SECTION_KEYS,
    SPACING_SIZE_CHOICES,
    BackgroundSettingsError,
    CardSettingsError,
    DestinationSettingsError,
    LayoutSettingsError,
    MotionSettingsError,
    NewsletterSettingsError,
    ProductSectionSettingsError,
    ResponsiveSettingsError,
    SpacingSettingsError,
    UnknownSectionTypeError,
    default_background_settings,
    default_card_settings,
    default_destination_settings,
    default_layout_settings,
    default_motion_settings,
    default_responsive_settings,
    default_spacing_settings,
    get_definition,
    is_section_allowed_on_page,
    is_valid_section_key,
    list_definitions,
    list_library_groups,
    validate_background_settings,
    validate_card_settings,
    validate_destination_settings,
    validate_layout_settings,
    validate_motion_settings,
    validate_responsive_settings,
    validate_spacing_settings,
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
    # Phase 5 — context-aware cart-only section types.
    "cart_items", "cart_summary",
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


class CardSettingsTests(TestCase):
    """Phase 8 P0-2 — بلوکِ مشترکِ «ظاهرِ کارتِ محصول»."""

    def test_default_shows_everything_square(self):
        defaults = default_card_settings()
        self.assertEqual(defaults, {
            "show_brand": True, "show_price": True, "show_badge": True,
            "show_wishlist": True, "show_quick_add": True, "card_border": True,
            "image_ratio": "square", "quick_add_reveal": "hover_slide",
        })

    def test_none_raw_defaults(self):
        self.assertEqual(validate_card_settings(None), default_card_settings())

    def test_explicit_false_toggles_are_respected(self):
        cleaned = validate_card_settings({
            "show_brand": False, "show_price": False, "show_badge": False,
            "show_wishlist": False, "show_quick_add": False, "card_border": False,
        })
        for key in ("show_brand", "show_price", "show_badge", "show_wishlist", "show_quick_add", "card_border"):
            self.assertFalse(cleaned[key], key)

    def test_valid_image_ratios_accepted(self):
        for ratio in IMAGE_RATIO_CHOICES:
            self.assertEqual(validate_card_settings({"image_ratio": ratio})["image_ratio"], ratio)

    def test_unknown_image_ratio_falls_back_to_square(self):
        self.assertEqual(validate_card_settings({"image_ratio": "circle"})["image_ratio"], "square")

    def test_valid_quick_add_reveal_modes_accepted(self):
        for mode in QUICK_ADD_REVEAL_CHOICES:
            self.assertEqual(validate_card_settings({"quick_add_reveal": mode})["quick_add_reveal"], mode)

    def test_unknown_quick_add_reveal_falls_back_to_hover_slide(self):
        self.assertEqual(validate_card_settings({"quick_add_reveal": "bounce"})["quick_add_reveal"], "hover_slide")

    def test_non_dict_rejected(self):
        with self.assertRaises(CardSettingsError):
            validate_card_settings("nope")


class CardAwareIntegrationTests(TestCase):
    def test_card_aware_keys_get_card_defaults(self):
        for key in CARD_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("card", defaults, key)
            self.assertEqual(defaults["card"], default_card_settings(), key)

    def test_non_card_aware_keys_have_no_card_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in CARD_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("card", defaults, key)

    def test_card_round_trips(self):
        definition = get_definition("product_section")
        cleaned = definition.validate_settings({
            "data_source": "newest", "card": {"show_brand": False, "image_ratio": "portrait"},
        })
        self.assertFalse(cleaned["card"]["show_brand"])
        self.assertEqual(cleaned["card"]["image_ratio"], "portrait")

    def test_unknown_card_awareness_types_are_the_expected_nine(self):
        """طبقِ برنامه‌ی پیاده‌سازیِ فاز ۸ — همان ۸ نوعی که واقعاً کارتِ
        محصول رندر می‌کنند (به‌علاوه‌ی amazing_offers)."""
        self.assertEqual(CARD_AWARE_SECTION_KEYS, frozenset({
            "product_section", "featured_products", "newest_products", "best_sellers",
            "discounted_products", "amazing_offers", "related_products", "product_listing",
            "collection_products",
        }))


class Phase8ColumnExpansionTests(TestCase):
    """Phase 8 P0-2 — کنترلِ «تعدادِ ستون‌ها» از ۲ نوع به ۸ نوعِ محصولی
    گسترش یافت؛ سه نوعِ غیرِمحصولیِ قبلی (category_grid/promo_cards/
    brand_carousel) عمداً دست‌نخورده باقی می‌مانند (نگاه کنید به
    MultiBannerColumnLayoutTests بالا)."""

    def test_all_eight_product_listing_types_are_column_visual(self):
        expected = {
            "product_section", "multi_banner", "featured_products", "newest_products",
            "best_sellers", "discounted_products", "related_products", "collection_products",
            "product_listing",
        }
        self.assertEqual(expected, COLUMN_VISUAL_SECTION_KEYS)
        for key in expected:
            self.assertIn(key, COLUMN_AWARE_SECTION_KEYS, key)


class LayoutSettingsTests(TestCase):
    """Phase 8 P0-5 — بلوکِ مشترکِ «اندازه‌ی بخش» (عرض/ارتفاع)."""

    def test_default_is_standard(self):
        self.assertEqual(
            default_layout_settings(supports_height=True),
            {"content_width": "standard", "height": "standard"},
        )
        self.assertEqual(
            default_layout_settings(supports_height=False),
            {"content_width": "standard"},
        )

    def test_none_raw_defaults(self):
        self.assertEqual(validate_layout_settings(None, supports_height=True), default_layout_settings(supports_height=True))

    def test_valid_widths_accepted(self):
        for width in CONTENT_WIDTH_CHOICES:
            self.assertEqual(
                validate_layout_settings({"content_width": width}, supports_height=False)["content_width"], width,
            )

    def test_valid_heights_accepted(self):
        for height in HEIGHT_CHOICES:
            self.assertEqual(
                validate_layout_settings({"height": height}, supports_height=True)["height"], height,
            )

    def test_unknown_width_falls_back_to_standard(self):
        self.assertEqual(
            validate_layout_settings({"content_width": "huge"}, supports_height=False)["content_width"], "standard",
        )

    def test_height_absent_when_not_supported(self):
        cleaned = validate_layout_settings({"height": "tall"}, supports_height=False)
        self.assertNotIn("height", cleaned)

    def test_non_dict_rejected(self):
        with self.assertRaises(LayoutSettingsError):
            validate_layout_settings("nope", supports_height=True)


class LayoutAwareIntegrationTests(TestCase):
    def test_width_aware_keys_get_layout_defaults(self):
        for key in LAYOUT_WIDTH_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("layout", defaults, key)
            self.assertEqual(defaults["layout"]["content_width"], "standard", key)
            self.assertEqual("height" in defaults["layout"], key in LAYOUT_HEIGHT_AWARE_SECTION_KEYS, key)

    def test_non_width_aware_keys_have_no_layout_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in LAYOUT_WIDTH_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("layout", defaults, key)

    def test_height_only_aware_for_hero_and_slider(self):
        self.assertEqual(LAYOUT_HEIGHT_AWARE_SECTION_KEYS, frozenset({"hero_banner", "image_slider"}))
        self.assertTrue(LAYOUT_HEIGHT_AWARE_SECTION_KEYS.issubset(LAYOUT_WIDTH_AWARE_SECTION_KEYS))

    def test_layout_round_trips(self):
        definition = get_definition("image_text")
        cleaned = definition.validate_settings({"layout": {"content_width": "full"}})
        self.assertEqual(cleaned["layout"]["content_width"], "full")
        self.assertNotIn("height", cleaned["layout"])


class BackgroundSettingsTests(TestCase):
    """spec §9 (Background System) + §10.2 (Custom Color Overrides)."""

    def test_missing_key_defaults_to_theme(self):
        cleaned = validate_background_settings(None)
        self.assertEqual(cleaned, default_background_settings())
        self.assertEqual(cleaned["mode"], "theme")

    def test_valid_color_mode(self):
        cleaned = validate_background_settings({"mode": "color", "color": "#E62B35"})
        self.assertEqual(cleaned["mode"], "color")
        self.assertEqual(cleaned["color"], "#E62B35")

    def test_invalid_hex_color_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "color", "color": "not-a-color"})

    def test_color_mode_without_color_falls_back_to_theme(self):
        cleaned = validate_background_settings({"mode": "color", "color": ""})
        self.assertEqual(cleaned["mode"], "theme")

    def test_valid_image_mode_stores_media_asset_id_not_a_url(self):
        """Phase 1 correction (tenant safety): تنظیماتِ خامِ mode=image فقط
        یک شناسه‌ی عددیِ اشاره‌گر به MediaAsset را می‌پذیرد، هرگز یک رشته‌ی
        URL دلخواه را — حلِ مالکیتِ Store در
        ``apps.content.services.resolve_background_media_url`` است، نه اینجا."""
        cleaned = validate_background_settings({"mode": "image", "media_asset_id": 42})
        self.assertEqual(cleaned["mode"], "image")
        self.assertEqual(cleaned["media_asset_id"], 42)
        self.assertNotIn("image_url", cleaned)

    def test_image_mode_without_media_asset_id_falls_back_to_theme(self):
        cleaned = validate_background_settings({"mode": "image"})
        self.assertEqual(cleaned["mode"], "theme")
        self.assertIsNone(cleaned["media_asset_id"])

    def test_non_integer_media_asset_id_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": "not-a-number"})

    def test_non_positive_media_asset_id_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": 0})

    def test_arbitrary_url_in_media_asset_id_field_rejected(self):
        """طبقِ تصمیمِ ایمنیِ مستأجر: حتی اگر مرچنت/کلاینتِ مخرب سعی کند یک
        رشته‌ی URL را در همان کلید پاس بدهد، به‌عنوانِ شناسه‌ی نامعتبر رد
        می‌شود — نه اینکه بی‌صدا به‌عنوانِ URL پذیرفته شود."""
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings({"mode": "image", "media_asset_id": "https://evil.example.com/x.jpg"})

    def test_pattern_mode_with_empty_registry_falls_back_to_theme(self):
        """PATTERN_REGISTRY عمداً در Phase 1 خالی است (هنوز هیچ دارایی‌ای
        ساخته نشده) — یک pattern_slug همیشه به‌شکلِ امن رد می‌شود، نه خطا."""
        cleaned = validate_background_settings({"mode": "pattern", "pattern_slug": "stationery"})
        self.assertEqual(cleaned["mode"], "theme")
        self.assertEqual(cleaned["pattern_slug"], "")

    def test_unknown_mode_falls_back_to_theme(self):
        cleaned = validate_background_settings({"mode": "not-a-real-mode"})
        self.assertEqual(cleaned["mode"], "theme")

    def test_non_dict_rejected(self):
        with self.assertRaises(BackgroundSettingsError):
            validate_background_settings("nope")


class BackgroundAwareIntegrationTests(TestCase):
    def test_background_aware_keys_get_background_defaults(self):
        for key in BACKGROUND_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("background", defaults, key)
            self.assertEqual(defaults["background"]["mode"], "theme", key)

    def test_non_background_aware_keys_have_no_background_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in BACKGROUND_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("background", defaults, key)

    def test_protected_context_sections_excluded(self):
        """spec §59 — sectionهایِ حیاتیِ محافظت‌شده (خرید/سبد/لیست) عمداً
        از override پس‌زمینه کنار گذاشته شده‌اند."""
        protected = {"product_main", "product_listing", "cart_items", "cart_summary", "collection_products"}
        self.assertTrue(protected.isdisjoint(BACKGROUND_AWARE_SECTION_KEYS))

    def test_background_round_trips(self):
        definition = get_definition("multi_banner")
        cleaned = definition.validate_settings({"background": {"mode": "color", "color": "#112233"}})
        self.assertEqual(cleaned["background"]["mode"], "color")
        self.assertEqual(cleaned["background"]["color"], "#112233")


class SpacingSettingsTests(TestCase):
    """spec §8 (Basic: Small/Normal/Large — Advanced: exact padding/margin)."""

    def test_missing_key_defaults_to_normal_no_advanced_override(self):
        cleaned = validate_spacing_settings(None)
        self.assertEqual(cleaned, default_spacing_settings())
        self.assertEqual(cleaned["vertical_spacing"], "normal")
        self.assertTrue(all(v is None for v in cleaned["advanced"].values()))

    def test_valid_basic_size(self):
        cleaned = validate_spacing_settings({"vertical_spacing": "large"})
        self.assertEqual(cleaned["vertical_spacing"], "large")

    def test_unknown_size_falls_back_to_normal(self):
        cleaned = validate_spacing_settings({"vertical_spacing": "huge"})
        self.assertEqual(cleaned["vertical_spacing"], "normal")

    def test_advanced_override_clamped_to_range(self):
        cleaned = validate_spacing_settings({"advanced": {"padding_top": 9999, "margin_top": -50}})
        self.assertEqual(cleaned["advanced"]["padding_top"], 200)
        self.assertEqual(cleaned["advanced"]["margin_top"], 0)

    def test_advanced_field_left_none_when_not_supplied(self):
        cleaned = validate_spacing_settings({"advanced": {"padding_top": 40}})
        self.assertEqual(cleaned["advanced"]["padding_top"], 40)
        self.assertIsNone(cleaned["advanced"]["padding_bottom"])

    def test_non_numeric_advanced_value_rejected(self):
        with self.assertRaises(SpacingSettingsError):
            validate_spacing_settings({"advanced": {"padding_top": "lots"}})

    def test_non_dict_rejected(self):
        with self.assertRaises(SpacingSettingsError):
            validate_spacing_settings("nope")


class SpacingAwareIntegrationTests(TestCase):
    def test_spacing_aware_keys_get_spacing_defaults(self):
        for key in SPACING_AWARE_SECTION_KEYS:
            defaults = get_definition(key).default_settings()
            self.assertIn("spacing", defaults, key)
            self.assertEqual(defaults["spacing"]["vertical_spacing"], "normal", key)

    def test_non_spacing_aware_keys_have_no_spacing_field(self):
        for key, definition in SECTION_REGISTRY.items():
            if key in SPACING_AWARE_SECTION_KEYS:
                continue
            defaults = definition.default_settings()
            self.assertNotIn("spacing", defaults, key)

    def test_background_and_spacing_share_exactly_the_same_allowlist(self):
        self.assertEqual(BACKGROUND_AWARE_SECTION_KEYS, SPACING_AWARE_SECTION_KEYS)


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
        "cart_items": frozenset({PAGE_TYPE_CART}),
        "cart_summary": frozenset({PAGE_TYPE_CART}),
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
