from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class CustomerViewsTestCase(TestCase):
    def setUp(self):
        self.store = store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09121180001", password="pass12345")
        self.customer = Customer.objects.create(
            user=user, full_name="فرزانه قاسمی", phone="09121180001", city="کرج", is_vip=True
        )
        self.vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cw")
        self.shipping = ShippingMethod.objects.create(store=store, name="پست", slug="post-cw", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=store, name="زرین‌پال", slug="zarin-cw")
        self.order = Order.objects.create(
            code="DM-cw1", store=store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("250000"), payment_status=Order.PaymentStatus.PAID,
        )
        self.staff = User.objects.create_user(username="09121180099", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121180099", password="pass12345")


class CustomerListViewTests(CustomerViewsTestCase):
    def test_renders_customer_table(self):
        response = self.client.get(reverse("dashboard:customer-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فرزانه قاسمی")
        self.assertContains(response, "مشتری ویژه VIP")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:customer-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_search_filters_table(self):
        response = self.client.get(reverse("dashboard:customer-table"), {"q": "فرزانه"})
        self.assertContains(response, "فرزانه قاسمی")

    def test_search_excludes_non_matching(self):
        response = self.client.get(reverse("dashboard:customer-table"), {"q": "چیز-نامرتبط"})
        self.assertNotContains(response, "فرزانه قاسمی")


class CustomerDetailViewTests(CustomerViewsTestCase):
    def test_shows_customer_and_orders(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فرزانه قاسمی")
        self.assertContains(response, "DM-cw1")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:customer-detail", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_404_for_unknown_customer(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[999999]))
        self.assertEqual(response.status_code, 404)
