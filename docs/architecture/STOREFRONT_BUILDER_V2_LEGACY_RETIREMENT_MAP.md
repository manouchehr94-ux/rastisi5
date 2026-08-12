# Storefront Builder V2 — Legacy Family Retirement Map

Companion to `STOREFRONT_BUILDER_V2_PHASE_7_AUDIT.md`. Every legacy Family mechanism, classified
and mapped to its Universal V2 replacement. Classifications:
`ACTIVE_RUNTIME_DEPENDENCY` · `MERCHANT_UI_ONLY` · `TEST_ONLY` · `DOCUMENTATION_ONLY` ·
`VISUAL_REFERENCE_ONLY` · `DEAD_CODE`.

## Registries and models

| Item | File | Classification | Replacement / disposition |
|---|---|---|---|
| `FamilyDefinition`, `FAMILY_REGISTRY`, `register_family`/`get_family`/`list_families` | `apps/storefront_builder/family_registry.py` | ACTIVE_RUNTIME_DEPENDENCY (via validation + template-path lookups) | Deleted. Universal replacement: `layout_preset_registry.LayoutPresetDefinition` (Phase 6) for composition/tokens; no DOM-swap concept survives — Universal has exactly one renderer. |
| `PresetDefinition`, `PRESET_REGISTRY` | `apps/storefront_builder/preset_registry.py` | ACTIVE_RUNTIME_DEPENDENCY (validated in `layout_service`) | Deleted. Replacement: `layout_preset_registry.py` (already built, Phase 6, family-agnostic). |
| `family_slug`/`preset_slug` keys | `apps/storefront_builder/models.py::APPEARANCE_CONFIG_DEFAULTS` | ACTIVE_RUNTIME_DEPENDENCY | Removed from defaults/validator. No schema impact (plain JSON keys — see audit §3). |
| `SHOP_FAMILY`, `SHOP_FAMILY_SLUG` context keys | `apps/core/context_processors.py` | ACTIVE_RUNTIME_DEPENDENCY (global injection) | Removed. Nothing replaces them — Universal templates never branch on family. |
| `cart_preview_mode` family branch | `apps/cart/context_processors.py:29-31` | ACTIVE_RUNTIME_DEPENDENCY (business logic) | Branch removed; `cart_preview_mode` falls back to its non-family default unconditionally. |

## Validation & application services

| Item | File | Classification | Replacement / disposition |
|---|---|---|---|
| Family/preset validation clauses | `services/layout_service.py::validate_appearance_config` (`:261-273`) | ACTIVE_RUNTIME_DEPENDENCY | Removed. `layout_preset_key` validation (Phase 6) already covers the V2 path. |
| `build_family_default_sections`, `apply_family_default_sections` | `services/bootstrap_service.py:204-244` | ACTIVE_RUNTIME_DEPENDENCY (one caller) | Deleted. Replacement: `preset_service.apply_preset` (Phase 6) — already generalized to all 6 pages, already transactional/tenant-safe. |

## Merchant-facing UI

| Item | File | Classification | Replacement / disposition |
|---|---|---|---|
| Family gallery, preview button, apply form | `templates/dashboard/storefront_builder/partials/appearance_panel.html` (`:109-131` and the "قالب فروشگاه" hub card) | MERCHANT_UI_ONLY | Removed. Layout Preset gallery (Phase 6, already present in the same panel) becomes the primary "choose a starting point" flow. |
| `#sfbApplyFamilyForm`, `preview-candidate-family`/`apply-candidate-family` family-specific wiring | `templates/dashboard/storefront_builder/editor.html` (`:18-19`, `:201-204`, `:265-297`) | MERCHANT_UI_ONLY | Removed. |
| `family_changed`/`confirm_family_switch` POST handling | `views.py::storefront_appearance_editor` (`:838-880`, `:963-967`) | ACTIVE_RUNTIME_DEPENDENCY | Removed; template-slug-only path in the same view continues to work for the (out-of-scope, retained) legacy Template system. |
| `active_family`, `families` context | `views.py::storefront_appearance_editor` GET branch (`:980,991`) | MERCHANT_UI_ONLY | Removed. |
| `preview_family_slug`, `_CandidateAppearanceVersion` family handling | `views.py` (`:91-118`, `:199-208`) | ACTIVE_RUNTIME_DEPENDENCY | Removed (candidate-preview-by-family code path deleted along with the UI that triggers it). |

