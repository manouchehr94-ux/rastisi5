# RastiSi R4 Storefront Design Engine + 50 Ready Templates — Implementation Plan

> **Execution rule:** follow the phases in order. Use TDD and focused tests inside every task. Do not begin the 50 Ready Templates until the Infrastructure Gate is completely green. Do not modify R3.

**Goal:** Extend the existing R4 Draft/Published, mutation, registry, preset, and shared-renderer architecture into one versioned Store Appearance engine, a reusable component library, Design Lab, real timed offers, and exactly 50 curated Ready Templates.

**Architecture:** `storefront_appearance` is a logical boundary inside the existing `apps.storefront_builder` app. It adapts existing registries and physical Draft fields rather than creating parallel registries, Drafts, or renderers. Stable component keys and typed settings are resolved server-side; Builder, Design Lab, Preview, and Public Store all use the existing R4 renderer.

**Canonical QA fixture:** `Rasti Mode Demo` (`rasti-mode-demo`). Demo content is never copied by a template apply operation.

**Official branch:** `feature/storefront-builder-r4`  
**Phase-1 checkpoint:** `e869b6a2ffd258d067e3d81b67c63c57cec39dc0`

---

## Safety and execution protocol

Before every task:

1. Confirm the active branch is `feature/storefront-builder-r4`.
2. Confirm the worktree contains only the expected current-task changes.
3. Run the smallest failing test first.
4. Implement only enough production code to make the focused test pass.
5. Run neighboring regression tests for the touched boundary.
6. Run `git diff --check` before commit.
7. Commit one logical unit only; never mix unrelated cleanup.

Never run `reset`, `stash`, `clean`, or `checkout` against R3. Never edit R3 source/tests merely to make an R4 gate green.

Repository-wide baseline debt recorded at Phase 1 remains explicit:

- three legacy guest-cart fixture errors;
- two superseded R3 fullscreen assertions.

These are not silently counted as R4 regressions and are not repaired through R3 changes. The Infrastructure Gate must still make every new/touched R4 and relevant neighboring suite green and must report the unchanged external baseline separately.

---

# PHASE A — Foundation / Infrastructure

## Task A1: Freeze the Store Appearance contracts and family catalog

**Create:**

- `apps/storefront_builder/storefront_appearance/__init__.py`
- `apps/storefront_builder/storefront_appearance/contracts.py`
- `apps/storefront_builder/storefront_appearance/families.py`
- `apps/storefront_builder/tests/test_r4_store_appearance_contracts.py`

**Contract:**

- `ComponentFamilyDefinition`: stable family key, label, storage adapter key, safe default, optional capability requirements, renderer role, and whether `off` is valid.
- `ComponentDefinition`: semantic stable key, family key, version, label, compatibility metadata, status/deprecation metadata, and existing-registry reference.
- `StoreAppearanceManifest`: schema version plus one selection per registered family.
- Stable keys must be normalized strings, unique within a family, and never contain file paths or executable expressions.
- Initial family keys: `header`, `mega_menu`, `hero`, `layout`, `product_view`, `card`, `badge`, `motion`, `footer`, `bottom_nav`.

**TDD:**

