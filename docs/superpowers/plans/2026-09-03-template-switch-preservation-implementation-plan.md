# Safe Ready Template Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Ready Template switching so that selecting a different template changes Design DNA/defaults **without silently destroying** merchant-authored content, section-local settings, custom composition, or section-scoped Hero/Banner/Story rows. Preserve merchant customization by default; keep replacing page structure available only as an **explicit, confirmation-gated** action; and make the switch recoverable through the existing history model. The R4 mutation path (`appearance.template.apply`) and the legacy merchant view path must have consistent, preserving semantics.

**Architecture:** Evolve the existing R4 Storefront Builder. Introduce **preservation-mode** template application as an option on `preset_service.apply_preset`, driven from both entry points, without a new renderer, a new Draft lifecycle, a new history system, or (unless proven necessary) a schema migration. Reuse `template_provenance`, `template_baseline_snapshot`, `template_slot_key`, `edit_history_service`, `layout_service.checkpoint_draft_before_replacement`, and the existing baseline-reset family.

**Tech Stack:** Django 5.2.x, Python 3.12.x, existing R4 Storefront Builder services and test suite.

**Spec:** docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-unified-architecture-design.md

**Audit:** docs/audits/2026-09-03-storefront-unified-architecture-gap-audit.md

---

## Global Constraints

Exact constraints from the Master Architecture that every task must honor:

1. **One Builder shell, one shared Draft mutation contract, one Preview/Public renderer.** Template switching must remain a `preset_service` operation invoked through the existing `r4_mutation_service.apply_mutation` contract and the existing legacy view; no second write endpoint, no second renderer, no second Draft lifecycle.
2. **Public changes only through Publish.** Template switching mutates only the active Draft; the published version is never touched (`layout_service.publish` is the only path to Public).
3. **Stale writes are rejected.** All R4 mutations flow through `_lock_active_draft` (`base_revision` compare → `R4StaleRevision`/409).
4. **No arbitrary HTML/CSS/JS, raw executable JSON, arbitrary renderer name, or template path.** Template DNA is typed and registered only (`storefront_appearance/validation.py`, `layout_preset_registry`).
5. **Content-vs-Commerce boundary.** This work never writes catalog/commerce truth (price/stock/SKU/ProductImage/orders/promotions). It only reorganizes/preserves `StorefrontSection` rows, `StorefrontSection.settings`, section-scoped content FKs, and Draft-level appearance/header/footer config.
6. **Template DNA is a default, not a permanent lock.** Applying a template sets Design DNA; merchant overrides remain possible and, per AC #7/#8, are preserved by default.
7. **Header/Footer/Mega Menu remain protected.** Their variant selection is Design DNA and may change on a template switch; merchant-supported local overrides on them are preserved unless the merchant explicitly resets to template defaults.
8. **Independent-mutation rule.** Changing one component changes only that component; only an explicit whole-template/preset operation changes composition.
9. **Fail closed.** Invalid/stale/unknown template or version leaves the Draft entirely unchanged (validate-before-write is already the `apply_preset` contract).
10. **Baseline-snapshot truthfulness invariant.** `template_baseline_snapshot` must always be a truthful immutable representation of the actual Template baseline (what the recipe authored), never a relabeled copy of the merchant's preserved storefront. See Design Decision 10.

---

## Phase 1 Design Decisions

All answers are grounded in the current code.

**1. How will we detect whether the current storefront is still an untouched template baseline versus merchant-customized?**
This decision gates a *destructive* structure replacement, so it must be **fail-safe: automatic destructive structure application is allowed only when the system can positively prove the storefront is pristine; if proof is incomplete or ambiguous, the storefront is treated as CUSTOMIZED and preserved.** The existing `preset_service._draft_already_matches_preset(draft, preset)` (`preset_service.py:616-657`) is useful *conceptual* evidence but is **not sufficient to reuse as-is**: it compares `appearance_config`, `header_config`, `footer_config`, and per-section `section_key`/`settings`/`row_key`/`row_span`/`template_slot_key`, but it does **not** compare `StorefrontContainer.settings` or `StorefrontCell`/block placement. Modern Drafts carry Container/Cell composition that a merchant can change without altering any section field; a helper blind to Container/Cell state could wrongly declare such a Draft pristine and then destroy the merchant's layout.

Therefore Phase 1 defines a **new, stricter** predicate `draft_matches_own_baseline(draft) -> bool` that returns `True` only when ALL of the following are proven against the Draft's **own** stored `template_baseline_snapshot` (identity taken from `template_provenance.template.key/version`):
- `template_provenance.template.key/version` is present and equals `template_baseline_snapshot.template_key/template_version`;
- `appearance_config` equals `snapshot["appearance"]`;
- `header_config` equals `snapshot["header_config"]` where the snapshot records one, and `footer_config` equals `snapshot["footer_config"]` where the snapshot records one;
- for every page the snapshot covers: equal section count; and for each ordered section, equal `section_key`, `settings`, `row_key`, `row_span`, and `template_slot_key` (any merchant-created section has `template_slot_key == ""` and thus cannot match a baseline slot → `False`);
- for every page the snapshot covers: the current `StorefrontContainer` ordered list equals the snapshot's `container_settings` (count and per-container `settings`), reconstructed from `snapshot["pages"][page]` entries via the existing `_container_settings_from_snapshot_sections` helper; and the current `StorefrontCell`/block placement of each section matches the baseline placement the snapshot implies (section→cell/container membership and `cell_order`).

If the stored snapshot does not carry enough information to prove Container/Cell state (any legacy/partial/absent snapshot), the predicate returns `False` — **safe-preserve**. This is the single source of truth for "pristine vs customized"; it adds no persisted state and no second tracking system. See Design Decision 13 for the exact Container/Cell comparison and Task 2 for the RED tests.

**2. What exact data is considered Design DNA?**
The Draft-level appearance/global config and global-region variant selections: `appearance_config` (palette_slug, font, type_scale, motion, button_style, radius, density, content_width, and the typed `store_appearance` manifest under `appearance_config["store_appearance"]`), `header_config["header_variant"]`, `footer_config["footer_variant"]`, and `footer_config[<mobile_nav variant key>]` (`global_region_registry.GLOBAL_MOBILE_NAV_REGION.variant_setting_key`). These are exactly the fields `apply_preset` overlays from `preset.appearance`, `preset.header`, `preset.footer` and `default_palette_slug`.

**3. What exact data is considered merchant-owned state?**
Everything in the page composition and section-local storage: the set/order of `StorefrontSection` rows per page; each section's `settings` JSON (title, subtitle, `body_html`, `data_source`, `product_ids`, `brand_ids`, `source_id`, `item_limit`, `display_mode`, `card`, `background`, `motion`, `spacing`, `appearance_overrides`, serialized `resource_source`); `StorefrontContainer`/`StorefrontCell` composition; merchant-created sections (`template_slot_key == ""`); duplicated sections; and section-scoped content rows (`HeroSlide`/`PromotionalBanner`/`StoryRailItem` with `section_id` set — reverse relations `hero_slides`/`banners`/`story_items`). Merchant-supported local overrides on Header/Footer config are also merchant-owned (Design Decision 7).

**4. When switching templates on a customized storefront, what is updated?**
Only Design DNA (Decision 2): `appearance_config` overlay from the new preset (palette per the existing Ready-Template rule, font, motion, layout/design defaults, the typed manifest sync), `header_config["header_variant"]`, `footer_config` variant + mobile-nav reset-then-overlay — exactly the "section (1)" appearance/header/footer overlay block of `apply_preset` (`preset_service.py:305-370`). `template_provenance` is set to the new template (Decision 9). `template_baseline_snapshot` is set to the new template's **authored** baseline (Decision 10).

