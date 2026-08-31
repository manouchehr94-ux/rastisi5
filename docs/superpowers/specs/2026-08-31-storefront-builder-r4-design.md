# RastiSi R4 Storefront Builder — Final Architecture Spec

**Version:** 1.0 — Owner Review Candidate  
**Date:** 2026-08-31  
**Status:** Architecture agreed in principle; implementation must not begin until this document is reviewed and approved.  
**Primary language:** Persian product intent, English technical terminology where clearer.

---

## 1. One-sentence definition

> **RastiSi R4 is a storefront builder that is simple for merchants and powerful underneath: the merchant starts from a professional template, clicks any section to edit it in one consistent place, swaps professionally designed variants, inherits a coherent global design by default, optionally overrides a section, and safely publishes only when ready — without code, fragmented admin journeys, or a separate mobile builder.**

---

## 2. Why R4 exists

RastiSi already has a substantial Storefront Builder domain and rendering foundation. The problem is not that the whole platform must be rewritten. The problem is that the current R2/R3 editor layer has accumulated multiple editing shells, section-specific forms, fragmented lifecycle rules, iframe/deep-workspace coupling, and manual save/validation branches.

The architectural decision is therefore:

> **Replace the Builder/Editor layer, not the healthy storefront engine.**

R4 must reuse the mature existing domain, rendering, preview, draft/publish, versioning, ready-template, appearance, and variant infrastructure wherever it is sound.

---

# Part I — Product intent

## 3. Merchant outcome

A merchant must be able to build a storefront they like without needing to understand:

- HTML
- CSS
- JavaScript
- responsive design
- Django forms
- HTMX
- iframe routing
- modal ownership
- form prefixes
- section registries
- admin URL boundaries

The merchant-facing mental model is only:

```text
Template
  -> Page
     -> Section
        -> Variant
        -> Content
        -> Basic Settings
        -> Advanced Settings

Global Design
  -> Colors
  -> Typography
  -> Motion
  -> Component Style
```

A Section inherits Global Design unless the merchant explicitly overrides a supported property.

---

## 4. What R4 is not

R4 is intentionally **not**:

- Webflow-style free-form canvas editing.
- Arbitrary pixel positioning.
- A separate builder per template.
- A separate save lifecycle per section type.
- A separate mobile-site builder.
- A customer-facing code editor.
- A system where normal section editing jumps between unrelated admin pages.
- A system where every possible visual property is visible by default.

---

# Part II — Final product decisions

## 5. Template strategy

RastiSi should ultimately support approximately **50 genuinely different storefront templates**.

A new template does not qualify merely because palette or font changed.

Meaningful template differentiation should come from a combination of:

- Header composition
- Hero composition
- Section order and rhythm
- Product-card geometry
- Collection presentation
- Brand presentation
- Image proportions
- Typography treatment and scale
- Spacing density
- Badge/ribbon style
- Button treatment
- Radius/shadow language
- Motion behavior
- Footer composition
- One or more unique section families where justified

### 5.1 Hybrid architecture

Most templates are compositions of shared Section/Variant building blocks.

Some templates may contain truly custom variants or sections when they are necessary for genuine design differentiation.

A template is a professional starting state, not an isolated codebase.

Conceptually:

```text
Template Preset
  Header Variant
  Hero Variant
  Ordered Section Instances
  Section Variants
  Footer Variant
  Global Appearance Preset
  Typography Preset
  Motion Preset
  Compatibility Profile
```

---

## 6. Library targets

Long-term design-library targets include approximately:

- 20 Header variants
- 20 Footer variants
- 30 or more Product/Collection presentation variants
- 10 or more Brand presentation variants
- Multiple Hero, Category, Banner, Editorial, Gallery, Newsletter, FAQ, Testimonials, Promotional and other section families

These are library goals, **not Phase 1 delivery requirements**.

---

## 7. Home-page freedom

The Home page is the primary modular composition surface.

Merchants may:

- reorder sections
- hide sections
- remove sections
- add sections
- re-add section types
- duplicate supported section types
- use multiple instances of the same supported section type

Example:

```text
Header
Hero
Products — New Arrivals
Banner
Products — Best Sellers
Collections
Products — Discounts
Brands
Newsletter
Footer
```

Header and Footer remain global regions, not arbitrarily duplicated Home sections.

---

## 8. Internal pages

R4 Phase 1 does **not** turn Product, Listing, Search, Cart, or other core commerce pages into equally free-form page builders.

Initial rule:

- Home: highly modular.
- Internal commerce pages: controlled presets/layouts with safe, limited customization.
- Global design tokens still apply consistently across the storefront.
- Broader internal-page composition is a later phase only if product value justifies it.

---

## 9. Responsive behavior

The merchant does **not** design a separate mobile storefront.

Responsive behavior is the responsibility of RastiSi components.

