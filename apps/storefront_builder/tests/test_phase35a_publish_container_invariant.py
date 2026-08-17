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
