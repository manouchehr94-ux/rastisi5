from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.orders.models import TaxClass
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProductTaxClassIsolationTests(TestCase):
    """Product.tax_class هرگز نمی‌تواند به دسته‌ی مالیاتیِ فروشگاه دیگری اشاره کند."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ptc")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-ptc")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدفون", slug="headphone-ptc",
            sku="SKU-PTC1", price=Decimal("1000000"), stock=10,
        )

    def test_rejects_tax_class_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ptc-other", status=Store.Status.ACTIVE)
        other_class = TaxClass.objects.create(store=other_store, name="دیگر", code="other-ptc")
        self.product.tax_class = other_class
        with self.assertRaises(ValidationError):
            self.product.full_clean()

    def test_accepts_tax_class_from_same_store(self):
        own_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-ptc")
        self.product.tax_class = own_class
        self.product.full_clean()  # should not raise
