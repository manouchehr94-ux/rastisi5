# RastiSi A8 Production Component Library and 50 Ready Template DNA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the Design Lab prototype's reusable visual DNA into the existing R4 Store Appearance engine as registered production components and exactly 50 versioned official Ready Template recipes.

**Architecture:** Extend the existing `LayoutPresetDefinition`, Store Appearance component adapters, global-region registry, section variants, and A7 shared resolver. Ready Templates remain data recipes applied atomically to Draft; Preview and Public keep one renderer, and all renderer/template paths remain platform-owned registry metadata.

**Tech Stack:** Python 3.12, Django, Django templates, CSS, unittest/Django TestCase, Playwright-based management capture command.

**Spec:** `docs/superpowers/specs/2026-09-01-storefront-design-engine-50-templates-design.md` and `docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md`, narrowed by the owner's A8 request attached to this task.

## Global Constraints

- Start from clean `feature/storefront-builder-r4` at exact SHA `2e8ca99406199220eb69033b03b77394b89f0dde`.
- Keep one A7 resolver and one shared Preview/Public renderer; Preview reads Draft and Public reads Published.
- Store only schema-version-1, typed, allowlisted component selections and bounded appearance/composition settings.
- Never persist arbitrary HTML, CSS, JavaScript, renderer paths, template paths, executable expressions, unrestricted JSON, prototype numeric IDs, Demo IDs, or merchant business/catalog data in template DNA.
- Preserve historical Ready Template keys/versions; material changes receive a new version and exact historical versions remain resolvable.
- The current merchant-facing official catalog contains exactly 50 templates; industry changes ranking only, never membership.
- Applying a template is one atomic Draft mutation and retains A6 history, no-op, stale-write, tenant, provenance, baseline, Undo/Redo, and Published-isolation behavior.
- Product-card variants are presentation-only and consume `apps.catalog.services.product_card_service` truth for price, discount, stock, variants, URLs, wishlist, rating, and quick-add eligibility.
- Countdown presentation is not introduced without real commerce-domain timing truth.
- Mobile bottom navigation is RTL/accessibility/safe-area aware, uses real URLs/cart count, and remains mobile-only.
- Do not build Design Lab, `iframe.srcdoc`, Random Mix, locks, Compare, transient manifests, campaign JS, or arbitrary occasion overlays in A8.
- No push, force-push, destructive cleanup, Published-data mutation, protected-store reset, or unrelated rewrite.
- Every production behavior change follows RED-GREEN-REFACTOR; unexpected failures follow systematic root-cause debugging.

---

### Task 1: Evidence-Based Prototype and Existing-Library Inventory

**Files:**
- Create: `docs/qa_evidence/storefront_design_engine/a8_component_inventory.md`
- Create: `docs/qa_evidence/storefront_design_engine/a8_template_mapping.md`

**Interfaces:**
- Consumes: prototype `C:/Users/hp/Downloads/RastiSi_50_Storefront_Design_Lab_TABBED_THEMES (1).html`, repository specs, `global_region_registry.py`, `section_registry.py`, `appearance_registry.py`, and `storefront_appearance/registry.py`.
- Produces: one semantic mapping row for every prototype primitive and every `TPLS` entry 01..50; these stable keys are the single vocabulary used by Tasks 2-6.

- [x] **Step 1: Record the existing catalog and family counts**

Run:

```powershell
python manage.py shell -c "from apps.storefront_builder.storefront_appearance.registry import component_counts_by_family; from apps.storefront_builder.layout_preset_registry import list_ready_templates; print(component_counts_by_family()); print([(p.key,p.version) for p in list_ready_templates()])"
```

Expected baseline: 10 families, 46 components, and 8 current official templates.

- [x] **Step 2: Inventory prototype primitives without copying prototype runtime code**

For each header, hero, category/discovery style, card, product composition, section-order pattern, footer, bottom nav, palette/type/density/width/radius concept, record prototype key/name/family, visual description, nearest existing production primitive, reuse/new decision, proposed semantic key, trusted renderer, responsive contract, compatibility notes, and recipe usage.

