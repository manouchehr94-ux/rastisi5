"""Tests for cleanup_import_files (service + management command): expired
source/error files deleted, Job records/counters preserved, Store-safe,
idempotent (ADR-62)."""

from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.models import ImportJob, ImportRowResult
from apps.dashboard.services import import_service
from apps.stores.models import Store

RETENTION = import_service.IMPORT_FILE_RETENTION_DAYS


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class CleanupImportFilesTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def _job(self, *, age_days, with_files=True):
        job = ImportJob.objects.create(
            store=self.store, import_type=ImportJob.ImportType.PRODUCTS,
            status=ImportJob.Status.COMPLETED, total_rows=3, created_rows=3,
        )
        if with_files:
            job.source_file.save("src.csv", ContentFile(b"a\n1\n"), save=True)
            job.error_report_file.save("err.csv", ContentFile(b"row\n1\n"), save=True)
        # Backdate created_at past the retention cutoff.
        ImportJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=age_days)
        )
        job.refresh_from_db()
        return job

    def test_old_files_deleted_but_record_preserved(self):
        job = self._job(age_days=RETENTION + 1)
        ImportRowResult.objects.create(
            import_job=job, row_number=1, status=ImportRowResult.RowStatus.CREATED,
        )
        count = import_service.cleanup_import_files(store=self.store)
        job.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertFalse(job.source_file)
        self.assertFalse(job.error_report_file)
        # Record and counters survive.
        self.assertEqual(job.total_rows, 3)
        self.assertEqual(job.created_rows, 3)
        self.assertEqual(ImportRowResult.objects.filter(import_job=job).count(), 1)

    def test_recent_files_untouched(self):
        job = self._job(age_days=1)
        count = import_service.cleanup_import_files(store=self.store)
        job.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertTrue(job.source_file)

    def test_idempotent(self):
        self._job(age_days=RETENTION + 1)
        first = import_service.cleanup_import_files(store=self.store)
        second = import_service.cleanup_import_files(store=self.store)
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)

    def test_store_filter_isolates(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="cif-other-store")
        other_job = ImportJob.objects.create(
            store=other_store, import_type=ImportJob.ImportType.PRODUCTS, status=ImportJob.Status.COMPLETED,
        )
        other_job.source_file.save("src.csv", ContentFile(b"a\n1\n"), save=True)
        ImportJob.objects.filter(pk=other_job.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=RETENTION + 5)
        )
        count = import_service.cleanup_import_files(store=self.store)
        other_job.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertTrue(other_job.source_file)

    def test_command_runs(self):
        self._job(age_days=RETENTION + 1)
        out = StringIO()
        call_command("cleanup_import_files", stdout=out)
        self.assertIn("پاک‌سازی شد", out.getvalue())

    def test_command_unknown_store_errors(self):
        err = StringIO()
        call_command("cleanup_import_files", "--store", "no-such-store", stderr=err)
        self.assertIn("یافت نشد", err.getvalue())
