"""Tests for ``apps.catalog.services.inventory_service.adjust_warehouse_stock``
— the checkpoint 4B addition that lets a specific (non-default) Warehouse's
``WarehouseInventory.on_hand`` be adjusted while keeping
``Product.stock``/``ProductVariant.stock`` (the aggregate, ADR-38) and the
``StockMovement`` ledger consistent, with reservation safety (ADR-60)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import (
    Category,
    InventoryReservation,
    Product,
    StockMovement,
    Vendor,
    Warehouse,
    WarehouseInventory,
)
from apps.catalog.services.inventory_service import (
    InsufficientStockError,
    InvalidRestockWarehouseError,
    adjust_warehouse_stock,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class AdjustWarehouseStockTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-aws")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-aws")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="prod-aws",
            sku="SKU-AWS1", price=Decimal("100000"), stock=0,
        )
        self.default_warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()
        self.other_warehouse = Warehouse.objects.create(
            store=self.store, name="انبارِ دوم", code="second-aws",
        )
        self.actor = User.objects.create_user(username="09121299001", password="p", is_staff=True)


class AdjustmentModeTests(AdjustWarehouseStockTestCase):
    def test_positive_adjustment_increases_aggregate_and_warehouse_balance(self):
        movement = adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product, variant=None,
            mode="adjustment", quantity=10, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(movement.delta, 10)
        self.assertEqual(movement.warehouse, self.other_warehouse)
        balance = WarehouseInventory.objects.get(store=self.store, warehouse=self.other_warehouse, product=self.product)
        self.assertEqual(balance.on_hand, 10)

    def test_negative_adjustment_decreases_aggregate(self):
        adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="adjustment", quantity=20, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="adjustment", quantity=-5, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)

    def test_adjustment_below_zero_aggregate_rejected(self):
        with self.assertRaises(InsufficientStockError):
            adjust_warehouse_stock(
                store=self.store, warehouse=self.other_warehouse, product=self.product,
                mode="adjustment", quantity=-1, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
            )

    def test_zero_delta_is_noop_and_creates_no_movement(self):
        result = adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="adjustment", quantity=0, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        self.assertIsNone(result)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 0)


class SetOnHandModeTests(AdjustWarehouseStockTestCase):
    def test_set_on_hand_computes_delta_from_that_warehouse(self):
        adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="adjustment", quantity=5, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="set_on_hand", quantity=8, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        balance = WarehouseInventory.objects.get(store=self.store, warehouse=self.other_warehouse, product=self.product)
        self.assertEqual(balance.on_hand, 8)

    def test_set_on_hand_does_not_affect_other_warehouses_balance(self):
        adjust_warehouse_stock(
            store=self.store, warehouse=self.default_warehouse, product=self.product,
            mode="adjustment", quantity=10, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        adjust_warehouse_stock(
            store=self.store, warehouse=self.other_warehouse, product=self.product,
            mode="set_on_hand", quantity=3, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        default_balance = WarehouseInventory.objects.get(store=self.store, warehouse=self.default_warehouse, product=self.product)
        self.assertEqual(default_balance.on_hand, 10)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 13)

    def test_negative_set_on_hand_rejected(self):
        with self.assertRaises(ValueError):
            adjust_warehouse_stock(
                store=self.store, warehouse=self.other_warehouse, product=self.product,
                mode="set_on_hand", quantity=-1, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
            )


class ReservationSafetyTests(AdjustWarehouseStockTestCase):
    def setUp(self):
        super().setUp()
        adjust_warehouse_stock(
            store=self.store, warehouse=self.default_warehouse, product=self.product,
            mode="adjustment", quantity=10, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        InventoryReservation.objects.create(
            store=self.store, product=self.product, variant=None, quantity=7,
            status=InventoryReservation.Status.ACTIVE,
        )

    def test_reduction_below_active_reservation_rejected(self):
        with self.assertRaises(InsufficientStockError):
            adjust_warehouse_stock(
                store=self.store, warehouse=self.default_warehouse, product=self.product,
                mode="adjustment", quantity=-5, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_reduction_down_to_exact_reserved_quantity_allowed(self):
        adjust_warehouse_stock(
            store=self.store, warehouse=self.default_warehouse, product=self.product,
            mode="adjustment", quantity=-3, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_set_on_hand_below_reservation_rejected(self):
        with self.assertRaises(InsufficientStockError):
            adjust_warehouse_stock(
                store=self.store, warehouse=self.default_warehouse, product=self.product,
                mode="set_on_hand", quantity=2, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
            )


class TenantIsolationTests(AdjustWarehouseStockTestCase):
    def test_foreign_warehouse_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="aws-other-store")
        foreign_warehouse = Warehouse.objects.create(store=other_store, name="خارجی", code="foreign-aws")
        with self.assertRaises(InvalidRestockWarehouseError):
            adjust_warehouse_stock(
                store=self.store, warehouse=foreign_warehouse, product=self.product,
                mode="adjustment", quantity=1, reason=StockMovement.Reason.IMPORT_ADJUSTMENT, actor=self.actor,
            )
