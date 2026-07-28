"""Dashboard order/invoice/payment/customer cross-Store adversarial tests
(PR23) — real two-Store isolation, mirroring
apps.dashboard.tests.test_catalog_store_isolation's established pattern.

Before this PR, ``orders_admin_service``/``customers_admin_service`` queried
``Order.objects``/``Transaction.objects``/``Customer.objects`` completely
unscoped by Store — the same bug class already fixed once for catalog in
PR#21, left open for orders. These tests prove list, detail, and mutation
endpoints are now all Store-scoped, and that a customer's Store-scoped
aggregates (order_count/paid_total) never leak another Store's totals.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod, Transaction
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

HOST_A = "dord-a.example.com"
HOST_B = "dord-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class DashboardOrderTwoStoreIsolationTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="dord-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.staff = User.objects.create_user(username="dord-staff", password="pass12345", is_staff=True)
        for store in (self.store_a, self.store_b):
            StoreMembership.objects.create(
                store=store, user=self.staff, role=StoreMembership.Role.OWNER,
                status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
            )
        self.client.login(username="dord-staff", password="pass12345")

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-dord-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-dord-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a,
            name="Product A", slug="product-dord-a", sku="SKU-DORD-A", price=Decimal("100000"),
        )
        self.shipping_a = ShippingMethod.objects.create(store=self.store_a, name="پست A", slug="post-dord-a", cost=Decimal("10000"))
        self.gateway_a = PaymentGateway.objects.create(store=self.store_a, name="درگاه A", slug="gw-dord-a")

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-dord-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-dord-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b,
            name="Product B", slug="product-dord-b", sku="SKU-DORD-B", price=Decimal("200000"),
        )
        self.shipping_b = ShippingMethod.objects.create(store=self.store_b, name="پست B", slug="post-dord-b", cost=Decimal("20000"))
        self.gateway_b = PaymentGateway.objects.create(store=self.store_b, name="درگاه B", slug="gw-dord-b")

        user_a = User.objects.create_user(username="09121240001", password="pass12345")
        self.customer_a = Customer.objects.create(user=user_a, full_name="مشتری آ", phone="09121240001")
        user_b = User.objects.create_user(username="09121240002", password="pass12345")
        self.customer_b = Customer.objects.create(user=user_b, full_name="مشتری ب", phone="09121240002")

        self.order_a = Order.objects.create(
            code="DM-DORDA1", store=self.store_a, customer=self.customer_a, vendor=self.vendor_a, address={},
            shipping_method=self.shipping_a, payment_gateway=self.gateway_a,
            grand_total=Decimal("100000"), payment_status=Order.PaymentStatus.PAID,
        )
        self.order_b = Order.objects.create(
            code="DM-DORDB1", store=self.store_b, customer=self.customer_b, vendor=self.vendor_b, address={},
            shipping_method=self.shipping_b, payment_gateway=self.gateway_b,
            grand_total=Decimal("200000"), payment_status=Order.PaymentStatus.PAID,
        )
        self.tx_a = Transaction.objects.create(
            code="TX-DORDA1", order=self.order_a, gateway=self.gateway_a,
            amount=Decimal("100000"), status=Transaction.Status.OK,
        )
        self.tx_b = Transaction.objects.create(
            code="TX-DORDB1", order=self.order_b, gateway=self.gateway_b,
            amount=Decimal("200000"), status=Transaction.Status.OK,
        )

    # ------------------------------------------------------------- orders

    def test_order_list_excludes_other_store_order(self):
        response = self.client.get(reverse("dashboard:order-list"), HTTP_HOST=HOST_B)
        self.assertContains(response, "DM-DORDB1")
        self.assertNotContains(response, "DM-DORDA1")

    def test_order_detail_denies_other_store_order(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order_a.code]), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 404)

    def test_order_status_mutation_denied_for_other_store_order(self):
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order_a.code]),
            {"status": Order.Status.PROCESSING}, HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        self.order_a.refresh_from_db()
        self.assertEqual(self.order_a.status, Order.Status.PENDING)

    def test_own_store_order_detail_and_mutation_still_work(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order_b.code]), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order_b.code]),
            {"status": Order.Status.PROCESSING}, HTTP_HOST=HOST_B,
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.order_b.code]))
        self.order_b.refresh_from_db()
        self.assertEqual(self.order_b.status, Order.Status.PROCESSING)

    # ------------------------------------------------------------ invoices

    def test_invoice_list_excludes_other_store_order(self):
        response = self.client.get(reverse("dashboard:invoice-list"), HTTP_HOST=HOST_B)
        self.assertContains(response, "DM-DORDB1")
        self.assertNotContains(response, "DM-DORDA1")

    def test_invoice_detail_denies_other_store_order(self):
        response = self.client.get(reverse("dashboard:invoice-detail", args=[self.order_a.code]), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ payments

    def test_payment_list_excludes_other_store_transaction(self):
        response = self.client.get(reverse("dashboard:payment-list"), HTTP_HOST=HOST_B)
        self.assertContains(response, "TX-DORDB1")
        self.assertNotContains(response, "TX-DORDA1")

    # ----------------------------------------------------------- customers

    def test_customer_list_excludes_customer_with_no_order_at_this_store(self):
        response = self.client.get(reverse("dashboard:customer-list"), HTTP_HOST=HOST_B)
        self.assertContains(response, "مشتری ب")
        self.assertNotContains(response, "مشتری آ")

    def test_customer_detail_denied_for_customer_with_no_order_at_this_store(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[self.customer_a.pk]), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_allowed_for_customer_with_order_at_this_store(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[self.customer_b.pk]), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)

    def test_shared_customer_aggregates_are_store_specific(self):
        """A customer who ordered from BOTH Stores must appear in both
        dashboards, but each dashboard's order_count/paid_total must only
        reflect its own Store's orders — never the other Store's total."""
        Order.objects.create(
            code="DM-DORDSHARED", store=self.store_b, customer=self.customer_a, vendor=self.vendor_b, address={},
            shipping_method=self.shipping_b, payment_gateway=self.gateway_b,
            grand_total=Decimal("50000"), payment_status=Order.PaymentStatus.PAID,
        )
        response_b = self.client.get(reverse("dashboard:customer-detail", args=[self.customer_a.pk]), HTTP_HOST=HOST_B)
        self.assertEqual(response_b.status_code, 200)
        self.assertContains(response_b, "DM-DORDSHARED")
        self.assertNotContains(response_b, "DM-DORDA1")

        response_a = self.client.get(reverse("dashboard:customer-detail", args=[self.customer_a.pk]), HTTP_HOST=HOST_A)
        self.assertEqual(response_a.status_code, 200)
        self.assertContains(response_a, "DM-DORDA1")
        self.assertNotContains(response_a, "DM-DORDSHARED")
