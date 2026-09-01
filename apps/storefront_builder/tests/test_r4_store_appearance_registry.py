from django.test import SimpleTestCase

from apps.storefront_builder import global_region_registry, section_registry
from apps.storefront_builder.services import container_service
from apps.storefront_builder.storefront_appearance.contracts import (
    ComponentDefinition,
    InvalidStoreAppearanceContract,
)
from apps.storefront_builder.storefront_appearance.families import COMPONENT_FAMILIES
from apps.storefront_builder.storefront_appearance.registry import (
    COMPONENT_REGISTRY,
    component_counts_by_family,
    get_component,
    list_components,
    require_component,
    resolve_component_implementation,
)


class StoreAppearanceRegistryAdapterTests(SimpleTestCase):
    def test_existing_registry_inventory_is_adapted_without_copying_renderers(self):
        self.assertEqual(
            component_counts_by_family(),
            {
                "header": 10,
                "mega_menu": 1,
                "hero": 6,
                "layout": 8,
                "product_view": 6,
                "card": 1,
                "badge": 1,
                "motion": 3,
                "footer": 8,
                "bottom_nav": 2,
            },
        )
        self.assertEqual(len(COMPONENT_REGISTRY), 46)
        self.assertTrue(all("/" not in item.registry_reference for item in list_components()))

    def test_every_family_safe_default_resolves(self):
        for family in COMPONENT_FAMILIES.values():
            with self.subTest(family=family.key):
                component = require_component(family.safe_default_component_key)
                self.assertEqual(component.family_key, family.key)
                self.assertIsNotNone(resolve_component_implementation(component))

    def test_global_regions_are_the_existing_objects(self):
        header = require_component("header.legacy_default.v1")
        footer = require_component("footer.marketplace_dense.v1")
        bottom_nav = require_component("bottom_nav.hidden.v1")

        header_variant = resolve_component_implementation(header)
        footer_variant = resolve_component_implementation(footer)
        mobile_variant = resolve_component_implementation(bottom_nav)

        self.assertIs(
            header_variant,
            global_region_registry.get_global_variant(
                global_region_registry.GLOBAL_HEADER_REGION, "legacy_default"
            ),
        )
        self.assertIs(
            footer_variant,
            global_region_registry.get_global_variant(
                global_region_registry.GLOBAL_FOOTER_REGION, "marketplace_dense"
            ),
        )
        self.assertIs(
            mobile_variant,
            global_region_registry.get_global_variant(
                global_region_registry.GLOBAL_MOBILE_NAV_REGION, "hidden"
            ),
        )

    def test_section_variants_are_the_existing_objects(self):
        hero = resolve_component_implementation(require_component("hero.split.v1"))
        product_view = resolve_component_implementation(
            require_component("product_view.catalog_group_columns.v1")
        )

        hero_definition = section_registry.get_definition("hero_banner")
        product_definition = section_registry.get_definition("catalog_product_wall")
        self.assertIn(hero, hero_definition.variants)
        self.assertIn(product_view, product_definition.variants)
        self.assertEqual(hero.key, "split")
        self.assertEqual(product_view.key, "group_columns")

    def test_layout_and_motion_adapters_point_at_existing_closed_choices(self):
        layout = resolve_component_implementation(require_component("layout.thirds.v1"))
        motion = resolve_component_implementation(require_component("motion.dynamic.v1"))
        self.assertEqual(layout, container_service.LAYOUT_PRESETS["thirds"])
        self.assertEqual(motion, "dynamic")

    def test_virtual_compatibility_defaults_are_explicit_noop_tokens(self):
        self.assertEqual(
            resolve_component_implementation(require_component("mega_menu.none.v1")),
            ("mega_menu", "none"),
        )
        self.assertEqual(
            resolve_component_implementation(require_component("card.legacy_default.v1")),
            ("card", "legacy_default"),
        )
        self.assertEqual(
            resolve_component_implementation(require_component("badge.none.v1")),
            ("badge", "none"),
        )

    def test_unknown_lookup_fails_closed(self):
        self.assertIsNone(get_component("header.missing.v1"))
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "unknown component key"):
            require_component("header.missing.v1")

    def test_family_listing_is_deterministic(self):
        headers = list_components("header")
        self.assertEqual(headers, list_components("header"))
        self.assertEqual(headers[0].key, "header.legacy_default.v1")
        self.assertEqual(len(headers), 10)

    def test_unregistered_symbolic_reference_is_rejected(self):
        component = ComponentDefinition(
            key="header.unregistered.v1",
            family_key="header",
            version=1,
            label_fa="ثبت‌نشده",
            registry_reference="global_region:header:unregistered",
        )
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "unresolvable registry reference"):
            resolve_component_implementation(component)
