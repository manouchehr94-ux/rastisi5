# RastiSi4 — Universal Storefront Builder V2
## Product Specification, Architecture Contract, Repository Audit Plan, and Kiro Execution Brief

**Status:** Proposed / Architecture Reset  
**Project:** RastiSi4 / Rastisi Store Builder  
**Primary goal:** Replace the current multi-family storefront implementation with one universal storefront engine and one unified visual builder that can produce radically different storefront designs without requiring separate coded template families.

---

# 1. Executive Decision

RastiSi4 must stop treating a storefront "template" as a separate coded family.

The existing storefront families must be **frozen and archived from merchant-facing selection UI**. They must not be deleted yet because they contain implementation work, reusable components, tests, CSS patterns, and design ideas that may help the new system.

From this point forward, the target architecture is:

> **One Universal Storefront Engine + One Unified Visual Builder + Reusable Blocks + Presets**

A merchant must be able to create a storefront that looks substantially different from another merchant's storefront while both are rendered by the same engine.

A "template" shown to the merchant in the future is not a separate HTML/CSS codebase. It is a **Preset**: a saved configuration of the same universal engine.

---

# 2. Why We Are Changing Direction

The current family architecture demonstrated a structural limitation during real browser QA.

A storefront family could affect parts such as:

- homepage header
- homepage hero
- homepage categories
- homepage product cards
- footer
- product detail fragments

But generic routes such as collection pages and product listing pages could still use common templates.

This creates a storefront where:

- Homepage may look like Family A.
- Collection page may look like a shared generic site.
- Category page may look different again.
- Draft media may not behave consistently with published media.
- A family can pass static tests while failing the visual consistency requirement.

This is not acceptable for RastiSi4.

The customer sees **one store**, not a collection of unrelated route templates.

Therefore every public storefront page must be rendered through the same storefront design system.

---

# 3. Core Product Principle

The platform must preserve **maximum design freedom** without forcing merchants to edit raw HTML/CSS.

The merchant should not have to choose between a small number of rigid layouts.

Instead:

- the system provides powerful reusable blocks;
- blocks can be added, removed, reordered, duplicated, hidden, and configured;
- header and footer are editable compositions;
- page templates are editable compositions;
- global design tokens control visual identity;
- responsive behavior is configurable;
- presets provide fast starting points;
- all storefront data remains tenant scoped;
- public rendering is deterministic and safe.

The builder should be powerful enough that two stores created using the same engine can look unrelated.

---

# 4. Non-Goals for V2 Phase 1

Do **not** build a full Webflow / Elementor clone in the first phase.

Phase 1 does not require:

- arbitrary HTML editing by merchants;
- arbitrary JavaScript injection;
- free absolute positioning;
- deeply nested arbitrary DOM trees;
- per-pixel drag positioning;
- arbitrary CSS properties;
- unlimited nested containers;
- raw database field editing;
- theme-specific backend logic;
- separate codebases for presets.

Freedom must come from **strong composable blocks**, not uncontrolled DOM editing.

---

# 5. Terminology

## 5.1 Universal Storefront Engine

The renderer used by all V2 stores.

It receives:

- Store
- Page Template
- Published Layout Version
- Sections / Blocks
- Store data
- Design tokens
- Device context where applicable

and produces the public storefront.

## 5.2 Builder

The merchant-facing visual editing environment.

It edits Draft state and never silently changes the published storefront.

## 5.3 Page Template

The layout definition for a storefront route type.

Examples:

- Home
- Product Detail
- Product Listing / Category
- Collection
- Search Results
- Cart

## 5.4 Section

A top-level ordered unit inside a page.

Examples:

- Hero
- Product Carousel
- Category Grid
- Promotional Banner
- Brand Rail

## 5.5 Block

A composable element inside a section or global region.

Examples:

- Logo
- Search
- Cart icon
- Button
- Heading
- Image
- Menu
- Social links

For Phase 1, nesting should be deliberately limited.

## 5.6 Global Region

A storefront-wide editable region shared across page templates.

Initially:

- Announcement Bar
- Header
- Navigation
- Footer

## 5.7 Preset

A saved configuration of:

- page structures
- global regions
- block settings
- design tokens
- responsive settings

A preset is **data**, not a new family implementation.

---

# 6. Merchant Experience — One Complete Builder Screen

The merchant should be able to perform the majority of storefront design work from one unified workspace.

