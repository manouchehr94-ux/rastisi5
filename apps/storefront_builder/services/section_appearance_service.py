"""R4 Task 7 — pure resolution of a Section's *effective* appearance from
the page's global appearance config plus an optional sparse local override
(``section.settings.appearance_overrides``, Phase 1 slice: typography only).

No database access here — the caller (``render_service``) is responsible
for resolving the correct ``StorefrontLayoutVersion`` (Draft vs Published)
and passing in its ``effective_appearance_config()`` once per page render.
"""

from __future__ import annotations

from ..settings_schema import SettingsSchemaError, validate_appearance_overrides


def resolve_section_appearance(global_appearance: dict, section_settings: dict) -> dict:
    """Start from a copy of ``global_appearance``; override only ``font``/
    ``type_scale`` when the Section has an explicitly enabled local
    typography override. Every other global key is preserved unchanged.
    Never mutates either input. A malformed/stale persisted override never
    raises here — it is treated as "no override" so a corrupt row can
    never crash Draft Preview or the public storefront."""
    resolved = dict(global_appearance or {})
    typography_override = _resolve_enabled_typography_override(section_settings)
    if typography_override is None:
        return resolved
    if "font" in typography_override:
        resolved["font"] = typography_override["font"]
    if "type_scale" in typography_override:
        resolved["type_scale"] = typography_override["type_scale"]
    return resolved


def _resolve_enabled_typography_override(section_settings: dict) -> dict | None:
    overrides_raw = (section_settings or {}).get("appearance_overrides")
    if not overrides_raw:
        return None
    try:
        cleaned = validate_appearance_overrides(overrides_raw)
    except SettingsSchemaError:
        return None
    typography = cleaned.get("typography")
    if not typography or not typography.get("enabled"):
        return None
    return typography
