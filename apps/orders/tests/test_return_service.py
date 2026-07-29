from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Category, Product, StockMovement, Vendor
from apps.customers.models import Customer
from apps.orders.models import (
    Order, OrderItem, PaymentGateway, Refund, ReturnItem, ReturnRequest, ShippingMethod,
)
from apps.orders.services.return_service import (
    ReturnError,
    approve_return_request,
    complete_return,
    create_return_request,
    inspect_return_items,
    mark_return_received,
    reject_return_request,
    review_return_request,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ReturnServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="09121400001", password="pass12345")
        self.staff = User.objects.create_user(username="09121400099", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="نگار احمدی", phone="09121400001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rt")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-rt")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کاپشن", slug="coat-rt",
            sku="SKU-RT1", price=Decimal("800000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rt", cost=Decimal("50000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-rt")
        self.order = Order.objects.create(
            code="DM-RT1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("1600000"), grand_total=Decimal("1650000"),
            payment_status=Order.PaymentStatus.PAID,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("800000"), line_total=Decimal("1600000"),
        )

    def _create(self, quantity=1):
        return create_return_request(
            self.order, store=self.store, customer=self.customer, reason=ReturnRequest.Reason.DEFECTIVE_ITEM,
            line_requests=[{"order_item_id": self.item.pk, "quantity": quantity}], actor=self.staff,
        )


class CreateReturnRequestTests(ReturnServiceTestCase):
    def test_creates_request_with_items(self):
        rr = self._create(quantity=1)
        self.assertEqual(rr.status, ReturnRequest.Status.REQUESTED)
        self.assertEqual(rr.items.count(), 1)
        self.assertTrue(rr.return_number.startswith("RET-"))

    def test_excess_quantity_rejected(self):
        with self.assertRaises(ReturnError):
            self._create(quantity=3)

    def test_wrong_store_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rt-other", status=Store.Status.ACTIVE)
        with self.assertRaises(ReturnError):
            create_return_request(
                self.order, store=other_store, customer=self.customer, reason=ReturnRequest.Reason.OTHER,
                line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
            )

    def test_multiple_returns_on_one_order_item_respect_remaining_quantity(self):
        self._create(quantity=1)
        # one more unit is still available
        second = self._create(quantity=1)
        self.assertIsNotNone(second)
        with self.assertRaises(ReturnError):
            self._create(quantity=1)  # nothing left now

    def test_rejected_return_frees_up_quantity_for_a_new_request(self):
        first = self._create(quantity=2)
        reject_return_request(first, store=self.store, actor=self.staff, rejection_reason="کالای اصلی گم شده")
        second = self._create(quantity=2)  # should be allowed again
        self.assertIsNotNone(second)


class TransitionTests(ReturnServiceTestCase):
    def test_full_happy_path(self):
        rr = self._create(quantity=2)
        review_return_request(rr, store=self.store, actor=self.staff)
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.UNDER_REVIEW)

        approve_return_request(rr, store=self.store, actor=self.staff)
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.APPROVED)
        item = rr.items.first()
        self.assertEqual(item.quantity_approved, 2)

        mark_return_received(rr, store=self.store, actor=self.staff)
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.RECEIVED)

        inspect_return_items(rr, store=self.store, actor=self.staff, inspections=[
            {"item_id": item.pk, "condition": "opened", "is_restockable": True, "merchant_resolution": "refund"},
        ])
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.INSPECTED)

        complete_return(rr, store=self.store, actor=self.staff)
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.COMPLETED)
        self.assertIsNotNone(rr.completed_at)

    def test_illegal_transition_rejected(self):
        rr = self._create(quantity=1)
        with self.assertRaises(ReturnError):
            mark_return_received(rr, store=self.store, actor=self.staff)  # cannot skip straight to received

    def test_cannot_transition_final_status(self):
        rr = self._create(quantity=1)
        reject_return_request(rr, store=self.store, actor=self.staff, rejection_reason="نامعتبر")
        with self.assertRaises(ReturnError):
            review_return_request(rr, store=self.store, actor=self.staff)

    def test_wrong_store_cannot_transition(self):
        rr = self._create(quantity=1)
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rt-other2", status=Store.Status.ACTIVE)
        with self.assertRaises(ReturnError):
            review_return_request(rr, store=other_store, actor=self.staff)

    def test_reject_requires_reason(self):
        rr = self._create(quantity=1)
        with self.assertRaises(ReturnError):
            reject_return_request(rr, store=self.store, actor=self.staff, rejection_reason="")

    def test_approve_cannot_exceed_requested_quantity(self):
        rr = self._create(quantity=1)
        item = rr.items.first()
        with self.assertRaises(ReturnError):
            approve_return_request(rr, store=self.store, actor=self.staff, approved_quantities={item.pk: 5})


class InventoryIntegrationTests(ReturnServiceTestCase):
    def _full_flow_to_inspected(self, quantity=1, is_restockable=True, resolution="refund"):
        rr = self._create(quantity=quantity)
        review_return_request(rr, store=self.store, actor=self.staff)
        approve_return_request(rr, store=self.store, actor=self.staff)
        mark_return_received(rr, store=self.store, actor=self.staff)
        item = rr.items.first()
        inspect_return_items(rr, store=self.store, actor=self.staff, inspections=[
            {"item_id": item.pk, "is_restockable": is_restockable, "merchant_resolution": resolution},
        ])
        return rr

    def test_restockable_item_restocks_on_complete(self):
        self.product.stock = 3
        self.product.save(update_fields=["stock"])
        rr = self._full_flow_to_inspected(quantity=1)
        complete_return(rr, store=self.store, actor=self.staff)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertTrue(StockMovement.objects.filter(reason=StockMovement.Reason.RETURN_RESTOCK).exists())

    def test_non_restockable_item_does_not_restock(self):
        self.product.stock = 3
        self.product.save(update_fields=["stock"])
        rr = self._full_flow_to_inspected(quantity=1, is_restockable=False, resolution="reject")
        complete_return(rr, store=self.store, actor=self.staff, create_refund=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_duplicate_completion_does_not_double_restock(self):
        self.product.stock = 3
        self.product.save(update_fields=["stock"])
        rr = self._full_flow_to_inspected(quantity=1)
        complete_return(rr, store=self.store, actor=self.staff)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(StockMovement.objects.filter(reason=StockMovement.Reason.RETURN_RESTOCK).count(), 1)

    def test_complete_with_refund_resolution_creates_refund(self):
        rr = self._full_flow_to_inspected(quantity=1, resolution="refund")
        complete_return(rr, store=self.store, actor=self.staff)
        rr.refresh_from_db()
        self.assertIsNotNone(rr.refund)
        self.assertEqual(rr.refund.status, Refund.Status.SUCCEEDED)
        self.assertEqual(rr.refund.approved_amount, Decimal("800000"))
