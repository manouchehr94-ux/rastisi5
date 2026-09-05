# RastiSi Storefront Appearance Convergence — Decision Baseline and Architecture Review Request

**Date:** 2026-09-05  
**Status:** Product Owner / Architecture decision baseline — **NOT an implementation plan**  
**Verified code baseline:** `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`  
**Repository:** `manouchehr94-ux/rastisi5`  
**Local working repository used for discovery:** `D:\Projects\RastiSi4_Golden_Manual`  
**Intended documentation branch:** `docs/storefront-appearance-convergence`  

---

## 0. Why this document exists

This document closes the broad discovery phase for the RastiSi Storefront Appearance / Builder architecture and establishes the shared starting point for the next phase.

Its purposes are:

1. give the Product Owner, Architect, Kiro, and any future engineering agent one factual view of where the project is now;
2. state what must be preserved and what must not be rewritten;
3. state the architectural risks that are already proven;
4. record the Product Owner rules that are already approved;
5. distinguish approved rules from still-open Product Owner decisions;
6. define our provisional convergence sequence without turning it into a file-by-file implementation plan;
7. ask Kiro to independently review that sequence and propose its own architecture-safe workflow **without writing implementation code**;
8. create a basis for comparing our workflow with Kiro's and selecting either one approach or a deliberate hybrid.

This document does **not** authorize implementation.

No agent should start refactoring, migration work, feature expansion, or component creation merely because this document exists.

---

# 1. Source evidence and discovery closure

The current baseline is supported by the following discovery package:

- `docs/architecture_audits/2026-09-05-storefront-appearance-builder-architecture-audit.md`
- `docs/architecture_audits/final_closure_pack/01-current-product-capability-inventory.md`
- `docs/architecture_audits/final_closure_pack/02-source-of-truth-and-writer-census.md`
- `docs/architecture_audits/final_closure_pack/03-component-contract-and-builder-coverage.md`
- `docs/architecture_audits/final_closure_pack/04-50-template-dna-reality-check.md`
- `docs/architecture_audits/final_closure_pack/05-runtime-parity-and-quality-readiness.md`
- `docs/architecture_audits/final_closure_pack/06-legacy-retirement-and-migration-readiness.md`
- `docs/architecture_audits/final_closure_pack/07-master-current-state-blueprint.md`

The discovery phase is considered sufficiently complete for architecture decisions.

Future broad codebase discovery should **not** be repeated unless one of these is true:

- the code baseline changes materially;
- a specific architecture decision cannot be resolved from the existing evidence;
- targeted production/staging evidence is required;
- an implementation task reveals a concrete contradiction in the current blueprint.

The next step is decision-making and convergence design, not another generic audit.

---

# 2. Verified baseline ledger

The following numbers are current-state facts at the verified baseline. They are different units and must not be conflated.

| Unit | Verified current-state count / meaning |
|---|---:|
| Major persisted Appearance authority groups | 5 |
| Major registry catalogs | 12 catalogs in 8 modules |
| Typed Store Appearance families | 10 |
| Registered section types | 36 |
| Sections with R4 `SettingsSchema` | 4 |
| Sections without R4 `SettingsSchema` | 32 |
| Explicit section VariantDefinition entries | 30 across 7 section types |
| Header registry variants | 22 |
| Footer registry variants | 16 |
| Mobile Bottom Navigation registry variants | 9 |
| Typed component keys | 119 |
| Symbolic component references | 90 |
| Registered renderer template paths compiled in discovery | 90 |
| Latest Ready Templates | 50 |
| Latest presets including internal presets | 55 |
| Retained key/version preset entries | 63 |
| Token-template profiles | 10 |
| Palettes | 64 |
| Normalized declared Ready-template DNA fingerprints | 50 / 50 distinct |
| Exact whole-recipe duplicate groups | 0 |
| Structurally distinct Home compositions | 27 |
| Distinct non-Home section sequence per Listing/Search/PDP/Collection/Cart | 1 each |
| Ready-used Header implementations | 12 |
| Ready-used Footer implementations | 8 |
| Ready-used Mobile Nav implementations | 7 |
| Ready-used Hero renderer implementations | 6 |
| Mutation-capable scoped HTTP routes | 86 |
| Explicit write routes | 76 |
| Additional initialization GET routes | 10 |
| Explicit R4 revision-safe endpoints | 3 |
| Mutation-capable routes outside R4 edit-revision protocol | 83 |
| Product capability groups | 40 |
| Capability status | 3 Working / 21 Partial / 6 Legacy-only / 4 Conflicting / 5 Missing / 1 Unknown |
| Confirmed conceptual overlaps in original audit | 14 |
| Legacy/compatibility retirement groups | 24 |
| Exact retirement blockers | 12 |
| Items proven safe to delete immediately | 0 |
| Architecture backlog | 2 P0 / 7 P1 / 5 P2 / 3 P3 |
| Focused closure tests executed | 52 |

Important interpretation rules:

- `119 component keys` does **not** mean 119 distinct visual implementations.
- `90 symbolic references` does **not** mean 90 storefront designs.
- `50 distinct declared DNA fingerprints` does **not** mean 50 browser-certified full-store designs.
- `83 routes outside R4 revision protocol` does **not** mean 83 security defects. Many are legitimate live-domain or compatibility paths, but they do not share one Builder concurrency contract.
- `0 families safe for unrestricted expansion` does **not** mean the current features are all broken. It means none satisfies the complete end-to-end expansion gate yet.

---

# 3. Executive current-state conclusion

RastiSi does **not** need a commerce rewrite and does **not** need a second Storefront rendering engine.

The project already has a substantial reusable foundation:

- tenant/store/membership boundaries;
- catalog, product, brand, collection, pricing, stock, cart and related business-domain services;
- a versioned layout lifecycle with Draft / Published / Archived states;
- stable section identities and recovery snapshots;
- one substantially shared section rendering engine;
- trusted renderer registries and allowlists;
- Ready Templates implemented primarily as recipes, not fifty independent storefront codebases;
- a shared standard product-card data contract and template;
- strong existing examples of shared family data loading, especially Brand Showcase;
- usable compatibility layers that protect existing data while the architecture evolves.

The main weakness is **incomplete convergence at ownership boundaries**, especially:

1. multiple write paths can modify or reconstruct related Appearance state using different preservation and concurrency rules;
2. declared Ready-template DNA is not guaranteed to become the complete effective applied DNA;
3. R4 revision safety does not yet wrap all active Builder/media/lifecycle editing paths;
4. full pages and dynamic fragments do not always receive the same Appearance/composition state;
5. media retention logic does not know about every supported reference representation;
6. CSS/JS/page-asset ownership is distributed enough that shared templates do not guarantee Preview/Public visual parity;
7. most section families do not yet have one uniform typed content/common-appearance/component-specific settings contract.

The correct strategy is **architecture convergence**, not a rewrite.

---

# 4. Foundations that are explicitly preserved

The convergence project must preserve these systems unless a later, evidence-backed decision explicitly says otherwise.

## 4.1 Business-domain ownership

Keep current domain ownership for:

- Product
- Brand
- Category
- MerchantCollection
- Pricing / discount / stock
- Cart
- Checkout / Order boundaries
- Authentication
- Store ownership / membership / tenant authorization
- Store identity and ordinary business content where explicitly designated live

Visual variants should consume these systems through contracts. They should not reproduce business logic.

## 4.2 Shared rendering foundation

Preserve and harden the existing shared rendering core rather than introducing a parallel Preview or Public engine.

Target direction:

```text
Draft / Published state
        ↓
Canonical effective appearance + composition
        ↓
Shared data/resource contracts
        ↓
Shared component / section registry
        ↓
Shared render engine
        ↓
Full page / fragment envelopes
        ↓
CSS / JS / media presentation
        ↓
Preview / Public
```

Preview and Public may intentionally differ in authorization, Draft-vs-Published state, editor affordances, representative preview data, or shopper request data. They should not independently own component semantics.

## 4.3 Version lifecycle and recovery

Preserve:

- Draft / Published separation;
- archived versions;
- clone / restore behavior;
- stable section/container identities where currently guaranteed;
- edit-history semantics;
- template baseline snapshots and provenance where they serve recovery/reset semantics.

An immutable snapshot is not treated as a harmful duplicate merely because it contains a copy of state.

## 4.4 Trusted registries and recipe-based templates

Preserve the allowlisted registry model and Ready-template recipe concept.

The convergence goal is to make the recipe declaration, persistence, effective appearance, and rendered result agree reliably.

---

# 5. Root causes already established

## 5.1 P0 — Competing / lossy Appearance writers

The same conceptual Appearance state can be affected through typed R4 commands, legacy dictionary forms, header/footer mirrors, preset/reset operations, history replay, live settings fallback and operational tooling.

The most dangerous case is not the existence of adapters. It is when two active write policies can disagree about which fields are authoritative or whether unrelated state must be preserved.

Required future invariant:

> One editable concept must have one canonical write contract. Compatibility paths may translate into that contract, but must not independently own the same concept.

## 5.2 P0 — Declared Ready-template manifest is not fully applied

The 50 Ready recipes declare complete typed component selections, but current Apply behavior does not guarantee that every declared family selection becomes the effective persisted manifest.

Therefore:

```text
Declared Template DNA
        ≠ guaranteed Effective Applied DNA
```

until this boundary is converged.

This is an architecture blocker for trustworthy template switching and 50-template certification.

## 5.3 P1 — Incomplete revision/lifecycle boundary

R4 uses a stronger active-Draft + base-revision + atomic mutation contract, but legacy section, media, lifecycle and selected live-placement editing paths remain reachable outside that protocol.

The convergence goal is not to force unrelated live business settings into the Builder revision model. It is to give every **Appearance/Builder-owned** mutation an explicit lifecycle target and concurrency policy.

## 5.4 P1 — Fragment state divergence

Confirmed examples include:

