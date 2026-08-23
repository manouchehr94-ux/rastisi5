"""Global Region/Variant Registry — U2A: Visual Global Header System.

``SECTION_REGISTRY`` (``section_registry.py``) resolves *page-section*
types (hero_banner, product_section, ...). It is deliberately NOT reused
for global chrome regions like Header/Navigation/Mobile shell — those are
not sections a merchant adds/removes/reorders on a page; they are exactly
one fixed region shared by all six page types, so forcing them into
``SectionDefinition`` (page_types/min_instances/duplicable/category_fa/
library visibility/... all meaningless here) would be a worse fit than a
small, dedicated registry.

This module reuses the exact U1 principle instead — the same one
``variant_contract.VariantDefinition`` already proved for section variants:

    persisted variant key (string, merchant-controlled)
            v
    trusted Python registry (this module)
            v
    trusted registered renderer path (Python code only, never merchant JSON)
            v
    shared storefront shell (``{% include header_variant_template %}``)

It is intentionally much smaller than ``SectionDefinition``/
``VariantDefinition``: a global variant has no ``validate_settings``/
``default_settings``/``capabilities``/``supported_settings``/
``required_data`` of its own (the *shape* of ``header_config`` is one
single schema, validated once by
``services.layout_service.validate_header_config`` — a variant only ever
selects which trusted renderer partial receives that same
``header_config`` dict), and there is no Pattern-A "same template as the
region" fallback (a region has no template_name of its own — the region
IS "a set of registered variants", and every variant, including the
backward-compatible default, always declares its own ``renderer``).

Read vs. write, exactly mirroring ``variant_contract``'s split:

- ``resolve_active_global_variant``/``resolve_header_variant_template``
  are the *read* (render-time) path — pure, zero-DB-query, never raise;
  an unknown/legacy/missing stored key fails safely to the region's
  ``default_variant``, never crashes the storefront, never falls back to
  an arbitrary/merchant-controlled path.
- ``validate_global_variant_selection`` is the *write* (editor POST) path
  — rejects a present-and-unknown key outright, exactly like
  ``variant_contract.validate_variant_selection``/
  ``UnknownVariantSelectionError`` does for section variants.

No branching on template-key identity, Store slug identity, or family-slug
identity exists or may be added anywhere that consumes this module — the
renderer is always the one fixed Python string already written on the
matching ``GlobalVariantDefinition``.
"""

from __future__ import annotations

import dataclasses
import re


class InvalidGlobalVariantDefinitionError(ValueError):
    """A ``GlobalVariantDefinition``/``GlobalRegionDefinition`` built in this
    module's own Python code (never merchant input) is malformed — raised at
    import time only, exactly like
    ``variant_contract.InvalidVariantDefinitionError``."""


@dataclasses.dataclass(frozen=True)
class GlobalVariantDefinition:
    """One registered, trusted rendering variant for a ``GlobalRegionDefinition``.

    ``key`` is the stable string persisted in merchant JSON config (e.g.
    ``header_config["header_variant"] = "marketplace_search_first"``) —
    never a template path. ``renderer`` is always a fixed Python string
    written in this module, validated against
    ``GLOBAL_RENDERER_NAMESPACE`` at import time (see
    ``_validate_global_variant_renderer`` below) — the same trusted-path
    invariant ``variant_contract`` already enforces for section variants,
    applied to a different (non-section) template namespace."""

    key: str
    label_fa: str
    renderer: str


@dataclasses.dataclass(frozen=True)
class GlobalRegionDefinition:
    """One fixed global chrome region (``"header"`` in U2A; a future phase
    may add ``"footer"``/``"mobile_shell"``) and its registered variants.

    Unlike ``SectionDefinition.variants`` (optional, defaults to ``()``), a
    ``GlobalRegionDefinition`` always has at least one variant — the
    backward-compatible default — and ``default_variant`` is always a real,
    resolvable key (never ``None``): a global region is not an optional
    per-instance feature a section may or may not have, it is the one
    thing every published Store already renders today, so "no variant
    registered yet" is not a valid state for it."""

    key: str
    label_fa: str
    variants: tuple[GlobalVariantDefinition, ...]
    default_variant: str
    #: Which key of the region's *existing* persisted config dict selects
    #: the active variant — exactly the same reason
    #: ``SectionDefinition.variant_setting_key`` exists: the header's own
    #: config already has many keys (``show_search``, ``sticky``, ...);
    #: this says which one is the variant selector, without renaming any
    #: of them.
    variant_setting_key: str


