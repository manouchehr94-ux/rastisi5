# RastiSi Storefront Appearance Convergence — 5-Phase Architecture Specification

**Date:** 2026-09-05  
**Status:** Architecture specification — Product Owner approved direction  
**Code baseline:** `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`  
**Repository:** `manouchehr94-ux/rastisi5`  
**Local reference repository:** `D:\Projects\RastiSi4_Golden_Manual`

---

## 1. Purpose

This specification defines the approved high-level architecture and delivery sequence for converging the RastiSi Storefront Appearance / Builder system.

It intentionally compresses the prior detailed architecture workflow into **five major phases**.

A phase is a major program milestone with one architecture gate. Individual engineering tasks may exist inside a phase, but tasks must not be promoted into additional top-level phases.

The goal is to make the program understandable and controllable for the Product Owner while preserving technical rigor, rollback safety, testability, and architectural evidence.

This specification does **not** authorize arbitrary refactoring or feature expansion outside the five-phase sequence.

---

# 2. Current-state conclusion

RastiSi does **not** need:

- a commerce rewrite;
- a new independent Preview engine;
- a new independent Public renderer;
- fifty independent storefront codebases;
- immediate deletion of legacy systems.

RastiSi already has valuable foundations that must be preserved:

- tenant/store authorization;
- Products / Brands / Categories / Collections;
- pricing, stock, cart and commerce logic;
- Draft / Published version lifecycle;
- shared section rendering;
- trusted section/component/global-region registries;
- recovery/history/baseline mechanisms;
- ProductCardData and shared standard product-card rendering;
- Ready Templates as recipes;
- existing component implementations and compatibility adapters.

The principal problem is **incomplete convergence of ownership**.

The project currently has a strong shared renderer but multiple active write and compatibility paths around Appearance state, recipe application, lifecycle, fragments, CSS/JS, and media references.

The architecture objective is therefore:

> **Converge ownership and contracts before expanding implementation count.**

---

# 3. Governing architecture rules

## Rule 1 — One concept, one canonical authority

For every editable concept, the target is:

```text
ONE CONCEPT
    =
ONE CANONICAL STATE
    +
ONE CANONICAL WRITE CONTRACT
    +
ONE CANONICAL EFFECTIVE RESOLVER
    +
ONE CLEAR OWNER
```

Compatibility adapters may remain temporarily, but they must not remain independent co-equal owners.

---

## Rule 2 — Preserve business-domain ownership

Appearance/Builder work must not duplicate:

- pricing;
- stock;
- catalog visibility;
- cart calculation;
- authentication;
- tenant/store authorization;
- Product/Brand/Collection domain ownership.

Visual components consume domain services; they do not replace them.

---

## Rule 3 — Preserve the shared rendering engine

Preview and Public should share component semantics.

They may intentionally differ in:

- Draft vs Published state;
- authorization;
- representative preview data vs shopper-request data;
- editor-only affordances.

They must not evolve into separate component-rendering architectures.

---

## Rule 4 — Approved normal Appearance precedence

The Product Owner has approved:

```text
Template DNA
      ↓
Store Global
      ↓
Page
      ↓
Section / Component
```

Interpretation:

- Template DNA provides curated defaults.
- Store Global overrides the template.
- Page may override a bounded subset of supported appearance values.
- Section/Component is the strongest normal local override.
- Any future store-wide forced style must be an explicit lock/force feature, not a hidden precedence side effect.

---

## Rule 5 — Variants are good; parallel engines are not

A component family may have many visual variants.

Desired family architecture:

```text
Component Family
      ↓
Canonical Data Contract
      ↓
Common Appearance Contract
      ↓
Component-specific Settings Schema
      ↓
Visual Variant
```

Variants must not independently recreate the same business-data or Appearance ownership logic.

---

## Rule 6 — Alias is not a visual implementation

A different marketing/component key does not count as a new visual implementation when it resolves to the same underlying renderer or behavior.

Future inventory and product claims must distinguish:

- marketing alias;
- recipe directive;
- virtual/no-op entry;
- actual renderer;
- actual visual implementation.

---

## Rule 7 — Migration before deletion

Legacy retirement order:

```text
KEEP
  ↓
MIGRATE / ADAPT
  ↓
PROVE
  ↓
DEPRECATE
  ↓
RETIRE
```

No code is removed solely because it is old or absent from current Ready Template recipes.

---

