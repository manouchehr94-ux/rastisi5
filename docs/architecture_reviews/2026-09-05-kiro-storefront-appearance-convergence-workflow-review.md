# RastiSi Storefront Appearance Convergence — Independent Workflow Review (Kiro)

**Date:** 2026-09-05
**Reviewer role:** Principal Software Architect / Senior Full-Stack Engineer / Senior Migration Architect / Senior Technical Project Lead
**Review type:** ARCHITECTURE / PROCESS REVIEW ONLY — **NO IMPLEMENTATION**
**Code baseline under review:** `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`
**Repository:** `manouchehr94-ux/rastisi5`
**Documentation branch (source of handoff docs):** `docs/storefront-appearance-convergence`
**Local working branch during review:** `main` (HEAD `00e8991f862bcace9e4188592a32408ec5d662f8`; baseline `93c5afe` is an ancestor)

> This document is an independent second architecture opinion requested by the Decision Baseline §15. It does not approve any D02–D12 decision, does not authorize implementation, and does not repeat the closed discovery audit. Where it inspects source, it does so read-only against the verified baseline to validate or challenge a specific claim.

---

## 1. Executive verdict

The Decision Baseline is a high-quality, honest handoff. Its central diagnosis is correct and I independently confirmed its three most load-bearing claims in source at the baseline commit:

- **Competing/lossy writers are real** (P0). Multiple write profiles (F/T/L/M/V/C) can touch the same appearance concepts with different preservation rules, while only R4 (profile R) enforces revision safety.
- **Declared Ready-template DNA is not applied** (P0, finding A02). At the baseline, `preset_service.apply_preset` never reads `preset.store_appearance`, and R4's template apply synchronizes only four legacy selector families (`header`, `footer`, `bottom_nav`, `motion`). Hero/layout/product_view/card/badge/mega_menu selections declared by a recipe are **not** applied.
- **Global-over-local precedence inversion is real** (D02). In `render_service._build_items_from_sections`, a non-default manifest variant overwrites the saved section variant in-memory, so a merchant's locally saved section choice can be persisted yet not effective.

I **agree with the Baseline's core strategy**: converge ownership boundaries; do **not** rewrite commerce; do **not** build a second renderer. R01–R10 and D01 are sound.

**My verdict on the proposed Phase 0–13 process: KEEP the spine, but MERGE and REORDER the front half.** The proposal is safety-first and correct in intent, but as sequenced it front-loads too much horizontal platform work (Phases 2–8) before any single family is proven end-to-end, which delays real evidence and inflates rework risk. I recommend a **Hybrid (Approach C)**: a mandatory safety spine (writer + recipe-fidelity + revision) done together as one atomic authority phase, immediately followed by a **single thin vertical slice (Brand Showcase)** used as the proving ground for the remaining horizontal contracts (media, fragment, CSS, common appearance), then a second slice (Collection), then breadth.

**Recommended approach: HYBRID (C), spine-first then vertical-proven-horizontal.**

The single most important sequencing correction: **canonical writer convergence and recipe-fidelity convergence should be ONE phase, not two.** They are the same invariant ("one canonical write contract, and Apply is a first-class writer that produces the declared effective state") observed from two angles. Splitting them invites a window where the writer is unified but Apply still bypasses it — exactly the A02 defect, re-created.

---

## 2. Baseline verification

| Check | Result |
|---|---|
| Baseline commit exists | `git cat-file -t 93c5afea…` → `commit` ✅ |
| Baseline is ancestor of working HEAD | `93c5afe` is ancestor of `main` HEAD `00e8991` ✅ |
| Docs present on documentation branch | Decision Baseline, audit, and all 7 closure-pack reports present on `origin/docs/storefront-appearance-convergence` ✅ |
| Baseline commit subject | `fix(g2.3): section-background persistence (Defect C) + brand layout resilience (Defect A)` ✅ |
| Working tree clean before review | `git status --porcelain` empty ✅ |
| Application code changed by this review | **NO** ✅ |

Note on baseline vs. disk: the handoff audit was produced on a mirror (`D:\Projects\RastiSi4_Golden_Manual`, branch `audit/storefront-appearance-g23`) at the same commit. The workspace here is `rastisi5` on `main`; `main` has advanced past the baseline. All source validations in this review were run against `93c5afe` explicitly (via `git show <sha>:<path>`), not against `main`, so they match the evidence base.

---

## 3. Facts accepted from discovery

Accepted as correct (spot-validated where load-bearing):

