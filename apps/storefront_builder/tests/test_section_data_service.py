from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, Vendor
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


def _category_settings(**overrides):
    return _settings(data_source="category", **overrides)


def _brand_settings(**overrides):
    return _settings(data_source="brand", **overrides)


class ResolveCategorySourceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = Store.objects.create(
            name="فروشگاه دوم دیتا کتگوری", slug="section-data-svc-cat-other", admin_subdomain="section-data-svc-cat-other",
        )
        self.category = Category.objects.create(store=self.store, name="لوازم برقی سکشن", slug="sec-cat-electric")

    def test_no_source_id_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _category_settings(source_id=None))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_missing_category_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _category_settings(source_id=999999))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_cross_store_category_returns_empty(self):
        other_category = Category.objects.create(store=self.other_store, name="دسته فروشگاه دیگر", slug="other-cat")
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=other_category.pk),
        )
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_inactive_category_returns_empty(self):
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=self.category.pk),
        )
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_direct_category_products_returned(self):
        product = _product(self.store, "sec-cat-p1", category=self.category)
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=self.category.pk),
        )
        self.assertEqual([p.pk for p in products], [product.pk])
        self.assertEqual(unquote(url), f"/products/?category={self.category.slug}")

    def test_parent_category_includes_child_products(self):
        child = Category.objects.create(store=self.store, name="زیردسته سکشن", slug="sec-cat-child", parent=self.category)
        product = _product(self.store, "sec-cat-child-p1", category=child)
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=self.category.pk),
        )
        self.assertEqual([p.pk for p in products], [product.pk])

    def test_non_storefront_visible_product_excluded(self):
        _product(self.store, "sec-cat-hidden", category=self.category, status=Product.Status.DRAFT)
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=self.category.pk),
        )
        self.assertEqual(products, [])

    def test_item_limit_applied(self):
        for i in range(5):
            _product(self.store, f"sec-cat-limit-{i}", category=self.category)
        products, url = section_data_service.resolve_products(
            self.store, _category_settings(source_id=self.category.pk, item_limit=3),
        )
        self.assertEqual(len(products), 3)


class ResolveBrandSourceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = Store.objects.create(
            name="فروشگاه دوم دیتا برند", slug="section-data-svc-brand-other", admin_subdomain="section-data-svc-brand-other",
        )
        self.brand = Brand.objects.create(store=self.store, name="برند سکشن", slug="sec-brand-1")

    def test_no_source_id_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _brand_settings(source_id=None))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_missing_brand_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _brand_settings(source_id=999999))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_cross_store_brand_returns_empty(self):
        other_brand = Brand.objects.create(store=self.other_store, name="برند دیگر", slug="other-brand")
        products, url = section_data_service.resolve_products(self.store, _brand_settings(source_id=other_brand.pk))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_inactive_brand_returns_empty(self):
        self.brand.is_active = False
        self.brand.save(update_fields=["is_active"])
        products, url = section_data_service.resolve_products(self.store, _brand_settings(source_id=self.brand.pk))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_brand_products_returned(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده برند سکشن", slug="v-sec-brand")
        category = Category.objects.create(store=self.store, name="دسته برند سکشن", slug="c-sec-brand")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, brand=self.brand, name="کالای برند سکشن",
            slug="sec-brand-p1", sku="SKU-SEC-BRAND-1", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        products, url = section_data_service.resolve_products(self.store, _brand_settings(source_id=self.brand.pk))
        self.assertEqual([p.pk for p in products], [product.pk])
        self.assertEqual(unquote(url), f"/products/?brand={self.brand.slug}")

    def test_item_limit_applied(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده برند محدودیت", slug="v-sec-brand-limit")
        category = Category.objects.create(store=self.store, name="دسته برند محدودیت", slug="c-sec-brand-limit")
        for i in range(5):
            Product.objects.create(
                store=self.store, vendor=vendor, category=category, brand=self.brand, name=f"کالای برند {i}",
                slug=f"sec-brand-limit-{i}", sku=f"SKU-SEC-BRAND-LIMIT-{i}", price=Decimal("10000"),
                status=Product.Status.ACTIVE,
            )
        products, url = section_data_service.resolve_products(
            self.store, _brand_settings(source_id=self.brand.pk, item_limit=3),
        )
        self.assertEqual(len(products), 3)