Every production-ready Header, Section Variant, Footer and mobile navigation component must have a formal responsive contract and QA evidence for:

- desktop
- tablet
- mobile

The Builder may provide device preview modes, but these are previews, not independent mobile layouts.

---

## 10. Header and Footer replacement

After selecting a template, the merchant may replace Header and Footer variants.

The system should provide broad freedom while protecting design quality through compatibility metadata.

Behavior:

- compatible variants are recommended first
- other valid variants may still be visible
- clearly poor/incompatible combinations may be warned or blocked only when there is a real functional constraint

R4 must not recreate the deleted legacy `family_registry.py` or `preset_registry.py`. Compatibility is a new lightweight layer built on the current architecture.

---

## 11. Mega Menu

Mega Menu must remain merchant-friendly.

The merchant does not design an arbitrary menu grid.

Instead:

- supported Header variants declare available Mega Menu presets
- each Mega Menu preset defines named content slots
- the merchant assigns categories, brands, collections, images or promotional content to those slots

Example:

```text
Mega Menu: Category + Brand + Promo
  Slot A -> Women's categories
  Slot B -> Featured brands
  Slot C -> Summer collection banner
```

### Architecture decision

Mega Menu is initially modeled as a **capability/sub-configuration of Header variants**, not as a new independent top-level registry. A separate registry is introduced only if real complexity later proves necessary.

---

# Part III — Merchant UX contract

## 12. Simplicity by default

When the merchant opens R4, the Preview is the main surface.

No large settings panel is forced open initially.

If the merchant likes the template as-is, they should be able to make only minimal changes and publish.

When the merchant clicks a Section or selects it from page structure, **one Inspector panel** opens for that Section.

The merchant is never required to discover multiple edit locations for the same Section.

---

## 13. One Inspector, two tabs

Every editable component follows the same interaction model:

```text
[ Basic Settings ] [ Advanced Settings ]
```

### 13.1 Basic Settings

Basic Settings contain the common merchant task for that component.

For Product Section, for example:

- title
- product source
- item count
- display variant
- show/hide price
- show/hide discount treatment

Basic Settings differ by Section type, but always remain short and task-oriented.

### 13.2 Advanced Settings

Advanced Settings contain supported visual customization such as:

- color override
- typography override
- background
- motion
- spacing
- radius
- shadow
- border
- image behavior
- other capability-specific advanced controls

Advanced controls are progressively disclosed and should not overwhelm the default UI.

---

## 14. Typed settings only for design configuration

Normal merchant design configuration must be expressed through typed controls such as:

- enum/choice
- number/range
- toggle
- color
- media/image/video selection
- resource picker
- structured link
- font/preset choice

### Important clarification

Normal merchant **content text** is allowed where required, for example:

- section title
- button label
- short descriptive copy
- alt text

But R4 must not expose design or behavior through arbitrary:

- CSS
- HTML
- JavaScript
- raw JSON
- template code
- unrestricted style-expression textareas

No hidden “advanced CSS” escape hatch is allowed in the standard merchant builder.

---

## 15. Clicking Preview content

Clicking a Section in Preview selects that Section and opens its Inspector.

For simple editable content within a Section, R4 may focus the corresponding Basic field automatically.

Example:

- click Hero title -> open Hero Inspector and focus Title field
- click Banner image -> open Banner Inspector and focus Image field

This remains one editor model; it does not create separate mini-editors.

---

## 16. Quick Edit boundary

Builder is for design and content selection, not full store administration.

R4 may provide limited Quick Edit for small metadata changes that are directly useful during design, such as:

- Brand display name
- Brand image/logo
- Collection title/image

Full Product/Inventory/Pricing/Order management remains in the main admin.

If a full admin edit is needed, R4 may offer an explicit action such as:

```text
Open full product management
```

This is an optional escape hatch, not part of the normal Section save lifecycle.

### Hard rule

R4 normal editing must not rely on iframe-based Deep Workspace flows.

No modal-inside-iframe-inside-modal architecture is allowed.

---

## 17. Section reordering

R4 supports both:

- Drag & Drop at the Section level
- accessible move up/down controls

R4 does not support arbitrary pixel placement of internal elements.

---

## 18. Adding a Section

The Add Section workflow is progressive:

1. Choose Section family/type.
2. Show approximately 5–8 recommended compatible variants.
3. Allow “View all variants” for deeper choice.
4. Insert the chosen Section using safe defaults.
5. Open its Basic Settings.

Recommended variants are not simply “first items in registry”. They come from explicit compatibility/recommendation metadata.

---

# Part IV — Design system

## 19. Global Design

R4 has a dedicated Global Design area.

### Basic Global Design

The simple surface should expose presets such as:

- overall appearance preset
- palette preset
- typography preset
- motion preset
- component style preset

### Advanced Global Design

Advanced Global Design may expose individual typed tokens for:

- primary/secondary/accent colors
- page/surface colors
- text colors
- button style
- radius
- shadow
- border style
- spacing density
- typography scale
- input/control style
- badge style

The exact token list must remain curated and understandable.

---

## 20. Global inheritance and sparse Section overrides

Sections inherit Global Design by default.

Per-Section overrides are stored as a **sparse override map**.

Conceptually:

```json
{
  "appearance_overrides": {
    "color": {
      "enabled": true,
      "values": {
        "surface": "#111111",
        "text": "#ffffff"
      }
    },
    "typography": {
      "enabled": false
    },
    "motion": {
      "enabled": false
    }
  }
}
```

Only overridden values are stored locally.

This preserves global coherence and makes future global changes propagate automatically.

---

## 21. Background capability

Advanced Section background may support, when the Section declares the capability:

- theme/default inheritance
- solid color
- image
- gradient
- overlay
- overlay opacity
- cover/contain behavior
- image position
- video background for explicitly supported variants only

Not every Section exposes every background mode.

Capability metadata controls the UI.

---

## 22. Typography

Typography follows the same two-level design:

```text
Global Typography
  -> inherited by default

Section Typography Override
  -> optional
```

Section override is allowed only through supported typed controls.

---

## 23. Motion

Motion also follows global-first inheritance.

Example global presets:

- none
- calm/luxury
- standard
- energetic

A Section may override Motion only if its Variant declares the capability.

Animations remain curated, not arbitrary.

---

# Part V — Existing architecture to keep

## 24. Reuse decision

The following current systems are architectural assets and should be preserved or only lightly evolved:

### KEEP / REUSE

- `StorefrontLayout`
- `StorefrontLayoutVersion`
- `StorefrontPage`
- `StorefrontSection`
- existing Draft/Published pointer model
- `layout_service` publish/restore/checkpoint concepts
- `render_service.build_render_items`
- shared Preview rendering path
- `section_registry.py` core `SectionDefinition`
- `variant_contract.py` core `VariantDefinition` and `resolve_*`
- `layout_preset_registry.py`
- `appearance_registry.py`
- `palette_pack_64.py`
- `edit_history_service.py`
- `global_region_registry.py` with light evolution
- `container_service.py` and `row_service.py` with eventual convergence rather than immediate rewrite

### EVOLVE

- Section Settings definition
- Resource selection abstraction
- Header/Footer variant compatibility metadata
- Section-level color/typography/motion override
- responsive contract metadata
- stale-write protection

### DEPRECATE / REPLACE AT BUILDER LAYER

- simultaneous R2 and R3 editor shells
- R3 full-screen modal as the normal Section editor
- Deep Workspace iframe dependency for normal editing
- giant `storefront_section_settings` `if/elif` growth pattern
- giant per-section template branches as the long-term settings-form architecture
- section-specific save lifecycle implementations

---

# Part VI — R4 technical architecture

## 25. Architectural boundaries

R4 is divided into these responsibilities:

```text
R4 Editor Shell
  -> Selection / Inspector state
  -> Mutation queue
  -> Autosave status
  -> Undo/Redo commands
  -> Publish command
  -> Preview bridge

Settings Schema Engine
  -> Field definitions
  -> Basic/Advanced grouping
  -> Typed widgets
  -> Validation rules
  -> Capability visibility

Resource Picker
  -> shared Product/Category/Brand/Collection UX

Domain Services (existing)
  -> Draft
  -> Section instances
  -> Composition
  -> History
  -> Publish

Renderer (existing)
  -> Preview
  -> Public storefront

Registries (existing/evolved)
  -> Section types
  -> Section variants
  -> Header/Footer variants
  -> Ready Templates
  -> Global appearance
  -> compatibility metadata
```

---

## 26. Section contract

R4 extends the existing `SectionDefinition` / `VariantDefinition` instead of replacing them.

A Section definition should conceptually describe:

```text
identity
label
page types
instance limits
duplicable/removable/lock rules
available variants
default variant
settings schema
resource capabilities
appearance capabilities
responsive contract
motion contract
compatibility metadata
defaults
renderer/template
```

A Variant should conceptually describe:

```text
key
label
renderer
supported settings
capabilities
required data
default settings
responsive contract
motion defaults
compatibility tags
```

### Critical success rule

Adding a normal new Variant may require declarative registration in Python and a renderer/template, but it must **not** require:

- a new View branch
- a new save endpoint
- a new modal
- a new JS save lifecycle
- a copied form template
- a separate validation pipeline

If any of those are routinely required, R4 architecture has failed.

---

## 27. Settings Schema Engine

R4 introduces a declarative schema layer.

Conceptual field definition:

```text
SettingsField
  key
  label
  type
  group: basic | advanced
  default
  required
  validation
  choices
  min/max
  capability requirement
  inheritance behavior
  UI widget hint
```

A schema may also define grouped sections and conditional visibility.

