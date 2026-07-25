import importlib

from django.apps import apps as global_apps
from django.test import TestCase

from apps.stores.models import Store, StoreMembership

_migration_0002 = importlib.import_module(
    "apps.stores.migrations.0002_create_akhlaghi_store"
)


class AkhlaghiDataMigrationTests(TestCase):
    """Confirms the Akhlaghi Store data migration's effects and idempotency.

    The Django test runner applies all migrations (including this data
    migration) when it builds the test database, so by the time any test
    method runs, ``create_akhlaghi_store`` has already executed once as
    part of normal migration history.
    """

    def test_akhlaghi_store_exists_after_migrations(self):
        store = Store.objects.get(slug="akhlaghi")
        self.assertEqual(store.name, "Akhlaghi")
        self.assertEqual(store.status, Store.Status.ACTIVE)

    def test_rerunning_migration_logic_does_not_duplicate_the_store(self):
        before_count = Store.objects.filter(slug="akhlaghi").count()
        self.assertEqual(before_count, 1)

        _migration_0002.create_akhlaghi_store(global_apps, schema_editor=None)

        after_count = Store.objects.filter(slug="akhlaghi").count()
        self.assertEqual(after_count, 1)

    def test_no_arbitrary_user_was_assigned_as_owner(self):
        store = Store.objects.get(slug="akhlaghi")
        self.assertFalse(
            StoreMembership.objects.filter(store=store).exists(),
            "The data migration must not assign any user as Owner; "
            "membership backfill is deferred to a later, dedicated migration.",
        )
