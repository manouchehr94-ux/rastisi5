# Universal Storefront Engine — Phase 1 Architecture

**Phase:** 1 — Universal Block/Data Architecture.
**Branch:** `feature/universal-storefront-engine-v1`, cut from the approved baseline
`9b867c457527137e95bfb14a5891b2cf39a1281b` on `claude/family-visual-fidelity-fix`.

**Correction pass (same day):** the initial Phase 1 pass left row-composition
validation and Lock enforcement unwired from the mutation paths that could actually
violate them, and the background-image field trusted an arbitrary merchant-supplied
URL. All three are fixed below (§3.2, §3.3, §3.5) and the fingerprint gap this
introduced is fixed in §6. Sections below describe the corrected, current state —
they are not a diff log; see the correction commit message for the itemized change
list.
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
`is_row_member(section)`.

**Correction:** the initial pass left this validator unwired from every actual mutation
path, meaning a row set up any way at all (fixture, admin, a future Preset) could be
silently broken by routine editing. It is now enforced, fail-closed, on every path that
can change row composition on an *existing* Draft:

- `storefront_section_remove` — rejects deleting a row member (`row_service.is_row_member`)
  rather than leaving an orphaned/undersized row behind.
- `storefront_section_move` (up/down) — simulates the swap in memory and runs
  `validate_page_row_layout` on the result before writing; also blocks moving into a
  *locked* neighbor (see §3.5). A subtlety worth recording: the section fetched via
  `_get_scoped_section` and its duplicate inside the freshly-queried `siblings` list are
  two distinct Python objects for the same row — the fix explicitly replaces the stale
  list entry with the mutated one before validating, otherwise the simulation would
  validate against pre-swap data for one side of the swap.
- `storefront_section_reorder` (bulk/drag-and-drop) — simulates the full proposed
  ordering (including sections *not* present in the posted `section_ids`, at their
  existing `order`) and validates before writing anything.
- `preset_service.apply_preset` — see §3.5; wholesale page replacement is a row-breaking
  operation too, not just a lock-breaking one, and is covered by the same guard.

No new "canonical setter" function was added for *writing* `row_key`/`row_span` in the
first place, because nothing writes them yet (no Builder UI exposes row assignment) —
inventing one now would be new UI-adjacent surface with no caller, which is exactly the
scope expansion this phase was told to avoid. What was missing, and is now fixed, is
that the mutation paths that already exist cannot silently corrupt a row however it got
there.

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
 "color": "#RRGGBB" | "", "media_asset_id": int | None, "pattern_slug": "..."}
