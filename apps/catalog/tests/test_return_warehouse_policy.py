from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Category, Product, StockMovement, Vendor, WarehouseInventory
from apps.catalog.services.inventory_service import (
    InvalidRestockWarehouseError,
    restock_refund_item,
    restock_return_item,
)
from apps.catalog.services.warehouse_service import create_warehouse, provision_default_warehouse
from apps.customers.models import Customer
from apps.orders.models import (
    Order, OrderItem, PaymentGateway, Refund, RefundItem, ReturnItem, ReturnRequest, ShippingMethod,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ReturnWarehousePolicyTestCase(TestCase):
    """اثبات ADR-48: انتخابِ صریحِ مدیر > انبارِ تأمین‌کننده‌ی اصلی > انبارِ پیش‌فرض."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="09121500001", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="آرش نجفی", phone="09121500001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rwp")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-rwp")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کاپشن", slug="coat-rwp",
            sku="SKU-RWP1", price=Decimal("800000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rwp", cost=Decimal("50000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-rwp")
        self.default_warehouse = provision_default_warehouse(self.store)
        self.other_warehouse = create_warehouse(self.store, name="انبار دیگر", code="other-rwp")
        self.order = Order.objects.create(
            code="DM-RWP1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("800000"), grand_total=Decimal("850000"),
            payment_status=Order.PaymentStatus.PAID,
        )

    def _order_item(self, fulfillment_warehouse=None):
        return OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=1, unit_price=Decimal("800000"), line_total=Decimal("800000"),
            fulfillment_warehouse=fulfillment_warehouse,
        )

    def _return_item(self, order_item, *, restock_warehouse=None, quantity_received=1):
        return_request = ReturnRequest.objects.create(
            store=self.store, order=self.order, customer=self.customer,
            reason=ReturnRequest.Reason.DEFECTIVE_ITEM, status=ReturnRequest.Status.INSPECTED,
        )
        return ReturnItem.objects.create(
            return_request=return_request, order_item=order_item, quantity_requested=1,
            quantity_approved=1, quantity_received=quantity_received, is_restockable=True,
            restock_warehouse=restock_warehouse,
        )


class ReturnRestockWarehouseSelectionTests(ReturnWarehousePolicyTestCase):
    def test_falls_back_to_store_default_when_nothing_else_set(self):
        order_item = self._order_item(fulfillment_warehouse=None)
        return_item = self._return_item(order_item)
        movement = restock_return_item(store=self.store, return_item=return_item)
        self.assertEqual(movement.warehouse, self.default_warehouse)

    def test_uses_original_fulfillment_warehouse_when_no_explicit_choice(self):
        order_item = self._order_item(fulfillment_warehouse=self.other_warehouse)
        return_item = self._return_item(order_item, restock_warehouse=None)
        movement = restock_return_item(store=self.store, return_item=return_item)
        self.assertEqual(movement.warehouse, self.other_warehouse)

    def test_explicit_choice_wins_over_fulfillment_warehouse(self):
        third_warehouse = create_warehouse(self.store, name="انبار سوم", code="third-rwp")
        order_item = self._order_item(fulfillment_warehouse=self.other_warehouse)
        return_item = self._return_item(order_item, restock_warehouse=third_warehouse)
        movement = restock_return_item(store=self.store, return_item=return_item)
        self.assertEqual(movement.warehouse, third_warehouse)

    def test_rejects_explicit_warehouse_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rwp-other", status=Store.Status.ACTIVE)
        other_store_warehouse = create_warehouse(other_store, name="خارجی", code="foreign-rwp")
        order_item = self._order_item()
        return_item = self._return_item(order_item, restock_warehouse=other_store_warehouse)
        with self.assertRaises(InvalidRestockWarehouseError):
            restock_return_item(store=self.store, return_item=return_item)

    def test_rejects_archived_explicit_warehouse(self):
        from apps.catalog.services.warehouse_service import archive_warehouse
        archive_warehouse(self.other_warehouse)
        order_item = self._order_item()
        return_item = self._return_item(order_item, restock_warehouse=self.other_warehouse)
        with self.assertRaises(InvalidRestockWarehouseError):
            restock_return_item(store=self.store, return_item=return_item)

    def test_archived_fulfillment_warehouse_falls_back_to_default(self):
        from apps.catalog.services.warehouse_service import archive_warehouse
        order_item = self._order_item(fulfillment_warehouse=self.other_warehouse)
        archive_warehouse(self.other_warehouse)
        return_item = self._return_item(order_item, restock_warehouse=None)
        movement = restock_return_item(store=self.store, return_item=return_item)
        self.assertEqual(movement.warehouse, self.default_warehouse)

    def test_restock_updates_correct_warehouse_balance(self):
        WarehouseInventory.objects.create(
            store=self.store, warehouse=self.other_warehouse, product=self.product, on_hand=0,
        )
        order_item = self._order_item(fulfillment_warehouse=self.other_warehouse)
        return_item = self._return_item(order_item)
        restock_return_item(store=self.store, return_item=return_item)
        balance = WarehouseInventory.objects.get(warehouse=self.other_warehouse, product=self.product, variant=None)
        self.assertEqual(balance.on_hand, 1)


class RefundRestockWarehouseSelectionTests(ReturnWarehousePolicyTestCase):
    def _refund_item(self, order_item, quantity=1):
        refund = Refund.objects.create(
            store=self.store, order=self.order, requested_amount=Decimal("800000"),
            status=Refund.Status.APPROVED,
        )
        return RefundItem.objects.create(refund=refund, order_item=order_item, quantity=quantity, amount=Decimal("800000"))

    def test_falls_back_to_original_fulfillment_warehouse(self):
        order_item = self._order_item(fulfillment_warehouse=self.other_warehouse)
        refund_item = self._refund_item(order_item)
        movement = restock_refund_item(store=self.store, refund_item=refund_item)
        self.assertEqual(movement.warehouse, self.other_warehouse)

    def test_falls_back_to_store_default_without_fulfillment_warehouse(self):
        order_item = self._order_item(fulfillment_warehouse=None)
        refund_item = self._refund_item(order_item)
        movement = restock_refund_item(store=self.store, refund_item=refund_item)
        self.assertEqual(movement.warehouse, self.default_warehouse)


class InspectReturnItemsWarehouseSelectionTests(ReturnWarehousePolicyTestCase):
    def test_inspect_sets_explicit_restock_warehouse(self):
        from apps.orders.services.return_service import inspect_return_items

        order_item = self._order_item()
        return_request_obj = ReturnRequest.objects.create(
            store=self.store, order=self.order, customer=self.customer,
            reason=ReturnRequest.Reason.DEFECTIVE_ITEM, status=ReturnRequest.Status.RECEIVED,
        )
        item = ReturnItem.objects.create(
            return_request=return_request_obj, order_item=order_item, quantity_requested=1,
            quantity_approved=1, quantity_received=1,
        )
        inspect_return_items(
            return_request_obj, store=self.store, inspections=[{
                "item_id": item.pk, "is_restockable": True, "merchant_resolution": "refund",
                "restock_warehouse_id": str(self.other_warehouse.pk),
            }],
        )
        item.refresh_from_db()
        self.assertEqual(item.restock_warehouse_id, self.other_warehouse.pk)

    def test_inspect_rejects_warehouse_from_other_store(self):
        from apps.orders.services.return_service import inspect_return_items

        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rwp-inspect-other", status=Store.Status.ACTIVE)
        foreign_warehouse = create_warehouse(other_store, name="خارجی", code="foreign-inspect-rwp")
        order_item = self._order_item()
        return_request_obj = ReturnRequest.objects.create(
            store=self.store, order=self.order, customer=self.customer,
            reason=ReturnRequest.Reason.DEFECTIVE_ITEM, status=ReturnRequest.Status.RECEIVED,
        )
        item = ReturnItem.objects.create(
            return_request=return_request_obj, order_item=order_item, quantity_requested=1,
            quantity_approved=1, quantity_received=1,
        )
        inspect_return_items(
            return_request_obj, store=self.store, inspections=[{
                "item_id": item.pk, "is_restockable": True, "merchant_resolution": "refund",
                "restock_warehouse_id": str(foreign_warehouse.pk),
            }],
        )
        item.refresh_from_db()
        # Store-scoped lookup silently finds nothing for a foreign warehouse id — falls back to None (auto policy).
        self.assertIsNone(item.restock_warehouse_id)
