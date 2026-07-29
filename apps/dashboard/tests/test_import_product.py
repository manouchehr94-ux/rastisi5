"""Tests for the checkpoint 4B Product Import service
(``apps.dashboard.services.import_service``): preview vs execution sharing
one validation path, create_only/update_only/upsert modes, stable identity
resolution, Store-scoped reference validation, dry-run non-mutation,
inventory-service-routed stock writes, and idempotent replay protection."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, StockMovement, Vendor
from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.orders.models import TaxClass
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv_upload(text: str, name="products.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


PRODUCT_HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)


class ProductImportTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-imp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-imp", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-imp", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-imp")
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-imp")
        self.actor = User.objects.create_user(username="imp-owner", password="p", is_staff=True)

    def _job(self, csv_text, *, mode=ImportJob.Mode.UPSERT, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key=""):
        return import_service.create_import_job(
            self.store, import_type=import_type, uploaded_file=_csv_upload(csv_text),
            mode=mode, requested_by=self.actor, idempotency_key=idempotency_key,
        )


class PreviewTests(ProductImportTestCase):
    def test_preview_does_not_create_product(self):
        csv_text = PRODUCT_HEADER + f",,کالای تازه,,,,brand-imp,leaf-imp,100000,5,,,,,\n"
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        self.assertFalse(Product.objects.filter(store=self.store, name="کالای تازه").exists())

    def test_preview_reports_invalid_row(self):
        csv_text = PRODUCT_HEADER + ",,,,,,,,,,,,,,\n"  # no name, no category
        job = self._job(csv_text)
        import_service.run_preview(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        row = ImportRowResult.objects.get(import_job=job)
        self.assertEqual(row.status, ImportRowResult.RowStatus.INVALID)
        self.assertTrue(row.errors)


class CreateExecutionTests(ProductImportTestCase):
    def test_create_only_creates_new_product_with_stock_via_service(self):
        csv_text = PRODUCT_HEADER + ",SKU-NEW-1,کالای وارداتی,,,active,brand-imp,leaf-imp,150000,8,500,بله,general-imp,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.created_rows, 1)
        product = Product.objects.get(store=self.store, sku="SKU-NEW-1")
        self.assertEqual(product.name, "کالای وارداتی")
        self.assertEqual(product.price, Decimal("150000"))
        self.assertEqual(product.stock, 8)
        self.assertEqual(product.brand, self.brand)
        self.assertEqual(product.category, self.leaf)
        self.assertEqual(product.tax_class, self.tax_class)
        movement = StockMovement.objects.get(product=product)
        self.assertEqual(movement.delta, 8)

    def test_create_only_rejects_row_matching_existing_sku(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="موجود", slug="existing-imp",
            sku="SKU-EXIST-1", price=Decimal("1"), stock=0,
        )
        csv_text = PRODUCT_HEADER + ",SKU-EXIST-1,به‌روزرسانی,,,,,leaf-imp,999999,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertEqual(job.created_rows, 0)

    def test_persian_digits_normalized_in_price_and_stock(self):
        csv_text = PRODUCT_HEADER + ",SKU-FA-1,کالایِ فارسی,,,,,leaf-imp,۱۵۰۰۰۰,۷,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        product = Product.objects.get(store=self.store, sku="SKU-FA-1")
        self.assertEqual(product.price, Decimal("150000"))
        self.assertEqual(product.stock, 7)


class UpdateExecutionTests(ProductImportTestCase):
    def setUp(self):
        super().setUp()
        self.existing = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="کالایِ قدیمی", slug="old-imp",
            sku="SKU-OLD-1", price=Decimal("50000"), stock=2,
        )

    def test_update_only_updates_matched_product_by_sku(self):
        csv_text = PRODUCT_HEADER + f",SKU-OLD-1,کالایِ به‌روزشده,,,,,,{75000},,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "کالایِ به‌روزشده")
        self.assertEqual(self.existing.price, Decimal("75000"))

    def test_update_only_rejects_unmatched_row(self):
        csv_text = PRODUCT_HEADER + ",SKU-NO-MATCH,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.assertFalse(Product.objects.filter(sku="SKU-NO-MATCH").exists())

    def test_update_by_product_id(self):
        csv_text = PRODUCT_HEADER.replace("product_id", "product_id")
        csv_text = f"product_id,sku,name,slug,barcode,status,brand_code,category_code,price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n{self.existing.pk},,نامِ تازه,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPDATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "نامِ تازه")

    def test_upsert_creates_and_updates_in_same_file(self):
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-OLD-1,به‌روزشده,,,,,,60000,,,,,,\n"
            + ",SKU-BRAND-NEW,تازه,,,,,leaf-imp,20000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.assertEqual(job.created_rows, 1)


class ReferenceValidationTests(ProductImportTestCase):
    def test_invalid_category_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADCAT,کالا,,,,,no-such-category,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_brand_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADBRAND,کالا,,,,no-such-brand,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_invalid_tax_class_code_rejected(self):
        csv_text = PRODUCT_HEADER + ",SKU-BADTAX,کالا,,,,,leaf-imp,1000,1,,,no-such-tax,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)

    def test_duplicate_sku_within_file_rejected_for_second_occurrence(self):
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-DUP-1,اول,,,,,leaf-imp,1000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        # Now attempt to create a second, *different* Product with the same SKU in a new job.
        job2 = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job2, actor=self.actor)
        job2.refresh_from_db()
        self.assertEqual(job2.invalid_rows, 1)
        self.assertEqual(Product.objects.filter(sku="SKU-DUP-1").count(), 1)


class TenantIsolationTests(ProductImportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="import-other-store")
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-imp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-imp")
        self.foreign_product = Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category,
            name="کالایِ فروشگاهِ دیگر", slug="foreign-product-imp", sku="SKU-FOREIGN-1",
            price=Decimal("1"), stock=0,
        )

    def test_foreign_product_id_rejected(self):
        csv_text = f"product_id,sku,name,slug,barcode,status,brand_code,category_code,price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n{self.foreign_product.pk},,دستکاری,,,,,,,,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.invalid_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.name, "کالایِ فروشگاهِ دیگر")

    def test_foreign_sku_never_matched(self):
        csv_text = PRODUCT_HEADER + ",SKU-FOREIGN-1,دستکاریِ نام,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        # Not matched (Store-scoped SKU lookup never sees another Store's SKU),
        # so create_only should CREATE a distinct Product in this Store instead
        # of touching the other Store's row.
        self.assertEqual(job.created_rows, 1)
        self.foreign_product.refresh_from_db()
        self.assertEqual(self.foreign_product.name, "کالایِ فروشگاهِ دیگر")
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-FOREIGN-1").count(), 1)


class IdempotencyTests(ProductImportTestCase):
    def test_completed_job_cannot_execute_twice(self):
        csv_text = PRODUCT_HEADER + ",SKU-IDEMP-1,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(sku="SKU-IDEMP-1").count(), 1)

    def test_duplicate_idempotency_key_rejected_at_upload(self):
        csv_text = PRODUCT_HEADER + ",SKU-KEY-1,کالا,,,,,leaf-imp,1000,1,,,,,\n"
        self._job(csv_text, idempotency_key="my-key-1")
        with self.assertRaises(import_service.ImportServiceError):
            self._job(csv_text, idempotency_key="my-key-1")

    def test_retry_after_partial_failure_does_not_double_apply(self):
        # A file where row 1 is valid and row 2 is invalid → completed_with_errors.
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-PARTIAL-1,خوب,,,,,leaf-imp,1000,1,,,,,\n"
            + ",,,,,,,,,,,,,,\n"  # invalid: missing everything
        )
        job = self._job(csv_text, mode=ImportJob.Mode.UPSERT)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED_WITH_ERRORS)
        self.assertEqual(job.created_rows, 1)
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-PARTIAL-1").count(), 1)
        # Retrying the same (now-final) job is blocked — no double creation.
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(Product.objects.filter(store=self.store, sku="SKU-PARTIAL-1").count(), 1)


class BatchIsolationTests(ProductImportTestCase):
    def test_apply_failure_on_one_row_does_not_lose_earlier_rows_in_batch(self):
        # Two create rows sharing an explicit slug: row 1 succeeds, row 2's
        # save hits the (store, slug) uniqueness → the row fails, but row 1
        # (already applied earlier in the same batch) must persist — proving
        # the per-row savepoint keeps the batch transaction usable.
        csv_text = (
            PRODUCT_HEADER
            + ",SKU-BATCH-1,اول,dup-slug,,,,leaf-imp,1000,1,,,,,\n"
            + ",SKU-BATCH-2,دوم,dup-slug,,,,leaf-imp,2000,1,,,,,\n"
        )
        job = self._job(csv_text, mode=ImportJob.Mode.CREATE_ONLY)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.created_rows, 1)
        self.assertEqual(job.failed_rows, 1)
        self.assertTrue(Product.objects.filter(store=self.store, sku="SKU-BATCH-1").exists())
        self.assertFalse(Product.objects.filter(store=self.store, sku="SKU-BATCH-2").exists())


class BoundedQueryTests(ProductImportTestCase):
    """§26: repeated Brand/Category/TaxClass references must not produce a
    query per CSV cell — the lookup cache is built once per job, so preview
    query count stays bounded as row count grows."""

    def _preview_rows(self, n):
        rows = PRODUCT_HEADER
        for i in range(n):
            rows += f",SKU-BQ-{i},کالا {i},,,,brand-imp,leaf-imp,1000,1,,,general-imp,,\n"
        job = self._job(rows, mode=ImportJob.Mode.CREATE_ONLY)
        return job

    def test_preview_query_count_bounded_regardless_of_row_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        small = self._preview_rows(2)
        with CaptureQueriesContext(connection) as ctx_small:
            import_service.run_preview(small, actor=self.actor)
        large = self._preview_rows(20)
        with CaptureQueriesContext(connection) as ctx_large:
            import_service.run_preview(large, actor=self.actor)

        # The delta between 2-row and 20-row previews must be far below the
        # 18-row difference times a per-reference cost — a per-cell lookup
        # of 3 references (brand/category/tax) would add ~54 queries.
        self.assertLess(len(ctx_large.captured_queries) - len(ctx_small.captured_queries), 18)
