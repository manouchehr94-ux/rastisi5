import copy

from django.core.cache import cache
from django.test import TestCase

from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    STORE_APPEARANCE_CONFIG_KEY,
    ImmutableStoreAppearanceError,
    load_store_appearance_manifest,
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _manifest_with(**selections):
    raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
    raw["selections"].update(selections)
    return raw


class StoreAppearancePersistenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = layout_service.get_or_create_draft(self.store)

    def test_legacy_draft_without_manifest_derives_existing_live_selectors(self):
        self.draft.header_config = {"header_variant": "marketplace_search_first"}
        self.draft.footer_config = {
            "footer_variant": "marketplace_dense",
            "mobile_nav_variant": "luxury_floating_cart",
        }
        self.draft.appearance_config = {"motion": "dynamic"}
        self.draft.save(
            update_fields=["header_config", "footer_config", "appearance_config"]
        )

        manifest = load_store_appearance_manifest(self.draft)

        self.assertEqual(
            manifest.selections["header"],
            "header.marketplace_search_first.v1",
        )
        self.assertEqual(
            manifest.selections["footer"],
            "footer.marketplace_dense.v1",
        )
        self.assertEqual(
            manifest.selections["bottom_nav"],
            "bottom_nav.luxury_floating_cart.v1",
        )
        self.assertEqual(manifest.selections["motion"], "motion.dynamic.v1")
        self.assertEqual(
            manifest.selections["hero"],
            DEFAULT_STORE_APPEARANCE_MANIFEST.selections["hero"],
        )

    def test_persisted_manifest_is_validated_stored_and_mirrored_to_live_selectors(self):
        raw = _manifest_with(
            header="header.dark_tech.v1",
            footer="footer.premium_columns.v1",
            bottom_nav="bottom_nav.luxury_floating_cart.v1",
            motion="motion.none.v1",
        )

        persisted = persist_store_appearance_manifest(self.draft, raw)
        self.draft.refresh_from_db()

        self.assertEqual(manifest_to_primitive(persisted), raw)
        self.assertEqual(
            self.draft.appearance_config[STORE_APPEARANCE_CONFIG_KEY], raw
        )
        self.assertEqual(self.draft.header_config["header_variant"], "dark_tech")
        self.assertEqual(self.draft.footer_config["footer_variant"], "premium_columns")
        self.assertEqual(
            self.draft.footer_config["mobile_nav_variant"],
            "luxury_floating_cart",
        )
        self.assertEqual(self.draft.appearance_config["motion"], "none")

    def test_model_exposes_one_effective_manifest_boundary(self):
        raw = _manifest_with(header="header.boutique_centered.v1")
        persist_store_appearance_manifest(self.draft, raw)

        self.assertEqual(
            manifest_to_primitive(self.draft.effective_store_appearance_manifest()),
            raw,
        )

    def test_existing_appearance_validator_preserves_valid_manifest_state(self):
        raw = _manifest_with(card="card.legacy_default.v1")
        cleaned = layout_service.validate_appearance_config(
            {
                **self.draft.effective_appearance_config(),
                STORE_APPEARANCE_CONFIG_KEY: raw,
            }
        )

        self.assertEqual(cleaned[STORE_APPEARANCE_CONFIG_KEY], raw)

    def test_published_version_rejects_appearance_mutation(self):
        persist_store_appearance_manifest(self.draft, _manifest_with())
        published = layout_service.publish(self.store)

        with self.assertRaises(ImmutableStoreAppearanceError):
            persist_store_appearance_manifest(
                published,
                _manifest_with(header="header.dark_tech.v1"),
            )

        published.refresh_from_db()
        self.assertEqual(
            load_store_appearance_manifest(published).selections["header"],
            "header.legacy_default.v1",
        )

    def test_manifest_changes_the_rendering_content_fingerprint(self):
        before = self.draft.compute_fingerprint()

        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(hero="hero.split.v1"),
        )

        self.assertNotEqual(self.draft.compute_fingerprint(), before)

    def test_publish_clone_and_restore_round_trip_manifest_without_cross_version_drift(self):
        original = _manifest_with(header="header.dark_tech.v1")
        persist_store_appearance_manifest(self.draft, original)
        published = layout_service.publish(self.store)

        next_draft = layout_service.get_or_create_draft(self.store)
        self.assertEqual(
            manifest_to_primitive(load_store_appearance_manifest(next_draft)),
            original,
        )
        persist_store_appearance_manifest(
            next_draft,
            _manifest_with(header="header.boutique_centered.v1"),
        )
        published.refresh_from_db()
        self.assertEqual(
            load_store_appearance_manifest(published).selections["header"],
            "header.dark_tech.v1",
        )

        restored = layout_service.restore_version(self.store, published.pk)
        self.assertEqual(restored.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertEqual(
            manifest_to_primitive(load_store_appearance_manifest(restored)),
            original,
        )

    def test_first_draft_bootstrap_persists_explicit_safe_manifest(self):
        self.draft.refresh_from_db()

        self.assertEqual(
            self.draft.appearance_config[STORE_APPEARANCE_CONFIG_KEY],
            manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST),
        )
