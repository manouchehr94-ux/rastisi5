"""Tests for the checkpoint 4B Inventory Import service — every successful
row routes through inventory_service.adjust_warehouse_stock (StockMovement
created, aggregate stock kept consistent, reservation-safety enforced);
the import service never writes WarehouseInventory/Product.stock/
ProductVariant.stock directly (ADR-60)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import (
    Category,
    InventoryReservation,
    Product,
    ProductVariant,
    StockMovement,
    Vendor,
    Warehouse,
    WarehouseInventory,
)
from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv_upload(text: str, name="inventory.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


INV_HEADER = "warehouse_code,product_id,product_sku,variant_id,variant_sku,mode,quantity,reason,note\n"


class InventoryImportTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-iimp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-iimp")
        self.actor = User.objects.create_user(username="iimp-owner", password="p", is_staff=True)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="prod-iimp", sku="SKU-IIMP-1", price=Decimal("100000"), stock=0,
        )
        self.warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()

    def _job(self, csv_text, *, mode=ImportJob.Mode.UPSERT, idempotency_key=""):
        return import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.INVENTORY, uploaded_file=_csv_upload(csv_text),
            mode=mode, requested_by=self.actor, idempotency_key=idempotency_key,
        )


class AdjustmentTests(InventoryImportTestCase):
    def test_positive_adjustment_creates_stock_movement(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,10,شمارشِ سالانه,اتاقِ ۲\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.updated_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        movement = StockMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, 10)
        self.assertEqual(movement.warehouse, self.warehouse)
        self.assertEqual(movement.actor, self.actor)
        self.assertEqual(movement.reason, StockMovement.Reason.IMPORT_ADJUSTMENT)
        self.assertIn("شمارشِ سالانه", movement.note)

    def test_negative_adjustment(self):
        csv_text = INV_HEADER + (
            f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,20,,\n"
            f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,-5,,\n"
        )
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)

    def test_persian_digit_quantity_normalized(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,۱۲,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 12)


class SetOnHandTests(InventoryImportTestCase):
    def test_set_on_hand_computes_delta(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,25,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)

    def test_negative_set_on_hand_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,-3,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_zero_delta_skipped(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,0,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.skipped_rows, 1)


class VariantInventoryTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        self.variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز",
            sku="VAR-IIMP-1", stock=0,
        )

    def test_variant_inventory_adjustment(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,VAR-IIMP-1,adjustment,6,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 6)
        movement = StockMovement.objects.get(variant=self.variant)
        self.assertEqual(movement.delta, 6)

    def test_variant_belonging_to_other_product_rejected(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="دیگر",
            slug="other-iimp", sku="SKU-IIMP-2", price=Decimal("1"), stock=0,
        )
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-2,,VAR-IIMP-1,adjustment,1,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)


class ReservationSafetyTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        # Seed 10 on-hand via an import, then reserve 7.
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,10,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        InventoryReservation.objects.create(
            store=self.store, product=self.product, variant=None, quantity=7,
            status=InventoryReservation.Status.ACTIVE,
        )

    def test_reduction_below_active_reservation_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,-5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.failed_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_set_on_hand_below_reservation_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,3,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.failed_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_reduction_to_exactly_reserved_allowed(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,set_on_hand,7,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)


class ValidationTests(InventoryImportTestCase):
    def test_missing_warehouse_rejected(self):
        csv_text = INV_HEADER + ",,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_unknown_warehouse_rejected(self):
        csv_text = INV_HEADER + "no-such-wh,,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_missing_product_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_mode_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,teleport,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_non_numeric_quantity_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,abc,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_dry_run_does_not_change_stock(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())


class ReplayTests(InventoryImportTestCase):
    def test_completed_job_cannot_replay(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # not applied twice


class TenantIsolationTests(InventoryImportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="iimp-other-store")
        self.foreign_warehouse = Warehouse.objects.create(store=self.other_store, name="خارجی", code="foreign-wh-iimp")
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-iimp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-iimp")
        self.foreign_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category, name="خارجی",
            slug="foreign-prod-iimp", sku="SKU-FOREIGN-IIMP", price=Decimal("1"), stock=0,
        )

    def test_foreign_warehouse_rejected(self):
        csv_text = INV_HEADER + f"foreign-wh-iimp,,SKU-IIMP-1,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_foreign_product_id_rejected(self):
        csv_text = INV_HEADER + f"{self.warehouse.code},{self.foreign_product.pk},,,,adjustment,5,,\n"
        job = self._job(csv_text)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.stock, 0)