## Rule 8 — Evidence must match the risk

Examples:

- writer changes → preservation + stale-write tests;
- tenant changes → cross-store negative tests;
- media changes → reference/recovery/deletion tests;
- fragment changes → full→fragment behavior tests;
- CSS/JS changes → real browser/mobile evidence;
- template changes → declared→persisted→effective roundtrip;
- legacy retirement → stored-data + usage + rollback evidence.

---

# 4. Program structure

The entire convergence program is divided into exactly five top-level phases:

```text
PHASE 1
ARCHITECTURE & AUTHORITY
        ↓
PHASE 2
LIFECYCLE & SAFETY
        ↓
PHASE 3
VERTICAL-SLICE PROOF
Brand + Collection
        ↓
PHASE 4
BUILDER & LEGACY MIGRATION
        ↓
PHASE 5
DESIGN EXPANSION & CERTIFICATION
```

Individual tasks, batches, review gates, and commits may exist within these five phases.

They are not additional phases.

---

# PHASE 1 — Architecture & Authority

## 5.1 Goal

Eliminate the most dangerous split-brain ownership in the Appearance system.

Phase 1 combines two previously separate concerns:

1. **Canonical Writer convergence**
2. **Ready Template declared/applied DNA fidelity**

These belong together because applying a Ready Template is itself an Appearance write operation.

The architecture is not considered stable if normal field edits use one canonical writer while Template Apply bypasses or incompletely updates that authority.

---

## 5.2 Core invariants

For editable Appearance state:

```text
Concept
   ↓
Canonical State
   ↓
Canonical Writer
   ↓
Canonical Effective Resolver
```

For Ready Templates:

```text
Declared DNA
    =
Persisted Intended DNA
    =
Effective Resolved DNA
```

No hidden dependence on old Draft state may decide whether a recipe actually applies its declared families.

---

## 5.3 Scope

Phase 1 covers architecture ownership for:

- Store Appearance manifest;
- global Appearance values;
- palette/token selection;
- Header selection;
- Footer selection;
- Mobile Bottom Navigation selection;
- component-family selections;
- Section variant resolution;
- card/badge/motion selection where applicable;
- Template/Ready Recipe application;
- reset/application preservation rules;
- legacy mirrors as compatibility projections.

---

## 5.4 Product decisions required

The target hierarchy is already approved.

Before implementation proceeds deeply, the specification must resolve or explicitly defer the remaining safety-critical decisions, especially:

- local Section choice versus Store Global family choice;
- legacy editor migration policy;
- Section lock meaning;
- live identity/navigation vs versioned visual placement boundary;
- media retention policy.

Scope-heavy decisions may be deliberately deferred until Phase 3 evidence if they are not required to establish canonical authority.

---

## 5.5 Non-goals

Phase 1 does not:

- migrate every Section family;
- build more variants;
- redesign commerce;
- delete legacy routes;
- redesign CSS globally;
- create a new renderer.

---

## 5.6 Exit gate

Phase 1 passes only when:

1. every Appearance concept in scope has one documented canonical write owner;
2. legacy writers in scope either delegate to the canonical contract or have an approved temporary migration role;
3. unrelated Appearance state survives updates;
4. Ready Template Apply explicitly handles every declared family with approved semantics;
5. `Declared = Persisted = Effective` is proven for Ready recipe state;
6. global/local resolution follows the approved architecture semantics;
7. no new parallel Appearance source of truth has been introduced;
8. tenant ownership remains intact;
9. rollback/backward compatibility is documented and tested where existing stores are affected.

---

# PHASE 2 — Lifecycle & Safety

## 6.1 Goal

Make every Appearance/Builder-owned mutation explicitly safe with respect to:

- tenant/store;
- authorization;
- Draft/Published lifecycle;
- base revision;
- stale writes;
- atomicity;
- history/recovery;
- media lifecycle.

Phase 1 answers:

> Who owns the write?

Phase 2 answers:

> Where and under what conditions may that owner write?

---

## 6.2 Target mutation model

```text
Mutation
   ↓
Correct Store
   ↓
Authorized Actor
   ↓
Correct Lifecycle Target
   ↓
Current Base Revision
   ↓
Atomic Mutation
   ↓
History / Recovery
   ↓
New Revision
```

This applies to Appearance/Builder-owned state.

It does **not** imply forcing ordinary live business-domain editing into the Builder Draft model.

---