#: Namespace constraint for every ``GlobalVariantDefinition.renderer`` —
#: deliberately a *different* namespace from
#: ``variant_contract.SECTION_VARIANT_RENDERER_NAMESPACE`` (global regions
#: are not sections). Broad enough to include the pre-existing, unchanged
#: ``page_shell_header.html`` (registered below as ``legacy_default``'s
#: renderer, at its current, un-moved path) as well as the four new
#: ``global_header/`` variant partials.
GLOBAL_RENDERER_NAMESPACE = "storefront_builder/partials/"

_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_global_variant_renderer(renderer: str) -> None:
    """Same shape of check as ``variant_contract._validate_variant_renderer``
    — renderer safety here is a defense-in-depth layer, not the primary
    guarantee (the primary guarantee is that ``renderer`` is always a fixed
    Python string in this file, never read from merchant JSON/settings).
    Unlike the section-variant version, ``None`` is never valid here —
    every global variant, including the default, must declare its own
    renderer (see ``GlobalRegionDefinition`` docstring)."""
    if not isinstance(renderer, str) or not renderer.strip():
        raise InvalidGlobalVariantDefinitionError("renderer باید یک رشته‌ی غیرخالی باشد")
    if renderer != renderer.strip():
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید فاصله‌ی ابتدا/انتهایی داشته باشد")
    if "\\" in renderer:
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید شامل بک‌اسلش باشد")
    if renderer.startswith("/"):
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ مطلق باشد")
    if _WINDOWS_DRIVE_PATH_RE.match(renderer):
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ درایوِ ویندوزی باشد")
    if ".." in renderer:
        raise InvalidGlobalVariantDefinitionError(f"renderer «{renderer}» نباید شامل .. باشد")
    if not renderer.startswith(GLOBAL_RENDERER_NAMESPACE):
        raise InvalidGlobalVariantDefinitionError(
            f"renderer «{renderer}» باید در فضای نامِ «{GLOBAL_RENDERER_NAMESPACE}» باشد"
        )


