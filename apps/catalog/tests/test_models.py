from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.customers.models import Customer

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


class CatalogModelsTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه نمونه", slug="sample-shop")
        self.category = Category.objects.create(name="لوازم خانگی", slug="home-appliances", icon="🏠")
        self.subcategory = Category.objects.create(
            name="آشپزخانه", slug="kitchen", icon="🍳", parent=self.category
        )
        self.brand = Brand.objects.create(name="برند نمونه", slug="sample-brand")

    def _make_product(self, **kwargs):
        defaults = dict(
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
        self.vendor = Vendor.objects.create(name="فروشگاه نمونه", slug="sample-shop-pv")
        self.category = Category.objects.create(name="لوازم خانگی", slug="home-appliances-pv")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-pv",
            sku="SKU-HOSE-PV", price=Decimal("200000"),
        )
        self.other_product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="کالای دیگر", slug="other-pv",
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
        self.vendor = Vendor.objects.create(name="فروشگاه نمونه", slug="sample-shop-spec")
        self.category = Category.objects.create(name="لوازم خودرو", slug="auto-parts-spec")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="لنت ترمز", slug="brake-pad-spec",
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
        self.category = Category.objects.create(name="لوازم خودرو", slug="auto-parts-tpl")
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