## 6.3 Scope

Phase 2 covers:

- section setting changes;
- structural Builder changes;
- publication;
- restore/discard/history interactions;
- version-associated media;
- stale-write handling;
- lock semantics after Product Owner decision;
- lifecycle-safe Template operations;
- same-store Published/Archived protection where relevant;
- recovery expectations.

---

## 6.4 Media is part of lifecycle safety

Media references may exist through:

- direct placement FKs;
- JSON background IDs;
- Draft state;
- Published state;
- Archived state;
- edit history;
- baseline/reset snapshots;
- legacy file fields;
- domain-owned Product/Brand/Collection media;
- static/template media.

The architecture must distinguish these reference classes.

No physical asset cleanup may occur while a supported rendered or recoverable state still depends on that asset.

---

## 6.5 Non-goals

Phase 2 does not:

- turn Product/Brand/Collection business content into Draft snapshots without a product decision;
- build new component families;
- certify all 50 Templates;
- remove legacy compatibility merely because R4 exists.

---

## 6.6 Exit gate

Phase 2 passes only when:

1. every Appearance-owned mutation has an explicit lifecycle target;
2. stale conflicting edits cannot silently overwrite newer state;
3. Published state cannot be accidentally edited through Draft tooling;
4. tenant/cross-store isolation is tested;
5. publish/restore/discard/history behavior remains recoverable;
6. media retention/deletion behavior respects all supported reference classes under the approved policy;
7. destructive migration/cleanup has rollback evidence;
8. legacy paths remaining outside the final boundary have an explicit temporary reason.

---

# PHASE 3 — Vertical-Slice Proof

## 7.1 Goal

Prove that the target architecture works end-to-end before generalizing it across all 36 Section types.

The approved pilot sequence is:

1. **Brand Showcase**
2. **Collection**

This phase prevents an abstract horizontal redesign from spreading unproven contracts across the whole codebase.

---

## 7.2 Why Brand first

Brand Showcase is the strongest existing foundation because it already has:

- one shared ordered store-scoped Brand loader;
- three visual variants;
- R4 SettingsSchema coverage;
- existing regression evidence;
- relatively low interaction complexity compared with Hero/Product.

Brand is not considered fully certified today; it is the best pilot foundation.

---

## 7.3 Why Collection second

Collection is deliberately different:

- it is more legacy-driven;
- it interacts with domain-owned Collection resources;
- it covers both showcase and page-level implications;
- it tests whether the Brand solution is genuinely reusable rather than Brand-specific.

---

## 7.4 End-to-end slice contract

Each pilot family must prove:

```text
Business Domain
      ↓
Canonical Data / Resource Contract
      ↓
Typed Content Schema
      ↓
Common Appearance
      ↓
Component-specific Settings
      ↓
Variant
      ↓
Canonical Mutation
      ↓
Draft / Published
      ↓
Shared Renderer
      ↓
Full Page / Fragment
      ↓
CSS / JS / Media
      ↓
Preview / Public
      ↓
Desktop / Mobile
```

---

## 7.5 Required family behavior

For each pilot:

- variants share one data contract where semantics allow;
- variants do not independently query the business domain without justification;
- common appearance works with approved inheritance;
- component-specific controls are typed and capability-aware;
- changing variant preserves compatible content/common appearance;
- unsupported controls are not shown;
- fragment behavior preserves the relevant effective settings;
- Preview/Public use the same component semantics;
- browser/mobile behavior is verified.

---

## 7.6 CSS/JS/fragment learning happens here

Phase 3 is where platform contracts for:

- component CSS;
- local styles;
- Preview assets;
- shared JS behavior;
- HTMX/fragment projections;
- media presentation

are proven in a real family before being generalized.

This is the core Hybrid strategy.

---

## 7.7 Exit gate

Phase 3 passes only when:

### Brand
- complete end-to-end family gate PASS.

### Collection
- complete end-to-end family gate PASS.

### Platform conclusion
- the common pattern works for two materially different families;
- no Brand-specific abstraction is being mistaken for a universal framework;
- reusable contracts are documented;
- any differences requiring family-specific semantics are explicitly documented;
- desktop and mobile browser evidence exists;
- rollback/regression evidence exists.

After Phase 3, a family may only leave the expansion freeze when it independently satisfies the same certification gate.

---

# PHASE 4 — Builder & Legacy Migration

## 8.1 Goal