Recommended desktop structure:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Page ▼   Undo  Redo              Draft Saved    Preview   Publish   │
├──────────────┬────────────────────────────────────┬──────────────────┤
│              │                                    │                  │
│ BLOCK        │                                    │ SETTINGS         │
│ LIBRARY      │          LIVE CANVAS               │ PANEL            │
│              │                                    │                  │
│ Hero         │                                    │ Content          │
│ Slider       │                                    │ Layout           │
│ Products     │                                    │ Style            │
│ Categories   │                                    │ Responsive       │
│ Banner       │                                    │ Data             │
│ Brands       │                                    │ Visibility       │
│ Text         │                                    │                  │
│ Button       │                                    │                  │
│ Video        │                                    │                  │
│ ...          │                                    │                  │
├──────────────┴────────────────────────────────────┴──────────────────┤
│            + Add Section                                            │
└──────────────────────────────────────────────────────────────────────┘
```

The builder must feel like editing the real storefront, not editing abstract database forms.

---

# 7. Page Selector

At the top of the builder:

```text
Page:
[ Home ▼ ]
```

Initial supported page types:

1. Home
2. Product Detail
3. Product Listing / Category
4. Collection
5. Search Results
6. Cart

Architecture must allow future page types without rewriting the editor:

- Customer Account
- Wishlist
- Blog Index
- Blog Detail
- Content Page
- Checkout presentation components
- Brand page
- Custom landing page

---

# 8. Required Editing Operations

Every supported top-level section must support where applicable:

- Add
- Select
- Reorder Up/Down
- Drag reorder later if safe
- Duplicate
- Hide
- Show
- Delete
- Edit
- Save
- Device visibility
- Optional scheduling later
- Optional save-as-reusable-section later

All actions must be tenant scoped.

---

# 9. Draft / Preview / Publish Contract

This is a critical architectural contract.

## Draft

All builder edits affect Draft only.

## Preview

Preview must render the actual Draft through the same universal storefront engine used by public rendering.

Preview must not require Publish.

## Publish

Publish atomically makes a validated Draft the public version.

## Rollback

Merchant can restore an earlier published version.

## New Draft After Publish

Creating a new Draft from Published must clone **all design state and all section-bound content references correctly**.

No section-specific media may be accidentally left attached only to the old section IDs.

This must be explicitly tested.

---

# 10. Global Regions

Global regions must be editable in the same builder.

## 10.1 Announcement Bar

Possible blocks/settings:

- text
- link
- dismissible option
- background
- text color
- visibility
- mobile visibility

## 10.2 Header Builder

Header must not be one hardcoded template.

Header should be composed from limited structured Rows and Blocks.

Example A:

```text
Row 1: [ Announcement ]
Row 2: [ Logo ] [ Search ] [ Account ] [ Wishlist ] [ Cart ]
Row 3: [ Main Navigation ]
```

Example B:

```text
Row 1: [ Menu Button ] [ Center Logo ] [ Search Icon ] [ Cart ]
```

Supported initial Header blocks:

- Logo
- Store Name
- Search bar
- Search icon
- Main menu
- Category menu
- Mega menu trigger
- Account
- Wishlist
- Cart
- Custom internal link
- Custom external link
- CTA Button
- Phone
- Social icon
- Spacer

Header settings:

- row order
- row height
- width mode
- sticky on/off
- background
- border
- shadow
- desktop visibility
- mobile visibility
- alignment
- spacing

Mobile header must be configurable independently where needed.

## 10.3 Navigation

Navigation must support:

- Store menu
- Category-driven menu
- Manually managed menu
- Nested items
- Mega menu eventually
- Internal link
- External link
- Collection link
- Category link
- Content page link where platform architecture supports it

## 10.4 Footer Builder

Footer should also use constrained Rows / Columns / Blocks.

Initial Footer blocks:

- Logo
- Store description
- Menu
- Contact details
- Phone
- Email
- Address
- Social links
- Newsletter
- Trust / badge region
- Custom text
- Internal link
- External link
- Copyright

---

# 11. Home Page Block Library

The Home page must support at least:

## Media / Promotion

- Single Hero Image
- Hero Image + Text
- Hero Slider
- Full-width Slider
- Multi-card Promotional Slider
- Single Banner
- Two-column Banner
- Multi-column Banner
- Video
- Story Rail

## Commerce

- Product Grid
- Product Carousel
- Selected Products
- Newest Products
- Discounted Products
- Best Selling Products when data exists
- Merchant Collection
- Category Grid
- Category Carousel
- Brand Grid
- Brand Carousel

## Content

- Heading
- Rich Text
- Image
- Image + Text
- Text + Button
- CTA Button
- Internal Link Button
- External Link Button
- Divider
- Spacer

Future extensibility must allow new blocks without migrations that rewrite all previous layouts.

---

# 12. Hero Requirements

The merchant may want:

- one large image;
- one large image with overlay text;
- normal slider;
- full-screen slider;
- serial carousel;
- video hero;
- no hero at all.

Therefore Hero is not mandatory.

Settings may include:

- source media
- desktop media
- mobile media
- headline
- subtitle
- CTA
- CTA destination
- content alignment
- overlay
- height
- width
- autoplay if slider
- interval
- navigation arrows
- pagination
- mobile behavior

---

# 13. Product Sections

A product section must not be tied to one hardcoded product query.

Merchant selects its data source.

Possible sources:

- Manual selected products
- Merchant Collection
- Category
- Newest
- Discounted
- Best seller when supported
- Tag / query rules later

Presentation settings:

- Grid / Carousel
- Products per row
- Number of products
- Image ratio
- Show/hide brand
- Show/hide price
- Show/hide compare price
- Show/hide wishlist
- Show/hide quick add
- Show/hide badges
- Card density
- desktop columns
- tablet columns
- mobile columns

Product card settings should come from shared product-card configuration, not family-specific HTML.

---

# 14. Product Detail Page Builder

The Product Detail page must belong to the same visual system.

Initial components:

- Breadcrumb
- Product Gallery
- Thumbnail Rail
- Product Brand
- Product Title
- Rating when supported
- Price
- Compare Price / Discount
- Variant Selector
- Color Swatches
- Size Selector
- Quantity
- Stock state
- Add to Cart
- Wishlist
- Compare when supported
- Size Guide
- Share
- Short Description
- Full Description
- Specifications
- Video
- FAQ if merchant content exists
- Related Products
- Recommended Collection

The merchant may reorder supported sections.

Example:

```text
Breadcrumb
Product Main Area
Description
Specifications
Related Products
```

Another store may use:

```text
Product Main Area
Trust badges
Description
Video
Related Products
FAQ
```

The storefront must remain functionally correct regardless of composition.

---

# 15. Category / Product Listing Page

Must be rendered by Universal Storefront Engine.

Configurable regions:

- Header
- Breadcrumb
- Category title
- Category description
- Category image/banner
- Subcategory chips/grid
- Filter panel
- Sort control
- Product count
- Product grid
- Pagination / load more
- Footer

Configurable presentation:

- sidebar vs drawer filters
- desktop columns
- mobile columns
- card settings
- content width
- spacing

Do not use a generic legacy template outside the V2 renderer.

---

# 16. Collection Page

Collection pages must use the same store shell and design tokens.

Configurable:

- Collection hero/title
- description
- optional image
- sort
- filters when relevant
- grid columns
- product-card settings
- additional promotional section
- footer

---

# 17. Search Results

Search must visually belong to the same storefront.

Configurable:

- search input presentation
- result count
- filters
- sorting
- grid
- empty state
- suggestions
- related categories later

---

# 18. Cart

Initial cart configuration should support:

- cart item rows/cards
- product image
- variant details
- quantity control
- remove
- gift wrap where enabled
- coupon
- subtotal
- shipping notice
- order summary
- checkout CTA
- recommended products optionally

Mini-cart should be implemented as a reusable global component rather than family-specific behavior.

---

# 19. Links and Buttons

A generic CTA / Button block must support destinations such as:

## Internal

- Home
- Product
- Category
- Collection
- Search
- Cart
- Content Page
- Custom internal URL where safe

## External

- HTTPS URL

Settings:

- label
- icon optional
- style
- size
- alignment
- open in new tab for external links
- nofollow option later

URL validation is required.

---

# 20. Design System / Global Appearance

A merchant should not need to edit every block to change store identity.

Global design tokens should support at least:

## Colors

- Background
- Surface
- Primary
- Secondary
- Text
- Muted text
- Border
- Success
- Warning
- Error

## Typography

- Primary font
- Heading font if supported
- Base size scale
- Heading scale
- Weight

## Shape

- Border radius scale
- Button radius
- Card radius

## Layout

- Content max width
- Section vertical spacing
- Grid gaps

## Effects

- Shadow level
- Borders

Blocks can override selected tokens where appropriate.

---

# 21. Responsive Editing

Builder must provide at minimum:

- Desktop preview
- Mobile preview

Tablet can be added if useful.

Merchant must be able to configure:

- visibility by device
- columns per device
- spacing overrides where necessary
- alternate mobile image for media-heavy sections
- mobile header arrangement

Avoid giving hundreds of low-level CSS controls in V2 Phase 1.

---

# 22. Presets

Future customer-facing "templates" are presets.

Example:

```text
Preset: Fashion Editorial
```

may define:

- header layout
- navigation layout
- home sections
- product-page arrangement
- product-card settings
- color tokens
- typography
- footer arrangement

Applying a preset must create a Draft.

It must never require a separate renderer.

A preset must be editable after application.

A merchant can:

1. choose preset;
2. customize it freely;
3. publish;
4. optionally reset selected regions later.

---

# 23. Existing Families — Archive Strategy

Existing families must not be immediately deleted.

Expected existing set currently includes historical families such as:

- modern_fashion
- heritage_premium
- artisan_editorial
- vibrant_catalog
- nordic_living
- atlas_catalog
- ava_fashion
- toranj_gifting
- sarv_stock
- sepidar_handmade
- zarrin_jewelry

Kiro must verify the exact current registry.

Required action:

1. Freeze feature development on family-specific storefronts.
2. Remove / hide them from merchant-facing new-store selection once V2 replacement is ready.
3. Preserve them in code temporarily as legacy/reference material.
4. Do not delete tests or code until migration strategy is approved.
5. Identify reusable UI patterns and behavior before retirement.
6. No new family-specific business logic.

---

# 24. Repository Audit — MUST HAPPEN BEFORE CODING

Kiro must **not assume this is a greenfield system**.

RastiSi4 already contains significant infrastructure.

Before proposing schema changes or writing V2 code, perform a complete source audit and produce a reuse matrix.

At minimum inspect:

```text
apps/storefront_builder/
apps/stores/
apps/catalog/
apps/content/
apps/core/
apps/cart/
apps/orders/
templates/
static/
docs/
```

Also inspect all relevant migrations and tests.

---

# 25. Exact Existing Capabilities to Audit

Kiro must determine the current implementation status of every item below.

Do not mark an item "available" based only on a filename. Inspect implementation and tests.

## 25.1 Layout Lifecycle

Check for:

- StorefrontLayout
- StorefrontLayoutVersion
- StorefrontSection
- Draft
- Published version
- Publish service
- Preview flow
- Rollback
- Clone published → draft
- Validation
- Rate limits
- revision/version history
- concurrency behavior if present

For each:
- location
- status
- reusable?
- change needed?

## 25.2 Existing Section Model

Determine:

- how sections are identified
- section_key behavior
- ordering
- config storage
- visibility
- collapsed state
- media relationships
- whether multiple same-type sections are supported
- whether duplication is supported
- whether section data can be safely cloned
- whether page ownership exists or sections are homepage-only

## 25.3 Existing Appearance Model

Inspect:

- appearance_config
- design tokens
- colors
- typography
- family_slug
- presets
- CSS variables
- ShopSettings visual identity
- logo/favicon/branding fields

Determine which should become V2 global design tokens.

## 25.4 Existing Family Registry

Find:

- registry
- family definitions
- family presets
- template mappings
- CSS mappings
- defaults
- tests

Document exact coupling to:

- homepage
- header/footer
- product cards
- product detail
- category
- collection
- search
- cart

This audit is crucial for retirement planning.

## 25.5 Content / Media

Inspect current models and editor flows for:

- HeroSlide
- PromotionalBanner
- StoryRailItem
- ContentPage
- Menu
- MenuItem
- FooterSettings
- SocialLink

Determine:

- store scope
- section scope
- publish behavior
- clone behavior
- media validation
- ordering
- enable/disable
- builder integration
- whether they can become generic block data

Special attention:
Current section-bound media must be tested across:

```text
Published → New Draft → Edit → Preview → Publish
```

No orphaned old-section relationships are acceptable.

## 25.6 Catalog Data Sources

Audit reusable storefront queries for:

- Product
- ProductVariant
- ProductImage
- Category
- Brand
- MerchantCollection
- MerchantCollectionItem
- product visibility
- published/active product rules
- stock
- discounts/pricing
- variant image switching
- category scoping
- collection scoping

V2 must use existing tenant-safe services wherever possible.

## 25.7 Menus

Audit:

- menu model
- menu item destinations
- nested menu behavior
- PROTECT relationships
- category destinations
- collection destinations
- external URL support
- internal page support
- editor
- header integration

Determine what is already enough for Header Builder.

## 25.8 Product Detail Functionality

Audit existing support for:

- gallery
- thumbnails
- variant selectors
- variant image changes
- quantity
- add to cart
- wishlist
- compare
- size guide
- video
- sharing
- tabs
- specifications
- FAQ
- related products

Separate:
- backend capability
- current frontend implementation
- browser verified status

## 25.9 Cart / Commerce

Audit existing:

- cart service
- stock enforcement
- variant stock
- gift wrap
- mini-cart
- coupons
- totals
- order snapshot behavior

V2 must not reimplement business rules already correctly enforced by services.

## 25.10 Tenant Boundaries

Verify current store scoping for:

- layouts
- sections
- media
- products
- variants
- categories
- collections
- menus
- content pages
- cart
- wishlist
- orders

No universal-builder change may weaken tenant isolation.

## 25.11 Admin Portal / Builder UI

Audit existing:

- builder routes
- appearance picker
- section editor
- media editors
- preview
- publish
- rollback
- drag/reorder controls
- section enable/disable
- current navigation
- mobile usability

Determine which routes/components can be reused for the V2 single-screen editor.

## 25.12 Tests

List all relevant tests and classify:

- unit
- integration
- tenant isolation
- template syntax
- visual/static
- cart
- builder lifecycle
- family regression
- media
- end-to-end

Do not delete passing safety tests just because the UI architecture changes.

---

# 26. Required Repository Reuse Matrix

Before implementation Kiro must create a document/table like:

| Capability | Existing implementation | Evidence | Reuse as-is | Extend | Replace | Notes |
|---|---|---|---:|---:|---:|---|
| Draft layout | ... | file/test | ✅ | | | |
| Publish | ... | ... | ✅ | | | |
| Rollback | ... | ... | | ✅ | | |
| Section ordering | ... | ... | | ✅ | | |
| Section media cloning | ... | ... | | | ✅ | current issue |
| Product collection query | ... | ... | ✅ | | | |
| Header editor | ... | ... | | ✅ | | |
| Family registry | ... | ... | | | ✅/archive | |
| ... | ... | ... | ... | ... | ... | ... |

This matrix is a required deliverable.

---

# 27. Proposed V2 Domain Shape

This is a design direction, **not permission to create migrations immediately**.

Kiro must first compare it to existing models and reuse current schema whenever reasonable.

Conceptually the system needs:

```text
Storefront
 ├── Global Design
 ├── Global Regions
 │    ├── Announcement
 │    ├── Header
 │    ├── Navigation
 │    └── Footer
 │
 └── Page Templates
      ├── Home
      ├── Product Detail
      ├── Product Listing
      ├── Collection
      ├── Search
      └── Cart
           └── ordered Sections
                 └── typed configuration