Example:

```text
ProductSectionSchema
  Basic
    title: text
    source: resource_source
    item_limit: integer(1..N)
    variant: variant_choice
    show_price: boolean
    show_discount: boolean

  Advanced
    appearance_overrides: appearance_override_group
    background: background_group
    motion: motion_override
    spacing: spacing_group
```

### Migration rule

Existing handwritten validators are not deleted in one big-bang migration.

R4 supports:

- declarative schema for migrated Sections
- legacy validator fallback for not-yet-migrated Sections
- custom post-schema validation only where real cross-field business logic requires it

The goal is gradual strangler migration.

---

## 28. Generic Resource Source model

Product, Category, Brand and Collection selection share one conceptual model:

```text
ResourceSource
  kind
  mode: auto | manual
  auto_rule
  auto_parameters
  manual_ids[]
```

Examples:

```text
Product / auto / newest
Product / auto / discounted
Product / auto / by_category(category_id)
Product / manual / [12, 9, 31, 4]
Brand   / manual / [5, 8, 2]
Collection / auto / featured
```

Resource-type-specific business logic remains in dedicated resolvers/services, but the editor lifecycle is shared.

---

## 29. Generic Resource Picker UX

One R4 Resource Picker component supports:

- Product
- Category
- Brand
- Collection

Capabilities:

- automatic/manual mode
- search
- ownership-safe results
- selection
- ordered manual selection
- remove/reorder
- max-items constraints

The Resource Picker may use a Builder-owned overlay when a large searchable list needs more space.

### Hard boundary

This overlay is still part of R4. It is not an embedded admin page and does not own a second Section save lifecycle.

It returns a typed selection result to the active Inspector.

---

## 30. Compatibility model

R4 introduces a lightweight compatibility layer.

It has two purposes:

1. enforce real functional constraints
2. rank/recommend aesthetically appropriate variants

Initial metadata should remain simple:

```text
capabilities
required_capabilities
style_tags
recommended_for
incompatible_with
supported_content_profiles
```

### Recommendation policy

For the first version:

- each Ready Template may explicitly curate recommended variants for important families
- compatibility tags provide fallback ranking/filtering
- hard blocking is used only for actual incompatibility, not subjective style preference

This gives the merchant broad freedom without pretending every combination is equally good.

---

## 31. Responsive contract

Each production-ready Variant must declare a formal responsive contract.

Conceptually:

```text
ResponsiveContract
  desktop: required
  tablet_behavior
  mobile_behavior
  overflow_strategy
  touch_target_expectation
  mobile_navigation_behavior where relevant
```

CI/contract tests must reject a newly registered production Variant that lacks the required responsive declaration.

Visual/browser QA provides evidence that the declaration is actually true.

---

# Part VII — Draft, autosave, publish and history

## 32. Draft model decision

R4 Phase 1 keeps the current single-active-Draft model.

When the merchant tries another Template:

1. current Draft is checkpointed/archived
2. a new Draft is created/applied from the selected Template preset
3. currently published storefront remains untouched
4. previous checkpoint can be restored

R4 Phase 1 does **not** support multiple simultaneously editable parallel Drafts.

This avoids a high-cost model redesign for limited initial product value.

---

## 33. Autosave

Draft edits auto-save.

There is no normal “Save section” ceremony required for each change.

Client behavior:

- debounce text/range input
- immediate save for discrete choices when appropriate
- serialize mutations through one central R4 mutation queue
- show states: `Saved`, `Saving…`, `Conflict`, `Offline/Error`

Preview updates from the Draft state.

---

## 34. Stale-write protection

R4 must not rely only on last-write-wins.

### Architecture decision

Introduce one monotonic Draft-level optimistic concurrency token, conceptually:

```text
StorefrontLayoutVersion.edit_revision: integer
```

Every R4 mutation sends:

```text
base_revision
mutation
```

Server mutation flow:

1. lock/validate active Draft aggregate
2. compare `base_revision`
3. reject stale mutation with HTTP 409 if revision no longer matches
4. apply mutation transactionally
5. increment revision
6. return `new_revision`

The R4 client keeps the latest revision from successful responses.

This protects against:

- out-of-order saves
- two tabs editing the same Draft
- stale Inspector state overwriting newer changes

The exact migration is additive and must not change the existing published-version model.

---

## 35. Undo / Redo

Reuse the existing edit-history concept.

R4 should record semantic history operations rather than every keystroke.

Examples:

- text edits coalesced after idle/blur
- variant change = one history action
- background change = one action
- section reorder = one action
- duplicate/remove/add = one action

Undo/Redo operates on Draft only.

---

## 36. Version History

Version History is distinct from Undo/Redo.

Policy for initial R4:

- keep all published versions
- keep the most recent 20 non-published archived/checkpoint versions per Storefront by default
- no time-based deletion in the first release
- retention policy remains configurable later if storage evidence requires it