**5. What remains untouched?**
The entire page composition write block of `apply_preset` (`preset_service.py:445-460`: `page.containers.all().delete()`, `page.sections.all().delete()`, `bulk_create(rows)`, container rebuild) is **skipped** in preservation mode. All `StorefrontSection` rows, their `settings`, `StorefrontContainer`/`StorefrontCell` composition, merchant-created/duplicated/reordered sections, and section-scoped Hero/Banner/Story rows remain exactly as they were. Independent domain records (Product/ProductImage/Category/Brand/Collection/MediaAsset/store-global content) are never referenced by `preset_service` and remain untouched (already true today).

**6. How are section-scoped Hero/Banner/Story rows preserved?**
By not deleting their owning `StorefrontSection`. Today they are lost only because `page.sections.all().delete()` cascades them (`apps/content/models.py:414-415`, `on_delete=models.CASCADE`; `_SCOPED_MEDIA` in `edit_history_service.py:39-42`). Preservation mode skips that delete, so the CASCADE never fires and the rows survive with their `section_id` intact. No change to the content models or their FK is made.

**7. How are explicit Header/Footer overrides handled?**
The new preset's `header`/`footer` overlays are applied as Design DNA (they change the variant). Merchant-supported local overrides that the preset overlay does not set are preserved because `apply_preset` overlays with `{**base_config, **overlay}` (`_validate_header_overlay`/`_validate_footer_overlay`, `preset_service.py:101-112`) — only keys the preset explicitly authors are replaced; other keys the merchant set persist. The existing mobile-nav reset-then-overlay behavior for Ready Templates (`preset_service.py:359-370`) is retained unchanged. This satisfies AC #14/#24/#25: variant changes as DNA; protected local settings survive unless an explicit reset-to-template is chosen.

**8. Does R4 template switching need a checkpoint/version snapshot in addition to edit_history? Why?**
**For a normal (non-destructive, preservation-mode) template switch on the R4 mutation path: No — the existing single-Draft edit-history entry is sufficient, and a durable checkpoint must NOT be created there.** Evidence: `apply_mutation` (`r4_mutation_service.py:591-611`) locks exactly one active Draft via `_lock_active_draft`, takes a **complete** `edit_history_service.snapshot_draft` `before_state` (which captures `header_config`, `footer_config`, `appearance_config`, `template_provenance`, `template_baseline_snapshot`, sections, section settings, containers, cells, and section-scoped `HeroSlide`/`PromotionalBanner`/`StoryRailItem` — `edit_history_service.py:124-145, 39-42`), dispatches the mutation on that same locked Draft, records the before/after history entry, and increments `edit_revision` on that same Draft. `layout_service.checkpoint_draft_before_replacement` (`layout_service.py:945-966`) does something incompatible inside that window: it **creates a new `StorefrontLayoutVersion`, `ARCHIVED`s the current Draft, and repoints `layout.draft_version`**. Calling it from `_apply_appearance_template` would archive the very Draft `apply_mutation` locked/snapshotted and would leave `apply_mutation` incrementing `edit_revision` on an archived, no-longer-active row — corrupting the single-locked-Draft contract and the stale-write model. So a normal switch is exactly one atomic R4 mutation → one edit-history entry → **Undo restores the full pre-switch state** (design DNA + merchant structure + section-scoped media), because `snapshot_draft`/`restore_draft_state` already round-trip all of it.

**A durable archived-version checkpoint remains appropriate only for the EXPLICIT DESTRUCTIVE "reset structure to template" operation** (and the legacy view's explicit apply/reset), which run **outside** `apply_mutation` through `reset_storefront_with_checkpoint`/`reset_page_with_checkpoint`/`apply_preset_with_checkpoint`. Those functions legitimately create the new-draft-and-archive because they are not nested inside a locked R4 mutation. This preserves the principle "no second history system": normal switch → edit_history; explicit destructive reset → the existing version-history checkpoint. See Task 5 for the R4 path and Task 7 for the explicit reset path.

**9. What happens to `template_provenance` after a design-only template switch?**
It is set to the newly selected template's key/version via `build_template_provenance(template_key=<new>, template_version=<new>)`. Provenance answers "which Design DNA baseline is this store currently on," which is truthfully the new template. This is unchanged from `apply_preset`'s current provenance write (`preset_service.py:412-414`).

**10. What should `template_baseline_snapshot` mean after a preservation-mode switch?** *(Core Phase 1 architecture problem.)*
It must be the **new template's authored baseline** — the exact appearance/header/footer/mobile-nav config, per-page section recipe, container settings, and slot keys the new recipe would have written — computed **purely from trusted platform defaults + the new template's registered recipe/selectors, NOT by overlaying onto the Draft's live (override-carrying) effective config**. See Design Decision 14 for the exact pure construction rule. This keeps the invariant that the snapshot truthfully describes what "reset structure to template" would produce, and it makes explicit reset (Decision 11) restore the *template's* structure, not the merchant's current structure. Consequently, after a preservation-mode switch there is a truthful asymmetry: `template_provenance` + `template_baseline_snapshot` describe the new template's authored baseline, while the live Draft sections/global-config are the merchant's preserved/merged state. `draft_matches_own_baseline` will therefore return `False` immediately after a preservation-mode switch on a customized store — which is correct and truthful (the live store is not the template's authored baseline). We never write the merchant's structure or overrides into the snapshot and never claim they are the template baseline.