- [x] **Step 3: Map all 50 prototype identities**

Write 50 numbered rows `01` through `50`, each with official semantic Ready Template key, version, palette/typography/density/width/radius, all ten Store Appearance selections, and section recipe. Preserve existing stable keys where they match a direction; never use `h1`, `x14`, `c-price`, `m5`, or another temporary prototype key as production identity.

- [x] **Step 4: Self-check completeness**

Run:

```powershell
rg -n '^\| (0[1-9]|[1-4][0-9]|50) ' docs/qa_evidence/storefront_design_engine/a8_template_mapping.md
```

Expected: exactly 50 numbered mapping rows.

- [x] **Step 5: Commit inventory**

```powershell
git add docs/qa_evidence/storefront_design_engine/a8_component_inventory.md docs/qa_evidence/storefront_design_engine/a8_template_mapping.md
git commit -m "docs(storefront-builder): inventory A8 template DNA"
```

### Task 2: Versioned Ready Template DNA Contract

**Files:**
- Modify: `apps/storefront_builder/layout_preset_registry.py`
- Create: `apps/storefront_builder/tests/test_a8_ready_template_contracts.py`

**Interfaces:**
- Consumes: `StoreAppearanceManifest`, `validate_store_appearance_manifest`, current `LayoutPresetDefinition` and registration functions.
- Produces: `LayoutPresetDefinition.store_appearance`, `get_layout_preset_version(key, version)`, version-preserving registration, and import-time recipe shape validation.

- [x] **Step 1: Write RED contract tests**

Add focused tests that construct definitions with duplicate `(key, version)`, invalid/empty versions, missing `schema_version`, incomplete ten-family selections, unknown keys, and renderer/template-path payloads. Assert duplicate versions raise `InvalidLayoutPresetError`; valid older and latest versions resolve independently; `list_ready_templates()` returns only latest official versions.

- [x] **Step 2: Prove RED**

Run:

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_contracts
```

Expected: failures because version lookup and `store_appearance` do not exist.

- [x] **Step 3: Add the minimal versioned contract**

Extend the frozen dataclass with:

```python
store_appearance: dict | None = None
```

Maintain `LAYOUT_PRESET_VERSION_REGISTRY: dict[tuple[str, str], LayoutPresetDefinition]`. `register_layout_preset()` must reject a duplicate exact identity, retain every registered version, and set `LAYOUT_PRESET_REGISTRY[key]` to the newly registered latest definition. Add:

```python
def get_layout_preset_version(key: str, version: str) -> LayoutPresetDefinition | None:
    return LAYOUT_PRESET_VERSION_REGISTRY.get((key, version))
```

Validate Ready Template DNA with the existing Store Appearance validator without introducing renderer discovery or DB access.

- [x] **Step 4: Prove GREEN and regress current catalog behavior**

Run:

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_contracts apps.storefront_builder.tests.test_u10_ready_template_catalog
```

- [x] **Step 5: Commit contract**

```powershell
git add apps/storefront_builder/layout_preset_registry.py apps/storefront_builder/tests/test_a8_ready_template_contracts.py
git commit -m "feat(storefront-builder): version Ready Template DNA"
```

### Task 3: Reusable A8 Production Components

**Files:**
- Modify: `apps/storefront_builder/global_region_registry.py`
- Modify: `apps/storefront_builder/section_registry.py`
- Modify: `apps/storefront_builder/storefront_appearance/adapters.py`
- Modify: `apps/storefront_builder/storefront_appearance/rendering.py`
- Modify: `apps/storefront_builder/services/render_service.py`
- Modify: `apps/catalog/templates/catalog/partials/product_card.html`
- Modify: `apps/catalog/static/css/product_card.css`
- Modify: `apps/storefront_builder/static/css/storefront_builder_v22.css`
- Create/Modify: only semantic reusable partials under `apps/storefront_builder/templates/storefront_builder/partials/global_header/`, `global_footer/`, `global_mobile_nav/`, and `sections/`
- Create: `apps/storefront_builder/tests/test_a8_component_library.py`
- Create: `apps/catalog/tests/test_a8_product_card_presentations.py`

