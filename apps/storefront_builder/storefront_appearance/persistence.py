"""Persistence adapter for typed Store Appearance state on an R4 version.

The existing ``StorefrontLayoutVersion`` remains the only Draft/Published
boundary.  Stable component identities live under one reserved
``appearance_config`` key while selectors already consumed by the R4 renderer
are mirrored into their established JSON locations.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import StoreAppearanceManifest
from .families import DEFAULT_STORE_APPEARANCE_MANIFEST
from .registry import COMPONENT_REGISTRY
from .validation import (
    manifest_to_primitive,
    normalize_persisted_manifest,
    validate_store_appearance_manifest,
)


STORE_APPEARANCE_CONFIG_KEY = "store_appearance"


class ImmutableStoreAppearanceError(ValueError):
    """Store Appearance may only be changed on the active Draft version."""


_COMPONENT_BY_REFERENCE = {
    component.registry_reference: component.key
    for component in COMPONENT_REGISTRY.values()
}


def component_key_for_registry_reference(
    reference: str, *, family_key: str | None = None
) -> str | None:
    """Resolve a platform-owned registry reference to its stable component key.

    Legacy R4 selector mutations use this inverse adapter to keep the typed
    Store Appearance manifest synchronized without duplicating registry
    knowledge in the mutation service.
    """
    component_key = _COMPONENT_BY_REFERENCE.get(reference)
    if component_key is None:
        return None
    if family_key is not None and COMPONENT_REGISTRY[component_key].family_key != family_key:
        return None
    return component_key


def _component_for_reference(reference: str, fallback: str) -> str:
    return component_key_for_registry_reference(reference) or fallback


def _legacy_manifest(version) -> StoreAppearanceManifest:
    """Derive the logical manifest of a pre-engine Draft without mutating it."""

    selections = dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections)
    header = version.effective_header_config()
    footer = version.effective_footer_config()
    appearance = version.effective_appearance_config()

    selections["header"] = _component_for_reference(
        f"global_region:header:{header['header_variant']}",
        selections["header"],
    )
    selections["footer"] = _component_for_reference(
        f"global_region:footer:{footer['footer_variant']}",
        selections["footer"],
    )
    selections["bottom_nav"] = _component_for_reference(
        f"global_region:mobile_bottom_nav:{footer['mobile_nav_variant']}",
        selections["bottom_nav"],
    )
    selections["motion"] = _component_for_reference(
        f"appearance_motion:{appearance['motion']}",
        selections["motion"],
    )
    return StoreAppearanceManifest(schema_version=1, selections=selections)


def load_store_appearance_manifest(version) -> StoreAppearanceManifest:
    """Return one normalized manifest for new and legacy layout versions."""

    appearance = version.appearance_config or {}
    if not isinstance(appearance, Mapping):
        appearance = {}
    raw = appearance.get(STORE_APPEARANCE_CONFIG_KEY)
    if raw is None or raw == {}:
        return _legacy_manifest(version)
    return normalize_persisted_manifest(raw)


def _selector(manifest: StoreAppearanceManifest, family: str, prefix: str) -> str:
    component = COMPONENT_REGISTRY[manifest.selections[family]]
    reference = component.registry_reference
    if not reference.startswith(prefix):
        # Registry validation makes this unreachable for platform definitions,
        # but refusing an inconsistent adapter is safer than persisting drift.
        raise ValueError(f"component {component.key} cannot populate {family}")
    return reference.removeprefix(prefix)


def persist_store_appearance_manifest(version, raw) -> StoreAppearanceManifest:
    """Validate and persist a complete manifest on one mutable Draft.

    No caller supplies a tenant id: ownership is derived from
    ``version.layout.store``.  Transactional locking and optimistic revision
    checks belong to the mutation service that invokes this adapter.
    """

    if version.status != version.Status.DRAFT:
        raise ImmutableStoreAppearanceError(
            "Store Appearance can only be changed on a Draft version"
        )

    if isinstance(raw, StoreAppearanceManifest):
        raw = manifest_to_primitive(raw)
    validated = validate_store_appearance_manifest(raw)
    manifest = validated.manifest
    primitive = manifest_to_primitive(manifest)

    header_config = dict(version.header_config or {})
    footer_config = dict(version.footer_config or {})
    appearance_config = dict(version.appearance_config or {})

    header_config["header_variant"] = _selector(
        manifest, "header", "global_region:header:"
    )
    footer_config["footer_variant"] = _selector(
        manifest, "footer", "global_region:footer:"
    )
    footer_config["mobile_nav_variant"] = _selector(
        manifest, "bottom_nav", "global_region:mobile_bottom_nav:"
    )
    appearance_config["motion"] = _selector(
        manifest, "motion", "appearance_motion:"
    )
    appearance_config[STORE_APPEARANCE_CONFIG_KEY] = primitive

    version.header_config = header_config
    version.footer_config = footer_config
    version.appearance_config = appearance_config
    version.save(
        update_fields=[
            "header_config",
            "footer_config",
            "appearance_config",
            "updated_at",
        ]
    )
    return manifest
