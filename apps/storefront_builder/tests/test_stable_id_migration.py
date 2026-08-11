"""Phase 0.5 repair — regression test for migration 0004 itself
(apps/storefront_builder/migrations/0004_storefrontsection_stable_id.py).

This targets the exact bug the owner found locally: on the owner's
Django 5.2.16 + SQLite environment, `python manage.py migrate` failed
with

    django.db.utils.IntegrityError: UNIQUE constraint failed:
    new__storefront_builder_storefrontsection.version_id,
    new__storefront_builder_storefrontsection.stable_id

Root cause: the migration's original AddField carried `default=uuid.uuid4`
on the nullable stable_id field. SQLite's ALTER-via-table-rebuild strategy
evaluated that callable default once and applied it (a single, shared,
non-distinct value) to every pre-existing row during the AddField step
itself, rather than leaving them NULL for the subsequent RunPython
backfill loop to fill in distinctly. With every pre-existing row sharing
one value, the RunPython loop's `.filter(stable_id__isnull=True)` matched
zero rows (nothing was actually NULL), so nothing was corrected before
the final UniqueConstraint(version, stable_id) was added — which then
failed for any version with more than one pre-existing section.

The repair removed `default=` from the AddField step entirely, so every
pre-existing row genuinely lands on NULL after AddField, and RunPython's
per-row `.update(stable_id=uuid.uuid4())` loop is the only thing that
ever assigns a pre-existing row's value — guaranteeing distinctness
before AlterField/AddConstraint run.

Two complementary test strategies are used here, because a normal
Django TestCase always runs against the FINAL, fully-migrated schema
(NOT NULL + UniqueConstraint already active) — it is not possible to
construct the exact broken intermediate migration state (colliding
non-null values, or raw NULLs) through the ORM/test database once the
final constraints are live, since the DB itself would reject those rows
immediately for reasons unrelated to the bug being tested. So:

1. `MigrationOperationOrderTests` — a STATIC/structural check that reads
   the actual `Migration.operations` list from the migration module and
   asserts the exact operation shape that prevents this bug (AddField's
   field has no default; RunPython comes next; AlterField's field DOES
   have a default; AddConstraint comes last). This is the test that
   would have caught the original bug, and the one most directly tied to
   the root cause.
2. `StableIdConstraintBehaviorTests` — functional tests against the live,
   fully-migrated schema, confirming the END STATE behaves correctly
   (new sections get distinct defaults, duplicates within a version are
   rejected, the same id is allowed across two different versions).

Written and read carefully this session; NOT executed (no Django runtime
available in this sandbox). The owner should validate the migration
itself end-to-end via `python manage.py migrate` from a fresh test
database, per the Phase 0.5 report's local validation commands — that is
the only way to prove the actual SQLite table-rebuild behavior this bug
depended on is now avoided.
"""

import importlib
import uuid

from django.core.cache import cache
from django.db import IntegrityError, migrations as django_migrations
from django.test import SimpleTestCase, TestCase

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.stores.models import Store


