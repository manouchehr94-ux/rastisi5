from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.stores.models import Store

from apps.customers.models import Address, Customer, Wishlist

User = get_user_model()


class CustomersModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sara", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="سارا احمدی", phone="09121111111")

    def test_customer_creation_and_joined_at(self):
        self.assertEqual(str(self.customer), "سارا احمدی")
        self.assertEqual(self.customer.joined_at, self.customer.created_at)
        self.assertFalse(self.customer.is_vip)

    def test_address_creation(self):
        address = Address.objects.create(
            customer=self.customer,
            receiver_name="سارا احمدی",
            phone="09121111111",
            province="تهران",
            city="تهران",
            postal_code="1234567890",
            full_address="تهران، خیابان ولیعصر",
            is_default=True,
        )
        self.assertIn(address, self.customer.addresses.all())

    def test_wishlist_unique_together(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-w")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-w")
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="گوشی", slug="phone-w",
            sku="SKU-W1", price=5_000_000,
        )
        Wishlist.objects.create(customer=self.customer, product=product)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Wishlist.objects.create(customer=self.customer, product=product)
