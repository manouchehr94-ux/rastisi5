"""Compatibility guidance and hard functional constraints for components."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping

from .contracts import (
    ComponentDefinition,
    ComponentFamilyDefinition,
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
)


_METADATA_KEYS = frozenset(
    {"requires_capabilities", "recommended_with", "discouraged_with"}
)
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_:-]*$")


@dataclasses.dataclass(frozen=True)
class CompatibilityEvaluation:
    hard_errors: tuple[str, ...]
    warnings: tuple[str, ...]
    score: int

    @property
    def is_valid(self) -> bool:
        return not self.hard_errors


def _metadata_mapping(component: ComponentDefinition, key: str) -> Mapping:
    value = component.compatibility.get(key, {})
    if not isinstance(value, Mapping):
        raise InvalidStoreAppearanceContract(
            f"{component.key} compatibility.{key} must be a mapping"
        )
    return value


def validate_compatibility_metadata(
    component: ComponentDefinition,
    families: Mapping[str, ComponentFamilyDefinition],
) -> None:
    unknown_metadata = set(component.compatibility) - _METADATA_KEYS
    if unknown_metadata:
        raise InvalidStoreAppearanceContract(
            f"{component.key} has unknown compatibility metadata: {sorted(unknown_metadata)}"
        )

    for metadata_key in _METADATA_KEYS:
        for target_family, values in _metadata_mapping(component, metadata_key).items():
            if target_family not in families:
                raise InvalidStoreAppearanceContract(
                    f"{component.key} references unknown target family: {target_family}"
                )
            if not isinstance(values, (tuple, list, set, frozenset)):
                raise InvalidStoreAppearanceContract(
                    f"{component.key} compatibility.{metadata_key}.{target_family} must be a collection"
                )
            if metadata_key == "requires_capabilities":
                for capability in values:
                    if not isinstance(capability, str) or not _CAPABILITY_RE.fullmatch(capability):
                        raise InvalidStoreAppearanceContract(
                            f"{component.key} has an unsafe required capability"
                        )
            else:
                for target_key in values:
                    if not isinstance(target_key, str) or not target_key.startswith(
                        f"{target_family}."
                    ):
                        raise InvalidStoreAppearanceContract(
                            f"{target_key} does not belong to target family {target_family}"
                        )


def validate_deprecation_chains(
    components: Mapping[str, ComponentDefinition],
) -> None:
    for component in components.values():
        if component.status != "deprecated":
            continue
        replacement = components.get(component.deprecated_by)
        if replacement is None:
            raise InvalidStoreAppearanceContract(
                f"deprecated_by target is not registered: {component.deprecated_by}"
            )
        if replacement.family_key != component.family_key:
            raise InvalidStoreAppearanceContract(
                f"deprecated_by target changes family for {component.key}"
            )
        if replacement.version <= component.version:
            raise InvalidStoreAppearanceContract(
                f"deprecated_by target must be a newer version for {component.key}"
            )


def evaluate_manifest_compatibility(
    manifest: StoreAppearanceManifest,
    components: Mapping[str, ComponentDefinition],
    families: Mapping[str, ComponentFamilyDefinition],
) -> CompatibilityEvaluation:
    """Evaluate a candidate without turning curation advice into access control."""

    hard_errors: list[str] = []
    warnings: list[str] = []
    score = 100
    selected: dict[str, ComponentDefinition] = {}

    for family_key, component_key in manifest.selections.items():
        if family_key not in families:
            hard_errors.append(f"unknown family: {family_key}")
            continue
        component = components.get(component_key)
        if component is None:
            hard_errors.append(f"unknown component: {component_key}")
            continue
        if component.family_key != family_key:
            hard_errors.append(
                f"component {component_key} does not belong to family {family_key}"
            )
            continue
        selected[family_key] = component

    for component in selected.values():
        validate_compatibility_metadata(component, families)
        if component.status == "deprecated":
            warnings.append(
                f"deprecated component {component.key}; replacement {component.deprecated_by}"
            )
            score -= 15

        for target_family, requirements in _metadata_mapping(
            component, "requires_capabilities"
        ).items():
            target = selected.get(target_family)
            if target is None:
                hard_errors.append(
                    f"{component.family_key} requires selected family {target_family}"
                )
                continue
            missing = set(requirements) - set(target.capabilities)
            if missing:
                hard_errors.append(
                    f"{component.family_key} requires {target_family} capabilities {sorted(missing)}"
                )

        for target_family, recommended_keys in _metadata_mapping(
            component, "recommended_with"
        ).items():
            target = selected.get(target_family)
            if target is not None and target.key not in set(recommended_keys):
                warnings.append(
                    f"{component.key} is not recommended with {target.key}"
                )
                score -= 10

        for target_family, discouraged_keys in _metadata_mapping(
            component, "discouraged_with"
        ).items():
            target = selected.get(target_family)
            if target is not None and target.key in set(discouraged_keys):
                warnings.append(f"{component.key} is discouraged with {target.key}")
                score -= 5

    return CompatibilityEvaluation(
        hard_errors=tuple(hard_errors),
        warnings=tuple(warnings),
        score=max(0, score),
    )
