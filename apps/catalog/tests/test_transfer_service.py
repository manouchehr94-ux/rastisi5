from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import (
    Category,
    Product,
    StockMovement,
    Vendor,
    WarehouseInventory,
    WarehouseTransfer,
)
from apps.catalog.services.transfer_service import (
    TransferError,
    cancel_transfer,
    create_transfer,
    receive_transfer,
    request_transfer,
    ship_transfer,
)
from apps.catalog.services.warehouse_service import create_warehouse, provision_default_warehouse
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class TransferServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-trf")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-trf")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-trf",
            sku="SKU-TRF1", price=Decimal("200000"), stock=10,
        )
        self.source = provision_default_warehouse(self.store)
        self.destination = create_warehouse(self.store, name="انبار شمال", code="north-trf")
        WarehouseInventory.objects.create(
            store=self.store, warehouse=self.source, product=self.product, variant=None, on_hand=10,
        )

    def _new_transfer(self, quantity=4):
        return create_transfer(
            self.store, source_warehouse=self.source, destination_warehouse=self.destination,
            items=[{"product": self.product, "quantity": quantity}],
        )


class CreateTransferTests(TransferServiceTestCase):
    def test_creates_draft_transfer_with_items(self):
        transfer = self._new_transfer(4)
        self.assertEqual(transfer.status, WarehouseTransfer.Status.DRAFT)
        self.assertEqual(transfer.items.count(), 1)

    def test_rejects_empty_items(self):
        with self.assertRaises(TransferError):
            create_transfer(
                self.store, source_warehouse=self.source, destination_warehouse=self.destination, items=[],
            )

    def test_rejects_same_source_and_destination(self):
        with self.assertRaises(TransferError):
            create_transfer(
                self.store, source_warehouse=self.source, destination_warehouse=self.source,
                items=[{"product": self.product, "quantity": 1}],
            )

    def test_rejects_warehouse_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="trf-other", status=Store.Status.ACTIVE)
        other_warehouse = provision_default_warehouse(other_store)
        with self.assertRaises(TransferError):
            create_transfer(
                self.store, source_warehouse=self.source, destination_warehouse=other_warehouse,
                items=[{"product": self.product, "quantity": 1}],
            )

    def test_transfer_numbers_are_sequential_per_store(self):
        first = self._new_transfer(1)
        second = self._new_transfer(1)
        self.assertNotEqual(first.transfer_number, second.transfer_number)


class TransferLifecycleTests(TransferServiceTestCase):
    def test_full_happy_path_moves_balance(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.IN_TRANSIT)

        source_balance = WarehouseInventory.objects.get(warehouse=self.source, product=self.product, variant=None)
        self.assertEqual(source_balance.on_hand, 6)

        receive_transfer(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.RECEIVED)
        destination_balance = WarehouseInventory.objects.get(
            warehouse=self.destination, product=self.product, variant=None,
        )
        self.assertEqual(destination_balance.on_hand, 4)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # aggregate stock unaffected by internal transfer (ADR-40)

    def test_ship_writes_transfer_out_movement(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        movement = StockMovement.objects.get(reason=StockMovement.Reason.WAREHOUSE_TRANSFER_OUT)
        self.assertEqual(movement.delta, -4)
        self.assertEqual(movement.warehouse, self.source)

    def test_receive_writes_transfer_in_movement(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        receive_transfer(transfer)
        movement = StockMovement.objects.get(reason=StockMovement.Reason.WAREHOUSE_TRANSFER_IN)
        self.assertEqual(movement.delta, 4)
        self.assertEqual(movement.warehouse, self.destination)

    def test_ship_rejects_insufficient_source_balance(self):
        transfer = self._new_transfer(999)
        request_transfer(transfer)
        with self.assertRaises(TransferError):
            ship_transfer(transfer)

    def test_cannot_ship_a_draft_transfer(self):
        transfer = self._new_transfer(4)
        with self.assertRaises(TransferError):
            ship_transfer(transfer)

    def test_ship_is_not_retryable_after_success(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        with self.assertRaises(TransferError):
            ship_transfer(transfer)
        source_balance = WarehouseInventory.objects.get(warehouse=self.source, product=self.product, variant=None)
        self.assertEqual(source_balance.on_hand, 6)  # not double-decremented

    def test_receive_is_not_retryable_after_success(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        receive_transfer(transfer)
        with self.assertRaises(TransferError):
            receive_transfer(transfer)
        destination_balance = WarehouseInventory.objects.get(
            warehouse=self.destination, product=self.product, variant=None,
        )
        self.assertEqual(destination_balance.on_hand, 4)  # not double-incremented


class CancelTransferTests(TransferServiceTestCase):
    def test_cancel_from_draft_touches_no_inventory(self):
        transfer = self._new_transfer(4)
        cancel_transfer(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.CANCELLED)
        source_balance = WarehouseInventory.objects.get(warehouse=self.source, product=self.product, variant=None)
        self.assertEqual(source_balance.on_hand, 10)

    def test_cancel_in_transit_restores_source_balance(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        cancel_transfer(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.CANCELLED)
        source_balance = WarehouseInventory.objects.get(warehouse=self.source, product=self.product, variant=None)
        self.assertEqual(source_balance.on_hand, 10)

    def test_cannot_cancel_received_transfer(self):
        transfer = self._new_transfer(4)
        request_transfer(transfer)
        ship_transfer(transfer)
        receive_transfer(transfer)
        with self.assertRaises(TransferError):
            cancel_transfer(transfer)
