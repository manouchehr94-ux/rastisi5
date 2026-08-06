from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دوم کالکشن", slug="collection-second-store", admin_subdomain="collection-second-store")


class MerchantCollectionModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_unique_slug_per_store(self):
        MerchantCollection.objects.create(store=self.store, name="وایر شمع", slug="wire-shame")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MerchantCollection.objects.create(store=self.store, name="وایر شمع دو", slug="wire-shame")

    def test_same_slug_allowed_across_stores(self):
        other = _other_store()
        MerchantCollection.objects.create(store=self.store, name="وایر شمع", slug="wire-shame")
        # هیچ استثنایی نباید رخ دهد — یکتاییِ اسلاگ فقط در محدوده‌ی Store است.
        MerchantCollection.objects.create(store=other, name="وایر شمع", slug="wire-shame")
        self.assertEqual(MerchantCollection.objects.filter(slug="wire-shame").count(), 2)

    def test_collection_type_defaults_to_manual(self):
        collection = MerchantCollection.objects.create(store=self.store, name="پیشنهادی", slug="pishnahadi")
        self.assertEqual(collection.collection_type, MerchantCollection.CollectionType.MANUAL)

    def test_deleting_collection_does_not_delete_products(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="mc-vendor")
        category = Category.objects.create(store=self.store, name="دسته", slug="mc-cat")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالا", slug="mc-product",
            sku="MC-SKU-1", price=Decimal("10000"),
        )
        collection = MerchantCollection.objects.create(store=self.store, name="کالکشن", slug="mc-coll")
        MerchantCollectionItem.objects.create(collection=collection, product=product, order=0)
        collection.delete()
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())


class MerchantCollectionItemModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده آیتم", slug="mci-vendor")
        self.category = Category.objects.create(store=self.store, name="دسته آیتم", slug="mci-cat")
        self.collection = MerchantCollection.objects.create(store=self.store, name="کالکشن آیتم", slug="mci-coll")

    def _product(self, store, slug):
        vendor = Vendor.objects.filter(store=store).first() or Vendor.objects.create(store=store, name="فروشنده", slug=f"v-{slug}")
        category = Category.objects.filter(store=store).first() or Category.objects.create(store=store, name="دسته", slug=f"c-{slug}")
        return Product.objects.create(
            store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
            sku=f"SKU-{slug}", price=Decimal("10000"),
        )

    def test_unique_product_per_collection(self):
        product = self._product(self.store, "mci-p1")
        MerchantCollectionItem.objects.create(collection=self.collection, product=product, order=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MerchantCollectionItem.objects.create(collection=self.collection, product=product, order=1)

    def test_same_product_allowed_in_two_different_collections(self):
        product = self._product(self.store, "mci-p2")
        other_collection = MerchantCollection.objects.create(store=self.store, name="کالکشن دو", slug="mci-coll-2")
        MerchantCollectionItem.objects.create(collection=self.collection, product=product, order=0)
        MerchantCollectionItem.objects.create(collection=other_collection, product=product, order=0)
        self.assertEqual(MerchantCollectionItem.objects.filter(product=product).count(), 2)

    def test_deleting_product_cascades_only_its_collection_items(self):
        product = self._product(self.store, "mci-p3")
        other_product = self._product(self.store, "mci-p4")
        MerchantCollectionItem.objects.create(collection=self.collection, product=product, order=0)
        MerchantCollectionItem.objects.create(collection=self.collection, product=other_product, order=1)
        product.delete()
        self.assertFalse(MerchantCollectionItem.objects.filter(product_id=product.pk).exists())
        self.assertTrue(MerchantCollectionItem.objects.filter(product=other_product).exists())
        self.assertTrue(MerchantCollection.objects.filter(pk=self.collection.pk).exists())

    def test_clean_rejects_cross_store_product(self):
        other_store = _other_store()
        other_product = self._product(other_store, "mci-cross")
        item = MerchantCollectionItem(collection=self.collection, product=other_product, order=0)
        with self.assertRaises(Exception):
            item.clean()
