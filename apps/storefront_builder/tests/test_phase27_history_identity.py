from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import edit_history_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase275HistoryIdentityTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self):
        return StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>identity</p>"},
        )

    def test_snapshot_carries_database_id_as_restore_hint(self):
        section = self._section()
        state = edit_history_service.snapshot_draft(self.draft)
        rows = state["pages"][StorefrontPage.PageType.HOME]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], section.pk)
        self.assertEqual(str(rows[0]["stable_id"]), str(section.stable_id))

    def test_toggle_undo_and_redo_preserve_primary_key(self):
        section = self._section()
        original_pk = section.pk
        stable_id = section.stable_id

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-toggle", args=[original_pk])
        )
        self.assertEqual(response.status_code, 200)

        undo = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(undo.status_code, 200)
        self.assertTrue(undo.json()["ok"])
        restored = self.page.sections.get(stable_id=stable_id)
        self.assertEqual(restored.pk, original_pk)
        self.assertTrue(restored.is_active)

        redo = self.client.post(reverse("dashboard:storefront-builder-redo"))
        self.assertEqual(redo.status_code, 200)
        self.assertTrue(redo.json()["ok"])
        redone = self.page.sections.get(stable_id=stable_id)
        self.assertEqual(redone.pk, original_pk)
        self.assertFalse(redone.is_active)

    def test_remove_undo_restores_same_pk_and_old_command_url_is_valid(self):
        section = self._section()
        original_pk = section.pk
        stable_id = section.stable_id
        remove_url = reverse(
            "dashboard:storefront-builder-section-remove",
            args=[original_pk],
        )

        removed = self.client.post(remove_url)
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(self.page.sections.filter(stable_id=stable_id).exists())

        undo = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(undo.status_code, 200)
        self.assertTrue(undo.json()["ok"])
        restored = self.page.sections.get(stable_id=stable_id)
        self.assertEqual(restored.pk, original_pk)

        second_remove = self.client.post(remove_url)
        self.assertEqual(second_remove.status_code, 200)
        self.assertFalse(self.page.sections.filter(stable_id=stable_id).exists())

    def test_legacy_snapshot_without_id_still_restores(self):
        section = self._section()
        stable_id = section.stable_id
        state = edit_history_service.snapshot_draft(self.draft)
        for page_rows in state["pages"].values():
            for row in page_rows:
                row.pop("id", None)

        edit_history_service.restore_draft_state(self.draft, state)

        restored = self.page.sections.get(stable_id=stable_id)
        self.assertEqual(restored.section_key, "rich_text")
