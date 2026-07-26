from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod, Transaction
from apps.orders.services.order_service import change_order_status
from apps.dashboard.services.orders_admin_service import (
    filtered_invoices,
    filtered_orders,
    filtered_transactions,
    invoice_totals,
    next_status_options,
    order_is_final,
    order_status_counts,
    order_status_steps,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class OrdersAdminServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        user = User.objects.create_user(username="09121130001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="سارا احمدی", phone="09121130001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-oa")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-oa", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-oa")
        self.order = Order.objects.create(
            code="DM-11111", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
        )
        self.order2 = Order.objects.create(
            code="DM-22222", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("200000"), grand_total=Decimal("200000"),
            payment_status=Order.PaymentStatus.PAID,
        )


class FilteredOrdersTests(OrdersAdminServiceTestCase):
    def test_search_by_code(self):
        result = filtered_orders(store=self.store, q="11111")
        self.assertEqual(list(result), [self.order])

    def test_search_by_customer_name(self):
        result = filtered_orders(store=self.store, q="سارا")
        self.assertEqual(set(result), {self.order, self.order2})

    def test_filter_by_status(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        result = filtered_orders(store=self.store, status=Order.Status.PROCESSING)
        self.assertEqual(list(result), [self.order])


class OrderStatusCountsTests(OrdersAdminServiceTestCase):
    def test_counts_include_total_under_empty_key(self):
        counts = order_status_counts(store=self.store)
        self.assertEqual(counts[""], 2)
        self.assertEqual(counts[Order.Status.PENDING], 2)

    def test_counts_reflect_status_change(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        counts = order_status_counts(store=self.store)
        self.assertEqual(counts[Order.Status.CANCELED], 1)
        self.assertEqual(counts[Order.Status.PENDING], 1)


class NextStatusOptionsTests(OrdersAdminServiceTestCase):
    def test_pending_offers_processing_and_canceled(self):
        options = dict(next_status_options(self.order))
        self.assertIn(Order.Status.PROCESSING, options)
        self.assertIn(Order.Status.CANCELED, options)

    def test_delivered_offers_nothing(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        self.assertEqual(next_status_options(self.order), [])


class OrderIsFinalTests(OrdersAdminServiceTestCase):
    def test_pending_is_not_final(self):
        self.assertFalse(order_is_final(self.order))

    def test_canceled_is_final(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.assertTrue(order_is_final(self.order))


class OrderStatusStepsTests(OrdersAdminServiceTestCase):
    def test_pending_marks_first_step_done_and_second_next(self):
        steps = order_status_steps(self.order)
        self.assertTrue(steps[0][2])  # pending itself is already done (registered)
        self.assertTrue(steps[1][3])  # processing is next-up
        self.assertFalse(steps[1][2])

    def test_processing_marks_pending_done(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        steps = order_status_steps(self.order)
        self.assertTrue(steps[0][2])
        self.assertTrue(steps[1][2])
        self.assertFalse(steps[2][2])

    def test_canceled_marks_nothing_done(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        steps = order_status_steps(self.order)
        self.assertFalse(any(done for _, _, done, _ in steps))


class FilteredInvoicesTests(OrdersAdminServiceTestCase):
    def test_filter_by_payment_status(self):
        result = filtered_invoices(store=self.store, status=Order.PaymentStatus.PAID)
        self.assertEqual(list(result), [self.order2])

    def test_no_filter_returns_all(self):
        result = filtered_invoices(store=self.store)
        self.assertEqual(set(result), {self.order, self.order2})


class InvoiceTotalsTests(OrdersAdminServiceTestCase):
    def test_totals_sum_grand_total(self):
        count, total = invoice_totals(filtered_invoices(store=self.store))
        self.assertEqual(count, 2)
        self.assertEqual(total, Decimal("300000"))


class FilteredTransactionsTests(OrdersAdminServiceTestCase):
    def test_filter_by_status(self):
        Transaction.objects.create(
            code="TX-11111", order=self.order, gateway=self.gateway,
            amount=Decimal("100000"), status=Transaction.Status.OK, ref_id="123456789",
        )
        Transaction.objects.create(
            code="TX-22222", order=self.order2, gateway=self.gateway,
            amount=Decimal("200000"), status=Transaction.Status.FAIL,
        )
        result = filtered_transactions(store=self.store, status=Transaction.Status.OK)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().code, "TX-11111")

    def test_no_filter_returns_all(self):
        Transaction.objects.create(
            code="TX-33333", order=self.order, gateway=self.gateway,
            amount=Decimal("100000"), status=Transaction.Status.PENDING,
        )
        self.assertEqual(filtered_transactions(store=self.store).count(), 1)
