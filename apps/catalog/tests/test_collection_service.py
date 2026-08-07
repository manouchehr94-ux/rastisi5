from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.query import QuerySet
from django.test import TestCase

from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor
from apps.catalog.services import collection_service as svc
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دوم سرویس", slug="collection-svc-second-store", admin_subdomain="collection-svc-second-store")


def _product(store, slug, *, vendor=None, category=None):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
    )


class CreateUpdateDeleteCollectionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_create_collection(self):
        collection = svc.create_collection(self.store, name="وایر شمع")
        self.assertTrue(collection.slug)
        self.assertEqual(collection.store_id, self.store.pk)
        self.assertEqual(collection.collection_type, MerchantCollection.CollectionType.MANUAL)

    def test_create_rejects_blank_name(self):
        with self.assertRaises(svc.CollectionError):
            svc.create_collection(self.store, name="   ")

    def test_create_slug_collision_gets_suffixed(self):
        first = svc.create_collection(self.store, name="پیشنهاد ویژه")
        second = svc.create_collection(self.store, name="پیشنهاد ویژه")
        self.assertNotEqual(first.slug, second.slug)

    def test_update_collection_does_not_change_slug(self):
        collection = svc.create_collection(self.store, name="نام اول")
        original_slug = collection.slug
        updated = svc.update_collection(collection, name="نام دوم کاملاً متفاوت")
        self.assertEqual(updated.slug, original_slug)
        self.assertEqual(updated.name, "نام دوم کاملاً متفاوت")

    def test_update_rejects_blank_name(self):
        collection = svc.create_collection(self.store, name="نام معتبر")
        with self.assertRaises(svc.CollectionError):
            svc.update_collection(collection, name="")

    def test_delete_collection_removes_only_items(self):
        collection = svc.create_collection(self.store, name="حذف‌شونده")
        product = _product(self.store, "del-p1")
        svc.add_product(collection, product)
        svc.delete_collection(collection)
        self.assertFalse(MerchantCollection.objects.filter(pk=collection.pk).exists())
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_activate_deactivate(self):
        collection = svc.create_collection(self.store, name="فعال‌سازی")
        svc.deactivate_collection(collection)
        collection.refresh_from_db()
        self.assertFalse(collection.is_active)
        svc.activate_collection(collection)
        collection.refresh_from_db()
        self.assertTrue(collection.is_active)


class ScopedCollectionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = _other_store()

    def test_get_scoped_collection_success(self):
        collection = svc.create_collection(self.store, name="محدود")
        found = svc.get_scoped_collection(self.store, collection.pk)
        self.assertEqual(found.pk, collection.pk)

    def test_get_scoped_collection_cross_store_rejected(self):
        collection = svc.create_collection(self.other_store, name="فروشگاه دیگر")
        with self.assertRaises(svc.CollectionNotFoundError):
            svc.get_scoped_collection(self.store, collection.pk)

    def test_get_scoped_collection_missing_rejected(self):
        with self.assertRaises(svc.CollectionNotFoundError):
            svc.get_scoped_collection(self.store, 999999)


class AddRemoveProductTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = _other_store()
        self.collection = svc.create_collection(self.store, name="افزودن کالا")

    def test_add_product(self):
        product = _product(self.store, "add-p1")
        item = svc.add_product(self.collection, product)
        self.assertEqual(item.order, 0)
        second = _product(self.store, "add-p2")
        item2 = svc.add_product(self.collection, second)
        self.assertEqual(item2.order, 1)

    def test_add_duplicate_product_rejected(self):
        product = _product(self.store, "add-dup")
        svc.add_product(self.collection, product)
        with self.assertRaises(svc.DuplicateProductError):
            svc.add_product(self.collection, product)
        self.assertEqual(MerchantCollectionItem.objects.filter(collection=self.collection, product=product).count(), 1)

    def test_add_cross_store_product_rejected(self):
        foreign_product = _product(self.other_store, "add-cross")
        with self.assertRaises(svc.ProductNotFoundError):
            svc.add_product(self.collection, foreign_product)
        self.assertEqual(MerchantCollectionItem.objects.filter(collection=self.collection).count(), 0)

    def test_add_products_bulk_skips_duplicates_and_cross_store(self):
        p1 = _product(self.store, "bulk-p1")
        p2 = _product(self.store, "bulk-p2")
        foreign = _product(self.other_store, "bulk-cross")
        svc.add_product(self.collection, p1)  # already a member
        created = svc.add_products(self.collection, [p1, p2, foreign])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].product_id, p2.pk)
        self.assertEqual(MerchantCollectionItem.objects.filter(collection=self.collection).count(), 2)

    def test_remove_product(self):
        product = _product(self.store, "remove-p1")
        item = svc.add_product(self.collection, product)
        svc.remove_product(self.collection, item.pk)
        self.assertFalse(MerchantCollectionItem.objects.filter(pk=item.pk).exists())

    def test_remove_product_not_in_collection_rejected(self):
        other_collection = svc.create_collection(self.store, name="کالکشن دیگر")
        product = _product(self.store, "remove-cross")
        item = svc.add_product(other_collection, product)
        with self.assertRaises(svc.ProductNotFoundError):
            svc.remove_product(self.collection, item.pk)


class ReorderItemsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.collection = svc.create_collection(self.store, name="ترتیب")
        self.i1 = svc.add_product(self.collection, _product(self.store, "reorder-p1"))
        self.i2 = svc.add_product(self.collection, _product(self.store, "reorder-p2"))
        self.i3 = svc.add_product(self.collection, _product(self.store, "reorder-p3"))

    def test_reorders_by_posted_id_sequence(self):
        svc.reorder_items(self.collection, [self.i3.pk, self.i1.pk, self.i2.pk])
        self.i1.refresh_from_db()
        self.i2.refresh_from_db()
        self.i3.refresh_from_db()
        self.assertEqual(self.i3.order, 0)
        self.assertEqual(self.i1.order, 1)
        self.assertEqual(self.i2.order, 2)

    def test_duplicate_ids_rejected_no_rows_changed(self):
        original = {i.pk: i.order for i in [self.i1, self.i2, self.i3]}
        with self.assertRaises(svc.CollectionReorderError):
            svc.reorder_items(self.collection, [self.i1.pk, self.i1.pk, self.i2.pk])
        for item in [self.i1, self.i2, self.i3]:
            item.refresh_from_db()
            self.assertEqual(item.order, original[item.pk])

    def test_foreign_ids_are_ignored(self):
        other_collection = svc.create_collection(self.store, name="ترتیب دیگر")
        foreign_item = svc.add_product(other_collection, _product(self.store, "reorder-foreign"))
        svc.reorder_items(self.collection, [self.i2.pk, foreign_item.pk, self.i1.pk])
        foreign_item.refresh_from_db()
        self.assertEqual(foreign_item.order, 0)  # دست‌نخورده

    def test_missing_ids_keep_current_order(self):
        svc.reorder_items(self.collection, [self.i2.pk, self.i1.pk])
        self.i3.refresh_from_db()
        self.assertEqual(self.i3.order, 2)

    def test_mid_operation_failure_rolls_back_completely(self):
        original_order = {i.pk: i.order for i in [self.i1, self.i2, self.i3]}
        original_update = QuerySet.update
        call_count = {"n": 0}

        def flaky_update(self_qs, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated mid-operation failure")
            return original_update(self_qs, *args, **kwargs)

        with patch.object(QuerySet, "update", flaky_update):
            with self.assertRaises(RuntimeError):
                svc.reorder_items(self.collection, [self.i3.pk, self.i1.pk, self.i2.pk])

        for item in [self.i1, self.i2, self.i3]:
            item.refresh_from_db()
            self.assertEqual(item.order, original_order[item.pk])


class PublicQuerysetTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_public_queryset_excludes_inactive(self):
        active = svc.create_collection(self.store, name="فعال")
        inactive = svc.create_collection(self.store, name="غیرفعال")
        svc.deactivate_collection(inactive)
        results = list(svc.public_collection_queryset(self.store))
        self.assertIn(active, results)
        self.assertNotIn(inactive, results)

    def test_public_queryset_excludes_other_store(self):
        other_store = _other_store()
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر")
        results = list(svc.public_collection_queryset(self.store))
        self.assertNotIn(other_collection, results)

    def test_collection_visible_items_excludes_non_storefront_visible_products(self):
        collection = svc.create_collection(self.store, name="نمایش")
        visible = _product(self.store, "visible-p1")
        hidden = _product(self.store, "hidden-p1")
        hidden.status = Product.Status.DRAFT
        hidden.save(update_fields=["status"])
        svc.add_product(collection, visible)
        svc.add_product(collection, hidden)
        items = list(svc.collection_visible_items(collection, self.store))
        product_ids = [item.product_id for item in items]
        self.assertIn(visible.pk, product_ids)
        self.assertNotIn(hidden.pk, product_ids)


class SearchableProductsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_excludes_draft_placeholder(self):
        real = _product(self.store, "search-real")
        placeholder = _product(self.store, "search-placeholder")
        placeholder.is_draft_placeholder = True
        placeholder.save(update_fields=["is_draft_placeholder"])
        results = list(svc.searchable_products(self.store))
        self.assertIn(real, results)
        self.assertNotIn(placeholder, results)

    def test_includes_inactive_and_draft_products(self):
        draft = _product(self.store, "search-draft")
        draft.status = Product.Status.DRAFT
        draft.save(update_fields=["status"])
        results = list(svc.searchable_products(self.store))
        self.assertIn(draft, results)

    def test_query_filters_by_name_or_sku(self):
        _product(self.store, "search-alpha")
        beta = _product(self.store, "search-beta")
        results = list(svc.searchable_products(self.store, query="SKU-search-beta"))
        self.assertEqual(list(results), [beta])

    def test_query_excludes_other_store(self):
        other_store = _other_store()
        _product(other_store, "search-foreign")
        results = list(svc.searchable_products(self.store))
        self.assertEqual(len(results), 0)
