from django.urls import reverse

from apps.storefront_builder.models import StorefrontCell, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase31AHiddenCellSemanticsTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self, order=0, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=order,
            settings={"body_html": f"section-{order}"},
            **kwargs,
        )

    def test_hidden_section_is_occupied_placeholder_not_empty_cell(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        first, second = list(container.cells.order_by("order", "id"))
        container_service.place_section(first, hidden)

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-hidden-section="{hidden.pk}"', html)
        self.assertIn("این محتوا مخفی است؛ خانه خالی نیست.", html)
        self.assertIn(f'data-cell-clear="{first.pk}"', html)
        self.assertIn(f'data-hidden-toggle="{hidden.pk}"', html)
        self.assertNotIn(f'data-empty-cell="{first.pk}"', html)
        self.assertIn(f'data-empty-cell="{second.pk}"', html)

    def test_library_appends_to_hidden_occupied_cell_without_overwriting_hidden_block(self):
        """V3 Free Layout intentionally supersedes the old single-block
        rejection: an occupied Cell may receive another Block, while hidden
        content remains placed and unchanged."""
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, hidden)

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"page": "home", "cell_id": cell.pk, "section_key": "rich_text"},
        )

        self.assertEqual(response.status_code, 200)
        cell.refresh_from_db()
        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].pk, hidden.pk)
        self.assertFalse(blocks[0].is_active)
        self.assertEqual(blocks[1].section_key, "rich_text")
        self.assertEqual([b.cell_order for b in blocks], [0, 1])
        # The legacy mirror still points at the original first Block; the new
        # second Block lives only through Section.cell/cell_order.
        self.assertEqual(cell.section_id, hidden.pk)
        self.assertEqual(self.page.sections.count(), 2)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_hidden_trailing_content_survives_shrink_via_merge_not_refusal(self):
        """Phase 2C REPLACES the previous Phase 2B behaviour asserted here
        (refuse the shrink whenever a trailing Cell — including one holding
        only hidden/inactive content — was non-empty). Hidden content is
        still content: it must survive a shrink by being merged into the
        surviving Cell (never dropped merely because its own Cell shrinks
        away), exactly like visible content. "Not currently visible" must
        never be treated as "empty" — this test now proves the merge
        happens, rather than proving the operation was refused."""
        first = self._section(0)
        second = self._section(1, is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        cells = list(container.cells.order_by("order", "id"))
        container_service.place_section(cells[0], first)
        container_service.place_section(cells[1], second)

        response = self.client.post(
            reverse("dashboard:storefront-builder-container-layout", args=[container.pk]),
            {"layout_key": "single"},
        )

        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        remaining_cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(remaining_cells), 1)
        surviving_cell = remaining_cells[0]
        blocks = container_service.get_cell_blocks(surviving_cell)
        self.assertEqual([b.pk for b in blocks], [first.pk, second.pk])
        # The hidden Section must still physically exist and remain hidden
        # (merge never changes is_active) — merely relocated, not deleted
        # or silently made permanently invisible.
        second.refresh_from_db()
        self.assertFalse(second.is_active)
        self.assertTrue(StorefrontSection.objects.filter(pk=second.pk).exists())
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_cell_clear_really_deletes_hidden_content_and_keeps_layout(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        cell = container.cells.order_by("order", "id").first()
        cell_sid = cell.stable_id
        container_sid = container.stable_id
        container_service.place_section(cell, hidden)

        response = self.client.post(reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=hidden.pk).exists())
        restored = StorefrontCell.objects.get(stable_id=cell_sid, container__stable_id=container_sid)
        self.assertIsNone(restored.section_id)
        self.assertEqual(self.page.containers.get(stable_id=container_sid).cells.count(), 2)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_active_cell_toolbar_removes_only_selected_block_and_keeps_cell_clear_distinct(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")

        self.assertIn(f'data-block-remove="{section.pk}"', html)
        self.assertIn('title="حذف فقط این بلاک"', html)
        self.assertIn("🗑", html)
        # Whole-cell clear remains a separate action for hidden/cell-context
        # controls; it is no longer overloaded by the selected Block toolbar.
        self.assertIn("var clearCellBtn = evt.target.closest('[data-cell-clear]');", html)

    def test_container_settings_explains_hidden_is_not_empty(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        container_service.place_section(container.cells.order_by("order", "id").first(), hidden)

        response = self.client.get(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خانه 1:")
        self.assertContains(response, "مخفی")
        self.assertContains(response, "مخفی کردن")
        self.assertContains(response, "آن خانه را خالی نمی‌کند")