def _load_migration_module():
    """Django migration filenames start with digits, so they can't be
    imported with a normal dotted `import` statement — use importlib
    with the exact module path instead."""
    return importlib.import_module(
        "apps.storefront_builder.migrations.0004_storefrontsection_stable_id"
    )


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class MigrationOperationOrderTests(SimpleTestCase):
    """Static check of the migration's own operation list — this is the
    test that would have caught the original bug, without needing to
    execute a real migration against a real database."""

    def setUp(self):
        self.module = _load_migration_module()
        self.operations = self.module.Migration.operations

    def test_first_operation_is_addfield_with_no_default(self):
        first = self.operations[0]
        self.assertIsInstance(first, django_migrations.AddField)
        self.assertEqual(first.name, "stable_id")
        # The exact regression: this field must NOT carry a default at
        # this step. `has_default()` returns False when no default was
        # supplied (Django's internal sentinel `NOT_PROVIDED`).
        self.assertFalse(
            first.field.has_default(),
            "AddField must not carry a default — a callable default here is exactly "
            "what caused SQLite to backfill every pre-existing row with a single, "
            "shared, non-distinct value during the table rebuild.",
        )
        self.assertTrue(first.field.null, "the field must be nullable at this step so every pre-existing row can genuinely land on NULL")

    def test_second_operation_is_the_runpython_backfill(self):
        second = self.operations[1]
        self.assertIsInstance(second, django_migrations.RunPython)
        self.assertEqual(second.code.__name__, "backfill_stable_ids")

    def test_third_operation_is_alterfield_with_a_default_and_not_null(self):
        third = self.operations[2]
        self.assertIsInstance(third, django_migrations.AlterField)
        self.assertEqual(third.name, "stable_id")
        self.assertTrue(third.field.has_default(), "the FINAL field state must restore the real uuid4 default for genuinely new rows")
        self.assertFalse(third.field.null, "the FINAL field state must be not-null, matching the live model declaration")

    def test_fourth_operation_is_the_unique_constraint_and_comes_last(self):
        fourth = self.operations[3]
        self.assertIsInstance(fourth, django_migrations.AddConstraint)
        self.assertEqual(len(self.operations), 4, "the constraint must be the LAST operation — added only after every row is guaranteed distinct")

    def test_backfill_function_targets_only_null_rows_and_assigns_one_uuid_per_row(self):
        """Static/source-level confirmation that the backfill function's
        own logic is per-row (not a single bulk .update() call, which
        would give every matched row the SAME value) — inspects the
        function's compiled bytecode constants for the literal filter
        kwarg and the presence of a per-iteration call, rather than
        executing it."""
        import inspect

        source = inspect.getsource(self.module.backfill_stable_ids)
        self.assertIn("stable_id__isnull=True", source)
        self.assertIn(".iterator()", source, "must iterate rather than load everything into memory at once")
        # the uuid4() call must appear inside the per-row loop body, i.e.
        # after `for section in`, not before it as a single shared value.
        for_index = source.index("for section in")
        update_call_index = source.index("update(stable_id=uuid.uuid4())")
        self.assertGreater(update_call_index, for_index, "uuid.uuid4() must be called inside the per-row loop, not once outside it")


class StableIdConstraintBehaviorTests(TestCase):
    """Functional tests against the live, fully-migrated schema — confirm
    the end state (after this migration has already run, which is
    always true for a Django TestCase's test database) behaves exactly
    as required."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.layout, _ = StorefrontLayout.objects.get_or_create(store=self.store)
        self.version = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=9001, status=StorefrontLayoutVersion.Status.DRAFT,
        )

    def test_new_sections_created_after_migration_get_distinct_uuid4_defaults(self):
        a = StorefrontSection.objects.create(version=self.version, section_key="rich_text", order=0)
        b = StorefrontSection.objects.create(version=self.version, section_key="rich_text", order=1)
        c = StorefrontSection.objects.create(version=self.version, section_key="rich_text", order=2)
        ids = {a.stable_id, b.stable_id, c.stable_id}
        self.assertEqual(len(ids), 3, "every newly created section must receive its own distinct stable_id")
        for sid in ids:
            self.assertIsNotNone(sid)

    def test_duplicate_stable_id_within_same_version_is_rejected_by_the_unique_constraint(self):
        a = StorefrontSection.objects.create(version=self.version, section_key="rich_text", order=0)
        with self.assertRaises(IntegrityError):
            StorefrontSection.objects.create(
                version=self.version, section_key="newest_products", order=1, stable_id=a.stable_id,
            )

    def test_same_stable_id_allowed_across_two_different_versions(self):
        """Phase 1A note: uniqueness scope moved from (version, stable_id)
        to (page, stable_id) — the assertion below now queries via
        ``page__version=`` (the real, physical FK chain) instead of the
        no-longer-existent ``version=`` column directly on
        StorefrontSection; this is exactly the ``.filter(version=...)``
        style of call site the Phase 1A migration removed from the
        schema (production code was updated the same way in views.py)."""
        other_version = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=9002, status=StorefrontLayoutVersion.Status.ARCHIVED,
        )
        a = StorefrontSection.objects.create(version=self.version, section_key="rich_text", order=0)
        shared_id = a.stable_id
        # must NOT raise — uniqueness is scoped per-page (transitively
        # per-version, since each page belongs to exactly one version),
        # not global.
        StorefrontSection.objects.create(version=other_version, section_key="rich_text", order=0, stable_id=shared_id)
        self.assertTrue(StorefrontSection.objects.filter(page__version=self.version, stable_id=shared_id).exists())
        self.assertTrue(StorefrontSection.objects.filter(page__version=other_version, stable_id=shared_id).exists())