## Templates (67 files)

| Group | Path pattern | Classification | Disposition |
|---|---|---|---|
| Structural partials (44) | `templates/storefront_builder/partials/families/<slug>/{header,hero,category,footer}.html` | ACTIVE_RUNTIME_DEPENDENCY (while `SHOP_FAMILY` branches exist) → DEAD_CODE once branches are cut | Deleted after the `{% if SHOP_FAMILY %}` branches referencing them are removed from the 7 shared includes. |
| Product Detail page partials (11) | `apps/catalog/templates/catalog/partials/product_pages/<slug>.html` | Same | Deleted after `product_detail.html`'s family branch is removed. |
| Product card partials (12) | `apps/catalog/templates/catalog/partials/product_cards/*.html` | Same | Deleted after `product_card.html`'s family branch is removed. |

## Static assets

| Item | Path | Classification | Disposition |
|---|---|---|---|
| 11 family CSS files | `apps/core/static/css/families/*.css` | ACTIVE_RUNTIME_DEPENDENCY → DEAD_CODE once the conditional `<link>` in `templates/base.html:33-40` is removed | Deleted. |
| `data-sfb-family` attribute | `templates/base.html:3` | ACTIVE_RUNTIME_DEPENDENCY | Removed along with the CSS `<link>` block. |

## Tests

| File | Classification | Disposition |
|---|---|---|
| `test_family_registry.py` | TEST_ONLY (mixed: some safety assertions, mostly product-contract) | Deleted — its safety guarantees (Draft-only, confirm-before-destructive-reset, cross-tenant safety) are already independently proven for the surviving mechanism in Phase 6's `test_preset_service.py`. |
| `test_family_default_section_reset.py` | TEST_ONLY (safety-pattern, parameterized over a retired mechanism) | Deleted, same reasoning. |
| `test_eleven_families.py` | TEST_ONLY (pure product-contract/inventory) | Deleted. |
| `test_preset_registry_import.py` | TEST_ONLY (pure product-contract) | Deleted. |
| `test_six_families_tenant_isolation.py` | TEST_ONLY (safety-pattern, parameterized over a retired mechanism) | Deleted — tenant isolation for the surviving V2 rendering path is covered by Phase 5's `test_phase5_composition_lifecycle.py::CrossStoreCompositionIsolationTests` and Phase 6's `TenantIsolationTests`. |
| `test_family_artisan_editorial.py`, `test_family_heritage_premium.py`, `test_family_nordic_living.py`, `test_family_vibrant_catalog.py` | TEST_ONLY (pure product-contract) | Deleted. |
| `test_shared_capabilities.py` | Mixed — most of the file is DOCUMENTATION_ONLY... no, ACTIVE (unrelated infra: category images, cart preview service, product metafields) | `IndependentImageSettingsTests`, the family-default cases in `StoryRailSectionTests`, and `AllElevenFamiliesRegisteredTests` removed; everything else retained untouched. |
| `test_appearance.py` | Out of scope (Template/Palette system, zero family references) | Untouched. |

## New tests added this phase (retirement assertions)

Per the master instruction's 32 required test areas — see the Phase 7 report for the full
mapping; new coverage lives in `test_phase7_family_retirement.py` and targeted additions to
existing suites, proving: no merchant-facing family selector exists; `family_slug`/legacy
`preset_slug` cannot switch the public renderer even when a stale value is present in
`appearance_config`; all 6 page types render exclusively through the Universal path; Header/
Footer never resolve a family partial; Layout Presets/Palette continue to function
independently; Draft/Published/tenant/CSRF/auth/variant/cart safety properties are unaffected.

## Explicitly NOT retired

- `appearance_registry.py` in full (Palette system + shared structural tokens + the separate,
  still-live 10-entry `TemplateDefinition`/`TEMPLATE_REGISTRY` system — see audit §0/§7 for the
  scoping rationale).
- `layout_preset_registry.py`, `services/preset_service.py` (Phase 6).
- Any product/category/collection/order/customer/content data.
