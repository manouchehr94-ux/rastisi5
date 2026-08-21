"""Phase 2A — additive multi-block schema foundation regression tests.

Covers migration ``0015_storefrontsection_cell_and_cell_order`` (adds
``StorefrontSection.cell``/``cell_order`` and backfills them from the
still-authoritative legacy ``StorefrontCell.section`` OneToOne) and the
model-level invariants it establishes.

Same sandbox constraint as ``test_page_backfill_migration.py`` and
``test_stable_id_migration.py``: a normal Django ``TestCase`` always runs
against the FINAL, fully-migrated schema, so the exact pre-migration
intermediate state cannot be constructed through the ORM once the new
columns already exist. The same two complementary strategies already
established by those files are used here:

1. ``BackfillFunctionUnitTests`` — imports the actual backfill function
   from migration 0015 and exercises it directly against a
   ``_LiveAppsShim`` (backed by the real live models, safe here because
   the function only reads/writes ``section_id``/``cell_id``/``cell_order``,
   which are structurally identical between the live model and the
   migration's historical state for this operation).
2. ``ModelInvariantTests`` — functional tests against the live,
   fully-migrated schema, confirming the end state (empty cell, populated
   cell, section never placed in a cell, cross-store/page isolation,
   ``order`` untouched) behaves exactly as required by the Phase 2A spec.

Written and read carefully this session; NOT executed end-to-end via
``python manage.py migrate``/``python manage.py test`` because this
sandbox has no Django installation and no network access to install one
(PyPI/files.pythonhosted.org are blocked by the sandbox's
``INTEGRATIONS_ONLY`` network policy — confirmed via direct ``pip``/``uv``
attempts, both returned ``403 Forbidden`` through the proxy). This blocker
is reported verbatim in the Phase 2A summary rather than a fabricated
PASS result. The owner should run this file (and the full
``apps.storefront_builder`` suite) via ``python manage.py test
apps.storefront_builder`` in an environment with Django installed before
merging.
"""

import importlib

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.storefront_builder.models import StorefrontCell, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service as svc
from apps.stores.models import Store


def _load_migration_module():
    """Migration filenames start with digits, so they can't be imported
    with a normal dotted ``import`` statement."""
    return importlib.import_module(
        "apps.storefront_builder.migrations.0015_storefrontsection_cell_and_cell_order"
    )


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class MigrationOperationShapeTests(SimpleTestCase):
    """Static/structural check of the migration's own operation list —
    confirms the two new fields are additive (nullable/defaulted, no
    unsafe callable default that could corrupt pre-existing rows the way
    migration 0004's original bug did — see test_stable_id_migration.py),
    and that the backfill RunPython runs after both AddField ops."""

    def setUp(self):
        self.module = _load_migration_module()
        self.operations = self.module.Migration.operations

    def test_depends_on_container_cell_foundation_migration(self):
        self.assertIn(
            ("storefront_builder", "0014_storefront_container_cell_foundation"),
            self.module.Migration.dependencies,
        )

    def test_cell_field_is_nullable_with_no_unsafe_default(self):
        from django.db import migrations as django_migrations

        add_field_ops = {op.name: op for op in self.operations if isinstance(op, django_migrations.AddField)}
        self.assertIn("cell", add_field_ops)
        cell_field = add_field_ops["cell"].field
        self.assertTrue(cell_field.null)
        self.assertTrue(cell_field.blank)
        self.assertFalse(
            cell_field.has_default(),
            "cell must not carry a default — every pre-existing row must land on "
            "genuine NULL, backfilled only by the explicit RunPython step.",
        )

    def test_cell_order_field_defaults_to_zero(self):
        from django.db import migrations as django_migrations

        add_field_ops = {op.name: op for op in self.operations if isinstance(op, django_migrations.AddField)}
        self.assertIn("cell_order", add_field_ops)
        cell_order_field = add_field_ops["cell_order"].field
        self.assertEqual(cell_order_field.get_default(), 0)

    def test_backfill_runpython_is_the_last_operation(self):
        from django.db import migrations as django_migrations

        self.assertIsInstance(self.operations[-1], django_migrations.RunPython)
        self.assertEqual(self.operations[-1].code.__name__, "backfill_section_cell")

    def test_conditional_unique_constraint_only_applies_when_cell_is_set(self):
        from django.db import migrations as django_migrations
        from django.db.models import Q

        constraint_ops = [op for op in self.operations if isinstance(op, django_migrations.AddConstraint)]
        self.assertEqual(len(constraint_ops), 1)
        constraint = constraint_ops[0].constraint
        self.assertEqual(constraint.fields, ("cell", "cell_order"))
        self.assertEqual(constraint.condition, Q(cell__isnull=False))


