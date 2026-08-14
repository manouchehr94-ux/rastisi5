# Universal Storefront Engine — Phase 1 Architecture

**Phase:** 1 — Universal Block/Data Architecture.
**Branch:** `feature/universal-storefront-engine-v1`, cut from the approved baseline
`9b867c457527137e95bfb14a5891b2cf39a1281b` on `claude/family-visual-fidelity-fix`.
**Scope:** models, schema, validation services, tests. No visual/frontend template work.
No V5 reproduction. No Builder UI beyond the minimal lock-toggle endpoint described below.

---

## 1. Starting point: this was not a greenfield phase

Before writing any code, this phase audited the actual code at the approved baseline
(not assumptions from an earlier review pass). The finding: the Family/Preset system
described in the product spec as forbidden (`family_registry.py`, `preset_registry.py`,
per-family template dispatch) **had already been retired** on this baseline, in a prior,
independent body of work (see git log: "Phase 7: hard cutover — retire the legacy Family
storefront system", and the `docs/architecture/STOREFRONT_BUILDER_V2_*` document set
already present in this tree). In its place, a substantial, working Universal
architecture already exists:

- `StorefrontLayout` / `StorefrontLayoutVersion` / `StorefrontPage` / `StorefrontSection`
  — a Draft/Published/Version-history model with atomic publish, six typed pages
  (home/product_detail/listing/collection/search/cart) per version, and sections owned
  by a page.
- `section_registry.py` — a 33-entry Block Definition registry (allowlisted template
  paths, per-type settings schema/validation, `min/max_instances`, `duplicable`,
  `removable`, `page_types`), with shared composable settings-blocks already layered
  onto it (`responsive`, `destination`, `motion`, `card`, `layout`/width-height).
- `render_service.py` — a single, section-type-agnostic renderer
  (`build_page_render_items`) shared by Draft preview and the public Published route.
- `section_data_service.py` — a store-scoped, fail-closed product-source resolver
  (`collection/category/brand/manual/newest/discounted/best_sellers/most_viewed`).
- `appearance_registry.py` — 20 ready-made palettes and 10 structural design Templates,
  applied through `StorefrontLayoutVersion.appearance_config`, fully independent of
  layout/preset choice.
- `layout_preset_registry.py` + `preset_service.py` — Presets as pure data (palette
  suggestion + header/footer partial config + per-page section lists), explicitly
  documented as not becoming a new Family system.

**Consequence for this phase's scope:** Phase 1's job was not to build this — it was to
find and close the concrete gaps between what already exists and what the specification
requires, without duplicating or replacing any of the above. Section 3 lists exactly what
was added; everything else in the bullet list above is unchanged.

## 2. Gaps identified and closed in this phase

A full read of `models.py`, `section_registry.py`, `render_service.py`,
`layout_service.py`, `appearance_registry.py`, `layout_preset_registry.py`, and a
codebase-wide search turned up four concrete gaps against the specification. All four
are additive (new fields with defaults that reproduce today's behavior exactly, or new
settings sub-blocks layered onto the existing per-type wrapper pattern already used for
`responsive`/`card`/`layout`/etc.) — nothing existing was removed, renamed, or
restructured.

| Gap (spec reference) | Status before this phase | What was added |
|---|---|---|
| Multiple **distinct block instances** sharing one horizontal row (spec §5.2 — 1/2/3/4 columns, e.g. Hero + Instant Offer side by side in V5) | Not supported — `StorefrontSection` was a flat per-page list; the only existing "columns" concept (`COLUMN_AWARE_SECTION_KEYS`) controls items *inside* one section instance (e.g. how many banners a `multi_banner` shows), not grouping of *different* section instances | `StorefrontSection.row_key` / `row_span` fields + `services/row_service.py` validation + `render_service.group_items_into_rows` (data-shaping helper) |
| Per-block **background** (spec §9 — color/image/pattern) and per-block **custom color override** (spec §10.2) | Not supported — only the store-wide palette (`appearance_config`) existed; no per-instance override | `background` settings sub-block (`_with_background`), mirroring the existing `_with_card`/`_with_layout` wrapper pattern |
| Per-block **spacing** (spec §8 — Basic: Small/Normal/Large, Advanced: exact padding/margin) | Not supported | `spacing` settings sub-block (`_with_spacing`), same wrapper pattern |
| Per-block **Lock** (spec §37 — cannot be moved/deleted until unlocked) | Not supported | `StorefrontSection.is_locked` field + guards in `storefront_section_remove`/`storefront_section_move` + a minimal toggle endpoint |

Everything else the specification asks for at the "data architecture" level (Draft/
Publish/Rollback, tenant scoping, Block Library allowlist, palette independent of
layout, product data sources, header/footer composable columns) was already present and
is reused as-is.