1. **Single shared render core.** `render_service._build_items_from_sections` is the one section-rendering engine; `build_page_render_items` is the shared entry consumed by Preview, the public context service, cart, and the unpublished-store fallback (`build_render_items` delegates to it). There is no second renderer. **Validated.**
2. **A02 — declared ≠ applied.** `preset_service.apply_preset` writes appearance/header/footer/pages but contains no `store_appearance` reference; R4 `_LEGACY_SELECTOR_FAMILIES = ("header","footer","bottom_nav","motion")` is the complete set synchronized on template apply. **Validated.**
3. **Precedence inversion (D02).** `_build_items_from_sections` applies the manifest variant over the saved section `variant_setting_key`; a non-default global selection masks a persisted local one. **Validated.**
4. **Writer plurality.** 86 mutation-capable routes; only 3 revision-safe (R4 mutate/history/publish); 83 outside the R4 edit-revision protocol, most legitimately (live business editing), but not sharing one Builder concurrency contract. Accepted.
5. **Counting honesty.** 119 component keys ≠ 119 implementations; 90 references ≠ 90 designs; 50 declared DNA fingerprints ≠ 50 certified stores; 0 items safe to delete now. Accepted; this is the report's strongest quality.
6. **Non-Home reality.** All 50 recipes declare six page types, but non-Home composition is 1 sequence each for Listing/Search/PDP/Collection/Cart; R4 structure operations are Home-only. Accepted.
7. **Brand Showcase is the strongest ready foundation** (one store-scoped loader, three variants, an R4 schema). Accepted.
8. **Media reachability gap.** JSON `media_asset_id` background references are invisible to asset reference counting. Accepted (source-consistent with the persistence map).

---

## 4. Facts challenged or qualified

None of the discovery facts are wrong. I qualify their **interpretation** in four places that affect sequencing:

- **Q1 — "5 authority groups" is a concept count, not a defect count.** Only a subset are *co-equal competing writers* (chiefly the F/T/L/M profiles vs. R for the typed manifest, header/footer configs, and section settings). Container/cell geometry (profile S) and immutable baseline/history snapshots are largely *intentional* and should not be treated as convergence targets with the same urgency. **Consequence:** Phase 2 scope should be explicitly narrowed to the *contested* concepts, not "all writers," to avoid over-converging safe compatibility paths.

- **Q2 — A02 is not only a "recipe fidelity" bug; it is a writer-contract bug.** The reason declared DNA is lost is that **Apply is not routed through the canonical manifest writer.** This is why fidelity (Phase 3) cannot be separated from writer convergence (Phase 2): the fix for A02 *is* "make Apply a first-class canonical writer." **Consequence:** merge Phase 2 and Phase 3.

- **Q3 — The D02 inversion is a rendering-resolution policy, not a storage problem.** It lives in the effective-resolution step (`_build_items_from_sections`), not in persistence. It can be corrected independently of writers, but its correctness *depends on D02 being decided* first. **Consequence:** it is gated by a Product Owner decision, not by more engineering — reinforcing "decisions before code."

- **Q4 — Cart fragment "divergence" is partly by design.** Cart calls `build_page_render_items` directly (not via the full public context envelope), so it is inside the shared engine but outside the full-page composition wrapper. The fix is envelope/projection parity, **not** a new fragment renderer. **Consequence:** Phase 6 should be framed as "shared projection contract," and the non-goal "no second fragment engine" must be explicit.

---

## 5. Architecture principles accepted

- **R01 No rewrite** — accepted. The shared engine, lifecycle, registries, and recipe model are assets; a rewrite would add risk without addressing the proven boundary defects.
- **R02 One concept → one canonical authority** — accepted as the north star. This is the correct framing of every P0/P1.
- **R03 Variants yes, parallel family engines no** — accepted. Source supports it (shared loaders, one DTO).
- **R04/D01 precedence (Template DNA → Store Global → Page → Section, Section strongest normal override; force/lock explicit)** — accepted. This is the only sane inheritance model and it directly contradicts the current inverted behavior, which correctly makes the inversion a defect to fix rather than a policy to keep.
- **R05 Template = curated recipe** — accepted.
- **R06 Full-store DNA (6 page types + header/footer/mobile nav)** — accepted as the certification bar.
- **R07 Expansion freeze until gates pass** — accepted; essential to stop ambiguity growth.
- **R08 Alias ≠ implementation** — accepted; honest counting must persist into certification.
- **R09 Migrate, not mass-delete (0 safe now)** — accepted.
- **R10 Evidence before closure** — accepted; the evidence-by-risk table is excellent.

---

## 6. Architecture principles to change

I do not want to *change* any approved principle. I propose **three additions/sharpenings**, none of which alter D01:

- **P-ADD-1 — "Apply is a writer."** Elevate to a first-class principle: every template Apply/Reset/Switch must execute through the canonical appearance write contract and produce a fully specified effective manifest (no silent inheritance of prior selections). This closes A02 by construction and prevents its recurrence.
- **P-ADD-2 — "Capability-declared contracts, not universal controls."** The common appearance contract (Phase 8) must be capability-gated per component; do not synthesize fake universal controls. (The Baseline says this in prose; make it a hard principle so Phase 8 cannot drift into an over-general JSON settings bag — an explicit non-goal already.)
- **P-ADD-3 — "Prove one before spreading."** No horizontal contract (media, fragment, CSS, common appearance) is declared "done for the platform" until it is proven end-to-end through at least one real family slice. This converts abstract horizontal phases into evidence-producing work.

---

## 7. D01–D12 review

D01 is approved and I accept it. For D02–D12 I give an engineering position **without** marking any approved.

| Decision | Baseline recommendation | Kiro position | Engineering / migration consequence & better option (if any) |
|---|---|---|---|
| **D01** precedence ladder, Section strongest normal override; force/lock explicit | Approved | **Agree** | Directly contradicts current inverted resolution (validated). Making it real is a *resolution-order* change in `_build_items_from_sections` + a persisted force/lock flag. Low storage risk; needs fragment/full-page parity tests so the new order holds everywhere. |
| **D02** local section variant vs global manifest: global = inherited default, explicit local wins; force-all modeled as explicit force/lock | Open | **Agree** | This is the operational form of D01. Consequence: a data reconciliation is needed for stores that currently rely on the inversion (a merchant may have a "hidden" local choice that will suddenly become effective). Migration must **detect and surface** such masked-but-persisted values before flipping the order, with a rollback that restores prior effective output. **Do not flip resolution before this census.** |
| **D03** legacy editor retirement: converge backend contracts first, migrate UI family-by-family/page-by-page with adapters; no one-shot cutover | Open | **Agree** | Correct and matches R09. Better option: bind each retirement to a *per-family* adoption/traffic gate (closure pack G-gates) rather than a global one, so families retire independently as they certify. |
| **D04** Page Override: bounded named scope, not arbitrary JSON | Open | **Agree, with a modification** | Bounded scope is right. **Modify:** defer building D04 until the common appearance contract (Phase 8) exists and at least one family slice is proven; otherwise Page scope is defined against an unstable base. Page is a *layer in D01* and should be introduced with the inheritance engine, not before it. |
| **D05** Apply semantics: keep deterministic Reset/Replace; define separate content-preserving Switch if promised | Open | **Agree** | Consequence: Reset/Replace and Switch are different writers with different preservation contracts; conflating them is how content is lost. Whether Switch is built at all is a **product promise** question — engineering should not assume it. Recommend: ship deterministic Reset/Replace first (needed for certification), treat Switch as an opt-in later phase. |
| **D06** no hidden per-variant memory initially | Open | **Agree** | YAGNI-correct. Per-variant memory adds state-explosion and migration cost for speculative benefit. Add only where a component genuinely has variant-specific fields. |
| **D07** Mega* as Header/Footer variants unless real independent config/reuse justifies a family | Open | **Agree** | Source shows no standalone Mega registry; creating one now is marketing-driven duplication (violates R03/R08). Keep as variants until a concrete reuse requirement appears. |
| **D08** `hero.none`: must truly hide/disable without deleting content if offered live, else recipe-only | Open | **Agree** | Consequence: today `none` is virtual and 5 recipes omit Hero. If exposed as a live choice it needs explicit "hidden, content retained" semantics + media retention (ties to D11). Cleaner near-term: keep `none` recipe-only and hide it from live selection. |
| **D09** section lock = structure-only initially, named honestly | Open | **Agree** | Matches source (R4 has no section-lock guard in settings patch). A stronger content/appearance lock is a larger concurrency change; do not imply it in UI until built. |
| **D10** live identity/nav stays live; version-associated placements obey Draft/Publish; boundary explicit | Open | **Agree** | This is the correct non-goal boundary (do not drag business content into Draft). The only requirement is that the boundary is *documented and tested*, so editors know which surface they are changing. |
| **D11** retain referenced media for every recoverable state until explicit expiry policy | Open | **Agree — treat as a prerequisite invariant, not just a decision** | This must hold **before** any destructive media cleanup ships (Phase 5). The JSON background reference gap (validated) means current accounting is already unsafe; adopting D11 as an invariant is the guardrail. |
| **D12** certify Brand + Collection first, then one family at a time; Hero after interaction/media convergence | Open | **Agree** | Consistent with my Hybrid. **Modification:** use Brand as the *first vertical slice during* convergence (not only as a post-convergence certification), so it produces the media/fragment/CSS evidence earlier. Hero last is correct (it has the most interaction/media surface and the most alias inflation). |

