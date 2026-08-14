# Universal Storefront Engine — Phase 2: Universal Renderer

**Phase:** 2 — Universal Storefront Renderer.
**Branch:** `feature/universal-storefront-renderer-v1`, cut from the approved Phase 1
checkpoint `1106a310b52903c43d9bd7dfda45dcb67c199aca` on
`feature/universal-storefront-engine-v1`.
**Scope:** wire the Phase 1 data architecture (row/grid composition, per-block
background/spacing, tenant-safe background media) into actual rendered output,
through the one existing shared renderer. New generic CSS/templates only where
needed to prove the pipeline. No V5 reproduction, no Builder UI work.

---

## 1. Starting point: the renderer already existed

As with Phase 1, this phase began by auditing the actual code rather than assuming a
greenfield build. Finding: **the "Universal Renderer" the brief asks for already
exists** — `render_service.build_page_render_items` is a single, section-type-agnostic
function that every one of the six public page types (home, product listing, product
detail, collection, search, cart) and the Builder's Draft preview all call, through one
shared context service (`storefront_context_service.build_universal_storefront_context`)
and one shared template partial (`responsive_section_wrapper.html`). There is no Family
renderer, no per-preset renderer, no Beraito renderer, and no per-template rendering
engine anywhere in this codebase — that was already true at the Phase 1 checkpoint.

**What was missing** was narrower than "build a renderer": two pieces of the Phase 1
data contract — `row_key`/`row_span` and `background`/`spacing` settings — were
validated and stored, but never actually reached rendered HTML. `group_items_into_rows`
(Phase 1) was a tested pure function nothing called; `resolve_background_media_url`
(Phase 1) was a tested resolver nothing called. Phase 2's job was to close exactly that
gap — wire the existing data contract into the existing renderer — not to build a
second rendering system alongside it.

## 2. Render pipeline (as it exists after this phase)

```
Store (resolved from Host header, apps.stores.resolution)
  │
  ▼
page_resolution_service.resolve_published_page(store, page_type)
  │  (or the Draft equivalent, for Builder preview — see §9)
  ▼
StorefrontLayoutVersion → StorefrontPage (one of 6 typed pages)
  │
  ▼
render_service.build_page_render_items(page, store, page_context)
  │  for each active StorefrontSection, ordered:
  │    - section_registry.get_definition(section.section_key)   [fail-closed lookup]
  │    - per-type context builder (or context-aware builder for page_context)
  │    - context["settings"] = section.settings                  [validated at save time]
  │    - context["background_media_url"] = resolve_background_media_url(store, ...)
  ▼
render_service.group_items_into_rows(items)
  │  groups adjacent items sharing a non-empty row_key into
  │  {"row_key": ..., "items": [...]}; a standalone item is a one-member row
  ▼
storefront_context_service / cart views / storefront_preview view
  │  add "rows" (and, unchanged, "render_items") to the template context
  ▼
render_rows.html  (ONE shared partial, new in this phase)
  │  for each row: >1 member → .rsec-row grid wrapper around each member;
  │                 1 member  → unwrapped, byte-identical to pre-Phase-2 output
  ▼
responsive_section_wrapper.html  (existing, extended this phase)
  │  resolves settings.responsive / motion / layout / background / spacing
  │  into data-* attributes and inline style — never touches the database
  ▼
{% include item.template_name %}  — the section's ONE allowlisted template
  (storefront_builder/sections/<key>.html — never a Family/preset variant)
```

This is one pipeline, walked identically by every page type and by both Draft preview
and the public (Published) route — the only branch point is *which version* is
resolved (§9), never *which renderer*.

## 3. Registry dispatch / template safety (verified, not changed)

`section_registry.SECTION_REGISTRY` remains the sole allowlist: `get_definition()` is
the only way any code resolves a `section_key` to a template path, and it raises
`UnknownSectionTypeError` for anything not registered — `_build_items_from_sections`
catches that and silently skips the section (fail-closed, never a 500). No merchant
input reaches `template_name` at any point; it is always the literal string from a
`SectionDefinition` written by the platform team. This phase added zero new section
types and zero new template-path sources — confirmed by test
(`test_get_definition_unknown_key_never_returns_template`, pre-existing, still passing).

## 4. Row/grid rendering