Restoring an older version creates a new Draft rather than mutating the historical version.

---

## 37. Publish

Publish continues to use the existing atomic version/pointer model.

The public storefront never renders a partially applied Draft.

Publish requirements:

- active Draft validates successfully
- requested publish revision is current
- publish is transactional
- published storefront pointer changes atomically
- new Draft baseline/history state is established according to existing domain semantics

R4 must not invent a second publish mechanism.

---

# Part VIII — Preview architecture

## 38. Shared renderer

Preview and public storefront continue to use the same core renderer path.

R4 does not fork rendering logic.

This is a hard architecture rule.

---

## 39. Preview bridge

Reuse the existing Preview communication concept where sound:

- Builder -> Preview: current Draft/selection/update instruction
- Preview -> Builder: selected Section/stable id and interaction events

The exact transport may continue using `postMessage` if it remains clean and same-origin-safe.

R4 does not need to rewrite working Preview rendering simply to build a new Inspector.

---

## 40. Preview refresh strategy

Prefer the least invasive strategy that keeps state reliable:

- update/reload affected Preview after successful mutation
- avoid client-side fake visual state that can diverge from server-rendered truth
- preserve selection when possible after refresh

The server-rendered Draft remains the source of truth.

---

# Part IX — R4 UI shell

## 41. Desktop builder layout

Primary R4 Builder target is desktop administration.

Default RTL layout:

```text
+--------------------------------------------------------------+
| Top Bar: Template | Draft status | Undo | Redo | Publish     |
+---------------------+----------------------------------------+
| Page Structure      |                                        |
| / Add Section       |              Live Preview              |
|                     |                                        |
| [Inspector opens here when something is selected]            |
+---------------------+----------------------------------------+
```

The exact visual split can be refined, but the interaction model is fixed:

- one Preview
- one page structure surface
- one Inspector
- no nested editor shells

When no Section is selected, the Inspector can collapse to maximize Preview.

---

## 42. Global Design entry

Global Design is a top-level Builder destination, not a fake Section.

It follows the same simplicity principle:

```text
Basic
  Appearance preset
  Palette
  Typography preset
  Motion preset

Advanced
  Token-level overrides
```

---

## 43. Header/Footer editing

Header and Footer use the same Inspector interaction principles as Sections while remaining global regions.

Basic examples:

- active variant
- logo/menu/search/account/cart visibility
- menu content assignment where applicable

Advanced examples:

- appearance override
- supported spacing
- motion
- supported Mega Menu preset assignment

No separate Header Builder application is introduced.

---

# Part X — Template diversity

## 44. Diversity quality gate

R4 must prevent superficial “50 templates” inflation.

Use three complementary checks:

### 44.1 Hard structural duplicate test

CI should fail when two templates have effectively the same:

- Header/Footer variants
- section sequence/families
- main section variants
- layout/density structure

and differ primarily in palette/font.

### 44.2 Diversity fingerprint / warning score

A non-blocking or review-support score may compare axes such as:

- Header
- section composition
- product-card geometry
- density
- typography scale/treatment
- unique section families
- motion

This is a heuristic, not an absolute “4 of 7” hard law.

### 44.3 Visual review evidence

Every new Ready Template requires desktop/mobile screenshots and explicit product/design review.

A human reviewer must be able to explain why it is materially different from its nearest existing template.

---

# Part XI — Migration strategy

## 45. Strangler migration

R4 is introduced alongside the current editor temporarily.

### Phase rule

- R3 receives only critical correctness/security/data-integrity fixes.
- No major new merchant-facing Builder feature is added to R3.
- R4 consumes the same underlying Draft/Renderer infrastructure.
- Section families migrate incrementally.
- R3 is retired only after R4 parity gates pass.

---

## 46. Feature gating

R4 should initially be available only to:

- staff/QA stores
- explicitly opted-in test stores

A Store-level feature flag or equivalent controlled rollout mechanism should route to R4 without affecting existing stores.

---

## 47. Settings migration approach

The new Schema Engine must coexist with legacy handwritten validators during migration.

Migration sequence:

1. schema engine infrastructure
2. 1–2 simple Section types
3. vertical slice with Product + Brand
4. Resource Picker consolidation
5. remaining resource-driven families
6. simple remaining families
7. R3 deprecation once parity is demonstrated

No mass migration of all 34 Section types in one commit/phase is allowed.

---

## 48. Page-composition model convergence

Existing `Container/Cell` and legacy `row_key/row_span` concepts are not rewritten as part of R4 Phase 1.

R4 uses the currently authoritative service layer.

A later focused architecture task may converge the two composition paths if evidence shows material maintenance cost.

Do not combine that debt cleanup with the first R4 editor slice.

---

# Part XII — First architecture vertical slice

## 49. Purpose

The first vertical slice exists to prove architecture, not to ship 50 templates.