**Interfaces:**
- Consumes: Task 1 reuse/new decisions and existing global/section/card registries.
- Produces: stable semantic component keys resolving to trusted existing or new generic implementations; `card_settings_for(state)` and `badge_settings_for(state)` pure presentation overlays consumed by the shared render service.

- [ ] **Step 1: Write RED registry and rendering tests**

Assert every new semantic key is unique, has responsive/RTL capabilities, resolves from an allowlist, and has no prototype ID in its key. For each new global region assert the resolved path is under `storefront_builder/partials/`. For card/badge selections render real `ProductCardState` fixtures covering normal, sale, out-of-stock, variable-product, and quick-add eligibility; assert only presentation changes and commerce truth remains unchanged.

- [ ] **Step 2: Prove RED**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_component_library apps.catalog.tests.test_a8_product_card_presentations
```

- [ ] **Step 3: Register only inventory-justified variants**

Add missing generic variants from Task 1. Card references use `card_style:<registered-style>`; badges use a bounded symbolic `badge_treatment:<registered-treatment>`; global regions use their existing `global_region:<region>:<variant>` adapter. Extend `_VIRTUAL_COMPONENTS` only for true no-render/default identities.

- [ ] **Step 4: Wire presentation overlays through A7**

In `_build_items_from_sections`, overlay the selected registered card/badge presentation into the in-memory `effective_settings["card"]` for product-bearing sections before context construction. Never mutate `section.settings` or write to DB. Continue using `product_card_service.build_product_card_state()` and the single shared product-card partial.

- [ ] **Step 5: Implement responsive/RTL/accessibility CSS and partials**

Bottom-nav partials use real named URLs/context actions, cart-count context, accessible labels, `env(safe-area-inset-bottom)`, mobile-only media queries, and content-offset classes. Header/footer/hero/card variants share tokens and existing partials rather than per-template bundles. No countdown is emitted unless backed by a real domain deadline supplied by existing commerce context.

- [ ] **Step 6: Prove GREEN and neighboring regressions**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_component_library apps.catalog.tests.test_a8_product_card_presentations apps.catalog.tests.test_product_card_service apps.storefront_builder.tests.test_r4_store_appearance_registry apps.storefront_builder.tests.test_r4_store_appearance_rendering apps.storefront_builder.tests.test_u2a_global_header_system apps.storefront_builder.tests.test_u2b_global_footer_system
```

- [ ] **Step 7: Commit component library**

```powershell
git add apps/storefront_builder apps/catalog/templates/catalog/partials/product_card.html apps/catalog/static/css/product_card.css apps/catalog/tests/test_a8_product_card_presentations.py
git commit -m "feat(storefront-builder): add reusable A8 components"
```

### Task 4: Exactly 50 Official Recipes, Diversity, and Coverage

**Files:**
- Create: `apps/storefront_builder/a8_ready_templates.py`
- Modify: `apps/storefront_builder/layout_preset_registry.py`
- Create: `apps/storefront_builder/storefront_appearance/inventory.py`
- Create: `apps/storefront_builder/tests/test_a8_ready_template_catalog.py`
- Create: `apps/storefront_builder/tests/test_a8_template_diversity.py`
- Create: `apps/storefront_builder/tests/test_a8_component_coverage.py`
- Modify: legacy tests that intentionally asserted the superseded eight-item catalog, retaining their eight historical templates as subset assertions.
- Create: `docs/qa_evidence/storefront_design_engine/a8_diversity_matrix.md`
- Create: `docs/qa_evidence/storefront_design_engine/a8_component_coverage.md`

