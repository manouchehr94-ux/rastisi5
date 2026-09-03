# RastiSi Storefront — Unified Architecture Implementation Roadmap

**Date:** 2026-09-03
**Branch:** `feature/storefront-builder-r4`
**Base commit:** `e00f4f0ba16db1baa3134a22108a770cfb9a392d`
**Type:** Dependency-aware master roadmap (planning only; no implementation).

**Authoritative sources (precedence):**
1. `docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-unified-architecture-design.md` — MASTER architecture.
2. `docs/audits/2026-09-03-storefront-unified-architecture-gap-audit.md` — current implementation reality (61-row Capability Gap Matrix: COMPLETE 28 / PARTIAL 25 / MISSING 5 / LEGACY_CONFLICT 2 / UNKNOWN 1 / NOT_APPLICABLE 0).
3. `docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-product-architecture.md` — approved UX/product decisions.
4. `docs/superpowers/specs/2026-09-01-storefront-design-engine-50-templates-design.md` — component/template architecture.
5. `docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md` — prior invariants unless superseded.

**Guiding principle:** *Power in the architecture, simplicity in the UI.* Evolve the existing R4 foundation; do not rewrite working systems. Each phase closes specific Gap-Audit rows and satisfies specific Unified acceptance criteria (referenced as "AC #n" against the Unified doc's §61 list).

This roadmap is a dependency map, not a line-by-line coding plan. Only **Phase 1** has a detailed executable plan today (`docs/superpowers/plans/2026-09-03-template-switch-preservation-implementation-plan.md`). Later phases receive detailed plans when their predecessors complete, so plans are never written against code that earlier phases will change.

---

## Architecture Assets We Must Preserve

Later phases MUST build upon these mature subsystems and MUST NOT rewrite them absent concrete evidence of necessity:

- **`apps/storefront_builder/storefront_appearance/`** — the Store Appearance engine: `contracts.py`, `families.py` (10 families), `adapters.py` (synthesizes 119 `ComponentDefinition`s from existing registries — reuse, never duplicate), `registry.py` (`COMPONENT_REGISTRY`), `validation.py` (server-side security boundary: forbidden markers, closed `ALLOWED_SETTINGS_BY_FAMILY`, registered-key + family enforcement, bounded JSON), `compatibility.py`, `persistence.py` (`appearance_config["store_appearance"]`), `rendering.py`, `inventory.py` (78 advertised keys, `recipe_signature`, coverage).
- **`apps/storefront_builder/services/r4_mutation_service.py`** — the single mutation boundary: `apply_mutation` (`@transaction.atomic`), `_lock_active_draft` (store-scoped `select_for_update` + `base_revision` stale-write → `R4StaleRevision`/409), the explicit `_dispatch_mutation` allowlist, `apply_history_command` (undo/redo), `publish_draft`. New behavior must extend this contract, not add a parallel endpoint.
- **`apps/storefront_builder/services/render_service.py`** — `build_page_render_items` / `build_render_items`; the single renderer used by both Preview and Public. No second renderer may be introduced.
- **`apps/storefront_builder/services/layout_service.py`** — Draft/Published/Archived version lifecycle: `get_or_create_draft`, `publish`, `restore_version`, `list_versions`, `checkpoint_draft_before_replacement`, `_clone_version_content`.
- **`apps/storefront_builder/services/edit_history_service.py`** — `snapshot_draft`/`restore_draft_state` (serialize full editable state incl. section-scoped Hero/Banner/Story media via `_SCOPED_MEDIA`), `record_change`, `undo`, `redo`, `history_state`.
- **`apps/storefront_builder/services/preset_service.py`** — `apply_preset`, `apply_preset_with_checkpoint`, the baseline/reset family (`reset_storefront_to_baseline`, `apply_baseline_snapshot`, `reset_page_to_baseline`, `reset_section_to_baseline`, `_draft_already_matches_preset`).
- **Registries:** `appearance_registry.py`, `global_region_registry.py`, `layout_preset_registry.py`, `section_registry.py`, `variant_contract.py`, `palette_pack_64.py`.
- **50 Ready Template DNA:** `a8_ready_templates.py` + `storefront_appearance/inventory.py`.
- **Header/Footer/Mega Menu design assets:** `templates/storefront_builder/partials/global_header/*` (21 partials, incl. `_shared/category_mega_menu.html`, `_shared/category_link_row.html`) and `.../global_footer/*` (25 partials). Adapt, do not rebuild.
- **R4 preview↔editor message bridge:** `static/storefront_builder/r4_editor.js` (listens for `sfb:selectSection`/`sfb:openSectionSettings`/`sfb:sectionCommand`/`sfb:blockCommand`) + `templates/storefront_builder/preview.html`. Extend for deeper editing; do not reintroduce the legacy shell.
- **Demo infrastructure:** `apps/stores/management/commands/seed_ready_template_fashion_demo.py`, `refresh_rasti_mode_demo_visuals.py`, `apps/storefront_builder/management/commands/capture_ready_template_previews.py`, `tools/storefront_builder_r4_qa/run.mjs`.
- **Version/data model:** `StorefrontLayout` (incl. `r4_editor_enabled`), `StorefrontLayoutVersion` (`edit_revision`, `template_provenance`, `template_baseline_snapshot`), `StorefrontPage`, `StorefrontSection` (`settings`, `template_slot_key`, `is_locked`, reverse `hero_slides`/`banners`/`story_items`), `StorefrontContainer`/`StorefrontCell`.
- **Content-vs-Commerce boundary:** the Builder is read-only over catalog/commerce truth (price/stock/SKU/ProductImage/orders/promotions). Every phase keeps this invariant.

---

## Phase Ordering — Dependency Verification

The Gap Audit's recommended order was verified against the repository. One boundary adjustment was made:

- **Adjustment:** Phase 7 (Commerce-owned timed offers) is placed as a Phase-5-dependent branch alongside Phase 6, and Phase 8 (library breadth + template diversity) is gated behind Phase 3 (component selection) rather than behind Phase 7, because template diversity/coverage work consumes the component-selection and Mega-Menu-registration outputs of Phase 3, and has no dependency on the Content Hub (Phase 6) or timed offers (Phase 7). This matches the actual data dependencies: `a8_ready_templates.py` and `storefront_appearance/inventory.py` depend on `COMPONENT_REGISTRY` breadth (Phase 3), not on Content Hub or Commerce timed offers.
- All other boundaries match the audit's recommended order.

---

## Phase 1 — Safe Ready Template Switching / Merchant Preservation

**Goal:** Make selecting a different Ready Template change Design DNA/defaults **without silently destroying** merchant-authored content, section-local settings, custom composition, or section-scoped Hero/Banner/Story rows. Preserve merchant customization by default; make "reset structure to template" an explicit, confirmation-gated action; make the switch recoverable through the existing history model.

**Why this phase comes first:** Gap-Audit row 21 is a `LEGACY_CONFLICT` classified CRITICAL — a direct merchant-data-loss defect (`preset_service.apply_preset` runs `page.sections.all().delete()` + rebuild from recipe; section-scoped media CASCADE-delete via `apps/content/models.py:414`; R4 `appearance.template.apply` calls raw `apply_preset` with no checkpoint). Later phases (component selection, direct editing, Content Hub) all build UX on top of the composition model; correcting the composition/preservation semantics first prevents building on a destructive foundation.

**Existing code to reuse:** `preset_service.apply_preset` / `apply_preset_with_checkpoint` / `_draft_already_matches_preset` / baseline-reset family; `layout_service.checkpoint_draft_before_replacement` / `restore_version`; `edit_history_service.snapshot_draft` / `restore_draft_state` (already serializes section-scoped media and the typed `store_appearance` manifest as part of `appearance_config`); `r4_mutation_service.apply_mutation` + `_apply_appearance_template` + `_sync_manifest_from_live_selectors`; `storefront_appearance.validation.validate_store_appearance_manifest` (pure projection of the preset's authored typed manifest — reused, never duplicated); the preset's authored `store_appearance` manifest (`LayoutPresetDefinition.store_appearance`); `template_provenance` / `template_baseline_snapshot` / `template_slot_key`.

**Major gaps it closes:** Gap-Audit rows 21 (LEGACY_CONFLICT → COMPLETE for preservation), and hardens rows 19/20; resolves the R4-vs-legacy checkpoint inconsistency.

**Unified acceptance criteria satisfied:** AC #7 (template switch preserves merchant content/catalog/business truth), AC #8 (custom Home structure preserved by default; reset-to-template-structure is explicit), and the Decision Register items 6–7. Also honors AC #21 (Public only on Publish), AC #26 (atomic validated Draft op with stale-write protection).

**Dependencies:** None (foundational).

**Non-goals:** No new component-selection UI; no Direct Preview Editing depth; no Content Hub; no Design Lab; no new renderer; no schema migration unless proven necessary (§J of the detailed plan).

**Main risk:** Semantically dishonest `template_baseline_snapshot` — after a preservation-mode switch the snapshot must truthfully describe the *new template's authored baseline* (so explicit reset works), not a relabeled copy of the merchant's preserved structure. The detailed plan makes this the central design decision.

**Verification gate:** the 25-test RED/GREEN matrix in the detailed Phase 1 plan; `python manage.py check`; `python manage.py makemigrations --check --dry-run`; neighboring regression on `test_preset_service`, `test_acceptance_batch1/2/3`, `test_u7_ready_template_baseline`, `test_r4_store_appearance_mutations`, `test_r4_vertical_slice`, `test_appearance`.

**Completion condition:** Ready Template switching preserves merchant structure/content/section-scoped media by default on both the R4 mutation path and the legacy view path; explicit reset-to-template-structure remains available and confirmation-gated; the switch is recoverable via the existing version-history/undo model; all 50 Ready Templates still validate; the baseline-snapshot invariant holds.

---

## Phase 2 — Deep Direct Preview Editing in R4

**Goal:** Extend the existing R4 preview bridge from section-level click-to-edit to the full approved experience: element/child edit identity, click-to-edit for header/footer/logo/badge/entity, the ~65–70% context-aware editing panel, and parent/child breadcrumb/tab navigation — all driven through `r4_mutation_service`.

**Why this phase comes here:** Gap-Audit rows 31/32/33 (PARTIAL/MISSING) — the primary approved experience. It comes after Phase 1 because element-level editing operates on the section composition Phase 1 makes safe, and because the "reset to parent/template" affordances surfaced in the editor depend on Phase 1's preservation semantics.

**Existing code to reuse:** `r4_editor.js` message listener (already handles `sfb:selectSection`/`sfb:openSectionSettings`); `preview.html` bridge (already emits section/header/footer/entity messages in the legacy path — the emit side is reusable); `r4_views.storefront_r4_section_inspector` + the tabbed `section_inspector.html`; `render_service` element identity attributes.

**Major gaps it closes:** rows 31, 32, 33; contributes to row 34 (relevant-only controls) by extending schema coverage as needed.

**Unified acceptance criteria satisfied:** AC #9 (click the visible element opens the correct context), AC #10 (immediate live preview, no per-edit Apply), AC #11 (child selected precisely, parent reachable), AC #12 (editor tabs show only capability-relevant controls), AC #17 (parent/child tabbed/contextual).

**Dependencies:** Phase 1.

**Non-goals:** No component-family gallery selection (Phase 3); no Content Hub; no new renderer or `srcdoc`; no arbitrary HTML/CSS/JS.

**Main risk:** Element identity leaking engine internals to merchants (section=None, registry fallback). Provenance messaging is deferred to Phase 4, so Phase 2 must present a coherent "edit what you see" flow without exposing fallback concepts.

**Verification gate:** targeted R4 inspector/bridge tests (`test_r4_inspector`, `test_views`, `test_builder_iframe_navigation_guard`), the `tools/storefront_builder_r4_qa/run.mjs` Playwright smoke, `python manage.py check`.

**Completion condition:** clicking a visible element (section, child element, header, footer, logo, badge) in the R4 preview opens the correct contextual editor at ~65–70% width with parent/child navigation; edits autosave and reflect immediately; Public unchanged until Publish.

---

## Phase 3 — Component Selection UX + Mega Menu Registration/Reuse

**Goal:** Expose the already-built typed component-selection engine to merchants (galleries for header/hero/card/product_view/layout/badge/bottom_nav via `appearance.component.update` / `appearance.manifest.apply`), and register the existing live Mega Menu design as a selectable `mega_menu` family (adapt `_shared/category_mega_menu.html`; do not rebuild).

**Why this phase comes here:** rows 25, 26, 27, 29, 50 (PARTIAL) and the UX-gap that the built engine is unreachable. It follows Phase 2 because component pickers are opened from the same contextual editor surface Phase 2 builds, and it feeds Phase 8 (template diversity/coverage depends on the registered/selectable component set).

**Existing code to reuse:** `storefront_appearance` engine + `appearance.component.update`/`appearance.manifest.apply` mutations (fully built, tested; only UI wiring missing); `global_region_registry`; header/footer/mega-menu partials; `compatibility.py` for Header↔Mega-Menu validation (row 13).

**Major gaps it closes:** rows 25, 26, 27, 29, 50; hardens row 13.

**Unified acceptance criteria satisfied:** AC #3 (change one component mutates only that component), AC #14 (Header/Footer/Mega Menu model-first and protected), AC #24 (Header/Footer chosen from ready models), AC #25 (limited protected customization), AC #37 (coherent Button/Badge/Tag/Ribbon language surfaced).

**Dependencies:** Phase 2 (contextual editor surface); Phase 1 (single-component change must not trigger destructive structure rebuild — guaranteed by Phase 1's independent-mutation rule).

**Non-goals:** No free-form Header/Footer/Mega-Menu builder; no per-child typography or arbitrary spacing; no new families beyond registering the existing Mega Menu design.

**Main risk:** Over-exposing customization on protected regions (Header/Footer), violating AC #25. Guard via the existing narrow patch allowlists (`_apply_header_update`/`_apply_footer_update`) and typed component keys only.

**Verification gate:** `test_r4_store_appearance_mutations`, `test_r4_store_appearance_compatibility`, `test_u2a_global_header_system`, `test_u2b_global_footer_system`, `test_r4_store_appearance_registry`, Playwright smoke.

**Completion condition:** merchants can browse and select header/hero/card/product_view/layout/badge/bottom_nav/mega_menu from galleries; a single-component change changes only that component; Header/Footer/Mega Menu remain protected; Mega Menu is a registered selectable family reusing the existing partial.

---

## Phase 4 — Full Design Inheritance / Overrides / Provenance UX

**Goal:** Extend the sparse-override model beyond the current typography-only slice to the full Template DNA → Global Design → Section → Element → Local override chain, with reset-to-parent/template at field/element granularity and provenance messaging ("using global setting", "using template", "make specific for this section").

**Why this phase comes here:** rows 35 (MISSING), 36/37/38 (PARTIAL). It follows Phase 3 because overrides apply to the components/sections whose selection UX Phase 3 delivers, and because provenance messaging resolves the "global fallback" concern that Phase 2's element editing exposes.

**Existing code to reuse:** `services/section_appearance_service.py` (typography-override slice to generalize); `settings_schema.py` (`validate_appearance_overrides`); `appearance_registry` token system; the baseline/reset machinery corrected in Phase 1.

**Major gaps it closes:** rows 35, 36, 37, 38.

**Unified acceptance criteria satisfied:** AC #13 (child overrides survive parent change; clear reset), AC #16 (template defaults with per-section/element local override), AC #18 (parent change does not clear child override), AC #20 (global coherence default, local override where capable), AC #38 (advanced typed, never arbitrary CSS). Addresses the §17.3 provenance rule.

**Dependencies:** Phase 3.

**Non-goals:** No arbitrary CSS escape hatch; no per-route page builder; no override capabilities beyond each component's declared typed schema.

**Main risk:** Override storage sprawl / inheritance ambiguity. Keep overrides sparse and typed; reuse the sparse-override map pattern already in `section_appearance_service`.

**Verification gate:** `test_r4_appearance_overrides`, `test_appearance`, `test_shared_capabilities`, `test_u9_advanced_settings`, `python manage.py check`.

**Completion condition:** the full inheritance chain is representable and editable; explicit child overrides survive parent/global changes; reset-to-parent/template works at field and element level; provenance is shown in plain language without exposing engine internals.

---

## Phase 5 — R4 Shell Consolidation / Legacy Builder Retirement

**Goal:** Bring R4 to parity for supported merchant flows, flip the `StorefrontLayout.r4_editor_enabled` default, and retire the legacy R2/R3 editor shell in a separate cleanup step.

**Why this phase comes here:** row 1 (PARTIAL). Retirement is only safe after Phases 2–4 deliver the R4 experience that currently exists more fully on the legacy shell. It is the pivot before the two independent branches (Phase 6, Phase 7).

**Existing code to reuse:** R4 shell, routes, and mutation contract; the parity gates defined in `docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md` Part XI.

**Major gaps it closes:** row 1; removes the dual-shell architectural tension.

**Unified acceptance criteria satisfied:** AC #1 (one Store Appearance subsystem / one Builder shell), AC #39 (Public rendering keeps the normal R4 Publish lifecycle).

**Dependencies:** Phases 2, 3, 4.

**Non-goals:** No public storefront rendering changes; no removal of the shared renderer or preview bridge; no big-bang deletion while R4 is still stabilizing.

**Main risk:** Removing legacy code paths still referenced by production stores. Gate the default flip behind parity evidence; retire code in a dedicated follow-up.

**Verification gate:** full R4 flow Playwright smoke; `test_views`; `test_r3_*` (confirm retired paths); `python manage.py check`; broad regression checkpoint.

**Completion condition:** R4 is the default editor, parity gates pass, legacy shell code is removed without changing public rendering.

---

## Phase 6 — Store Content Hub

**Goal:** Deliver the centralized merchant-facing Content Hub over the existing content models (store identity, logo/favicon, heroes/sliders, banners, categories, brands, collections, promotional content, stories, blog/editorial, newsletter, contact/trust, media reuse) — same data and contracts as Direct Editing, not a second system.

**Why this phase comes here:** row 40 (MISSING). It is a Phase-5-dependent branch (parallel to Phase 7): it consumes the consolidated single shell and the same content data the Direct Editor edits.

**Existing code to reuse:** `media_views.py` (content-model writes for Hero/Banner/Story/MediaAsset); content models in `apps/content/`; `resource_source.py`; the R4 shell.

**Major gaps it closes:** row 40; hardens rows 42 (product-image shortcut), 46 (unified Media Picker).

**Unified acceptance criteria satisfied:** AC #10 (Direct Editor and Content Hub share one source of truth), §17.2 (Content Hub is a central management view over the same data).

**Dependencies:** Phase 5.

**Non-goals:** Not Django admin; must not move domain ownership (Catalog stays source of truth for products/categories/brands); no new renderer.

**Main risk:** Duplicating catalog ownership. Content Hub edits only presentation/content or provides shortcuts to source-of-truth management.

**Verification gate:** `test_media_asset_lifecycle`, `test_media_views`, `test_media_write_path`, new Content Hub tests, `python manage.py check`.

**Completion condition:** a single merchant-facing Content Hub manages storefront content over the same data/contracts as Direct Editing, with a unified Media Picker and a product-image "manage in catalog" shortcut.

---

## Phase 7 — Commerce-owned Timed Offers + Campaign Presentation

**Goal:** Move timed-offer truth (start/end/validity) into the Commerce/Promotion domain and make Appearance present it only; wire festival/campaign presentation to real promotion truth.

**Why this phase comes here:** row 56 (LEGACY_CONFLICT), row 55 (PARTIAL). It is a Phase-5-dependent branch (parallel to Phase 6) because it touches Commerce plus the campaign-presentation sections, independent of the Content Hub.

**Existing code to reuse:** `apps/catalog/models.py` (`Product.discount_percent`, `final_price`); `section_registry.py` `amazing_offers` presentation; `section_data_service.py` (read-only product resolution); the appearance engine for `campaign_band`/`sale` presentation.

**Major gaps it closes:** rows 55, 56; contributes to demo completeness (row 53).

**Unified acceptance criteria satisfied:** AC #8-decision (Builder controls campaign presentation; Commerce owns discount truth), AC #11-#12 of the Design-Engine doc (timed-offer truth in Commerce; expiry behavior), AC #20 (timed-offer truth in Commerce, appearance presents).

**Dependencies:** Phase 5.

**Non-goals:** No fake discounts generated in Appearance; the Builder still never writes price/stock/SKU (Content-vs-Commerce boundary preserved).

**Main risk:** A schema addition in Commerce (`sale_start`/`sale_end` or promotion linkage) — justify against existing fields, provide migration + tests, preserve backward compatibility.

**Verification gate:** new Commerce timed-offer tests; `section_registry`/`section_data_service` tests; migration check; `python manage.py check`.

**Completion condition:** timed-offer validity lives in Commerce; appearance renders countdown/active/expired states from Commerce truth; on expiry the countdown disappears and normal commerce state renders; the Builder writes no commerce truth.

---

## Phase 8 — Component Library Breadth + 50-Template Diversity/Coverage

**Goal:** Grow under-target families (Mega Menu, Motion, Badge/Tag/Ribbon) and raise real template diversity (fonts, compositions) and component coverage so the 50 Ready Templates pass diversity/coverage gates on a broader library, and use currently-unused advertised components.

**Why this phase comes here:** rows 17, 18, 26–30 (PARTIAL). It depends on Phase 3 (registered/selectable component set + Mega Menu family) and Phase 7 (timed-offer presentations to include in templates), but not on Content Hub.

**Existing code to reuse:** `a8_ready_templates.py`, `storefront_appearance/inventory.py` (`recipe_signature`, coverage), the header/footer/mega-menu partials, `compatibility.py`.

**Major gaps it closes:** rows 17, 18, 26, 27, 28, 29, 30.

**Unified acceptance criteria satisfied:** AC #17 (50 pass coverage/responsive/parity/diversity gates), AC #18 (palette/font-only variation does not qualify), AC #34-#35 (diversity/coverage gates), AC #37 (coherent Button/Badge/Tag/Ribbon).

**Dependencies:** Phase 3; Phase 7 (for timed-offer template variants).

**Non-goals:** No 51st+ template subsystem; no per-template codebase; no arbitrary component families outside the typed contracts.

**Main risk:** Superficial "new" templates that only change palette/font. Enforce the diversity gate (`recipe_signature`) and coverage matrix.

**Verification gate:** `test_a8_template_diversity`, `test_a8_component_coverage`, `test_a8_component_library`, `test_a8_ready_template_contracts`, `test_u10_ready_template_catalog`.

**Completion condition:** library families approach targets; all 50 templates pass diversity and coverage gates on the broader library; unused advertised components are used or explicitly excepted.

---

## Phase 9 — Product Detail Guided Customization + Design Lab + Full QA/Release Closure

**Goal:** Deliver Product Detail guided customization (curated layouts + controlled-area controls), the Design Lab (transient state over the same engine/renderer), and full QA/release closure (Desktop/Mobile/RTL/a11y evidence for all 50 templates; browser/responsive coverage).

**Why this phase comes here:** rows 48, 51 (MISSING), plus QA rows (16 evidence gaps, row 60 Lab parity). Product Detail and Design Lab depend on the full component/override/selection stack (Phases 3–4) and the consolidated shell (Phase 5); QA closure depends on the broadened library (Phase 8).

**Existing code to reuse:** `capture_ready_template_previews.py` (real Playwright desktop+mobile), `tools/storefront_builder_r4_qa/run.mjs`, the shared renderer, the appearance engine (Design Lab must reuse it — no second renderer/persistence), Product Detail sections in `section_registry.py`.

**Major gaps it closes:** rows 48, 51, 60; closes the QA-evidence gaps (visual QA for all 50; RTL/a11y/mobile).

**Unified acceptance criteria satisfied:** AC #16 (Product Detail controlled layout, not free-form), AC #22-#23 (Home free / Product Detail guided / others theme-driven), AC #25-#27 (Design Lab transient, shared renderer, apply-to-Draft atomic, no `srcdoc`/independent renderer), AC #33-#34 (Demo canonical fixture; all 50 pass gates), and QA §56-§58.

**Dependencies:** Phases 3, 4, 5, 8.

**Non-goals:** No second renderer/persistence for Design Lab; no free-form Product Detail builder; no arbitrary code.

**Main risk:** Design Lab drifting into a second renderer/persistence model. Enforce transient typed state + shared renderer + atomic apply-to-Draft.

**Verification gate:** all 50 templates captured Desktop+Mobile; RTL/a11y/responsive suites; Design Lab apply-to-Draft tests; full regression checkpoint; `python manage.py check`.

**Completion condition:** Product Detail offers curated layouts + controlled customization; Design Lab explores the real engine transiently and applies atomically to Draft; all 50 templates have committed Desktop+Mobile QA evidence and pass renderer-parity/RTL/responsive gates.

---

## Roadmap Dependency Graph

```
Phase 1  Safe Ready Template Switching / Merchant Preservation
   ↓
Phase 2  Deep Direct Preview Editing in R4
   ↓
Phase 3  Component Selection UX + Mega Menu registration/reuse
   ↓
Phase 4  Full Design Inheritance / Overrides / Provenance UX
   ↓
Phase 5  R4 Shell Consolidation / Legacy Builder retirement
   ├── Phase 6  Store Content Hub
   └── Phase 7  Commerce-owned Timed Offers + Campaign presentation
            ↓
Phase 8  Component Library breadth + 50-template diversity/coverage
   (Phase 8 also depends on Phase 3)
            ↓
Phase 9  Product Detail guided customization + Design Lab + full QA/release closure
   (Phase 9 also depends on Phases 4 and 5)
```

Notes on the graph:
- Phase 8 depends on **both** Phase 7 (timed-offer template variants) and Phase 3 (registered/selectable component set). The vertical edge from Phase 7 is the critical path; the Phase 3 edge is shown in the phase's Dependencies.
- Phase 9 depends on **Phase 8** (broadened library for QA closure) and additionally on **Phases 4 and 5** (override stack + consolidated shell) as stated in its Dependencies.
- Phases 6 and 7 are independent of each other and may proceed in parallel once Phase 5 completes.

---

## Cross-Phase Invariants (every phase must uphold)

1. One Builder shell, one shared Draft mutation contract (`r4_mutation_service`), one shared renderer (`render_service`) for Preview and Public.
2. Public changes only on Publish; Draft is autosaved; stale writes rejected via `base_revision`.
3. No arbitrary merchant HTML/CSS/JS, raw executable JSON, arbitrary renderer name or template path; only registered, typed, tenant-scoped values (`storefront_appearance/validation.py`).
4. Content-vs-Commerce boundary: the Builder never mutates price/stock/SKU/ProductImage/orders/promotion truth.
5. Responsive belongs to components; no separate mobile builder.
6. No parallel registry stack, no second Draft lifecycle, no second history system, no per-template Builder, no demo-only renderer.
7. Every phase closes specific Gap-Audit rows and satisfies specific Unified acceptance criteria, verified by tests before completion.