def _validate_global_region(region: GlobalRegionDefinition) -> None:
    """Import-time validation for one ``GlobalRegionDefinition`` — never
    called for merchant input, only for the Python-code registry entries
    below (see ``_GLOBAL_REGIONS`` construction)."""
    if not isinstance(region.key, str) or not region.key.strip():
        raise InvalidGlobalVariantDefinitionError("کلیدِ Global Region نمی‌تواند خالی باشد")
    if not region.variants:
        raise InvalidGlobalVariantDefinitionError(f"Global Region «{region.key}» باید حداقل یک Variant داشته باشد")
    seen: set[str] = set()
    for variant in region.variants:
        if not isinstance(variant.key, str) or not variant.key.strip():
            raise InvalidGlobalVariantDefinitionError(f"کلیدِ Variantِ «{region.key}» نمی‌تواند خالی باشد")
        if not isinstance(variant.label_fa, str) or not variant.label_fa.strip():
            raise InvalidGlobalVariantDefinitionError(f"برچسبِ Variantِ «{variant.key}» نمی‌تواند خالی باشد")
        _validate_global_variant_renderer(variant.renderer)
        if variant.key in seen:
            raise InvalidGlobalVariantDefinitionError(f"کلیدِ Variantِ «{variant.key}» در «{region.key}» تکراری است")
        seen.add(variant.key)
    if region.default_variant not in seen:
        raise InvalidGlobalVariantDefinitionError(
            f"default_variant «{region.default_variant}» در «{region.key}» به هیچ Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )


# ----------------------------------------------------------------- registry

#: U2A — backward-compatible default: the exact, unmoved, unmodified
#: partial every published-V2 Store renders today. Registering it as a
#: normal (not a special-cased) variant is what "Existing stores must not
#: visually change simply because U2A is merged" reduces to: a Store with
#: no ``header_variant`` in its persisted ``header_config`` resolves this
#: exact key via ``GlobalRegionDefinition.default_variant`` below —
#: same file, same DOM, same CSS classes as before U2A.
_LEGACY_DEFAULT_VARIANT = GlobalVariantDefinition(
    key="legacy_default",
    label_fa="فعلی / پیش‌فرض",
    renderer="storefront_builder/partials/page_shell_header.html",
)

_MARKETPLACE_SEARCH_FIRST_VARIANT = GlobalVariantDefinition(
    key="marketplace_search_first",
    label_fa="بازارگاهی (جستجو-محور)",
    renderer="storefront_builder/partials/global_header/marketplace_search_first.html",
)

_PREMIUM_THREE_COLUMN_VARIANT = GlobalVariantDefinition(
    key="premium_three_column",
    label_fa="پرمیوم سه‌ستونه",
    renderer="storefront_builder/partials/global_header/premium_three_column.html",
)

_BOUTIQUE_CENTERED_VARIANT = GlobalVariantDefinition(
    key="boutique_centered",
    label_fa="بوتیک (لوگوی مرکزی)",
    renderer="storefront_builder/partials/global_header/boutique_centered.html",
)

_DARK_TECH_VARIANT = GlobalVariantDefinition(
    key="dark_tech",
    label_fa="دیجیتال تیره",
    renderer="storefront_builder/partials/global_header/dark_tech.html",
)

GLOBAL_HEADER_REGION = GlobalRegionDefinition(
    key="header",
    label_fa="هدر فروشگاه",
    variants=(
        _LEGACY_DEFAULT_VARIANT,
        _MARKETPLACE_SEARCH_FIRST_VARIANT,
        _PREMIUM_THREE_COLUMN_VARIANT,
        _BOUTIQUE_CENTERED_VARIANT,
        _DARK_TECH_VARIANT,
    ),
    default_variant="legacy_default",
    variant_setting_key="header_variant",
)

#: Every ``GlobalRegionDefinition`` this module currently defines — U2A
#: covers header only (navigation/mobile shell are composed *within* the
#: header variant's own renderer, not separate regions yet); a future
#: phase (U2B footer, or a later mobile-shell split) extends this tuple,
#: never replaces the header entry.
_GLOBAL_REGIONS: tuple[GlobalRegionDefinition, ...] = (GLOBAL_HEADER_REGION,)

for _region in _GLOBAL_REGIONS:
    _validate_global_region(_region)
del _region


# --------------------------------------------------------------- resolve

def list_global_variants(region: GlobalRegionDefinition) -> tuple[GlobalVariantDefinition, ...]:
    return region.variants


def get_global_variant(region: GlobalRegionDefinition, variant_key: str | None) -> GlobalVariantDefinition | None:
    """Lookup by key — ``None`` for a missing/unknown key (no exception;
    the caller decides the fallback), exactly ``variant_contract.get_variant``'s
    contract."""
    if not variant_key:
        return None
    for variant in region.variants:
        if variant.key == variant_key:
            return variant
    return None


def resolve_active_global_variant(region: GlobalRegionDefinition, config: dict | None) -> GlobalVariantDefinition:
    """Read-time resolution — pure, no DB query, never raises. An
    absent/blank/unknown (including retired-in-a-future-release) stored
    key always falls safely back to ``region.default_variant``, which
    ``_validate_global_region`` already guaranteed resolves to a real,
    registered variant at import time — so this function's return value is
    never ``None``, unlike ``variant_contract.resolve_active_variant``
    (which legitimately returns ``None`` for the common "no variants
    registered at all" section case; a ``GlobalRegionDefinition`` never has
    that empty case, see its docstring)."""
    config = config if isinstance(config, dict) else {}
    requested = config.get(region.variant_setting_key)
    match = get_global_variant(region, requested)
    if match is not None:
        return match
    default_match = get_global_variant(region, region.default_variant)
    assert default_match is not None, "GlobalRegionDefinition.default_variant validated at import time"
    return default_match


def resolve_global_renderer_template(region: GlobalRegionDefinition, config: dict | None) -> str:
    """The one function render code/templates should call — resolves the
    active variant and returns its trusted renderer path directly, so
    callers never need to touch a ``GlobalVariantDefinition`` themselves."""
    return resolve_active_global_variant(region, config).renderer


class UnknownGlobalVariantSelectionError(ValueError):
    """Write-time (editor POST) counterpart of
    ``variant_contract.UnknownVariantSelectionError`` — a merchant submitted
    a ``header_variant`` value that names no registered variant. Never
    raised at read time (see ``resolve_active_global_variant`` above)."""


def validate_global_variant_selection(region: GlobalRegionDefinition, value) -> str:
    """Write-time validation for the editor POST path. An absent/blank
    value is not an error — it resolves to ``region.default_variant``
    (mirrors every other ``HEADER_TOGGLE_FIELDS``-style field's
    ``config.get(field, <default>)`` pattern in
    ``layout_service.validate_header_config``). A present, non-empty value
    that names no registered variant is rejected outright — a tampered/
    stale POST must never be able to persist an arbitrary string into
    ``header_config[region.variant_setting_key]``."""
    if not value:
        return region.default_variant
    if not isinstance(value, str) or get_global_variant(region, value) is None:
        raise UnknownGlobalVariantSelectionError(
            f"مقدارِ «{value}» برایِ سبکِ «{region.label_fa}» به هیچ Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )
    return value