class BackfillFunctionUnitTests(TestCase):
    """Exercises the actual backfill function from migration 0015
    directly, against the live (already-migrated) schema — safe because
    the function only touches ``section_id``/``cell_id``/``cell_order``,
    which have the same shape pre- and post-migration for this operation."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()

    def _load_backfill_fn(self):
        module = _load_migration_module()
        return module.backfill_section_cell

    def _load_reverse_fn(self):
        module = _load_migration_module()
        return module.reverse_backfill_section_cell

    class _LiveAppsShim:
        @staticmethod
        def get_model(app_label, model_name):
            assert app_label == "storefront_builder"
            return {
                "StorefrontCell": StorefrontCell,
                "StorefrontSection": StorefrontSection,
            }[model_name]

    def _section(self, order=0, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=order, settings={}, **kwargs
        )

    def test_empty_cell_backfills_nothing(self):
        """Scenario A — an empty Cell (``section`` is NULL) must never
        cause any Section to receive a ``cell`` value.

        Deliberately scoped to the one Cell/Section this test controls —
        NOT a global count. The Django test database already runs every
        migration (including 0015) during its own setup, and legitimately
        seeded/default storefront content for OTHER stores/pages may
        already contain populated Cells that migration 0015 correctly
        backfilled long before this test ever runs — asserting a global
        ``cell__isnull=False`` count of zero would incorrectly fail on
        that pre-existing, correctly-migrated data. What this test must
        actually prove is narrower and fully self-contained: (a) the one
        empty Cell created here stays empty, and (b) the one unrelated
        Section created here (never placed anywhere) is not accidentally
        picked up by the backfill."""
        empty_container = container_service.create_empty_container(self.page, "single")
        empty_cell = empty_container.cells.get()
        untouched_section = self._section(0)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)

        empty_cell.refresh_from_db()
        untouched_section.refresh_from_db()
        self.assertIsNone(empty_cell.section_id, "the empty Cell must remain empty after the backfill")
        self.assertIsNone(untouched_section.cell_id, "a Section never placed in any Cell must not be assigned one")
        # No Section anywhere ends up pointing at THIS specific empty Cell.
        self.assertEqual(StorefrontSection.objects.filter(cell_id=empty_cell.pk).count(), 0)

    def test_populated_cell_mirrors_into_new_fk_with_cell_order_zero(self):
        """Scenario B — an existing populated Cell: before/after the
        backfill, ``cell.section`` (legacy OneToOne) is byte-identical;
        after the backfill, the referenced Section additionally has
        ``cell_id == cell.pk`` and ``cell_order == 0``.

        Phase 2B correction: ``container_service.place_section`` now keeps
        the legacy OneToOne and the new FK synchronized as one atomic write
        (a real-environment fix made after this migration test was
        originally written — see ``container_service.place_section``'s
        updated docstring), so it can no longer be used here to construct
        the genuinely pre-migration-shaped state this test needs (legacy
        OneToOne set, new FK still NULL) — calling it would immediately
        populate the new FK itself, defeating the point of testing the
        migration's *own* backfill function in isolation. The pre-migration
        state is instead constructed directly via the plain legacy OneToOne
        assignment (``cell.section = section; cell.save()``), bypassing
        ``place_section`` entirely — exactly the shape a real pre-Phase-2B
        database row had before either the migration backfill or the
        Phase 2B ``place_section`` fix ever existed."""
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        cell = container.cells.order_by("order").first()

        # Simulated pre-0015 state, made explicit: a freshly created
        # Section always starts with cell_id NULL (the new field doesn't
        # exist in spirit yet, only the legacy OneToOne is meaningful).
        self.assertIsNone(section.cell_id)

        cell.section = section
        cell.save(update_fields=["section", "updated_at"])
        # BEFORE backfill: the legacy OneToOne is the only relationship
        # reflecting the real placement; the new FK still reflects
        # nothing (mirrors the simulated pre-0015 state above).
        self.assertEqual(cell.section_id, section.pk)
        legacy_section_id_before = cell.section_id
        section.refresh_from_db()
        self.assertIsNone(section.cell_id)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)

        cell.refresh_from_db()
        section.refresh_from_db()
        # AFTER backfill: the legacy OneToOne value must not have changed.
        self.assertEqual(cell.section_id, legacy_section_id_before)
        self.assertEqual(cell.section_id, section.pk)
        # New transitional FK now mirrors the same placement.
        self.assertEqual(section.cell_id, cell.pk)
        self.assertEqual(section.cell_order, 0)

    def test_legacy_section_never_placed_in_a_cell_keeps_cell_null_and_order_unchanged(self):
        """Scenario C — a Section that has never been placed in any Cell:
        ``cell`` stays NULL and its existing ``order``/``row_key``/
        ``row_span`` data is completely unaffected by the backfill."""
        section = self._section(order=3, row_key="pair", row_span=6)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)

        section.refresh_from_db()
        self.assertIsNone(section.cell_id)
        self.assertEqual(section.cell_order, 0)
        self.assertEqual(section.order, 3)
        self.assertEqual(section.row_key, "pair")
        self.assertEqual(section.row_span, 6)

    def test_backfill_never_crosses_page_boundaries(self):
        """Scenario D (page dimension) — a Cell on Page A can only ever
        backfill a Section that already legitimately belongs to Page A
        (``place_section`` itself enforces this at write time); the
        backfill must not accidentally associate a Cell with a Section
        from a different page."""
        other_page = self.draft.get_page(StorefrontPage.PageType.SEARCH)
        section_a = self._section(0)
        other_page_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0, settings={}
        )
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order"))
        container_service.place_section(cell_a, section_a)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)

        section_a.refresh_from_db()
        other_page_section.refresh_from_db()
        self.assertEqual(section_a.cell_id, cell_a.pk)
        self.assertIsNone(other_page_section.cell_id)
        self.assertIsNone(cell_b.section_id)

    def test_backfill_never_crosses_store_boundaries(self):
        """Scenario D (store dimension) — two different stores' drafts
        each get their own Containers/Cells; backfilling one store's
        Cells must never touch a Section belonging to another store.

        A second Store is created directly (``Store.objects.create``)
        rather than skipped when no second fixture exists in the test
        database — this mirrors the exact lightweight pattern already
        used elsewhere in this codebase for cross-store isolation tests
        (e.g. ``apps/dashboard/tests/test_collection_views.py``,
        ``apps/core/tests/test_shop_settings.py``): no factory/fixture
        framework is needed, ``Store`` has no required fields beyond
        ``name``/``slug`` for this purpose, and ``layout_service`` only
        needs a valid ``Store`` row to provision a layout/draft for it."""
        other_store = Store.objects.create(name="فروشگاه دوم آزمایشی", slug="phase2a-cross-store-check")
        other_draft = svc.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_page.containers.all().delete()
        other_page.sections.all().delete()
        other_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0, settings={}
        )
        other_container = container_service.create_empty_container(other_page, "single")
        other_cell = other_container.cells.get()
        container_service.place_section(other_cell, other_section)

        section_here = self._section(0)
        container_here = container_service.create_empty_container(self.page, "single")
        cell_here = container_here.cells.get()
        container_service.place_section(cell_here, section_here)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)

        section_here.refresh_from_db()
        other_section.refresh_from_db()
        self.assertEqual(section_here.cell_id, cell_here.pk)
        self.assertEqual(other_section.cell_id, other_cell.pk)
        self.assertNotEqual(section_here.cell_id, other_section.cell_id)

    def test_backfill_is_idempotent(self):
        """Running the backfill twice must produce exactly the same
        result as running it once (safe for a retried/re-applied
        migration in a test harness)."""
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)
        section.refresh_from_db()
        self.assertEqual((section.cell_id, section.cell_order), (cell.pk, 0))

        backfill(self._LiveAppsShim(), None)
        section.refresh_from_db()
        self.assertEqual((section.cell_id, section.cell_order), (cell.pk, 0))

    def test_reverse_backfill_clears_new_fields_without_touching_legacy_relationship(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)
        backfill = self._load_backfill_fn()
        backfill(self._LiveAppsShim(), None)
        section.refresh_from_db()
        self.assertIsNotNone(section.cell_id)

        reverse = self._load_reverse_fn()
        reverse(self._LiveAppsShim(), None)

        section.refresh_from_db()
        cell.refresh_from_db()
        self.assertIsNone(section.cell_id)
        self.assertEqual(section.cell_order, 0)
        # Legacy OneToOne is completely unaffected by the reverse either.
        self.assertEqual(cell.section_id, section.pk)


class ModelInvariantTests(TestCase):
    """Functional tests against the live, fully-migrated schema — confirm
    the model-level invariants Phase 2A must establish going forward."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()

    def test_new_section_defaults_to_no_cell_and_cell_order_zero(self):
        section = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={}
        )
        self.assertIsNone(section.cell_id)
        self.assertEqual(section.cell_order, 0)

    def test_order_field_semantics_are_completely_unaffected_by_cell_fields(self):
        """The existing page-level ``order`` field must keep meaning
        exactly what it means today, regardless of whether a Section
        happens to also have a ``cell`` set — this is the entire point
        of adding a separate ``cell_order`` field instead of reusing
        ``order`` for a second purpose (see models.py docstrings)."""
        s1 = StorefrontSection.objects.create(page=self.page, section_key="rich_text", order=0, settings={})
        s2 = StorefrontSection.objects.create(page=self.page, section_key="rich_text", order=1, settings={})
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, s2)

        ordered = list(self.page.sections.order_by("order", "id"))
        self.assertEqual([s.pk for s in ordered], [s1.pk, s2.pk])
        self.assertEqual(s1.order, 0)
        self.assertEqual(s2.order, 1)

    def test_placing_a_section_in_a_cell_keeps_legacy_and_new_relationship_synchronized(self):
        """Phase 2A shipped ``place_section`` writing only the legacy
        OneToOne, with the new FK populated solely by the one-time migration
        backfill. Real-environment verification of Phase 2B found that
        boundary insufficient: the current Builder UI still calls
        ``place_section`` directly, and the new ``get_cell_blocks`` read path
        prefers the new FK whenever it has any rows — so leaving
        ``place_section`` from writing only the legacy relationship risked a
        stale/contradictory new-FK pointer (e.g. left over from an earlier
        multi-block operation on the same Cell) surviving underneath a
        legacy write that believes it made ``section`` the Cell's sole
        content. Phase 2B therefore correctly updated ``place_section`` to
        keep BOTH relationships synchronized — this test now locks in that
        corrected, intentional Phase 2B behaviour instead of the superseded
        Phase 2A-only boundary the old version of this test asserted."""
        section = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={}
        )
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        container_service.place_section(cell, section)

        section.refresh_from_db()
        cell.refresh_from_db()
        self.assertEqual(cell.section_id, section.pk, "legacy OneToOne must still be written by place_section")
        self.assertEqual(section.cell_id, cell.pk, "Phase 2B: place_section must also keep the new FK synchronized")
        self.assertEqual(section.cell_order, 0)

    def test_cell_order_uniqueness_only_enforced_when_cell_is_set(self):
        """Two Sections with no cell (both NULL) and ``cell_order=0`` must
        coexist freely — the conditional UniqueConstraint must not apply
        to legacy, unplaced Sections."""
        s1 = StorefrontSection.objects.create(page=self.page, section_key="rich_text", order=0, settings={})
        s2 = StorefrontSection.objects.create(page=self.page, section_key="rich_text", order=1, settings={})
        self.assertIsNone(s1.cell_id)
        self.assertIsNone(s2.cell_id)
        self.assertEqual(s1.cell_order, 0)
        self.assertEqual(s2.cell_order, 0)

    def test_cell_order_uniqueness_enforced_when_cell_is_set(self):
        """Once ``cell`` is actually set on two different Sections
        pointing at the same Cell with the same ``cell_order``, the
        conditional UniqueConstraint must reject the second one — this
        is the exact invariant Phase 2B will depend on to keep a Cell's
        blocks unambiguously ordered."""
        from django.db import IntegrityError, transaction as db_transaction

        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        s1 = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={}, cell=cell, cell_order=0
        )
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                StorefrontSection.objects.create(
                    page=self.page, section_key="rich_text", order=1, settings={}, cell=cell, cell_order=0
                )

    def test_deleting_a_cell_sets_section_cell_to_null_not_cascade(self):
        """``on_delete=SET_NULL`` (mirroring the legacy OneToOne's own
        on_delete behavior) — deleting a Cell must never delete the
        Section it was mirroring; it must only clear the new FK."""
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        section = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={}, cell=cell, cell_order=0
        )

        cell.delete()

        section.refresh_from_db()
        self.assertIsNone(section.cell_id)
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