**No D02–D12 decision is marked approved by this review.**

---

## 8. Phase 0–13 review

Legend: **Keep** / **Reorder** / **Merge** / **Split** / **Reject**.

| Our phase | Keep/Change/Merge/Split | Concern | Kiro position | Why | Exit evidence |
|---|---|---|---|---|---|
| **P0** Freeze & baseline protection | **Keep** | None | Keep as-is | Freeze stops ambiguity growth (R07); doc-only, zero risk | Doc-only branch; approved preserved-systems list; freeze statement; no app changes |
| **P1** Close D02–D12 + write convergence spec | **Keep (partial split)** | Resolving all 12 before any proof risks deciding D04/D05/D12 against an unstable base | **Keep but split:** approve the *safety-critical* decisions now (D02, D03, D09, D10, D11); defer *scope* decisions (D04, D05 Switch, D06, D07, D08, D12 timing) until slice evidence exists | Some decisions are prerequisites; others are premature without a proven contract. Deciding everything up front is false certainty | Decision register: mandatory set resolved; deferred set explicitly parked with trigger conditions; convergence spec (v1, revisable) |
| **P2** Canonical write/preservation boundary | **Merge with P3** | A window where writers are unified but Apply still bypasses them re-creates A02 | **Merge P2+P3 into one Authority phase**; narrow scope to *contested* concepts (Q1) | A02's root cause is that Apply is not a canonical writer; the two phases share one invariant | Mixed old/new edits preserve unrelated state; Apply routed through canonical writer; canonical-writer matrix has no unexplained co-owner |
| **P3** Declared DNA = effective applied DNA | **Merge into P2** | Separately sequenced, it can slip after writers "look done" | **Merge (see above)** | Same invariant, two views | Declared recipe = persisted = effective for every declared family under approved Apply/Reset semantics |
| **P4** Revision/lifecycle/mutation safety | **Keep, reorder earlier** | Media (P5) and fragment (P6) work touch mutation paths; doing lifecycle after them means re-testing | **Keep; run alongside/just after the P2+P3 Authority phase** | Every appearance writer needs a concurrency target *before* new writers/adapters are added downstream | No appearance writer bypasses the approved concurrency model; Published not editable via Draft tooling; stale-client tests; recovery intact |
| **P5** Media ownership & retention | **Keep, reorder after slice-1 starts** | Doing full platform media accounting before any family proves the reference graph is abstract | **Keep; adopt D11 as invariant immediately (block destructive cleanup); complete accounting *through* the Brand slice**, then generalize | The JSON-reference gap is real and dangerous; the *retention invariant* must precede cleanup, but the full graph is best proven on a real family first | Complete reference graph or policy; deletion/recovery tests for every reference class; migration+rollback before any destructive cleanup |
| **P6** Full-page/fragment parity | **Keep, reorder into slice-1** | Abstract "all fragments" work without a family produces weak evidence | **Keep; prove first on the Brand slice (and Cart)**; frame as shared *projection* contract, not a new engine | Cart-direct call is inside the shared engine; fix is envelope parity | Full→fragment interactions preserve effective state; no duplicate business logic; fragment scope minimal |
| **P7** CSS/JS/Preview-Public ownership | **Keep, reorder into slice-1** | Defining cascade ownership platform-wide before a family is theoretical | **Keep; establish token/component/local authority rules, then *prove* them on the Brand slice desktop+mobile** | Ownership rules are cheap to state, expensive to verify without a real page | Non-Home Preview/Public asset contract aligned; duplicated JS removed/separated; desktop+mobile browser parity on the slice |
| **P8** Common appearance contract + bounded Page scope | **Split** | Bundles a platform-wide contract with the D04 Page feature | **Split:** (8a) define capability-declared common appearance contract and prove on slice; (8b) add bounded Page scope only after D04 approved and the inheritance engine exists | Page scope is a D01 layer and must ride the inheritance engine, not precede it | (8a) inheritance follows D01, source explainable, unsupported controls hidden; (8b) only D04-approved values, bounded |
| **P9** Pilot family contracts (Brand, Collection) | **Keep, reorder earlier** | Treated as the *ninth* step, the pilot arrives after all horizontal work is nominally "done" | **Reorder: Brand slice begins right after the Authority+lifecycle phase and is the vehicle that proves P5–P8; Collection is slice-2** | A vertical slice converts abstract horizontal phases into evidence and surfaces integration defects early | Reusable family migration pattern proven on two materially different families (Brand + Collection) |
| **P10** Migrate remaining families + non-Home coverage | **Keep** | Risk of over-generalizing away real semantic differences | **Keep; enforce "no abstraction that destroys semantics"** | Correct breadth phase once the pattern is proven | Per-family acceptance gate met; non-Home Builder coverage where product promises 6-page design |
| **P11** Retire legacy after evidence | **Keep** | None | **Keep; bind to per-family adoption/traffic gates (D03)** | Matches R09; retirement is evidence-gated, family-scoped | Data census + caller/traffic evidence + reversible migration rehearsal + rollback + parity |
| **P12** Resume component-family expansion | **Keep** | None | **Keep** | Correct place; only after gates | New key mapping to existing renderer not counted; one certified family at a time |
| **P13** Certify 50 full-store designs | **Keep** | May over-protect "50" | **Keep; allow merge/retire/redesign of recipes** | Certification is about differentiated quality, not the number 50 | Deterministic Apply; declared=effective; 6 page types; header/footer/nav; desktop+mobile; interactions; fragments; a11y; media/recovery |

