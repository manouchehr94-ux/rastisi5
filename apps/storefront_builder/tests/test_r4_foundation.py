from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase


class R4FoundationModelTests(TestCase):
    def test_r4_editor_is_disabled_by_default(self):
        field = StorefrontLayout._meta.get_field("r4_editor_enabled")
        self.assertFalse(field.default)

    def test_draft_edit_revision_starts_at_zero(self):
        field = StorefrontLayoutVersion._meta.get_field("edit_revision")
        self.assertEqual(field.default, 0)


class R4EditorRouteGateTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)

    def test_r4_route_is_unavailable_when_gate_is_off(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 404)

    def test_r4_route_renders_one_shell_when_gate_is_on(self):
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-r4-shell="true"')
        self.assertContains(response, 'id="r4PreviewFrame"')
        self.assertContains(response, 'id="r4Inspector"')
        self.assertContains(response, 'data-r4-inspector-open="false"')
