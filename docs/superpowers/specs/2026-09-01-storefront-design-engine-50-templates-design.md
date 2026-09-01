# RastiSi R4 Storefront Design Engine + 50 Ready Templates — Architecture Design

**Version:** 1.0  
**Date:** 2026-09-01  
**Status:** Product/architecture decisions approved in conversation; written spec awaiting owner review before implementation planning.  
**Scope:** R4 Phase 2+ storefront appearance engine, component library, Design Lab, 50 curated Ready Templates, and timed-offer presentation contract.  

---

## 1. One-sentence definition

> **RastiSi will have one central Store Appearance / Design Engine made of reusable, versioned, server-validated visual components; RastiSi publishes 50 professionally curated template recipes from that engine, while every merchant remains free to change each valid component independently after choosing a template.**

The 50 templates are professional starting points, not isolated codebases and not permanent restrictions.

---

## 2. Relationship to the existing R4 architecture

This document **refines and extends** `docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md` for the Phase 2 design-library/template expansion.

All existing R4 invariants remain in force:

- one Builder shell;
- one shared Draft mutation contract;
- one Preview/Public rendering engine;
- no arbitrary merchant HTML/CSS/JavaScript/raw JSON;
- Global Design first, sparse local overrides;
- responsive behavior belongs to components, not a separate mobile builder;
- Public changes only on Publish;
- stale writes are rejected;
- no per-template builder and no per-component save lifecycle.

This document clarifies the final product model for the large appearance library and 50 Ready Templates.

---

## 3. Core product model

RastiSi does **not** build 50 independent storefront applications.

It builds a reusable design library with a very large combination space:

```text
Store Appearance Component Library
              |
              v
     many valid combinations
              |
              v
 Compatibility / QA guidance
              |
              v
  50 curated RastiSi templates
              |
              v
      merchant chooses one
              |
              v
 merchant may change any valid part
```

Product principle:

> **Curated by RastiSi, customizable by the merchant.**

The 50 templates are the initial official showcase of the engine, not the maximum number of storefront appearances the engine can produce.

---

## 4. Initial component-library targets

| Component family | Target |
| --- | ---: |
| Header | 20 |
| Mega Menu presentation | 20 |
| Footer | 20 |
| Layout / composition | 20 |
| Hero / first slider | 20 |
| Product display / collection presentation | 15 |
| Product card | 30 |
| Motion profile | 20 |
| Discount / badge / promotional icon treatment | 15 |
| Mobile bottom navigation | 15 |
| Timed-offer / countdown capability | real domain capability + curated presentations |

Existing R4 palettes, typography, radius, density, width, and other Global Appearance systems are **reused**, not rebuilt as parallel systems.

---

## 5. Store Appearance boundary

The codebase should expose a clear logical boundary called **Store Appearance** (technical package name may be `storefront_appearance` or an equivalent name consistent with the existing app).

Conceptually:

```text
storefront_appearance/
  contracts
  component-family definitions
  registry/resolution adapters
  compatibility metadata
  template recipes
  preview-manifest validation
  version/deprecation rules
```

This is a **logical architectural boundary**, not permission for a big-bang rewrite of existing R4 files.

Existing assets such as `appearance_registry.py`, `global_region_registry.py`, `section_registry.py`, `layout_preset_registry.py`, existing Variant contracts, and the existing renderer must be reused/evolved behind this boundary rather than copied into duplicate registries.

---

## 6. Stable component identities

Every production component has a stable, allowlisted key.

Example:

```text
header.editorial_centered
mega_menu.visual_columns
hero.split_story
layout.editorial_spacious
product_view.featured_grid
card.portrait_minimal
badge.discount_corner
motion.soft_reveal
footer.magazine
bottom_nav.floating_pill
```

Numeric labels such as “Header 08” are fine in the UI, but persisted identities should be stable semantic keys or stable versioned keys.

A merchant stores references to approved components — never copied HTML/CSS/JS implementations.

---

## 7. Merchant Store Appearance state

The merchant's current Draft should conceptually contain a typed appearance configuration such as:

