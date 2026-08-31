import dataclasses
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.settings_schema import SettingsField, SettingsSchema
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase


def _inspector_url(pk):
    return reverse("dashboard:storefront-builder-r4-section-inspector", args=[pk])


class RichTextInspectorTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )

    def test_rich_text_inspector_shell_and_tabs(self):
        response = self.client.get(_inspector_url(self.rich_text_section.pk))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertContains(response, "data-r4-section-inspector")
        self.assertContains(response, f'data-r4-section-id="{self.rich_text_section.pk}"')
        self.assertContains(response, 'data-r4-tab="basic"')
        self.assertContains(response, 'data-r4-tab="advanced"')
        self.assertContains(response, 'aria-selected="true"')
        self.assertContains(response, 'aria-selected="false"')

        # Advanced panel is initially hidden; Basic is not.
        advanced_idx = content.index('data-r4-tab-panel="advanced"')
        self.assertIn("hidden", content[advanced_idx:advanced_idx + 60])

        self.assertContains(response, 'data-r4-field-key="body_html"')
        self.assertContains(response, 'data-r4-field-type="rich_text"')
        self.assertContains(response, "<textarea")
        self.assertContains(response, "متن")  # schema label

        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "storefront-builder/sections/")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, '<form')


class HeroInspectorGroupSplitTests(R4MutationApiTestCase):
    def test_basic_and_advanced_fields_come_from_schema_group(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        basic_start = content.index('data-r4-tab-panel="basic"')
        advanced_start = content.index('data-r4-tab-panel="advanced"')
        basic_chunk = content[basic_start:advanced_start]
        advanced_chunk = content[advanced_start:]

        for key in ("hero_style", "autoplay"):
            self.assertIn(f'data-r4-field-key="{key}"', basic_chunk)
        for key in ("interval_ms", "show_arrows", "show_dots", "loop", "text_position"):
            self.assertIn(f'data-r4-field-key="{key}"', advanced_chunk)

        # None of the advanced-only keys leak into the basic panel.
        for key in ("interval_ms", "show_arrows", "show_dots", "loop", "text_position"):
            self.assertNotIn(f'data-r4-field-key="{key}"', basic_chunk)


class CurrentValueHydrationTests(R4MutationApiTestCase):
    def test_hero_field_values_reflect_persisted_non_default_settings(self):
        self.section.settings = {
            **self.section.settings,
            "autoplay": False,
            "interval_ms": 4500,
            "text_position": "center",
        }
        self.section.save(update_fields=["settings"])

        response = self.client.get(_inspector_url(self.section.pk))
        content = response.content.decode()
        script_start = content.index('id="r4InspectorFieldValues"')
        json_start = content.index(">", script_start) + 1
        json_end = content.index("</script>", json_start)
        field_values = json.loads(content[json_start:json_end])

        self.assertIs(field_values["autoplay"], False)
        self.assertEqual(field_values["interval_ms"], 4500)
        self.assertEqual(field_values["text_position"], "center")
        # Untouched fields still surface their schema default.
        self.assertEqual(field_values["hero_style"], "overlay")

    def test_rich_text_field_values_reflect_persisted_body_html(self):
        rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
            settings={"body_html": "<p>متن فعلی</p>"},
        )
        response = self.client.get(_inspector_url(rich_text_section.pk))
        content = response.content.decode()
        script_start = content.index('id="r4InspectorFieldValues"')
        json_start = content.index(">", script_start) + 1
        json_end = content.index("</script>", json_start)
        field_values = json.loads(content[json_start:json_end])
        self.assertEqual(field_values["body_html"], "<p>متن فعلی</p>")


