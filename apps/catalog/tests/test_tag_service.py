from django.test import TestCase

from apps.catalog.models import Category, Product, ProductTag, Vendor
from apps.catalog.services.tag_service import archive_tag, get_or_create_tags, suggest_tags
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GetOrCreateTagsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_creates_new_tags(self):
        tags = get_or_create_tags(self.store, ["نخی", "مردانه"])
        self.assertEqual(len(tags), 2)
        self.assertEqual(ProductTag.objects.filter(store=self.store).count(), 2)

    def test_reuses_existing_tag_by_normalized_name(self):
        first = get_or_create_tags(self.store, ["تابستانی"])[0]
        second = get_or_create_tags(self.store, ["تابستانی"])[0]
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ProductTag.objects.filter(store=self.store).count(), 1)

    def test_reactivates_archived_tag_instead_of_duplicating(self):
        tag = get_or_create_tags(self.store, ["حراج"])[0]
        archive_tag(tag)
        tag.refresh_from_db()
        self.assertFalse(tag.is_active)

        reused = get_or_create_tags(self.store, ["حراج"])[0]
        self.assertEqual(reused.pk, tag.pk)
        reused.refresh_from_db()
        self.assertTrue(reused.is_active)
        self.assertEqual(ProductTag.objects.filter(store=self.store).count(), 1)

    def test_blank_and_whitespace_entries_ignored(self):
        tags = get_or_create_tags(self.store, ["", "   ", "واقعی"])
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].name, "واقعی")

    def test_tags_are_store_scoped(self):
        other_store = Store.objects.create(name="B", slug="tag-store-b", status=Store.Status.ACTIVE)
        get_or_create_tags(self.store, ["مشترک"])
        get_or_create_tags(other_store, ["مشترک"])
        self.assertEqual(ProductTag.objects.filter(store=self.store).count(), 1)
        self.assertEqual(ProductTag.objects.filter(store=other_store).count(), 1)


class SuggestTagsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        get_or_create_tags(self.store, ["نخی", "پشمی", "پلی‌استر"])

    def test_filters_by_query(self):
        results = list(suggest_tags(self.store, "نخی"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "نخی")

    def test_excludes_archived_tags(self):
        tag = ProductTag.objects.get(store=self.store, name="پشمی")
        archive_tag(tag)
        results = [t.name for t in suggest_tags(self.store)]
        self.assertNotIn("پشمی", results)

    def test_empty_query_returns_all_active(self):
        results = list(suggest_tags(self.store))
        self.assertEqual(len(results), 3)


class ProductTagsAssignmentTests(TestCase):
    def test_product_tags_m2m_works(self):
        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-pta")
        category = Category.objects.create(store=store, name="دسته", slug="cat-pta")
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالا", slug="product-pta",
            sku="SKU-PTA1", price=100000,
        )
        tags = get_or_create_tags(store, ["نو", "پرفروش"])
        product.tags.set(tags)
        self.assertEqual(product.tags.count(), 2)
        self.assertEqual(tags[0].products.first(), product)
