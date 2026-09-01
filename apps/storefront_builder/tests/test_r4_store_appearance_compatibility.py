from django.test import SimpleTestCase

from apps.storefront_builder.storefront_appearance.compatibility import (
    evaluate_manifest_compatibility,
    validate_compatibility_metadata,
    validate_deprecation_chains,
)
from apps.storefront_builder.storefront_appearance.contracts import (
    ComponentDefinition,
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
)
from apps.storefront_builder.storefront_appearance.families import (
    COMPONENT_FAMILIES,
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.registry import COMPONENT_REGISTRY


def _component(
    key,
    family,
    *,
    capabilities=(),
    compatibility=None,
    status="active",
    deprecated_by=None,
):
    version = int(key.rsplit(".v", 1)[1])
    return ComponentDefinition(
        key=key,
        family_key=family,
        version=version,
        label_fa=key,
        registry_reference=f"virtual:{family}:{key.split('.')[1]}",
        capabilities=capabilities,
        compatibility=compatibility or {},
        status=status,
        deprecated_by=deprecated_by,
    )


class StoreAppearanceCompatibilityTests(SimpleTestCase):
    def test_current_default_manifest_is_valid(self):
        result = evaluate_manifest_compatibility(
            DEFAULT_STORE_APPEARANCE_MANIFEST,
            COMPONENT_REGISTRY,
            COMPONENT_FAMILIES,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.hard_errors, ())
        self.assertEqual(result.score, 100)

    def test_functional_capability_mismatch_is_hard_error(self):
        header = _component("header.simple.v1", "header")
        mega_menu = _component(
            "mega_menu.visual.v1",
            "mega_menu",
            compatibility={"requires_capabilities": {"header": ["mega_menu"]}},
        )
        components = {header.key: header, mega_menu.key: mega_menu}
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections={"header": header.key, "mega_menu": mega_menu.key},
        )

        result = evaluate_manifest_compatibility(
            manifest, components, COMPONENT_FAMILIES
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.hard_errors), 1)
        self.assertIn("mega_menu", result.hard_errors[0])

    def test_satisfied_capability_requirement_is_valid(self):
        header = _component(
            "header.capable.v1", "header", capabilities={"mega_menu"}
        )
        mega_menu = _component(
            "mega_menu.visual.v1",
            "mega_menu",
            compatibility={"requires_capabilities": {"header": ["mega_menu"]}},
        )
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections={"header": header.key, "mega_menu": mega_menu.key},
        )
        result = evaluate_manifest_compatibility(
            manifest,
            {header.key: header, mega_menu.key: mega_menu},
            COMPONENT_FAMILIES,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.hard_errors, ())

    def test_recommendations_warn_but_do_not_block_valid_choice(self):
        header = _component("header.simple.v1", "header")
        hero = _component(
            "hero.editorial.v1",
            "hero",
            compatibility={
                "recommended_with": {"header": ["header.editorial.v1"]}
            },
        )
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections={"header": header.key, "hero": hero.key},
        )
        result = evaluate_manifest_compatibility(
            manifest, {header.key: header, hero.key: hero}, COMPONENT_FAMILIES
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.hard_errors, ())
        self.assertEqual(len(result.warnings), 1)
        self.assertLess(result.score, 100)

    def test_discouraged_combination_is_warning_only(self):
        header = _component("header.dense.v1", "header")
        layout = _component(
            "layout.spacious.v1",
            "layout",
            compatibility={
                "discouraged_with": {"header": ["header.dense.v1"]}
            },
        )
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections={"header": header.key, "layout": layout.key},
        )
        result = evaluate_manifest_compatibility(
            manifest, {header.key: header, layout.key: layout}, COMPONENT_FAMILIES
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.warnings), 1)

    def test_deprecated_component_stays_resolvable_with_warning(self):
        old = _component(
            "card.portrait.v1",
            "card",
            status="deprecated",
            deprecated_by="card.portrait.v2",
        )
        new = _component("card.portrait.v2", "card")
        manifest = StoreAppearanceManifest(
            schema_version=1, selections={"card": old.key}
        )
        result = evaluate_manifest_compatibility(
            manifest, {old.key: old, new.key: new}, COMPONENT_FAMILIES
        )
        self.assertTrue(result.is_valid)
        self.assertIn("deprecated", result.warnings[0])
        validate_deprecation_chains({old.key: old, new.key: new})

    def test_deprecation_chain_requires_registered_newer_same_family_target(self):
        old = _component(
            "card.portrait.v2",
            "card",
            status="deprecated",
            deprecated_by="card.portrait.v1",
        )
        earlier = _component("card.portrait.v1", "card")
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "newer version"):
            validate_deprecation_chains({old.key: old, earlier.key: earlier})

        replacement_missing = _component(
            "card.square.v1",
            "card",
            status="deprecated",
            deprecated_by="card.square.v2",
        )
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "not registered"):
            validate_deprecation_chains({replacement_missing.key: replacement_missing})

    def test_compatibility_metadata_rejects_unknown_family_or_cross_family_key(self):
        unknown_family = _component(
            "hero.sample.v1",
            "hero",
            compatibility={"recommended_with": {"floating_cart": ["floating_cart.a.v1"]}},
        )
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "unknown target family"):
            validate_compatibility_metadata(unknown_family, COMPONENT_FAMILIES)

        wrong_key = _component(
            "hero.sample.v1",
            "hero",
            compatibility={"recommended_with": {"header": ["footer.a.v1"]}},
        )
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "does not belong"):
            validate_compatibility_metadata(wrong_key, COMPONENT_FAMILIES)

    def test_unknown_component_is_reported_as_hard_error(self):
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections={"header": "header.unknown.v1"},
        )
        result = evaluate_manifest_compatibility(
            manifest, {}, COMPONENT_FAMILIES
        )
        self.assertFalse(result.is_valid)
        self.assertIn("unknown component", result.hard_errors[0])