class ActiveDraftTenantScopingTests(R4MutationApiTestCase):
    def test_foreign_store_section_is_not_found(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر بازرس", slug="r4-inspector-other-store",
            admin_subdomain="r4-inspector-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(
            version=other_draft, section_key="hero_banner", order=0,
        )
        response = self.client.get(_inspector_url(other_section.pk))
        self.assertEqual(response.status_code, 404)

    def test_published_version_section_is_not_found(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        published_section = StorefrontSection.objects.create(
            version=published, section_key="hero_banner", order=0,
        )
        response = self.client.get(_inspector_url(published_section.pk))
        self.assertEqual(response.status_code, 404)


class FeatureGateTests(R4MutationApiTestCase):
    def test_inspector_unavailable_when_r4_gate_is_off(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 404)


class NonSchemaSectionTests(R4MutationApiTestCase):
    def test_faq_section_inspector_is_not_found(self):
        faq_section = StorefrontSection.objects.create(
            version=self.draft, section_key="faq", order=1,
        )
        response = self.client.get(_inspector_url(faq_section.pk))
        self.assertEqual(response.status_code, 404)


class MethodContractTests(R4MutationApiTestCase):
    def test_post_to_inspector_endpoint_is_405(self):
        response = self.client.post(_inspector_url(self.section.pk))
        self.assertEqual(response.status_code, 405)


class UnsupportedWidgetContractTests(R4MutationApiTestCase):
    def test_unsupported_field_type_raises_improperly_configured(self):
        real_definition = section_registry_module.get_definition("hero_banner")
        bad_schema = SettingsSchema(fields=(
            SettingsField("swatch", "رنگ", "color", "basic"),
        ))
        bad_definition = dataclasses.replace(real_definition, settings_schema=bad_schema)
        with patch(
            "apps.storefront_builder.r4_views.section_registry.get_definition",
            return_value=bad_definition,
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.get(_inspector_url(self.section.pk))


class CsrfCookieOnEditorLoadTests(R4MutationApiTestCase):
    def test_r4_editor_response_sets_csrf_cookie(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)


class R4EditorJsSourceContractTests(R4MutationApiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")

    def test_open_section_entry_point_exists(self):
        self.assertIn("openSection = function", self.js_source)

    def test_accepts_both_select_section_and_open_section_settings(self):
        self.assertIn("sfb:selectSection", self.js_source)
        self.assertIn("sfb:openSectionSettings", self.js_source)

    def test_does_not_handle_out_of_scope_preview_events(self):
        for event_type in ("sfb:openEntityEditor", "sfb:openHeaderSettings", "sfb:openFooterSettings"):
            self.assertNotIn(event_type, self.js_source)

    def test_validates_message_origin(self):
        self.assertIn("evt.origin", self.js_source)
        self.assertIn("window.location.origin", self.js_source)

    def test_validates_message_source_against_preview_frame(self):
        self.assertIn("evt.source", self.js_source)
        self.assertIn("previewFrame.contentWindow", self.js_source)

    def test_has_one_enqueue_and_one_send_mutation_function(self):
        self.assertEqual(self.js_source.count("enqueueMutation = function"), 1)
        self.assertEqual(self.js_source.count("sendMutation = function"), 1)

    def test_base_revision_uses_in_memory_revision(self):
        self.assertIn("base_revision: R4.revision", self.js_source)

    def test_revision_updated_from_server_response_only(self):
        self.assertIn("new_revision", self.js_source)
        self.assertIn("R4.revision = result.body.new_revision", self.js_source)

    def test_explicit_409_conflict_handling(self):
        self.assertIn("409", self.js_source)
        self.assertIn("conflict", self.js_source)

    def test_conflict_blocks_further_automatic_mutation_without_retry(self):
        # The same conflict guard must gate both enqueueing new mutations
        # and sending them — no automatic replay of the stale mutation.
        self.assertGreaterEqual(self.js_source.count("if (R4.conflict) return"), 2)
        self.assertNotIn("retry", self.js_source.lower())

    def test_reload_is_the_explicit_conflict_recovery_action(self):
        self.assertIn("window.location.reload()", self.js_source)

    def test_uses_task5_mutate_endpoint_and_not_r3_settings_endpoint(self):
        self.assertIn("mutate/", self.js_source)
        self.assertNotIn("section-settings", self.js_source)
        self.assertNotIn("/admin-portal/", self.js_source)

    def test_does_not_open_a_modal(self):
        self.assertNotIn("modal", self.js_source.lower())


# ------------------------------------------------------------------------
# Task 6 visual/product correction pass — the owner rejected the raw
# unstyled screenshots (visible <h2>/<p> tags, no sidebar collapse, no
# Inspector polish). This is a presentation-layer-only correction; the
# functional Task 6 contracts above must keep passing unmodified.
# ------------------------------------------------------------------------


class RichTextUsesMerchantEditorTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=1,
        )

    def test_rich_text_field_requests_existing_ckeditor_mount_contract(self):
        response = self.client.get(_inspector_url(self.rich_text_section.pk))
        self.assertContains(response, 'x-data="storefrontRichTextEditor()"')
        self.assertContains(response, 'x-init="mount()"')
        self.assertContains(response, "sfb-rich-editor")
        # The backing textarea must still carry the R4 field contract so
        # hydration/mutation keep working — this is additive styling, not
        # a second rich-text system.
        self.assertContains(response, 'data-r4-field-key="body_html"')
        self.assertContains(response, 'data-r4-field-type="rich_text"')


class R4EditorSidebarToggleMarkupTests(R4MutationApiTestCase):
    def test_editor_shell_includes_accessible_sidebar_toggle(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertContains(response, 'id="r4SidebarToggle"')
        self.assertContains(response, "aria-label=")
        self.assertContains(response, 'aria-expanded="false"')


class R4EditorJsSidebarContractTests(R4MutationApiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")

    def test_js_toggles_r4_specific_sidebar_expanded_state(self):
        self.assertIn("r4SidebarToggle", self.js_source)
        self.assertIn("r4SidebarExpanded", self.js_source)

    def test_js_does_not_persist_sidebar_state_across_loads(self):
        self.assertNotIn("localStorage", self.js_source)

    def test_mutate_endpoint_remains_the_only_write_path(self):
        self.assertIn("mutate/", self.js_source)
        # No second write endpoint is referenced anywhere in the source.
        self.assertEqual(self.js_source.count("method: 'POST'"), 1)

    def test_rich_text_save_flows_through_enqueue_mutation(self):
        self.assertIn("sfb-rich-editor", self.js_source)
        self.assertIn("focusout", self.js_source)
        # The focusout handler must itself call the same single queue —
        # not a second/parallel save path.
        focusout_idx = self.js_source.index("focusout")
        self.assertIn("enqueueMutation", self.js_source[focusout_idx:focusout_idx + 800])


class BaseAdminTemplateUntouchedTests(R4MutationApiTestCase):
    def test_base_admin_template_has_no_r4_specific_markup(self):
        base_admin_source = Path(
            settings.BASE_DIR,
            "apps/dashboard/templates/dashboard/base_admin.html",
        ).read_text(encoding="utf-8")
        self.assertNotIn("r4Sidebar", base_admin_source)
        self.assertNotIn("R4EditorSidebar", base_admin_source)
        self.assertNotIn("data-r4", base_admin_source)


class InspectorArchitectureUnchangedByPolishTests(R4MutationApiTestCase):
    def test_inspector_still_has_exactly_basic_and_advanced_tabs(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertContains(response, 'data-r4-tab="basic"')
        self.assertContains(response, 'data-r4-tab="advanced"')
        self.assertEqual(response.content.decode().count('role="tab"'), 2)

    def test_inspector_still_has_no_r3_modal_iframe_or_form_action(self):
        response = self.client.get(_inspector_url(self.section.pk))
        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, "sfb-modal")
        self.assertNotContains(response, "<form")