**Interfaces:**
- Consumes: Task 1's 50-row mapping, Task 2's version contract, Task 3's registered keys, existing 64 palettes and typed appearance choices.
- Produces: `A8_READY_TEMPLATES`, exactly 50 latest official recipes, `recipe_signature(preset)`, `component_coverage(presets)`, and reproducible evidence matrices.

- [ ] **Step 1: Write RED catalog tests**

Assert exactly 50 latest official keys, 50 unique stable keys, `schema_version == 1`, all ten families present, every component resolvable, every `(key, version)` exactly resolvable, all recipes available in show-all independent of industry metadata, no resource IDs, and no executable/path fields.

- [ ] **Step 2: Write RED diversity/coverage tests**

Define a structural signature from header, mega menu, hero, layout, product view, card, badge, motion, footer, bottom nav, and normalized Home section sequence/presentation. Fail when two recipes differ only by palette/font, and fail for any active A8-advertised component unused by all 50 unless its semantic key is in an explicit documented exception tuple (expected empty for A8).

- [ ] **Step 3: Prove RED**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_catalog apps.storefront_builder.tests.test_a8_template_diversity apps.storefront_builder.tests.test_a8_component_coverage
```

- [ ] **Step 4: Implement 50 typed recipes**

Build recipes from small typed helpers for common non-home pages and bounded section entries. Preserve the eight existing stable keys and register their old versions before their material A8 versions. Add 42 semantic keys from Task 1. Each recipe selects all ten component families, uses registered palette/font/density/content-width/radius values, contains merchant-ID-free section composition, and differs structurally across multiple axes.

- [ ] **Step 5: Generate human-readable matrices from the same inventory functions**

Write the 50 rows and per-family component usage counts into the two evidence documents; do not hand-maintain a second conflicting dataset.

- [ ] **Step 6: Prove GREEN**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_catalog apps.storefront_builder.tests.test_a8_template_diversity apps.storefront_builder.tests.test_a8_component_coverage apps.storefront_builder.tests.test_u10_ready_template_catalog apps.storefront_builder.tests.test_ready_template_real_previews
```

- [ ] **Step 7: Commit recipes and matrices**

```powershell
git add apps/storefront_builder/a8_ready_templates.py apps/storefront_builder/layout_preset_registry.py apps/storefront_builder/storefront_appearance/inventory.py apps/storefront_builder/tests docs/qa_evidence/storefront_design_engine/a8_diversity_matrix.md docs/qa_evidence/storefront_design_engine/a8_component_coverage.md
git commit -m "feat(storefront-builder): define 50 Ready Template recipes"
```

### Task 5: Atomic DNA Application and Exact Version Resolution

**Files:**
- Modify: `apps/storefront_builder/services/preset_service.py`
- Modify: `apps/storefront_builder/services/r4_mutation_service.py`
- Modify: `apps/storefront_builder/services/template_preview_service.py`
- Create: `apps/storefront_builder/tests/test_a8_ready_template_application.py`
- Create: `apps/storefront_builder/tests/test_a8_shared_renderer.py`

**Interfaces:**
- Consumes: `LayoutPresetDefinition.store_appearance`, `get_layout_preset_version()`, and A7 `persist_store_appearance_manifest()`/resolver.
- Produces: exact-version template mutation, one-transaction full-DNA apply, normalized baseline snapshot including final Store Appearance state, and preview metadata for all 50.

- [ ] **Step 1: Write RED mutation/application tests**

Cover atomic one-revision apply, wrong-version failure, historical exact-version resolution, merchant catalog/business-data preservation, one-family sibling preservation, semantic no-op, provenance/baseline Undo/Redo, stale 409, tenant isolation, and unchanged Published state.

- [ ] **Step 2: Write RED shared-renderer tests**

For representative new header/footer/bottom-nav/hero/card recipes, assert Preview resolves Draft, Public resolves Published, both call the same A7 resolver/render service, state for another version is rejected, and query capture sees no writes during render.

