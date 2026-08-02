from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Vendor
from apps.catalog.services.product_completion_service import build_completion_checklist, completion_percent
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProductCompletionServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pcs")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pcs")

    def test_minimal_draft_product_is_partially_complete(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای ناقص",
            slug="incomplete-pcs", sku="SKU-PCS1", price=Decimal("100000"), status=Product.Status.DRAFT,
        )
        checklist = {item.key: item.done for item in build_completion_checklist(product)}
        self.assertTrue(checklist["title"])
        self.assertTrue(checklist["category"])
        self.assertTrue(checklist["price"])
        self.assertFalse(checklist["cover_image"])
        self.assertFalse(checklist["inventory"])
        self.assertFalse(checklist["seo"])
        self.assertFalse(checklist["status"])
        self.assertLess(completion_percent(product), 100)

    def test_fully_complete_active_simple_product_is_100_percent(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای کامل",
            slug="complete-pcs", sku="SKU-PCS2", price=Decimal("100000"), stock=5,
            status=Product.Status.ACTIVE, seo_title="عنوان سئو", seo_description="توضیحات متا",
        )
        ProductImage.objects.create(product=product, image="products/gallery/x.jpg")
        self.assertEqual(completion_percent(product), 100)

    def test_variable_product_requires_at_least_one_active_variant(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای متنوع",
            slug="variable-pcs", sku="SKU-PCS3", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        checklist = {item.key: item.done for item in build_completion_checklist(product)}
        self.assertFalse(checklist["variants"])
        self.assertFalse(checklist["inventory"])

        ProductVariant.objects.create(product=product, attribute="رنگ", value="قرمز", stock=3)
        checklist = {item.key: item.done for item in build_completion_checklist(product)}
        self.assertTrue(checklist["variants"])
        self.assertTrue(checklist["inventory"])

    def test_obsolete_only_variants_do_not_count_as_valid_setup(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای منسوخ",
            slug="obsolete-pcs", sku="SKU-PCS4", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        ProductVariant.objects.create(
            product=product, attribute="رنگ", value="قرمز", stock=3, is_obsolete=True, is_active=False,
        )
        checklist = {item.key: item.done for item in build_completion_checklist(product)}
        self.assertFalse(checklist["variants"])

    def test_percent_is_computed_from_real_ratio_not_hardcoded(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="ratio-pcs", sku="SKU-PCS5", price=Decimal("100000"),
        )
        items = build_completion_checklist(product)
        expected = round(sum(1 for i in items if i.done) * 100 / len(items))
        self.assertEqual(completion_percent(product), expected)