It must answer:

> Can RastiSi add and edit real storefront components through one generic R4 contract without recreating the R3 per-section lifecycle problem?

---

## 50. Slice scope

Use one existing Ready Template and only the Home page.

Required components:

- Header
- Hero
- Product Section
- Brand Section
- Footer

Required capabilities:

- Global Colors
- one local Typography override on Hero
- click Preview -> Inspector
- Basic/Advanced tabs
- add Section
- remove/hide Section
- reorder Section
- duplicate where allowed
- one generic Resource Picker used by both Product and Brand paths
- Autosave Draft
- Preview refresh
- Undo/Redo
- Publish through existing domain service
- revision/conflict handling

Before the full slice, prove the Schema Engine on one or two simple Sections such as Newsletter/Rich Text.

---

## 51. Vertical-slice PASS criteria

The architecture passes only if all are true:

1. A migrated Variant can be registered without adding a new View branch.
2. It does not require a new save endpoint.
3. It does not require a new modal/editor lifecycle.
4. Product and Brand use the same Resource Picker component/contract.
5. Basic/Advanced UI is schema-driven.
6. Hero typography override affects only Hero and leaves Global Typography unchanged.
7. Add/remove/reorder/duplicate work through shared composition services.
8. Draft Autosave never changes the public storefront before Publish.
9. stale `base_revision` is rejected rather than silently overwriting newer Draft state.
10. Preview and public storefront continue using the same renderer.
11. existing Ready Template renders without conversion to a new rendering system.
12. Browser QA passes for the full merchant flow.

### Architecture FAIL condition

If a normal new migrated Section/Variant requires copied save JavaScript, copied form lifecycle, a dedicated View branch, a dedicated modal, or a parallel renderer, stop and revise the architecture before migrating additional families.

---

# Part XIII — Testing policy

## 52. Test pyramid

R4 development must not run the ~3300–3500 full suite after every small change.

### Level 1 — TDD / local iteration

Typical target: 5–100 tests.

Use:

- schema unit tests
- validation tests
- variant-contract tests
- targeted mutation/service tests
- focused R4 endpoint tests

### Level 2 — coherent subsystem checkpoint

Typical target: tens to a few hundred tests.

Run directly related neighboring modules.

Examples:

- settings schema
- resource selection
- section registry
- composition service
- preview bridge contracts
- R4 builder views

### Level 3 — full suite

Run only at meaningful checkpoints such as:

- end of the vertical slice
- major migration phase completion
- pre-merge/release checkpoint
- broad change with plausible cross-system regression risk

A one-line CSS change or one assertion change is not a reason to rerun 3000+ tests.

---

## 53. Required test types

### Pure/unit

- schema parsing/validation
- inheritance resolution
- compatibility ranking
- variant metadata contracts
- diversity fingerprint logic

### Django integration

- tenant ownership
- Draft mutations
- optimistic revision handling
- add/remove/reorder/duplicate
- publish/restore behavior
- ResourceSource resolution

### Renderer contract

- existing Ready Template rendering
- variant renderer resolution
- global + local appearance resolution
- responsive contract presence

### Playwright browser smoke suite

R4 must have a small automated browser suite.

At minimum:

1. open R4 Builder
2. click Section in Preview
3. edit Basic field
4. switch to Advanced
5. use Resource Picker
6. add/reorder Section
7. verify Autosave status
8. reload and verify Draft persistence
9. Publish
10. verify public rendering
11. automated conflict path for stale revision

Browser tests are not optional/manual-only for R4 core lifecycle.

### Visual regression/evidence

Use screenshots for:

- Ready Templates
- key Header/Footer variants
- representative complex sections
- desktop/mobile responsive evidence

Do not create expensive pixel snapshots for every minor form control.

---

# Part XIV — Security and integrity

## 54. Tenant isolation

All resource IDs selected in R4 must be resolved within the active Store/tenant.

Never trust client-supplied Product/Brand/Category/Collection IDs without ownership validation.

---

## 55. Draft and Preview access

Draft Preview must remain authenticated/authorized.

Public storefront must render only the published version.

Preview URLs/state must not expose another merchant’s Draft.

---

## 56. Media/background uploads

R4 media inputs must use the platform’s safe media pipeline.

Validate:

- ownership
- allowed content type
- file size
- safe storage path

Background video support is capability-gated and not universally enabled.

---

## 57. Settings validation

All R4 settings are validated server-side against the Section/Variant schema even if client-side controls already constrain values.

Client UI is convenience; server validation is authority.

Unknown or unsupported fields are rejected or ignored according to an explicit schema policy, never implicitly persisted.

---

# Part XV — Performance principles

## 58. No premature rendering rewrite

R4 does not add a new caching system before real measurement.

The existing renderer remains authoritative.

Measure:

- query count
- render time
- Preview update time
- autosave latency

before adding cache complexity.

