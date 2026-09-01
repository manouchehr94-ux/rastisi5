"""Adapters from Store Appearance identities to existing R4 registries.

Persisted component keys are never renderer paths.  These adapters resolve a
platform-owned symbolic reference to the already-registered implementation.
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import appearance_registry, global_region_registry, section_registry
from ..services import container_service
from ..variant_contract import get_variant
from .contracts import ComponentDefinition, InvalidStoreAppearanceContract


_GLOBAL_REGIONS = {
    "header": global_region_registry.GLOBAL_HEADER_REGION,
    "footer": global_region_registry.GLOBAL_FOOTER_REGION,
    "mobile_bottom_nav": global_region_registry.GLOBAL_MOBILE_NAV_REGION,
}

_VIRTUAL_COMPONENTS = frozenset(
    {
        ("mega_menu", "none"),
        ("card", "legacy_default"),
        ("badge", "none"),
    }
)


def _component(
    *,
    key: str,
    family_key: str,
    label_fa: str,
    registry_reference: str,
    capabilities: Iterable[str] = ("responsive", "rtl"),
) -> ComponentDefinition:
    return ComponentDefinition(
        key=key,
        family_key=family_key,
        version=1,
        label_fa=label_fa,
        registry_reference=registry_reference,
        capabilities=capabilities,
    )


def _global_region_components(
    family_key: str,
    region: global_region_registry.GlobalRegionDefinition,
    *,
    default_identity: str,
) -> list[ComponentDefinition]:
    definitions = []
    for variant in global_region_registry.list_global_variants(region):
        identity = default_identity if variant.key == region.default_variant else variant.key
        definitions.append(
            _component(
                key=f"{family_key}.{identity}.v1",
                family_key=family_key,
                label_fa=variant.label_fa,
                registry_reference=f"global_region:{region.key}:{variant.key}",
                capabilities=("mobile", "rtl", "safe_area")
                if family_key == "bottom_nav"
                else ("responsive", "rtl"),
            )
        )
    return definitions


def _section_variant_components(
    family_key: str,
    section_key: str,
    *,
    default_identity: str,
    identity_prefix: str = "",
) -> list[ComponentDefinition]:
    section = section_registry.get_definition(section_key)
    definitions = []
    for variant in section.variants:
        identity = default_identity if variant.key == section.default_variant else f"{identity_prefix}{variant.key}"
        definitions.append(
            _component(
                key=f"{family_key}.{identity}.v1",
                family_key=family_key,
                label_fa=variant.label_fa,
                registry_reference=f"section_variant:{section_key}:{variant.key}",
                capabilities=variant.capabilities | frozenset({"responsive", "rtl"}),
            )
        )
    return definitions


def build_existing_component_definitions() -> tuple[ComponentDefinition, ...]:
    """Return deterministic adapters for the implementations present at R4 Phase 1."""

    definitions: list[ComponentDefinition] = []

    definitions.extend(
        _global_region_components(
            "header",
            global_region_registry.GLOBAL_HEADER_REGION,
            default_identity="legacy_default",
        )
    )
    definitions.append(
        _component(
            key="mega_menu.none.v1",
            family_key="mega_menu",
            label_fa="بدون مگامنو",
            registry_reference="virtual:mega_menu:none",
        )
    )
    definitions.extend(
        _section_variant_components(
            "hero", "hero_banner", default_identity="legacy_default"
        )
    )

    for layout_key in container_service.LAYOUT_PRESETS:
        identity = "legacy_default" if layout_key == "single" else layout_key
        definitions.append(
            _component(
                key=f"layout.{identity}.v1",
                family_key="layout",
                label_fa=f"چیدمان {layout_key}",
                registry_reference=f"composition:{layout_key}",
            )
        )

    definitions.extend(
        _section_variant_components(
            "product_view", "product_section", default_identity="legacy_default"
        )
    )
    definitions.extend(
        _section_variant_components(
            "product_view",
            "catalog_product_wall",
            default_identity="catalog_rows",
            identity_prefix="catalog_",
        )
    )

    definitions.append(
        _component(
            key="card.legacy_default.v1",
            family_key="card",
            label_fa="کارت فعلی / پیش‌فرض",
            registry_reference="virtual:card:legacy_default",
        )
    )
    definitions.append(
        _component(
            key="badge.none.v1",
            family_key="badge",
            label_fa="بدون نشان تزئینی",
            registry_reference="virtual:badge:none",
        )
    )

    for motion_key in appearance_registry.MOTION_CHOICES:
        definitions.append(
            _component(
                key=f"motion.{motion_key}.v1",
                family_key="motion",
                label_fa=f"حرکت {motion_key}",
                registry_reference=f"appearance_motion:{motion_key}",
                capabilities=("reduced_motion",),
            )
        )

    definitions.extend(
        _global_region_components(
            "footer",
            global_region_registry.GLOBAL_FOOTER_REGION,
            default_identity="legacy_default",
        )
    )
    definitions.extend(
        _global_region_components(
            "bottom_nav",
            global_region_registry.GLOBAL_MOBILE_NAV_REGION,
            default_identity="hidden",
        )
    )
    return tuple(definitions)


def resolve_registry_reference(reference: str):
    """Resolve one trusted symbolic reference to its existing implementation."""

    parts = reference.split(":")
    resolved = None
    if len(parts) == 3 and parts[0] == "global_region":
        region = _GLOBAL_REGIONS.get(parts[1])
        if region is not None:
            resolved = global_region_registry.get_global_variant(region, parts[2])
    elif len(parts) == 3 and parts[0] == "section_variant":
        try:
            section = section_registry.get_definition(parts[1])
        except section_registry.UnknownSectionTypeError:
            section = None
        if section is not None:
            resolved = get_variant(section, parts[2])
    elif len(parts) == 2 and parts[0] == "composition":
        resolved = container_service.LAYOUT_PRESETS.get(parts[1])
    elif len(parts) == 2 and parts[0] == "appearance_motion":
        if parts[1] in appearance_registry.MOTION_CHOICES:
            resolved = parts[1]
    elif len(parts) == 3 and parts[0] == "virtual":
        token = (parts[1], parts[2])
        if token in _VIRTUAL_COMPONENTS:
            resolved = token

    if resolved is None:
        raise InvalidStoreAppearanceContract(
            f"unresolvable registry reference: {reference}"
        )
    return resolved


def resolve_component_implementation(component: ComponentDefinition):
    if not isinstance(component, ComponentDefinition):
        raise InvalidStoreAppearanceContract("component definition is required")
    return resolve_registry_reference(component.registry_reference)

