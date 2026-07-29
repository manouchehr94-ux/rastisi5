from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor, Warehouse, WarehouseInventory
from apps.catalog.services.warehouse_service import (
    WarehouseError,
    archive_warehouse,
    create_warehouse,
    provision_default_warehouse,
    set_default_warehouse,
    update_warehouse,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProvisionDefaultWarehouseTests(TestCase):
    def test_creates_default_warehouse_for_new_store(self):
        store = _akhlaghi()
        warehouse = provision_default_warehouse(store)
        self.assertTrue(warehouse.is_default)
        self.assertEqual(Warehouse.objects.filter(store=store, is_default=True).count(), 1)

    def test_idempotent_does_not_create_duplicate(self):
        store = _akhlaghi()
        first = provision_default_warehouse(store)
        second = provision_default_warehouse(store)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Warehouse.objects.filter(store=store).count(), 1)


class ProvisionDefaultWarehousesCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-wh")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-wh")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="لپ‌تاپ", slug="laptop-wh",
            sku="SKU-WH1", price=Decimal("30000000"), stock=7,
        )

    def test_command_creates_balance_matching_existing_stock(self):
        call_command("provision_default_warehouses")
        warehouse = Warehouse.objects.get(store=self.store, is_default=True)
        balance = WarehouseInventory.objects.get(warehouse=warehouse, product=self.product, variant=None)
        self.assertEqual(balance.on_hand, 7)

    def test_command_is_idempotent(self):
        call_command("provision_default_warehouses")
        call_command("provision_default_warehouses")
        warehouse = Warehouse.objects.get(store=self.store, is_default=True)
        self.assertEqual(
            WarehouseInventory.objects.filter(warehouse=warehouse, product=self.product).count(), 1,
        )

    def test_command_does_not_change_existing_stock(self):
        call_command("provision_default_warehouses")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)


class CreateWarehouseTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_creates_non_default_warehouse(self):
        warehouse = create_warehouse(self.store, name="انبار شمال", code="north")
        self.assertFalse(warehouse.is_default)

    def test_creating_second_default_clears_first(self):
        first = provision_default_warehouse(self.store)
        second = create_warehouse(self.store, name="انبار شمال", code="north", is_default=True)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_duplicate_code_in_same_store_rejected(self):
        create_warehouse(self.store, name="انبار الف", code="alpha")
        with self.assertRaises(WarehouseError):
            create_warehouse(self.store, name="انبار ب", code="alpha")

    def test_same_code_allowed_in_different_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-other", status=Store.Status.ACTIVE)
        create_warehouse(self.store, name="انبار الف", code="alpha")
        warehouse = create_warehouse(other_store, name="انبار ب", code="alpha")
        self.assertIsNotNone(warehouse.pk)


class WarehouseLifecycleTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.default = provision_default_warehouse(self.store)
        self.secondary = create_warehouse(self.store, name="انبار شمال", code="north")

    def test_set_default_switches_default(self):
        set_default_warehouse(self.secondary)
        self.default.refresh_from_db()
        self.secondary.refresh_from_db()
        self.assertFalse(self.default.is_default)
        self.assertTrue(self.secondary.is_default)

    def test_cannot_set_inactive_warehouse_as_default(self):
        self.secondary.is_active = False
        self.secondary.save(update_fields=["is_active"])
        with self.assertRaises(WarehouseError):
            set_default_warehouse(self.secondary)

    def test_cannot_archive_default_warehouse(self):
        with self.assertRaises(WarehouseError):
            archive_warehouse(self.default)

    def test_archive_non_default_warehouse(self):
        archive_warehouse(self.secondary)
        self.secondary.refresh_from_db()
        self.assertFalse(self.secondary.is_active)

    def test_update_warehouse_fields(self):
        update_warehouse(self.secondary, name="انبار جدید", city="تبریز")
        self.secondary.refresh_from_db()
        self.assertEqual(self.secondary.name, "انبار جدید")
        self.assertEqual(self.secondary.city, "تبریز")
