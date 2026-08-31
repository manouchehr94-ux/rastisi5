from django.test import TestCase

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion


class R4FoundationModelTests(TestCase):
    def test_r4_editor_is_disabled_by_default(self):
        field = StorefrontLayout._meta.get_field("r4_editor_enabled")
        self.assertFalse(field.default)

    def test_draft_edit_revision_starts_at_zero(self):
        field = StorefrontLayoutVersion._meta.get_field("edit_revision")
        self.assertEqual(field.default, 0)