---

## 9. Approach A — Safety-first architecture convergence

**Shape:** Complete every horizontal platform contract (writers → recipe fidelity → revision → media → fragment → CSS → common appearance) across the whole platform *before* touching any single family, then pilot families, then breadth.

**Strengths:** maximal correctness ordering; no family is migrated onto an unstable base; every invariant is globally true before it is relied upon.

**Weaknesses:** long lead time before any *end-to-end verified* improvement; horizontal contracts are validated against abstractions and mock cases, so integration defects surface late and expensively; high rework risk if a real family reveals a wrong assumption in P5–P8; morale/PO-confidence cost of many phases with no visible certified outcome. This is essentially the Baseline's Phase 2→8 ordering.

**Verdict:** correct in spirit, but its front half over-serializes work that produces stronger evidence when proven on a real family.

---

## 10. Approach B — Vertical-slice convergence

**Shape:** Pick one family (Brand), and drive it end-to-end through *all* concerns at once — writer, recipe fidelity, revision, media, fragment, CSS, common appearance, certification — then repeat per family.

**Strengths:** fastest path to one certified, demonstrable full result; every concern is proven against real data early; excellent evidence quality.

**Weaknesses:** the P0 writer/authority defect and the A02/Apply defect are **cross-cutting** — they cannot be safely "sliced" per family, because a single canonical write contract and a single Apply-writer must exist platform-wide or two families will re-diverge. Doing writer convergence "inside" a Brand slice risks a Brand-specific writer, which violates R02/R03. Pure vertical-slice therefore under-serves the very P0 that motivated the project.

**Verdict:** correct for families and horizontal *presentation* contracts, wrong for the cross-cutting authority/lifecycle core.

---

## 11. Approach C — Hybrid (recommended)

**Shape (spine-first, then vertical-proven-horizontal):**

1. **Spine (must be platform-wide, cannot be sliced):** Freeze (P0) → resolve safety-critical decisions + spec v1 (P1 partial) → **Authority phase = canonical writers + Apply-as-writer + recipe fidelity (merged P2+P3)** → revision/lifecycle (P4) run alongside → adopt D11 retention **invariant** (blocks destructive cleanup).
2. **Slice-1 = Brand Showcase (vertical), which *proves* the remaining horizontal contracts:** media accounting (P5), fragment/projection parity (P6), CSS/JS ownership (P7), common appearance contract (P8a) — each generalized to the platform only after the slice proves it.
3. **Slice-2 = Collection (vertical):** confirms the pattern on a more legacy-driven, domain-resource, page-implicated family; hardens the reusable migration pattern.
4. **Breadth:** remaining families + non-Home coverage (P10) → bounded Page scope (P8b) once D04 approved → legacy retirement per family (P11) → resume expansion (P12) → 50-store certification (P13).

**Why C beats A and B:** it treats the cross-cutting authority core as a platform-wide spine (as A demands) while using a real family to generate integration evidence early (as B demands), and it defers scope decisions (D04/D05/D07/D12-timing) until there is a stable base to decide against. It directly closes A02 in the spine (where its root cause lives) and gates the D02 resolution flip behind a data census.

---

## 12. Recommended final workflow