```text
header        = header.editorial_centered
mega_menu     = mega_menu.visual_columns
hero          = hero.split_story
layout        = layout.editorial_spacious
product_view  = product_view.featured_grid
card          = card.portrait_minimal
badge         = badge.discount_corner
motion        = motion.soft_reveal
footer        = footer.magazine
bottom_nav    = bottom_nav.floating_pill
palette       = <existing R4 palette key>
typography    = <existing R4 typography key>
```

The exact physical storage should reuse the existing versioned Draft/Published layout architecture. This initiative must **not** introduce a new parallel Draft lifecycle merely to store appearance choices.

All mutations continue through the shared R4 mutation contract.

---

## 8. Independent mutation rule

Changing one component changes only that component unless the merchant explicitly applies a whole template/preset.

Example:

```text
before: header = header_08
change: header = header_14
```

Footer, Card, Motion, Palette, Bottom Nav, Hero, and other selections remain unchanged.

This is a hard product rule.

---

## 9. Ready Template DNA

Each of the 50 Ready Templates is a versioned recipe containing compatible component selections, composition, and limited typed settings.

Conceptually:

```text
Template 10
  header        = header_08
  mega_menu     = mega_menu_03
  hero          = hero_14
  layout        = layout_07
  product_view  = product_view_11
  card          = card_15
  badge         = badge_05
  motion        = motion_03
  footer        = footer_12
  bottom_nav    = bottom_nav_09
  palette       = existing_palette_18
  typography    = existing_typography_x
  section_recipe = [...]
```

DNA may include typed, schema-validated overrides, but never arbitrary HTML, CSS, JavaScript, unrestricted style expressions, or unvalidated JSON.

Selecting a Ready Template applies its design recipe into the merchant's **Draft**. It does not copy Demo products, categories, brands, prices, stock, or catalog imagery.

Once applied, the merchant owns the resulting Draft configuration and can independently replace any valid component.

A template origin/provenance key may be retained for analytics, “reset to original DNA”, or support, but the merchant is not runtime-locked to that template.

---

## 10. All 50 templates are available to all industries

Industry/category may affect recommendation or ranking only.

It must not hide or forbid otherwise valid Ready Templates.

The merchant must always have a “show all 50” path.

---

## 11. Compatibility metadata

The library has a lightweight compatibility layer to prevent poor automatic combinations and rank good choices.

Uses:

- Design Lab recommendations;
- Random Mix generation;
- Ready Template curation;
- Builder recommendation ordering;
- QA warnings.

Compatibility metadata is guidance first. If a combination is technically valid, the merchant may generally choose it even when not recommended. Blocking is reserved for genuine functional incompatibility.

Mega Menu may appear independently in Store Appearance state, but it must be validated against the selected Header's declared capabilities to remain consistent with the existing R4 global-region model.

---

## 12. Design Lab

Design Lab is a separate advanced R4 surface for exploring the same real Store Appearance library.

It is not the normal simple Builder and not a second renderer.

The Lab may expose Templates, Header, Mega Menu, Hero, Layout, Product View, Product Card, Badge, Motion, Footer, Mobile Bottom Navigation, existing Palette/Typography/Density/Radius/Width systems, campaign/occasion overlays where supported, Compare, Desktop/Tablet/Mobile preview, Random Mix, per-family locks, and “return to original DNA”.

---

## 13. Transient Lab state

Exploration in Design Lab must not create a new persistent Draft or fill merchant history with every experimental click.

Recommended model:

```text
Lab UI
  -> transient typed Lab state
  -> server-side registry/schema validation
  -> ephemeral Preview Manifest
  -> shared R4 renderer
```

Transient Lab state may be preserved locally in the browser across refresh for usability, but it is not merchant production state until explicitly applied.

Production Design Lab must not render using its own `srcdoc`, cloned HTML, or independent template engine.

---

## 14. Apply to Draft

Design Lab experiments become real only when the merchant chooses an explicit Apply action.

That action:

1. validates the full candidate manifest server-side;
2. checks tenant and stale-write/version preconditions;
3. converts it into one logical/atomic Draft mutation operation;
4. preserves merchant catalog/content/business data;
5. becomes part of the normal history/Undo/Redo model.

A hundred Lab experiments should not become a hundred Draft history mutations.

---

## 15. Canonical Template Demo Store