**11. How does explicit "Reset structure to template" work afterward?**
It calls the existing `reset_page_to_baseline` / `reset_storefront_to_baseline` (`preset_service.py:835-878, 487-556`), which rebuild page composition from `template_baseline_snapshot`. Because Decision 10 keeps the snapshot truthful (the new template's authored baseline), reset restores exactly the new template's structure. This path stays confirmation-gated (the legacy view already enforces explicit confirmation, `views.py:2030-2035`) and remains a checkpointed operation via `reset_storefront_with_checkpoint` / `reset_page_with_checkpoint`.

**12. How do historical Drafts without complete baseline snapshots behave?**
`draft_matches_own_baseline` returns `False` for any Draft lacking a complete matching snapshot, including any snapshot that cannot prove Container/Cell state (Decision 1's fail-safe branch). A `False` result routes template application through **preservation mode**, which never deletes composition — so a legacy/partial-snapshot Draft can never lose merchant structure on a normal switch. Explicit reset on such a Draft still raises the existing `NoTemplateBaselineError`/`TemplateBaselineVersionChangedError`/`BaselineSlotNotFoundError` (`preset_service.py:473-486, 724-741`) exactly as today. No migration/backfill of old snapshots is performed.

**13. What Container/Cell state does `draft_matches_own_baseline` compare, and why?**
Because a merchant can restructure layout without touching any section field, the pristine proof must include the composition layer. For each page the snapshot covers, the predicate:
- reconstructs the expected per-container settings list from the snapshot via `_container_settings_from_snapshot_sections(snapshot["pages"][page])` (`preset_service.py:188-197`), and compares it (count + per-container `settings`) against the current `page.containers.order_by("order", "id")` `settings`;
- compares the section→cell/container membership and `StorefrontSection.cell_order` of the current sections against the placement the snapshot's `row_key`/`row_span` runs imply (the same mapping `container_service.rebuild_page_from_legacy_rows` produces from those entries).
If the stored snapshot lacks `container_settings` on its entries (older snapshot shape) or the reconstruction is not exactly reproducible, the predicate returns `False` (safe-preserve). This makes "changed Container settings" and "moved Cell/block placement" both count as customization (RED tests in Task 2). The comparison is read-only and reuses existing helpers; it does not rebuild anything.

**14. How is the new template's authored `template_baseline_snapshot` constructed purely (no merchant-override absorption)?**
`apply_preset` today builds its overlays by merging the preset onto the Draft's **live effective** config (`_validate_appearance_overlay(draft.effective_appearance_config(), ...)`, `preset_service.py:305, 346, 360`). In preservation mode that would let a merchant's live overrides leak into the "authored baseline." The plan extracts the pure preparation already demonstrated in `validate_layout_preset` (`preset_service.py:124-129`), which overlays the preset onto `models.APPEARANCE_CONFIG_DEFAULTS` / `HEADER_CONFIG_DEFAULTS` / `FOOTER_CONFIG_DEFAULTS` (trusted platform defaults) rather than live config. Task 3 introduces a single shared helper `build_authored_baseline(preset) -> dict` (returning `{template_key, template_version, default_palette_slug, appearance, header_config, footer_config, pages}`) that:
- computes `appearance` = `_validate_appearance_overlay(dict(APPEARANCE_CONFIG_DEFAULTS), {**preset.appearance, "palette_slug": preset.default_palette_slug if set, "layout_preset_key": preset.key})`;
- computes `header_config` = `_validate_header_overlay(dict(HEADER_CONFIG_DEFAULTS), preset.header)`;
- computes `footer_config` = `_validate_footer_overlay(dict(FOOTER_CONFIG_DEFAULTS with mobile-nav reset for Ready Templates), preset.footer)`;
- computes the **truthful authored typed Store Appearance manifest** and writes it into the authored `appearance` under `appearance["store_appearance"]` — see Design Decision 17 (this is the completeness fix; the snapshot's legacy selectors AND its typed `store_appearance` selections must both be Template-B-authored and mutually consistent);
- builds `pages` (section entries + `slot_key` + `container_settings`) exactly as `apply_preset` builds `snapshot_pages` today (`preset_service.py:398-408`), which are already derived from the preset recipe, not from live state.
Both destructive full apply and preservation-mode apply call `build_authored_baseline` to produce the snapshot, so the two paths cannot drift, and no second Ready-Template validation is introduced (the same `_validate_*_overlay` functions, the same `layout_service.validate_*_config` cleaners, and the same `storefront_appearance.validation.validate_store_appearance_manifest` are reused). The merchant's global overrides are applied **separately** to the live Draft config per Design Decision 16 rules; they never enter `build_authored_baseline`'s output.

**15. What are `template_slot_key` semantics after a preservation-mode switch?** *(Chosen model — option B.)*
Chosen: **the preserved sections KEEP their existing `template_slot_key` as historical origin metadata, but are explicitly treated as NON-RESETTABLE against the new template B.** Rationale: after a preservation switch A→B, live sections may still carry A slot keys (`A.key:vN:page:idx`) while the truthful snapshot now describes B. Clearing the keys (option A) would destroy the section's real origin provenance and is a write to merchant rows for no correctness benefit; falsely re-stamping them with B slot keys would lie about B's authored baseline (forbidden). Keeping them as historical metadata is truthful and requires no write.
Semantic consequences the plan makes correct:
- `reset_section_to_baseline(draft, section)` / `reset_section_setting_to_baseline(...)`: these already look up the section's `template_slot_key` in the **current** snapshot via `_find_baseline_section_entry` (`preset_service.py:735-741, 742+`). After a preservation switch, an A slot key will not be found in B's snapshot, so the existing code path raises `BaselineSlotNotFoundError` (`preset_service.py:54-58`). Task 7 asserts this is the correct, truthful behavior: you cannot "reset this A-origin section to B baseline" because B never authored that slot. A section whose slot key *does* match a B baseline entry (only possible after an explicit full B apply/reset) resets normally.
- `reset_page_to_baseline` / `reset_storefront_to_baseline`: these rebuild the whole page/storefront from the truthful B snapshot, creating fresh B-authored sections that receive B `slot_key`s (`preset_service.py:558-616, 835-878`) — unchanged behavior, now truthful because the snapshot is B's authored baseline.
So no misleading "reset to B" ever occurs against an A slot: single-section reset fails closed with a clear Persian error, and full page/storefront reset legitimately replaces everything with B-authored sections and B slot keys.

**16. How are Global Design overrides (palette, font, type_scale, motion, button_style, header variant/settings, footer variant/settings, mobile bottom nav, future Mega Menu selection) preserved on a switch?**
Global Design lives in `appearance_config`/`header_config`/`footer_config`, not in `Section.settings`, but explicit merchant overrides there must not be silently overwritten merely because they are "global." The rule distinguishes **template-authored default** vs **merchant explicit override** using the truthful previous baseline:
- For a Draft with a complete, matching previous `template_baseline_snapshot` (its own baseline provenance), a per-field override is "explicit merchant divergence" when the current live value differs from the previous baseline's value for that field. On switch to B:
  - a field the merchant did NOT diverge from (live == previous-baseline value) **adopts B's authored default** for that field;
  - a field the merchant explicitly diverged from **retains the merchant's value** (survives the switch);
  - the B `template_baseline_snapshot` still records **B's authored value** for every field (never the merchant's).
  Concretely, the live post-switch config is computed as: start from B's authored baseline config (from `build_authored_baseline`), then re-apply only the fields where `live_value != previous_baseline_value` (the proven explicit overrides). This is a field-level three-way reconciliation (B-default, previous-baseline, live) that reuses the existing `layout_service.validate_appearance_config`/`validate_header_config`/`validate_footer_config` cleaners for the final write.
- Header/Footer **variant** selection is Design DNA: it adopts B's authored variant on switch unless the merchant explicitly chose a non-baseline variant (proven the same way). Mobile bottom nav follows the existing Ready-Template reset-then-overlay rule (`preset_service.py:359-370`). A future Mega Menu selection (registered in roadmap Phase 3) follows the same reconciliation once it exists; Phase 1 does not add Mega Menu handling.
- For a **legacy/incomplete/unprovable baseline** where a merchant-visible divergence cannot be established from the stored data, the safe behavior is: **preserve the merchant's entire live global config as-is** (conservatively) and set the B `template_baseline_snapshot` to B's authored values. Documented consequence: such a Draft will not auto-adopt B's global defaults, matching the fail-safe "when uncertain, preserve" principle; the merchant can adopt B defaults explicitly via reset-to-template. This never silently overwrites a merchant value.

**Terminology (tightened per review):** the test `live_value != previous_baseline_value` proves a **provable merchant divergence** from the previous baseline — a merchant-visible difference the data can establish — not necessarily UI-level explicit intent. Where a stronger explicit marker already exists in the current schema (e.g. an existing `*_customized` flag such as `color_overrides_customized`, `preset_service.py:337`), the plan uses that stronger evidence for the field it governs. The rare case "merchant explicitly re-selected exactly the baseline value" is intentionally indistinguishable from "never diverged" and both adopt B defaults; Phase 1 does **not** add a schema migration to disambiguate it. Stronger per-field override provenance, if ever needed, is deferred to the planned full inheritance/override phase (roadmap Phase 4).

**17. How is the typed `store_appearance` manifest kept truthful and internally consistent in BOTH the snapshot and the live Draft?** *(Completeness fix for the baseline invariant.)*
Today `_apply_appearance_template` (`r4_mutation_service.py:394-427`) does a full apply, then `_sync_manifest_from_live_selectors`, then overwrites `snapshot["appearance"]` with the **live** `appearance_config` (which by then contains the synced `store_appearance` typed manifest). That is correct only for a full apply, where live == authored. In preservation mode the live config carries merchant overrides, so copying live into the snapshot would put a merchant/stale-A typed manifest inside B's "authored baseline" — violating the invariant. The plan therefore separates the two manifests explicitly:
- **Snapshot (authored B):** `build_authored_baseline(preset)` sets `appearance["store_appearance"]` to the **preset's own authored, validated typed manifest** — `preset.store_appearance` (authored in `a8_ready_templates._manifest`, validated at registration by `_validate_ready_template_store_appearance` → `validate_store_appearance_manifest(..., require_complete=True)`, `layout_preset_registry.py:298-310`) — normalized through the existing `storefront_appearance.validation` contract. No second validation is introduced. The snapshot's legacy selectors (`header_variant`/`footer_variant`/`mobile_nav_variant`/`motion`) and its typed `store_appearance` selections are therefore both Template-B-authored and mutually consistent by construction: `snapshot.header_config["header_variant"] == component→selector(snapshot["store_appearance"].selections["header"])`, and likewise for footer, mobile-nav, motion, and any future Mega Menu selector.
- **Live Draft:** the live typed manifest is synchronized from the **reconciled live** selectors via the existing `_sync_manifest_from_live_selectors` after the DNA/global-override reconciliation (Decision 16) has set the live legacy selectors. So the live `appearance_config["store_appearance"]` always matches the live reconciled `header_config`/`footer_config`/motion selectors.
- **Consequence (Decision 3 of the review):** after a preservation A→B switch, `snapshot["store_appearance"]` = B-authored selections while `live appearance_config["store_appearance"]` = the preserved/reconciled selections; they are intentionally allowed to differ. The plan never copies the live manifest into the snapshot to force equality. Concretely, if B authors header `H_B` but the merchant's provable divergence preserves `H_M`: `snapshot.header_config = H_B` and `snapshot["store_appearance"].selections["header"] = component(H_B)`, while `draft.header_config = H_M` and `live store_appearance.selections["header"] = component(H_M)`.
- **R4 mutation change (Task 7):** replace the "overwrite `snapshot["appearance"]` with live config" step with "set `draft.template_baseline_snapshot = build_authored_baseline(preset)` (authored B, incl. typed manifest)" and, separately, run `_sync_manifest_from_live_selectors(draft)` so the LIVE manifest reflects the reconciled live selectors. The two are written independently and are each internally consistent.

---

## Migration Decision

**No schema migration is planned.** The required state — "is this Draft still the template's authored baseline?", "which template DNA is active?", and "what would reset restore?" — is fully representable with the existing fields `StorefrontLayoutVersion.template_provenance`, `StorefrontLayoutVersion.template_baseline_snapshot`, `StorefrontSection.template_slot_key` (empty ⇒ merchant-created), plus `edit_history` and the archived-version history. Preservation mode is a control-flow change in `apply_preset` (skip the composition-replacement block) plus a truthful snapshot/provenance write; it adds no persisted state. Task 10 explicitly runs `python manage.py makemigrations --check --dry-run` and requires "No changes detected." If a future need for new state is discovered during implementation, it must (per plan policy) prove why current fields cannot represent it, add the minimal field, explain backward compatibility, and include migration tests — but this plan does not anticipate or authorize one.

---

## Expected File Map

**Modified:**
- `apps/storefront_builder/services/preset_service.py` — add: (a) `build_authored_baseline(preset) -> dict` — pure construction of the new template's authored baseline from `APPEARANCE_CONFIG_DEFAULTS`/`HEADER_CONFIG_DEFAULTS`/`FOOTER_CONFIG_DEFAULTS` + preset recipe, **including the authored typed `store_appearance` manifest from `preset.store_appearance`** (Design Decisions 14, 17), reused by both apply modes so they cannot drift; (b) `draft_matches_own_baseline(draft) -> bool` — the fail-safe pristine predicate incl. Container/Cell verification (Design Decisions 1, 13); (c) a `preserve_structure: bool` keyword on `apply_preset` that, when `True`, skips the per-page composition-replacement block while still writing appearance/header/footer DNA (with global-override reconciliation per Design Decision 16), provenance, and the truthful authored baseline snapshot from `build_authored_baseline`; (d) `apply_ready_template(draft, preset, *, mode)` orchestration (`mode in {"preserve", "replace_structure"}`) with `mode="preserve"` as the default for normal switches; ensure `apply_preset_with_checkpoint` applies in `mode="preserve"`; and (e) a live-typed-manifest re-sync inside `reset_header_to_baseline`/`reset_footer_to_baseline` (Task 9) so a reset legacy selector cannot leave a stale live `store_appearance` manifest. Responsibility: the single home of all preset/template application and baseline/reset logic. No second Ready-Template or Store-Appearance validation is added — reuse existing `_validate_*_overlay`, `layout_service.validate_*_config`, and `storefront_appearance.validation.validate_store_appearance_manifest`.
- `apps/storefront_builder/services/r4_mutation_service.py` — change `_apply_appearance_template` (`r4_mutation_service.py:394-424`) to apply the template through `preset_service.apply_ready_template(draft, preset, mode="preserve")` **on the same locked Draft**, then refresh the truthful authored baseline snapshot from `build_authored_baseline`. It **must NOT** call `layout_service.checkpoint_draft_before_replacement` (that would create/repoint a new Draft and break the locked-Draft contract — Design Decision 8). The whole operation stays the single atomic R4 mutation `apply_mutation` already provides: one `edit_history` entry, one `edit_revision` increment, undo restores pre-switch state. Keeps the `appearance.template.apply` mutation type and its history label (`"اعمال قالب آماده"`). Responsibility: the single R4 mutation boundary.
- `apps/storefront_builder/views.py` — confirm the explicit merchant apply/confirm view (`views.py:2030-2049`) still routes explicit **structure-replacing** applies through `apply_preset_with_checkpoint` (a durable checkpoint is correct here because this path runs OUTSIDE `apply_mutation`), and that its default (non-confirmed) behavior is preservation. Adjust only if an entry-point signature changes. Responsibility: legacy merchant apply/confirm view.

**Created (only if a test needs a dedicated module; prefer existing modules):**
- `apps/storefront_builder/tests/test_template_switch_preservation.py` — the Phase 1 RED/GREEN preservation matrix (Tasks 1–7 tests) if the assertions do not fit cleanly into existing modules. Responsibility: focused Phase-1 regression suite.

**Tested (existing modules extended or asserted against):**
- `apps/storefront_builder/tests/test_preset_service.py` — preset apply/reset behavior.
- `apps/storefront_builder/tests/test_acceptance_batch2.py` — checkpoint/restore-on-switch semantics.
- `apps/storefront_builder/tests/test_u7_ready_template_baseline.py` — provenance/baseline.
- `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py` — `appearance.template.apply` mutation.
- `apps/storefront_builder/tests/test_r4_vertical_slice.py` — structure mutations + template switch.
- `apps/storefront_builder/tests/test_appearance.py` — template-switch appearance/palette rules.
- `apps/storefront_builder/tests/test_u1a_preset_edit_history_characterization.py` — edit-history around preset apply.

**Explicitly NOT modified:**
- `apps/storefront_builder/services/render_service.py` — no renderer change.
- `apps/storefront_builder/storefront_appearance/**` — the engine, validation, and manifest are unchanged.
- `apps/content/models.py` — the section FK and `on_delete=CASCADE` are unchanged (preservation avoids the delete, so CASCADE never fires).
- `apps/storefront_builder/models.py` — no schema change (Migration Decision).
- `apps/storefront_builder/a8_ready_templates.py` and `storefront_appearance/inventory.py` — the 50 recipes are unchanged.
- `apps/catalog/**`, `apps/orders/**` — Content-vs-Commerce boundary preserved.

---

## Regression Gates (layered)

- **Task-level targeted test:** the single test method for the task, e.g. `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation.TemplateSwitchPreservationTests.test_<name> -v2`.
- **Phase-focused module:** `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v1`.
- **Neighboring regression:** `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_acceptance_batch1 apps.storefront_builder.tests.test_acceptance_batch2 apps.storefront_builder.tests.test_acceptance_batch3 apps.storefront_builder.tests.test_u7_ready_template_baseline apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization apps.storefront_builder.tests.test_r4_store_appearance_mutations apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_appearance -v1`.
- **Django + migration check:** `python manage.py check` and `python manage.py makemigrations --check --dry-run` (expect "No changes detected").
- **Template validity gate:** `python manage.py test apps.storefront_builder.tests.test_a8_ready_template_catalog apps.storefront_builder.tests.test_a8_ready_template_contracts apps.storefront_builder.tests.test_a8_template_diversity -v1`.
- **Final broad checkpoint (run once at the end, Task 11):** `python manage.py test apps.storefront_builder -v1`.

Do not run the full `apps.storefront_builder` suite after every task; use it only at the Task 9 checkpoint.

---

## Tasks

### Task 1: Codify template-switch preservation semantics as failing tests (fresh + pristine cases)

**Files**
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py` (create)

**Interfaces**
- Consumes: `layout_service.get_or_create_draft`, `layout_preset_registry.get_layout_preset`, `preset_service.apply_preset`, `StorefrontLayoutVersion`, `StorefrontSection`.
- Produces: `TemplateSwitchPreservationTests` test class with fixtures for a store, a Draft, and two distinct Ready Templates (e.g. `dense_marketplace` and `warm_boutique`).

- [ ] Step 1 — Write failing tests for CASE 1 (fresh/no-provenance Draft → applying template writes its suggested structure) and CASE 2 (Draft that exactly matches its own baseline → switching to template B may write B's structure). Assert home section `section_key`s equal the target recipe's home composition.
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED (helpers/predicate not yet present).
- [ ] Step 3 — No production code yet; these two cases must remain achievable by existing `apply_preset` behavior once the orchestration exists (they use structure-applying mode).
- [ ] Step 4 — Leave RED; Task 3 makes them GREEN.
- [ ] Step 5 — (deferred to Task 3)
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `test(storefront-builder): codify fresh/pristine template-switch cases`

### Task 2: Add `draft_matches_own_baseline` fail-safe pristine classifier (incl. Container/Cell)

**Files**
- Modify: `apps/storefront_builder/services/preset_service.py`
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`

**Interfaces**
- Consumes: `StorefrontLayoutVersion.template_provenance`, `.template_baseline_snapshot`, `StorefrontSection` fields (`section_key`, `settings`, `row_key`, `row_span`, `template_slot_key`, `cell`, `cell_order`), `StorefrontContainer.settings`, `draft.get_page`, `_container_settings_from_snapshot_sections`.
- Produces: `preset_service.draft_matches_own_baseline(draft: StorefrontLayoutVersion) -> bool`.

- [ ] Step 1 — Write failing tests: a freshly applied template Draft → `True`; after reordering sections → `False`; after adding a merchant section (`template_slot_key == ""`) → `False`; after editing a section `settings` value → `False`; **after changing a `StorefrontContainer.settings` value → `False`**; **after moving a section to a different Cell/block placement (`cell`/`cell_order`) → `False`**; a legacy Draft with empty `template_baseline_snapshot` → `False`; a Draft whose snapshot entries lack `container_settings` → `False` (safe-preserve).
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation.TemplateSwitchPreservationTests -v2` and verify RED (`AttributeError`: function missing).
- [ ] Step 3 — Implement `draft_matches_own_baseline` per Design Decisions 1 and 13: compare against the Draft's **own** snapshot (identity from `provenance.template.key/version`); verify appearance/header/footer equality; verify per-section fields; **verify per-page Container settings** (reconstruct expected via `_container_settings_from_snapshot_sections` and compare to `page.containers.order_by("order","id")` `settings`, count-checked); **verify Cell/block placement** (section→container/cell membership and `cell_order` match the snapshot's `row_key`/`row_span` runs); return `False` on any deviation or any snapshot too old/partial to prove Container/Cell state. Keep `_draft_already_matches_preset` as a thin wrapper: first assert `provenance/snapshot` identity equals the candidate preset, then delegate to `draft_matches_own_baseline`.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_acceptance_batch2 -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `refactor(storefront-builder): fail-safe pristine baseline detection`

### Task 3: Extract pure `build_authored_baseline(preset)` (no live-override absorption)

**Files**
- Modify: `apps/storefront_builder/services/preset_service.py`
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`

**Interfaces**
- Consumes: `models.APPEARANCE_CONFIG_DEFAULTS`/`HEADER_CONFIG_DEFAULTS`/`FOOTER_CONFIG_DEFAULTS`, `_validate_appearance_overlay`/`_validate_header_overlay`/`_validate_footer_overlay`, `preset.appearance`/`.header`/`.footer`/`.default_palette_slug`/`.pages`/`.store_appearance`, `storefront_appearance.validation.validate_store_appearance_manifest`/`manifest_to_primitive`, existing `snapshot_pages` construction, `global_region_registry.GLOBAL_MOBILE_NAV_REGION`.
- Produces: `preset_service.build_authored_baseline(preset: LayoutPresetDefinition) -> dict` returning `{template_key, template_version, default_palette_slug, appearance, header_config, footer_config, pages}`, where `appearance["store_appearance"]` is the preset's authored, validated typed manifest.

- [ ] Step 1 — Write failing tests: `build_authored_baseline(presetB)` is **independent of any live Draft** (call it with no draft) and equals presetB's authored config; specifically, given a Draft whose live `appearance_config` carries a merchant override (e.g. a custom `font` and a diverged header), `build_authored_baseline(presetB)["appearance"]["font"]` equals presetB's authored font, **not** the merchant's; `["appearance"]["store_appearance"]["selections"]` equals presetB's authored `store_appearance` selections (assert it contains **no** A/merchant selector); the snapshot's legacy `header_config["header_variant"]` maps to the same component as `["appearance"]["store_appearance"]["selections"]["header"]` (internal consistency), and likewise footer/mobile-nav/motion; `["pages"]["home"]` section_keys equal presetB's recipe; the result matches the snapshot a fresh full `apply_preset` writes today (parity assertion).
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED.
- [ ] Step 3 — Implement `build_authored_baseline` by overlaying the preset onto the trusted `*_CONFIG_DEFAULTS` (the exact pure pattern already in `validate_layout_preset`, `preset_service.py:124-129`) — never onto `draft.effective_*_config()` — plus the mobile-nav reset for Ready Templates; set `appearance["store_appearance"]` from `preset.store_appearance` normalized through `validate_store_appearance_manifest(preset.store_appearance, require_complete=True)` then `manifest_to_primitive` (reuse the engine contract; no second validation); and build the `pages` entries/`slot_key`/`container_settings` from the existing `snapshot_pages` construction. Refactor `apply_preset`'s existing full-apply snapshot build to call `build_authored_baseline` so both paths share one implementation (no drift, no second Ready-Template validation, and the snapshot's legacy selectors and typed manifest are consistent by construction — Design Decision 17).
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_u7_ready_template_baseline -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `refactor(storefront-builder): build authored template baseline purely from defaults`

### Task 4: Add preservation mode to `apply_preset` and the `apply_ready_template` orchestrator

**Files**
- Modify: `apps/storefront_builder/services/preset_service.py`
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`

**Interfaces**
- Consumes: `draft_matches_own_baseline`, `build_authored_baseline`, existing appearance/header/footer overlay + validation, `build_template_provenance`.
- Produces: `apply_preset(draft, preset, *, _record_baseline_snapshot=True, preserve_structure=False)`; `apply_ready_template(draft, preset, *, mode: str) -> None` where `mode in {"preserve", "replace_structure"}` (default caller uses `"preserve"`).

- [ ] Step 1 — Write failing tests: (a) `apply_preset(draft, presetB, preserve_structure=True)` on a customized Draft leaves every `StorefrontSection` row/order/`settings`, `StorefrontContainer.settings`, and Cell placement unchanged while Design DNA changes to presetB; (b) after the call, `template_provenance` equals presetB and `template_baseline_snapshot` equals `build_authored_baseline(presetB)` (assert `snapshot["pages"]["home"]` section_keys equal presetB's recipe, NOT the merchant's live sections); (c) `apply_ready_template(mode="replace_structure")` DOES rebuild composition from presetB; (d) Task 1 CASE 1/CASE 2 pass (fresh/pristine → structure applies).
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED.
- [ ] Step 3 — Implement: in `apply_preset`, keep validation + provenance; write the snapshot from `build_authored_baseline(preset)`; when `preserve_structure=True`, **skip** the per-page composition write loop (`page.containers.all().delete()` / `page.sections.all().delete()` / `bulk_create` / container rebuild, `preset_service.py:445-460`) and write the live Design-DNA config via the global-override reconciliation added in Task 5 (until Task 5 lands, preservation mode adopts presetB authored config for global fields; Task 5 refines to reconcile overrides). Implement `apply_ready_template`: `mode="preserve"` → `apply_preset(..., preserve_structure=True)`; `mode="replace_structure"` → `apply_preset(..., preserve_structure=False)`.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_appearance apps.storefront_builder.tests.test_u7_ready_template_baseline -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `feat(storefront-builder): preserve merchant structure during template switch`

### Task 5: Reconcile Global Design overrides on a preservation switch

**Files**
- Modify: `apps/storefront_builder/services/preset_service.py`
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`

**Interfaces**
- Consumes: `build_authored_baseline`, the Draft's own previous `template_baseline_snapshot` (for the previous-baseline values), `draft.effective_appearance_config`/`_header_config`/`_footer_config` (live values), `layout_service.validate_appearance_config`/`validate_header_config`/`validate_footer_config`.
- Produces: internal `_reconcile_global_overrides(draft, authored_baseline_config, previous_baseline_config) -> dict` used by preservation-mode `apply_preset` for `appearance_config`/`header_config`/`footer_config`.

- [ ] Step 1 — Write failing tests (Design Decision 16): starting from a Draft on template A with a proven previous baseline, where the merchant explicitly changed `font` (live != A-baseline) but did NOT change `motion` (live == A-baseline): after `apply_ready_template(draft, presetB, mode="preserve")`, live `font` retains the merchant value, live `motion` adopts presetB's authored motion, and `template_baseline_snapshot["appearance"]` records presetB's authored `font` AND `motion` (never the merchant's font); an explicit header-variant override survives while a non-overridden footer variant adopts presetB; a **legacy/incomplete-baseline** Draft preserves its entire live global config and records presetB authored values in the snapshot.
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED.
- [ ] Step 3 — Implement `_reconcile_global_overrides`: for each global field, start from the authored-B value; if a complete matching previous baseline exists AND `live_value != previous_baseline_value`, keep the live (explicit-override) value; otherwise adopt the authored-B value. If no complete previous baseline can be proven, keep the entire live config unchanged (safe-preserve). Clean the reconciled config through the existing `layout_service.validate_*_config`. Wire it into preservation-mode `apply_preset` so the snapshot (authored-B, from Task 3) and the live config (reconciled) are written independently.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_appearance apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_dark_digital_luxury_v2 -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `feat(storefront-builder): reconcile explicit global overrides on template switch`

### Task 6: Verify and lock section-scoped Hero/Banner/Story preservation

**Files**
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`
- Modify (only if a test proves a gap): `apps/storefront_builder/services/preset_service.py`

**Interfaces**
- Consumes: `HeroSlide`/`PromotionalBanner`/`StoryRailItem` with `section` FK; `apply_ready_template(..., mode="preserve")`.
- Produces: regression coverage proving CASCADE never fires in preservation mode.

- [ ] Step 1 — Write failing tests (CASE 5): create a `hero_banner` section with a section-scoped `HeroSlide` (and analogous `PromotionalBanner`, `StoryRailItem`) whose `section_id` is set; run `apply_ready_template(draft, presetB, mode="preserve")`; assert each row still exists with the same `section_id` and the same field values.
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED if any gap exists (expected GREEN if Task 4 correctly skips the section delete; a RED here reveals an unexpected deletion path to fix minimally).
- [ ] Step 3 — If RED, fix minimally within `apply_preset` preservation mode (no content-model change). If GREEN, no production change — the test locks the invariant.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization apps.storefront_builder.tests.test_preset_service -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `test(storefront-builder): lock section-scoped content survival on template switch`

### Task 7: Route the R4 `appearance.template.apply` mutation through same-Draft preservation (no checkpoint inside the locked mutation)

**Files**
- Modify: `apps/storefront_builder/services/r4_mutation_service.py`
- Test: `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`

**Interfaces**
- Consumes: `preset_service.apply_ready_template`, `preset_service.build_authored_baseline`, existing `_apply_appearance_template` validation (template key/version, `is_ready_template`), `_sync_manifest_from_live_selectors`.
- Produces: preservation-mode template application on the R4 mutation path as **one atomic same-Draft mutation with exactly one edit-history entry**; the `appearance.template.apply` mutation type and its history label (`"اعمال قالب آماده"`) are unchanged. **Does NOT call `layout_service.checkpoint_draft_before_replacement`** (Design Decision 8).

- [ ] Step 1 — Write failing tests: dispatching `appearance.template.apply` on a **customized** Draft preserves the merchant's sections (order/added/settings), Container settings, and section-scoped media while changing Design DNA; the operation runs on the **same** active Draft (`layout.draft_version_id` unchanged; no new/archived version created — assert `layout.versions.count()` unchanged and no `ARCHIVED` row appears); it produces **exactly one** new edit-history entry (assert `edit_history_service.history_state` count increments by one); `edit_revision` increments by exactly one; the **live** `appearance_config["store_appearance"]` matches the reconciled live selectors (assert live header selection == component of live `header_config["header_variant"]`); the **snapshot** `template_baseline_snapshot["appearance"]["store_appearance"]` equals presetB's authored selections and contains **no** A/merchant selector; **undo** restores the full pre-switch state including the complete pre-switch typed manifest (sections + Design DNA + section-scoped media + `store_appearance`); the published version is unchanged; a stale `base_revision` returns 409 and leaves the Draft unchanged.
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_r4_store_appearance_mutations -v2` and verify RED.
- [ ] Step 3 — Modify `_apply_appearance_template` (`r4_mutation_service.py:394-427`): after validating the preset, apply through `preset_service.apply_ready_template(draft, preset, mode="preserve")` **on the same locked `draft`**; run `_sync_manifest_from_live_selectors(draft)` so the **live** typed manifest reflects the reconciled live selectors; set `draft.template_baseline_snapshot = preset_service.build_authored_baseline(preset)` (truthful authored-B baseline incl. the authored typed manifest). **Replace** the current step that overwrites `snapshot["appearance"]` with the live `appearance_config` (`r4_mutation_service.py:421-427`) — in preservation mode that would copy the merchant/stale-A typed manifest into B's authored snapshot (Design Decision 17). Do **not** call `checkpoint_draft_before_replacement` or create/repoint any version — the surrounding `apply_mutation` already locked this Draft, snapshotted `before_state`, will record one history entry, and will increment `edit_revision`; a durable checkpoint here would archive the locked Draft and break that contract (Design Decision 8). Recoverability of a normal switch is via Undo (the recorded edit-history entry); the durable checkpoint stays exclusively on the explicit destructive reset / legacy-view paths (Task 8).
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_acceptance_batch2 -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `fix(storefront-builder): R4 template switch preserves structure as one atomic mutation`

### Task 8: Confirm/align the legacy merchant apply view to preservation mode

**Files**
- Modify (only if the entry-point signature changed): `apps/storefront_builder/views.py`
- Test: `apps/storefront_builder/tests/test_acceptance_batch2.py`

**Interfaces**
- Consumes: `preset_service.apply_preset_with_checkpoint` (now preservation-mode by default). This path runs **outside** `apply_mutation`, so its durable version checkpoint is contract-safe and correct here (unlike Task 7's R4 path).
- Produces: legacy view behavior consistent with the R4 path's *preservation* semantics, while retaining its durable pre-apply checkpoint.

- [ ] Step 1 — Write failing tests: the merchant apply view on a customized Draft preserves sections while changing DNA, still creates a durable pre-apply archived checkpoint (query `layout.versions.filter(status=ARCHIVED)`), and still requires explicit confirmation for structure replacement (the existing confirm-gate at `views.py:2030-2035`).
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_acceptance_batch2 -v2` and verify RED if the view still replaces structure by default.
- [ ] Step 3 — Ensure `apply_preset_with_checkpoint` (`preset_service.py:659-689`) applies in preservation mode by default (call `apply_ready_template(..., mode="preserve")` internally instead of raw `apply_preset`) while keeping its `checkpoint_draft_before_replacement` call (contract-safe here — not inside a locked R4 mutation). Update the view only if the callable signature changed; otherwise no view edit is needed.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_views -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `fix(storefront-builder): default legacy template apply to preservation mode`

### Task 9: Explicit "reset structure to template" remains available, confirmation-gated, and truthful (incl. slot-key transition)

**Files**
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`
- Modify (only if a test proves a gap): `apps/storefront_builder/services/preset_service.py`

**Interfaces**
- Consumes: `apply_ready_template(..., mode="replace_structure")`, `reset_storefront_to_baseline`, `reset_page_to_baseline`, `reset_section_to_baseline`, `reset_storefront_with_checkpoint`, `reset_page_with_checkpoint`, `LockedSectionsPresentError`, `BaselineSlotNotFoundError`.
- Produces: explicit structure-reset regression coverage, including the slot-key transition semantics (Design Decision 15).

- [ ] Step 1 — Write failing tests: (CASE 4) after a preservation-mode switch to presetB, `reset_page_to_baseline(draft, "home")` replaces the home composition with presetB's authored baseline and the newly created sections carry **presetB** `template_slot_key`s (proving Decisions 10/15 kept the snapshot truthful); **explicit Reset Header/Footer to B** restores B's authored legacy selector **and** the corresponding B typed `store_appearance` component key (assert the live manifest selection for that family equals `component(B authored variant)` after reset); **slot-key transition** — a section preserved from template A (still carrying an A `template_slot_key`) that has no matching B slot raises `BaselineSlotNotFoundError` on `reset_section_to_baseline` (no misleading "reset to B" against an A slot), while a section whose slot key matches a B entry resets normally; (CASE 6) a locked section causes `reset_page_to_baseline`/`apply_ready_template(mode="replace_structure")` to raise `LockedSectionsPresentError` and leave the Draft unchanged; explicit replace_structure with confirmation replaces merchant composition.
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED where gaps exist.
- [ ] Step 3 — If RED, fix minimally: ensure `replace_structure` mode and reset read from the truthful authored-B snapshot; ensure preserved A slot keys are left intact but non-resettable against B per Decision 15; and ensure the header/footer reset paths **re-synchronize the live typed manifest** after writing the reset legacy config — `reset_header_to_baseline`/`reset_footer_to_baseline` (`preset_service.py:880-898`) currently write only `header_config`/`footer_config` and do not sync `appearance_config["store_appearance"]`, so add a `storefront_appearance.persistence`-consistent live-selector re-sync (reuse the same live-selector→manifest projection `_sync_manifest_from_live_selectors` uses; do not duplicate the engine contract) so the live typed manifest matches the reset legacy selectors. If GREEN, the tests lock the behavior.
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_acceptance_batch2 apps.storefront_builder.tests.test_acceptance_batch3 -v1`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `test(storefront-builder): lock explicit reset-to-template-structure and slot-key transition`

### Task 10: Complete the preservation regression matrix + invariant/safety checks

**Files**
- Test: `apps/storefront_builder/tests/test_template_switch_preservation.py`

**Interfaces**
- Consumes: all interfaces above.
- Produces: the full 25-item RED/GREEN matrix (see Test Requirements) as executable tests.

- [ ] Step 1 — Write the remaining failing tests covering: reordered sections survive (CASE 3); merchant-added section survives; duplicated section survives; rich-text `body_html` survives; manual `product_ids`+order survive; manual `brand_ids`+order survive; section `appearance_overrides` survive; changed `StorefrontContainer.settings` and moved Cell/block placement survive a preservation switch; independent Product/ProductImage/Category/Brand/Collection unchanged (assert counts/PKs); explicit merchant global overrides survive while non-overridden global defaults adopt B values (Design Decision 16); template Design DNA actually changes (assert `appearance_config`/variants differ); `template_baseline_snapshot` contains B authored values, never merchant global overrides; invalid template/version leaves Draft unchanged (`R4MutationError`/`InvalidPresetError`); Published unchanged until Publish; **undo restores pre-switch design metadata and merchant state via the single edit-history entry** (R4 path — no archived version created); the legacy view path's durable checkpoint is recoverable via `restore_version`; legacy/incomplete snapshot behaves safely (preservation, no data loss); no cross-tenant resource leakage (a second store's IDs are rejected/absent).
- [ ] Step 2 — Run `python manage.py test apps.storefront_builder.tests.test_template_switch_preservation -v2` and verify RED for any not-yet-covered assertion.
- [ ] Step 3 — Make minimal production adjustments only if a specific assertion fails for a real defect; prefer no change (Tasks 2–9 should already satisfy most).
- [ ] Step 4 — Run the same test command and verify GREEN.
- [ ] Step 5 — `python manage.py check` and `python manage.py makemigrations --check --dry-run` (expect "No changes detected").
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `test(storefront-builder): complete template-switch preservation regression matrix`

### Task 11: Template-validity + neighboring + final regression checkpoint

**Files**
- Test: (no new files) run the existing suites.

**Interfaces**
- Consumes: the full storefront_builder test suite.
- Produces: green regression evidence that the 50 templates remain valid and existing reset/appearance tests pass or are deliberately updated to the new semantics.

- [ ] Step 1 — Run the template-validity gate: `python manage.py test apps.storefront_builder.tests.test_a8_ready_template_catalog apps.storefront_builder.tests.test_a8_ready_template_contracts apps.storefront_builder.tests.test_a8_template_diversity apps.storefront_builder.tests.test_a8_component_coverage -v1`; expect GREEN (all 50 valid).
- [ ] Step 2 — Run the neighboring regression set: `python manage.py test apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_acceptance_batch1 apps.storefront_builder.tests.test_acceptance_batch2 apps.storefront_builder.tests.test_acceptance_batch3 apps.storefront_builder.tests.test_u7_ready_template_baseline apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization apps.storefront_builder.tests.test_r4_store_appearance_mutations apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_appearance -v1`.
- [ ] Step 3 — For any existing test that asserted the OLD destructive default (e.g. a `test_acceptance_batch2`/`test_r4_vertical_slice` case asserting sections are replaced on a customized-store switch), deliberately update it to the newly approved preservation semantics, documenting the change in the commit body; do not weaken unrelated assertions.
- [ ] Step 4 — Run the final broad checkpoint: `python manage.py test apps.storefront_builder -v1`; expect GREEN.
- [ ] Step 5 — `python manage.py check`.
- [ ] Step 6 — `git diff --check`
- [ ] Step 7 — Commit: `test(storefront-builder): align template-switch regression suite to preservation semantics`

---

## Test Requirements (RED/GREEN coverage — mapped to tasks)

1. Pristine A → B may receive B authored structure — Task 1 (fresh/pristine) + Task 4.
2. Untouched template A → template B → B structure may apply — Task 1 + Task 4.
3. Customized A → B preserves structure — Task 4 + Task 10.
4. Merchant reordered sections → switch → order survives — Task 10.
5. Merchant-added section → switch → survives — Task 10.
6. Merchant duplicated section → switch → survives — Task 10.
7. Changed `StorefrontContainer.settings` counts as customization (pristine → `False`) and survives a preservation switch — Task 2 + Task 10.
8. Moved Cell/block placement counts as customization (pristine → `False`) and survives a preservation switch — Task 2 + Task 10.
9. Legacy/incomplete baseline defaults to preservation (safe) — Task 2 + Task 5 + Task 10 (Design Decisions 12, 16).
10. Merchant rich-text `body_html` → switch → survives — Task 10.
11. Manual product selection/order → switch → survives — Task 10.
12. Manual brand selection/order → switch → survives — Task 10.
13. Section `appearance_overrides` → switch → survives — Task 10.
14. Section-scoped `HeroSlide`/`PromotionalBanner`/`StoryRailItem` → normal switch → survive — Task 6.
15. Independent Product/ProductImage/Category/Brand/Collection unchanged — Task 10.
16. Preservation switch does **not** create/replace the active Draft inside the R4 mutation — Task 7.
17. One successful R4 switch produces **exactly one** edit-history entry (and one `edit_revision` increment) — Task 7.
18. Undo restores pre-switch design metadata and merchant state (incl. the complete pre-switch typed `store_appearance` manifest) — Task 7 + Task 10.
19. Preserved section slot identity does **not** falsely map to B baseline (A slot → `BaselineSlotNotFoundError` on section reset) — Task 9 (Design Decision 15).
20. Explicit page reset rebuilds B sections with B slot keys — Task 9.
21. B baseline snapshot does **not** contain merchant global overrides (built purely from defaults) — Task 3 + Task 5 + Task 10 (Design Decision 14).
22. Provable merchant global divergence survives the switch — Task 5 + Task 10 (Design Decision 16).
23. Non-overridden global values adopt B values — Task 5 + Task 10 (Design Decision 16).
24. Template Design DNA actually changes — Task 4 + Task 10.
25. Explicit reset-to-template-structure replaces merchant composition — Task 9.
26. Locked sections protect explicit destructive reset — Task 9.
27. Invalid template/version leaves Draft unchanged — Task 10.
28. Stale `base_revision` returns 409 / preserves state — Task 7.
29. Published remains unchanged until Publish — Task 7 + Task 10.
30. Explicit destructive reset remains confirmation/history protected (durable checkpoint via `reset_*_with_checkpoint`) — Task 8 (legacy view) + Task 9.
31. No cross-tenant resource leakage — Task 10.
32. Existing 50 Ready Templates remain valid — Task 11.
33. Existing template reset tests pass or are deliberately updated to the new semantics — Task 11.
34. Authored B baseline includes B's typed `store_appearance` manifest (`snapshot["appearance"]["store_appearance"].selections` == B authored) — Task 3 (Design Decisions 14, 17).
35. No stale A/merchant component selector exists in the B baseline typed manifest — Task 3 + Task 7 (Design Decision 17).
36. Snapshot legacy selectors and snapshot typed manifest are mutually consistent (both B-authored) — Task 3 (Design Decision 17).
37. Live typed manifest matches the preserved/reconciled live selectors after a preservation switch — Task 5 + Task 7 (Design Decision 17).
38. B snapshot typed manifest remains B-authored while live manifest may differ (intentional live-vs-baseline divergence) — Task 7 (Design Decision 17).
39. Explicit Reset Header/Footer to B synchronizes both the legacy selector and the typed `store_appearance` component key — Task 9 (Design Decision 17).
40. Legacy/unprovable global state preserves live values safely (typed manifest included) — Task 5 + Task 10 (Design Decision 16).

---

## Commit Strategy

Small commits, one per task, exact messages as specified in each task's Step 7:

1. `test(storefront-builder): codify fresh/pristine template-switch cases`
2. `refactor(storefront-builder): fail-safe pristine baseline detection`
3. `refactor(storefront-builder): build authored template baseline purely from defaults`
4. `feat(storefront-builder): preserve merchant structure during template switch`
5. `feat(storefront-builder): reconcile explicit global overrides on template switch`
6. `test(storefront-builder): lock section-scoped content survival on template switch`
7. `fix(storefront-builder): R4 template switch preserves structure as one atomic mutation`
8. `fix(storefront-builder): default legacy template apply to preservation mode`
9. `test(storefront-builder): lock explicit reset-to-template-structure and slot-key transition`
10. `test(storefront-builder): complete template-switch preservation regression matrix`
11. `test(storefront-builder): align template-switch regression suite to preservation semantics`

---

## Anti-Patterns This Plan Forbids

- No second renderer (`render_service` untouched).
- No second Draft lifecycle (only `StorefrontLayoutVersion` Draft/Published/Archived).
- No second history system: a normal R4 template switch is one atomic same-Draft mutation → one `edit_history` entry (undo-recoverable); a durable archived-version checkpoint is used ONLY on the explicit destructive reset / legacy-view apply paths that run outside `apply_mutation`. Never call `checkpoint_draft_before_replacement` from inside the locked R4 mutation.
- No arbitrary HTML/CSS/JS or raw JSON (engine validation unchanged).
- No template-specific Builder.
- No destructive default template switching (preservation is the default; structure replacement is explicit + confirmation-gated).
- No dishonest `template_baseline_snapshot` (always the new template's authored baseline).
- No schema migration unless a discovered need is proven per the Migration Decision policy.
