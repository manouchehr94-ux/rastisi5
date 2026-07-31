from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store
from apps.stores.services.deletion_service import request_deletion
from apps.stores.services.platform_code_service import generate_unique_platform_code


class PurgeDeletedStoresCommandTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه دستور حذف", slug="cmd-deletion-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="cmd-deletion-store",
        )
        request_deletion(store=self.store, actor=None, typed_confirmation="cmd-deletion-store")
        self.store.deletion_scheduled_purge_at = timezone.now() - timezone.timedelta(days=1)
        self.store.save(update_fields=["deletion_scheduled_purge_at"])

    def test_default_is_dry_run(self):
        out = StringIO()
        call_command("purge_deleted_stores", stdout=out)
        self.assertIn("dry-run", out.getvalue())
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())

    def test_execute_flag_actually_purges(self):
        out = StringIO()
        call_command("purge_deleted_stores", "--execute", stdout=out)
        self.assertFalse(Store.objects.filter(pk=self.store.pk).exists())

    def test_no_candidates_reports_cleanly(self):
        Store.objects.filter(pk=self.store.pk).delete()
        out = StringIO()
        call_command("purge_deleted_stores", stdout=out)
        self.assertIn("آماده نیست", out.getvalue())