Generalize the proven Phase 3 contracts across the remaining Builder and storefront architecture.

This is the largest migration phase.

---

## 8.2 Scope

### Section/family migration

Migrate the remaining controlled families incrementally, including as applicable:

- Hero
- Slider
- Category
- Product Showcase
- Ribbon / Promo
- Story / Editorial
- Newsletter
- Header
- Footer
- Mobile Bottom Navigation
- Product Detail
- Listing / Search
- Cart
- other registered controlled sections

Do not force semantically different components into one artificial data contract.

---

## 8.3 SettingsSchema convergence

Current discovery shows:

- 36 registered Section types;
- 4 with R4 `SettingsSchema`;
- 32 without.

Phase 4 does not mean blindly adding identical schemas to all 32.

Instead, every family must have:

- an appropriate typed content contract;
- declared common appearance capabilities;
- declared component-specific capabilities;
- explicit responsive behavior;
- explicit media behavior where relevant;
- canonical mutation support.

---

## 8.4 Non-Home Builder

The Builder must evolve beyond a Home-only R4 experience if RastiSi promises full-store design control.

The migration must cover the controlled architecture for:

- Listing
- Search
- Product Detail
- Collection
- Cart

without duplicating the business logic already owned by those domains.

---

## 8.5 Legacy migration

Legacy is removed only after evidence.

Required order:

```text
Replacement Contract
      ↓
Migration / Adapter
      ↓
Stored-data Compatibility
      ↓
Usage / Caller Evidence
      ↓
Tests
      ↓
Rollback Proof
      ↓
Deprecation
      ↓
Retirement
```

Current discovery explicitly proves that no broad legacy item is yet safe to delete without further evidence.

---

## 8.6 Stored-data / deployment evidence

Retirement may require targeted evidence such as:

- old editor adoption;
- legacy endpoint usage;
- persisted settings keys;
- selector/mirror mismatches;
- row/cell/block state;
- asset references;
- archived/history shapes;
- external integrations.

These are targeted migration inputs, not a reason to reopen broad architectural discovery.

---

## 8.7 Exit gate

Phase 4 passes only when:

1. all required product-facing families use approved ownership/contracts;
2. required non-Home Builder controls use the canonical architecture;
3. the common Appearance contract is consistently applied;
4. Preview/Public/fragment semantics are aligned for migrated families;
5. remaining legacy paths are explicitly classified;
6. any deleted legacy path has replacement, usage, data, test and rollback proof;
7. business domains remain unchanged except for approved integration adapters;
8. no new parallel engine or source of truth exists.

---

# PHASE 5 — Design Expansion & Certification

## 9.1 Goal

Resume product/design growth only after the architecture is safe.

This is the first phase where adding new visual variants is a primary objective.

---

## 9.2 Family-by-family unfreeze

Expansion freeze is removed per family, not globally.

Example:

```text
Brand
FROZEN
  ↓
CERTIFIED
  ↓
EXPANSION ALLOWED
```

while another family may remain:

```text
Hero
FROZEN
```

until it passes its own gate.

---

## 9.3 New visual implementations

Permitted after family certification:

- real Header variants;
- real Hero variants;
- real Product variants;
- real Collection variants;
- real Brand variants;
- real Footer variants;
- real Bottom Navigation variants;
- other product-approved design families.

A new alias mapping to an old renderer is not counted as a new visual variant.

---

## 9.4 MegaHeader / MegaFooter / MegaMenu

Do not create new standalone Mega families solely for taxonomy or marketing.

They become standalone families only if product requirements show that they require:

- independent configuration;
- independent reuse;
- independent data contract;
- independent lifecycle/appearance semantics.

Otherwise they remain advanced Header/Footer variants.

---

## 9.5 Seasonal / occasion design

After family architecture is stable, design expansion can include product-approved occasion themes such as:

- Nowruz;
- Yalda;
- Valentine;
- Iranian celebrations;
- Islamic occasions;
- other campaign themes.

These should reuse canonical design tokens/components rather than create one-off engines.

---

## 9.6 50 Ready Template certification

Current 50 recipes are code-distinct declarations, but that is not sufficient for claiming fifty certified full-store designs.

Certification requires:

```text
Known Baseline
     ↓
Apply Recipe
     ↓
Declared = Persisted = Effective
     ↓
Home
Listing
Search
Product Detail
Collection
Cart
     ↓
Header / Footer / Bottom Nav
     ↓
Desktop / Mobile
     ↓
Core Interactions
     ↓
Fragments / HTMX
     ↓
Visual + Functional QA
     ↓
CERTIFIED
```