```text
Phase 0  Freeze & baseline protection                         (KEEP, doc-only)
Phase 1  Resolve SAFETY-CRITICAL decisions (D02,D03,D09,D10,D11) + spec v1
         Defer SCOPE decisions (D04,D05-Switch,D06,D07,D08,D12-timing)   (KEEP, split)
Phase 2  AUTHORITY phase — merged:
           (a) one canonical appearance write/preservation contract (contested concepts only)
           (b) Apply/Reset routed THROUGH that writer  ← closes A02
           (c) declared DNA = persisted = effective                     (MERGE P2+P3)
Phase 3  Revision / lifecycle / mutation safety              (KEEP, run with/just after Phase 2)
         + adopt D11 media-retention INVARIANT (block destructive cleanup)
Phase 4  SLICE-1 Brand Showcase (vertical) — proves & then generalizes:
           media accounting (old P5) · fragment/projection parity (old P6)
           CSS/JS ownership (old P7) · common appearance contract (old P8a)
Phase 5  SLICE-2 Collection (vertical) — harden reusable migration pattern
Phase 6  Fix D02 resolution order (after masked-value census + rollback proof)
Phase 7  Breadth: remaining families + non-Home Builder coverage        (old P10)
Phase 8  Bounded Page scope (old P8b) — only after D04 approved
Phase 9  Legacy retirement, per-family, evidence-gated                  (old P11)
Phase 10 Resume component-family expansion                             (old P12)
Phase 11 Certify 50 full-store designs                                 (old P13)
```

The 14-phase proposal collapses to ~12 with the two most important changes being **P2+P3 merge** and **pulling the Brand slice forward to prove P5–P8**.

---

## 13. Dependency graph

```text
P0 Freeze
  └─> P1 Decisions(spec v1)         [D02,D03,D09,D10,D11 mandatory before flips]
        └─> P2 AUTHORITY (writers + Apply-as-writer + fidelity)   ← closes A02
              ├─> P3 Revision/lifecycle  (needs one write contract to pin concurrency)
              │      └─> D11 retention invariant  (blocks any destructive media cleanup)
              └─> P4 SLICE-1 Brand  (needs canonical writer + lifecycle in place)
                     ├─ proves ─> media accounting (was P5)
                     ├─ proves ─> fragment/projection parity (was P6)
                     ├─ proves ─> CSS/JS ownership (was P7)
                     └─ proves ─> common appearance contract (was P8a)
                          └─> P5 SLICE-2 Collection (reuse pattern; page-implicated)
                                └─> P6 D02 resolution flip
                                      (GATE: masked-value census + rollback proof)
                                      └─> P7 Breadth + non-Home
                                            ├─> P8 Bounded Page scope (GATE: D04 approved)
                                            └─> P9 Legacy retirement (GATE: per-family adoption/rollback)
                                                  └─> P10 Resume expansion
                                                        └─> P11 Certify 50
```

**Hard ordering invariants:**
- Nothing that flips effective resolution (D02) ships before the masked-value census + rollback proof.
- No destructive media cleanup ships before the D11 retention invariant + full reference graph.
- No family migration begins before one canonical writer + Apply-as-writer + lifecycle exist.
- No expansion (new variants/Template 51+) before at least two families are certified and the pattern is proven.

---

## 14. Phase gates and exit criteria

- **G-Freeze:** doc-only baseline; preserved-systems list; expansion freeze acknowledged. No app changes.
- **G-Decisions:** D02/D03/D09/D10/D11 resolved; scope decisions explicitly parked with trigger conditions; spec v1 with explicit non-goals.
- **G-Authority (the critical gate):** (1) contested appearance concepts have exactly one canonical writer; legacy routes are adapters, not co-owners; (2) mixed old/new edits preserve unrelated state (regression proof); (3) **Apply/Reset execute through the canonical writer**; (4) for every declared family in every recipe: `declared = persisted = effective` under approved semantics (this is the A02 closure gate). No unexplained co-owner in the writer matrix.
- **G-Lifecycle:** no appearance writer bypasses the approved concurrency model; Published not editable via Draft tooling; stale-client 409 behavior tested; recovery/rollback intact. D11 retention invariant active.
- **G-Slice-1 (Brand):** one canonical data/resource contract; one common-appearance integration; typed component-specific settings; safe variant switching preserving shared content; approved revision/media behavior; Preview/Public/full/fragment consistency; desktop+mobile browser proof.
- **G-Slice-2 (Collection):** same gate on a materially different, page-implicated, domain-resource family; reusable pattern documented.
- **G-D02-flip:** masked-but-persisted local values censused and surfaced; resolution order changed; before/after effective-output diff reviewed; rollback proven.
- **G-Breadth (per family):** same acceptance gate as Slice-1/2.
- **G-Retire (per item):** data census + caller/traffic evidence + reversible migration rehearsal + rollback + parity. "Zero recipe usage" is **not** evidence.
- **G-Certify (per recipe):** deterministic Apply from known baseline; declared=effective; 6 page types + header/footer/mobile nav; desktop+mobile; core interactions; fragment behavior; a11y/visual criteria; media/recovery stability.

