from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, InventoryReservation, Product, Vendor, WarehouseInventory
from apps.catalog.services.reservation_service import reserve_inventory
from apps.catalog.services.warehouse_service import provision_default_warehouse
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ExpireInventoryReservationsCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cmd")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-cmd")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-cmd",
            sku="SKU-CMD1", price=Decimal("200000"), stock=10,
        )

    def test_expires_due_reservations(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=2, ttl_minutes=10)
        InventoryReservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        out = StringIO()
        call_command("expire_inventory_reservations", stdout=out)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, InventoryReservation.Status.EXPIRED)
        self.assertIn("1", out.getvalue())

    def test_no_expired_reservations_reports_zero(self):
        reserve_inventory(store=self.store, product=self.product, quantity=1, ttl_minutes=10)
        out = StringIO()
        call_command("expire_inventory_reservations", stdout=out)
        self.assertIn("0", out.getvalue())


class VerifyInventoryConsistencyCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cmd2")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-cmd2")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-cmd2",
            sku="SKU-CMD2", price=Decimal("200000"), stock=10,
        )
        self.warehouse = provision_default_warehouse(self.store)

    def test_reports_success_when_consistent(self):
        WarehouseInventory.objects.create(store=self.store, warehouse=self.warehouse, product=self.product, on_hand=10)
        out = StringIO()
        call_command("verify_inventory_consistency", stdout=out)
        self.assertIn("سازگار", out.getvalue())

    def test_reports_mismatch_when_totals_differ(self):
        WarehouseInventory.objects.create(store=self.store, warehouse=self.warehouse, product=self.product, on_hand=3)
        out = StringIO()
        call_command("verify_inventory_consistency", stdout=out)
        self.assertIn("ناسازگاری", out.getvalue())

    def test_strict_mode_raises_on_mismatch(self):
        WarehouseInventory.objects.create(store=self.store, warehouse=self.warehouse, product=self.product, on_hand=3)
        with self.assertRaises(SystemExit):
            call_command("verify_inventory_consistency", "--strict", stdout=StringIO())

    def test_strict_mode_passes_when_consistent(self):
        WarehouseInventory.objects.create(store=self.store, warehouse=self.warehouse, product=self.product, on_hand=10)
        call_command("verify_inventory_consistency", "--strict", stdout=StringIO())

    def test_json_output_lists_mismatches(self):
        WarehouseInventory.objects.create(store=self.store, warehouse=self.warehouse, product=self.product, on_hand=3)
        out = StringIO()
        call_command("verify_inventory_consistency", "--json", stdout=out)
        self.assertIn("product_stock", out.getvalue())

    def test_missing_warehouse_balance_counts_as_zero(self):
        # هیچ WarehouseInventory ثبت نشده اما Product.stock=10 است — ناسازگاری باید گزارش شود.
        out = StringIO()
        call_command("verify_inventory_consistency", stdout=out)
        self.assertIn("ناسازگاری", out.getvalue())
