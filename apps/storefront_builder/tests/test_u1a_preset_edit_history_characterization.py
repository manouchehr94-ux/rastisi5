"""U1A — Engine Metadata Contract Foundation, item J/§15.

R1 marked one thing UNVERIFIED: whether applying a ``LayoutPresetDefinition``
(``services/preset_service.apply_preset``) currently produces exactly one
logical Undo/Redo history event, or several/none.

This file only characterizes the CURRENT behaviour — it does not change
``preset_service.apply_preset``, ``views.storefront_apply_layout_preset``, or
``edit_history_service`` in any way. Per the U1A brief: if the answer had
turned out to be "not exactly one event", the correct move would be to
report that and defer any behavioural change to U7 (Reset design), never to
adjust application behaviour just to make a test pass. The finding recorded
below (exactly one event) is what the existing code already does, traced
directly from source before this file was written:

- ``views.py::storefront_apply_layout_preset`` is decorated with
  ``@_record_edit_history(...)`` (views.py), which wraps the *entire* view
  call in exactly one ``_history_before``/``_history_record`` pair
  (views.py::_record_edit_history).
- ``edit_history_service.record_change`` creates at most one
  ``StorefrontEditHistoryEntry`` row per call, comparing one full
  before/after Draft snapshot.
- ``preset_service.apply_preset`` itself is one ``@transaction.atomic``
  function and never calls ``edit_history_service`` directly — history
  recording happens entirely in the view layer that wraps it.

Together this means: applying a preset that rewrites multiple pages in one
request still yields exactly one row in ``StorefrontEditHistoryEntry``, and
Undo restores every page it touched in a single step.
"""

from apps.storefront_builder.models import StorefrontEditHistoryEntry
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.tests.test_preset_service import PresetServiceTestCase


class PresetApplyEditHistoryCharacterizationTests(PresetServiceTestCase):
    def test_applying_a_preset_via_the_view_creates_exactly_one_history_entry(self):
        draft = svc.get_or_create_draft(self.store)
        before_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

        resp = self.admin_client.post(
            reverse_apply_preset_url(),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)

        after_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()
        self.assertEqual(
            after_count - before_count, 1,
            "applying one LayoutPresetDefinition must create exactly one edit-history entry",
        )

    def test_the_one_history_entry_undoes_every_page_the_preset_touched_at_once(self):
        draft = svc.get_or_create_draft(self.store)
        home_before = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))

        resp = self.admin_client.post(
            reverse_apply_preset_url(),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        draft.refresh_from_db()
        home_after_apply = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertNotEqual(home_before, home_after_apply)  # the preset really changed the page

        entry = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).latest("sequence")
        self.assertEqual(entry.action_label, "اعمال پیش‌تنظیم صفحه‌آرایی")

        undo_resp = self.admin_client.post(reverse_undo_url())
        self.assertEqual(undo_resp.status_code, 200)
        draft.refresh_from_db()
        home_after_undo = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(
            home_after_undo, home_before,
            "one Undo must fully restore the pre-preset state of every page the preset touched",
        )

    def test_a_rejected_preset_apply_creates_no_history_entry(self):
        """A no-op/failed submission must not pollute the history log — this
        mirrors record_change's own before==after no-op filtering."""
        draft = svc.get_or_create_draft(self.store)
        before_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

        # Missing confirm_preset_apply=1 while pages already have sections —
        # the view rejects this without calling apply_preset at all.
        resp = self.admin_client.post(reverse_apply_preset_url(), {"preset_key": "dense_catalog"})
        self.assertEqual(resp.status_code, 302)

        after_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()
        self.assertEqual(after_count, before_count)


def reverse_apply_preset_url():
    from django.urls import reverse
    return reverse("dashboard:storefront-builder-apply-preset")


def reverse_undo_url():
    from django.urls import reverse
    return reverse("dashboard:storefront-builder-undo")
