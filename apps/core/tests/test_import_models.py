"""Tests for the ImportJob/ImportRowResult models (checkpoint 4B §4-5):
Store-scoped idempotency-key uniqueness, private file storage, and
ImportRowResult indexing/relationship."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import ImportJob, ImportRowResult
from apps.core.storage import private_storage
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ImportJobModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_idempotency_key_unique_per_store(self):
        ImportJob.objects.create(
            store=self.store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="key-1",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportJob.objects.create(
                    store=self.store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="key-1",
                )

    def test_same_idempotency_key_allowed_in_different_stores(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="imp-model-other")
        ImportJob.objects.create(
            store=self.store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="shared-key",
        )
        # Must not raise — the unique constraint is per (store, idempotency_key).
        ImportJob.objects.create(
            store=other_store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="shared-key",
        )

    def test_empty_idempotency_key_not_subject_to_uniqueness(self):
        ImportJob.objects.create(store=self.store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="")
        # A second empty-key job in the same store must be allowed.
        ImportJob.objects.create(store=self.store, import_type=ImportJob.ImportType.PRODUCTS, idempotency_key="")
        self.assertEqual(ImportJob.objects.filter(store=self.store, idempotency_key="").count(), 2)

    def test_source_file_uses_private_storage(self):
        field = ImportJob._meta.get_field("source_file")
        self.assertIs(field.storage, private_storage)

    def test_error_report_file_uses_private_storage(self):
        field = ImportJob._meta.get_field("error_report_file")
        self.assertIs(field.storage, private_storage)

    def test_defaults(self):
        job = ImportJob.objects.create(store=self.store, import_type=ImportJob.ImportType.INVENTORY)
        self.assertEqual(job.status, ImportJob.Status.UPLOADED)
        self.assertEqual(job.mode, ImportJob.Mode.UPSERT)
        self.assertTrue(job.dry_run)
        self.assertEqual(job.total_rows, 0)


class ImportRowResultModelTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.job = ImportJob.objects.create(store=self.store, import_type=ImportJob.ImportType.PRODUCTS)

    def test_row_result_linked_to_job(self):
        row = ImportRowResult.objects.create(
            import_job=self.job, row_number=1, source_identifier="SKU-1",
            status=ImportRowResult.RowStatus.CREATED, errors=[], warnings=["w"],
        )
        self.assertEqual(row.import_job, self.job)
        self.assertEqual(list(self.job.row_results.all()), [row])

    def test_cascade_delete_with_job(self):
        ImportRowResult.objects.create(
            import_job=self.job, row_number=1, status=ImportRowResult.RowStatus.VALID,
        )
        self.job.delete()
        self.assertEqual(ImportRowResult.objects.count(), 0)
