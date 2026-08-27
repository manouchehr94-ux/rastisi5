from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.catalog.services.product_image_service import add_product_image
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


def _manual_settings(**overrides):
    return _settings(data_source="manual", **overrides)


class ResolveManualSourceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.other_store = Store.objects.create(
            name="فروشگاه دوم دیتا دستی", slug="section-data-svc-manual-other", admin_subdomain="section-data-svc-manual-other",
        )

    def test_no_product_ids_returns_empty(self):
        products, url = section_data_service.resolve_products(self.store, _manual_settings(product_ids=[]))
        self.assertEqual(products, [])
        self.assertIsNone(url)

    def test_products_returned_in_manual_order_not_db_order(self):
        p1 = _product(self.store, "sec-man-p1")
        p2 = _product(self.store, "sec-man-p2")
        p3 = _product(self.store, "sec-man-p3")
        products, url = section_data_service.resolve_products(
            self.store, _manual_settings(product_ids=[p3.pk, p1.pk, p2.pk]),
        )
        self.assertEqual([p.pk for p in products], [p3.pk, p1.pk, p2.pk])
        self.assertIsNone(url)

    def test_cross_store_product_excluded(self):
        vendor = Vendor.objects.create(store=self.other_store, name="فروشنده دیگر دستی", slug="v-manual-other")
        category = Category.objects.create(store=self.other_store, name="دسته دیگر دستی", slug="c-manual-other")
        other_product = Product.objects.create(
            store=self.other_store, vendor=vendor, category=category, name="کالای فروشگاه دیگر",
            slug="manual-other-p1", sku="SKU-MANUAL-OTHER-1", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        own_product = _product(self.store, "sec-man-own")
        products, url = section_data_service.resolve_products(
            self.store, _manual_settings(product_ids=[other_product.pk, own_product.pk]),
        )
        self.assertEqual([p.pk for p in products], [own_product.pk])

    def test_deleted_or_missing_product_excluded(self):
        p1 = _product(self.store, "sec-man-existing")
        products, url = section_data_service.resolve_products(
            self.store, _manual_settings(product_ids=[999999, p1.pk]),
        )
        self.assertEqual([p.pk for p in products], [p1.pk])

    def test_non_storefront_visible_product_excluded(self):
        hidden = _product(self.store, "sec-man-hidden", status=Product.Status.DRAFT)
        visible = _product(self.store, "sec-man-visible")
        products, url = section_data_service.resolve_products(
            self.store, _manual_settings(product_ids=[hidden.pk, visible.pk]),
        )
        self.assertEqual([p.pk for p in products], [visible.pk])

    def test_item_limit_applied_after_ordering(self):
        products_created = [_product(self.store, f"sec-man-limit-{i}") for i in range(5)]
        ordered_ids = [p.pk for p in reversed(products_created)]
        products, url = section_data_service.resolve_products(
            self.store, _manual_settings(product_ids=ordered_ids, item_limit=2),
        )
        self.assertEqual([p.pk for p in products], ordered_ids[:2])


def _png(name="test.png"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (400, 400), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class ResolveCategoryRepresentativeMediaTests(TestCase):
    """Micro-fix pass: the category mosaic must show a real per-product
    cover image (edge-to-edge) instead of ``Category.image`` (a
    deliberately composed thumbnail with baked-in colored margins — see
    ``section_data_service.resolve_category_representative_media``'s own
    docstring for the full root-cause). Generic/ID-free: only
    already-resolved Category objects go in, only real, currently
    storefront-visible Products come out."""

    def setUp(self):
        self.store = _akhlaghi()
        self.category = Category.objects.create(store=self.store, name="دسته موزاییک", slug="mosaic-cat")

    def test_no_products_returns_none(self):
        self.assertIsNone(section_data_service.resolve_category_representative_media(self.category))

    def test_returns_cover_image_of_a_real_product_in_category(self):
        product = _product(self.store, "mosaic-p1", category=self.category)
        image = add_product_image(product, _png())
        media = section_data_service.resolve_category_representative_media(self.category)
        self.assertEqual(media.pk, image.pk)

    def test_subcategory_product_counts_as_representative(self):
        child = Category.objects.create(store=self.store, name="زیردسته موزاییک", slug="mosaic-cat-child", parent=self.category)
        product = _product(self.store, "mosaic-child-p1", category=child)
        image = add_product_image(product, _png())
        media = section_data_service.resolve_category_representative_media(self.category)
        self.assertEqual(media.pk, image.pk)

    def test_product_with_no_images_returns_none(self):
        _product(self.store, "mosaic-no-image", category=self.category)
        self.assertIsNone(section_data_service.resolve_category_representative_media(self.category))

    def test_non_storefront_visible_product_excluded(self):
        _product(self.store, "mosaic-hidden", category=self.category, status=Product.Status.DRAFT)
        self.assertIsNone(section_data_service.resolve_category_representative_media(self.category))

    def test_cross_store_category_products_never_leak(self):
        other_store = Store.objects.create(
            name="فروشگاه دوم موزاییک", slug="section-data-svc-mosaic-other", admin_subdomain="section-data-svc-mosaic-other",
        )
        other_category = Category.objects.create(store=other_store, name="دسته فروشگاه دیگر موزاییک", slug="mosaic-other-cat")
        other_product = _product(other_store, "mosaic-other-p1", category=other_category)
        add_product_image(other_product, _png())
        self.assertIsNone(section_data_service.resolve_category_representative_media(self.category))