**Representation** (Phase 1, unchanged): `StorefrontSection.row_key` (empty = standalone)
and `.row_span` (a 12-unit grid span, meaningful only when `row_key` is set).

**New this phase — `render_rows.html`** (`apps/storefront_builder/templates/
storefront_builder/partials/`): the one shared partial every render-items consumer now
includes instead of looping `render_items` directly. A row with more than one member is
wrapped in `<div class="rsec-row">`, each member in `<div class="rsec-row-item"
style="--row-span:N">` before including the existing `responsive_section_wrapper.html`
unchanged; a one-member row (the default, unconfigured case) renders with zero extra
markup — **byte-identical to the pre-Phase-2 output** for every section that has never
touched `row_key`, which is every section on every existing store today.

**New this phase — CSS** (`storefront_builder.css`): `.rsec-row` is `display: grid;
grid-template-columns: repeat(12, 1fr)`; each `.rsec-row-item` takes `grid-column: span
var(--row-span, 12)`. Verified compositions, in a real browser (§8): `12` (single/
standalone), `6+6`, `4+4+4`, `3+3+3+3`, `8+4` (the asymmetric split V5's Hero+Instant-
Offer pairing will need in Phase 3) — all render as a genuine CSS Grid with the correct
track widths (confirmed via `getComputedStyle(...).gridTemplateColumns`, not just
inspecting markup).

**Where `rows` is computed**: `render_service.group_items_into_rows(items)` is called
in exactly three places — `storefront_context_service.build_universal_storefront_context`
(covers home/listing/product-detail/collection/search/cart on the public Published
route), `storefront_builder/views.py::storefront_preview` (Draft), and
`apps/cart/views.py::_render_cart_container` (the HTMX cart-update partial, a third,
independent call site that predates this phase and intentionally does not go through
`storefront_context_service`). All three add a `"rows"` context key alongside the
existing `"render_items"` key — nothing that reads `render_items` directly needed to
change.

## 5. Responsive foundation

`.rsec-row` collapses to `grid-template-columns: 1fr` (single column, every member
`grid-column: span 1`) under `max-width: 1000px` — the same breakpoint already used
throughout `home.css`/`product_card.css`. No merchant-facing "mobile row" setting exists
anywhere in the schema or the UI; the merchant configures one `row_span` per member and
the collapse is automatic. Verified in a real browser at a 390px viewport (§8): the
computed `grid-template-columns` at that width is a single track, confirmed for a row
that renders as 12 tracks at 1440px.

## 6. Global design tokens (verified, not changed)

`apps/core/static/css/tokens.css` already exposes the full semantic palette
(`--brand-primary/secondary/accent/text/muted/border/background/surface`, resolved from
`appearance_registry.resolve_colors()` and injected on `<html>` — unrelated to this
phase, unchanged) plus structural tokens (`--radius`, `--button-radius` from the active
Template). This phase's per-block overrides compose with, not against, these: a
section's `background`/`spacing` settings are a second, more specific layer applied via
inline `style` on `.rsec` (§7), which naturally wins CSS specificity over the
token-driven base without needing `!important` anywhere.

## 7. Background-media resolution (tenant-safe)

**Resolution**: `apps.content.services.resolve_background_media_url(store, background)`
(Phase 1, unchanged) — looks up `MediaAsset(pk=media_asset_id, store=store)`, returns
`None` for anything missing or belonging to another store. **Now actually called**, once,
centrally, inside `render_service._build_items_from_sections` for every section
(per-instance, not per-section-type-cached, since two sections of the same type can
reference different assets) — the result is stashed on `item["context"]
["background_media_url"]`.

