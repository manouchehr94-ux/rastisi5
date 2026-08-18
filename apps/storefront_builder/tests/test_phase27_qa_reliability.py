from pathlib import Path
from django.urls import reverse

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection

from .test_views import StorefrontBuilderViewsTestCase


class Phase27QAReliabilityTests(StorefrontBuilderViewsTestCase):
    def _draft(self):
        from apps.storefront_builder.services import layout_service
        return layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_editor_uses_alpine_component_root_for_shared_endpoint_dataset(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertNotIn("this.$el.dataset", html)
        # Container/Cell is now the primary composition API. The legacy
        # section-add dataset remains on the root for compatibility, but new
        # content insertion reads the real cell/container endpoints.
        self.assertIn("this.$root.dataset.cellAddSectionUrl", html)
        self.assertIn("this.$root.dataset.containerAddUrl", html)
        self.assertIn("this.$root.dataset.undoUrl", html)
        self.assertIn("this.$root.dataset.redoUrl", html)
        self.assertIn("this.$root.dataset.sectionListUrl", html)

    def test_section_settings_save_preserves_non_home_builder_page(self):
        draft = self._draft()
        page = draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)
        definition = section_registry.get_definition("rich_text")
        section = StorefrontSection.objects.create(
            page=page,
            section_key="rich_text",
            order=0,
            settings=definition.default_settings(),
        )

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "body_html": "<p>QA</p>",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("dashboard:storefront-builder-editor") + "?page=product_detail",
        )

class Phase27CapabilityContractTests(StorefrontBuilderViewsTestCase):
    def _draft(self):
        from apps.storefront_builder.services import layout_service
        return layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_inspector_disables_duplicate_when_registry_disallows_it(self):
        draft = self._draft()
        page = draft.get_page(StorefrontPage.PageType.HOME)
        definition = section_registry.get_definition("newsletter")
        self.assertFalse(definition.duplicable)
        section = StorefrontSection.objects.create(
            page=page,
            section_key=definition.key,
            order=0,
            settings=definition.default_settings(),
        )
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        command = f"sectionCommand({section.pk}, 'duplicate')"
        position = html.index(command)
        fragment = html[position:position + 180]
        self.assertIn("disabled", fragment)

    def test_inspector_template_guards_remove_with_registry_and_lock(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "dashboard"
            / "storefront_builder"
            / "partials"
            / "section_settings_form.html"
        )
        source = template_path.read_text(encoding="utf-8")
        self.assertIn(
            "{% if not definition.duplicable %}disabled{% endif %}",
            source,
        )
        self.assertIn(
            "{% if section.is_locked or not definition.removable %}disabled{% endif %}",
            source,
        )