```

A possible normalized concept:

```text
StorefrontLayout
StorefrontLayoutVersion
StorefrontPage
StorefrontSection
StorefrontBlock
```

But if existing version/section models can express this through backward-compatible extensions, prefer extension over unnecessary replacement.

---

# 28. Typed Configuration

Avoid an uncontrolled JSON dumping ground.

Each section/block type needs:

- schema
- defaults
- validation
- renderer
- editor schema
- migration/version strategy for config changes

Example conceptual registry:

```python
BLOCK_REGISTRY = {
    "hero": HeroBlockDefinition(...),
    "product_carousel": ProductCarouselDefinition(...),
    "category_grid": CategoryGridDefinition(...),
    "button": ButtonDefinition(...),
}
```

Each definition should describe:

- allowed pages
- default config
- validation
- data resolver
- template/component
- editor controls
- responsive options

Implementation details may differ after repository audit.

---

# 29. Renderer Contract

Public routes should not choose unrelated templates manually.

Conceptually:

```text
request
  ↓
tenant/store resolution
  ↓
route/page type resolution
  ↓
published storefront version
  ↓
global regions + page template
  ↓
section/block registry
  ↓
tenant-scoped data resolvers
  ↓
universal renderer
```

All supported public page types must share:

- global design tokens
- header
- navigation
- product-card system
- footer
- consistent width/spacing rules

---

# 30. Data Resolver Contract

Section renderers should not contain random ORM queries.

Use typed data resolvers/services.

Examples:

```text
ProductCarousel
  source = collection
  collection_id = ...
