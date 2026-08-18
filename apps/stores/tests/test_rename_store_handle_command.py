from io import StringIO

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.platform_code_service import generate_unique_platform_code


class RenameStoreHandleCommandTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه دستور", slug="cmd-handle-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="cmd-handle-store",
        )
        StoreDomain.objects.create(
            store=self.store, hostname="cmdhandle.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_requires_reason_flag(self):
        with self.assertRaises(CommandError):
            call_command("rename_store_handle", "cmd-handle-store", "newlabel", stdout=StringIO())

    def test_unknown_store_slug_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                "rename_store_handle", "no-such-store", "newlabel", "--reason=test", stdout=StringIO(),
            )

    def test_successful_rename(self):
        out = StringIO()
        call_command("rename_store_handle", "cmd-handle-store", "newlabel", "--reason=owner asked", stdout=out)
        expected_hostname = f"newlabel.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        self.assertTrue(StoreDomain.objects.filter(hostname=expected_hostname, is_primary=True).exists())
        self.assertIn(expected_hostname, out.getvalue())
