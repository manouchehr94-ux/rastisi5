from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.customers.models import Customer

from apps.catalog.models import Brand, Category, Product, ProductImage, ProductVariant, Review, Vendor

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