## 3. New/changed components

### 3.1 `StorefrontSection` — three new fields (`models.py`, migration `0012`)

```python
row_key  = models.CharField(max_length=40, blank=True, default="")
row_span = models.PositiveSmallIntegerField(default=12)
is_locked = models.BooleanField(default=False)
```

Migration `0012_universal_block_row_and_lock.py` is three plain `AddField` operations,
no `RunPython`, no backfill. This is safe *because* the chosen defaults are exact
no-ops for every existing row: `row_key=""` means "standalone, full width" (today's only
behavior), `row_span=12` is inert when `row_key` is empty, `is_locked=False` preserves
today's full move/delete freedom. Verified explicitly with a new test
(`test_row_and_lock_defaults_reproduce_pre_phase1_behavior`).

### 3.2 Row/Grid composition — no new model

The specification requires composing 1/2/3/4 columns in a row (§5.2) but does not
mandate a specific schema. Before adding anything, the alternative of a separate
`GridRow` table (parent row → child sections) was weighed against extending
`StorefrontSection` directly, against the criteria in the task brief:

- **Validation** — a dedicated grid unit (12, the standard web-grid convention already
  implicit in this codebase's Bootstrap-derived CSS) lets `row_span` express both equal
  splits (2 cols = 6+6, 3 = 4+4+4, 4 = 3+3+3+3) and the asymmetric 1/3+2/3 split V5's
  Hero+Instant-Offer pairing needs (4+8), with one simple invariant: spans of a row's
  members sum to 12.
- **Ordering / drag-and-drop** — sections stay a flat list under `StorefrontPage`,
  ordered by the existing `order` field, exactly as today. A row is just "N sections in
  a row sharing a `row_key`, contiguous in `order`" — no second ordering axis, no
  parent/child re-parenting for the Builder's drag logic to reason about.
  a lightweight optional grouping over the *existing* mechanism.
- **Rendering simplicity** — the renderer's job becomes "group adjacent items with the
  same non-empty `row_key`", a pure list transformation (`group_items_into_rows`), not a
  second query path or template hierarchy.
- **Migrations** — two nullable-with-safe-default columns vs. a new table, an FK on
  every section, and a data migration to backfill "no row" for every existing row.
- **Nesting complexity** — zero new levels in the data model. `StorefrontSection` is
  still owned directly by `StorefrontPage`, matching the Phase 1A decision record this
  phase found already in place and deliberately did not re-litigate.
- **Extensibility / V5 reproduction** — `MAX_ROW_MEMBERS = 4` and `ROW_WIDTH_UNITS = 12`
  are both named constants in `row_service.py`, not hardcoded — raising the column cap
  later (spec only requires up to 4) is a one-line change, not a schema change.

**Decision:** extend `StorefrontSection`, do not add a `GridRow` model. This satisfies
every criterion above with the smallest possible change surface, and is fully consistent
with "prefer reuse/extension over duplication."

`services/row_service.py` (new) provides `validate_page_row_layout(ordered_sections)` —
fail-closed validation of a page's full row composition (group size 2-4, contiguous
membership, spans summing to exactly 12, each span between 1 and 12) — and
`is_row_member(section)`. This function is not yet wired into any create/reorder
endpoint (that wiring belongs to the Builder UI work explicitly deferred past this
phase); it exists now as the tested, ready-to-call contract Phase 2+ will build on.

`render_service.group_items_into_rows(items)` (new, additive) is a pure data
transformation: given the existing flat `build_page_render_items` output, it returns a
list of `{"row_key": str, "items": [...]}` groups (a standalone section becomes a
one-member row with `row_key=""`). **It renders no HTML and is not called by any view or
template yet** — it is the data shape Phase 2 ("Universal Renderer") will consume to
emit actual grid/flex markup, kept separate so this phase touches zero `.html` files.

### 3.3 Background settings block (`section_registry.py`)

`_with_background`, layered exactly like the existing `_with_card`/`_with_layout`
wrappers, adds a `background` key to `settings` for `BACKGROUND_AWARE_SECTION_KEYS`
(every registered section type except the five spec-protected, `removable=False`
context-aware page-critical types — `product_main`, `product_listing`, `cart_items`,
`cart_summary`, `collection_products` — and the header-adjacent `announcement_bar`):

```python
{"mode": "theme" | "color" | "image" | "pattern",
 "color": "#RRGGBB" | "", "image_url": "...", "pattern_slug": "..."}
```

