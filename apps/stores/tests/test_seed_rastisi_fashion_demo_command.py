"""Django tests for ``seed_rastisi_fashion_demo`` — the deterministic QA/demo
Store seeder for the six-family visual-testing dataset.

MEDIA_ROOT is overridden to a temporary directory (same pattern as
``apps.core.tests.test_seed_shop.SeedShopCommandTests``) so the generated
synthetic images are never written under the real project ``media/``.

NOTE: this file is written to run under a real Django test runner; it is
NOT executed in this sandbox (no Django available — see the mission's
implementation report for the exact NOT EXECUTED disclosure). It is added
so the owner's Django-capable environment can run it directly.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    MerchantCollectionItem,
    Product,
    ProductImage,
    ProductVariant,
    Vendor,
)
from apps.content.models import ContentPage, FooterSettings, HeroSlide, Menu, MenuItem, PromotionalBanner, StoryRailItem
from apps.core.models import ShopSettings
from apps.storefront_builder.models import StorefrontLayout
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

STORE_SLUG = "rastisi-fashion-test"


@override_settings(DEBUG=True)
class SeedRastisiFashionDemoCommandTests(TestCase):
    """MEDIA_ROOT موقت — دقیقاً همان الگویِ ``test_seed_shop.py``.

    ``cache.clear()`` در ``setUp`` — ایزوله‌سازیِ Rate Limit میانِ تست‌ها.

    ``apps.core.services.rate_limit.enforce_rate_limit`` روی
    ``django.core.cache.cache`` (یک شیءِ سراسریِ سطحِ پروسه) شمارنده
    نگه می‌دارد. ``TestCase`` هر متد را در یک تراکنشِ دیتابیسی که در
    پایان rollback می‌شود اجرا می‌کند — اما این rollback هرگز کش را پاک
    نمی‌کند، و در SQLite (پرکاربردترین DBِ تستِ محلی) شماره‌یِ pk ردیفِ
    بعدی معمولاً از رویِ ``max(rowid)`` محاسبه می‌شود، نه یک شمارنده‌یِ
    مستقل و پایدار؛ پس Storeِ QAیِ تازه‌ساخته‌شده در متدهایِ تستِ مختلف
    اغلب دقیقاً همان pk را می‌گیرد. چون کلیدِ Rate Limit شاملِ
    ``str(store.pk)`` است، شمارنده‌ها بین متدهایِ تستیِ کاملاً مستقل
    تجمیع می‌شوند و پس از چند ده فراخوانی به سقفِ ۲۰/۳۰ در ساعت می‌رسند —
    این دقیقاً ریشه‌یِ ۲۲ خطایِ ``RateLimitExceeded``یِ گزارش‌شده بود.

    ``cache.clear()`` باریک‌ترین مکانیزمِ پشتیبانی‌شده‌یِ Django برایِ
    این ایزوله‌سازی است — هیچ Rate Limitِ Productionی غیرفعال/دستکاری
    نمی‌شود؛ فقط حافظه‌یِ کشِ *تست* بینِ هر متد صفر می‌شود، دقیقاً همان‌طور
    که تراکنشِ دیتابیس بینِ هر متد rollback می‌شود."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="qa-fashion-owner", password="pass12345")

    def _run(self, *extra_args):
        call_command(
            "seed_rastisi_fashion_demo", "--owner-username", "qa-fashion-owner", *extra_args, stdout=StringIO(),
        )

    def _store(self) -> Store:
        return Store.objects.get(slug=STORE_SLUG)


class SafetyGateTests(SeedRastisiFashionDemoCommandTests):
    @override_settings(DEBUG=False)
    def test_refuses_to_run_outside_debug(self):
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_unknown_owner_username_raises_and_creates_nothing(self):
        with self.assertRaises(CommandError):
            call_command(
                "seed_rastisi_fashion_demo", "--owner-username", "does-not-exist-at-all", stdout=StringIO(),
            )
        self.assertFalse(Store.objects.filter(slug=STORE_SLUG).exists())
        self.assertFalse(User.objects.filter(username="does-not-exist-at-all").exists())

    def test_unknown_family_slug_raises(self):
        with self.assertRaises(CommandError):
            self._run("--family", "not_a_real_family")

    def test_never_creates_an_insecure_default_user(self):
        """The command must never silently create a user for the requested
        username — the owner user must already exist."""
        with self.assertRaises(CommandError):
            call_command(
                "seed_rastisi_fashion_demo", "--owner-username", "brand-new-nobody", stdout=StringIO(),
            )
        self.assertEqual(User.objects.filter(username="brand-new-nobody").count(), 0)