- [ ] **Step 3: Prove RED**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_application apps.storefront_builder.tests.test_a8_shared_renderer
```

- [ ] **Step 4: Validate and apply full DNA before any write**

`preset_service.apply_preset()` validates `preset.store_appearance` with `validate_store_appearance_manifest()` before replacing sections, then persists the normalized manifest inside the existing `appearance_config` boundary in the same `transaction.atomic`. The immutable baseline's `appearance` member must contain the exact final normalized manifest. Remove the A6 transitional selector-only sync when redundant.

- [ ] **Step 5: Resolve requested template version exactly**

`appearance.template.apply` must call `get_layout_preset_version(template_key, template_version)` and reject missing/non-official versions without falling back to latest. Gallery/preview paths continue to use the latest official version list.

- [ ] **Step 6: Prove GREEN with A6/A7 regressions**

```powershell
python manage.py test apps.storefront_builder.tests.test_a8_ready_template_application apps.storefront_builder.tests.test_a8_shared_renderer apps.storefront_builder.tests.test_r4_store_appearance_mutations apps.storefront_builder.tests.test_r4_store_appearance_persistence apps.storefront_builder.tests.test_r4_store_appearance_rendering
```

- [ ] **Step 7: Commit integration**

```powershell
git add apps/storefront_builder/services apps/storefront_builder/tests
git commit -m "feat(storefront-builder): apply complete Ready Template DNA"
```

### Task 6: Capture Pipeline and 50-Template Visual QA

**Files:**
- Modify: `apps/storefront_builder/management/commands/capture_ready_template_previews.py`
- Modify/Create: generated versioned preview assets and metadata under `apps/storefront_builder/static/ready_template_previews/`
- Create: evidence under `docs/qa_evidence/storefront_design_engine/a8_captures/`
- Create: `docs/qa_evidence/storefront_design_engine/a8_final_qa.md`
- Modify: `apps/storefront_builder/tests/test_ready_template_real_previews.py`

**Interfaces:**
- Consumes: exact 50 latest recipes and canonical `rasti-mode-demo` seed/capture pipeline.
- Produces: 50/50 registry/render/Desktop/Mobile status, versioned gallery previews, capture metadata, broken-reference summary, and deferred-capability list.

- [ ] **Step 1: Write RED capture contract tests**

Assert the command enumerates the live 50-item official registry, remains hard-pinned to `STORE_SLUG = "rasti-mode-demo"`, writes metadata with exact template version, and supports batched `--only` capture without accepting a store argument.

- [ ] **Step 2: Prove RED, then remove eight-template assumptions**

```powershell
$env:PYTHONUTF8='1'; python manage.py test apps.storefront_builder.tests.test_ready_template_real_previews
```

Update help/count assertions and metadata logic only; do not introduce another capture renderer.

- [ ] **Step 3: Seed/reset only the canonical QA store**

Use the existing safe `seed_ready_template_fashion_demo`/capture-command path after checking its help and tests. Never pass or add an arbitrary merchant-store selector.

- [ ] **Step 4: Start the existing local server and capture all 50**

```powershell
$env:PYTHONUTF8='1'; python manage.py runserver 127.0.0.1:8000 --noreload
$env:PYTHONUTF8='1'; python manage.py capture_ready_template_previews --base-url http://127.0.0.1:8000 --full-qa --qa-output-dir docs/qa_evidence/storefront_design_engine/a8_captures
```

Capture Desktop and Mobile for every recipe; retain Tablet automated coverage and capture Tablet when the recipe's structure differs materially. Investigate every browser/console/network/capture failure at root cause.

- [ ] **Step 5: Inspect visual batches**

Review contact sheets/batches of 10 for clipping, overlap, missing regions, broken RTL, safe-area collision, empty fake offers, and palette/font-only duplication. Correct generic components/recipes, rerun focused tests, and recapture affected versions.

- [ ] **Step 6: Write final QA summary and commit evidence**

Record 50/50 registry/render/Desktop/Mobile results, any Tablet captures, broken references, coverage/diversity status, and intentional deferrals: full Design Lab, transient preview, Random Mix, locks, Compare, and typed occasion overlays.

```powershell
git add apps/storefront_builder/management/commands/capture_ready_template_previews.py apps/storefront_builder/static/ready_template_previews apps/storefront_builder/tests/test_ready_template_real_previews.py docs/qa_evidence/storefront_design_engine
git commit -m "test(storefront-builder): capture 50 Ready Templates"
```

### Task 7: Security Inspection, Full Regression Gate, Review, and Final Commit

**Files:**
- Modify: only files required by verified review findings
- Update: `docs/qa_evidence/storefront_design_engine/a8_final_qa.md`

**Interfaces:**
- Consumes: all prior tasks and required A8 acceptance gates.
- Produces: clean reviewed branch and final integration commit `feat(storefront-builder): add 50 Ready Template DNA recipes` if the branch remains safe to integrate locally.

- [ ] **Step 1: Run forbidden-coupling inspection**

```powershell
rg -n 'template_key\s*==|store\.slug|store\.pk|rasti-mode-demo|iframe\.srcdoc|renderer(_path)?\s*[:=]|template_path|<script|javascript:' apps/storefront_builder/a8_ready_templates.py apps/storefront_builder/storefront_appearance apps/storefront_builder/services/render_service.py apps/storefront_builder/services/preset_service.py
```

Classify every match; the canonical store slug may exist only in the capture command/tests, never generic runtime code.

- [ ] **Step 2: Run all focused and required regression suites**

```powershell
$env:PYTHONUTF8='1'; python manage.py test apps.storefront_builder.tests.test_a8_ready_template_contracts apps.storefront_builder.tests.test_a8_component_library apps.catalog.tests.test_a8_product_card_presentations apps.storefront_builder.tests.test_a8_ready_template_catalog apps.storefront_builder.tests.test_a8_template_diversity apps.storefront_builder.tests.test_a8_component_coverage apps.storefront_builder.tests.test_a8_ready_template_application apps.storefront_builder.tests.test_a8_shared_renderer apps.storefront_builder.tests.test_r4_store_appearance_contracts apps.storefront_builder.tests.test_r4_store_appearance_compatibility apps.storefront_builder.tests.test_r4_store_appearance_validation apps.storefront_builder.tests.test_r4_store_appearance_persistence apps.storefront_builder.tests.test_r4_store_appearance_registry apps.storefront_builder.tests.test_r4_store_appearance_mutations apps.storefront_builder.tests.test_r4_store_appearance_rendering apps.storefront_builder.tests.test_r4_foundation apps.storefront_builder.tests.test_r4_mutation_api apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_appearance apps.storefront_builder.tests.test_u2a_global_header_system apps.storefront_builder.tests.test_u2b_global_footer_system apps.storefront_builder.tests.test_layout_service apps.storefront_builder.tests.test_section_registry apps.storefront_builder.tests.test_u10_ready_template_catalog apps.storefront_builder.tests.test_ready_template_real_previews apps.catalog.tests.test_product_card_service
```

- [ ] **Step 3: Run framework/static gates**

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
git status -sb
```

- [ ] **Step 4: Request whole-branch code review**

Review the complete `2e8ca99406199220eb69033b03b77394b89f0dde..HEAD` diff for correctness, security, commerce semantics, renderer parity, and A8 scope. Fix Critical/Important findings with TDD, rerun impacted suites, and request scoped re-review.

- [ ] **Step 5: Freshly rerun every required gate after review fixes**

Repeat Steps 1-3 and recapture any template whose production renderer/CSS/recipe changed.

- [ ] **Step 6: Create the final integration commit if needed**

Confirm the branch is still `feature/storefront-builder-r4`, the worktree contains only A8 changes, and no conflicting owner work appeared. Then:

```powershell
git commit --allow-empty -m "feat(storefront-builder): add 50 Ready Template DNA recipes"
```

Do not push. Preserve the host-managed worktree and report exact start/end SHA, counts, files by responsibility, component before/after counts, 50 keys/versions, commands/results, capture status, matrices, final status, and next-phase deferrals.
