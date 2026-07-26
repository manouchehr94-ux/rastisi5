from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.dashboard.services.customers_admin_service import annotated_customers, customer_orders, customer_paid_total
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


class CustomersAdminServiceTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        user1 = User.objects.create_user(username="09121170001", password="pass12345")
        self.customer1 = Customer.objects.create(
            user=user1, full_name="پریسا کاظمی", phone="09121170001", city="تهران", is_vip=True
        )
        user2 = User.objects.create_user(username="09121170002", password="pass12345")
        self.customer2 = Customer.objects.create(user=user2, full_name="بهروز امینی", phone="09121170002", city="یزد")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ca")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-ca", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-ca")
        Order.objects.create(
            code="DM-c1", store=self.store, customer=self.customer1, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("100000"), payment_status=Order.PaymentStatus.PAID,
        )
        Order.objects.create(
            code="DM-c2", store=self.store, customer=self.customer1, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("50000"), payment_status=Order.PaymentStatus.PENDING,
        )


class AnnotatedCustomersTests(CustomersAdminServiceTestCase):
    def test_order_count_includes_all_statuses(self):
        row = annotated_customers(store=self.store).get(pk=self.customer1.pk)
        self.assertEqual(row.order_count, 2)

    def test_paid_total_only_counts_paid_orders(self):
        row = annotated_customers(store=self.store).get(pk=self.customer1.pk)
        self.assertEqual(row.paid_total, Decimal("100000"))

    def test_customer_without_any_order_at_this_store_is_not_listed(self):
        """طراحی عمدی PR23: Customer فیلد store ندارد، پس دید داشبورد از
        طریق رابطه‌ی Order.store اعمال می‌شود — مشتری‌ای که هیچ Order در
        همین Store ندارد (چه اصلاً سفارشی نداده، چه فقط از Store دیگری خرید
        کرده) اصلاً در این فهرست ظاهر نمی‌شود، نه این‌که با شمارش صفر نشان
        داده شود."""
        self.assertFalse(annotated_customers(store=self.store).filter(pk=self.customer2.pk).exists())

    def test_search_by_name(self):
        result = annotated_customers(store=self.store, q="پریسا")
        self.assertEqual(list(result), [self.customer1])

    def test_search_by_city_excludes_customers_without_orders_here(self):
        """قبلاً customer2 (شهر یزد، بدون Order) نتیجه بود؛ طبق طراحی جدید،
        بدون Order در این Store اصلاً در استخر جست‌وجو نیست."""
        result = annotated_customers(store=self.store, q="یزد")
        self.assertEqual(list(result), [])


class CustomerOrdersTests(CustomersAdminServiceTestCase):
    def test_returns_only_that_customers_orders(self):
        orders = customer_orders(self.customer1, store=self.store)
        self.assertEqual(orders.count(), 2)
        self.assertEqual(customer_orders(self.customer2, store=self.store).count(), 0)


class CustomerPaidTotalTests(CustomersAdminServiceTestCase):
    def test_sums_only_paid_orders(self):
        total = customer_paid_total(customer_orders(self.customer1, store=self.store))
        self.assertEqual(total, Decimal("100000"))

    def test_zero_when_no_paid_orders(self):
        total = customer_paid_total(customer_orders(self.customer2, store=self.store))
        self.assertEqual(total, 0)