class StoreIdentityTests(SeedRastisiFashionDemoCommandTests):
    def test_creates_exactly_one_new_store(self):
        before = Store.objects.count()
        self._run()
        self.assertEqual(Store.objects.count(), before + 1)
        store = self._store()
        self.assertEqual(store.name, "فروشگاه لباس تستی راستی سی")
        self.assertEqual(store.status, Store.Status.ACTIVE)

    def test_does_not_touch_the_akhlaghi_store(self):
        akhlaghi_before = Store.objects.get(slug="akhlaghi")
        akhlaghi_name_before = akhlaghi_before.name
        akhlaghi_updated_before = akhlaghi_before.updated_at
        self._run()
        akhlaghi_after = Store.objects.get(slug="akhlaghi")
        self.assertEqual(akhlaghi_after.name, akhlaghi_name_before)
        self.assertEqual(akhlaghi_after.updated_at, akhlaghi_updated_before)

    def test_store_domain_is_verified_and_routable(self):
        self._run()
        store = self._store()
        domain = StoreDomain.objects.get(store=store, is_primary=True)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertIsNotNone(domain.verified_at)
        self.assertIsNone(domain.retired_at)
        self.assertTrue(domain.hostname.endswith(".rastisi.localhost"))

    def test_owner_membership_is_active_owner(self):
        self._run()
        store = self._store()
        membership = StoreMembership.objects.get(store=store, user=self.owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertIsNotNone(membership.accepted_at)

    def test_shop_settings_provisioned_with_gift_wrap_enabled(self):
        self._run()
        store = self._store()
        shop = ShopSettings.objects.get(store=store)
        self.assertTrue(shop.gift_wrap_available)
        self.assertGreater(shop.gift_wrap_price, 0)

    def test_footer_settings_provisioned(self):
        self._run()
        store = self._store()
        footer = FooterSettings.objects.get(store=store)
        self.assertTrue(footer.is_enabled)
        self.assertTrue(footer.phone)


class CatalogCountTests(SeedRastisiFashionDemoCommandTests):
    def test_creates_exactly_100_products(self):
        self._run()
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store).count(), 100)

    def test_creates_10_primary_categories_with_2_children_each(self):
        self._run()
        store = self._store()
        primary = Category.objects.filter(store=store, parent__isnull=True)
        self.assertEqual(primary.count(), 10)
        for category in primary:
            self.assertEqual(category.children.count(), 2)
        self.assertEqual(Category.objects.filter(store=store).count(), 30)

    def test_10_products_per_primary_category(self):
        self._run()
        store = self._store()
        for category in Category.objects.filter(store=store, parent__isnull=True):
            count = Product.objects.filter(store=store, category__parent=category).count()
            self.assertEqual(count, 10, category.slug)

    def test_all_products_belong_to_the_qa_store(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            self.assertEqual(product.category.store_id, store.pk)
            self.assertEqual(product.vendor.store_id, store.pk)

    def test_no_product_leaks_to_another_store(self):
        self._run()
        store = self._store()
        akhlaghi = Store.objects.get(slug="akhlaghi")
        overlap = Product.objects.filter(store=store, pk__in=Product.objects.filter(store=akhlaghi))
        self.assertEqual(overlap.count(), 0)

    def test_stock_distribution_matches_expected_shape(self):
        self._run()
        store = self._store()
        products = Product.objects.filter(store=store)
        zero_stock = products.filter(stock=0).count()
        low_stock = products.filter(stock__gte=1, stock__lte=5).count()
        normal_stock = products.filter(stock__gt=5).count()
        self.assertGreaterEqual(zero_stock, 5)
        self.assertGreaterEqual(low_stock, 5)
        self.assertGreaterEqual(normal_stock, 60)
        self.assertEqual(zero_stock + low_stock + normal_stock, 100)

    def test_most_products_are_active_but_some_are_draft_or_inactive(self):
        self._run()
        store = self._store()
        products = Product.objects.filter(store=store)
        active = products.filter(status=Product.Status.ACTIVE).count()
        non_active = products.exclude(status=Product.Status.ACTIVE).count()
        self.assertGreater(active, 90)
        self.assertGreater(non_active, 0)

    def test_some_products_are_discounted(self):
        self._run()
        store = self._store()
        self.assertTrue(Product.objects.filter(store=store, discount_percent__gt=0).exists())


class VariantAndImageTests(SeedRastisiFashionDemoCommandTests):
    def test_at_least_30_products_have_multiple_variants(self):
        self._run()
        store = self._store()
        multi_variant_products = 0
        for product in Product.objects.filter(store=store):
            if product.variants.count() >= 2:
                multi_variant_products += 1
        self.assertGreaterEqual(multi_variant_products, 30)

    def test_some_products_have_no_variants(self):
        self._run()
        store = self._store()
        self.assertTrue(Product.objects.filter(store=store, variants__isnull=True).exists())

    def test_at_least_10_products_have_one_unavailable_variant_alongside_available_ones(self):
        self._run()
        store = self._store()
        matching = 0
        for product in Product.objects.filter(store=store):
            variants = list(product.variants.all())
            if len(variants) < 2:
                continue
            zero = [v for v in variants if v.stock == 0]
            nonzero = [v for v in variants if v.stock > 0]
            if zero and nonzero:
                matching += 1
        self.assertGreaterEqual(matching, 10)

    def test_variants_belong_to_the_correct_store(self):
        self._run()
        store = self._store()
        for variant in ProductVariant.objects.filter(product__store=store):
            self.assertEqual(variant.store_id, store.pk)
            self.assertEqual(variant.product.store_id, store.pk)

    def test_at_least_20_variant_image_mappings_exist(self):
        self._run()
        store = self._store()
        mapped = ProductImage.objects.filter(product__store=store, variant__isnull=False).count()
        self.assertGreaterEqual(mapped, 20)

    def test_variant_image_mapping_belongs_to_the_same_product(self):
        self._run()
        store = self._store()
        for image in ProductImage.objects.filter(product__store=store, variant__isnull=False):
            self.assertEqual(image.variant.product_id, image.product_id)

    def test_products_without_variant_images_still_have_at_least_2_images(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            if product.images.filter(variant__isnull=False).exists():
                continue
            self.assertGreaterEqual(product.images.count(), 2, product.slug)


class MerchantCollectionTests(SeedRastisiFashionDemoCommandTests):
    def test_creates_at_least_6_collections(self):
        self._run()
        store = self._store()
        self.assertGreaterEqual(MerchantCollection.objects.filter(store=store).count(), 6)

    def test_collections_only_reference_qa_store_products(self):
        self._run()
        store = self._store()
        for item in MerchantCollectionItem.objects.filter(collection__store=store):
            self.assertEqual(item.product.store_id, store.pk)
            self.assertEqual(item.collection.store_id, store.pk)


class HeroBannerStoryTests(SeedRastisiFashionDemoCommandTests):
    def test_creates_at_least_4_hero_slides(self):
        self._run()
        store = self._store()
        self.assertGreaterEqual(HeroSlide.objects.filter(store=store).count(), 4)

    def test_creates_at_least_4_promotional_banners(self):
        self._run()
        store = self._store()
        self.assertGreaterEqual(PromotionalBanner.objects.filter(store=store).count(), 4)

    def test_creates_at_least_10_story_rail_items(self):
        self._run()
        store = self._store()
        self.assertGreaterEqual(StoryRailItem.objects.filter(store=store).count(), 10)

    def test_story_rail_items_have_a_real_destination(self):
        self._run()
        store = self._store()
        for item in StoryRailItem.objects.filter(store=store):
            self.assertNotEqual(item.destination_type, "none")


class NavigationAndContentTests(SeedRastisiFashionDemoCommandTests):
    def test_header_menu_has_no_dead_links(self):
        self._run()
        store = self._store()
        menu = Menu.objects.get(store=store, location=Menu.Location.HEADER)
        for item in MenuItem.objects.filter(menu=menu):
            self.assertNotEqual(item.destination_type, "none")

    def test_creates_content_pages_visible_in_footer(self):
        self._run()
        store = self._store()
        pages = ContentPage.objects.filter(store=store, show_in_footer=True)
        self.assertGreaterEqual(pages.count(), 6)
        for page in pages:
            self.assertEqual(page.status, ContentPage.Status.PUBLISHED)


class BuilderLifecycleTests(SeedRastisiFashionDemoCommandTests):
    def test_storefront_layout_belongs_to_qa_store_with_published_version(self):
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        self.assertIsNotNone(layout.published_version_id)
        self.assertIsNone(layout.draft_version_id)  # publish() clears the draft pointer

    def test_published_family_matches_requested_family(self):
        self._run("--family", "zarrin_jewelry")
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        config = layout.published_version.effective_appearance_config()
        self.assertEqual(config["family_slug"], "zarrin_jewelry")

    def test_default_family_is_atlas_catalog(self):
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        config = layout.published_version.effective_appearance_config()
        self.assertEqual(config["family_slug"], "atlas_catalog")

    def test_published_version_has_real_family_default_sections(self):
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        section_keys = list(layout.published_version.sections.values_list("section_key", flat=True))
        self.assertTrue(section_keys)

    def test_rerunning_with_same_family_does_not_create_a_new_published_version(self):
        """Checkpoint (Root Cause 1) — a second, identical invocation must
        not perform a redundant publish() when the published state already
        matches the requested family. Proven directly at the model level:
        the published StorefrontLayoutVersion's pk (and total version
        count) must be unchanged after a second run."""
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        first_published_version_id = layout.published_version_id
        first_version_count = layout.versions.count()

        self._run()

        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, first_published_version_id)
        self.assertEqual(layout.versions.count(), first_version_count)
        self.assertIsNone(layout.draft_version_id)

    def test_rerunning_with_a_different_family_does_perform_a_real_publish(self):
        """The idempotency short-circuit must only apply when the requested
        family already matches — a genuine family change must still go
        through the real lifecycle (new Draft + publish)."""
        self._run("--family", "atlas_catalog")
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        first_published_version_id = layout.published_version_id

        self._run("--family", "zarrin_jewelry")

        layout.refresh_from_db()
        self.assertNotEqual(layout.published_version_id, first_published_version_id)
        config = layout.published_version.effective_appearance_config()
        self.assertEqual(config["family_slug"], "zarrin_jewelry")

    def test_many_reruns_with_same_family_never_exhaust_the_publish_rate_limit(self):
        """Checkpoint (Root Cause 1) — the production publish rate limit is
        20 attempts/hour per Store. Rerunning the seed command 25 times with
        an unchanged family must not raise RateLimitExceeded, because only
        the FIRST run should ever call layout_service.publish()."""
        for _ in range(25):
            self._run()  # must never raise RateLimitExceeded
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        self.assertIsNotNone(layout.published_version_id)


class IdempotencyTests(SeedRastisiFashionDemoCommandTests):
    def test_first_seed_run_succeeds(self):
        self._run()  # must not raise
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 100)

    def test_immediate_identical_second_run_succeeds(self):
        self._run()
        self._run()  # must not raise (this is exactly what previously hit RateLimitExceeded)
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_second_identical_run_does_not_duplicate_products(self):
        self._run()
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 100)

    def test_second_identical_run_does_not_duplicate_variants(self):
        self._run()
        first_count = ProductVariant.objects.filter(product__store=self._store()).count()
        self._run()
        second_count = ProductVariant.objects.filter(product__store=self._store()).count()
        self.assertEqual(first_count, second_count)

    def test_rerunning_does_not_duplicate_store_or_products(self):
        self._run()
        self._run()
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store).count(), 100)

    def test_rerunning_does_not_duplicate_categories_or_brands(self):
        self._run()
        self._run()
        store = self._store()
        self.assertEqual(Category.objects.filter(store=store).count(), 30)
        self.assertEqual(Brand.objects.filter(store=store).count(), 4)

    def test_rerunning_does_not_duplicate_variants(self):
        self._run()
        first_variant_count = ProductVariant.objects.filter(product__store=self._store()).count()
        self._run()
        second_variant_count = ProductVariant.objects.filter(product__store=self._store()).count()
        self.assertEqual(first_variant_count, second_variant_count)

    def test_rerunning_does_not_duplicate_hero_banner_story_items(self):
        self._run()
        store = self._store()
        hero_before = HeroSlide.objects.filter(store=store).count()
        banner_before = PromotionalBanner.objects.filter(store=store).count()
        story_before = StoryRailItem.objects.filter(store=store).count()
        self._run()
        self.assertEqual(HeroSlide.objects.filter(store=store).count(), hero_before)
        self.assertEqual(PromotionalBanner.objects.filter(store=store).count(), banner_before)
        self.assertEqual(StoryRailItem.objects.filter(store=store).count(), story_before)


