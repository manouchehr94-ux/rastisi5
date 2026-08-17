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

    def test_library_cannot_overwrite_hidden_occupied_cell(self):
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
        self.assertEqual(cell.section_id, hidden.pk)
        self.assertEqual(self.page.sections.count(), 1)
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

    def test_hidden_trailing_content_blocks_shrink_without_data_loss(self):
        first = self._section(0)
        second = self._section(1, is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        cells = list(container.cells.order_by("order", "id"))
        container_service.place_section(cells[0], first)
        container_service.place_section(cells[1], second)
        before = list(container.cells.values_list("pk", "span", "section_id"))

        response = self.client.post(
            reverse("dashboard:storefront-builder-container-layout", args=[container.pk]),
            {"layout_key": "single"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(container.cells.values_list("pk", "span", "section_id")), before)
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

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

    def test_active_cell_toolbar_uses_direct_cell_clear_action(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")

        self.assertIn(f'data-cell-clear="{cell.pk}"', html)
        self.assertIn('title="حذف محتوا از این خانه"', html)
        self.assertIn("🗑", html)
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