- Listing/Search HTMX results that do not carry the full card Appearance projection;
- Cart fragment rendering that does not carry the complete container composition envelope;
- Newsletter replacement responses that can lose a merchant-customized button label.

Dynamic fragments that reconstruct merchant-customizable UI must receive the same relevant effective state as the full page.

## 5.5 P1 — Media reachability mismatch

Supported references include:

- placement FKs;
- JSON `media_asset_id` background references;
- legacy file paths;
- Draft / Published / Archived placements;
- edit-history snapshots;
- baseline snapshots;
- domain-owned media;
- static/template media.

Current physical-deletion accounting does not cover every recoverable or rendered reference representation.

## 5.6 P1 — CSS / JS / Preview asset ownership

The presentation result can be affected by:

- resolved design tokens;
- theme rules;
- component CSS;
- `!important` counter-rules;
- inline fallback styles;
- page-specific CSS;
- Preview-only assets;
- copied or variant-specific JS behavior.

This does not imply that hardcoded CSS is always wrong. It means authority and precedence must be explicit and browser-verified.

## 5.7 P1 — Global/local variant semantics are unresolved

Today a non-default global manifest selection can mask a saved local Section variant.

A merchant can therefore save a valid local choice that is persisted but not effective.

This directly conflicts with the desired normal override model unless an explicit force/lock policy is introduced.

## 5.8 P1 — Template Apply is replacement, not content-preserving switch

Current Ready-template application rebuilds covered page composition. Recovery/checkpoint behavior exists, but recovery is not the same as preserving compatible merchant content in place.

Reset / Replace and Switch are different product operations and must not be conflated.

## 5.9 P1 — Family controls do not yet share one behavior contract

Hero/slider-like implementations demonstrate that similar-looking controls such as autoplay, arrows, loop, timing or media behavior are not yet universally meaningful across every implementation advertised under a broad family identity.

Before adding more variants, each exposed setting must either:

- have shared semantics across the declared family, or
- be explicitly component/variant-specific and only shown where supported.

---

# 6. Product Owner rules already approved

The following rules are approved project direction and should be treated as architecture constraints unless the Product Owner explicitly revises them later.

## R01 — No whole-system rewrite

Do not rewrite RastiSi commerce or business domains to solve Appearance architecture problems.

## R02 — One concept, one canonical authority

Desired invariant:

```text
ONE CONCEPT
    =
ONE CANONICAL STORAGE/STATE MODEL
    +
ONE CANONICAL WRITE CONTRACT
    +
ONE CANONICAL EFFECTIVE RESOLUTION RULE
    +
ONE CLEAR OWNER
```

Compatibility adapters may exist, but must not create an independent competing owner.

## R03 — Variants are allowed; parallel family engines are not

A family may have many visual variants.

Expected shape:

```text
Family
  ↓
Canonical data contract
  ↓
Canonical common appearance contract
  ↓
Component-specific schema
  ↓
Variant presentation
```

Not:

```text
PreviewBrandRenderer
PublicBrandRenderer
ReadyTemplateBrandRenderer
LegacyBrandRenderer
```

all independently owning the same semantics.

## R04 — Approved normal Appearance precedence

The Product Owner has approved this normal inheritance/override order:

```text
Template DNA
    ↓ default/base
Store Global
    ↓ override
Page
    ↓ override
Section / Component
    ↓ strongest normal override
```

Meaning:

- Template DNA supplies curated defaults;
- Store Global can customize those defaults;
- Page may override a bounded set of supported appearance values;
- Section/Component is the strongest ordinary local override;
- if a future feature intentionally forces a store-wide style, that must be an explicit force/lock policy, not a hidden precedence side-effect.

This is the approved D01 direction.

## R05 — Template is a curated versioned recipe, not a new rendering engine

Ready Templates should define a coherent composition/DNA using trusted components and appearance values.

## R06 — Full-store DNA matters

A final certified design must cover more than Home. At minimum the design system must produce coherent behavior for:

- Home
- Product Listing
- Search
- Product Detail
- Collection
- Cart
- Header
- Footer
- Mobile Bottom Navigation

## R07 — Feature expansion is frozen until convergence gates pass

Do not increase selector counts merely to make the library look larger.

Do not add new unrestricted:

- Header variants
- Hero variants
- Brand variants
- Collection variants
- Product-view variants
- Footer variants
- Bottom Navigation variants
- MegaHeader/MegaFooter families
- Template 51+

until the relevant architecture gates are satisfied.

Existing components remain supported and may be migrated/hardened.

## R08 — Alias is not a visual implementation

Marketing keys, recipe aliases, no-op directives and implementation references must be counted honestly.

Examples already proven:

- multiple Hero keys can resolve to the same renderer;
- `hero.none` does not currently represent a live hidden Hero behavior;
- some layout names imply geometry that the actual composition reference does not provide.

## R09 — Legacy is migrated, not mass-deleted

Current discovery proves **0 items safe to delete immediately**.

Default retirement order:

```text
KEEP
  ↓
MIGRATE / ADAPT
  ↓
PROVE replacement + data compatibility + rollback
  ↓
DEPRECATE
  ↓
RETIRE
```

## R10 — Evidence before closure

A phase is not complete merely because source compiles or unit tests pass.

Evidence must match the risk being changed: contract tests, integration tests, revision/tenant tests, browser/mobile proof, fragment proof, media recovery proof, migration rehearsal, or deployment census as applicable.

---

# 7. What is frozen and what may still change

## Frozen from feature expansion

All 18 product-facing family groups are frozen for unrestricted expansion under the current end-to-end gate:

1. Header
2. MegaHeader / MegaMenu
3. Hero
4. Slider
5. Category
6. Collection
7. Product Showcase
8. Brand Showcase
9. Ribbon / Promo
10. Story / Editorial
11. Newsletter
12. Footer
13. MegaFooter
14. Mobile Bottom Navigation
15. Product Detail
16. Listing / Search
17. Cart
18. Other controlled sections

`FROZEN` means "do not add more variants before the family/platform contract is safe," not "remove or disable the current family."

Brand Showcase is the strongest current **READY FOUNDATION** because it already has:

- one shared ordered store-scoped loader;
- three variants at the presentation boundary;
- an R4 schema for core content/source/variant fields.

It still lacks the complete platform convergence and browser-certification gate.

## Allowed during convergence

The convergence work may:

- unify writers;
- add preservation adapters;
- define missing typed contracts;
- move active paths behind one lifecycle/revision boundary;
- fix declared/applied recipe fidelity;
- harden media reference accounting;
- make fragments preserve effective Appearance;
- normalize CSS/JS ownership;
- migrate existing families to a common contract;
- add bounded Page appearance scope if approved;
- provide compatibility migrations and retirement evidence.

Those are not feature-library expansion; they are architecture stabilization.

---

# 8. Target architecture direction

The architecture direction is:

```text
BUSINESS DOMAINS
Products / Brands / Categories / Collections / Pricing / Cart / Content / Identity
        ↓
CANONICAL RESOURCE + DATA CONTRACTS
        ↓
CANONICAL APPEARANCE / BUILDER WRITE BOUNDARY
        ↓
DRAFT / PUBLISHED VERSION LIFECYCLE
        ↓
EFFECTIVE APPEARANCE RESOLUTION
Template DNA → Store Global → Page → Section
        ↓
COMPONENT FAMILY CONTRACTS
Data + Common Appearance + Specific Settings + Variant
        ↓
TRUSTED COMPONENT / SECTION REGISTRIES
        ↓
SHARED RENDER ENGINE
        ↓
SHARED RESPONSE PROJECTION
Full Page / HTMX / Fragment
        ↓
EXPLICIT PRESENTATION OWNERSHIP
Tokens / Component CSS / Local Styles / JS / Media
        ↓
PREVIEW / PUBLIC
Draft vs Published, not separate component semantics
```

The desired ownership pattern per concept is:

```text
Concept
   ↓
Canonical state
   ↓
Canonical writer
   ↓
Canonical effective resolver
   ↓
Canonical consumer contract
```

Legacy paths may temporarily adapt into the canonical writer. They should not permanently remain co-equal writers.

---

# 9. Canonical ownership goals by concept

This is target direction, not a claim that the current code already satisfies it.

| Concept | Target owner |
|---|---|
| Template / recipe identity | Versioned Ready-template application contract |
| Palette / global design tokens | Version Appearance contract |
| Store component selections | Typed Store Appearance manifest under one writer |
| Header/Footer/Nav selected implementation | Typed family selection, with content/config explicitly separated |
| Page appearance | Bounded Page override contract if D04 is approved |
| Section content | Section family schema + domain/resource references |
| Section common appearance | Common section appearance schema |
| Section specific settings | Family/component-specific typed schema |
| Section variant | Family contract, local explicit override under approved precedence |
| Layout geometry | Canonical Container/Cell composition model |
| Draft revision | Universal Appearance/Builder mutation boundary |
| Publish | Same lifecycle service behind one approved concurrency boundary |
| Media references | One complete reachable-reference/lifetime policy |
| Product prices/stock/eligibility | Existing business-domain services |
| Brand/Product/Collection business content | Existing domain ownership |
| Render semantics | Existing shared render engine, hardened |
| Fragment appearance | Shared effective projection appropriate to replacement scope |
| CSS authority | Explicit token/global/component/local contract |

---

# 10. Product Owner decisions still open

Only D01 has been approved in this document. D02–D12 remain open until explicitly approved by the Product Owner.

Kiro must not silently decide these during implementation planning.

## D02 — Local Section variant versus global manifest selection

**Current:** non-default global selection can mask local saved variant.  
**Recommended:** global selection acts as inherited default; explicit local selection wins. If a force-all capability is needed, model it explicitly as force/lock state.  
**Status:** OPEN.

## D03 — Legacy editor retirement strategy