Certification may reveal that some recipes need redesign, merging, or retirement.

The product goal is meaningful differentiated quality, not preserving the number 50 regardless of quality.

---

## 9.7 Exit gate

Phase 5 passes when the Product Owner can truthfully claim:

- certified component families;
- real rather than alias-only variant diversity;
- deterministic Ready Template Apply behavior;
- full-store consistency;
- desktop/mobile quality;
- stable interactions/fragments;
- proven Preview/Public parity under the approved model;
- evidence-backed 50-template certification or an approved revised template catalog.

---

# 10. Phase summary

| Phase | Name | Primary question | Architecture gate |
|---|---|---|---|
| 1 | Architecture & Authority | Who owns each Appearance write and what does a Template actually apply? | One writer + declared=persisted=effective |
| 2 | Lifecycle & Safety | Where and under what revision/lifecycle rules may that owner write? | Safe Draft/Published/revision/media/recovery |
| 3 | Vertical-Slice Proof | Does the architecture work end-to-end in real families? | Brand + Collection certified as architecture pilots |
| 4 | Builder & Legacy Migration | Can the proven contract replace fragmented Builder/legacy ownership across the product? | Required families/pages migrated; legacy retired only with evidence |
| 5 | Design Expansion & Certification | Can we safely grow the design system and make strong product claims? | Family unfreeze + real variants + full-store template certification |

---

# 11. Program-wide stop conditions

Work stops for architecture review if any task discovers:

- a second competing source of truth;
- a need to modify commerce logic to solve a presentation concern;
- a new Preview/Public renderer proposal;
- data loss or inability to roll back;
- unexplained Published mutation;
- cross-store ownership ambiguity;
- a required Product Owner decision not covered by the approved spec;
- a migration whose legacy data shape has not been established;
- a test failure indicating the task boundary was incorrectly scoped.

A task must not silently expand scope to solve such a finding.

---

# 12. Definition of Done philosophy

No phase is closed because:

- code was written;
- tests compile;
- a single screenshot looks good;
- an agent says the work is complete.

A phase closes only when its architecture gate has evidence.

Each implementation task inside a phase must:

1. start from a known clean baseline;
2. have bounded scope;
3. define preservation/non-goals;
4. use TDD where behavioral code changes;
5. run focused regression tests;
6. record relevant evidence;
7. receive review before the next architecture-sensitive task;
8. avoid feature expansion unrelated to its phase.

---

# 13. Immediate next step

The project is now positioned at:

```text
Discovery
    ✅ COMPLETE

Architecture direction
    ✅ 5 PHASES APPROVED

Next:
PHASE 1 — Architecture & Authority
```

Before changing application code, Phase 1 must be decomposed into an implementation plan with testable, reviewable tasks.

The first implementation plan must remain inside Phase 1.

It must not start:

- Phase 2 media/lifecycle generalization beyond what Phase 1 interfaces require;
- Brand/Collection migration;
- non-Home Builder expansion;
- legacy deletion;
- new visual variants;
- Template 51+.

---

# 14. Final approved roadmap

```text
PHASE 1
ARCHITECTURE & AUTHORITY
One Writer
+ Recipe Fidelity
+ Approved Precedence
        ↓
PHASE 2
LIFECYCLE & SAFETY
Revision
+ Draft/Published
+ Recovery
+ Media Lifetime
        ↓
PHASE 3
VERTICAL-SLICE PROOF
Brand
+ Collection
+ Browser/Fragment/CSS/JS proof
        ↓
PHASE 4
BUILDER & LEGACY MIGRATION
Remaining Families
+ Non-Home Builder
+ Evidence-based Legacy Retirement
        ↓
PHASE 5
DESIGN EXPANSION & CERTIFICATION
Real Variants
+ Seasonal Themes
+ Full-store Template Certification
```

---

# 15. Architecture commitment

The governing objective of this program is:

> **Reduce ambiguity before increasing implementation count.**

RastiSi's strong commerce, lifecycle, registry, recipe, and shared-rendering foundations are assets.

The project will converge ownership around those assets rather than replace them.

No phase may introduce a new parallel source of truth as a shortcut for migrating the existing one.

**Architecture specification approved direction: Five phases.**
