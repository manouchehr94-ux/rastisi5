import importlib

from django.apps import apps as global_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.stores.models import Store

_migration_0002 = importlib.import_module(
    "apps.stores.migrations.0002_create_akhlaghi_store"
)


class AkhlaghiSeedMigrationRunPythonIdempotencyTests(TestCase):
    """RunPython-function idempotency test only — NOT a migration test.

    This calls ``create_akhlaghi_store`` directly against the current,
    already-migrated global app registry. It proves the forward function
    itself is idempotent (calling it twice does not duplicate the Store);
    it does not exercise Django's migration executor, migration history, or
    historical model state at all. See
    ``AkhlaghiSeedMigrationExecutorTests`` below for the real,
    history-driven migration test.
    """

    def test_rerunning_the_runpython_function_does_not_duplicate_the_store(self):
        before_count = Store.objects.filter(slug="akhlaghi").count()
        self.assertEqual(before_count, 1)

        _migration_0002.create_akhlaghi_store(global_apps, schema_editor=None)

        after_count = Store.objects.filter(slug="akhlaghi").count()
        self.assertEqual(after_count, 1)


class AkhlaghiSeedMigrationExecutorTests(TransactionTestCase):
    """Real, ``MigrationExecutor``-driven test of the 0002 data migration.

    ``TransactionTestCase`` (not ``TestCase``) is required: the migration
    executor issues real DDL (``CREATE``/``DROP TABLE``) as part of
    unapplying and reapplying migrations, which does not behave correctly
    wrapped in the atomic block ``TestCase`` uses per test.

    ``TransactionTestCase`` flushes (truncates) every table in its own
    teardown. Without any counter-measure, that flush would permanently wipe
    the Akhlaghi Store row that migration 0002 seeds for the whole test
    database — a row the rest of the suite relies on being present
    (``test_models.py`` deliberately avoids the "akhlaghi" slug to avoid
    colliding with it).

    An earlier version of this test set ``serialized_rollback = True`` to
    restore that row. That backfires: Django's flush already re-emits the
    ``post_migrate`` signal (which recreates ``django_content_type``/
    ``auth_permission`` rows after truncation), and ``serialized_rollback``
    *also* replays a full data snapshot captured at test-database build
    time on top of that — the two collide and raise
    ``IntegrityError: UNIQUE constraint failed: django_content_type.app_label,
    django_content_type.model``. Instead, ``_fixture_teardown()`` is
    overridden below to run the ordinary flush (letting ``post_migrate``
    recreate content types cleanly, with nothing else competing with it),
    then re-seed only the one row this test is actually responsible for.
    """

    def setUp(self):
        self.executor = MigrationExecutor(connection)

    def tearDown(self):
        # Unconditionally restore the "stores" app to its latest migration
        # state, regardless of where the test body left it, so later tests
        # never see a stale/partial schema.
        self.executor.loader.build_graph()
        targets = self.executor.loader.graph.leaf_nodes("stores")
        self.executor.migrate(targets)

    def _fixture_teardown(self):
        super()._fixture_teardown()
        # TransactionTestCase's flush truncates every table, including the
        # Akhlaghi Store row seeded by migration 0002. Re-seed it directly
        # via the same RunPython function the migration itself uses, so the
        # rest of the suite sees the same state it would have without this
        # test having run.
        _migration_0002.create_akhlaghi_store(global_apps, schema_editor=None)

    def test_migration_creates_exactly_one_akhlaghi_store_with_no_membership(self):
        # Fully unapply the "stores" app first. This guarantees a genuinely
        # empty Store table once we reapply 0001_initial, regardless of
        # 0002's reverse behavior — 0002's reverse is an intentional no-op
        # (see its docstring), so asking to "go back to 0001" directly from
        # an already-applied 0002 would not, by itself, remove the seeded
        # row. Going all the way to zero and back sidesteps that entirely.
        self.executor.migrate([("stores", None)])
        self.executor.loader.build_graph()

        # 1. Migrate to 0001_initial.
        self.executor.migrate([("stores", "0001_initial")])
        self.executor.loader.build_graph()
        state_at_0001 = self.executor.loader.project_state(("stores", "0001_initial"))
        store_model_0001 = state_at_0001.apps.get_model("stores", "Store")

        # 2. The Akhlaghi Store does not yet exist.
        self.assertFalse(store_model_0001.objects.filter(slug="akhlaghi").exists())

        # 3. Migrate to 0002_create_akhlaghi_store.
        self.executor.migrate([("stores", "0002_create_akhlaghi_store")])
        self.executor.loader.build_graph()
        state_at_0002 = self.executor.loader.project_state(
            ("stores", "0002_create_akhlaghi_store")
        )
        store_model_0002 = state_at_0002.apps.get_model("stores", "Store")
        membership_model_0002 = state_at_0002.apps.get_model("stores", "StoreMembership")

        # 4. Exactly one Store exists with the expected fields.
        stores = store_model_0002.objects.filter(slug="akhlaghi")
        self.assertEqual(stores.count(), 1)
        store = stores.get()
        self.assertEqual(store.name, "Akhlaghi")
        self.assertEqual(store.status, "active")

        # 5. / 6. No StoreMembership was created — which also proves no
        # arbitrary User was ever selected as Owner.
        self.assertFalse(membership_model_0002.objects.filter(store=store).exists())

        # 7. Restoring to the latest migration state happens in tearDown().
