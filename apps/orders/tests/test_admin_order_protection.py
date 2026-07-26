"""Django Admin cannot bypass the Order state machine (PR23).

Django Admin is already restricted to active superusers only
(apps.stores.admin_permissions, from the PR#21 remediation) — but Django
grants superusers every model permission by default, so without an explicit
override a superuser could still edit Order/OrderItem/Transaction/
OrderStatusHistory directly through /admin/, bypassing
apps.orders.services.order_service.change_order_status entirely (no
transition validation, no OrderStatusHistory record). These tests prove
apps.orders.admin.ReadOnlyFinancialRecordMixin actually closes that gap.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, OrderStatusHistory, PaymentGateway, ShippingMethod, Transaction
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class AdminOrderProtectionFixture(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-aop")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-aop")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالا", slug="product-aop", sku="SKU-AOP", price=Decimal("100000"), stock=5,
        )
        user = User.objects.create_user(username="aop-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121230081")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-aop", cost=Decimal("10000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-aop")
        self.order = Order.objects.create(
            code="DM-AOP1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("100000"),
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            sku=self.product.sku, quantity=1, unit_price=Decimal("100000"), line_total=Decimal("100000"),
        )
        self.transaction = Transaction.objects.create(
            code="TX-AOP1", order=self.order, gateway=self.gateway,
            amount=Decimal("100000"), status=Transaction.Status.PENDING,
        )

        self.superuser = User.objects.create_superuser(username="aop-super", email="s@example.com", password="pass12345")
        self.client.login(username="aop-super", password="pass12345")


class OrderAdminReadOnlyTests(AdminOrderProtectionFixture):
    def test_change_view_is_read_only_not_a_404(self):
        """A superuser can still open the page to inspect the Order (audit
        value), but it must render read-only, not a normal editable form."""
        response = self.client.get(reverse("admin:orders_order_change", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="status"')

    def test_direct_post_cannot_change_status(self):
        response = self.client.post(
            reverse("admin:orders_order_change", args=[self.order.pk]),
            {"status": Order.Status.DELIVERED, "payment_status": Order.PaymentStatus.PAID},
        )
        self.assertNotEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_direct_post_cannot_change_store_or_vendor(self):
        other_store = Store.objects.create(name="Other", slug="aop-other", status=Store.Status.ACTIVE)
        response = self.client.post(
            reverse("admin:orders_order_change", args=[self.order.pk]),
            {"store": other_store.pk},
        )
        self.assertNotEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.store_id, self.store.pk)

    def test_direct_post_cannot_change_grand_total(self):
        response = self.client.post(
            reverse("admin:orders_order_change", args=[self.order.pk]),
            {"grand_total": "1"},
        )
        self.assertNotEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.grand_total, Decimal("100000"))

    def test_add_view_denied(self):
        response = self.client.get(reverse("admin:orders_order_add"))
        self.assertEqual(response.status_code, 403)

    def test_delete_view_denied(self):
        response = self.client.get(reverse("admin:orders_order_delete", args=[self.order.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_no_status_history_created_by_denied_admin_attempt(self):
        count_before = OrderStatusHistory.objects.filter(order=self.order).count()
        self.client.post(
            reverse("admin:orders_order_change", args=[self.order.pk]),
            {"status": Order.Status.DELIVERED},
        )
        self.assertEqual(OrderStatusHistory.objects.filter(order=self.order).count(), count_before)


class OrderItemAdminReadOnlyTests(AdminOrderProtectionFixture):
    def test_direct_post_cannot_change_unit_price(self):
        response = self.client.post(
            reverse("admin:orders_orderitem_change", args=[self.item.pk]),
            {"unit_price": "1", "line_total": "1"},
        )
        self.assertNotEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.unit_price, Decimal("100000"))

    def test_delete_view_denied(self):
        response = self.client.get(reverse("admin:orders_orderitem_delete", args=[self.item.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(OrderItem.objects.filter(pk=self.item.pk).exists())


class TransactionAdminReadOnlyTests(AdminOrderProtectionFixture):
    def test_direct_post_cannot_fabricate_successful_payment(self):
        response = self.client.post(
            reverse("admin:orders_transaction_change", args=[self.transaction.pk]),
            {"status": Transaction.Status.OK, "amount": "100000"},
        )
        self.assertNotEqual(response.status_code, 200)
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status, Transaction.Status.PENDING)

    def test_add_view_denied(self):
        response = self.client.get(reverse("admin:orders_transaction_add"))
        self.assertEqual(response.status_code, 403)


class OrderStatusHistoryAdminReadOnlyTests(AdminOrderProtectionFixture):
    def test_add_view_denied(self):
        """History rows must only ever be created by change_order_status —
        never fabricated directly."""
        response = self.client.get(reverse("admin:orders_orderstatushistory_add"))
        self.assertEqual(response.status_code, 403)

    def test_delete_view_denied(self):
        history = OrderStatusHistory.objects.create(
            order=self.order, from_status="", to_status=Order.Status.PENDING, note="test"
        )
        response = self.client.get(reverse("admin:orders_orderstatushistory_delete", args=[history.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(OrderStatusHistory.objects.filter(pk=history.pk).exists())


class ValidServiceTransitionStillCreatesHistoryTests(AdminOrderProtectionFixture):
    """Sanity check: the admin lockdown does not accidentally break the
    real, sanctioned transition path (the dashboard's own
    change_order_status call) — only direct Admin edits are blocked."""

    def test_change_order_status_service_call_still_works(self):
        from apps.orders.services.order_service import change_order_status

        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertEqual(self.order.status_history.count(), 1)
