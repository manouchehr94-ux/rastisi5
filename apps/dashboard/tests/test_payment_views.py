from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod, Transaction
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class PaymentViewsTestCase(TestCase):
    def setUp(self):
        self.store = store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09121160001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="الهام یوسفی", phone="09121160001")
        self.vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-pw")
        self.shipping = ShippingMethod.objects.create(store=store, name="پست", slug="post-pw", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=store, name="زرین‌پال", slug="zarin-pw")
        self.order = Order.objects.create(
            code="DM-99991", store=store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
        )
        self.tx_ok = Transaction.objects.create(
            code="TX-99991", order=self.order, gateway=self.gateway,
            amount=Decimal("100000"), status=Transaction.Status.OK, ref_id="123456789",
        )
        self.tx_fail = Transaction.objects.create(
            code="TX-99992", order=self.order, gateway=self.gateway,
            amount=Decimal("100000"), status=Transaction.Status.FAIL,
        )
        self.staff = User.objects.create_user(username="09121160099", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121160099", password="pass12345")


class PaymentListViewTests(PaymentViewsTestCase):
    def test_renders_transaction_table(self):
        response = self.client.get(reverse("dashboard:payment-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TX-99991")
        self.assertContains(response, "TX-99992")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:payment-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/login/", response.url)

    def test_filter_by_status(self):
        response = self.client.get(reverse("dashboard:payment-table"), {"status": Transaction.Status.OK})
        self.assertContains(response, "TX-99991")
        self.assertNotContains(response, "TX-99992")