**Recommended:** converge backend write/lifecycle contracts first, then migrate UI family-by-family and page-by-page with compatibility adapters. Avoid a one-shot cutover until capability/data/traffic evidence exists.  
**Status:** OPEN.

## D04 — Page Override capability

**Recommended:** add a bounded Page appearance scope for named use cases, not an unlimited arbitrary JSON override.  
**Status:** OPEN.

## D05 — Template Apply semantics

**Recommended:** keep explicit Reset/Replace as a deterministic operation and define a separate content-preserving Switch operation if merchant switching is a product promise.  
**Status:** OPEN.

## D06 — Per-variant settings memory

**Recommended:** do not add hidden per-variant memory initially. Preserve shared settings; add remembered variant-specific state only where real component-specific fields justify it.  
**Status:** OPEN.

## D07 — MegaHeader / MegaMenu / MegaFooter

**Recommended:** treat advanced menu/footer layouts as Header/Footer variants unless independent configuration/reuse requirements justify standalone families. Do not create a new family merely for marketing labels.  
**Status:** OPEN.

## D08 — `hero.none` semantics

**Recommended:** if offered as a live merchant choice, `none` must explicitly hide/disable Hero without deleting content. Otherwise remove/rename it from live selection and keep it recipe-only.  
**Status:** OPEN.

## D09 — Section lock semantics

**Recommended:** initially define current lock as structure-only unless the Product Owner explicitly needs a stronger content/appearance lock. Name it honestly in the UI/contract.  
**Status:** OPEN.

## D10 — Live identity/navigation after publish

**Recommended:** keep ordinary store identity/navigation/business content live; version-associated visual placements obey Draft/Publish. Make this boundary explicit.  
**Status:** OPEN.

## D11 — Media retention for archived/history states

**Recommended:** every state currently offered as recoverable must retain its referenced media until an explicit retention/expiry policy says otherwise.  
**Status:** OPEN.

## D12 — Family certification threshold before expansion

**Recommended:** after platform P0/P1 convergence, certify two representative families first — Brand Showcase and Collection — then proceed one family at a time. Hero follows after interaction/media convergence.  
**Status:** OPEN.

---

# 11. Our provisional convergence workflow

This section is intentionally a **phase architecture**, not an implementation plan. It does not specify file-by-file edits.

Kiro is explicitly asked to challenge the ordering and propose alternatives in Section 15.

## Phase 0 — Freeze and baseline protection

### Goal
Preserve the verified G2.3/discovery state and prevent new feature expansion from increasing ambiguity.

### Preconditions
- exact baseline known;
- discovery package available;
- no implementation started from audit findings.

### Exit evidence
- documentation-only baseline branch;
- approved list of preserved systems;
- approved freeze statement;
- no application changes in this phase.

---

## Phase 1 — Close Product Owner decisions and write the final convergence specification

### Goal
Resolve D02–D12 and convert approved policy into one target architecture specification.

### Why first
Writer, inheritance, template-switch, lock, media-retention and live-domain behavior cannot be safely implemented while their product semantics are undecided.

### Exit evidence
- D01–D12 decision register fully resolved;
- no contradictory precedence rules;
- approved final architecture spec;
- explicit non-goals and preserved business boundaries.

---

## Phase 2 — Establish the canonical write/preservation boundary

### Goal
Make every Appearance/Builder-owned edit converge on one preservation-aware command/lifecycle contract.

### Scope direction
- typed manifest and mirrors;
- global appearance;
- Header/Footer/Nav selection;
- section settings;
- structure actions;
- reset/history entry policies where applicable.

### Key invariant
Unrelated state cannot be erased by editing another field.

### Compatibility rule
Legacy routes may remain temporarily, but become adapters into the canonical contract rather than independent co-equal writers.

### Exit evidence
- mixed old/new edits preserve unrelated state;
- stale conflicting edits behave consistently;
- tenant isolation preserved;
- canonical writer matrix has no unexplained parallel owner.

---

## Phase 3 — Make Ready-template declared DNA equal effective applied DNA

### Goal
A Ready recipe must have deterministic, explicit semantics for every declared family selection and applicable setting.

### Key invariant
Applying a recipe cannot accidentally inherit unrelated prior manifest selections merely because the Apply path omitted them.

### Must distinguish
- Apply/Replace;
- Reset;
- future content-preserving Switch if approved.

### Exit evidence
For every declared family used by Ready recipes:

```text
Declared recipe
    = persisted intended state
    = effective resolved state
```

under the approved operation semantics.

---

## Phase 4 — Converge revision, lifecycle and mutation safety

### Goal
Every Appearance/Builder-owned mutation has an explicit lifecycle target and concurrency policy.

### Important distinction
Live business-domain editing is not automatically converted into Draft editing. The boundary must be intentional.

### Focus
- active Draft targeting;
- base revision;
- publish/restore/discard/history;
- section media and version-associated placements;
- lock semantics after D09.

### Exit evidence
- no Appearance-owned writer can silently bypass the approved concurrency model;
- Published state is not accidentally edited through Draft tooling;
- stale-client behavior is tested;
- rollback/recovery remains intact.

