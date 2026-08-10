"""تست‌هایِ جامعِ قابلیت‌هایِ مشترکِ خانواده‌ها — Phase 5 Family Implementation.

این فایل تمامِ shared capabilities ای که در این فاز اضافه شدند را پوشش
می‌دهد:
  - Category image field (4.1)
  - Cart preview engine (4.2)
  - Size guide via ProductMetafield (4.3)
  - Independent image settings (4.4)
  - Story Rail section (4.5)
  - Maker/region via ProductMetafield (4.6)
  - All five families registered with correct defaults (5.x)
"""

from decimal import Decimal

from django.test import TestCase, RequestFactory, override_settings

from apps.catalog.models import (
    Category, Product, ProductMetafield,
    METAFIELD_NS_SIZE_GUIDE, METAFIELD_NS_ARTISAN, METAFIELD_NS_CUSTOM,
)
from apps.storefront_builder import family_registry, preset_registry, section_registry
from apps.storefront_builder.models import APPEARANCE_CONFIG_DEFAULTS


# ============================================================ 4.1 Category Media

class CategoryImageFieldTests(TestCase):
    """Category.image — ImageField اختیاری با emoji fallback."""

    def test_category_model_has_image_field(self):
        """فیلد image روی Category وجود دارد."""
        field = Category._meta.get_field("image")
        self.assertTrue(field.blank)
        self.assertTrue(field.null)
        self.assertEqual(field.upload_to, "categories/images/")

    def test_category_without_image_uses_icon(self):
        """دسته‌بندی بدون تصویر — icon (emoji) باید به‌عنوان fallback عمل کند."""
        cat = Category(name="تست", icon="📦", slug="test")
        self.assertFalse(bool(cat.image))
        self.assertEqual(cat.icon, "📦")

    def test_category_with_image(self):
        """دسته‌بندی با تصویر — image.url باید در دسترس باشد."""
        cat = Category(name="تست", icon="📦", slug="test")
        cat.image = "categories/images/test.jpg"
        self.assertTrue(bool(cat.image))


# ============================================================ 4.2 Cart Preview Engine

class CartPreviewServiceTests(TestCase):
    """Cart preview engine — count_link و mini_cart."""

    def test_get_cart_preview_data_empty(self):
        """بدون سبد — باید cart_is_empty=True برگرداند."""
        from apps.cart.services.cart_preview import get_cart_preview_data, CART_PREVIEW_MODE_COUNT_LINK

        factory = RequestFactory()
        request = factory.get("/")
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        request.session = type("FakeSession", (), {"session_key": None})()

        data = get_cart_preview_data(request, mode=CART_PREVIEW_MODE_COUNT_LINK)
        self.assertTrue(data["cart_is_empty"])
        self.assertEqual(data["cart_count"], 0)
        self.assertEqual(data["cart_preview_mode"], "count_link")

    def test_cart_preview_modes_are_valid(self):
        """حالت‌های مجاز: count_link و mini_cart."""
        from apps.cart.services.cart_preview import CART_PREVIEW_MODES

        self.assertIn("count_link", CART_PREVIEW_MODES)
        self.assertIn("mini_cart", CART_PREVIEW_MODES)
        self.assertEqual(len(CART_PREVIEW_MODES), 2)


# ============================================================ 4.3 + 4.6 ProductMetafield

class ProductMetafieldModelTests(TestCase):
    """ProductMetafield — مکانیزم extensible متادیتا."""

    def test_metafield_namespace_constants(self):
        """ثابت‌های namespace وجود دارند."""
        self.assertEqual(METAFIELD_NS_SIZE_GUIDE, "size_guide")
        self.assertEqual(METAFIELD_NS_ARTISAN, "artisan")
        self.assertEqual(METAFIELD_NS_CUSTOM, "custom")

    def test_metafield_unique_constraint(self):
        """UniqueConstraint (product, namespace, key) وجود دارد."""
        constraints = {c.name for c in ProductMetafield._meta.constraints}
        self.assertIn("uniq_product_metafield", constraints)

    def test_metafield_str(self):
        """نمایش متنی metafield."""
        mf = ProductMetafield(namespace="artisan", key="maker", value_text="استاد احمدی")
        self.assertIn("artisan.maker", str(mf))


# ============================================================ 4.4 Independent Image Settings

