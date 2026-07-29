"""Tests for ``mark_expired_jobs``/``cleanup_expired_exports`` — the
Store-safe, batch-safe reclamation of expired ``ExportJob`` files (ADR-52)."""

from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.models import ExportJob
from apps.core.services.export_service import mark_expired_jobs
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class MarkExpiredJobsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def _completed_job(self, *, expires_at):
        job = ExportJob.objects.create(
            store=self.store, export_type=ExportJob.ExportType.PRODUCTS,
            status=ExportJob.Status.COMPLETED, expires_at=expires_at,
        )
        job.file.save("products.csv", ContentFile(b"a,b\n1,2\n"), save=True)
        return job

    def test_expired_job_marked_and_file_deleted(self):
        job = self._completed_job(expires_at=timezone.now() - timezone.timedelta(days=1))
        file_name = job.file.name
        count = mark_expired_jobs(store=self.store)
        job.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(job.status, ExportJob.Status.EXPIRED)
        self.assertFalse(job.file)
        self.assertFalse(job.file.storage.exists(file_name))

    def test_not_yet_expired_job_untouched(self):
        job = self._completed_job(expires_at=timezone.now() + timezone.timedelta(days=1))
        count = mark_expired_jobs(store=self.store)
        job.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)

    def test_other_stores_job_not_touched_when_store_filter_given(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="export-cleanup-other")
        other_job = ExportJob.objects.create(
            store=other_store, export_type=ExportJob.ExportType.PRODUCTS,
            status=ExportJob.Status.COMPLETED, expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        count = mark_expired_jobs(store=self.store)
        other_job.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(other_job.status, ExportJob.Status.COMPLETED)


class CleanupExpiredExportsCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_command_marks_expired_jobs_across_all_stores(self):
        job = ExportJob.objects.create(
            store=self.store, export_type=ExportJob.ExportType.PRODUCTS,
            status=ExportJob.Status.COMPLETED, expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        job.file.save("products.csv", ContentFile(b"a\n1\n"), save=True)
        out = StringIO()
        call_command("cleanup_expired_exports", stdout=out)
        job.refresh_from_db()
        self.assertEqual(job.status, ExportJob.Status.EXPIRED)

    def test_command_with_unknown_store_slug_errors_without_crash(self):
        err = StringIO()
        call_command("cleanup_expired_exports", "--store", "no-such-store-slug", stderr=err)
        self.assertIn("یافت نشد", err.getvalue())
