from pathlib import Path

from django.urls import reverse

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection

from .test_views import StorefrontBuilderViewsTestCase


class Phase274InteractionStabilityTests(StorefrontBuilderViewsTestCase):
    def _draft(self):
        from apps.storefront_builder.services import layout_service
        return layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_section_inspector_exposes_exact_instance_state_for_browser_sync(self):
        draft = self._draft()
        page = draft.get_page(StorefrontPage.PageType.HOME)
        definition = section_registry.get_definition("rich_text")
        section = StorefrontSection.objects.create(
            page=page, section_key=definition.key, order=0,
            is_locked=True, row_key="", row_span=12,
            settings=definition.default_settings(),
        )
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-inspector-section-id="{section.pk}"')
        self.assertContains(response, 'data-inspector-locked="1"')
        self.assertContains(response, 'data-inspector-row-key=""')

    def test_row_layout_refresh_event_runs_after_htmx_settle(self):
        draft = self._draft()
        page = draft.get_page(StorefrontPage.PageType.HOME)
        definition = section_registry.get_definition("rich_text")
        first = StorefrontSection.objects.create(
            page=page, section_key="rich_text", order=0,
            settings=definition.default_settings(),
        )
        StorefrontSection.objects.create(
            page=page, section_key="rich_text", order=1,
            settings=definition.default_settings(),
        )
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-row-layout", args=[first.pk]),
            {"layout_mode": "half"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger-After-Settle", response)
        self.assertNotIn("HX-Trigger-After-Swap", response)
        self.assertIn("sfbRowLayoutChanged", response["HX-Trigger-After-Settle"])

    def test_preview_exposes_row_and_lock_state_for_builder_sync(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-section-row-key")
        self.assertContains(response, "data-section-row-span")
        self.assertContains(response, "data-section-locked")

    def test_inline_toolbar_uses_registry_capabilities(self):
        render_service = (
            Path(__file__).resolve().parents[1] / "services" / "render_service.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            Path(__file__).resolve().parents[1]
            / "templates" / "storefront_builder" / "partials" / "responsive_section_wrapper.html"
        ).read_text(encoding="utf-8")
        self.assertIn('"definition": definition', render_service)
        self.assertIn("not item.definition.duplicable", wrapper)
        self.assertIn("not item.definition.removable", wrapper)

    def test_browser_runner_guards_dialog_drag_and_repeated_key_order(self):
        runner = (
            Path(__file__).resolve().parents[3]
            / "tools" / "storefront_builder_qa" / "run.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn("async function previewSectionIdOrder()", runner)
        self.assertIn("await waitSectionIdOrderChanged(before)", runner)
        self.assertIn("clickAcceptingDialog(toolbar.locator('[data-cmd=\"remove\"]'))", runner)
        self.assertIn("overlay.dataset.dropIndex !== ''", runner)
        self.assertIn("inline-toolbar-capability-contract", runner)
        self.assertIn("async function revealInlineToolbar(section)", runner)
        self.assertIn("await section.hover()", runner)
        self.assertIn("await toolbar.waitFor({ state: 'visible'", runner)