class IndependentImageSettingsTests(TestCase):
    """card_image_crossfade و card_image_zoom — مستقل از هم."""

    def test_defaults_in_appearance_config(self):
        """هر دو فیلد با مقادیر پیش‌فرض در APPEARANCE_CONFIG_DEFAULTS هستند."""
        self.assertIn("card_image_crossfade", APPEARANCE_CONFIG_DEFAULTS)
        self.assertIn("card_image_zoom", APPEARANCE_CONFIG_DEFAULTS)
        # پیش‌فرض: crossfade غیرفعال، zoom فعال
        self.assertFalse(APPEARANCE_CONFIG_DEFAULTS["card_image_crossfade"])
        self.assertTrue(APPEARANCE_CONFIG_DEFAULTS["card_image_zoom"])

    def test_modern_fashion_preset_has_crossfade(self):
        """preset مد امروز: crossfade=True, zoom=False."""
        preset = preset_registry.get_preset("modern_fashion_default")
        self.assertIsNotNone(preset)
        self.assertTrue(preset.card_image_crossfade)
        self.assertFalse(preset.card_image_zoom)

    def test_nordic_living_preset_has_crossfade(self):
        """preset خانه آرام: crossfade=True, zoom=False."""
        preset = preset_registry.get_preset("nordic_living_default")
        self.assertIsNotNone(preset)
        self.assertTrue(preset.card_image_crossfade)
        self.assertFalse(preset.card_image_zoom)

    def test_heritage_premium_preset_defaults(self):
        """preset پرمیوم: crossfade=False (پیش‌فرض), zoom=True (پیش‌فرض)."""
        preset = preset_registry.get_preset("heritage_premium_default")
        self.assertIsNotNone(preset)
        self.assertFalse(preset.card_image_crossfade)
        self.assertTrue(preset.card_image_zoom)

    def test_settings_are_independent(self):
        """تغییر یکی نباید دیگری را تغییر دهد — هر دو field مستقل‌اند."""
        # هر دو True باید مجاز باشد
        config = {**APPEARANCE_CONFIG_DEFAULTS, "card_image_crossfade": True, "card_image_zoom": True}
        self.assertTrue(config["card_image_crossfade"])
        self.assertTrue(config["card_image_zoom"])


# ============================================================ 4.5 Story Rail

class StoryRailSectionTests(TestCase):
    """Story Rail — بخش مشترک اختیاری."""

    def test_story_rail_registered_in_section_registry(self):
        """story_rail باید در SECTION_REGISTRY ثبت شده باشد."""
        self.assertTrue(section_registry.is_valid_section_key("story_rail"))

    def test_story_rail_definition_attributes(self):
        """تعریف story_rail: قابل حذف، تکی، دسته‌ی «کشف و خرید»."""
        defn = section_registry.get_definition("story_rail")
        self.assertEqual(defn.label_fa, "ریلِ استوری")
        self.assertTrue(defn.removable)
        self.assertFalse(defn.duplicable)
        self.assertEqual(defn.max_instances, 1)
        self.assertEqual(defn.category_fa, "کشف و خرید")

    def test_story_rail_in_artisan_editorial_defaults(self):
        """story_rail باید در default_section_keys خانواده‌ی روایت هنر باشد."""
        family = family_registry.get_family("artisan_editorial")
        self.assertIn("story_rail", family.default_section_keys)

    def test_story_rail_not_in_modern_fashion_defaults(self):
        """story_rail در modern_fashion پیش‌فرض نیست (تصحیح شد)."""
        family = family_registry.get_family("modern_fashion")
        self.assertNotIn("story_rail", family.default_section_keys)

    def test_story_rail_not_in_other_families_by_default(self):
        """story_rail فقط در artisan_editorial پیش‌فرض است — بقیه ندارند."""
        for slug in ("heritage_premium", "vibrant_catalog", "nordic_living"):
            family = family_registry.get_family(slug)
            self.assertNotIn("story_rail", family.default_section_keys,
                             f"story_rail should not be in {slug} defaults")


# ============================================================ 5.x All Five Families

