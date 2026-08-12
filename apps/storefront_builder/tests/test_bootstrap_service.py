from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.catalog.models import Category, IndustryTemplate, Product, Vendor
from apps.content.models import HeroSlide, PromotionalBanner
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import bootstrap_service, layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class BootstrapSectionsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_minimal_store_gets_baseline_sections(self):
        sections = bootstrap_service.build_bootstrap_sections(_akhlaghi())
        keys = [s["section_key"] for s in sections]
        self.assertIn("category_grid", keys)
        self.assertIn("newest_products", keys)
        self.assertIn("best_sellers", keys)
        self.assertIn("trust_features", keys)
        self.assertNotIn("hero_banner", keys)
        self.assertNotIn("discounted_products", keys)

    def test_active_hero_slide_included(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("hero_banner", [s["section_key"] for s in sections])

    def test_inactive_hero_slide_excluded(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=False)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertNotIn("hero_banner", [s["section_key"] for s in sections])

    def test_active_promo_banner_included_as_multi_banner(self):
        store = _akhlaghi()
        PromotionalBanner.objects.create(store=store, title="B", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("multi_banner", [s["section_key"] for s in sections])

    def test_discounted_products_included_only_when_present(self):
        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="V", slug="v-boot")
        cat = Category.objects.create(store=store, name="C", slug="c-boot")
        Product.objects.create(
            store=store, vendor=vendor, category=cat, name="P", slug="p-boot",
            sku="SKU-BOOT", price=Decimal("1000"), stock=1, discount_percent=10,
        )
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("discounted_products", [s["section_key"] for s in sections])

    def test_sections_ordered_sequentially(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        orders = [s["order"] for s in sections]
        self.assertEqual(orders, list(range(len(orders))))


class BootstrapIntegrationWithDraftTests(TestCase):
    """اطمینان از این‌که اولین Draft هر فروشگاه هرگز خالی نیست."""

    def setUp(self):
        cache.clear()

    def test_first_draft_is_bootstrapped_not_empty(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        self.assertEqual(draft.source, StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP)
        self.assertGreater(draft.sections.count(), 0)

    def test_second_draft_after_publish_is_manual_source_not_rebootstrapped(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        svc.publish(store)
        second_draft = svc.get_or_create_draft(store)
        self.assertEqual(second_draft.source, StorefrontLayoutVersion.Source.MANUAL)

    def test_flag_stays_false_until_explicit_publish(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        layout = svc.get_or_create_layout(store)
        self.assertFalse(layout.uses_visual_storefront_layout)


class IndustryDefaultSectionsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_uses_explicit_default_section_keys_in_order(self):
        store = _akhlaghi()
        template = IndustryTemplate.objects.create(
            slug="test-industry-bootstrap", name="صنف تست",
            default_section_keys=["hero_banner", "category_grid", "best_sellers"],
        )
        sections = bootstrap_service.build_industry_default_sections(store, template)
        self.assertEqual(
            [s["section_key"] for s in sections], ["hero_banner", "category_grid", "best_sellers"],
        )
        self.assertEqual([s["order"] for s in sections], [0, 1, 2])

    def test_unknown_keys_silently_dropped_never_crashes(self):
        store = _akhlaghi()
        template = IndustryTemplate.objects.create(
            slug="test-industry-unknown-key", name="صنف تست ۲",
            default_section_keys=["category_grid", "not_a_real_section_type", "best_sellers"],
        )
        sections = bootstrap_service.build_industry_default_sections(store, template)
        self.assertEqual([s["section_key"] for s in sections], ["category_grid", "best_sellers"])

    def test_empty_default_section_keys_falls_back_to_generic_bootstrap(self):
        store = _akhlaghi()
        template = IndustryTemplate.objects.create(slug="test-industry-empty", name="صنف تست ۳")
        sections = bootstrap_service.build_industry_default_sections(store, template)
        self.assertGreater(len(sections), 0)
        self.assertIn("category_grid", [s["section_key"] for s in sections])

    def test_apply_industry_content_creates_sections_on_version(self):
        store = _akhlaghi()
        template = IndustryTemplate.objects.create(
            slug="test-industry-apply", name="صنف تست ۴",
            default_section_keys=["hero_banner", "trust_features"],
        )
        layout = svc.get_or_create_layout(store)
        version = StorefrontLayoutVersion.objects.create(
            layout=layout, version_number=999, status=StorefrontLayoutVersion.Status.DRAFT,
        )
        bootstrap_service.apply_industry_content(version, store, template)
        # Phase 1A: apply_industry_content targets the version's home page
        # specifically; the aggregating `version.sections` property still
        # works (it spans all six pages) and is correct here too since
        # this version has content on exactly one page.
        self.assertEqual(
            list(version.sections.order_by("order").values_list("section_key", flat=True)),
            ["hero_banner", "trust_features"],
        )


class DefaultNonHomeSectionsTests(TestCase):
    """Phase 5: چهار صفحه‌ی غیرِ اصلی (product_detail/listing/collection/
    search/cart) دیگر خالی نمی‌مانند — نه یک صفحه‌ی «بومِ خالی» برایِ
    فروشگاهِ تازه."""

    def setUp(self):
        cache.clear()

    def test_build_default_non_home_sections_matches_expected_keys_per_page(self):
        self.assertEqual(
            [s["section_key"] for s in bootstrap_service.build_default_non_home_sections("product_detail")],
            ["product_main", "product_description", "product_video", "related_products"],
        )
        self.assertEqual(
            [s["section_key"] for s in bootstrap_service.build_default_non_home_sections("listing")],
            ["product_listing"],
        )
        self.assertEqual(
            [s["section_key"] for s in bootstrap_service.build_default_non_home_sections("search")],
            ["product_listing"],
        )
        self.assertEqual(
            [s["section_key"] for s in bootstrap_service.build_default_non_home_sections("collection")],
            ["collection_header", "collection_products"],
        )
        self.assertEqual(
            [s["section_key"] for s in bootstrap_service.build_default_non_home_sections("cart")],
            ["cart_items", "cart_summary"],
        )

    def test_build_default_non_home_sections_unknown_page_type_returns_empty(self):
        self.assertEqual(bootstrap_service.build_default_non_home_sections("home"), [])
        self.assertEqual(bootstrap_service.build_default_non_home_sections("not_a_real_page"), [])

    def test_first_draft_seeds_all_five_non_home_pages(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        for page_type, expected_first_key in [
            ("product_detail", "product_main"), ("listing", "product_listing"),
            ("collection", "collection_header"), ("search", "product_listing"),
            ("cart", "cart_items"),
        ]:
            page = draft.get_page(page_type)
            keys = list(page.sections.order_by("order").values_list("section_key", flat=True))
            self.assertGreater(len(keys), 0, page_type)
            self.assertEqual(keys[0], expected_first_key, page_type)

    def test_apply_default_non_home_sections_is_idempotent(self):
        """صدا زدنِ دوباره روی صفحه‌ای که از قبل Section دارد، چیزی
        تکراری اضافه نمی‌کند و محتوایِ موجود را بازنویسی نمی‌کند."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        pd_page = draft.get_page("product_detail")
        before = list(pd_page.sections.order_by("order").values_list("section_key", flat=True))

        bootstrap_service.apply_default_non_home_sections(draft)

        after = list(pd_page.sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(before, after)

    def test_apply_default_non_home_sections_never_overwrites_merchant_content(self):
        """اگر مرچنت خودش چیدمانِ یک صفحه را دستی تغییر داده (مثلاً
        related_products را حذف کرده)، فراخوانیِ دوباره‌ی این تابع آن را
        برنمی‌گرداند — چون صفحه دیگر خالی نیست."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        pd_page = draft.get_page("product_detail")
        pd_page.sections.filter(section_key="related_products").delete()
        remaining_before = set(pd_page.sections.values_list("section_key", flat=True))
        self.assertNotIn("related_products", remaining_before)

        bootstrap_service.apply_default_non_home_sections(draft)

        remaining_after = set(pd_page.sections.values_list("section_key", flat=True))
        self.assertEqual(remaining_before, remaining_after)

    def test_settings_are_valid_defaults_not_raw_empty_dict_where_applicable(self):
        """همان الگویی که ``_defaults`` بالایِ همین فایل مستند می‌کند —
        هر ``settings`` باید از خودِ ``default_settings()`` بیاید، نه
        ``{}`` خام، تا حداقل بلوکِ ``responsive`` همیشه حاضر باشد."""
        for section in bootstrap_service.build_default_non_home_sections("cart"):
            self.assertIn("responsive", section["settings"])
