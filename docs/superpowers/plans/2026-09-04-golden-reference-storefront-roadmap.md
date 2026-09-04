# RastiSi Golden Reference Storefront — Roadmap

**Date:** 2026-09-04
**Branch:** `golden/g1-reference-storefront`
**Base commit:** `ac2fd5dcad7b4952b02ed42995143e2cfd2504e3`
**Authority:** `docs/superpowers/specs/2026-09-04-golden-reference-storefront-design.md`

> Reconstructed at baseline `ac2fd5d`. Phase-1 "Safe Template Switching" implementation is
> absent here and deferred; the Golden storefront work is architecturally separable from it.

## Guiding principle

REUSE → WIRE → COMPOSE → POLISH before CREATE NEW. Golden is a customized `rasti-mode-demo`
built on the existing universal renderer, section registry, appearance registry, and the
`fashion_promo_catalog` Ready Template baseline. No parallel architecture; exactly 50 Ready
Templates; Content/Commerce ownership preserved.

## Gate sequence (customer-facing first)

| Gate | Deliverable | Status |
|---|---|---|
| **G1** | Global Shell + complete Home | **← this cycle** |
| G2 | Search / Category / Listing pages | deferred |
| G3 | Product Detail | deferred |
| G4 | Cart | deferred |
| G5 | Responsive / Accessibility / Visual-QA lock across the demo | deferred |

Only **G1** is executed now. G2 does not begin until owner review of G1.

## G1 summary

Turn `rasti-mode-demo` into the first visually complete Golden Reference Storefront:

1. Establish the reproducible baseline via the existing demo seed applying the
   `fashion_promo_catalog` Ready Template.
2. Customize the demo through existing production contracts: Golden Home composition (15
   registered sections in commercial rhythm), Golden shell variants
   (`marketplace_search_first` / `premium_columns` / `five_item`), identity palette
   (`theme-forest-cream`), then Publish.
3. Make the whole setup idempotent and re-runnable (converges, never duplicates).
4. Browser visual QA at 390 / 768 / 1440; fix visible defects.
5. Targeted + neighboring regression gates; fresh whole-G1 review.

## Phase-1 deferral (not forgotten)

Phase-1 Safe Template Switching will be reconstructed later from its approved architecture
plan and retained test/report evidence. G1 avoids changing these Phase-1 production areas
unless it has a genuinely independent reason:

- `apps/storefront_builder/services/preset_service.py`
- `apps/storefront_builder/services/r4_mutation_service.py`
- `apps/storefront_builder/storefront_appearance/persistence.py`

G1 primarily touches: storefront composition (via existing services), the demo seed/refresh
commands, registered visual components/templates/styles, and tests.

## Sandbox-persistence safety

Frequent small **local** commits; never leave substantial completed work uncommitted; after
major milestones produce a recovery `git bundle` (`RastiSi_Golden_G1_recovery.bundle`) as a
backup artifact. **No push. No merge.** GitHub sync is deliberately deferred.

## Cross-gate invariants

Same as the unified roadmap (`2026-09-03-storefront-unified-implementation-roadmap.md`):
one shell, one mutation contract, one renderer for Preview and Public; Public changes only on
Publish; no arbitrary merchant HTML/CSS/JS or raw executable JSON; Content-vs-Commerce
boundary; responsive belongs to components; no parallel registry/renderer/lifecycle; exactly
50 Ready Templates.