---

## Phase 5 — Complete media ownership and retention

### Goal
No supported rendered or recoverable state can reference media that cleanup considers unreferenced.

### Reference classes
- FK placements;
- JSON background IDs;
- legacy files;
- Draft;
- Published;
- Archived;
- history/baseline snapshots according to approved retention policy;
- domain-owned media;
- static/template assets as a separate class.

### Exit evidence
- complete reference graph or equivalent policy;
- deletion tests for every supported reference representation;
- migration/rollback evidence before any destructive cleanup.

---

## Phase 6 — Converge full-page and fragment effective state

### Goal
HTMX/AJAX/partial responses receive the merchant-owned Appearance/composition state relevant to the UI they replace.

### Known cases
- listing/search card settings;
- cart container state;
- newsletter custom response label;
- global/OOB elements that vary by selected Header/Nav implementation.

### Exit evidence
- full page → fragment interactions preserve effective visual/config state;
- no duplicate business logic introduced;
- fragment scope remains intentionally minimal.

---

## Phase 7 — Define CSS, JS and Preview/Public presentation ownership

### Goal
Make the cascade and behavior ownership explicit enough that shared templates produce predictable output.

### Principles
- tokens own theme/design values;
- component CSS owns component geometry/presentation;
- Section-local style owns explicit local override surface;
- inline fallback is permitted only where intentionally justified;
- `!important` is not automatically forbidden but must have an explicit authority reason;
- Preview uses the shopper page asset contract plus separate editor affordances, not a substitute Home stylesheet envelope for unrelated pages;
- identical JS behavior should have one authority.

### Exit evidence
- non-Home Preview/Public asset contract aligned;
- copied identical behavior removed or intentionally separated;
- representative desktop/mobile browser parity established.

---

## Phase 8 — Establish the common Appearance contract and bounded Page scope

### Goal
Define the shared settings every eligible section can inherit/override and the family-specific schema boundary.

### Candidate common contract categories
- background/surface;
- text/heading color where supported;
- typography;
- spacing;
- content width;
- border;
- radius;
- shadow;
- responsive visibility/layout;
- motion as decorative motion, separate from playback controls.

### Important
Not every component must expose every property. The contract must support capability declarations rather than fake universal controls.

### Page scope
Only add the Page override values approved in D04.

### Exit evidence
- explicit inheritance computation follows D01;
- defaults/global/page/local source is explainable to the editor;
- unsupported controls are not shown;
- section-specific settings remain separate from common appearance.

---

## Phase 9 — Pilot canonical family contracts

### Recommended pilot
1. Brand Showcase
2. Collection

### Why
Brand is already the strongest schema/shared-loader foundation. Collection tests a currently more legacy-driven family with domain-owned resources and page implications.

### Family acceptance gate
A pilot family should have:

- one canonical data/resource contract;
- no independent variant queries where not semantically required;
- one common appearance integration;
- typed component-specific settings;
- safe variant switching preserving shared content/settings;
- approved revision/media behavior;
- Preview/Public/full/fragment consistency where applicable;
- desktop/mobile browser proof.

### Exit evidence
A reusable family migration pattern proven on two materially different families.

---

## Phase 10 — Migrate remaining families and non-Home Builder coverage incrementally

### Goal
Apply the proven contract pattern family-by-family and page-by-page.

### Rule
Do not build a generic abstraction that destroys real semantic differences between Product, Story, Hero, Cart, etc.

### Exit evidence per family
Same acceptance gate as Phase 9.

### Non-Home direction
R4 or its successor must not remain Home-only if the product promises six-page controlled design.

---

## Phase 11 — Retire legacy paths only after evidence

### Goal
Remove proven obsolete compatibility only after replacement, data, usage and rollback gates pass.

### Required evidence classes
- stored-data census;
- endpoint/editor adoption or traffic evidence where needed;
- historical geometry/settings/media shape census;
- migration rehearsal;
- rollback verification;
- browser and integration parity.

### Invariant
Zero-recipe usage or an old filename is not deletion evidence.

---

## Phase 12 — Resume real component-family expansion

### Goal
Only now add genuinely new visual implementations where product value justifies them.

### Counting rule
A new key mapping to an existing renderer is not counted as a new variant.

### Expansion strategy
One certified family at a time.

---

## Phase 13 — Certify the 50 full-store designs

### Goal
Move from "50 code-distinct curated recipes" to "50 certified full-store designs".

### Required proof
- deterministic Apply from known baseline state;
- declared/effective DNA match;
- Home and all five non-Home page types;
- Header/Footer/Mobile Nav;
- desktop/mobile;
- core interactions;
- fragment behavior;
- visual/accessibility acceptance criteria;
- media and recovery stability.

### Important
Certification can conclude that some current recipes should be merged, retired, or redesigned. The product goal is meaningful differentiated quality, not protecting the number 50 at any cost.

---

# 12. Required evidence gates across the program

No phase should be closed with generic "tests passed" language.

Use evidence appropriate to the changed boundary.

