"""Central read-only view of reusable components backed by existing registries."""

from __future__ import annotations

from types import MappingProxyType

from .adapters import (
    build_existing_component_definitions,
    resolve_component_implementation,
)
from .compatibility import (
    validate_compatibility_metadata,
    validate_deprecation_chains,
)
from .contracts import (
    ComponentDefinition,
    InvalidStoreAppearanceContract,
    validate_component_catalog,
)
from .families import COMPONENT_FAMILIES


_DEFINITIONS = build_existing_component_definitions()
validate_component_catalog(_DEFINITIONS, COMPONENT_FAMILIES)
for _definition in _DEFINITIONS:
    validate_compatibility_metadata(_definition, COMPONENT_FAMILIES)
    resolve_component_implementation(_definition)

COMPONENT_REGISTRY = MappingProxyType(
    {definition.key: definition for definition in _DEFINITIONS}
)
validate_deprecation_chains(COMPONENT_REGISTRY)


def get_component(key: str) -> ComponentDefinition | None:
    if not isinstance(key, str):
        return None
    return COMPONENT_REGISTRY.get(key)


def require_component(key: str) -> ComponentDefinition:
    component = get_component(key)
    if component is None:
        raise InvalidStoreAppearanceContract(f"unknown component key: {key}")
    return component


def list_components(family_key: str | None = None) -> tuple[ComponentDefinition, ...]:
    if family_key is None:
        return tuple(COMPONENT_REGISTRY.values())
    return tuple(
        component
        for component in COMPONENT_REGISTRY.values()
        if component.family_key == family_key
    )


def component_counts_by_family() -> dict[str, int]:
    return {
        family_key: len(list_components(family_key))
        for family_key in COMPONENT_FAMILIES
    }
