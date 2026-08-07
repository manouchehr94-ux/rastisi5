from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.storefront_builder.services import section_data_service
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug, *, vendor=None, category=None, status=Product.Status.ACTIVE):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=status,
    )


def _settings(**overrides):
    base = {
        "data_source": "collection", "source_id": None, "product_ids": [],
        "item_limit": 8, "display_mode": "carousel", "show_view_all": True,
        "title": "", "subtitle": "",
    }
    base.update(overrides)
    return base


class ResolveCollectionSourceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = Store.objects.create(
            name="فروشگاه دوم دیتا", slug="section-data-svc-other", admin_subdomain="section-data-svc-other",
        )

    def test_no_source_id_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _settings(source_id=None))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_deleted_or_missing_collection_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _settings(source_id=999999))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_cross_store_collection_returns_empty(self):
        other_collection = collection_service.create_collection(self.other_store, name="کالکشن فروشگاه دیگر")
        products, url = section_data_service.resolve_products(
            self.store, _settings(source_id=other_collection.pk),
        )
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_inactive_collection_returns_empty(self):
        collection = collection_service.create_collection(self.store, name="غیرفعال")
        product = _product(self.store, "coll-inactive-p1")
        collection_service.add_product(collection, product)
        collection_service.deactivate_collection(collection)
        products, url = section_data_service.resolve_products(self.store, _settings(source_id=collection.pk))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_active_collection_returns_products_in_manual_order(self):
        collection = collection_service.create_collection(self.store, name="وایر شمع")
        p1 = _product(self.store, "coll-p1")
        p2 = _product(self.store, "coll-p2")
        collection_service.add_product(collection, p1)
        collection_service.add_product(collection, p2)
        products, url = section_data_service.resolve_products(self.store, _settings(source_id=collection.pk))
        self.assertEqual([p.pk for p in products], [p1.pk, p2.pk])
        self.assertEqual(unquote(url), f"/collections/{collection.slug}/")

    def test_non_storefront_visible_product_excluded(self):
        collection = collection_service.create_collection(self.store, name="با کالای پنهان")
        visible = _product(self.store, "coll-visible")
        hidden = _product(self.store, "coll-hidden", status=Product.Status.DRAFT)
        collection_service.add_product(collection, visible)
        collection_service.add_product(collection, hidden)
        products, url = section_data_service.resolve_products(self.store, _settings(source_id=collection.pk))
        self.assertEqual([p.pk for p in products], [visible.pk])

    def test_item_limit_applied(self):
        collection = collection_service.create_collection(self.store, name="محدودیت")
        for i in range(5):
            collection_service.add_product(collection, _product(self.store, f"coll-limit-{i}"))
        products, url = section_data_service.resolve_products(
            self.store, _settings(source_id=collection.pk, item_limit=3),
        )
        self.assertEqual(len(products), 3)

    def test_unimplemented_data_source_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _settings(data_source="best_sellers"))
        self.assertEqual(products, [])
        self.assertIsNone(url)