```

`mode="theme"` (no override — today's only behavior) is the default and the fallback for
any invalid/incomplete input, matching the codebase's established lenient-fallback
convention for closed-choice settings (e.g. `validate_motion_settings`). Colors are
validated with the platform's existing `validate_hex_color`.

**Correction — tenant safety:** the initial pass validated `mode="image"` as a free
`image_url` string checked only for a safe *scheme* (`validate_external_url`, the same
validator `image_text` uses), with no relationship to the current Store at all. That is
a materially different, weaker guarantee than every other per-instance reference in this
codebase (`source_id`, `destination_id`, `category_ids`, `brand_ids`, ...), which are all
opaque integer IDs resolved against the current Store later. A raw external URL is
schema-safe (no XSS/protocol injection) but not *tenant*-safe — nothing stopped a section
from pointing at any arbitrary external image forever, and the pattern doesn't compose
with the platform's actual media storage.

Fixed by replacing `image_url` with `media_asset_id` — shape-validated here as a plain
positive integer (mirroring `source_id`), never touching the database at this layer, per
the file's own established separation of concerns. The store-scoped resolution now
lives in `apps/content/services.py::resolve_background_media_url(store, background)`,
directly alongside — and following the exact same fail-closed shape as —
`resolve_destination_setting`: it looks up `apps.content.models.MediaAsset` filtered by
`(pk=media_asset_id, store=store)`, and returns `None` (never an exception, never another
store's file) for anything missing, deleted, or foreign. `mode="image"` with no
`media_asset_id` supplied falls back to `theme`, matching every other optional-reference
field in this file.

No Media Picker UI was built (out of scope per the correction brief) — there is
currently no way for a merchant to actually set `media_asset_id` through the Builder
UI, which is an honest reflection of reality, not a gap introduced by this fix: the same
was already true of `mode="pattern"` before this correction (empty registry, no UI), and
remains true of `mode="image"` now (real reference, but no picker yet). What changed is
that the *data contract itself* can no longer represent "trust this arbitrary external
URL" — only "resolve this Store's own uploaded asset, or show nothing."

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

**Correction — the enforcement above was incomplete; three real bypasses were found and
closed:**

1. **`storefront_section_move`'s swap partner.** A move is a swap of two neighbors; the
   original guard only checked the section being explicitly moved, so an *unlocked*
   neighbor could still be moved "up"/"down" straight into — and thereby displace — a
   *locked* one. Fixed: the guard now also checks `other.is_locked` (the computed swap
   target) before performing the swap.
2. **`storefront_section_reorder` (bulk/drag-and-drop) had no lock check at all** — this
   was previously deferred with the reasoning that it needed real Builder-UI design work
   first. On reflection that reasoning doesn't hold at the backend-enforcement level: no
   UI decision is needed to state the invariant "a locked section's final position must
   equal its current position," and leaving the *backend* unenforced meant the lock
   guarantee was only ever a UI-disabling convention, never a real one, for this path.
   Fixed: the endpoint now computes each candidate's resulting index and rejects the
   entire reorder (matching the pre-existing "duplicate IDs" all-or-nothing convention)
   if any locked section's index would change.
3. **`preset_service.apply_preset`** wholesale-deletes every section on each page a
   Preset covers (`page.sections.all().delete()`) and rebuilds from the Preset's list —
   an "alternate service path" that bypassed `storefront_section_remove`'s guard
   entirely. Fixed: `apply_preset` now raises `LockedSectionsPresentError` (a subclass of
   the existing `InvalidPresetError`, so the calling view's existing exception handling
   needed no changes) if any page it would replace currently has a locked section —
   checked in the function's existing validate-everything-before-writing pass, so a
   rejection leaves the Draft completely untouched (header/footer/appearance included).

**Still deliberately not touched:** `storefront_section_duplicate`. Spec §37 names only
move and delete; duplication creates an independent new logical section (its own fresh
`stable_id`, and — since `row_key`/`is_locked` are real model fields never copied by the
duplicate view's explicit field list — a duplicate is never locked and never a row member
regardless of the source), so a lock on the source has no bearing on it. Also
deliberately not touched: whole-*version* replacement paths (`discard_draft`,
`restore_version`'s pre-restore cleanup, `apply_industry_layout`'s draft replacement) —
these already require their own explicit user confirmation before running and are a
different, coarser action ("start over") than the per-block protection Lock is for;
treating them as another Lock bypass would be scope creep into a product decision that
wasn't asked for.

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

## 6. Draft/Published behavior

`StorefrontLayout.published_version`/`draft_version` pointer pair, atomic
`layout_service.publish()`, and `restore_version()` (which always creates a new Draft,
never republishes directly) are unchanged.

**Correction:** the initial pass's claim that the three new `StorefrontSection` fields
"participate in `compute_fingerprint()` automatically" was checked against the actual
code for this pass and found to be wrong — `compute_fingerprint()` builds its per-section
payload from an explicit, hand-written dict of four named keys
(`page_type`/`section_key`/`order`/`is_active`/`settings`), not a wholesale field
serialization, so a new *model* column (as opposed to a new key inside the `settings`
JSONField, which *is* covered automatically) is invisible to it unless added by name.

Fixed with an explicit, tested product decision for each new field:

- **`row_key`/`row_span` — included.** They change what the public render actually looks
  like (which section sits in which row, at what width), so a Draft that only changes
  these must be detected as different from the currently-Published version — exactly the
  same reasoning that already covers `order`/`is_active`.
- **`background`/`spacing` — already included, no change needed.** Both live inside the
  `settings` JSONField, which the fingerprint already serializes wholesale.
- **`is_locked` — explicitly excluded.** It has zero effect on public rendering (editor-
  only, like the pre-existing `collapsed_in_editor`, which this fingerprint has also
  never included) — locking or unlocking a section must not make an otherwise-identical
  Draft register as "changed" for publish/drift purposes.

Verified with two new tests: changing `row_key`/`row_span` changes the fingerprint;
toggling `is_locked` does not.

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

- **Superseded by the correction pass** (previously listed here, now done): wiring row
  validation into remove/move/reorder/preset-apply; lock enforcement on bulk reorder and
  the move swap-partner; lock enforcement in `preset_service.apply_preset`.
- A UI for actually *assigning* `row_key`/`row_span` to sections (placing two blocks into
  a row) — still correctly out of scope; this phase closed the *validation* gap (nothing
  can silently corrupt a row through an existing mutation path), not the *authoring* gap
  (there is still no way to create a row in the first place through the Builder UI). Both
  belong with the Builder UI work.
- A Media Picker UI for choosing a `MediaAsset` for `background.media_asset_id` — the
  data contract and store-scoped resolver are ready and tested; no picker was built, per
  the explicit "do not overbuild" instruction.
- Wiring `render_service.group_items_into_rows` and
  `apps.content.services.resolve_background_media_url` into an actual template/CSS
  output — this is Phase 2 ("Universal Renderer") by the approved phase order.
- Populating `PATTERN_REGISTRY` with real pattern assets.
- A `Featured` product data source distinct from the existing `newest`-fallback (a
  pre-existing, previously-documented gap this phase did not touch — it is a data-source
  addition, not a Universal-architecture gap, and was not raised as blocking by the
  Owner).
- Lock-awareness for whole-*version* replacement actions (`discard_draft`,
  `restore_version`, `apply_industry_layout`) — considered and deliberately excluded; see
  §3.5's closing paragraph for the reasoning.
- Any V5-specific configuration/Preset — explicitly Phase 3.

## 13. Risks / unresolved issues

None identified that require an Owner decision at this time. The row/grid design
decision (§3.2) and the whole-version-replacement exclusion (§3.5) were both made using
the criteria/reasoning the Owner's briefs specified, and are documented here for review
rather than raised as open questions.