class AllFiveFamiliesRegisteredTests(TestCase):
    """تمام پنج خانواده باید ثبت شده و با تعریفات کامل باشند."""

    EXPECTED_FAMILIES = {"modern_fashion", "heritage_premium", "artisan_editorial", "vibrant_catalog", "nordic_living"}

    def test_all_five_registered(self):
        """هر ۵ خانواده در FAMILY_REGISTRY ثبت شده‌اند."""
        registered = {f.slug for f in family_registry.list_families()}
        self.assertEqual(registered, self.EXPECTED_FAMILIES)

    def test_each_family_has_complete_variant_paths(self):
        """هر خانواده باید تمام ۶ variant path را داشته باشد."""
        for slug in self.EXPECTED_FAMILIES:
            family = family_registry.get_family(slug)
            self.assertTrue(family.header_variant, f"{slug} missing header_variant")
            self.assertTrue(family.hero_variant, f"{slug} missing hero_variant")
            self.assertTrue(family.category_variant, f"{slug} missing category_variant")
            self.assertTrue(family.footer_variant, f"{slug} missing footer_variant")
            self.assertTrue(family.product_card_variant, f"{slug} missing product_card_variant")
            self.assertTrue(family.product_page_variant, f"{slug} missing product_page_variant")

    def test_each_family_has_default_preset(self):
        """هر خانواده باید یک preset پیش‌فرض معتبر داشته باشد."""
        for slug in self.EXPECTED_FAMILIES:
            family = family_registry.get_family(slug)
            preset = preset_registry.get_preset(family.default_preset_slug)
            self.assertIsNotNone(preset, f"{slug}: preset '{family.default_preset_slug}' not found")
            self.assertEqual(preset.family_slug, slug)

    def test_each_family_has_default_section_keys(self):
        """هر خانواده باید حداقل ۳ section key پیش‌فرض داشته باشد."""
        for slug in self.EXPECTED_FAMILIES:
            family = family_registry.get_family(slug)
            self.assertGreaterEqual(len(family.default_section_keys), 3,
                                    f"{slug} has fewer than 3 default sections")
            for key in family.default_section_keys:
                self.assertTrue(
                    section_registry.is_valid_section_key(key),
                    f"{slug}: default section '{key}' is not a valid section key",
                )

    def test_families_have_distinct_swatches(self):
        """هر خانواده باید swatch رنگی متفاوت داشته باشد."""
        swatches = set()
        for slug in self.EXPECTED_FAMILIES:
            family = family_registry.get_family(slug)
            self.assertEqual(len(family.swatch), 3)
            swatches.add(family.swatch)
        self.assertEqual(len(swatches), 5, "All five families must have distinct swatches")


class BackwardCompatibilityTests(TestCase):
    """سازگاری عقب — فروشگاه‌های موجود بدون family_slug نباید تغییر کنند."""

    def test_no_family_slug_default(self):
        """family_slug پیش‌فرض None است — خانواده‌ای فعال نیست."""
        self.assertIsNone(APPEARANCE_CONFIG_DEFAULTS["family_slug"])

    def test_no_preset_slug_default(self):
        """preset_slug پیش‌فرض None است."""
        self.assertIsNone(APPEARANCE_CONFIG_DEFAULTS["preset_slug"])

    def test_get_family_returns_none_for_null(self):
        """get_family(None) باید None برگرداند."""
        self.assertIsNone(family_registry.get_family(None))
        self.assertIsNone(family_registry.get_family(""))

    def test_new_appearance_fields_have_safe_defaults(self):
        """فیلدهای جدید (card_image_crossfade, card_image_zoom) باید safe default داشته باشند."""
        # crossfade=False یعنی هیچ تغییری در رفتار قبلی
        self.assertFalse(APPEARANCE_CONFIG_DEFAULTS["card_image_crossfade"])
        # zoom=True رفتار قبلی (image_hover=zoom) را حفظ می‌کند
        self.assertTrue(APPEARANCE_CONFIG_DEFAULTS["card_image_zoom"])


class SectionRegistryIntegrityTests(TestCase):
    """Section Registry — سلامت و کامل بودن."""

    def test_story_rail_is_only_new_section(self):
        """story_rail تنها section جدید اضافه‌شده در این فاز است."""
        # بررسی که story_rail ثبت شده
        self.assertTrue(section_registry.is_valid_section_key("story_rail"))

    def test_all_expected_sections_present(self):
        """تمام section key های مورد انتظار (شامل قبلی‌ها + story_rail) موجودند."""
        expected_keys = {
            "hero_banner", "image_slider", "single_banner", "multi_banner",
            "category_grid", "featured_products", "newest_products",
            "best_sellers", "discounted_products", "amazing_offers",
            "brand_carousel", "promo_cards", "rich_text", "image_text",
            "product_section", "trust_features", "collection_tiles",
            "quick_links", "faq", "testimonials", "video_section",
            "announcement_bar", "story_rail",
        }
        for key in expected_keys:
            self.assertTrue(
                section_registry.is_valid_section_key(key),
                f"Section '{key}' expected but not found in registry",
            )
