from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import change_order_status
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class OrderViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        user = User.objects.create_user(username="09121140001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="نگار مرادی", phone="09121140001")
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ov")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-ov", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-ov")
        self.order = Order.objects.create(
            code="DM-77777", customer=self.customer, vendor=self.vendor,
            address={"province": "تهران", "city": "تهران", "full_address": "خیابان ولیعصر"},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("109000"), tax=Decimal("9000"),
        )
        self.staff = User.objects.create_user(username="09121140099", password="pass12345", is_staff=True)
        self.client.login(username="09121140099", password="pass12345")


class OrderListViewTests(OrderViewsTestCase):
    def test_renders_order_table(self):
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DM-77777")
        self.assertContains(response, "نگار مرادی")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_status_filter(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        response = self.client.get(reverse("dashboard:order-table"), {"status": Order.Status.PENDING})
        self.assertNotContains(response, "DM-77777")

    def test_search_by_code(self):
        response = self.client.get(reverse("dashboard:order-table"), {"q": "77777"})
        self.assertContains(response, "DM-77777")


class OrderDetailViewTests(OrderViewsTestCase):
    def test_shows_order_items_and_address(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خیابان ولیعصر")

    def test_shows_status_change_form_for_non_final_order(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertContains(response, "ثبت تغییرات")

    def test_valid_status_change_redirects_and_updates(self):
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]), {"status": Order.Status.PROCESSING}
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.order.code]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertEqual(self.order.status_history.count(), 1)

    def test_invalid_status_transition_shows_error_without_changing_status(self):
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]), {"status": Order.Status.DELIVERED}
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertContains(response, "مجاز نیست")

    def test_shipping_with_tracking_code_saves_it_on_order(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]),
            {"status": Order.Status.SHIPPED, "tracking_code": "TRACK-ABC123"},
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.order.code]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.tracking_code, "TRACK-ABC123")

    def test_final_order_hides_status_change_form(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertNotContains(response, "ثبت تغییرات")

    def test_status_history_displayed(self):
        change_order_status(self.order, Order.Status.PROCESSING, note="بررسی شد", store=self.store)
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertContains(response, "بررسی شد")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_404_for_unknown_code(self):
        response = self.client.get(reverse("dashboard:order-detail", args=["DM-00000"]))
        self.assertEqual(response.status_code, 404)
