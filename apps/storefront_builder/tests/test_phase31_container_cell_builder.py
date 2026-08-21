from django.urls import reverse

from apps.storefront_builder.models import StorefrontCell, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase31ContainerCellBuilderTests(StorefrontBuilderViewsTestCase):
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

    def _layout_url(self, container):
        return reverse("dashboard:storefront-builder-container-layout", args=[container.pk])

    def test_editor_exposes_layout_first_container_cell_workflow(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        for marker in (
            "افزودن Section",
            "هر کامپوننت را داخل هر ستون",
            "sfb-v3-layout-grid",
            "چیدمان آزاد",
            "createContainer('half')",
            "addContentBlock(",
            "openCellLibrary(",
            "data-container-add-url=",
            "data-cell-add-section-url=",
            "data-block-move-url-template=",
            "data-block-remove-url-template=",
            "storefrontContainerState",
        ):
            self.assertContains(response, marker)
        self.assertNotContains(response, "sfb-library-drop-overlay")

    def test_add_half_container_creates_two_real_empty_cells_and_one_history_step(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-container-add"),
            {"page": "home", "layout_key": "half"},
        )
        self.assertEqual(response.status_code, 200)
        container = self.page.containers.get()
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(container.layout_key, "half")
        self.assertEqual([cell.span for cell in cells], [6, 6])
        self.assertEqual([cell.section_id for cell in cells], [None, None])
        self.assertEqual(self.draft.edit_history_entries.count(), 1)
        self.assertIn("sfbContainerAdded", response.headers["HX-Trigger-After-Settle"])

    def test_single_content_to_half_preserves_content_and_adds_empty_cell(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        original_cell = container.cells.get()
        original_cell_sid = original_cell.stable_id
        container_service.place_section(original_cell, section)

        response = self.client.post(self._layout_url(container), {"layout_key": "half"})

        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(container.layout_key, "half")
        self.assertEqual([cell.span for cell in cells], [6, 6])
        self.assertEqual(cells[0].stable_id, original_cell_sid)
        self.assertEqual(cells[0].section_id, section.pk)
        self.assertIsNone(cells[1].section_id)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_single_content_to_quarters_keeps_content_and_creates_three_empty_cells(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)

        self.client.post(self._layout_url(container), {"layout_key": "quarters"})

        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual([cell.span for cell in cells], [3, 3, 3, 3])
        self.assertEqual([cell.section_id for cell in cells], [section.pk, None, None, None])

    def test_shrink_merges_trailing_content_into_last_surviving_cell_as_one_history_step(self):
        """Phase 2C REPLACES the previous Phase 2B behaviour asserted here
        (refuse the shrink and record no history whenever a trailing Cell
        held content). The approved V3 prototype's own ``applyLayout()``
        requires a layout change to NEVER silently destroy content — with
        Phase 2B's multi-block infrastructure now in place, refusing is no
        longer the safest available behaviour: the merchant's content is
        preserved by merging every removed Cell's Blocks into the last
        surviving Cell (relative order preserved) instead of blocking the
        resize outright. This is documented, intentional, approved new
        behaviour, not a regression — the underlying requirement ("content
        must never be silently destroyed") is honoured even more strongly
        than before, since now the merchant doesn't have to manually move
        content out of the way first."""
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cells = list(container.cells.order_by("order", "id"))
        container_service.place_section(cells[0], first)
        container_service.place_section(cells[1], second)

        response = self.client.post(self._layout_url(container), {"layout_key": "single"})

        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        remaining_cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(remaining_cells), 1)
        surviving_cell = remaining_cells[0]
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(surviving_cell)],
            [first.pk, second.pk],
        )
        # A single logical layout-change operation, not one history entry
        # per moved Block.
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_content_library_adds_section_to_the_exact_empty_cell(self):
        container = container_service.create_empty_container(self.page, "half")
        first, second = list(container.cells.order_by("order", "id"))

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"page": "home", "cell_id": second.pk, "section_key": "rich_text"},
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.section_id)
        self.assertIsNotNone(second.section_id)
        self.assertEqual(second.section.section_key, "rich_text")
        self.assertEqual(second.section.page_id, self.page.pk)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)
        self.assertIn("sfbContentAdded", response.headers["HX-Trigger-After-Settle"])

    def test_clear_content_leaves_the_cell_and_container_alive(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "half")
        cell = container.cells.order_by("order", "id").first()
        cell_sid = cell.stable_id
        container_sid = container.stable_id
        container_service.place_section(cell, section)

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        restored_cell = StorefrontCell.objects.get(stable_id=cell_sid, container__stable_id=container_sid)
        self.assertIsNone(restored_cell.section_id)
        self.assertEqual(self.page.containers.get(stable_id=container_sid).cells.count(), 2)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_preview_renders_empty_cells_before_content_exists(self):
        container_service.create_empty_container(self.page, "half")

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-layout="half"')
        self.assertContains(response, 'class="rcontainer-cell', count=2)
        self.assertContains(response, "افزودن محتوا", count=2)
        self.assertContains(response, "data-empty-cell=", count=2)

    def test_container_settings_persist_gap_mobile_and_vertical_alignment(self):
        container = container_service.create_empty_container(self.page, "half")

        response = self.client.post(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk]),
            {"gap": "26", "mobile_mode": "same", "vertical_align": "center"},
        )

        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        settings = container_service.effective_container_settings(container.settings)
        self.assertEqual(settings["gap"], 26)
        self.assertEqual(settings["mobile_mode"], "same")
        self.assertEqual(settings["vertical_align"], "center")
        self.assertEqual(settings["content_width"], "standard")

    def test_layout_change_is_one_real_undo_step(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        container_sid = container.stable_id
        first_cell = container.cells.get()
        container_service.place_section(first_cell, section)

        self.client.post(self._layout_url(container), {"layout_key": "half"})
        self.assertEqual(self.draft.edit_history_entries.count(), 1)
        self.assertEqual(self.page.containers.get(stable_id=container_sid).cells.count(), 2)

        undo = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertTrue(undo.json()["ok"])
        restored = self.page.containers.get(stable_id=container_sid)
        self.assertEqual(restored.layout_key, "single")
        cells = list(restored.cells.order_by("order", "id"))
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0].span, 12)
        self.assertEqual(cells[0].section.stable_id, section.stable_id)

    def test_ensure_page_containers_appends_unplaced_content_after_order_zero(self):
        container_service.create_empty_container(self.page, "single", order=0)
        section = self._section()

        container_service.ensure_page_containers(self.page)

        containers = list(self.page.containers.order_by("order", "id"))
        self.assertEqual([item.order for item in containers], [0, 1])
        self.assertEqual(containers[1].cells.get().section_id, section.pk)


    def test_published_context_uses_container_layout_as_source_of_truth(self):
        from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context

        section = self._section()
        container = container_service.create_empty_container(self.page, "half")
        container_service.place_section(container.cells.order_by("order", "id").first(), section)
        published = layout_service.publish(self.store)

        class Request:
            pass

        context = build_universal_storefront_context(
            Request(), self.store, StorefrontPage.PageType.HOME
        )
        self.assertTrue(context["use_container_layout"])
        self.assertEqual(context["storefront_version"].pk, published.pk)
        self.assertEqual(len(context["render_containers"]), 1)
        composition = context["render_containers"][0]
        self.assertEqual(composition["container"].layout_key, "half")
        self.assertEqual([entry["cell"].span for entry in composition["cells"]], [6, 6])
        self.assertIsNotNone(composition["cells"][0]["item"])
        self.assertIsNone(composition["cells"][1]["item"])

    def test_section_inspector_no_longer_exposes_legacy_row_layout_controls(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)

        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این پنل فقط همین بلاک را تنظیم می‌کند")
        self.assertContains(response, "تنظیم چیدمان")
        self.assertNotContains(response, "چیدمان ردیف")
        self.assertNotContains(
            response,
            reverse("dashboard:storefront-builder-section-row-layout", args=[section.pk]),
        )
