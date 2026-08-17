from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase29OneClickRowLayoutTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self, order, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=order,
            settings={"body_html": f"section-{order}"},
            **kwargs,
        )

    def _post(self, section, mode):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-row-layout", args=[section.pk]),
            {"layout_mode": mode},
        )

    def test_existing_quarter_row_converts_directly_to_half(self):
        first = self._section(0, row_key="pair", row_span=3)
        second = self._section(1, row_key="pair", row_span=9)

        response = self._post(first, "half")

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.row_key, second.row_key), ("pair", "pair"))
        self.assertEqual((first.row_span, second.row_span), (6, 6))
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_existing_pair_can_expand_to_three_columns_using_next_standalone(self):
        first = self._section(0, row_key="pair", row_span=6)
        second = self._section(1, row_key="pair", row_span=6)
        third = self._section(2)

        self._post(first, "thirds")

        for item in (first, second, third):
            item.refresh_from_db()
        self.assertEqual([first.row_span, second.row_span, third.row_span], [4, 4, 4])
        self.assertEqual({first.row_key, second.row_key, third.row_key}, {"pair"})
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_existing_three_column_row_can_shrink_and_release_trailing_member(self):
        first = self._section(0, row_key="triple", row_span=4)
        second = self._section(1, row_key="triple", row_span=4)
        third = self._section(2, row_key="triple", row_span=4)

        self._post(first, "quarter_left")

        for item in (first, second, third):
            item.refresh_from_db()
        self.assertEqual((first.row_key, first.row_span), ("triple", 3))
        self.assertEqual((second.row_key, second.row_span), ("triple", 9))
        self.assertEqual((third.row_key, third.row_span), ("", 12))
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_selecting_nonfirst_member_edits_whole_row_from_row_start(self):
        first = self._section(0, row_key="pair", row_span=3)
        second = self._section(1, row_key="pair", row_span=9)

        self._post(second, "quarter_right")

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.row_span, second.row_span), (9, 3))
        self.assertEqual((first.row_key, second.row_key), ("pair", "pair"))

    def test_locked_existing_row_refuses_conversion_without_history(self):
        first = self._section(0, row_key="pair", row_span=3)
        second = self._section(1, row_key="pair", row_span=9, is_locked=True)
        before = list(
            self.page.sections.values_list("pk", "row_key", "row_span", "is_locked")
        )

        response = self._post(first, "half")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(self.page.sections.values_list("pk", "row_key", "row_span", "is_locked")),
            before,
        )
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

    def test_expansion_never_steals_member_from_next_composite_row(self):
        first = self._section(0, row_key="pair", row_span=6)
        self._section(1, row_key="pair", row_span=6)
        self._section(2, row_key="other", row_span=6)
        self._section(3, row_key="other", row_span=6)
        before = list(self.page.sections.values_list("pk", "row_key", "row_span"))

        response = self._post(first, "thirds")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(self.page.sections.values_list("pk", "row_key", "row_span")),
            before,
        )
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

    def test_direct_conversion_is_one_undo_step(self):
        first = self._section(0, row_key="pair", row_span=3)
        second = self._section(1, row_key="pair", row_span=9)
        first_sid, second_sid = first.stable_id, second.stable_id

        self._post(first, "half")
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

        undo = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertTrue(undo.json()["ok"])

        restored_first = self.page.sections.get(stable_id=first_sid)
        restored_second = self.page.sections.get(stable_id=second_sid)
        self.assertEqual((restored_first.row_key, restored_first.row_span), ("pair", 3))
        self.assertEqual((restored_second.row_key, restored_second.row_span), ("pair", 9))

    def test_legacy_row_endpoint_stays_compatible_but_is_hidden_from_new_content_inspector(self):
        first = self._section(0, row_key="pair", row_span=3)
        self._section(1, row_key="pair", row_span=9)

        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[first.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, "چیدمان ردیف")
        self.assertNotContains(
            response,
            reverse("dashboard:storefront-builder-section-row-layout", args=[first.pk]),
        )

        backend_response = self._post(first, "half")
        self.assertEqual(backend_response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.row_span, 6)
        container = self.page.containers.get()
        self.assertEqual(container.layout_key, "half")
