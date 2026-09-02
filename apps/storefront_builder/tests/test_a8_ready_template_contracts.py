"""A8 contract tests for immutable, versioned Ready Template DNA."""

from copy import deepcopy

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)


class ReadyTemplateContractTests(SimpleTestCase):
    """Exercise registry behavior without a database or renderer dependency."""

    def setUp(self):
        super().setUp()
        self._latest_before = dict(lpr.LAYOUT_PRESET_REGISTRY)
        self._versions_before = dict(lpr.LAYOUT_PRESET_VERSION_REGISTRY)

    def tearDown(self):
        lpr.LAYOUT_PRESET_REGISTRY.clear()
        lpr.LAYOUT_PRESET_REGISTRY.update(self._latest_before)
        lpr.LAYOUT_PRESET_VERSION_REGISTRY.clear()
        lpr.LAYOUT_PRESET_VERSION_REGISTRY.update(self._versions_before)
        super().tearDown()

    def _manifest(self):
        return {
            "schema_version": 1,
            "selections": dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
            "settings": {},
        }

    def _ready(self, *, key="__a8_contract__", version="1", manifest=None):
        if manifest is None:
            manifest = self._manifest()
        return lpr.LayoutPresetDefinition(
            key=key,
            label_fa="قرارداد",
            description_fa="قرارداد آماده",
            version=version,
            is_ready_template=True,
            store_appearance=manifest,
        )

    def test_exact_versions_are_immutable_and_latest_is_numeric_not_import_order(self):
        """Registering an older version later must not replace the numeric latest."""
        newest = self._ready(version="10")
        older = self._ready(version="2")

        lpr.register_layout_preset(newest)
        lpr.register_layout_preset(older)

        self.assertIs(lpr.get_layout_preset_version(newest.key, "2"), older)
        self.assertIs(lpr.get_layout_preset_version(newest.key, "10"), newest)
        self.assertIs(lpr.get_layout_preset(newest.key), newest)
        self.assertEqual(
            [preset.version for preset in lpr.list_ready_templates() if preset.key == newest.key],
            ["10"],
        )

    def test_duplicate_exact_version_is_rejected_without_mutating_registries(self):
        original = self._ready(version="1")
        duplicate = self._ready(version="1")
        lpr.register_layout_preset(original)
        latest_before = dict(lpr.LAYOUT_PRESET_REGISTRY)
        versions_before = dict(lpr.LAYOUT_PRESET_VERSION_REGISTRY)

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(duplicate)

        self.assertEqual(lpr.LAYOUT_PRESET_REGISTRY, latest_before)
        self.assertEqual(lpr.LAYOUT_PRESET_VERSION_REGISTRY, versions_before)

    def test_empty_and_non_numeric_versions_are_rejected(self):
        for version in ("", " ", "v2", "2.0", "01", "0"):
            with self.subTest(version=version):
                with self.assertRaises(lpr.InvalidLayoutPresetError):
                    lpr.register_layout_preset(self._ready(key=f"__a8_version_{version!r}__", version=version))

    def test_new_ready_template_requires_a_manifest(self):
        preset = self._ready(manifest=None)
        preset = lpr.LayoutPresetDefinition(
            key=preset.key,
            label_fa=preset.label_fa,
            description_fa=preset.description_fa,
            version=preset.version,
            is_ready_template=True,
        )

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(preset)

    def test_existing_ready_catalog_is_explicitly_transitional_until_task_four(self):
        """The eight historical recipes predate DNA and remain import-compatible only."""
        self.assertTrue(lpr.get_layout_preset("dense_marketplace").is_ready_template)
        self.assertIsNone(lpr.get_layout_preset("dense_marketplace").store_appearance)

    def test_ready_template_rejects_missing_schema_version(self):
        manifest = self._manifest()
        manifest.pop("schema_version")

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

    def test_ready_template_rejects_incomplete_family_selections(self):
        manifest = self._manifest()
        manifest["selections"].pop("bottom_nav")

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

    def test_ready_template_rejects_unknown_component_keys(self):
        manifest = self._manifest()
        manifest["selections"]["header"] = "header.unknown.v1"

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

    def test_ready_template_rejects_renderer_and_template_payloads(self):
        for payload in (
            {"renderer_path": "apps.evil.renderer"},
            {"template_path": "evil/template.html"},
            {"settings": {"hero": {"javascript": "alert(1)"}}},
        ):
            with self.subTest(payload=payload):
                manifest = deepcopy(self._manifest())
                manifest.update(payload)
                with self.assertRaises(lpr.InvalidLayoutPresetError):
                    lpr.register_layout_preset(self._ready(manifest=manifest))
