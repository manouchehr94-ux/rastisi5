import copy
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder import global_region_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service, render_service
from apps.storefront_builder.services.storefront_context_service import (
    build_universal_storefront_context,
)
from apps.storefront_builder.storefront_appearance.contracts import (
    InvalidStoreAppearanceContract,
)
from apps.storefront_builder.storefront_appearance.families import (
    COMPONENT_FAMILIES,
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    STORE_APPEARANCE_CONFIG_KEY,
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
)
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _manifest_with(**selections):
    raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
    raw["selections"].update(selections)
    return raw


class _FakeRequest:
    pass


class StoreAppearanceRenderResolverTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = layout_service.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.hero = StorefrontSection.objects.create(
            page=self.page,
            section_key="hero_banner",
            order=0,
            settings={"hero_style": "overlay"},
        )

    def _resolve(self, version=None):
        resolver = getattr(
            render_service, "resolve_store_appearance_render_state", None
        )
        self.assertIsNotNone(
            resolver,
            "A7 requires one shared Store Appearance render resolver",
        )
        return resolver(version or self.draft)

    def _global_template(self, state, family_key):
        resolver = getattr(
            render_service, "store_appearance_global_renderer_template", None
        )
        self.assertIsNotNone(
            resolver,
            "A7 requires registry-owned global renderer resolution",
        )
        legacy_config = (
            self.draft.effective_header_config()
            if family_key == "header"
            else self.draft.effective_footer_config()
        )
        return resolver(state, family_key, legacy_config)

    def test_resolver_returns_one_typed_component_per_registered_family(self):
        state = self._resolve()

        self.assertEqual(state.version_id, self.draft.pk)
        self.assertEqual(set(state.components), set(COMPONENT_FAMILIES))
        for family_key, resolved in state.components.items():
            self.assertEqual(resolved.family.key, family_key)
            self.assertEqual(resolved.component.family_key, family_key)
            self.assertEqual(
                resolved.component.key,
                state.manifest.selections[family_key],
            )
            self.assertIsNotNone(resolved.implementation)

    def test_build_page_resolves_store_appearance_once_and_reuses_same_state_in_items(self):
        real_resolver = getattr(
            render_service, "resolve_store_appearance_render_state", None
        )
        self.assertIsNotNone(real_resolver)
        with patch.object(
            render_service,
            "resolve_store_appearance_render_state",
            wraps=real_resolver,
        ) as resolver:
            items = render_service.build_page_render_items(self.page, self.store)

        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(len(items), 1)
        state = items[0]["store_appearance"]
        self.assertIs(items[0]["context"]["store_appearance"], state)
        self.assertEqual(state.version_id, self.draft.pk)

    def test_unknown_legacy_selectors_fall_back_safely_without_rewriting_legacy_state(self):
        appearance = dict(self.draft.appearance_config or {})
        appearance.pop(STORE_APPEARANCE_CONFIG_KEY, None)
        appearance["motion"] = "retired-motion-value"
        self.draft.appearance_config = appearance
        self.draft.header_config = {"header_variant": "retired-header-value"}
        self.draft.footer_config = {
            "footer_variant": "retired-footer-value",
            "mobile_nav_variant": "retired-mobile-nav-value",
        }
        self.draft.save(
            update_fields=["appearance_config", "header_config", "footer_config"]
        )

        state = self._resolve()

        self.assertEqual(state.component("header").component.key, "header.legacy_default.v1")
        self.assertEqual(state.component("footer").component.key, "footer.legacy_default.v1")
        self.assertEqual(state.component("bottom_nav").component.key, "bottom_nav.hidden.v1")
        self.assertEqual(state.component("motion").component.key, "motion.subtle.v1")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["header_variant"], "retired-header-value")
        self.assertEqual(self.draft.appearance_config["motion"], "retired-motion-value")

    def test_malformed_new_manifest_is_not_hidden_by_render_fallback(self):
        raw = _manifest_with()
        raw["selections"]["header"] = "header.not_registered.v1"
        self.draft.appearance_config = {
            **(self.draft.appearance_config or {}),
            STORE_APPEARANCE_CONFIG_KEY: raw,
        }
        self.draft.save(update_fields=["appearance_config"])

        with self.assertRaises(InvalidStoreAppearanceContract):
            self._resolve()

    def test_persisted_renderer_like_noise_never_controls_global_template_path(self):
        appearance = dict(self.draft.appearance_config or {})
        appearance.pop(STORE_APPEARANCE_CONFIG_KEY, None)
        appearance["renderer"] = "../../merchant-controlled.html"
        self.draft.appearance_config = appearance
        self.draft.header_config = {
            "header_variant": "dark_tech",
            "renderer": "../../merchant-controlled-header.html",
        }
        self.draft.save(update_fields=["appearance_config", "header_config"])

        state = self._resolve()
        template_name = self._global_template(state, "header")
        trusted = global_region_registry.get_global_variant(
            global_region_registry.GLOBAL_HEADER_REGION,
            "dark_tech",
        ).renderer

        self.assertEqual(template_name, trusted)
        self.assertNotIn("merchant-controlled", template_name)

    def test_manifest_settings_cannot_supply_a_renderer_path(self):
        raw = _manifest_with(header="header.dark_tech.v1")
        raw["settings"] = {"renderer": "../../merchant-controlled-manifest.html"}
        before = copy.deepcopy(self.draft.appearance_config)

        with self.assertRaises(InvalidStoreAppearanceContract):
            persist_store_appearance_manifest(self.draft, raw)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config, before)

    def test_manifest_hero_selection_drives_existing_registered_variant_without_db_mutation(self):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(hero="hero.split.v1"),
        )
        state = self._resolve()

        items = render_service.build_page_render_items(
            self.page,
            self.store,
            store_appearance=state,
        )

        self.assertEqual(items[0]["active_variant"].key, "split")
        self.assertIn("hero_banner_split", items[0]["template_name"])
        self.assertEqual(items[0]["context"]["settings"]["hero_style"], "split")
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.settings["hero_style"], "overlay")

    def test_section_variant_component_does_not_override_unrelated_section_type(self):
        product = StorefrontSection.objects.create(
            page=self.page,
            section_key="product_section",
            order=1,
            settings={"display_mode": "grid", "source_type": "newest"},
        )
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(hero="hero.split.v1"),
        )

        items = {
            item["section"].section_key: item
            for item in render_service.build_page_render_items(self.page, self.store)
        }

        self.assertEqual(items["product_section"]["active_variant"].key, "grid")
        self.assertEqual(
            items["product_section"]["context"]["settings"]["display_mode"],
            "grid",
        )
        product.refresh_from_db()
        self.assertEqual(product.settings["display_mode"], "grid")

    def test_safe_default_section_component_preserves_existing_legacy_variant(self):
        self.hero.settings = {"hero_style": "luxury_showcase"}
        self.hero.save(update_fields=["settings"])

        items = render_service.build_page_render_items(self.page, self.store)

        self.assertEqual(items[0]["active_variant"].key, "luxury_showcase")
        self.assertIn("hero_banner_luxury", items[0]["template_name"])
        self.assertEqual(
            items[0]["context"]["settings"]["hero_style"],
            "luxury_showcase",
        )

    def test_safe_default_global_component_preserves_existing_legacy_selector(self):
        self.draft.header_config = layout_service.validate_header_config(
            {"show_cart": True, "header_variant": "dark_tech"}
        )
        self.draft.save(update_fields=["header_config"])

        state = self._resolve()
        template_name = self._global_template(state, "header")
        dark_tech = global_region_registry.get_global_variant(
            global_region_registry.GLOBAL_HEADER_REGION, "dark_tech"
        ).renderer

        self.assertEqual(
            state.component("header").component.key,
            "header.legacy_default.v1",
        )
        self.assertEqual(template_name, dark_tech)

    def test_manifest_global_selection_is_authoritative_over_stale_mirrored_selector(self):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(header="header.dark_tech.v1"),
        )
        self.draft.header_config = {
            **(self.draft.header_config or {}),
            "header_variant": "boutique_centered",
        }
        self.draft.save(update_fields=["header_config"])

        state = self._resolve()
        template_name = self._global_template(state, "header")
        dark_tech = global_region_registry.get_global_variant(
            global_region_registry.GLOBAL_HEADER_REGION, "dark_tech"
        ).renderer

        self.assertEqual(state.component("header").component.key, "header.dark_tech.v1")
        self.assertEqual(template_name, dark_tech)

    def test_state_from_another_version_cannot_be_threaded_into_page_renderer(self):
        state = self._resolve()
        published = layout_service.publish(self.store)
        self.assertEqual(state.version_id, published.pk)

        new_draft = layout_service.get_or_create_draft(self.store)
        self.assertNotEqual(new_draft.pk, state.version_id)

        with self.assertRaises(ValueError):
            render_service.build_page_render_items(
                new_draft.get_page(StorefrontPage.PageType.HOME),
                self.store,
                store_appearance=state,
            )


class PreviewPublicStoreAppearanceParityTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        StorefrontSection.objects.create(
            page=self.page,
            section_key="hero_banner",
            order=0,
            settings={"hero_style": "overlay"},
        )

    def test_preview_and_public_share_resolver_and_component_context_for_equivalent_versions(self):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(
                header="header.dark_tech.v1",
                hero="hero.split.v1",
                footer="footer.premium_columns.v1",
            ),
        )

        preview = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(preview.status_code, 200)
        self.assertIn("store_appearance", preview.context)
        preview_state = preview.context["store_appearance"]
        preview_hero = preview.context["render_items"][0]

        published = layout_service.publish(self.store)
        public = build_universal_storefront_context(
            _FakeRequest(), self.store, StorefrontPage.PageType.HOME
        )
        self.assertIn("store_appearance", public)
        public_state = public["store_appearance"]
        public_hero = public["render_items"][0]

        self.assertEqual(published.pk, public_state.version_id)
        self.assertEqual(
            dict(preview_state.manifest.selections),
            dict(public_state.manifest.selections),
        )
        self.assertEqual(preview_hero["active_variant"].key, public_hero["active_variant"].key)
        self.assertEqual(preview_hero["template_name"], public_hero["template_name"])
        self.assertEqual(
            preview_hero["context"]["settings"]["hero_style"],
            public_hero["context"]["settings"]["hero_style"],
        )

    def test_public_safe_default_manifest_preserves_existing_legacy_header_selection(self):
        self.draft.header_config = layout_service.validate_header_config(
            {"show_cart": True, "header_variant": "dark_tech"}
        )
        self.draft.save(update_fields=["header_config"])
        layout_service.publish(self.store)

        public = build_universal_storefront_context(
            _FakeRequest(), self.store, StorefrontPage.PageType.HOME
        )
        dark_tech = global_region_registry.get_global_variant(
            global_region_registry.GLOBAL_HEADER_REGION, "dark_tech"
        ).renderer

        public_state = public.get("store_appearance")
        self.assertIsNotNone(
            public_state,
            "A7 public rendering must expose the resolved Store Appearance state",
        )
        self.assertEqual(
            public_state.component("header").component.key,
            "header.legacy_default.v1",
        )
        self.assertEqual(public["header_variant_template"], dark_tech)

    def test_preview_reads_draft_while_public_stays_on_published_manifest_until_publish(self):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(header="header.dark_tech.v1"),
        )
        layout_service.publish(self.store)
        next_draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        persist_store_appearance_manifest(
            next_draft,
            _manifest_with(header="header.boutique_centered.v1"),
        )

        preview = self.client.get(reverse("dashboard:storefront-builder-preview"))
        public = build_universal_storefront_context(
            _FakeRequest(), self.store, StorefrontPage.PageType.HOME
        )
        self.assertIn("store_appearance", preview.context)
        self.assertIn("store_appearance", public)

        self.assertEqual(
            preview.context["store_appearance"].component("header").component.key,
            "header.boutique_centered.v1",
        )
        self.assertEqual(
            public["store_appearance"].component("header").component.key,
            "header.dark_tech.v1",
        )
        self.assertNotEqual(
            preview.context["header_variant_template"],
            public["header_variant_template"],
        )

    def test_public_context_resolves_manifest_once_and_threads_same_state_into_items(self):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(hero="hero.split.v1"),
        )
        layout_service.publish(self.store)
        real_resolver = getattr(
            render_service, "resolve_store_appearance_render_state", None
        )
        self.assertIsNotNone(real_resolver)

        with patch.object(
            render_service,
            "resolve_store_appearance_render_state",
            wraps=real_resolver,
        ) as resolver:
            public = build_universal_storefront_context(
                _FakeRequest(), self.store, StorefrontPage.PageType.HOME
            )

        self.assertEqual(resolver.call_count, 1)
        self.assertIs(
            public["render_items"][0]["store_appearance"],
            public["store_appearance"],
        )
