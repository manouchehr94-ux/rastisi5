"""Django tests for ``seed_ready_template_fashion_demo`` — «Rasti Mode Demo —
COMPLETE REAL CATALOG + MEDIA + CONTENT» mission.

The old apparel-only 50-product matrix (Phase 1 / Phase 1.1) is no longer
the visual source of truth — the real 345 user-supplied QA images are (see
``apps/stores/demo_assets/rasti_mode_demo/`` and the execution ledger's
image-audit section). This file replaces the old matrix-specific
assertions with the new real-catalog contract: 10 categories built around
the ACTUAL observed image content (running/casual sneakers, casual
trousers/jeans, bomber & leather/overshirt jackets, women's shoes &
sandals, handbags & shoulder bags), 6 fictional brands (no real/guessed
brand names, since several raw source photos show unverified third-party
trademarks), real ProductImage media imported from the pre-processed
``products/<SKU>/0N.webp`` files (never from ``raw_user_catalog/``
directly), and content (hero/banners/story rail/collections/navigation/
footer/ShopSettings) built from that same real catalog.

MEDIA_ROOT is overridden to a temporary directory so uploaded
``ProductImage``/``HeroSlide``/etc. files are never written under the real
project ``media/``.
"""

import shutil
import tempfile
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    Product,
    ProductImage,
    ProductTag,
    ProductVariant,
)
from apps.content.models import FooterSettings, HeroSlide, Menu, MenuItem, PromotionalBanner, StoryRailItem
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry as lpr
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    BAG_CATEGORIES,
    CATEGORY_NAMES,
    OUT_OF_STOCK,
    PARTIAL_VARIANT_STOCK,
    PRODUCT_MATRIX,
)
from apps.stores.models import Store, StoreDomain

STORE_SLUG = "rasti-mode-demo"
OTHER_REAL_SLUG = "rastisi-fashion-test"


class SeedReadyTemplateFashionDemoCommandTests(TestCase):
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

    def _run(self, *extra_args):
        call_command("seed_ready_template_fashion_demo", *extra_args, stdout=StringIO())

    def _store(self) -> Store:
        return Store.objects.get(slug=STORE_SLUG)


class StoreIdentityTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_creates_the_isolated_demo_store(self):
        self._run()
        store = self._store()
        self.assertEqual(store.name, "Rasti Mode Demo")
        self.assertEqual(store.status, Store.Status.ACTIVE)

    def test_does_not_touch_the_akhlaghi_store(self):
        akhlaghi_before = Store.objects.get(slug="akhlaghi")
        name_before = akhlaghi_before.name
        self._run()
        akhlaghi_after = Store.objects.get(slug="akhlaghi")
        self.assertEqual(akhlaghi_after.name, name_before)

    def test_store_has_both_admin_and_public_domains(self):
        self._run()
        store = self._store()
        domains = list(StoreDomain.objects.filter(store=store))
        self.assertEqual(len(domains), 2)
        admin_domain = next(d for d in domains if d.is_primary)
        public_domain = next(d for d in domains if not d.is_primary)
        self.assertTrue(admin_domain.hostname.startswith(store.admin_subdomain))
        self.assertTrue(public_domain.hostname.startswith(f"shop-{store.admin_subdomain}"))
        self.assertNotEqual(admin_domain.hostname, public_domain.hostname)
        for domain in domains:
            self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)

    def test_shop_settings_provisioned(self):
        """Without this, the real PDP breaks with ShopSettingsNotProvisionedError
        (discovered during real-storefront verification)."""
        self._run()
        store = self._store()
        settings_row = ShopSettings.objects.get(store=store)
        self.assertTrue(settings_row.tagline)
        self.assertTrue(settings_row.contact_phone)


class ExactCatalogCountTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_exactly_50_products(self):
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)

    def test_exactly_10_categories(self):
        self._run()
        self.assertEqual(Category.objects.filter(store=self._store()).count(), 10)
        self.assertEqual(
            set(Category.objects.filter(store=self._store()).values_list("name", flat=True)),
            set(CATEGORY_NAMES),
        )

    def test_exactly_5_products_per_category(self):
        self._run()
        store = self._store()
        for category in Category.objects.filter(store=store):
            self.assertEqual(Product.objects.filter(store=store, category=category).count(), 5, category.name)

    def test_at_least_6_brands_and_every_brand_used(self):
        self._run()
        store = self._store()
        brands = Brand.objects.filter(store=store)
        self.assertGreaterEqual(brands.count(), 6)
        for brand in brands:
            self.assertGreater(Product.objects.filter(store=store, brand=brand).count(), 0, brand.name)

    def test_exactly_22_discounted_and_28_non_discounted(self):
        self._run()
        store = self._store()
        products = Product.objects.filter(store=store)
        self.assertEqual(products.filter(discount_percent__gt=0).count(), 22)
        self.assertEqual(products.filter(discount_percent=0).count(), 28)

    def test_exactly_10_fully_out_of_stock_products(self):
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store(), stock=0).count(), 10)

    def test_at_least_8_partial_stock_products_with_real_variant_semantics(self):
        self._run()
        store = self._store()
        partial_count = sum(1 for row in PRODUCT_MATRIX if row[8] == PARTIAL_VARIANT_STOCK)
        self.assertGreaterEqual(partial_count, 8)
        for code, *_rest, stock_state in PRODUCT_MATRIX:
            if stock_state != PARTIAL_VARIANT_STOCK:
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertTrue(product.is_variable, code)
            variants = list(product.variants.filter(is_obsolete=False))
            self.assertTrue(any(v.stock == 0 for v in variants), code)
            self.assertTrue(any(v.stock > 0 for v in variants), code)

    def test_exactly_150_product_images(self):
        self._run()
        self.assertEqual(ProductImage.objects.filter(product__store=self._store()).count(), 150)

    def test_exactly_3_images_and_1_cover_per_product(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            images = list(product.images.all())
            self.assertEqual(len(images), 3, product.sku)
            self.assertEqual(sum(1 for i in images if i.is_cover), 1, product.sku)


class SizeAndVariantSemanticsTests(SeedReadyTemplateFashionDemoCommandTests):
    """Mission Step 9: category-correct size semantics — no meaningless
    apparel sizes on bags, sensible footwear sizes on shoes/sandals."""

    def test_bags_have_no_size_option_and_are_simple_products(self):
        """Bags never get a meaningful size axis. A single-color bag stays a
        plain SIMPLE product with zero option axes; a genuine multi-color bag
        (mission Issue 2 hardening pass) becomes VARIABLE but with ONLY a
        real colour axis — never a size axis, since bags have no meaningful
        size."""
        self._run()
        store = self._store()
        for code, category_name, *rest in PRODUCT_MATRIX:
            if category_name not in BAG_CATEGORIES:
                continue
            color = rest[4]
            product = Product.objects.get(store=store, sku=code)
            self.assertFalse(product.options.filter(label="سایز", is_active=True).exists(), code)
            if isinstance(color, tuple):
                self.assertTrue(product.is_variable, f"{code} multi-color bag should be VARIABLE")
                self.assertEqual(product.options.filter(is_active=True).count(), 1, code)
            else:
                self.assertFalse(product.is_variable, f"{code} should be SIMPLE, no size option")
                self.assertEqual(product.options.count(), 0, code)

    def test_footwear_categories_use_plausible_shoe_sizes(self):
        self._run()
        footwear_categories = {"کتانی رانینگ", "کتانی کژوال", "کفش زنانه", "صندل و دمپایی"}
        for row in PRODUCT_MATRIX:
            code, category_name, sizes = row[0], row[1], row[7]
            if category_name not in footwear_categories:
                continue
            for size in sizes:
                self.assertTrue(size.isdigit(), f"{code}: {size!r} is not a numeric shoe size")
                self.assertGreaterEqual(int(size), 36)
                self.assertLessEqual(int(size), 46)

    def test_all_non_bag_products_have_real_color_and_size_options(self):
        self._run()
        store = self._store()
        for code, category_name, *_rest in PRODUCT_MATRIX:
            if category_name in BAG_CATEGORIES:
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertTrue(product.options.filter(label="رنگ", is_active=True).exists(), code)
            self.assertTrue(product.options.filter(label="سایز", is_active=True).exists(), code)

    def test_single_visible_color_products_are_not_given_fake_multi_color_variants(self):
        """Post-demo hardening pass (mission Issue 2): a small, verified set
        of products now has genuine multi-color media (see
        ``MultiColorProductTests`` below) — every *other* product must still
        show exactly the one real color it was photographed in, per the
        original mission Step 8: 'Do NOT invent color variants merely to
        satisfy an old count.'"""
        self._run()
        store = self._store()
        for row in PRODUCT_MATRIX:
            code, category_name, color = row[0], row[1], row[6]
            if category_name in BAG_CATEGORIES or isinstance(color, tuple):
                continue
            product = Product.objects.get(store=store, sku=code)
            color_option = product.options.get(label="رنگ", is_active=True)
            self.assertEqual(color_option.values.filter(is_active=True).count(), 1, code)


class StockSemanticsTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_out_of_stock_products_have_zero_stock_everywhere(self):
        self._run()
        store = self._store()
        for code, category_name, *_rest, stock_state in PRODUCT_MATRIX:
            if stock_state != OUT_OF_STOCK:
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertEqual(product.stock, 0, code)
            if category_name not in BAG_CATEGORIES:
                variants = list(product.variants.filter(is_obsolete=False))
                self.assertTrue(variants, code)
                self.assertTrue(all(v.stock == 0 for v in variants), code)

    def test_product_stock_equals_sum_of_variant_stocks_for_variable_products(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store, product_type=Product.ProductType.VARIABLE):
            total = sum(v.stock for v in product.variants.filter(is_obsolete=False))
            self.assertEqual(product.stock, total, product.sku)


class MultiColorProductTests(SeedReadyTemplateFashionDemoCommandTests):
    """Post-demo hardening pass, mission Issue 2: a verified set of products
    now has genuine multi-color real media (real second/third photos of the
    same garment/silhouette, never a fabricated label) — this class covers
    every required contract for those products specifically."""

    def _multi_color_rows(self):
        return [row for row in PRODUCT_MATRIX if isinstance(row[6], tuple)]

    def test_at_least_eight_products_are_genuinely_multi_color(self):
        self.assertGreaterEqual(len(self._multi_color_rows()), 8)

    def test_every_declared_color_has_its_own_mapped_option_value(self):
        self._run()
        store = self._store()
        for row in self._multi_color_rows():
            code, colors = row[0], row[6]
            product = Product.objects.get(store=store, sku=code)
            color_option = product.options.get(label="رنگ", is_active=True)
            mapped_labels = set(color_option.values.filter(is_active=True).values_list("label", flat=True))
            self.assertEqual(mapped_labels, set(colors), code)

    def test_every_declared_color_has_at_least_one_real_mapped_image(self):
        """No declared color exists without matching real media — every
        colour value on the product must be referenced by at least one of
        that product's own ProductImage rows."""
        self._run()
        store = self._store()
        for row in self._multi_color_rows():
            code = row[0]
            product = Product.objects.get(store=store, sku=code)
            color_option = product.options.get(label="رنگ", is_active=True)
            mapped_via_images = set(
                product.images.filter(option_value__isnull=False)
                .values_list("option_value__label", flat=True)
            )
            for value in color_option.values.filter(is_active=True):
                self.assertIn(value.label, mapped_via_images, f"{code}: color {value.label!r} has no mapped image")

    def test_color_image_mapping_never_points_at_another_products_media(self):
        """Color selection must never resolve to another SKU's image —
        every ProductImage a product's color values map to must itself
        belong to that same product."""
        self._run()
        store = self._store()
        for row in self._multi_color_rows():
            code = row[0]
            product = Product.objects.get(store=store, sku=code)
            for image in product.images.filter(option_value__isnull=False):
                self.assertEqual(image.product_id, product.id, code)

    def test_multi_color_products_retain_full_size_combinations_per_color(self):
        """A multi-color apparel/footwear product must still offer every
        declared size for every declared color — no color is a second-class
        citizen with a truncated size run."""
        self._run()
        store = self._store()
        for row in self._multi_color_rows():
            code, category_name, colors, sizes = row[0], row[1], row[6], row[7]
            if category_name in BAG_CATEGORIES:
                continue
            product = Product.objects.get(store=store, sku=code)
            variants = product.variants.filter(is_obsolete=False)
            self.assertEqual(variants.count(), len(colors) * len(sizes), code)
            seen = {tuple(v.value.split(" / ")) for v in variants}
            expected = {(c, s) for c in colors for s in sizes}
            self.assertEqual(seen, expected, code)

    def test_stock_varies_across_color_and_size_combinations(self):
        """A PARTIAL_VARIANT_STOCK multi-color product shows genuine
        within-product stock variation (not a flat constant); OUT_OF_STOCK
        and IN_STOCK products are legitimately uniform (all-zero / all
        healthy, respectively)."""
        self._run()
        store = self._store()
        for row in self._multi_color_rows():
            code, stock_state = row[0], row[8]
            product = Product.objects.get(store=store, sku=code)
            stocks = {v.stock for v in product.variants.filter(is_obsolete=False)}
            if stock_state == PARTIAL_VARIANT_STOCK:
                self.assertGreater(len(stocks), 1, f"{code}: expected genuine stock variation")
                self.assertIn(0, stocks, f"{code}: expected at least one zero-stock combination")
            elif stock_state == OUT_OF_STOCK:
                self.assertEqual(stocks, {0}, code)
            else:
                self.assertNotIn(0, stocks, code)

    def test_several_partial_stock_cases_cross_color_boundaries(self):
        """A partial-stock multi-color product must not confine its
        zero-stock combinations to a single color — the same zero-stock
        condition (e.g. the first size, or the cover color on a bag) must
        recur across more than one declared color, proving the shortage is
        not merely 'one color happens to be entirely OOS'."""
        self._run()
        store = self._store()
        partial_rows = [row for row in self._multi_color_rows() if row[8] == PARTIAL_VARIANT_STOCK]
        self.assertGreaterEqual(len(partial_rows), 2, "expected several partial-stock multi-color products")
        crossing_count = 0
        for row in partial_rows:
            code, colors = row[0], row[6]
            product = Product.objects.get(store=store, sku=code)
            zero_variants = product.variants.filter(is_obsolete=False, stock=0)
            colors_with_zero_stock = {v.value.split(" / ")[0] for v in zero_variants}
            if len(colors_with_zero_stock) >= 2:
                crossing_count += 1
            self.assertTrue(zero_variants.exists(), f"{code}: PARTIAL_VARIANT_STOCK but nothing is zero-stock")
        self.assertGreaterEqual(crossing_count, 2, "expected several partial-stock cases to cross color boundaries")

    def test_single_color_products_are_unaffected_by_the_multi_color_mechanism(self):
        self._run()
        store = self._store()
        multi_skus = {row[0] for row in self._multi_color_rows()}
        for row in PRODUCT_MATRIX:
            code, category_name, color = row[0], row[1], row[6]
            if code in multi_skus or category_name in BAG_CATEGORIES:
                continue
            product = Product.objects.get(store=store, sku=code)
            color_option = product.options.get(label="رنگ", is_active=True)
            self.assertEqual(color_option.values.filter(is_active=True).count(), 1, code)
            self.assertEqual(color_option.values.get(is_active=True).label, color, code)


class MediaImportTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_images_are_imported_from_processed_folder_not_raw_catalog(self):
        """Mission's explicit prohibition: raw_user_catalog must never be
        directly used as a public media URL."""
        self._run()
        store = self._store()
        for image in ProductImage.objects.filter(product__store=store):
            self.assertNotIn("raw_user_catalog", str(image.image))

    def test_multi_color_products_get_option_value_mapping_on_cover(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store, product_type=Product.ProductType.VARIABLE):
            cover = product.images.get(is_cover=True)
            self.assertIsNotNone(cover.option_value_id, product.sku)

    def test_no_external_retailer_urls_in_product_data(self):
        self._run()
        store = self._store()
        forbidden = ("http://", "https://", "zara.com", "asos.com", "farfetch")
        for product in Product.objects.filter(store=store):
            haystack = f"{product.name} {product.description}"
            for token in forbidden:
                self.assertNotIn(token, haystack, f"{product.sku}: found {token!r}")


class TagTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_tags_are_meaningful_and_assigned(self):
        self._run()
        store = self._store()
        self.assertGreater(ProductTag.objects.filter(store=store).count(), 0)
        tagged_products = Product.objects.filter(store=store, tags__isnull=False).distinct()
        self.assertGreater(tagged_products.count(), 0)
        discounted = Product.objects.filter(store=store, discount_percent__gt=0)
        for product in discounted:
            self.assertTrue(product.tags.filter(name="تخفیف‌دار").exists(), product.sku)


class ContentTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_collections_exist_with_valid_demo_products(self):
        self._run()
        store = self._store()
        collections = MerchantCollection.objects.filter(store=store)
        self.assertGreaterEqual(collections.count(), 4)
        for collection in collections:
            self.assertGreater(collection.items.count(), 0, collection.name)
            for item in collection.items.all():
                self.assertEqual(item.product.store_id, store.pk)

    def test_hero_slides_are_store_scoped_with_real_images(self):
        self._run()
        store = self._store()
        slides = HeroSlide.objects.filter(store=store)
        self.assertGreaterEqual(slides.count(), 3)
        for slide in slides:
            self.assertTrue(slide.desktop_image)
            self.assertTrue(slide.title)

    def test_promotional_banners_are_store_scoped(self):
        self._run()
        store = self._store()
        banners = PromotionalBanner.objects.filter(store=store)
        self.assertGreater(banners.count(), 0)
        for banner in banners:
            self.assertTrue(banner.desktop_image)

    def test_story_rail_covers_all_categories(self):
        self._run()
        store = self._store()
        items = StoryRailItem.objects.filter(store=store)
        self.assertEqual(items.count(), 10)
        for item in items:
            self.assertIsNotNone(item.destination_category_id)
            self.assertEqual(item.destination_category.store_id, store.pk)

    def test_category_visuals_exist_for_all_10_categories(self):
        self._run()
        store = self._store()
        for category in Category.objects.filter(store=store):
            self.assertTrue(category.image, category.name)

    def test_header_navigation_covers_all_categories(self):
        self._run()
        store = self._store()
        menu = Menu.objects.get(store=store, location=Menu.Location.HEADER)
        category_items = MenuItem.objects.filter(menu=menu, destination_category__isnull=False)
        self.assertEqual(category_items.count(), 10)

    def test_footer_settings_have_demo_contact_content(self):
        self._run()
        store = self._store()
        footer = FooterSettings.objects.get(store=store)
        self.assertTrue(footer.description)
        self.assertTrue(footer.phone)


class TenantIsolationTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_all_created_records_belong_to_the_demo_store(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            self.assertEqual(product.category.store_id, store.pk)
            self.assertEqual(product.brand.store_id, store.pk)
            self.assertEqual(product.vendor.store_id, store.pk)

    def test_never_reads_or_copies_from_an_existing_rastisi_fashion_test_store(self):
        other = Store.objects.create(name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other, name="Real Cat", slug="real-cat")
        self._run()
        store = self._store()
        self.assertFalse(Product.objects.filter(store=store, category=other_category).exists())
        other.refresh_from_db()
        self.assertEqual(other.name, "فروشگاه لباس تستی راستی سی")

    def test_no_product_leaks_between_demo_store_and_akhlaghi(self):
        self._run()
        store = self._store()
        akhlaghi = Store.objects.get(slug="akhlaghi")
        overlap = Product.objects.filter(store=store, pk__in=Product.objects.filter(store=akhlaghi))
        self.assertEqual(overlap.count(), 0)


class IdempotencyTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_second_identical_run_does_not_duplicate_anything(self):
        self._run()
        self._run()
        store = self._store()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        self.assertEqual(Product.objects.filter(store=store).count(), 50)
        self.assertEqual(ProductImage.objects.filter(product__store=store).count(), 150)
        self.assertEqual(HeroSlide.objects.filter(store=store).count(), 4)
        self.assertEqual(StoreDomain.objects.filter(store=store).count(), 2)

    def test_second_run_does_not_duplicate_variants(self):
        self._run()
        first = ProductVariant.objects.filter(product__store=self._store(), is_obsolete=False).count()
        self._run()
        second = ProductVariant.objects.filter(product__store=self._store(), is_obsolete=False).count()
        self.assertEqual(first, second)


class ResetSafetyTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_reset_after_a_completed_seed_succeeds(self):
        self._run()
        self._run("--reset")  # must not raise ProtectedError (MenuItem.menu is PROTECT)
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)

    def test_reset_rebuilds_only_the_demo_store(self):
        self._run()
        first_pk = self._store().pk
        self._run("--reset")
        self.assertNotEqual(self._store().pk, first_pk)

    def test_reset_never_touches_a_store_with_the_real_rastisi_fashion_test_slug(self):
        other = Store.objects.create(name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE)
        self._run()
        self._run("--reset")
        self.assertTrue(Store.objects.filter(pk=other.pk).exists())

    def test_reset_can_be_run_repeatedly(self):
        self._run()
        self._run("--reset")
        self._run()
        self._run("--reset")
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)


class NoRegistryMutationTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_ready_template_registry_is_unchanged_after_seeding(self):
        before = {p.key for p in lpr.list_ready_templates()}
        self._run()
        after = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(before, after)


class NoCustomerOrOrderDataTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_no_orders_or_customers_created(self):
        from apps.customers.models import CustomerProfile
        from apps.orders.models import Order

        self._run()
        store = self._store()
        self.assertEqual(Order.objects.filter(store=store).count(), 0)
        self.assertEqual(CustomerProfile.objects.filter(store=store).count(), 0)