---

## 59. Autosave load control

Use:

- debounce
- semantic batching where appropriate
- central mutation queue
- no request per keypress

The goal is responsive editing without unnecessary server chatter.

---

## 60. Resource selection scale

Resource search must be server-paginated/searchable.

Do not load the merchant’s entire large Product catalog into the browser merely to populate a picker.

Manual selected IDs remain ordered and bounded by Section constraints.

---

# Part XVI — Operational rules for implementation

## 61. Do not rewrite healthy infrastructure

During R4 Phase 1, avoid broad changes to:

- storefront renderer
- Draft/Published version structure
- public storefront routing
- checkout/cart/inventory/order domain
- Ready Template rendering engine

Changes require direct evidence that R4 cannot meet its contract without them.

---

## 62. Do not grow R3

After R4 work starts:

R3 may receive only:

- security fixes
- data integrity fixes
- blocking production correctness fixes

Do not add new section families, advanced styling systems, compatibility engines or major UX features to R3.

---

## 63. No large test-loop waste

Every implementation task must state its intended Level 1 and Level 2 test set before development.

A full Level 3 run requires a checkpoint-level reason.

---

## 64. Evidence before migration

Each Section family is migrated only after the previous family has:

- green contract tests
- green relevant integration tests
- browser smoke evidence
- no new custom lifecycle

---

# Part XVII — Recommended implementation phases

## 65. Phase 0 — R4 foundation spike

**Effort:** MEDIUM  
**Purpose:** establish skeleton without merchant scope explosion.

Deliver:

- R4 feature gate
- R4 shell route
- shared Preview reuse
- generic Inspector state model
- Settings Schema core
- schema rendering on 1–2 simple Sections
- mutation API shape with `base_revision`
- focused tests

No Product/Brand migration yet if schema foundation is not stable.

---

## 66. Phase 1 — Architecture vertical slice

**Effort:** LARGE

Deliver the exact slice defined in Parts 49–51.

This is the architectural go/no-go gate.

No 50-template expansion before this passes.

---

## 67. Phase 2 — Resource-driven Section family

**Effort:** LARGE

Migrate:

- Product
- Category
- Brand
- Collection

Deliver one generic Resource Picker and ResourceSource contract.

---

## 68. Phase 3 — Remaining common Sections

**Effort:** MEDIUM/LARGE

Migrate simpler families using the proven schema pattern.

Avoid simultaneous migration of unrelated complex families.

---

## 69. Phase 4 — Compatibility and recommendations

**Effort:** MEDIUM

Deliver:

- lightweight compatibility metadata
- curated per-template recommendations
- 5–8 suggested variants
- “View all variants”
- warnings only for real functional incompatibility or clearly curated poor fit

---

## 70. Phase 5 — Responsive contract enforcement

**Effort:** MEDIUM

Formalize responsive metadata and QA gates for production variants.

This may partly run in parallel once the contract is stable.

---

## 71. Phase 6 — Mega Menu presets

**Effort:** MEDIUM

Add preset-driven Mega Menu capabilities to supporting Header variants.

---

## 72. Phase 7 — Template library expansion

**Effort:** VERY LARGE in aggregate, parallelizable

Grow from current Ready Templates toward approximately 50 real designs.

Every template requires:

- structural distinctness evidence
- responsive evidence
- design review
- targeted tests

This is content/design-system expansion, not a new Builder architecture each time.

---

## 73. Phase 8 — R3 retirement

**Effort:** MEDIUM

Retire R2/R3 only after R4 parity criteria for supported merchant flows are satisfied.

Remove old shell/lifecycle code in a separate cleanup phase, not while core R4 is still unstable.

---

# Part XVIII — R4 acceptance principles

## 74. Merchant simplicity acceptance test

A merchant who likes the selected Template should be able to:

1. open Builder
2. change logo/global palette if desired
3. publish

without opening Advanced Settings.

---

## 75. Moderate customization acceptance test

A merchant should be able to:

1. click Header
2. select another recommended Header
3. click Product Section
4. choose source/count/variant in Basic
5. optionally change background/motion in Advanced
6. add another Product Section
7. reorder it
8. publish

without leaving Builder or encountering a second save lifecycle.

---

## 76. Advanced customization acceptance test

A merchant should be able to:

1. change Global Design preset
2. override Hero typography only
3. override Brand background only
4. choose a Collection Variant
5. manually select content with the shared Resource Picker
6. Undo/Redo
7. reload and retain Draft
8. Publish
9. later restore a previous version

without custom code.

---

# Part XIX — Non-negotiable architecture invariants

## 77. Invariants

The following must remain true throughout R4 development:

1. **One Builder shell.**
2. **One Section editing mental model.**
3. **One shared Draft mutation contract.**
4. **One shared renderer for Preview and public storefront.**
5. **Global design first; sparse local overrides second.**
6. **Variants are curated building blocks, not independent applications.**
7. **Resource selection is shared across resource families.**
8. **Responsive behavior belongs to components, not merchants.**
9. **No merchant code editor.**
10. **Public storefront changes only on Publish.**
11. **Stale writes are detected, not silently accepted.**
12. **R4 growth must not require a new lifecycle for every Section.**
13. **Internal-page free-form editing is out of Phase 1.**
14. **R3 is maintenance-only once R4 implementation begins.**
15. **Test speed is an engineering requirement, not an afterthought.**

---

# Part XX — Definition of success

## 78. Technical success

R4 is technically successful when:

- the vertical slice passes its architecture gate
- adding normal variants does not add editor lifecycle code
- existing renderer/domain services remain stable
- Autosave/Preview/Publish are reliable
- stale-write conflict is handled explicitly
- R4 has focused automated browser coverage
- R3 can be retired without changing public storefront rendering

---

## 79. Product success

R4 is product-successful when a merchant experiences:

> “I picked a professional store design. I liked most of it. I clicked the part I wanted to change, changed it there, and published.”

The system may be complex internally, but that complexity must not leak into the merchant workflow.

---

# Part XXI — Final decisions resolved before implementation

## 80. Blocking decisions resolved

### Decision 1 — R3 vs R4

**Approved:** Build an R4 Editor layer while reusing healthy existing domain/rendering infrastructure.

### Decision 2 — Template experimentation

**Approved for initial R4:** one active Draft; checkpoint/archive current Draft before template replacement; restore previous checkpoint when needed. No parallel simultaneously editable Drafts in Phase 1.

### Decision 3 — Advanced Settings safety

**Approved:** typed/curated design controls only. Merchant content text is allowed where semantically required, but no custom HTML/CSS/JavaScript/raw JSON/style-code escape hatch.

### Decision 4 — Mobile

**Approved:** responsive automatically; no separate mobile builder.

### Decision 5 — Home vs internal pages

**Approved:** Home is the primary modular page in R4 Phase 1; internal commerce pages remain controlled.

### Decision 6 — Builder interaction

**Approved:** clicking any editable part opens that component’s own Basic/Advanced Inspector in the same Builder experience.

---

# Part XXII — Immediate next step after approval

## 81. Next deliverable

After the product owner approves this Spec, create a detailed implementation plan for **Phase 0 + Phase 1 only**.

Do not plan all 50 templates in implementation detail yet.

The implementation plan must include:

- exact repository files to inspect/change
- test-first sequence
- additive migration introducing the optimistic Draft revision token
- R4 route/feature flag
- schema engine
- first simple schema-driven sections
- vertical-slice section set
- Resource Picker contract
- Playwright smoke suite
- Level 1/2/3 test policy per task
- checkpoints where the owner reviews screenshots/browser evidence

Implementation must not begin until that plan is reviewed.

---

---

# Appendix A — Current repository evidence baseline

This Spec is intentionally not greenfield. It is based on the architecture review performed against Git HEAD:

```text
37339c3d5c48304ca6b4a6047432802c3e9f81b3
```

Key evidence from the current repository:

- `apps/storefront_builder/models.py` already provides `StorefrontLayout`, `StorefrontLayoutVersion`, `StorefrontPage`, `StorefrontSection`, `StorefrontContainer`, `StorefrontCell`, and edit-history entities.
- `apps/storefront_builder/section_registry.py` currently registers approximately 34 Section types.
- `apps/storefront_builder/variant_contract.py` already provides the core `VariantDefinition` / resolver contract.
- Only a small subset of current Section families currently adopt formal variants, so R4 needs broader adoption rather than a new variant engine.
- `apps/storefront_builder/layout_preset_registry.py` is the active Ready Template mechanism; the older `family_registry.py` and `preset_registry.py` were retired/deleted and must not be revived as dependencies.
- `apps/storefront_builder/global_region_registry.py` is the active Header/Footer variant mechanism.
- `apps/storefront_builder/appearance_registry.py` and `palette_pack_64.py` are the active Global Appearance foundation.
- `apps/storefront_builder/services/render_service.py::build_render_items` is shared by Preview and public storefront rendering and is a major reuse boundary.
- Current R2/R3 editing uses `editor.html`, `section_settings_form.html`, HTMX/Alpine flows and a manually dispatched `storefront_section_settings` path; this is the primary replacement/evolution target.
- Current working architecture already supports Draft/Publish/restore concepts and should not be replaced by a second R4 persistence model.

These facts are constraints for implementation planning. Any later repository inspection that disproves one of them must update this Spec before implementation proceeds.

# Final product statement

> **RastiSi R4 gives merchants professional variety without builder complexity. The platform owns responsive quality, design-system coherence, validation and safe publishing; the merchant owns the creative choices that matter: template, section order, component variants, content, global style, and optional per-section overrides.**

