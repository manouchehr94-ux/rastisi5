from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase35APublishContainerInvariantTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.page.containers.all().delete()

    def test_publish_never_silently_drops_an_unplaced_section(self):
        # A deliberately empty two-cell layout is valid merchant data and must
        # remain empty. An unplaced Section must be appended in a NEW single
        # Container rather than hijacking either empty Cell.
        empty = container_service.create_empty_container(self.page, "half", order=0)
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>must survive publish</p>"},
        )

        published = layout_service.publish(self.store, user=self.staff)

        self.assertEqual(published.pk, self.draft.pk)
        empty.refresh_from_db()
        self.assertEqual(empty.cells.filter(section__isnull=False).count(), 0)

        placement = self.page.containers.filter(cells__section=section).distinct().get()
        self.assertEqual(placement.layout_key, "single")
        self.assertEqual(placement.order, 1)
        cell = placement.cells.get()
        self.assertEqual(cell.span, 12)
        self.assertEqual(cell.section_id, section.pk)

    def test_publish_preserves_existing_container_placement(self):
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>placed</p>"},
        )
        container = container_service.create_empty_container(self.page, "half", order=0)
        target = container.cells.order_by("order", "id").first()
        target_sid = target.stable_id
        container_service.place_section(target, section)

        layout_service.publish(self.store, user=self.staff)

        container.refresh_from_db()
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(cells), 2)
        self.assertEqual(cells[0].stable_id, target_sid)
        self.assertEqual(cells[0].section_id, section.pk)
        self.assertIsNone(cells[1].section_id)

    # ------------------------------------------------------------------
    # Phase 2B — multi-block Cell coverage of the same invariant. These
    # extend (never weaken) the two tests above: a Cell holding several
    # ordered Blocks via the new ``StorefrontSection.cell``/``cell_order``
    # FK must survive Draft -> Publish exactly like a single-Block Cell
    # does, and none of its Blocks may be silently treated as orphaned
    # and re-wrapped into a brand-new Container by ``ensure_page_containers``
    # (which the ordinary ``publish()`` call path always runs first).
    # ------------------------------------------------------------------

    def test_publish_never_drops_any_block_in_a_multi_block_cell(self):
        heading = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={"body_html": "heading"},
        )
        text = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=1, settings={"body_html": "text"},
        )
        button = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=2, settings={"body_html": "button"},
        )
        container = container_service.create_empty_container(self.page, "single", order=0)
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        container_service.add_block(cell, button)

        layout_service.publish(self.store, user=self.staff)

        # No new "unplaced Section" Container was created — all three Blocks
        # were already correctly placed, so ensure_page_containers's
        # orphan-wrapping logic must never have touched them.
        self.assertEqual(self.page.containers.count(), 1)
        cell.refresh_from_db()
        blocks = list(container_service.get_cell_blocks(cell))
        self.assertEqual([b.pk for b in blocks], [heading.pk, text.pk, button.pk])
        for section in (heading, text, button):
            self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_publish_preserves_multi_block_order_through_container_render(self):
        from apps.storefront_builder.services import render_service

        first = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=0, settings={"body_html": "first"},
        )
        second = StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=1, settings={"body_html": "second"},
        )
        container = container_service.create_empty_container(self.page, "single", order=0)
        cell = container.cells.get()
        container_service.add_block(cell, second)
        container_service.add_block(cell, first, at_index=0)

        published = layout_service.publish(self.store, user=self.staff)

        published_page = published.get_page(StorefrontPage.PageType.HOME)
        items = render_service.build_page_render_items(published_page, self.store)
        rendered = render_service.build_container_render_items(published_page, items)
        composition = rendered[0]
        cell_entry = composition["cells"][0]
        self.assertEqual(
            [item["section"].pk for item in cell_entry["items"]],
            [first.pk, second.pk],
        )