The canonical design/QA fixture is:

```text
Rasti Mode Demo
slug: rasti-mode-demo
```

Its seed provides a substantial curated commerce dataset including 50 products, 10 categories, 6 brands, 150 product images, 206 variants on 41 products, 6 collections, 4 Hero items, 6 banners, and 10 Story items.

This fixture is the fixed content baseline for designing and comparing the official 50 Ready Templates.

Template Demo and Template Preset remain separate concepts:

- **Template Demo:** Ready Template rendered against Rasti Mode Demo so a new user can understand its potential.
- **Template Preset:** design/layout DNA applied to the merchant Draft.

On signup, Demo catalog/business data is never copied into the merchant's store.

After a merchant already has a store, template exploration should use the merchant's own current data where possible.

---

## 16. Timed products / timed offers

Timed-offer truth belongs to the commerce domain, not Store Appearance.

A product or offer may have real time-bounded state such as `sale_start`, `sale_end`, `normal_price`, and `sale_price` using existing or evolved commerce infrastructure.

Supported Card/Product View/Badge/Promo variants may display a real countdown while the timed offer is active.

When the offer expires:

- the countdown disappears;
- the temporary discount is no longer presented as active;
- the product remains visible;
- normal pricing remains/returns according to commerce-domain truth.

The Demo Store should include representative active/expired timed-offer cases for QA once the capability is implemented.

---

## 17. Security

Persisted appearance configuration may reference only registered component keys and typed schema values.

Forbidden normal merchant design inputs include arbitrary HTML, CSS, JavaScript, unrestricted raw JSON, executable expressions, arbitrary template paths, and arbitrary renderer names.

All component selection and settings validation is server-side even if the browser also validates for UX.

Resource identifiers used by a component must continue to be validated within the merchant's tenant/store scope.

Invalid or unknown component keys are rejected with typed errors. New optional component families receive an explicit safe default/off state for older stores.

---

## 18. Versioning and extensibility

Stable bug fixes may update an existing component implementation.

A materially redesigned component that could surprise existing merchants receives a new stable version/key, for example:

```text
card.portrait.v1
card.portrait.v2
```

Every Ready Template recipe has a schema version, beginning with `schema_version = 1`.

Future component families — e.g. Floating Cart, Sticky Buy Bar, Announcement Bar, Story Products, AI Search presentation, Live Shopping presentation, Comparison Drawer, 3D Product Viewer, Video Commerce surfaces — must plug into Store Appearance through the same contracts, validation, renderer, responsive behavior, compatibility metadata, and safe-default rules.

Adding a new family must not require rewriting all 50 templates or introducing a new save lifecycle.

---

## 19. Performance and maintenance cost

Thousands of merchants may reference the same component implementation.

RastiSi stores the merchant's small set of stable selections, not a copied implementation per store.

Performance principles:

- deterministic registry lookup;
- shared static assets;
- cache keyed by immutable/versioned layout or appearance state where safe;
- no runtime filesystem discovery or arbitrary dynamic imports;
- no duplicated per-template CSS/JS bundles where shared component assets suffice;
- debounced/cancellable Design Lab preview requests;
- cache boundaries must respect tenant data and Draft/Published version identity.

This gives lower storage cost, simpler cache behavior, faster global bug fixes, and lower regression/maintenance cost.

---

## 20. Exactly 50 official templates for this initiative

For this initiative, RastiSi publishes exactly 50 official Ready Templates.

Candidate-marketplace workflows, hundreds of public templates, and a separate persistent candidate subsystem are out of scope for now.

The 50 should cover broad design directions such as minimal/clean, luxury/premium, dense marketplace, editorial/magazine, modern/technology, warm/boutique, bold/colorful, visual/Hero-led, promotion/countdown-led, and mobile/social-commerce-led.

These are curation directions/tags, not new technical template families.

---

## 21. Diversity gate

A template is not considered distinct merely because Palette or Typography changed.

Before acceptance, each template must be reviewed across major dimensions such as Header composition, Hero composition, section sequence, Product View, Product Card geometry, density/rhythm, Footer, Mobile Bottom Navigation, typography treatment, motion language, and distinctive reusable variants.

