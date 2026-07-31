"""Section 14 — Store deletion is always soft, typed-confirmation-gated,
and retention-scheduled; purge only happens for real once the retention
window has actually elapsed, and only via the explicit purge command."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreDomain
from apps.stores.services.deletion_service import (
    DeletionError,
    cancel_deletion,
    purge_due_stores,
    request_deletion,
    stores_due_for_purge,
)
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()


class DeletionServiceTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه حذف", slug="deletion-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="deletion-store",
        )
        self.actor = User.objects.create_user(username="09121300011", password="a-very-strong-pass-1")


class RequestDeletionTests(DeletionServiceTestCase):
    def test_wrong_typed_confirmation_is_rejected(self):
        with self.assertRaises(DeletionError):
            request_deletion(store=self.store, actor=self.actor, typed_confirmation="wrong-slug")
        self.store.refresh_from_db()
        self.assertIsNone(self.store.deletion_requested_at)
        self.assertEqual(self.store.status, Store.Status.ACTIVE)

    def test_correct_typed_confirmation_soft_closes_the_store(self):
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Store.Status.CLOSED)
        self.assertEqual(self.store.pre_deletion_status, Store.Status.ACTIVE)
        self.assertIsNotNone(self.store.deletion_requested_at)
        self.assertEqual(self.store.deletion_requested_by, self.actor)
        self.assertIsNotNone(self.store.deletion_scheduled_purge_at)

    def test_default_retention_is_365_days(self):
        before = timezone.now()
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.store.refresh_from_db()
        delta = self.store.deletion_scheduled_purge_at - before
        self.assertGreaterEqual(delta.days, 364)
        self.assertLessEqual(delta.days, 365)

    def test_retention_days_is_configurable(self):
        update_platform_configuration(actor=None, deletion_retention_days=200)
        before = timezone.now()
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.store.refresh_from_db()
        delta = self.store.deletion_scheduled_purge_at - before
        self.assertGreaterEqual(delta.days, 199)
        self.assertLessEqual(delta.days, 200)

    def test_cannot_request_deletion_twice(self):
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        with self.assertRaises(DeletionError):
            request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")

    def test_records_a_store_scoped_audit_event(self):
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="store.deletion_requested").exists()
        )

    def test_no_data_is_deleted(self):
        StoreDomain.objects.create(
            store=self.store, hostname=f"{self.store.platform_code}.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())
        self.assertTrue(StoreDomain.objects.filter(store=self.store).exists())


class CancelDeletionTests(DeletionServiceTestCase):
    def test_restores_the_prior_status(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        cancel_deletion(store=self.store, actor=self.actor)
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Store.Status.SUSPENDED)
        self.assertIsNone(self.store.deletion_requested_at)
        self.assertIsNone(self.store.deletion_scheduled_purge_at)
        self.assertEqual(self.store.pre_deletion_status, "")

    def test_rejects_when_no_deletion_was_requested(self):
        with self.assertRaises(DeletionError):
            cancel_deletion(store=self.store, actor=self.actor)

    def test_records_a_cancellation_audit_event(self):
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        cancel_deletion(store=self.store, actor=self.actor)
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="store.deletion_cancelled").exists()
        )


class PurgeDueStoresTests(DeletionServiceTestCase):
    def _request_and_backdate(self, *, days_from_now):
        request_deletion(store=self.store, actor=self.actor, typed_confirmation="deletion-store")
        self.store.refresh_from_db()
        self.store.deletion_scheduled_purge_at = timezone.now() + timezone.timedelta(days=days_from_now)
        self.store.save(update_fields=["deletion_scheduled_purge_at"])

    def test_not_yet_due_is_excluded(self):
        self._request_and_backdate(days_from_now=30)
        self.assertEqual(stores_due_for_purge().count(), 0)

    def test_due_store_is_included(self):
        self._request_and_backdate(days_from_now=-1)
        self.assertEqual(stores_due_for_purge().count(), 1)

    def test_dry_run_never_deletes(self):
        self._request_and_backdate(days_from_now=-1)
        results = purge_due_stores(dry_run=True)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["purged"])
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())

    def test_execute_actually_deletes_the_store(self):
        self._request_and_backdate(days_from_now=-1)
        results = purge_due_stores(dry_run=False, actor=self.actor)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["purged"])
        self.assertFalse(Store.objects.filter(pk=self.store.pk).exists())

    def test_execute_records_a_platform_audit_event_surviving_the_deleted_store(self):
        from apps.portal.models import PlatformAuditLogEntry

        self._request_and_backdate(days_from_now=-1)
        purge_due_stores(dry_run=False, actor=self.actor)
        entry = PlatformAuditLogEntry.objects.get(action_code="store.purged")
        self.assertEqual(entry.object_label, "فروشگاه حذف")
        self.assertEqual(entry.metadata["slug"], "deletion-store")

    def test_a_store_not_yet_due_is_never_purged_even_with_execute(self):
        self._request_and_backdate(days_from_now=30)
        purge_due_stores(dry_run=False, actor=self.actor)
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())