`mode="theme"` (no override — today's only behavior) is the default and the fallback for
any invalid/incomplete input, matching the codebase's established lenient-fallback
convention for closed-choice settings (e.g. `validate_motion_settings`). Colors are
validated with the platform's existing `validate_hex_color`; image URLs with the
platform's existing `validate_external_url` (rejects `javascript:`/`data:`/
protocol-relative URLs — same validator `image_text` already uses).

`pattern_slug` is validated against a new `PATTERN_REGISTRY: dict[str, str] = {}` —
**deliberately empty**. No pattern/texture CSS assets exist anywhere in this codebase
today (confirmed by search); inventing a fixed list of slugs pointing at files that don't
exist would be exactly the "build something not yet designed" this phase was told to
avoid. The schema is ready (`mode="pattern"` is a legal, tested value); an unrecognized
or not-yet-registered `pattern_slug` falls back to `theme` rather than erroring, so
merchants are never blocked and no error message references a feature that doesn't
exist yet. Populating `PATTERN_REGISTRY` later (Phase 2/3, once real pattern assets are
built) is a pure data change — zero schema/migration impact.

### 3.4 Spacing settings block (`section_registry.py`)

`_with_spacing`, same wrapper pattern, adds a `spacing` key using the identical
allowlist as background (`SPACING_AWARE_SECTION_KEYS = BACKGROUND_AWARE_SECTION_KEYS`,
since both answer "how does this block sit in the page," not "what is inside it"):

```python
{"vertical_spacing": "small" | "normal" | "large",
 "advanced": {"padding_top": int|None, "padding_bottom": int|None,
              "margin_top": int|None, "margin_bottom": int|None}}
```

`vertical_spacing="normal"` with no advanced overrides is the default — again a pure
no-op for every section that has never touched this control. Advanced pixel values are
clamped to `[0, 200]` (same clamp-not-reject convention as the existing slider-interval
validator) and `None` means "not overridden, derive from `vertical_spacing`" — the actual
small/normal/large → pixel mapping is a CSS/rendering decision left to Phase 2, exactly
as `density`/`motion` tokens already work at the store-wide level.

### 3.5 Lock (`models.py`, `views.py`, `urls.py`)

`is_locked` (§3.1) plus:

- A guard at the top of `storefront_section_remove` — a locked section cannot be
  deleted, checked before the existing `removable` type-level check.
- A guard at the top of `storefront_section_move` — a locked section cannot be
  reordered via the up/down buttons.
- `storefront_section_lock_toggle` (new view, identical shape to the existing
  `storefront_section_collapse_toggle`) + one new URL,
  `storefront-builder/sections/<pk>/lock/` (`dashboard:storefront-builder-section-lock`).

**Deliberately not touched:** the bulk `storefront_section_reorder` endpoint (drag-and-
drop). Making that endpoint lock-aware requires deciding Builder-UI-level behavior (does
a locked section silently stay put while others reflow around it? is it undraggable at
the DOM level? does the request get rejected wholesale?) that has no drag-and-drop UI to
answer against yet — real design work belongs with the Builder phase, not invented here.
`storefront_section_duplicate` is also untouched: spec §37 names only move and delete;
duplication creates an independent new logical section (its own fresh `stable_id`,
exactly like duplicating an unlocked section today), so a lock on the source has no
bearing on it.

## 4. Preset representation (verified, not changed)

`layout_preset_registry.LayoutPresetDefinition` already satisfies the "Preset = data
only" requirement (spec §40, §5.7 in the existing V2 spec doc) precisely: no template
path field anywhere on it, `appearance` limited to structural tokens (never color —
palette is a separate, always-independent choice per an existing locked owner decision),
`pages: dict[page_type, tuple[PresetSectionEntry, ...]]` where each entry is just a
`section_key` + optional partial settings dict, validated at import time against the
same `SECTION_REGISTRY` this phase extended. No changes were needed here — the new
`background`/`spacing`/`row_key`/`row_span` fields are simply available to any future
Preset's section entries the same way `destination`/`card`/`layout` already are, with no
special-casing required.

## 5. Palette / design-config representation (verified, not changed)

`appearance_registry.py` already ships 20 palettes (spec asks for "at least 10") and 10
structural Templates, applied via `StorefrontLayoutVersion.appearance_config` — global,
independent of layout Preset (spec §10.3), with `resolve_colors()` implementing
"base palette + per-store manual overrides" layering. This phase's per-block
`background.mode="color"` override composes with, not against, this: a section's
`background` block is a second, more specific override layer sitting *below* the
section itself, exactly matching spec §10.2's "○ Use Theme Color / ● Custom Color"
per-block picture. No changes were needed to the global palette system.

## 6. Draft/Published behavior (verified, not changed)

