from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, ProductTag, Vendor
from apps.catalog.services.legacy_collection_migration_service import (
    apply_legacy_conversion,
    preview_legacy_conversion,
)
from apps.catalog.services.tag_service import get_or_create_collection_tag
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دوم قدیمی", slug="legacy-second-store", admin_subdomain="legacy-second-store")


def _product(store, slug, *, vendor=None, category=None):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"),
    )


class LegacyConversionServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_dry_run_creates_nothing(self):
        tag = get_or_create_collection_tag(self.store, "وایر شمع قدیمی")
        product = _product(self.store, "legacy-p1")
        product.tags.add(tag)

        report = preview_legacy_conversion(store=self.store)
        self.assertTrue(report.dry_run)
        self.assertEqual(report.created_count, 1)
        self.assertEqual(MerchantCollection.objects.count(), 0)
        self.assertTrue(ProductTag.objects.filter(pk=tag.pk).exists())  # دست‌نخورده

    def test_apply_creates_collection_and_items(self):
        tag = get_or_create_collection_tag(self.store, "وایر شمع اعمال")
        p1 = _product(self.store, "legacy-apply-1")
        p2 = _product(self.store, "legacy-apply-2")
        p1.tags.add(tag)
        p2.tags.add(tag)

        report = apply_legacy_conversion(store=self.store)
        self.assertFalse(report.dry_run)
        self.assertEqual(report.created_count, 1)
        self.assertEqual(report.total_items_created, 2)

        collection = MerchantCollection.objects.get(store=self.store, name="وایر شمع اعمال")
        self.assertEqual(collection.source_legacy_product_tag_id, tag.pk)
        self.assertEqual(collection.items.count(), 2)
        self.assertTrue(ProductTag.objects.filter(pk=tag.pk).exists())  # دست‌نخورده

    def test_skips_tag_with_no_products(self):
        get_or_create_collection_tag(self.store, "خالی قدیمی")
        report = apply_legacy_conversion(store=self.store)
        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(MerchantCollection.objects.count(), 0)

    def test_idempotent_apply_does_not_duplicate(self):
        tag = get_or_create_collection_tag(self.store, "ایدمپوتنت")
        product = _product(self.store, "legacy-idem-1")
        product.tags.add(tag)

        apply_legacy_conversion(store=self.store)
        second_report = apply_legacy_conversion(store=self.store)

        self.assertEqual(MerchantCollection.objects.filter(store=self.store).count(), 1)
        self.assertEqual(second_report.reused_count, 1)
        self.assertEqual(second_report.created_count, 0)
        self.assertEqual(second_report.total_items_created, 0)  # کالا از قبل عضو بود

    def test_idempotent_apply_syncs_newly_added_products(self):
        tag = get_or_create_collection_tag(self.store, "همگام‌سازی")
        p1 = _product(self.store, "legacy-sync-1")
        p1.tags.add(tag)
        apply_legacy_conversion(store=self.store)

        p2 = _product(self.store, "legacy-sync-2")
        p2.tags.add(tag)
        second_report = apply_legacy_conversion(store=self.store)

        self.assertEqual(second_report.reused_count, 1)
        self.assertEqual(second_report.total_items_created, 1)
        collection = MerchantCollection.objects.get(store=self.store, source_legacy_product_tag=tag)
        self.assertEqual(collection.items.count(), 2)

    def test_never_creates_cross_store_links(self):
        tag = get_or_create_collection_tag(self.store, "بدون ارتباط بین‌فروشگاهی")
        product = _product(self.store, "legacy-cross-own")
        product.tags.add(tag)
        other_store = _other_store()
        _product(other_store, "legacy-cross-foreign")  # بدون تگ — نباید هرگز دیده شود

        apply_legacy_conversion(store=self.store)
        collection = MerchantCollection.objects.get(store=self.store, source_legacy_product_tag=tag)
        for item in collection.items.all():
            self.assertEqual(item.product.store_id, self.store.pk)

    def test_slug_collision_with_manual_collection_reported_as_conflicted(self):
        from apps.catalog.services import collection_service as svc

        svc.create_collection(self.store, name="تداخل اسلاگ")
        tag = get_or_create_collection_tag(self.store, "تداخل اسلاگ")
        product = _product(self.store, "legacy-conflict-1")
        product.tags.add(tag)

        report = apply_legacy_conversion(store=self.store)
        self.assertEqual(report.conflicted_count, 1)
        # هر دو کالکشن باید مستقل باقی بمانند — هیچ‌کدام رونویسی نشده.
        self.assertEqual(MerchantCollection.objects.filter(store=self.store).count(), 2)

    def test_deterministic_product_order(self):
        tag = get_or_create_collection_tag(self.store, "ترتیب قطعی")
        p1 = _product(self.store, "legacy-order-1")
        p2 = _product(self.store, "legacy-order-2")
        p2.tags.add(tag)
        p1.tags.add(tag)  # عمداً برعکسِ ترتیبِ pk اضافه می‌شود

        apply_legacy_conversion(store=self.store)
        collection = MerchantCollection.objects.get(store=self.store, source_legacy_product_tag=tag)
        ordered_products = [item.product_id for item in collection.items.order_by("order")]
        self.assertEqual(ordered_products, sorted([p1.pk, p2.pk]))

    def test_only_active_tags_are_considered(self):
        from apps.catalog.services.tag_service import archive_tag

        tag = get_or_create_collection_tag(self.store, "آرشیوشده")
        product = _product(self.store, "legacy-archived-1")
        product.tags.add(tag)
        archive_tag(tag)

        report = apply_legacy_conversion(store=self.store)
        self.assertEqual(len(report.results), 0)
        self.assertEqual(MerchantCollection.objects.count(), 0)


class LegacyConversionCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_command_defaults_to_dry_run(self):
        tag = get_or_create_collection_tag(self.store, "دستور پیش‌فرض")
        product = _product(self.store, "legacy-cmd-1")
        product.tags.add(tag)

        out = StringIO()
        call_command("migrate_legacy_product_tag_collections", stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertEqual(MerchantCollection.objects.count(), 0)

    def test_command_apply_writes_data(self):
        tag = get_or_create_collection_tag(self.store, "دستور اعمال")
        product = _product(self.store, "legacy-cmd-apply-1")
        product.tags.add(tag)

        out = StringIO()
        call_command("migrate_legacy_product_tag_collections", "--apply", stdout=out)
        self.assertIn("APPLY", out.getvalue())
        self.assertEqual(MerchantCollection.objects.count(), 1)

    def test_command_rejects_both_flags(self):
        with self.assertRaises(CommandError):
            call_command("migrate_legacy_product_tag_collections", "--dry-run", "--apply")

    def test_command_scoped_to_single_store(self):
        other_store = _other_store()
        tag_here = get_or_create_collection_tag(self.store, "فروشگاه یک")
        tag_there = get_or_create_collection_tag(other_store, "فروشگاه دو")
        p1 = _product(self.store, "legacy-scope-1")
        p1.tags.add(tag_here)
        p2 = _product(other_store, "legacy-scope-2")
        p2.tags.add(tag_there)

        out = StringIO()
        call_command("migrate_legacy_product_tag_collections", "--apply", "--store", self.store.slug, stdout=out)
        self.assertEqual(MerchantCollection.objects.filter(store=self.store).count(), 1)
        self.assertEqual(MerchantCollection.objects.filter(store=other_store).count(), 0)

    def test_command_unknown_store_raises(self):
        with self.assertRaises(CommandError):
            call_command("migrate_legacy_product_tag_collections", "--store", "does-not-exist")