| Risk changed | Minimum evidence type |
|---|---|
| Writer preservation | old/new mixed edit tests, unrelated-state preservation |
| Revision/lifecycle | stale-write conflict, active-Draft target, publish/restore tests |
| Tenant safety | cross-store negative tests |
| Recipe fidelity | declared → persisted → effective roundtrip |
| Media retention | deletion/recovery tests across every supported reference class |
| Fragment parity | full→fragment interaction tests with customized state |
| CSS/JS parity | real browser desktop/mobile checks |
| Family switching | switch/back, invalid values, content retention, capability assertions |
| Legacy retirement | data census + caller evidence + reversible migration rehearsal |
| 50-template certification | browser/state/device matrix on deterministic applied recipes |

---

# 13. Explicit non-goals

The convergence project must not accidentally become any of these:

- a rewrite of catalog, pricing, stock, cart, checkout or authentication;
- a second Preview rendering engine;
- a second Public rendering engine;
- a new template-specific data-query layer;
- a mass deletion of legacy code;
- a cosmetic CSS rewrite before ownership is defined;
- a "119 components" marketing count based on aliases;
- a "50 finished stores" claim based only on recipe fingerprints;
- a feature sprint that adds variants before the architecture gates;
- an unbounded generic Page/Section JSON settings system;
- a hidden change to product semantics such as locking, publish snapshots or media retention without Product Owner approval.

---

# 14. Deployment evidence still required later

Source discovery is closed, but source code cannot answer every deployment question.

Targeted evidence still required before specific retirement/migration actions may include:

- actual stores using old vs R4 editor entry points;
- visual-layout flag and Draft/Published page coverage;
- stored settings keys and mirror mismatches;
- legacy row/cell/block shapes;
- asset/file/JSON/history/archive reference census;
- traffic to legacy routes and external integrations;
- shared file-name incidence;
- real browser behavior under merchant-edited data.

These are targeted evidence requests, not justification for another broad architecture audit.

---

# 15. Kiro independent architecture review assignment — NO CODE

Kiro is now asked to act as an independent Principal Architect / Senior Full-Stack Lead / Migration Reviewer.

The purpose is **not** to repeat the discovery pack and **not** to start implementation.

Kiro must review:

1. the verified baseline code;
2. this decision-baseline document;
3. the original audit and closure reports if available;
4. the proposed Phase 0–13 workflow above.

Kiro should use targeted source inspection only where needed to validate or challenge a claim.

## 15.1 Strict constraints

Kiro must NOT:

- modify application Python;
- modify templates;
- modify CSS;
- modify JavaScript;
- modify tests;
- create migrations;
- mutate business/development data;
- implement any architecture change;
- refactor;
- fix any defect discovered during review;
- commit;
- push;
- merge;
- rebase;
- cherry-pick;
- reset/stash/clean/restore;
- start G3 or any feature-expansion task;
- generate a file-by-file implementation plan.

The only repository write permitted is Kiro's review report:

`docs/architecture_reviews/2026-09-05-kiro-storefront-appearance-convergence-workflow-review.md`

If the directory does not exist, creating that documentation directory is allowed.

After writing the report, Kiro must stop.

## 15.2 Kiro must independently evaluate our workflow

Kiro must not simply agree with Phase 0–13.

For each phase answer:

- Is the phase necessary?
- Is it in the correct order?
- What must precede it?
- Can it be safely combined with another phase?
- Should it be split?
- What is the smallest meaningful architecture gate?
- What evidence proves completion?
- What rollback/recovery concern exists?
- Which Product Owner decision blocks it?
- What existing system must explicitly remain untouched?

## 15.3 Kiro must propose 2–3 workflow approaches

At minimum:

### Approach A — Safety-first convergence

Maximize architecture boundary closure before family migration.

### Approach B — Vertical-slice convergence

Choose one representative family/page path and converge writer→state→render→fragment→browser end-to-end earlier, then generalize.

### Approach C — Hybrid

Kiro should propose this only if it genuinely combines the strongest properties of A and B.

For each approach provide:

- sequence;
- benefits;
- risks;
- assumptions;
- what could go wrong;
- evidence gates;
- effect on legacy migration;
- effect on future variant expansion.

Then recommend one approach.

## 15.4 Required comparison with our proposed sequence

Include a table:

| Our phase | Agree / Change / Merge / Split | Kiro concern | Kiro proposed position | Reason | Required evidence |
|---|---|---|---|---|---|

Do this for every Phase 0–13.

## 15.5 Review the open Product Owner decisions

For D02–D12:

- restate current behavior only if needed;
- assess engineering consequences of the recommendation in this document;
- identify hidden migration risks;
- state whether Kiro agrees with the recommendation;
- propose a better option if needed;
- do **not** silently mark it approved.

D01 is already approved and should be treated as a target architecture constraint unless Kiro finds a concrete contradiction that makes it unsafe. In that case Kiro must report the contradiction rather than changing policy.

## 15.6 Kiro must identify sequencing invariants

At minimum answer:

- Does canonical writer convergence need to precede recipe-fidelity work, or can they be one atomic architecture phase?
- Should revision/lifecycle convergence happen before or after media reachability?
- Can CSS/fragment convergence safely begin before family contracts?
- Should Brand/Collection pilot migration happen before all platform P1 items close?
- At what point is it safe to start non-Home R4 migration?
- At what point is it safe to start deprecating legacy editors?
- What is the earliest safe point to resume variant expansion?
- What is the earliest safe point to claim any Ready Template is "certified"?

## 15.7 Kiro must explicitly challenge overengineering

Identify any proposed abstraction/phase that may be unnecessary.

Use YAGNI:

- do not create new engines if existing shared services can be hardened;
- do not create standalone Mega families without a real product requirement;
- do not introduce per-variant memory unless real settings need it;
- do not force heterogeneous components into one artificial data contract;
- do not convert live business domains into version snapshots unless policy requires it.

## 15.8 Required Kiro report structure

Kiro's report must contain:

1. Executive verdict
2. Baseline verification
3. Facts accepted from discovery
4. Facts challenged or requiring qualification
5. Architecture principles Kiro agrees with
6. Architecture principles Kiro would change
7. Review of D01–D12
8. Review of Phase 0–13
9. Approach A — Safety-first
10. Approach B — Vertical-slice
11. Approach C — Hybrid, if justified
12. Recommended final workflow
13. Dependency graph / phase ordering
14. Architecture gates and exit criteria
15. Test/evidence strategy by phase
16. Legacy migration strategy
17. Rollback/recovery strategy
18. Systems that must not be rewritten
19. Remaining targeted deployment evidence
20. Top risks in our proposed workflow
21. Top risks in Kiro's proposed workflow
22. What should be done first after approval
23. What must NOT be done first
24. Final recommendation to Product Owner / Architect

The report must be architecture/process level, not a code implementation plan.

## 15.9 Final Kiro response in chat

Kiro should return only a concise summary after saving the review report:

- report path;
- baseline branch + HEAD;
- application code changed: NO;
- its recommended approach: A / B / Hybrid;
- first three architecture gates;
- biggest disagreement with our proposed workflow, if any;
- biggest agreement;
- Product Owner decisions required before implementation;
- one-paragraph verdict.

End with:

```text
NO IMPLEMENTATION OR REFACTOR WAS PERFORMED.
ARCHITECTURE WORKFLOW REVIEW COMPLETE.
STOP. WAIT FOR PRODUCT OWNER / ARCHITECT COMPARISON.
```

---

# 16. How we will compare our workflow with Kiro's

After Kiro returns its report, the Product Owner and Architect will not automatically accept either process.

We will compare them against five criteria:

## C1 — Architectural correctness

Does the sequence eliminate dangerous co-ownership without creating new parallel systems?

## C2 — Migration safety

Can current stores, Draft/Published state, media and compatibility behavior survive each phase with rollback?

## C3 — Product continuity

Does the sequence preserve current business/domain capabilities while improving Appearance architecture?

## C4 — Proof quality

Does each phase have evidence that proves its actual risk was closed?

## C5 — Delivery efficiency

Does the sequence avoid a long abstract rewrite before producing a verified end-to-end improvement?

We will then choose one of:

1. Our proposed workflow;
2. Kiro's proposed workflow;
3. A deliberate hybrid with explicit reasons for every merge/reorder.

Only after that comparison and Product Owner approval will we write the final Architecture Convergence Specification and the later implementation plan.

---

# 17. Decision / implementation boundary

This document is the last broad architecture-discovery handoff.

Current sequence:

```text
G2.3 baseline
    ✅
Architecture audit
    ✅
Final closure pack
    ✅
Discovery closed
    ✅
Product Owner D01 / governing rules
    ✅
This convergence decision baseline
    ✅
Kiro independent workflow review
    NEXT
Compare workflows
    THEN
Resolve D02–D12
    THEN
Final Architecture Convergence Specification
    THEN
Implementation Plan
    THEN
TDD / evidence-gated execution
    THEN
Family expansion
    THEN
50-template certification
```

No code should be written between this document and the workflow comparison merely to "get started."

---

# 18. Final architecture position

RastiSi already has enough working infrastructure that a broad rewrite would add risk rather than solve the proven problems.

The project must now reduce ambiguity, not increase implementation count.

The architectural objective is:

> preserve the strong business and shared rendering foundation; converge active Appearance writers and lifecycle semantics; make recipe declaration equal effective applied state; make full pages/fragments/media/presentation obey one explicit contract; migrate families into typed contracts; prove replacement and recovery; only then expand the design library.

The Product Owner's core concern — "if one concept lives in two or more places, fixing one will break another" — is supported at specific ownership boundaries. The response is not to remove every duplicate representation. The response is to distinguish legitimate snapshots/adapters from dangerous co-equal authorities, then give every editable concept one canonical owner.

**NO IMPLEMENTATION IS AUTHORIZED BY THIS DOCUMENT.**
