from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.customers.models import Customer
from apps.stores.models import Store

from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Specification,
    SpecificationTemplate,
    SpecificationTemplateField,
    Vendor,
)

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class CatalogModelsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه نمونه", slug="sample-shop")
        self.category = Category.objects.create(
            store=self.store, name="لوازم خانگی", slug="home-appliances", icon="🏠"
        )
        self.subcategory = Category.objects.create(
            store=self.store, name="آشپزخانه", slug="kitchen", icon="🍳", parent=self.category
        )
        self.brand = Brand.objects.create(store=self.store, name="برند نمونه", slug="sample-brand")

    def _make_product(self, **kwargs):
        defaults = dict(
            store=self.store,
            vendor=self.vendor,
            category=self.category,
            brand=self.brand,
            name="محصول نمونه",
            slug="sample-product",
            sku="SKU-0001",
            price=Decimal("1000000"),
            discount_percent=10,
        )
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

    def test_vendor_creation(self):
        self.assertEqual(str(self.vendor), "فروشگاه نمونه")
        self.assertTrue(self.vendor.is_active)

    def test_category_tree(self):
        self.assertEqual(self.subcategory.parent, self.category)
        self.assertIn(self.subcategory, self.category.children.all())

    def test_product_final_price_property(self):
        product = self._make_product()
        self.assertEqual(product.final_price, Decimal("900000"))

    def test_product_final_price_no_discount(self):
        product = self._make_product(sku="SKU-0002", slug="sample-product-2", discount_percent=0)
        self.assertEqual(product.final_price, product.price)

    def test_product_sku_must_be_unique(self):
        self._make_product()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_product(slug="sample-product-2")

    def test_product_image_and_variant(self):
        product = self._make_product()
        variant = ProductVariant.objects.create(
            product=product, attribute="رنگ", value="مشکی", value_hex="#000000", stock=5
        )
        image = ProductImage.objects.create(product=product, image="products/gallery/sample.jpg", order=1)
        self.assertEqual(product.variants.count(), 1)
        self.assertEqual(product.images.count(), 1)
        self.assertEqual(variant.product, product)
        self.assertEqual(image.product, product)

    def test_review_creation(self):
        product = self._make_product()
        user = User.objects.create_user(username="ali", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="علی رضایی", phone="09120000000")
        review = Review.objects.create(product=product, customer=customer, rating=5, text="عالی بود")
        self.assertEqual(product.reviews.count(), 1)
        self.assertFalse(review.is_approved)

    def test_product_type_defaults_to_simple(self):
        product = self._make_product()
        self.assertEqual(product.product_type, Product.ProductType.SIMPLE)
        self.assertFalse(product.is_variable)


class ProductVariantConstraintTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه نمونه", slug="sample-shop-pv")
        self.category = Category.objects.create(store=self.store, name="لوازم خانگی", slug="home-appliances-pv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-pv",
            sku="SKU-HOSE-PV", price=Decimal("200000"),
        )
        self.other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر", slug="other-pv",
            sku="SKU-OTHER-PV", price=Decimal("100000"),
        )

    def test_duplicate_active_value_same_normalized_name_rejected(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(product=self.product, attribute="طول", value="30")

    def test_duplicate_detection_ignores_persian_arabic_digit_and_whitespace_differences(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(product=self.product, attribute=" طول ", value="۳۰")

    def test_same_value_allowed_on_different_products(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        variant = ProductVariant.objects.create(product=self.other_product, attribute="طول", value="30")
        self.assertEqual(variant.product, self.other_product)

    def test_inactive_duplicate_does_not_block_new_active_value(self):
        first = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        first.is_active = False
        first.save(update_fields=["is_active"])
        second = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        self.assertTrue(second.is_active)

    def test_empty_attribute_rejected_by_full_clean(self):
        variant = ProductVariant(product=self.product, attribute="   ", value="30")
        with self.assertRaises(ValidationError):
            variant.full_clean(exclude=["normalized_attribute", "normalized_value"])

    def test_empty_value_rejected_by_full_clean(self):
        variant = ProductVariant(product=self.product, attribute="طول", value="   ")
        with self.assertRaises(ValidationError):
            variant.full_clean(exclude=["normalized_attribute", "normalized_value"])

    def test_sku_unique_across_variants(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30", sku="HOSE-30")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(
                    product=self.other_product, attribute="طول", value="40", sku="HOSE-30"
                )

    def test_multiple_blank_skus_allowed(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="40")
        self.assertEqual(variant.sku, "")

    def test_negative_stock_rejected_by_positive_integer_field(self):
        variant = ProductVariant(product=self.product, attribute="طول", value="30", stock=-1)
        with self.assertRaises(ValidationError):
            variant.full_clean(exclude=["normalized_attribute", "normalized_value"])

    def test_deterministic_ordering_by_display_order_then_attribute_value(self):
        v2 = ProductVariant.objects.create(product=self.product, attribute="طول", value="50", display_order=2)
        v1 = ProductVariant.objects.create(product=self.product, attribute="طول", value="30", display_order=1)
        v0 = ProductVariant.objects.create(product=self.product, attribute="طول", value="100", display_order=0)
        self.assertEqual(list(self.product.variants.all()), [v0, v1, v2])

    def test_variant_belongs_to_exactly_one_product(self):
        variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        self.assertEqual(variant.product_id, self.product.pk)
        self.assertNotIn(variant, self.other_product.variants.all())


class SpecificationModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه نمونه", slug="sample-shop-spec")
        self.category = Category.objects.create(store=self.store, name="لوازم خودرو", slug="auto-parts-spec")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="لنت ترمز", slug="brake-pad-spec",
            sku="SKU-BRAKE-SPEC", price=Decimal("350000"),
        )

    def test_specification_requires_label(self):
        spec = Specification(product=self.product, label="   ", value="مقدار")
        with self.assertRaises(ValidationError):
            spec.full_clean()

    def test_specification_value_may_be_blank(self):
        spec = Specification.objects.create(product=self.product, label="جنس", value="")
        self.assertEqual(spec.value, "")

    def test_specification_ordering(self):
        second = Specification.objects.create(product=self.product, label="کشور سازنده", value="ایران", order=2)
        first = Specification.objects.create(product=self.product, label="جنس", value="فلز", order=1)
        self.assertEqual(list(self.product.specifications.all()), [first, second])


class SpecificationTemplateModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.category = Category.objects.create(store=self.store, name="لوازم خودرو", slug="auto-parts-tpl")
        self.template = SpecificationTemplate.objects.create(name="قطعات خودرو", category=self.category)

    def test_template_field_requires_label(self):
        field = SpecificationTemplateField(template=self.template, label="  ")
        with self.assertRaises(ValidationError):
            field.full_clean()

    def test_duplicate_label_in_same_template_rejected(self):
        SpecificationTemplateField.objects.create(template=self.template, label="شماره فنی")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpecificationTemplateField.objects.create(template=self.template, label="شماره فنی")

    def test_same_label_allowed_in_different_templates(self):
        other_template = SpecificationTemplate.objects.create(name="لوازم خانگی تست")
        SpecificationTemplateField.objects.create(template=self.template, label="جنس")
        field = SpecificationTemplateField.objects.create(template=other_template, label="جنس")
        self.assertEqual(field.template, other_template)


class CatalogTwoStoreUniquenessTests(TestCase):
    """اثبات این‌که یکتاییِ اسلاگ/SKU در سطح هر Store اجرا می‌شود، نه در کل
    پلتفرم — دو Store می‌توانند مقدار یکسان داشته باشند، یک Store هرگز
    نمی‌تواند دو رکورد با مقدار یکسان داشته باشد."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)

    def test_two_stores_may_use_the_same_vendor_slug(self):
        Vendor.objects.create(store=self.store_a, name="A", slug="shared-vendor")
        vendor_b = Vendor.objects.create(store=self.store_b, name="B", slug="shared-vendor")
        self.assertEqual(vendor_b.slug, "shared-vendor")

    def test_same_store_cannot_reuse_vendor_slug(self):
        Vendor.objects.create(store=self.store_a, name="A", slug="dup-vendor")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vendor.objects.create(store=self.store_a, name="A2", slug="dup-vendor")

    def test_two_stores_may_use_the_same_category_slug(self):
        Category.objects.create(store=self.store_a, name="A", slug="shared-category")
        category_b = Category.objects.create(store=self.store_b, name="B", slug="shared-category")
        self.assertEqual(category_b.slug, "shared-category")

    def test_same_store_cannot_reuse_category_slug(self):
        Category.objects.create(store=self.store_a, name="A", slug="dup-category")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(store=self.store_a, name="A2", slug="dup-category")

    def test_two_stores_may_use_the_same_brand_slug(self):
        Brand.objects.create(store=self.store_a, name="A", slug="shared-brand")
        brand_b = Brand.objects.create(store=self.store_b, name="B", slug="shared-brand")
        self.assertEqual(brand_b.slug, "shared-brand")

    def test_same_store_cannot_reuse_brand_slug(self):
        Brand.objects.create(store=self.store_a, name="A", slug="dup-brand")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Brand.objects.create(store=self.store_a, name="A2", slug="dup-brand")

    def _vendor_and_category(self, store, suffix):
        vendor = Vendor.objects.create(store=store, name=f"V{suffix}", slug=f"v-{suffix}")
        category = Category.objects.create(store=store, name=f"C{suffix}", slug=f"c-{suffix}")
        return vendor, category

    def test_two_stores_may_use_the_same_product_slug_and_sku(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "a")
        vendor_b, category_b = self._vendor_and_category(self.store_b, "b")
        Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="shared-product", sku="SHARED-SKU", price=Decimal("100000"),
        )
        product_b = Product.objects.create(
            store=self.store_b, vendor=vendor_b, category=category_b, name="B",
            slug="shared-product", sku="SHARED-SKU", price=Decimal("200000"),
        )
        self.assertEqual(product_b.slug, "shared-product")
        self.assertEqual(product_b.sku, "SHARED-SKU")

    def test_same_store_cannot_reuse_product_slug(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "slugdup")
        Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="dup-product", sku="SKU-DUP-1", price=Decimal("100000"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    store=self.store_a, vendor=vendor_a, category=category_a, name="A2",
                    slug="dup-product", sku="SKU-DUP-2", price=Decimal("100000"),
                )

    def test_same_store_cannot_reuse_product_sku(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "skudup")
        Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="sku-dup-1", sku="SKU-DUP-SAME", price=Decimal("100000"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    store=self.store_a, vendor=vendor_a, category=category_a, name="A2",
                    slug="sku-dup-2", sku="SKU-DUP-SAME", price=Decimal("100000"),
                )

    def test_two_stores_may_use_the_same_variant_sku(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "va")
        vendor_b, category_b = self._vendor_and_category(self.store_b, "vb")
        product_a = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="variant-host-a", sku="VARIANT-HOST-A", price=Decimal("100000"),
        )
        product_b = Product.objects.create(
            store=self.store_b, vendor=vendor_b, category=category_b, name="B",
            slug="variant-host-b", sku="VARIANT-HOST-B", price=Decimal("100000"),
        )
        ProductVariant.objects.create(product=product_a, attribute="رنگ", value="قرمز", sku="SHARED-VAR-SKU")
        variant_b = ProductVariant.objects.create(
            product=product_b, attribute="رنگ", value="قرمز", sku="SHARED-VAR-SKU"
        )
        self.assertEqual(variant_b.sku, "SHARED-VAR-SKU")
        self.assertEqual(variant_b.store_id, self.store_b.pk)

    def test_same_store_cannot_reuse_variant_sku_across_products(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "vardup")
        product1 = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="vardup-1", sku="VARDUP-SKU-1", price=Decimal("100000"),
        )
        product2 = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="B",
            slug="vardup-2", sku="VARDUP-SKU-2", price=Decimal("100000"),
        )
        ProductVariant.objects.create(product=product1, attribute="رنگ", value="قرمز", sku="DUP-VAR-SKU")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(product=product2, attribute="رنگ", value="آبی", sku="DUP-VAR-SKU")

    def test_product_rejects_category_from_another_store(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "mismatch")
        _, category_b = self._vendor_and_category(self.store_b, "mismatch")
        product = Product(
            store=self.store_a, vendor=vendor_a, category=category_b, name="Mismatch",
            slug="mismatch-product", sku="MISMATCH-SKU", price=Decimal("100000"),
        )
        with self.assertRaises(ValidationError):
            product.full_clean(exclude=["slug"])

    def test_product_rejects_vendor_from_another_store(self):
        vendor_b, _ = self._vendor_and_category(self.store_b, "vendormismatch")
        _, category_a = self._vendor_and_category(self.store_a, "vendormismatch")
        product = Product(
            store=self.store_a, vendor=vendor_b, category=category_a, name="Mismatch",
            slug="mismatch-product-2", sku="MISMATCH-SKU-2", price=Decimal("100000"),
        )
        with self.assertRaises(ValidationError):
            product.full_clean(exclude=["slug"])

    def test_product_image_rejects_variant_from_another_product(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "imgvarmismatch")
        product1 = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="A",
            slug="imgvarmismatch-1", sku="IMGVARMISMATCH-SKU-1", price=Decimal("100000"),
        )
        product2 = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a, name="B",
            slug="imgvarmismatch-2", sku="IMGVARMISMATCH-SKU-2", price=Decimal("100000"),
        )
        other_variant = ProductVariant.objects.create(product=product2, attribute="رنگ", value="زرد")
        image = ProductImage(product=product1, image="products/gallery/sample.jpg", variant=other_variant)
        with self.assertRaises(ValidationError):
            image.full_clean()

    def test_category_rejects_parent_from_another_store(self):
        parent_b = Category.objects.create(store=self.store_b, name="ParentB", slug="parent-b-mismatch")
        child = Category(store=self.store_a, name="ChildA", slug="child-a-mismatch", parent=parent_b)
        with self.assertRaises(ValidationError):
            child.full_clean()

    def test_missing_store_rejected_for_product(self):
        vendor_a, category_a = self._vendor_and_category(self.store_a, "nostore")
        product = Product(
            vendor=vendor_a, category=category_a, name="NoStore",
            slug="no-store-product", sku="NO-STORE-SKU", price=Decimal("100000"),
        )
        with self.assertRaises(ValidationError):
            product.full_clean(exclude=["slug"])