```

Resolver verifies:

- collection belongs to current store;
- products are storefront visible;
- product/variant relations stay inside tenant;
- limits are respected.

Same for:

- category
- manual products
- brand
- newest
- discounts

Cross-store object IDs supplied through config must be rejected.

---

# 31. Builder Safety Requirements

The builder must validate all references.

Never trust:

- product IDs
- category IDs
- collection IDs
- media IDs
- menu IDs
- page IDs

from browser payloads without store scoping.

Also preserve:

- CSRF protection
- auth
- owner/staff authorization
- rate limiting where appropriate
- HTML sanitization for rich text
- URL safety for external links
- uploaded image validation

---

# 32. Rendering Performance

Avoid an ORM query per block.

The implementation should consider:

- page-level prefetch
- block resolver batching
- controlled limits
- cached static config where safe
- no cross-tenant cache keys
- media thumbnails
- lazy image loading where appropriate

Do not optimize prematurely, but do not create obvious N+1 architecture.

---

# 33. Accessibility

Initial blocks should support:

- alt text for images
- keyboard navigation
- visible focus
- semantic buttons/links
- accessible slider controls
- sufficient contrast defaults
- ARIA labels for icon-only actions
- reduced-motion consideration

---

# 34. Mobile Requirements

Mobile is not a smaller desktop screenshot.

At minimum verify:

- no horizontal overflow
- no iPhone form zoom caused by input text smaller than 16px
- usable navigation
- mobile header
- carousel touch behavior
- product grid
- filters as drawer where applicable
- PDP variant controls
- cart controls
- builder itself remains usable enough for merchant tasks

---

# 35. Preset Strategy

Do not build many presets until the universal engine is stable.

Recommended order:

1. build engine;
2. build one neutral default preset;
3. prove one complex real-world-inspired preset;
4. verify every route;
5. only then scale preset library.

A preset may later recreate design patterns inspired by reference stores, but it must remain data/config on top of the universal engine.

---

# 36. Migration from Existing Stores

Kiro must propose, but not blindly implement, migration policy.

Questions to answer:

- Do existing stores stay on Legacy renderer temporarily?
- Can a Legacy family be converted into a V2 preset?
- Should conversion create a Draft rather than publish immediately?
- How is rollback handled?
- How do we preserve old published design until merchant approves V2?
- What happens to family_slug?

Preferred safety strategy:

> Existing storefronts stay functional on Legacy until explicitly migrated.  
> New V2 development does not break their published sites.

---

# 37. Phase Plan

## Phase 0 — Freeze and Audit

No V2 implementation before this is complete.

Deliverables:

- repository audit;
- route/template map;
- model map;
- lifecycle map;
- reuse matrix;
- legacy-family dependency map;
- identified blockers;
- proposed schema delta;
- implementation plan.

## Phase 1 — Universal Rendering Skeleton

Goal:

- one V2-capable store;
- global design tokens;
- header/footer through universal shell;
- Home / Product / Listing / Collection all use same shell;
- Draft / Preview / Publish / Rollback work;
- no visual sophistication required yet.

## Phase 2 — Single-Screen Builder Foundation

Goal:

- page selector;
- canvas;
- block library;
- settings inspector;
- add/delete/reorder/duplicate/hide;
- desktop/mobile preview;
- autosave or explicit safe save;
- preview draft.

## Phase 3 — Home Blocks

Implement high-value blocks:

- Hero
- Slider
- Banner
- Category Grid
- Product Grid
- Product Carousel
- Collection
- Brands
- Text
- Image + Text
- Button
- Story Rail
- Spacer

## Phase 4 — Header / Footer Composer

Structured row/block composer.

## Phase 5 — Commerce Pages

- Product Detail
- Listing
- Collection
- Search
- Cart

All through V2.

## Phase 6 — Presets

- Neutral default
- One complex preset
- Import/apply preset flow

## Phase 7 — Legacy Migration

Only after browser QA and regression confidence.

---

# 38. Definition of Done — Engine

Universal Storefront Builder V2 is not considered technically viable until:

- Homepage uses V2 renderer.
- Product Detail uses V2 renderer.
- Product Listing uses V2 renderer.
- Collection uses V2 renderer.
- Search uses V2 renderer.
- Cart uses V2 renderer.
- Header/footer stay visually consistent across routes.
- Draft Preview displays draft content.
- Public storefront displays only published content.
- Rollback works.
- New Draft from Published retains all media and block references.
- Tenant boundaries pass tests.
- Product/variant/cart behavior still passes commerce tests.
- Desktop and mobile browser smoke tests pass.

---

# 39. Definition of Done — Builder UX

Merchant can, in one main editor:

- select page;
- select section;
- add section;
- remove section;
- reorder;
- duplicate;
- hide/show;
- edit content;
- configure data source;
- configure layout;
- configure key styles;
- inspect desktop;
- inspect mobile;
- edit header;
- edit footer;
- preview Draft;
- publish;
- rollback.

---

# 40. Definition of Done — Design Freedom

We must be able to create at least two demo storefronts using the same V2 engine that differ materially in:

- header composition;
- navigation;
- Hero;
- homepage ordering;
- category presentation;
- product-card density;
- banners;
- typography;
- colors;
- section spacing;
- footer composition;
- Product Detail composition.

No separate family templates are allowed to create the difference.

---

# 41. Required Browser QA

Static/template tests are not sufficient.

For every major milestone, use real browser evidence.

At minimum capture:

## Desktop

- Home
- Product Detail
- Product Listing
- Collection
- Builder

## Mobile

- Home
- Product Detail
- Product Listing
- Builder core workflow

Check interactions, not just screenshots.

---

# 42. Required Tests

Preserve and expand automated coverage.

At minimum:

## Lifecycle

- draft creation
- preview
- publish
- rollback
- clone published to draft
- media/reference clone integrity

## Tenant Isolation

- cross-store section reference rejected
- cross-store product rejected
- cross-store category rejected
- cross-store collection rejected
- cross-store media rejected
- cross-store menus rejected

## Block Registry

- registered block schemas valid
- defaults valid
- renderer exists
- editor metadata exists
- unknown block rejected safely

## Page Types

- V2 route shell consistency
- correct published version
- draft preview does not leak publicly

## Commerce Regression

- stock
- variants
- cart
- gift wrap
- wishlist
- orders

---

# 43. Legacy Code Rules During Migration

Until migration is complete:

- no force-delete of old families;
- no broad refactor unrelated to V2;
- no breaking migration without rollback plan;
- no changing commerce service semantics just to fit UI;
- no weakening tenant checks;
- no force push;
- do not merge into main unless explicitly instructed;
- keep GitHub as canonical source;
- keep working tree clean between checkpoints.

---

# 44. Git / Branch Safety

Before work:

```text
git status
git branch --show-current
git rev-parse HEAD
git fetch --prune
```

Confirm expected official work branch before edits.

Do not create unrequested PRs.

Do not merge into main.

Commit by coherent checkpoint.

Push only to the agreed branch.

---

# 45. Required Documentation Placement

Kiro must add **this exact specification** to the repository before implementation.

Recommended path:

```text
docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md
```

If repository documentation conventions require another directory, keep the filename and explain the chosen location.

Do not silently rewrite this product contract.

If Kiro proposes changes, place them in a separate ADR / proposal document.

---

# 46. Companion UX Prototype

There is a separate HTML UX prototype representing the intended editor concept:

```text
rastisi_builder_v2_prototype.html
```

Recommended repository destination:

```text
docs/prototypes/storefront-builder-v2/rastisi_builder_v2_prototype.html
```

The prototype is not production code.

Its purpose is to communicate:

- single-screen editor;
- block library;
- live canvas;
- settings inspector;
- page selector;
- desktop/mobile preview;
- global header/footer editing;
- section operations.

Kiro should use it as UX intent, not copy its mock implementation into production.

---

# 47. Kiro — Mandatory First Task

**Do not start coding V2 yet.**

Your first task is repository reconnaissance.

Perform a deep audit of the current RastiSi4 source and answer:

1. What parts of Universal Storefront Builder V2 already exist?
2. Which existing models are reusable as-is?
3. Which existing models only need extension?
4. Which concepts are currently homepage-only?
5. Which routes bypass the family/storefront renderer?
6. Which current page types already use a common shell?
7. What is the exact Draft → Preview → Publish → Rollback lifecycle?
8. Does Published → New Draft correctly clone section-bound media?
9. Which block-like systems already exist?
10. How are section media currently linked?
11. How are header/footer/menu/content settings currently modeled?
12. How are design tokens currently modeled?
13. How are current family presets represented?
14. Which product/catalog services are tenant-safe and reusable?
15. What gaps prevent a universal renderer today?
16. What can be reused from existing builder UI?
17. Which tests already protect the lifecycle and tenant boundaries?
18. Which old family assets/components are worth extracting into generic blocks?

---

# 48. Kiro — Required Audit Deliverables

Before implementation, commit the following documentation:

## A. Existing Capability Audit

Recommended:

```text
docs/architecture/STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md
```

Must cite concrete:

- files
- classes
- functions
- routes
- templates
- services
- models
- migrations
- tests

## B. Reuse Matrix

Recommended:

```text
docs/architecture/STOREFRONT_BUILDER_V2_REUSE_MATRIX.md
```

Classify every relevant component:

```text
REUSE_AS_IS
EXTEND
REFACTOR
LEGACY_KEEP
REPLACE
REMOVE_LATER
```

## C. Route / Renderer Map

Recommended:

```text
docs/architecture/STOREFRONT_BUILDER_V2_ROUTE_RENDERER_MAP.md
```

For each public route show:

```text
URL pattern
View
Template
Shell
Family influence
Store scope
V2 migration requirement
```

## D. Data / Lifecycle Map

Recommended:

```text
docs/architecture/STOREFRONT_BUILDER_V2_DATA_LIFECYCLE.md
```

Map:

```text
Draft
Preview
Publish
Rollback
Clone
Media
Sections
Appearance
```

## E. Proposed Implementation Plan

Recommended:

```text
docs/architecture/STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md
```

Must be evidence-based on the repository audit.

Do not begin implementation until these documents are reviewed.

---

# 49. Kiro — Important Audit Principle

Do not report:

> "Feature exists"

because a model/template/file exists.

For each capability, classify evidence:

```text
SOURCE_ONLY
TESTED
RUNTIME_VERIFIED
BROWSER_VERIFIED
```

Example:

```text
Variant image switching:
SOURCE_ONLY / TESTED / BROWSER_VERIFIED?
```

This prevents repeating the previous mistake where source completeness looked stronger than actual storefront behavior.

---

# 50. Kiro — Special Investigation: Current Builder Media Bug Risk

Explicitly investigate section-bound media.

Current architecture has used models such as:

- HeroSlide
- PromotionalBanner
- StoryRailItem

Confirm whether their ownership is:

```text
Store → Section
```

or another structure.

Then trace clone behavior when a Published layout becomes a new Draft.

Verify by code and tests whether the new Draft receives correct media relations.

If not, document:

- exact failure mode;
- affected models;
- affected services;
- backward-compatible remediation options.

Do not patch this before the audit deliverable unless required to reproduce safely.

---

# 51. Kiro — Special Investigation: Route Inconsistency

Build a concrete route/template matrix for at least:

```text
/
product detail
/products/
category-filtered listing
/collections/
/collections/<slug>/
search
cart
wishlist
content pages
```

For each, answer:

- Does it use the same storefront shell?
- Does it use family-specific header/footer?
- Does it use universal product-card config?
- Does it receive appearance tokens?
- Does it use generic base.html?
- Does it expose legacy appearance?

This audit is required before designing the V2 renderer.

---

# 52. Kiro — Do Not Destroy Existing Work

The previous families are unsuccessful as the long-term architecture, but they are still valuable reference material.

Extract lessons such as:

- header compositions;
- product card variants;
- hero layouts;
- footer styles;
- PDP layouts;
- responsive patterns;
- interaction ideas.

Those can become:

- block variants;
- preset settings;
- design-token presets;
- reusable component options.

The objective is not to throw away all prior work.

The objective is to stop maintaining every design as an independent site implementation.

---

# 53. Final Product Vision

The end state should feel like this:

A merchant enters:

```text
Appearance → Storefront Builder
```

and sees one complete visual editor.

They choose:

```text
Page: Home
```

They may create:

```text
Announcement
Header
Large Image
Slider
Categories
Products
Banner
Products
Brands
Custom CTA
Footer
```

Another merchant may create:

```text
Header
Video Hero
Story Rail
Sale Products
Two Banners
Editorial Text
Collection Carousel
Footer
```

Another merchant may have no Hero and no Brands.

No developer creates a new Family for these differences.

All three stores use the same storefront engine.

---

# 54. Product Success Criterion

The architecture succeeds when we can say:

> "A new visual design usually requires configuration or a new reusable block — not a new storefront codebase."

That is the core contract of Universal Storefront Builder V2.

---

# 55. Immediate Next Action

1. Add this file to the repository.
2. Add the HTML UX prototype under docs/prototypes if supplied.
3. Perform the complete existing-capability audit.
4. Commit audit documents only.
5. Run relevant existing tests needed to verify audit claims.
6. Do **not** implement V2 yet.
7. Report:
   - exact current capabilities;
   - reuse matrix;
   - architectural blockers;
   - recommended smallest safe Phase 1;
   - files/models/services expected to change in Phase 1;
   - risks;
   - tests required before and after.

Wait for explicit approval before implementation.

---

# 56. Approval Gate

Kiro must stop after the audit checkpoint.

The next implementation phase begins only after the owner reviews:

- Existing Capability Audit
- Reuse Matrix
- Route/Renderer Map
- Data/Lifecycle Map
- Implementation Plan

**No automatic continuation into implementation.**

---

## End of Specification