class RateLimitIsolationTests(SeedRastisiFashionDemoCommandTests):
    """Checkpoint — test-process rate-limit state must never leak between
    independent test methods (the exact mechanism behind the originally
    reported 22 errors: predictable Store pks + a cache that survives
    per-test transaction rollback)."""

    def test_rate_limit_cache_is_cleared_before_each_test(self):
        from apps.core.services.rate_limit import enforce_rate_limit

        # If a previous test method leaked counters into this identifier,
        # this call would already be near/at its limit. setUp()'s
        # cache.clear() must guarantee a clean slate every time.
        enforce_rate_limit("storefront_layout.publish", "isolation-probe", max_attempts=1, window_seconds=3600)

    def test_running_the_seed_command_in_many_independent_test_methods_never_leaks_rate_limit_state(self):
        """Simulates what happens across this file's own many TestCase
        methods: each gets a fresh cache, so even though the QA Store
        (and therefore its pk-derived rate-limit key) is recreated
        identically every time, no test observes another test's counters."""
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        self.assertIsNotNone(layout.published_version_id)


class ResetTests(SeedRastisiFashionDemoCommandTests):
    """Checkpoint (Root Cause 2) — ``--reset`` must succeed against the
    real model graph (Product.category / MenuItem.menu are both PROTECT),
    never touch unrelated Store-owned data, and remain safely repeatable."""

    def test_reset_after_a_completed_seed_succeeds(self):
        """This is the exact scenario that previously raised
        ProtectedError: a fully-seeded QA Store (100 Products under
        PROTECTed Categories, a header Menu with PROTECTed MenuItems) must
        be resettable without any exception."""
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 100)
        self._run("--reset")  # must not raise ProtectedError
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_reset_rebuilds_only_the_qa_store(self):
        self._run()
        first_store_pk = self._store().pk
        akhlaghi_before = Store.objects.get(slug="akhlaghi")

        self._run("--reset")

        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())
        new_store = self._store()
        # A fresh row after --reset: same slug, but the Store itself was
        # deleted and recreated, not merely updated in place.
        self.assertNotEqual(new_store.pk, first_store_pk)
        self.assertEqual(Product.objects.filter(store=new_store).count(), 100)

        akhlaghi_after = Store.objects.get(slug="akhlaghi")
        self.assertEqual(akhlaghi_after.pk, akhlaghi_before.pk)

    def test_reset_on_a_never_seeded_database_does_not_error(self):
        # No prior _run() call — the QA Store does not exist yet.
        self._run("--reset")
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_reset_never_deletes_an_unrelated_store(self):
        other_store = Store.objects.create(
            name="Store Unrelated", slug="unrelated-store-srfd", status=Store.Status.ACTIVE,
        )
        self._run()
        self._run("--reset")
        self.assertTrue(Store.objects.filter(pk=other_store.pk).exists())

    def test_reset_does_not_delete_unrelated_categories_products_or_menus(self):
        """A second, unrelated Store with its own Category/Product/Menu
        graph (deliberately exercising the same PROTECT relationships as
        the QA Store) must be completely untouched by --reset."""
        other_store = Store.objects.create(
            name="Store Unrelated Catalog", slug="unrelated-catalog-srfd", status=Store.Status.ACTIVE,
        )
        other_vendor = Vendor.objects.create(store=other_store, name="Other Vendor", slug="other-vendor-srfd")
        other_category = Category.objects.create(store=other_store, name="Other Cat", slug="other-cat-srfd")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="Other Product",
            slug="other-product-srfd", sku="OTHER-SRFD-1", price=1000, stock=1,
        )
        other_menu = Menu.objects.create(store=other_store, title="Other Menu", location=Menu.Location.HEADER)
        other_menu_item = MenuItem.objects.create(
            menu=other_menu, title="Other Item", destination_type="category", destination_category=other_category,
        )

        self._run()
        self._run("--reset")

        self.assertTrue(Category.objects.filter(pk=other_category.pk).exists())
        self.assertTrue(Product.objects.filter(pk=other_product.pk).exists())
        self.assertTrue(Menu.objects.filter(pk=other_menu.pk).exists())
        self.assertTrue(MenuItem.objects.filter(pk=other_menu_item.pk).exists())

    def test_reset_can_be_run_repeatedly(self):
        self._run()
        self._run("--reset")
        self._run()
        self._run("--reset")
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 100)

    def test_reset_removes_qa_store_products_categories_and_menu_items(self):
        self._run()
        store_pk = self._store().pk
        self._run("--reset")
        # The old Store row (and everything that was CASCADE/PROTECT-owned
        # by it) must be fully gone — not merely orphaned.
        self.assertFalse(Store.objects.filter(pk=store_pk).exists())
        self.assertFalse(Product.objects.filter(store_id=store_pk).exists())
        self.assertFalse(Category.objects.filter(store_id=store_pk).exists())
        self.assertFalse(MenuItem.objects.filter(menu__store_id=store_pk).exists())