1. Write failures for duplicate keys, unknown families, invalid versions, path-like keys, missing defaults, and unsafe optional-family defaults.
2. Implement immutable dataclasses and pure validators.
3. Prove importing contracts requires no Django database access.
4. Run:

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_store_appearance_contracts
```

**Commit:** `feat(storefront-builder): define Store Appearance contracts`

---

## Task A2: Add adapters over existing registries

**Create:**

- `apps/storefront_builder/storefront_appearance/registry.py`
- `apps/storefront_builder/storefront_appearance/adapters.py`
- `apps/storefront_builder/tests/test_r4_store_appearance_registry.py`

**Reuse, do not copy:**

- `appearance_registry.py`
- `global_region_registry.py`
- `section_registry.py`
- `layout_preset_registry.py`
- existing Variant contracts and renderer paths

**Requirements:**

- Header/Footer/Bottom Nav resolve through `global_region_registry`.
- Hero/Product View/Card/Badge resolve through registered section/variant contracts or explicit adapters to them.
- Layout resolves through existing container/layout composition contracts.
- Motion reuses existing R4 appearance choices.
- Registry lookup is deterministic, allowlisted, and filesystem-discovery-free.
- Existing legacy/default keys map to safe components so old Drafts render unchanged.

**TDD:** unknown keys fail closed; duplicate adapter identity fails startup tests; every component points at a real registered implementation.

**Commit:** `feat(storefront-builder): adapt existing registries to Store Appearance`

---

## Task A3: Define compatibility and versioning metadata

**Create:**

- `apps/storefront_builder/storefront_appearance/compatibility.py`
- `apps/storefront_builder/tests/test_r4_store_appearance_compatibility.py`

**Requirements:**

- Recommendation scores/warnings are distinct from hard incompatibility.
- Header capability declares Mega Menu support; hard rejection occurs only for functional mismatch.
- Component version identity is explicit; compatible bug fixes retain identity, material redesigns receive a new key/version.
- Deprecated components remain resolvable for existing stores until a documented retirement migration exists.
- New optional families have an explicit safe default/off state.

**Commit:** `feat(storefront-builder): add appearance compatibility metadata`

---

## Task A4: Add typed manifest validation and safe defaults

**Create:**

- `apps/storefront_builder/storefront_appearance/validation.py`
- `apps/storefront_builder/tests/test_r4_store_appearance_validation.py`

**Requirements:**

- Validate full and partial manifests server-side.
- Reject unknown families, unknown component keys, raw HTML/CSS/JS, arbitrary renderer names, and non-typed settings.
- Produce a deterministic normalized manifest.
- Apply compatibility rules after registry resolution.
- Default an old Draft without component state to the exact current legacy visual behavior.

**Security tests:** path traversal, drive paths, template paths, script/style payloads, oversized keys, nested unbounded data, boolean-as-integer, and unknown schema version.

**Commit:** `feat(storefront-builder): validate Store Appearance manifests`

---

## Task A5: Persist appearance selections inside the existing Draft boundary

**Modify:**

- `apps/storefront_builder/models.py`
- `apps/storefront_builder/services/layout_service.py`
- `apps/storefront_builder/services/bootstrap_service.py`
- `apps/storefront_builder/storefront_appearance/persistence.py`
- focused model/layout tests

**Storage decision:** reuse the existing `StorefrontLayoutVersion` JSON boundaries. Add no second Draft model or lifecycle. The persistence adapter may normalize logical selections across existing `header_config`, `footer_config`, `appearance_config`, and typed section/composition state, but callers see one Store Appearance manifest.

**Requirements:**

- Existing Drafts require no visual migration.
- Published versions remain immutable.
- fingerprint/clone/restore/publish include all rendering-relevant component selections.
- defaults are explicit and deterministic.
- tenant ownership is always derived from the locked Draft/store relationship.

**Migration rule:** add a database migration only if inspection proves existing JSON storage cannot satisfy the contract safely. Prefer a compatibility/default strategy over a data rewrite.

**Commit:** `feat(storefront-builder): persist typed appearance selections on Draft`

---

## Task A6: Add independent and atomic R4 appearance mutations

**Modify:**

- `apps/storefront_builder/services/r4_mutation_service.py`
- `apps/storefront_builder/r4_views.py`
- `apps/storefront_builder/urls.py`
- `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`

**Mutations:**

- `appearance.component.update`: update exactly one family.
- `appearance.manifest.apply`: validate and apply one complete candidate atomically.
- `appearance.template.apply`: resolve a versioned recipe and apply it atomically.

**Hard proofs:**

- Changing Header preserves every sibling selection byte-for-byte after normalization.
- Invalid keys perform no write and create no history entry.
- stale `base_revision` returns 409 and performs no write.
- successful apply increments revision once and creates one semantic history operation.
- tenant/store isolation prevents cross-store IDs and Draft access.
- Public remains unchanged until Publish.

**Commit:** `feat(storefront-builder): add atomic appearance mutations`

---

## Task A7: Integrate the manifest with the shared renderer

**Modify:**

- `apps/storefront_builder/services/render_service.py`
- existing shared shell/global-region/section render helpers
- `apps/storefront_builder/tests/test_r4_store_appearance_rendering.py`

**Requirements:**

- Resolve Store Appearance once per rendered version and pass typed results into existing render items/context.
- Preview selects Draft; Public selects Published; both invoke the same resolver and renderer.
- Never trust renderer paths from persisted merchant state.
- Unknown legacy data falls back safely without hiding validation failures on new mutations.
- No Design-Lab-only render path.

**Parity tests:** same version + same store data produces equivalent component selection/context in Preview and Public.

**Commit:** `feat(storefront-builder): render Store Appearance through shared pipeline`

---

## Task A8: Upgrade Ready Template recipes to Store Appearance DNA

**Modify:**

- `apps/storefront_builder/layout_preset_registry.py`
- `apps/storefront_builder/services/preset_service.py`
- `apps/storefront_builder/services/template_preview_service.py`
- provenance/baseline tests

**Requirements:**

- Extend the existing `LayoutPresetDefinition`; do not add a parallel template registry.
- Recipe `schema_version=1` includes typed component selections and existing palette/typography/composition data.
- Apply preserves merchant catalog, prices, stock, media ownership, and business data.
- Baseline snapshot stores normalized stable selections, never renderer paths or Demo IDs.
- Reset to DNA uses the recorded immutable baseline, not a possibly changed live recipe.
- Industry changes recommendation ordering only; all official templates remain selectable.

**Commit:** `feat(storefront-builder): make Ready Templates appearance recipes`

---

## Phase A checkpoint

Run all new Phase A tests plus:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_foundation `
  apps.storefront_builder.tests.test_r4_mutation_api `
  apps.storefront_builder.tests.test_r4_vertical_slice `
  apps.storefront_builder.tests.test_appearance `
  apps.storefront_builder.tests.test_u2a_global_header_system `
  apps.storefront_builder.tests.test_u2b_global_footer_system `
  apps.storefront_builder.tests.test_layout_service `
  apps.storefront_builder.tests.test_u10_ready_template_catalog

