"""Django tests for ``seed_ready_template_fashion_demo`` — Phase 1 (Deterministic
Data Foundation) of «Ready Template Demo Fashion Store».

Proves the exact data-shape contract from the mission (50 products / 10
categories / 6 brands / exact discount, stock-state, multi-color and
sizing counts), that stock semantics for ``PARTIAL_VARIANT_STOCK`` and
``OUT_OF_STOCK`` use the real Attribute/Option/Variant + Product.stock
inventory architecture (not a display-only flag), tenant isolation and
``--reset`` safety against an unrelated Store (including one sharing the
real ``rastisi-fashion-test`` slug), idempotency, and the no-mutation
contract against the Ready Template registry.

MEDIA_ROOT is overridden to a temporary directory (same pattern as
``test_seed_rastisi_fashion_demo_command.py``) so the generated synthetic
placeholder images are never written under the real project ``media/``.
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
    ProductVariant,
)
from apps.storefront_builder import layout_preset_registry as lpr
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
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
        updated_before = akhlaghi_before.updated_at
        self._run()
        akhlaghi_after = Store.objects.get(slug="akhlaghi")
        self.assertEqual(akhlaghi_after.name, name_before)
        self.assertEqual(akhlaghi_after.updated_at, updated_before)

    def test_store_domain_is_verified(self):
        self._run()
        store = self._store()
        domain = StoreDomain.objects.get(store=store, is_primary=True)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertIsNotNone(domain.verified_at)


class ExactCountTests(SeedReadyTemplateFashionDemoCommandTests):
    """"Do not silently change these counts" — the mission's own enumerated
    contract, verified directly against the live database."""

    def test_exactly_50_products(self):
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)

    def test_exactly_10_categories(self):
        self._run()
        self.assertEqual(Category.objects.filter(store=self._store()).count(), 10)

    def test_exactly_5_products_per_category(self):
        self._run()
        store = self._store()
        for category in Category.objects.filter(store=store):
            self.assertEqual(Product.objects.filter(store=store, category=category).count(), 5, category.name)

    def test_exactly_6_brands(self):
        self._run()
        self.assertEqual(Brand.objects.filter(store=self._store()).count(), 6)

    def test_exactly_10_fully_out_of_stock_products(self):
        self._run()
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store, stock=0).count(), 10)

    def test_exactly_22_discounted_and_28_non_discounted(self):
        self._run()
        store = self._store()
        products = Product.objects.filter(store=store)
        self.assertEqual(products.filter(discount_percent__gt=0).count(), 22)
        self.assertEqual(products.filter(discount_percent=0).count(), 28)

    def test_exactly_20_multi_color_and_30_single_color(self):
        self._run()
        store = self._store()
        multi, single = 0, 0
        for product in Product.objects.filter(store=store):
            color_option = product.options.filter(label="رنگ", is_active=True).first()
            n_colors = color_option.values.filter(is_active=True).count() if color_option else 0
            if n_colors > 1:
                multi += 1
            else:
                single += 1
        self.assertEqual(multi, 20)
        self.assertEqual(single, 30)

    def test_exactly_35_broad_sizing_and_15_limited_sizing(self):
        self._run()
        store = self._store()
        broad, limited = 0, 0
        for product in Product.objects.filter(store=store):
            size_option = product.options.filter(label="سایز", is_active=True).first()
            n_sizes = size_option.values.filter(is_active=True).count() if size_option else 0
            if n_sizes >= 4:
                broad += 1
            else:
                limited += 1
        self.assertEqual(broad, 35)
        self.assertEqual(limited, 15)

    def test_exactly_150_product_images(self):
        self._run()
        store = self._store()
        self.assertEqual(ProductImage.objects.filter(product__store=store).count(), 150)

    def test_exactly_4_collections(self):
        self._run()
        store = self._store()
        self.assertEqual(MerchantCollection.objects.filter(store=store).count(), 4)


class StockSemanticsTests(SeedReadyTemplateFashionDemoCommandTests):
    """Proves stock states use the real variant/inventory architecture, not
    a display-only flag — exactly what the mission demands verbatim."""

    def test_partial_variant_stock_products_remain_purchasable_with_one_dead_combination(self):
        self._run()
        store = self._store()
        for code, *_rest, stock_state in PRODUCT_MATRIX:
            if stock_state != PARTIAL_VARIANT_STOCK:
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertGreater(product.stock, 0, code)
            variants = list(product.variants.filter(is_obsolete=False))
            self.assertTrue(any(v.stock == 0 for v in variants), f"{code}: no zero-stock combination")
            self.assertTrue(any(v.stock > 0 for v in variants), f"{code}: no purchasable combination")

    def test_out_of_stock_products_have_zero_stock_on_product_and_every_variant(self):
        self._run()
        store = self._store()
        for code, *_rest, stock_state in PRODUCT_MATRIX:
            if stock_state != OUT_OF_STOCK:
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertEqual(product.stock, 0, code)
            variants = list(product.variants.filter(is_obsolete=False))
            self.assertTrue(variants, code)
            self.assertTrue(all(v.stock == 0 for v in variants), f"{code}: a variant still has stock")

    def test_in_stock_products_are_purchasable_on_every_combination(self):
        self._run()
        store = self._store()
        for code, *_rest, stock_state in PRODUCT_MATRIX:
            if stock_state not in ("IN_STOCK",):
                continue
            product = Product.objects.get(store=store, sku=code)
            self.assertGreater(product.stock, 0, code)
            variants = list(product.variants.filter(is_obsolete=False))
            self.assertTrue(all(v.stock > 0 for v in variants), code)

    def test_variants_use_real_combination_keys_not_single_axis_rows(self):
        self._run()
        store = self._store()
        product = Product.objects.get(store=store, sku="FSH-001")
        variants = list(product.variants.filter(is_obsolete=False))
        self.assertEqual(len(variants), 3 * 5)  # 3 colors x 5 sizes
        for variant in variants:
            self.assertTrue(variant.combination_key)
            self.assertIn(" / ", variant.value)

    def test_product_stock_equals_sum_of_variant_stocks(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            total = sum(v.stock for v in product.variants.filter(is_obsolete=False))
            self.assertEqual(product.stock, total, product.sku)


class MediaAndColorMappingTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_every_product_has_exactly_3_images(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            self.assertEqual(product.images.count(), 3, product.sku)

    def test_multi_color_products_get_color_driven_image_mapping(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            color_option = product.options.filter(label="رنگ", is_active=True).first()
            n_colors = color_option.values.filter(is_active=True).count() if color_option else 0
            if n_colors <= 1:
                continue
            mapped = product.images.filter(option_value__isnull=False).count()
            self.assertGreaterEqual(mapped, min(3, n_colors), product.sku)

    def test_no_external_retailer_urls_anywhere_in_demo_data(self):
        self._run()
        store = self._store()
        forbidden = ("zara.com", "zalando", "asos.com", "farfetch", "http://", "https://")
        for product in Product.objects.filter(store=store):
            haystack = f"{product.name} {product.description}"
            for token in forbidden:
                self.assertNotIn(token, haystack, f"{product.sku}: found {token!r}")
        for image in ProductImage.objects.filter(product__store=store):
            for token in forbidden:
                self.assertNotIn(token, image.alt or "", f"image {image.pk}: found {token!r} in alt")


class CollectionContentTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_expected_collection_names_exist(self):
        self._run()
        store = self._store()
        names = set(MerchantCollection.objects.filter(store=store).values_list("name", flat=True))
        self.assertEqual(
            names, {"جدیدترین‌ها", "پرفروش‌ها", "تخفیف‌های منتخب", "انتخاب فصل"},
        )

    def test_collections_only_reference_demo_store_products(self):
        self._run()
        store = self._store()
        for collection in MerchantCollection.objects.filter(store=store):
            for item in collection.items.all():
                self.assertEqual(item.product.store_id, store.pk)

    def test_discount_collection_contains_exactly_the_discounted_products(self):
        self._run()
        store = self._store()
        collection = MerchantCollection.objects.get(store=store, name="تخفیف‌های منتخب")
        member_skus = set(p.sku for p in Product.objects.filter(pk__in=collection.items.values("product_id")))
        discounted_skus = set(
            Product.objects.filter(store=store, discount_percent__gt=0).values_list("sku", flat=True)
        )
        self.assertEqual(member_skus, discounted_skus)


class TenantIsolationTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_all_created_records_belong_to_the_demo_store(self):
        self._run()
        store = self._store()
        for product in Product.objects.filter(store=store):
            self.assertEqual(product.category.store_id, store.pk)
            self.assertEqual(product.brand.store_id, store.pk)
            self.assertEqual(product.vendor.store_id, store.pk)

    def test_never_reads_or_copies_from_an_existing_rastisi_fashion_test_store(self):
        """The mission's explicit prohibition: never touch/read from a Store
        with the real ``rastisi-fashion-test`` slug, even if one exists."""
        other = Store.objects.create(name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other, name="Real Cat", slug="real-cat")
        other_brand = Brand.objects.create(store=other, name="Real Brand", slug="real-brand")

        self._run()

        store = self._store()
        self.assertFalse(Product.objects.filter(store=store, category=other_category).exists())
        self.assertFalse(Product.objects.filter(store=store, brand=other_brand).exists())
        other.refresh_from_db()
        self.assertEqual(other.name, "فروشگاه لباس تستی راستی سی")

    def test_no_product_leaks_between_demo_store_and_akhlaghi(self):
        self._run()
        store = self._store()
        akhlaghi = Store.objects.get(slug="akhlaghi")
        overlap = Product.objects.filter(store=store, pk__in=Product.objects.filter(store=akhlaghi))
        self.assertEqual(overlap.count(), 0)


class IdempotencyTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_first_run_succeeds(self):
        self._run()
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)

    def test_second_identical_run_does_not_duplicate_anything(self):
        self._run()
        self._run()
        store = self._store()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        self.assertEqual(Product.objects.filter(store=store).count(), 50)
        self.assertEqual(Category.objects.filter(store=store).count(), 10)
        self.assertEqual(Brand.objects.filter(store=store).count(), 6)
        self.assertEqual(ProductImage.objects.filter(product__store=store).count(), 150)
        self.assertEqual(MerchantCollection.objects.filter(store=store).count(), 4)

    def test_second_run_does_not_duplicate_variants(self):
        self._run()
        first_count = ProductVariant.objects.filter(product__store=self._store(), is_obsolete=False).count()
        self._run()
        second_count = ProductVariant.objects.filter(product__store=self._store(), is_obsolete=False).count()
        self.assertEqual(first_count, second_count)

    def test_many_reruns_preserve_exact_stock_semantics(self):
        for _ in range(3):
            self._run()
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store, stock=0).count(), 10)
        self.assertEqual(Product.objects.filter(store=store, discount_percent__gt=0).count(), 22)


class ResetSafetyTests(SeedReadyTemplateFashionDemoCommandTests):
    """Checkpoint: --reset must succeed against the real, PROTECT-heavy
    model graph (ProductOption/ProductOptionValue/VariantOptionValue), and
    must never be able to target any other Store."""

    def test_reset_after_a_completed_seed_succeeds(self):
        self._run()
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)
        self._run("--reset")  # must not raise ProtectedError
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_reset_rebuilds_only_the_demo_store(self):
        self._run()
        first_pk = self._store().pk
        self._run("--reset")
        new_store = self._store()
        self.assertNotEqual(new_store.pk, first_pk)
        self.assertEqual(Product.objects.filter(store=new_store).count(), 50)

    def test_reset_on_a_never_seeded_database_does_not_error(self):
        self._run("--reset")
        self.assertTrue(Store.objects.filter(slug=STORE_SLUG).exists())

    def test_reset_never_touches_a_store_with_the_real_rastisi_fashion_test_slug(self):
        other = Store.objects.create(name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE)
        other_vendor_name_before = other.name

        self._run()
        self._run("--reset")

        other.refresh_from_db()
        self.assertEqual(other.name, other_vendor_name_before)
        self.assertTrue(Store.objects.filter(pk=other.pk).exists())

    def test_reset_never_deletes_an_unrelated_store_or_its_catalog(self):
        from apps.catalog.models import Vendor

        other = Store.objects.create(name="Store Unrelated", slug="unrelated-store-srtfd", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other, name="Other Vendor", slug="other-vendor-srtfd")
        other_category = Category.objects.create(store=other, name="Other Cat", slug="other-cat-srtfd")
        other_product = Product.objects.create(
            store=other, vendor=other_vendor, category=other_category, name="Other Product",
            slug="other-product-srtfd", sku="OTHER-SRTFD-1", price=1000, stock=1,
        )

        self._run()
        self._run("--reset")

        self.assertTrue(Store.objects.filter(pk=other.pk).exists())
        self.assertTrue(Category.objects.filter(pk=other_category.pk).exists())
        self.assertTrue(Product.objects.filter(pk=other_product.pk).exists())

    def test_reset_can_be_run_repeatedly(self):
        self._run()
        self._run("--reset")
        self._run()
        self._run("--reset")
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        self.assertEqual(Product.objects.filter(store=self._store()).count(), 50)

    def test_reset_removes_demo_store_products_categories_and_variants(self):
        self._run()
        store_pk = self._store().pk
        self._run("--reset")
        self.assertFalse(Store.objects.filter(pk=store_pk).exists())
        self.assertFalse(Product.objects.filter(store_id=store_pk).exists())
        self.assertFalse(Category.objects.filter(store_id=store_pk).exists())
        self.assertFalse(ProductVariant.objects.filter(store_id=store_pk).exists())

    def test_reset_argument_accepts_no_store_target_and_cannot_be_redirected(self):
        """Structural guarantee: there is no CLI argument to redirect --reset
        at a different Store — passing an unrecognized extra argument must
        be rejected by argparse rather than silently accepted."""
        from django.core.management.base import CommandError as DjangoCommandError

        with self.assertRaises((DjangoCommandError, SystemExit)):
            call_command(
                "seed_ready_template_fashion_demo", "--reset", "--target-store", "akhlaghi", stdout=StringIO(),
            )
        # akhlaghi must still exist untouched regardless of the rejected call.
        self.assertTrue(Store.objects.filter(slug="akhlaghi").exists())


class NoRegistryMutationTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_ready_template_registry_is_unchanged_after_seeding(self):
        before = {p.key for p in lpr.list_ready_templates()}
        self._run()
        after = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(before, after)

    def test_no_storefront_layout_apply_publish_side_effect(self):
        """The command must not Apply/Publish a Ready Template on the demo
        store as a side effect — this phase is data-foundation only."""
        from apps.storefront_builder.models import StorefrontLayout

        self._run()
        store = self._store()
        self.assertFalse(StorefrontLayout.objects.filter(store=store, published_version__isnull=False).exists())


class NoCustomerOrOrderDataTests(SeedReadyTemplateFashionDemoCommandTests):
    def test_no_orders_or_customers_created(self):
        from apps.customers.models import CustomerProfile
        from apps.orders.models import Order

        self._run()
        store = self._store()
        self.assertEqual(Order.objects.filter(store=store).count(), 0)
        self.assertEqual(CustomerProfile.objects.filter(store=store).count(), 0)
