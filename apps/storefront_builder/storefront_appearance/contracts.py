"""Pure, database-free contracts for the R4 Store Appearance engine."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType


SUPPORTED_MANIFEST_SCHEMA_VERSION = 1

_FAMILY_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ADAPTER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_:-]*$")
_COMPONENT_KEY_RE = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_-]*)+\.v[1-9][0-9]*$"
)
_REGISTRY_REFERENCE_RE = re.compile(
    r"^[a-z][a-z0-9_]*(?::[a-z0-9][a-z0-9_.-]*)+$"
)
_RENDERER_ROLES = frozenset(
    {"global_region", "section_variant", "composition", "appearance_token"}
)
_COMPONENT_STATUSES = frozenset({"active", "deprecated"})
_OPTIONAL_DEFAULT_MARKERS = frozenset({"off", "none", "hidden"})


class InvalidStoreAppearanceContract(ValueError):
    """Platform-owned Store Appearance metadata violates its contract."""


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _require_nonempty_label(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidStoreAppearanceContract(f"{field_name} must be a non-empty string")


def _require_safe_component_key(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _COMPONENT_KEY_RE.fullmatch(value):
        raise InvalidStoreAppearanceContract(f"{field_name} is not a safe stable component key")
    return value


def _normalize_capabilities(value: Iterable[str] | None) -> frozenset[str]:
    normalized = frozenset(value or ())
    if any(not isinstance(item, str) or not _TOKEN_RE.fullmatch(item) for item in normalized):
        raise InvalidStoreAppearanceContract("capabilities contain an unsafe token")
    return normalized


@dataclasses.dataclass(frozen=True)
class ComponentFamilyDefinition:
    key: str
    label_fa: str
    storage_adapter_key: str
    safe_default_component_key: str
    renderer_role: str
    optional: bool = False
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _FAMILY_KEY_RE.fullmatch(self.key):
            raise InvalidStoreAppearanceContract("family key is unsafe")
        _require_nonempty_label(self.label_fa, "family label_fa")
        if not isinstance(self.storage_adapter_key, str) or not _ADAPTER_KEY_RE.fullmatch(
            self.storage_adapter_key
        ):
            raise InvalidStoreAppearanceContract("storage_adapter_key is unsafe")
        default_key = _require_safe_component_key(
            self.safe_default_component_key, "safe_default_component_key"
        )
        if not default_key.startswith(f"{self.key}."):
            raise InvalidStoreAppearanceContract(
                "safe_default_component_key must belong to its family"
            )
        if self.renderer_role not in _RENDERER_ROLES:
            raise InvalidStoreAppearanceContract("renderer_role is unknown")
        if not isinstance(self.optional, bool):
            raise InvalidStoreAppearanceContract("optional must be a boolean")
        if self.optional:
            identity_segments = default_key.split(".")[1:-1]
            if not _OPTIONAL_DEFAULT_MARKERS.intersection(identity_segments):
                raise InvalidStoreAppearanceContract(
                    "optional family requires an explicit off/none/hidden safe default"
                )
        object.__setattr__(self, "capabilities", _normalize_capabilities(self.capabilities))


@dataclasses.dataclass(frozen=True)
class ComponentDefinition:
    key: str
    family_key: str
    version: int
    label_fa: str
    registry_reference: str
    capabilities: frozenset[str] = frozenset()
    compatibility: Mapping = dataclasses.field(default_factory=dict)
    status: str = "active"
    deprecated_by: str | None = None

    def __post_init__(self) -> None:
        key = _require_safe_component_key(self.key, "component key")
        if not isinstance(self.family_key, str) or not _FAMILY_KEY_RE.fullmatch(self.family_key):
            raise InvalidStoreAppearanceContract("family_key is unsafe")
        if not key.startswith(f"{self.family_key}."):
            raise InvalidStoreAppearanceContract("component key must match family_key")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvalidStoreAppearanceContract("version must be a positive strict integer")
        if not key.endswith(f".v{self.version}"):
            raise InvalidStoreAppearanceContract("component key version does not match version")
        _require_nonempty_label(self.label_fa, "component label_fa")
        if not isinstance(self.registry_reference, str) or not _REGISTRY_REFERENCE_RE.fullmatch(
            self.registry_reference
        ):
            raise InvalidStoreAppearanceContract(
                "registry_reference must be an allowlisted symbolic reference, not a renderer path"
            )
        if self.status not in _COMPONENT_STATUSES:
            raise InvalidStoreAppearanceContract("component status is unknown")
        if self.deprecated_by is not None:
            replacement = _require_safe_component_key(self.deprecated_by, "deprecated_by")
            if replacement == key:
                raise InvalidStoreAppearanceContract("deprecated_by cannot reference itself")
            if not replacement.startswith(f"{self.family_key}."):
                raise InvalidStoreAppearanceContract("deprecated_by must stay in the same family")
        if self.status == "deprecated" and self.deprecated_by is None:
            raise InvalidStoreAppearanceContract(
                "deprecated component requires a versioned deprecated_by identity"
            )
        if self.status == "active" and self.deprecated_by is not None:
            raise InvalidStoreAppearanceContract("active component cannot declare deprecated_by")
        if not isinstance(self.compatibility, Mapping):
            raise InvalidStoreAppearanceContract("compatibility must be a mapping")
        object.__setattr__(self, "capabilities", _normalize_capabilities(self.capabilities))
        object.__setattr__(self, "compatibility", _freeze(self.compatibility))


@dataclasses.dataclass(frozen=True)
class StoreAppearanceManifest:
    schema_version: int
    selections: Mapping[str, str]
    settings: Mapping = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SUPPORTED_MANIFEST_SCHEMA_VERSION
        ):
            raise InvalidStoreAppearanceContract(
                f"schema_version must be {SUPPORTED_MANIFEST_SCHEMA_VERSION}"
            )
        if not isinstance(self.selections, Mapping):
            raise InvalidStoreAppearanceContract("selections must be a mapping")
        normalized_selections: dict[str, str] = {}
        for family_key, component_key in self.selections.items():
            if not isinstance(family_key, str) or not _FAMILY_KEY_RE.fullmatch(family_key):
                raise InvalidStoreAppearanceContract("manifest contains an unsafe family key")
            normalized_selections[family_key] = _require_safe_component_key(
                component_key, f"selection for {family_key}"
            )
        if not isinstance(self.settings, Mapping):
            raise InvalidStoreAppearanceContract("settings must be a mapping")
        object.__setattr__(self, "selections", MappingProxyType(normalized_selections))
        object.__setattr__(self, "settings", _freeze(self.settings))


def validate_family_catalog(definitions: Iterable[ComponentFamilyDefinition]) -> None:
    seen: set[str] = set()
    adapter_keys: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, ComponentFamilyDefinition):
            raise InvalidStoreAppearanceContract("family catalog contains an invalid definition")
        if definition.key in seen:
            raise InvalidStoreAppearanceContract(f"duplicate family key: {definition.key}")
        if definition.storage_adapter_key in adapter_keys:
            raise InvalidStoreAppearanceContract(
                f"duplicate storage adapter key: {definition.storage_adapter_key}"
            )
        seen.add(definition.key)
        adapter_keys.add(definition.storage_adapter_key)


def validate_component_catalog(
    definitions: Iterable[ComponentDefinition],
    families: Mapping[str, ComponentFamilyDefinition],
) -> None:
    seen: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, ComponentDefinition):
            raise InvalidStoreAppearanceContract("component catalog contains an invalid definition")
        if definition.key in seen:
            raise InvalidStoreAppearanceContract(f"duplicate component key: {definition.key}")
        if definition.family_key not in families:
            raise InvalidStoreAppearanceContract(
                f"unknown component family: {definition.family_key}"
            )
        seen.add(definition.key)


def validate_manifest_families(
    manifest: StoreAppearanceManifest,
    families: Mapping[str, ComponentFamilyDefinition],
    *,
    require_complete: bool = True,
) -> None:
    known = set(families)
    present = set(manifest.selections)
    unknown = present - known
    if unknown:
        raise InvalidStoreAppearanceContract(f"manifest contains unknown families: {sorted(unknown)}")
    missing = known - present
    if require_complete and missing:
        raise InvalidStoreAppearanceContract(f"manifest is missing families: {sorted(missing)}")
    for family_key, component_key in manifest.selections.items():
        if not component_key.startswith(f"{family_key}."):
            raise InvalidStoreAppearanceContract(
                f"selection {component_key} does not belong to family {family_key}"
            )
