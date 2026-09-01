from django.test import SimpleTestCase

from apps.storefront_builder.storefront_appearance.contracts import (
    InvalidStoreAppearanceContract,
)
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
    normalize_persisted_manifest,
    validate_store_appearance_manifest,
)


class StoreAppearanceManifestValidationTests(SimpleTestCase):
    def test_complete_default_manifest_is_normalized_deterministically(self):
        raw = manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        validated = validate_store_appearance_manifest(raw)
        self.assertTrue(validated.compatibility.is_valid)
        self.assertEqual(manifest_to_primitive(validated.manifest), raw)

    def test_old_missing_state_gets_exact_safe_defaults(self):
        for raw in (None, {}, {"schema_version": 1, "selections": {}}):
            with self.subTest(raw=raw):
                manifest = normalize_persisted_manifest(raw)
                self.assertEqual(
                    manifest_to_primitive(manifest),
                    manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST),
                )

    def test_partial_selection_is_valid_only_in_partial_mode(self):
        raw = {
            "schema_version": 1,
            "selections": {"header": "header.marketplace_search_first.v1"},
        }
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "missing families"):
            validate_store_appearance_manifest(raw)

        validated = validate_store_appearance_manifest(raw, require_complete=False)
        self.assertEqual(
            validated.manifest.selections["header"],
            "header.marketplace_search_first.v1",
        )

    def test_partial_manifest_can_merge_into_validated_base(self):
        validated = validate_store_appearance_manifest(
            {
                "schema_version": 1,
                "selections": {"header": "header.dark_tech.v1"},
            },
            require_complete=False,
            base_manifest=DEFAULT_STORE_APPEARANCE_MANIFEST,
        )
        self.assertEqual(validated.manifest.selections["header"], "header.dark_tech.v1")
        self.assertEqual(
            validated.manifest.selections["footer"],
            DEFAULT_STORE_APPEARANCE_MANIFEST.selections["footer"],
        )

    def test_unknown_top_level_field_family_or_component_is_rejected(self):
        cases = (
            {
                "schema_version": 1,
                "selections": dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
                "renderer": "storefront_builder/preview.html",
            },
            {"schema_version": 1, "selections": {"floating_cart": "floating_cart.off.v1"}},
            {"schema_version": 1, "selections": {"header": "header.unknown.v1"}},
            {"schema_version": 1, "selections": {"header": "footer.legacy_default.v1"}},
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    validate_store_appearance_manifest(raw, require_complete=False)

    def test_raw_html_css_js_template_and_expression_payloads_are_rejected(self):
        payloads = (
            "<script>alert(1)</script>",
            "<style>body{display:none}</style>",
            "javascript:alert(1)",
            "expression(alert(1))",
            "{% include 'secret.html' %}",
            "{{ unsafe }}",
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    validate_store_appearance_manifest(
                        {
                            "schema_version": 1,
                            "selections": {},
                            "settings": {"header": {"custom_html": payload}},
                        },
                        require_complete=False,
                    )

    def test_unregistered_setting_is_rejected_even_when_value_looks_safe(self):
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "unknown settings"):
            validate_store_appearance_manifest(
                {
                    "schema_version": 1,
                    "selections": {},
                    "settings": {"header": {"spacing": "compact"}},
                },
                require_complete=False,
            )

    def test_settings_must_be_bounded_json_like_data(self):
        invalid_values = (
            {"header": object()},
            {"header": {"value": float("nan")}},
            {"header": {"value": "x" * 501}},
            {"header": {"value": [[[[[[[[[["too-deep"]]]]]]]]]]}},
        )
        for settings in invalid_values:
            with self.subTest(settings=settings):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    validate_store_appearance_manifest(
                        {"schema_version": 1, "selections": {}, "settings": settings},
                        require_complete=False,
                    )

    def test_boolean_schema_version_and_non_mapping_shapes_are_rejected(self):
        cases = (
            [],
            {"schema_version": True, "selections": {}},
            {"schema_version": 1, "selections": []},
            {"schema_version": 1, "selections": {}, "settings": []},
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    validate_store_appearance_manifest(raw, require_complete=False)

    def test_primitive_output_contains_no_mapping_proxy_or_tuple(self):
        primitive = manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        self.assertIs(type(primitive), dict)
        self.assertIs(type(primitive["selections"]), dict)
        self.assertIs(type(primitive["settings"]), dict)