python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

Write `docs/qa_evidence/storefront_builder/r4/design_engine/PHASE_A_FOUNDATION_GATE.md` and commit only with exact commands/counts/results.

---

# PHASE B — Component Library

Build families as real reusable components. Each task starts with contract/renderer tests, then templates/styles/scripts, then responsive and RTL tests. Reuse shared primitives and assets; no per-Ready-Template implementation forks.

## Task B1: Header library — exactly 20 production components

- Extend `global_region_registry.py` through the Store Appearance adapter.
- Preserve existing Header variants and add only the missing distinct compositions.
- Test search/account/cart/category capability, long Persian merchant names, RTL, keyboard interaction, and Mega Menu compatibility.

## Task B2: Mega Menu library — exactly 20 presentations

- Implement as a capability-aware family, independently selectable where supported.
- Reuse real merchant categories/collections/brands; never hard-code Demo IDs.
- Test empty, shallow, deep, image-rich, and long-label navigation.

## Task B3: Footer library — exactly 20 production components

- Preserve existing footer variants and extend the shared region.
- Test sparse/full merchant information, legal links, trust/payment/social data, RTL, and narrow screens.

## Task B4: Layout/composition library — exactly 20 components

- Build on existing Container/Row/Layout services.
- Store only stable composition keys/settings.
- Test content width, density, mixed rows, ordering, tablet collapse, and mobile stacking.

## Task B5: Hero/first-slider library — exactly 20 components

- Extend existing Hero section/variant contracts.
- Cover single image, split, editorial, campaign, product-led, collection-led, video-capable fallback, and mobile crops.
- Test 0/1/many slides, short/long Persian text, CTA safety, image absence, and autoplay/motion accessibility.

## Task B6: Product display library — exactly 15 components

