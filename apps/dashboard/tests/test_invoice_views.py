from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


class InvoiceViewsTestCase(TestCase):
    def setUp(self):
        self.store = store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09121150001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="کیوان رستمی", phone="09121150001")
        self.vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-iv")
        self.shipping = ShippingMethod.objects.create(store=store, name="پست", slug="post-iv", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=store, name="زرین‌پال", slug="zarin-iv")
        self.paid_order = Order.objects.create(
            code="DM-88881", store=store, customer=self.customer, vendor=self.vendor,
            address={"province": "تهران", "city": "تهران", "full_address": "میدان آزادی"},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("109000"), tax=Decimal("9000"),
            payment_status=Order.PaymentStatus.PAID,
        )
        self.pending_order = Order.objects.create(
            code="DM-88882", store=store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("50000"), grand_total=Decimal("54500"), tax=Decimal("4500"),
        )
        self.staff = User.objects.create_user(username="09121150099", password="pass12345", is_staff=True)
        self.client.login(username="09121150099", password="pass12345")


class InvoiceListViewTests(InvoiceViewsTestCase):
    def test_renders_invoice_table(self):
        response = self.client.get(reverse("dashboard:invoice-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DM-88881")
        self.assertContains(response, "DM-88882")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:invoice-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_filter_by_payment_status(self):
        response = self.client.get(reverse("dashboard:invoice-table"), {"status": Order.PaymentStatus.PAID})
        self.assertContains(response, "DM-88881")
        self.assertNotContains(response, "DM-88882")

    def test_summary_totals_present(self):
        response = self.client.get(reverse("dashboard:invoice-list"))
        self.assertContains(response, "مجموع فاکتورها")


class InvoiceDetailViewTests(InvoiceViewsTestCase):
    def test_renders_printable_invoice(self):
        response = self.client.get(reverse("dashboard:invoice-detail", args=[self.paid_order.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DM-88881")
        self.assertContains(response, "میدان آزادی")
        self.assertContains(response, 'id="printArea"')

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:invoice-detail", args=[self.paid_order.code]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_404_for_unknown_code(self):
        response = self.client.get(reverse("dashboard:invoice-detail", args=["DM-00000"]))
        self.assertEqual(response.status_code, 404)