`StorefrontLayout.published_version`/`draft_version` pointer pair, atomic
`layout_service.publish()`, and `restore_version()` (which always creates a new Draft,
never republishes directly) are unchanged. The three new `StorefrontSection` fields
participate in the existing `StorefrontLayoutVersion.compute_fingerprint()` drift-
detection hash automatically (it serializes each section's full field set including any
new columns added here) — no change to that method was required.

## 7. Tenant safety (verified, not changed; explicitly checked for the new fields)

`row_key`/`row_span`/`is_locked` carry no cross-store reference — they are pure layout
metadata on a `StorefrontSection` row that is already store-scoped through its `page →
version → layout → store` chain, and the existing `_get_scoped_section` helper (used by
every mutating view, including the two new guards and the new lock-toggle view) already
enforces that a section can only be acted on if it belongs to the requesting store's
Draft. `background.image_url` and `pattern_slug` go through the platform's existing
`validate_external_url`; `pattern_slug` additionally has nothing valid to reference yet
(empty registry), so there is no new cross-tenant surface introduced by this phase.

## 8. Tests added

- `apps/storefront_builder/tests/test_models.py` —
  `test_row_and_lock_defaults_reproduce_pre_phase1_behavior`.
- `apps/storefront_builder/tests/test_row_service.py` (new file) — row-group validity
  (2-4 members, span-sums-to-12, per-span range, non-contiguous same-`row_key` rejected,
  two independent rows on one page both valid, sections without `row_key` always valid),
  plus `is_row_member`.
- `apps/storefront_builder/tests/test_render_service.py` — `GroupItemsIntoRowsTests`
  (standalone sections each become a one-member row; adjacent same-`row_key` items
  group; non-adjacent same-`row_key` items stay separate rather than incorrectly
  merging; empty input).
- `apps/storefront_builder/tests/test_section_registry.py` — `BackgroundSettingsTests`,
  `BackgroundAwareIntegrationTests` (including an explicit assertion that the five
  protected context-aware types are excluded), `SpacingSettingsTests`,
  `SpacingAwareIntegrationTests`.
- `apps/storefront_builder/tests/test_views.py` — `LockSectionTests` (toggle flips the
  flag; locked section survives a remove POST; unlocked section is still removable;
  locked section does not move on a move POST; a locked section can still be
  duplicated).

## 9. Exact test commands and results

```
DJANGO_SETTINGS_MODULE=shop_core.settings python manage.py test apps.storefront_builder -v 2
```

Run once against the unmodified baseline (`9b867c4`) before any change, to establish a
known-green starting point, and again after this phase's changes. Full output and pass/
fail counts for both runs are reported in the accompanying stop report (Section 17 of
that report), not duplicated here since this document describes the architecture, not
the run log.

## 10. Migrations created

- `apps/storefront_builder/migrations/0012_universal_block_row_and_lock.py` — three
  additive `AddField` operations on `StorefrontSection` (`row_key`, `row_span`,
  `is_locked`), no data migration, no backfill, fully reversible.

## 11. Legacy frontend systems intentionally left untouched

Per the explicit frontend-freeze instruction for this phase: no `.html` template was
created, edited, or even inspected for the purpose of changing its output. Specifically
untouched: every file under `apps/storefront_builder/templates/`, every file under
`apps/catalog/templates/catalog/partials/product_cards/` and `.../product_pages/`, all
CSS. The already-retired Family system (`SIX_NEW_FAMILIES_IMPLEMENTATION_*.md` and its
associated historical templates, if any remain on disk) was not touched or re-examined —
it was already fully retired at the approved baseline and is out of scope for this
phase.

## 12. Deferred items (explicitly out of scope for this phase)

- Wiring `row_service.validate_page_row_layout` into the section-add/reorder views —
  belongs with the Builder UI work that lets a merchant actually place two blocks into a
  row (drag-and-drop grouping interaction design).
- Wiring `render_service.group_items_into_rows` into an actual template/CSS grid output
  — this is Phase 2 ("Universal Renderer") by the approved phase order.
- Lock-awareness in the bulk drag-and-drop reorder endpoint.
- Populating `PATTERN_REGISTRY` with real pattern assets.
- A `Featured` product data source distinct from the existing `newest`-fallback (a
  pre-existing, previously-documented gap this phase did not touch — it is a data-source
  addition, not a Universal-architecture gap, and was not raised as blocking by the
  Owner).
- Any V5-specific configuration/Preset — explicitly Phase 3.

## 13. Risks / unresolved issues

None identified that require an Owner decision at this time. The row/grid design
decision (Section 3.2) was made using the criteria the Owner specified, and is
documented here for review rather than raised as an open question, since the brief
asked for a decision with rationale, not a fresh question.