- Reuse ResourceSource and section data services.
- Cover grid, carousel, editorial, dense, spotlight, tabs, grouped, and mobile-scroll compositions.
- Test normal/sale/timed/variant products and empty/partial catalogs.

## Task B7: Product Card library — exactly 30 components

- One card renderer contract with 30 materially distinct versioned components.
- Test geometry, image states, price states, stock, variants, CTA, badges, hover/focus, touch, RTL, and long titles.

## Task B8: Motion library — exactly 20 profiles

- Reuse the existing motion appearance channel.
- Honor `prefers-reduced-motion` and prevent motion from changing layout truth or accessibility.

## Task B9: Badge/discount/icon treatment — exactly 15 components

- Presentation only; consume commerce truth.
- Test normal sale, percentage/fixed display, timed active, timed expired, out-of-stock, and no-discount states.

## Task B10: Mobile Bottom Navigation — exactly 15 components

- Extend the existing `mobile_bottom_nav` global region and `footer_config` adapter.
- Test safe-area insets, cart count, active route, keyboard/focus, hidden desktop behavior, RTL order, and collision with sticky elements.

## Task B11: Component inventory and coverage instrumentation

**Create:**

- `apps/storefront_builder/storefront_appearance/inventory.py`
- `apps/storefront_builder/tests/test_r4_component_inventory.py`
- `docs/qa_evidence/storefront_builder/r4/design_engine/COMPONENT_INVENTORY.md`

Fail tests unless target counts, unique stable keys, registered renderers, responsive metadata, and coverage eligibility are correct.

---

# PHASE C — Design Lab

## Task C1: Add a separate R4 Design Lab route/tab

- Reuse R4 permissions, tenant resolution, feature gate, Preview URL, and shell conventions.
- Keep the normal Builder unchanged and simple.

## Task C2: Implement transient typed Lab state

- Browser state is ephemeral and may be locally restorable.
- Server validates every candidate manifest and returns an ephemeral preview token/manifest.
- No Draft/history mutation during exploration.
- No arbitrary raw JSON endpoint.

## Task C3: Shared-renderer device preview

- Desktop/Tablet/Mobile controls use the same R4 Preview/Public renderer.
- No `srcdoc`, cloned HTML, second template engine, or Lab-only component.

## Task C4: Random Mix, Locks, Compare, and Return to DNA

- Random Mix respects hard compatibility and recommendations.
- Locked families never change.
- Compare is deterministic and does not persist.
- Return to DNA uses recorded baseline provenance/snapshot.

## Task C5: Apply to Draft atomically

- Full server validation, tenant check, stale revision check, one transaction, one revision increment, one history entry.
- Browser QA proves 100 exploratory changes create zero Draft history entries before Apply.

---

# PHASE D — Timed Offer

## Task D1: Audit and define commerce-domain timed-offer truth

Inspect existing pricing/product/variant promotion models and services first. Extend the commerce domain only where required for `start`, `end`, normal price, and special price. Appearance must never decide price truth.

## Task D2: Add timezone-safe active/expired pricing behavior

- Use timezone-aware server truth.
- At expiry: temporary sale becomes inactive, product remains visible, normal commerce price/state returns.
- Test future, active boundary, end boundary, expired, missing bounds, invalid interval, and variant cases.

## Task D3: Expose typed timed-offer presentation context

- Renderer receives server-derived state/end timestamp only.
- Countdown JS is progressive presentation and corrects/removes itself at expiry.
- Card/Product View/Badge components never infer discounted truth from stale DOM.

## Task D4: Seed representative Rasti Mode Demo timed states

Add idempotent Demo-only seed behavior for future, active, and expired cases without coupling Ready Template apply to Demo content.

---

# PHASE E — INFRASTRUCTURE GATE

## Task E1: Automated contract/security gate

Must cover:

- unit and registry contracts;
- server validation/security;
- independent mutation;
- stale-write protection;
- Draft/Published isolation;
- Preview/Public renderer parity;
- invalid keys and compatibility failures;
- tenant/store isolation;
- template apply without Demo-data copying;
- version/default/deprecation behavior;
- normal/sale/timed/expired commerce states.