**Application**: `responsive_section_wrapper.html` emits `data-bg-mode="color"|"image"`
(omitted for the default `"theme"`) and, for `"color"`, an inline
`background-color:<hex>`; for `"image"`, an inline `background-image:url(...)` using
only the pre-resolved, store-verified URL — the template never reads
`media_asset_id` itself or constructs a URL. A foreign-store `media_asset_id` therefore
never has any code path to a rendered `background-image` — verified in a real browser
render (§8: a section pointed at another store's `MediaAsset` renders with no
`background-image` at all, not a broken image, not the wrong store's image).

`mode="pattern"` remains schema-ready but inert (`PATTERN_REGISTRY` is still
deliberately empty, per the Phase 1 decision — no pattern assets exist yet to render).

## 8. Runtime / browser verification performed

Per the explicit requirement that Phase 2 is not accepted from unit tests alone:

1. Django dev database migrated fresh; a generic demo dataset was seeded directly via
   the ORM (one Vendor, two Categories, one Brand, six Products, one MediaAsset) — no
   V5 content, no V5 imagery, no V5 copy anywhere in the seed data.
2. A Draft home page was assembled and published with: an 8+4 row (`hero_banner` +
   `amazing_offers`), two independent `product_section` instances (different
   `data_source`, different background colors — proving repeated block type with
   independent per-instance config), a 4+4+4 row (`rich_text`/`faq`/`testimonials`), a
   3+3+3+3 row (four `rich_text`), a 6+6 row (`image_text` with a real store-scoped
   background image + `trust_features` with a background color), standalone
   `category_grid`/`brand_carousel` sections, and one `is_active=False` `newsletter`
   section.
3. `manage.py runserver` was started against this database; `manage.py shell` seeding
   used the ORM directly (bypassing the Builder UI, which cannot author rows yet —
   consistent with Phase 1's documented deferral).
4. **A real headless Chromium** (Playwright, the pre-installed browser in this
   environment — not a template-string assertion) opened `http://127.0.0.1:8123/` at a
   1440×1000 desktop viewport and a 390×844 mobile viewport.

**Observed, in the browser** (screenshots delivered to the user):
- All four configured rows (8+4, 4+4+4, 3+3+3+3, 6+6) render as visible side-by-side
  columns at desktop width; `getComputedStyle(row).gridTemplateColumns` confirmed 12
  equal tracks on the first row.
- At 390px, the same row's computed `gridTemplateColumns` collapsed to a single track —
  automatic, no configuration.
- The two independent `product_section` rails show different real product data (from
  the seeded catalog) with different background colors, proving per-instance settings
  actually reach the renderer, not just the database.
- The `image_text` block's background is the actual uploaded `MediaAsset` image
  (rendered as a solid-color PNG, matching the synthetic test image byte-for-byte in
  color).
- The `is_active=False` newsletter section's marker text does not appear anywhere in the
  page.
- Header (logo, cart, search, account) and footer (contact, categories, copyright) both
  render intact and unrelated to any of the above changes.
- No Family- or preset-specific code path was involved anywhere in this render — the
  same `render_service`/`section_registry` code that renders every other store rendered
  this demo.

This is architectural proof that the pipeline works end-to-end in a real browser. It is
explicitly **not** V5 visual verification — the demo data and styling are generic and
intentionally not V5-derived (§14).

## 9. Draft vs. Published behavior

Unchanged mechanism (`StorefrontLayout.published_version`/`draft_version`,
`layout_service.publish()`); explicitly extended coverage for the two new pieces:

- `storefront_context_service.build_universal_storefront_context` — used by every public
  route — only ever calls `page_resolution_service.resolve_published_page`, never
  reads `draft_version`. The new `"rows"` key is built from that same resolved
  (Published-only) `render_items` list — there is no separate code path by which a
  Draft-only row or background configuration could leak to `rows` without also leaking
  to `render_items`, which the pre-existing Draft/Publish tests already guard.
  New tests (`RowGridRenderingTests.test_draft_row_configuration_never_reaches_public_page`)
  confirm this explicitly for `row_key`/`row_span`.
- `storefront_builder/views.py::storefront_preview` — Draft-only, staff-gated (existing
  `@staff_required`/`@permission_required(STOREFRONT_LAYOUT_MANAGE)`), unchanged
  authorization. New test (`RowGridPreviewTests.test_preview_shows_row_configured_only_in_draft`)
  confirms a row configured only on the Draft is visible in preview.

## 10. Tenant safety

No new tenant-crossing surface was introduced. `resolve_background_media_url` is called
with the same already-store-scoped `store` parameter every other resolver in
`render_service.py` uses; `group_items_into_rows` is a pure list transformation with no
database access at all. New tests explicitly prove the one genuinely new
data-resolution path (background media) fails closed for a foreign-store reference, all
the way to rendered HTML (`test_foreign_store_media_asset_never_renders_as_background`),
not just at the Python-function level (already covered in Phase 1's
`test_background_media_resolution.py`).

## 11. Error / fail-closed behavior

- Unknown `section_key` → silently skipped (pre-existing, unchanged, still tested).
- `group_items_into_rows` on an empty list → empty list, no error (Phase 1 test, still
  valid).
- A row whose composition is invalid (wrong member count, spans not summing to 12) can
  no longer be *written* through any mutation path (Phase 1 correction pass); if such a
  row somehow still exists in the database, `group_items_into_rows` degrades to grouping
  by literal adjacency rather than raising — a rendering-time convenience, not a second
  validation layer (validation is `row_service.validate_page_row_layout`'s job, already
  enforced at write time).
- Missing/foreign background media → `None`, renders as "no background override" (falls
  through to whatever the section's own template/CSS does by default) — never a broken
  image, never a crash, never another store's file.
- Missing optional data (e.g. an empty `hero_banner` with no `HeroSlide` rows) renders an
  empty content area, not an error — confirmed visually in §8 (the seeded demo's Hero
  block, which had no slides, rendered as blank space, not a broken layout).

## 12. Generic templates/components added

- `apps/storefront_builder/templates/storefront_builder/partials/render_rows.html` (new)
  — the single row-grouping partial described in §4.
- CSS additions to the existing `storefront_builder.css` (`.rsec-row`/`.rsec-row-item`
  grid, `.rsec[data-spacing]`, `.rsec[data-bg-mode]`) — no new CSS file.
- No new section templates were added — every section type used in the runtime-proof
  demo (`hero_banner`, `amazing_offers`, `product_section`, `rich_text`, `faq`,
  `testimonials`, `image_text`, `trust_features`, `category_grid`, `brand_carousel`,
  `newsletter`) already existed at the Phase 1 checkpoint. All of it is intentionally
  generic/neutral — none of the copy, imagery, or color choices are V5-derived.

## 13. Legacy frontend files intentionally untouched

No file under the already-retired Family system was touched or re-examined (there is
none left to touch — confirmed retired at the Phase 1 baseline). No V5 reference file
(`docs/references/beraito-exact-frontend-v5/**`) was copied, adapted, or used as a
template source.

## 14. V5-specific work intentionally NOT performed

No `beraito_renderer.py`, no `v5.html`, no `if preset == "v5"`/`if store == ...`
branching anywhere. The runtime-proof demo (§8) deliberately used generic copy
("ستون A/B/C/D", "متن نمونه", solid-color placeholder imagery) rather than anything
resembling V5's actual content, styling, or composition specifics — the point of this
phase's demo is that the *engine* can compose arbitrary blocks into arbitrary rows, not
that it currently looks like V5. Reproducing V5 through this engine + a V5-specific
configuration is explicitly Phase 3.

## 15. Deferred items

- A Builder UI for actually authoring `row_key`/`row_span` (placing two blocks into a
  row via drag-and-drop or an equivalent control) — still not built, per the explicit
  "no Builder UI work" instruction; the demo in §8 was seeded directly via the ORM.
- Populating `PATTERN_REGISTRY` with real pattern assets, and rendering `mode="pattern"`
  backgrounds — still schema-ready, still inert.
- A Media Picker UI for choosing `background.media_asset_id` from the Builder — still
  not built, same reasoning as Phase 1.
- The Draft-preview iframe's drag-and-drop JS (`preview.html`) operates on
  `[data-section-id]` elements assuming they are direct children of
  `.sfb-preview-sections`; wrapping a multi-member row in `.rsec-row` nests them one
  level deeper. This has no live effect today (no UI can create a multi-member row, so
  Draft preview never actually renders one outside of this phase's own manual ORM-seeded
  test), but is a known latent interaction gap for whenever row-authoring UI is built —
  recorded here rather than fixed now, since fixing it is Builder-UI interaction design,
  explicitly out of scope for this phase.
- Any V5 Preset, V5-specific templates, or V5 visual reproduction — explicitly Phase 3.

## 16. Risks / unresolved issues

None identified that require an Owner decision. The one latent interaction gap noted in
§15 (Draft-preview drag-and-drop nesting) is flagged for future awareness, not raised as
blocking, since it cannot be reached through any currently-shipped UI.
