import json
from unittest.mock import patch

from django.urls import reverse

from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


class R4MutationApiTestCase(StorefrontBuilderViewsTestCase):
    """Shared setUp: R4 gate ON, a Draft with one schema-enabled
    (hero_banner) section, matching the actual repository contracts
    (layout_service.get_or_create_draft, the StorefrontSection(version=...)
    convenience shim)."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0,
        )

    def _post_json(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _history_count(self):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()


class SuccessfulSchemaMutationTests(R4MutationApiTestCase):
    def test_autoplay_toggle_increments_revision_and_persists(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"autoplay": False},
            },
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["mutation_type"], "section.update_settings")
        self.assertEqual(body["new_revision"], starting_revision + 1)

        self.section.refresh_from_db()
        self.assertIs(self.section.settings["autoplay"], False)
        # unrelated legacy/wrapper settings survive the patch untouched.
        self.assertIn("responsive", self.section.settings)
        self.assertEqual(self.section.settings["hero_style"], "overlay")

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision + 1)

    def test_successful_mutation_writes_one_history_entry(self):
        before_count = self._history_count()
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"autoplay": False},
            },
        })
        self.assertEqual(self._history_count(), before_count + 1)


class PersianIntegerThroughMutationTests(R4MutationApiTestCase):
    def test_interval_ms_persian_digits_persist_as_integer(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"interval_ms": "۴۵۰۰"},
            },
        })
        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["interval_ms"], 4500)
        self.assertIsInstance(self.section.settings["interval_ms"], int)


class StaleRevisionTests(R4MutationApiTestCase):
    def test_stale_base_revision_is_rejected_and_nothing_changes(self):
        self.draft.edit_revision = 4
        self.draft.save(update_fields=["edit_revision"])
        original_settings = dict(self.section.settings)
        before_count = self._history_count()

        response = self._post_json({
            "base_revision": 3,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"autoplay": False},
            },
        })

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], "stale_revision")
        self.assertEqual(body["current_revision"], 4)

        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, 4)
        self.assertEqual(self._history_count(), before_count)


class TenantIsolationTests(R4MutationApiTestCase):
    def test_foreign_store_section_id_is_rejected_without_leaking_settings(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-mutation-other-store",
            admin_subdomain="r4-mutation-other-store",
        )
        other_layout = svc.get_or_create_layout(other_store)
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(
            version=other_draft, section_key="hero_banner", order=0,
        )
        other_original_settings = dict(other_section.settings)
        own_starting_revision = self.draft.edit_revision
        other_starting_revision = other_draft.edit_revision

        response = self._post_json({
            "base_revision": own_starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": other_section.pk,
                "patch": {"autoplay": False},
            },
        })

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIs(body["ok"], False)
        self.assertNotIn("settings", json.dumps(body))
        self.assertNotIn("autoplay", json.dumps(body))

        other_section.refresh_from_db()
        self.assertEqual(other_section.settings, other_original_settings)
        other_draft.refresh_from_db()
        self.assertEqual(other_draft.edit_revision, other_starting_revision)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, own_starting_revision)


class PublishedVersionImmutabilityTests(R4MutationApiTestCase):
    def test_section_on_published_version_is_not_mutable_via_r4(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        published_section = StorefrontSection.objects.create(
            version=published, section_key="hero_banner", order=0,
        )
        original_settings = dict(published_section.settings)
        starting_revision = self.draft.edit_revision

        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": published_section.pk,
                "patch": {"autoplay": False},
            },
        })

        self.assertEqual(response.status_code, 400)
        published_section.refresh_from_db()
        self.assertEqual(published_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)


class UnknownMutationTypeTests(R4MutationApiTestCase):
    def test_unknown_mutation_type_is_rejected(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "something.dynamic", "section_id": self.section.pk, "patch": {}},
        })
        self.assertEqual(response.status_code, 400)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)


class NonSchemaEnabledSectionTests(R4MutationApiTestCase):
    def test_section_without_settings_schema_is_rejected(self):
        # faq has no attached SettingsSchema (verified in Task 4 tests) —
        # section.update_settings must not fall back to arbitrary legacy
        # mutation for it under R4.
        faq_section = StorefrontSection.objects.create(
            version=self.draft, section_key="faq", order=1,
        )
        original_settings = dict(faq_section.settings)
        starting_revision = self.draft.edit_revision

        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": faq_section.pk,
                "patch": {"anything": "x"},
            },
        })

        self.assertEqual(response.status_code, 400)
        faq_section.refresh_from_db()
        self.assertEqual(faq_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)


class TransactionalFailureRegressionTests(R4MutationApiTestCase):
    def test_post_revision_check_failure_rolls_back_everything(self):
        """A mutation that fails validation AFTER the revision check has
        already passed (an unsupported settings key on a schema-enabled
        section) must leave section state, draft.edit_revision, and
        history completely untouched — proving the atomic boundary is
        real, not just the stale-revision path."""
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.section.settings)
        before_count = self._history_count()

        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"not_a_real_hero_field": "x"},
            },
        })

        self.assertEqual(response.status_code, 400)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)


class R3CompatibilityTests(R4MutationApiTestCase):
    def test_existing_r3_section_settings_route_still_works_without_base_revision(self):
        rich_text_section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=2,
        )
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[rich_text_section.pk]),
            {"body_html": "<p>متن تست R3</p>"},
        )
        self.assertEqual(response.status_code, 302)
        rich_text_section.refresh_from_db()
        self.assertIn("متن تست R3", rich_text_section.settings["body_html"])


class R4FeatureGateTests(R4MutationApiTestCase):
    def test_mutation_endpoint_is_unavailable_when_r4_gate_is_off(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"autoplay": False},
            },
        })
        self.assertEqual(response.status_code, 404)


class MethodContractTests(R4MutationApiTestCase):
    def test_get_is_rejected_with_405_and_does_not_mutate(self):
        starting_revision = self.draft.edit_revision
        response = self.client.get(reverse("dashboard:storefront-builder-r4-mutation"))
        self.assertEqual(response.status_code, 405)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)


class MalformedRequestShapeTests(R4MutationApiTestCase):
    def _assert_rejected_with_400(self, body_bytes, content_type="application/json"):
        starting_revision = self.draft.edit_revision
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=body_bytes,
            content_type=content_type,
        )
        self.assertEqual(response.status_code, 400)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)

    def test_malformed_json_body(self):
        self._assert_rejected_with_400(b"{not valid json")

    def test_top_level_json_list_instead_of_object(self):
        self._assert_rejected_with_400(json.dumps([1, 2, 3]).encode())

    def test_missing_base_revision(self):
        self._assert_rejected_with_400(json.dumps({
            "mutation": {"type": "section.update_settings", "section_id": self.section.pk, "patch": {}},
        }).encode())

    def test_base_revision_as_string(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": "3",
            "mutation": {"type": "section.update_settings", "section_id": self.section.pk, "patch": {}},
        }).encode())

    def test_base_revision_as_boolean(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": True,
            "mutation": {"type": "section.update_settings", "section_id": self.section.pk, "patch": {}},
        }).encode())

    def test_negative_base_revision(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": -1,
            "mutation": {"type": "section.update_settings", "section_id": self.section.pk, "patch": {}},
        }).encode())

    def test_missing_mutation(self):
        self._assert_rejected_with_400(json.dumps({"base_revision": 0}).encode())

    def test_mutation_not_an_object(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": 0, "mutation": "section.update_settings",
        }).encode())

    def test_missing_mutation_type(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": 0,
            "mutation": {"section_id": self.section.pk, "patch": {}},
        }).encode())

    def test_section_id_not_an_integer(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": "not-an-int",
                "patch": {"autoplay": False},
            },
        }).encode())

    def test_section_id_as_boolean(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": True,
                "patch": {"autoplay": False},
            },
        }).encode())

    def test_patch_not_an_object(self):
        self._assert_rejected_with_400(json.dumps({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": "autoplay=false",
            },
        }).encode())


# ------------------------------------------------------------------------
# Task 5 corrective review pass — stable settings error code
# ------------------------------------------------------------------------


class StableSettingsErrorCodeTests(R4MutationApiTestCase):
    def test_schema_invalid_patch_returns_stable_code_and_leaks_nothing(self):
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.section.settings)
        before_count = self._history_count()

        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"not_a_real_hero_field": "value-that-must-not-appear-in-response"},
            },
        })

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], "invalid_settings")

        raw_body = response.content.decode()
        self.assertNotIn("not_a_real_hero_field", raw_body)
        self.assertNotIn("value-that-must-not-appear-in-response", raw_body)

        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_legacy_validator_plain_value_error_becomes_controlled_400(self):
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.section.settings)
        before_count = self._history_count()

        with patch(
            "apps.storefront_builder.services.r4_mutation_service.clean_section_schema_patch",
            side_effect=ValueError("legacy-validation-details-must-not-leak"),
        ):
            response = self._post_json({
                "base_revision": starting_revision,
                "mutation": {
                    "type": "section.update_settings",
                    "section_id": self.section.pk,
                    "patch": {"autoplay": False},
                },
            })

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "invalid_settings")
        raw_body = response.content.decode()
        self.assertNotIn("legacy-validation-details-must-not-leak", raw_body)

        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)
