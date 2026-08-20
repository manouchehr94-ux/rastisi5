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


def _create_customer_with_order(store, vendor, shipping, gateway, *, phone, name):
    user = User.objects.create_user(username=phone, password="pass12345")
    customer = Customer.objects.create(user=user, full_name=name, phone=phone)
    Order.objects.create(
        code=f"DM-{phone[-6:]}", store=store, customer=customer, vendor=vendor, address={},
        shipping_method=shipping, payment_gateway=gateway, grand_total=Decimal("100000"),
    )
    return customer


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
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
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
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_404_for_unknown_customer(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[999999]))
        self.assertEqual(response.status_code, 404)


class CustomerListPerformanceTests(CustomerViewsTestCase):
    """Phase 2 — the customer list used to render the entire Store customer
    base unpaginated. Fixed via ``_customer_list_context``'s ``Paginator``
    (mirrors ``_product_list_context``). ``annotated_customers`` itself was
    already correctly annotated (order_count/paid_total, no per-row N+1) —
    only pagination was missing.

    Fixture size: 1 customer from ``CustomerViewsTestCase.setUp`` + 25
    created here = 26 total, past ``CUSTOMERS_PER_PAGE`` (20)."""

    def test_customer_list_is_paginated_not_unbounded(self):
        for i in range(25):
            _create_customer_with_order(
                self.store, self.vendor, self.shipping, self.gateway,
                phone=f"0912200{i:04d}", name=f"مشتری {i}",
            )
        response = self.client.get(reverse("dashboard:customer-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)
        self.assertEqual(response.context["paginator"].count, 26)
        self.assertContains(response, "بعدی")

    def test_second_page_reachable(self):
        for i in range(25):
            _create_customer_with_order(
                self.store, self.vendor, self.shipping, self.gateway,
                phone=f"0912201{i:04d}", name=f"مشتری {i}",
            )
        response = self.client.get(reverse("dashboard:customer-table"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 6)