## Task E2: Responsive/RTL/accessibility gate

- Automated Desktop/Tablet/Mobile assertions for every component.
- RTL structure and Persian long-content cases.
- reduced motion, focus/keyboard, safe areas, and responsive overflow.

## Task E3: Deterministic Playwright Design Engine QA

Extend the existing R4 QA tool; do not introduce a second QA app unless technically required.

Scenarios include Builder component independence, Lab transient state, Random/Lock/Compare/DNA, one atomic Apply, Publish isolation, public parity, timed expiry, invalid key, expected 409, and zero unexpected console/network/page errors.

## Task E4: Performance sanity

- Registry lookup/import budget.
- renderer query-count and render-time comparison against Phase-1 baseline.
- Design Lab request cancellation/debounce.
- no per-template duplicate asset bundle.

## Task E5: Full Infrastructure Gate report

Run focused and neighboring suites first, then the justified full R4/infrastructure suite, Django check, migration drift check, Playwright, and performance sanity.

Create:

`docs/qa_evidence/storefront_builder/r4/design_engine/INFRASTRUCTURE_GATE.md`

If any required criterion fails, stop. Do not create Template 01.

---

# PHASE F — Exactly 50 Curated Ready Templates

## Task F1: Define curation taxonomy and diversity scoring

Create a matrix across Header, Mega Menu, Hero, layout, section sequence, Product View, Card geometry, Badge, Motion, Footer, Bottom Nav, rhythm/density, palette, and typography. Palette/font-only difference never passes.

## Task F2: Create the component coverage matrix

Every production component must appear in at least one official recipe or have an explicit Product Owner-approved exception before final acceptance.

## Tasks F3–F7: Five batches of ten

- Batch 1: Templates 01–10
- Batch 2: Templates 11–20
- Batch 3: Templates 21–30
- Batch 4: Templates 31–40
- Batch 5: Templates 41–50

For each template:

1. add one versioned DNA recipe to the existing Ready Template registry;
2. validate all component references and compatibility;
3. render against `rasti-mode-demo`;
4. capture Desktop and Mobile evidence;
5. inspect Tablet when composition warrants it;
6. prove no Demo catalog IDs/data are copied by apply;
7. run diversity comparison against all earlier accepted templates;
8. update component coverage matrix;
9. run focused registry/render/browser tests.

Each batch receives one QA report and Product Owner visual-review checkpoint before the next batch.

## Task F8: Final 50-template QA

Required final proofs:

- exactly 50 official Ready Templates;
- all available to every industry, with recommendation-only ranking;
- no palette/font-only duplicates;
- complete or explicitly approved component coverage;
- all registry references valid;
- Preview/Public parity;
- Desktop/Tablet/Mobile and RTL gates;
- active/expired timed-offer correctness;
- no Demo-data coupling;
- zero unexpected browser errors;
- Django check and migration check clean;
- full relevant regression suite green, with unchanged unrelated baseline debt separately disclosed.

Create:

`docs/qa_evidence/storefront_builder/r4/design_engine/FINAL_50_TEMPLATE_QA.md`

Only after this report is green may the project be declared complete.

---

# Owner review checkpoints

1. **Foundation Gate:** contracts, persistence, independent mutation, shared-renderer parity.
2. **Component Library:** inventory/counts and representative responsive screenshots.
3. **Design Lab:** transient exploration and atomic Apply browser evidence.
4. **Timed Offer:** active-to-expired evidence with product retained.
5. **Infrastructure Gate:** mandatory approval before Template 01.
6. **Batch reviews:** one review after each ten templates.
7. **Final Gate:** all 50, coverage matrix, diversity matrix, and full QA.

# Definition of done

A task is done only when its production change, focused tests, neighboring regressions, static checks, and evidence are complete. A phase is done only when its gate report is green. The initiative is done only when the Final 50 Template QA is green and the Product Owner accepts the evidence.
