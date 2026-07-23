import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.blog.models import BlogPost
from apps.catalog.models import Brand, Category, Product, ProductImage
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod


class SeedShopCommandTests(TestCase):
    """MEDIA_ROOT موقت تا فایل‌های تصویر نمونه در media/ واقعی پروژه نوشته نشوند."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def _run(self):
        call_command("seed_shop", stdout=StringIO())

    def test_seed_creates_expected_records(self):
        self._run()
        self.assertEqual(Category.objects.count(), 15)
        self.assertEqual(Brand.objects.count(), 5)
        self.assertEqual(Product.objects.count(), 15)
        self.assertEqual(Customer.objects.count(), 5)
        self.assertEqual(ShippingMethod.objects.count(), 3)
        self.assertEqual(PaymentGateway.objects.count(), 4)
        self.assertEqual(Order.objects.count(), 6)
        self.assertEqual(BlogPost.objects.count(), 4)

    def test_seed_data_spans_multiple_generic_domains(self):
        """فروشگاه نباید به یک نوع کالای خاص گره بخورد — چند دسته‌ی متفاوت باید موجود باشد."""
        self._run()
        top_level_slugs = set(Category.objects.filter(parent=None).values_list("slug", flat=True))
        self.assertEqual(
            top_level_slugs,
            {"home-appliances", "stationery", "fruits-vegetables", "digital", "clothing"},
        )

    def test_seed_orders_cover_all_statuses(self):
        self._run()
        statuses = set(Order.objects.values_list("status", flat=True))
        self.assertEqual(
            statuses,
            {Order.Status.PENDING, Order.Status.PROCESSING, Order.Status.SHIPPED,
             Order.Status.DELIVERED, Order.Status.CANCELED},
        )

    def test_seed_is_idempotent(self):
        self._run()
        self._run()
        self._run()
        self.assertEqual(Category.objects.count(), 15)
        self.assertEqual(Product.objects.count(), 15)
        self.assertEqual(Customer.objects.count(), 5)
        self.assertEqual(Order.objects.count(), 6)
        self.assertEqual(BlogPost.objects.count(), 4)

    def test_seed_creates_sample_images_for_selected_products(self):
        self._run()
        self.assertEqual(ProductImage.objects.count(), 4)
        for image in ProductImage.objects.all():
            self.assertTrue(image.is_cover)
            self.assertTrue(image.image.name)
            self.assertTrue(image.thumbnail.name)

    def test_seed_leaves_other_products_without_images_for_fallback(self):
        self._run()
        products_without_images = Product.objects.exclude(images__isnull=False).count()
        self.assertEqual(products_without_images, Product.objects.count() - 4)

    def test_seed_image_creation_is_idempotent(self):
        self._run()
        self._run()
        self.assertEqual(ProductImage.objects.count(), 4)