---

## 15. Evidence/testing strategy

I accept the Baseline's evidence-by-risk table and add emphasis:

- **Authority phase:** contract tests for the single writer; **mixed-editor stale-write** tests (old form + R4 command interleaved) proving unrelated-state preservation; **declared→persisted→effective roundtrip** for every declared family across all 50 recipes (this is the mechanized A02 gate); cross-tenant negative tests.
- **Lifecycle:** stale-revision 409 tests; "Published not mutated via Draft tooling" tests; undo/redo/publish/restore recovery tests.
- **Slices:** real-browser desktop+mobile parity (Preview vs Public); full-page→fragment interaction tests with merchant-customized state (the newsletter-label, cart-container, listing-card cases named in discovery); media deletion/recovery across FK, JSON background, legacy file, Draft/Published/Archived, and snapshot classes.
- **D02 flip:** a data census script (read-only in staging) enumerating stores where a local variant is persisted but masked, plus a golden before/after effective-render diff.
- **Certification:** deterministic Apply matrix on a known-empty baseline (to neutralize A02-style start-state dependence), across the 6-page + regions + device matrix.

Do **not** accept "unit tests pass" or "Django check clean" as phase-closure evidence (the audit itself notes its 42 passing tests set up no DB and are not integration proof).

---

## 16. Migration strategy

- **Adapter-first, per the Baseline:** legacy routes translate into the canonical writer; they do not remain co-equal owners.
- **Census before flip:** any change that alters *effective* output (chiefly the D02 resolution flip and A02 closure) must be preceded by a read-only staging census of affected stored state and a reviewed before/after effective-output diff.
- **Family-by-family, page-by-page:** each family migrates behind its acceptance gate; non-Home coverage follows once R4 (or successor) is no longer Home-only.
- **Media:** treat D11 retention as an invariant from the start; build the complete reference graph (including JSON `media_asset_id`) and prove deletion/recovery per reference class *before* any physical cleanup.
- **Rollback baked in:** every migration step retains a pre-change checkpoint (version snapshot + referenced assets) and a proven restore path.

---

## 17. Legacy retirement strategy

- Follow R09: KEEP → MIGRATE/ADAPT → PROVE (replacement + data compatibility + rollback) → DEPRECATE → RETIRE.
- **Per-family, evidence-gated retirement** (D03), not one-shot cutover: an editor/route retires only after its replacement family is certified, its stored-data shapes are censused and migratable, caller/traffic evidence shows safe removal, and rollback is proven.
- **0 items are safe to delete now** — accepted. The first legitimate retirements are the legacy appearance/header/footer forms (L02/L03) once the Authority phase makes them pure adapters and Slice-1 proves the replacement.
- An old filename or zero recipe usage is explicitly **not** retirement evidence.

---

## 18. Rollback/recovery strategy

- Preserve Draft/Published separation, archived versions, clone/restore, stable identities, edit history, and baseline snapshots throughout (immutable snapshots are recovery assets, not duplicate authorities).
- Every effective-changing phase (Authority/A02, D02 flip, media cleanup, each family migration) ships with: a pre-change checkpoint, a reviewed before/after diff, and a rehearsed restore that reproduces prior effective output.
- Concurrency rollback: stale-client conflicts must fail closed (409) rather than silently overwrite — extend this guarantee to every appearance writer, not only R4.

---

## 19. Systems that must remain untouched

Reaffirmed (R01, §4, §13 non-goals):

- Commerce/business domains: Product, Brand, Category, MerchantCollection, pricing/discount/stock, Cart, Checkout/Order, Authentication, tenant/store/membership authorization, live store identity/business content.
- The single shared render engine (`render_service`) — harden, do not fork.
- The versioned lifecycle, stable identities, history/baseline snapshots.
- Trusted registries/allowlists and the recipe-based Ready-template model.
- The shared product-card DTO and shared family loaders (e.g., Brand loader).

**No second Preview engine, no second Public engine, no second fragment engine, no per-template data-query layer.**

---

## 20. Remaining targeted deployment evidence

Source cannot answer these; gather them as *targeted* requests (not another broad audit), before the actions they gate:

- Stores using legacy vs R4 editor entry points (gates D03/L01 retirement).
- Stores with a local section variant persisted but masked by a non-default global manifest (gates the D02 flip).
- Visual-layout flag coverage and Draft/Published page coverage per store.
- Stored settings keys and manifest/mirror mismatches (gates writer convergence census).
- Legacy row/cell/block shapes (gates structure retirement L05).
- Full asset/file/JSON-background/history/archive reference census (gates media cleanup + D11).
- Traffic to legacy routes and external integrations (gates retirement).
- Real browser behavior under merchant-edited data (gates certification).

---

## 21. Risks in our (Baseline) workflow

- **R-1 (highest): P2/P3 split re-opens A02.** A window where writers are unified but Apply still bypasses them recreates the exact declared≠applied defect. *Mitigation: merge them (my Phase 2).*
- **R-2: Horizontal-before-slice = late integration defects.** P5–P8 validated against abstractions surface real defects only at P9, when rework is expensive. *Mitigation: pull the Brand slice forward.*
- **R-3: Deciding D04/D05/D12-timing in P1 against an unstable base.** Premature scope decisions get invalidated by slice evidence. *Mitigation: split P1 into mandatory vs deferred decisions.*
- **R-4: P8 bundles a platform contract with the Page feature.** Risk of an over-general Page/Section JSON bag (an explicit non-goal). *Mitigation: split P8 into 8a contract / 8b bounded Page after D04.*
- **R-5: D02 flip without a masked-value census** silently changes merchant-visible output. *Mitigation: census + before/after diff + rollback as a hard gate.*

## 22. Risks in Kiro's (Hybrid) workflow

- **R-K1: Slice bias.** Building horizontal contracts "through Brand" risks Brand-specific shortcuts. *Mitigation: the contract, not the family, is the deliverable; Slice-2 (Collection) must reuse it unchanged, and that reuse is the gate.*
- **R-K2: Spine underestimation.** Merging P2+P3 makes the Authority phase large; if under-scoped it becomes a mega-phase. *Mitigation: narrow to *contested* concepts only (Q1); container geometry and snapshots are out of scope for this phase.*
- **R-K3: Perceived slower start.** The spine produces no visible certified store until Slice-1. *Mitigation: the A02 declared=effective roundtrip is itself a concrete, demonstrable milestone at end of Phase 2.*
- **R-K4: Two-slice pattern may not generalize** to Hero/interaction-heavy families. *Mitigation: Hero remains explicitly last (D12), after interaction/media convergence is proven on breadth.*

## 23. First work after approval

1. **P0 freeze acknowledgment** (doc-only) and confirm preserved-systems list.
2. **Resolve the safety-critical decisions** D02, D03, D09, D10, D11 (leave scope decisions parked).
3. **Begin the Authority phase design** (contested-concept writer inventory → single canonical write contract → Apply-as-writer), and stand up the **declared→persisted→effective roundtrip harness** across all 50 recipes as the A02 gate.
4. In parallel, request the **two highest-value deployment censuses**: masked-local-variant stores (for D02) and legacy-vs-R4 editor adoption (for D03/retirement).

## 24. Work that must NOT begin yet

- Any application code, Python, template, JS, or CSS change (this task).
- G3 / any new variant / any new component / Template 51+.
- The D02 resolution-order flip (before its census + rollback proof).
- Any destructive media cleanup (before D11 invariant + full reference graph).
- Any legacy deletion (0 safe now).
- Building D04 Page Override or D05 content-preserving Switch (scope decisions still parked).
- A file-by-file implementation plan (out of scope for this review).

## 25. Final recommendation

Adopt the **Hybrid (Approach C)**: keep the Baseline's safety-first spirit and its excellent evidence discipline, but **merge writer convergence with recipe-fidelity into one Authority phase** (this is where A02's root cause lives), run **revision/lifecycle alongside it**, adopt **D11 media retention as a hard invariant immediately**, and then **use Brand Showcase as an early vertical slice to prove the media/fragment/CSS/common-appearance contracts** before generalizing them platform-wide, with Collection as slice-2. Gate the **D02 resolution flip** behind a masked-value census and rollback proof. Resolve D02/D03/D09/D10/D11 now; defer D04/D05-Switch/D06/D07/D08/D12-timing until slice evidence exists. There is **no engineering justification** to create another renderer or rewrite any business domain — the single shared engine, versioned lifecycle, registries, and recipe model are the correct foundation and were confirmed intact at the baseline. The correct objective remains reducing ambiguity, not increasing implementation count.

---

*No implementation, refactor, migration, or data change was performed. This document is a read-only architecture/process review. All source references were validated read-only against baseline `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`.*