A palette-only or font-only change does not pass as a new template.

---

## 22. Component coverage matrix

For the initial advertised library target, every production component should appear in at least one curated Ready Template unless an explicit documented exception is approved.

The curation/QA matrix should make unused official components obvious.

This detects components that are unnecessary, not integrated well, or missing a compatible curated template.

---

## 23. Builder versus Design Lab

The normal Builder remains the merchant's primary simple editing surface.

A merchant who selects Template 10 can change Header 08 to Header 14 without seeing or understanding the entire combinatorial engine.

Design Lab is optional and advanced. Both surfaces manipulate the same typed Store Appearance state and use the same renderer.

There is no Lab-only appearance model that cannot be represented by production domain contracts.

---

## 24. QA and release gates

Every production component must have evidence appropriate to its capability, including registry/contract validation, schema validation, renderer resolution, safe invalid-key behavior, Desktop/Tablet/Mobile behavior, RTL, short/long content, image variations, normal/sale/timed-offer states where relevant, interaction/accessibility behavior, and no unexpected console/request/render errors.

Every one of the 50 Ready Templates must be rendered with the canonical Demo Store and reviewed at minimum on Desktop and Mobile, with Tablet included in automated/component responsive coverage and in visual review when structure warrants it.

Each template must prove shared-renderer parity, no broken registry references, no unsupported combinations, acceptable RTL/responsive behavior, no accidental Demo-data coupling, visual differentiation, correct Header/Footer/BottomNav behavior, and representative commerce states.

A Ready Template cannot be declared complete if Design Lab/Preview depends on a renderer path Public does not use.

---

## 25. Explicit non-goals

This architecture does not introduce:

- 50 separate template codebases;
- a separate Builder per template;
- a separate renderer for Design Lab;
- arbitrary merchant CSS/HTML/JS;
- a new Draft lifecycle per component;
- a separate mobile-site builder;
- copying Rasti Mode Demo catalog into merchant stores;
- permanent merchant lock-in to the originally selected Ready Template;
- a public template marketplace in this phase;
- an unlimited persistent candidate-template subsystem in this phase.

---

## 26. Acceptance criteria

This design is implemented correctly only if:

1. RastiSi has one central Store Appearance logical subsystem over existing R4 registries/contracts rather than duplicated parallel registries.
2. A merchant Draft stores validated component choices/settings, not copied component code.
3. Changing one component can mutate only that component while preserving the rest of Store Appearance.
4. Applying a whole Ready Template is an explicit preset operation and preserves merchant catalog/business content.
5. The 50 templates are recipes on the shared engine, not separate applications.
6. All 50 templates remain available to all industries; industry only influences recommendation/ranking.
7. Design Lab uses transient validated state and the shared R4 renderer.
8. Applying Lab state to Draft is one logical validated operation with stale-write protection.
9. Rasti Mode Demo is the canonical fixed content fixture for official template comparison/QA/onboarding demo rendering.
10. Template Demo content is never copied into the merchant's real catalog by template selection.
11. Timed-offer truth lives in the commerce domain; appearance components only present it.
12. On timed-offer expiry, countdown/temporary discount ends while the product remains visible with normal commerce state.
13. Existing R4 Palette/Typography/Appearance infrastructure is reused rather than duplicated.
14. Invalid/unknown component keys are rejected server-side.
15. Future component families can be added with safe defaults without rewriting all 50 templates.
16. Material component redesigns follow explicit version/deprecation rules.
17. The official 50 pass component coverage, responsive QA, renderer parity, and diversity gates.
18. Palette/font-only changes cannot qualify as separate Ready Templates.
19. The normal Builder remains simpler than Design Lab and does not expose the entire combinatorial engine by default.
20. Public rendering still changes only through the normal R4 Publish lifecycle.

---

## 27. Final product statement

> **RastiSi is building a reusable storefront appearance engine capable of producing a very large number of valid storefront combinations. RastiSi initially publishes 50 carefully curated, coherent, tested Ready Templates from that engine. The merchant may start from any of those 50 and then independently choose the Header, Hero, Card, Footer, Motion, Bottom Navigation, Palette, and other valid components they actually want.**

That combination of strong defaults and merchant freedom is the intended product.
