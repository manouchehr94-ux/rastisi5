from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.blog.models import BlogPost
from apps.catalog.models import Brand, Category, Product
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod


class SeedShopCommandTests(TestCase):
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
