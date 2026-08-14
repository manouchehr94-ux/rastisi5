# RastiSi Storefront Builder — Final Specification

**Version:** 1.0  
**Status:** Approved Product & Implementation Specification  
**Golden Visual Reference:** `Beraito Exact Frontend V5`

---

## 1. Product Goal

RastiSi must be a **Universal Storefront Builder** that allows a store owner to design and customize their storefront without needing HTML, CSS, JavaScript, or JSON.

Core principle:

> One rendering engine, a reusable block library, and many data-driven presets.

RastiSi must **not** create a separate template engine, renderer family, or duplicated storefront codebase for each visual style.

Target architecture:

```text
Universal Storefront Engine
          │
          ├── Blocks
          ├── Layout
          ├── Palette
          ├── Presets
          └── Store Data
```

---

## 2. Golden Visual Reference

The approved visual reference is:

```text
Beraito Exact Frontend V5
```

This is the official **Golden Reference #1** for the RastiSi storefront system.

Its visual structure — including dimensions, spacing, card proportions, header, hero, product rails, promotional banners, footer, and general composition — is accepted as the reference design.

Implementation rule:

> When V5 is converted into Universal Blocks, flexibility must be added without degrading, reinterpreting, or redesigning the approved visual result.

The first default preset must reproduce a storefront visually very close to V5 without requiring manual editing.

---

## 3. Current Builder Scope

For the current phase, the main visual Builder focuses on:

```text
Homepage
```

The following pages initially keep standardized system layouts:

```text
Category / Product Listing
Search
Cart
Checkout
Customer Account
```

The Product Detail Page (PDP) also begins with a standardized layout, but its architecture must be prepared for gradual block-based customization.

---

## 4. Block System

Every independently configurable visual section is a **Block Instance**.

Examples:

```text
Hero
Category Grid
Product Rail
Banner
Trust Features
Brands
Blog
Instant Offer
```

Each block must support, where appropriate:

```text
Show / Hide
Drag & Drop
Move Up
Move Down
Duplicate
Lock
Configure
Change Color
Change Background
Change Spacing
```

A block type may be used multiple times on the same page without an artificial hard limit.

Example:

```text
Product Rail
Product Rail
Banner
Product Rail
Categories
Product Rail
Product Rail
```

This is valid.

---

## 5. Layout System

The layout system must be powerful but easy for non-technical users.

### 5.1 Vertical Ordering

All homepage blocks must be reorderable by Drag & Drop.

The Builder must also provide:

```text
↑ Move Up
↓ Move Down
```

for users who prefer buttons over dragging.

### 5.2 Multiple Blocks in One Row

The system must support generic row/grid compositions with:

```text
1 column
2 columns
3 columns
4 columns
```

Examples:

```text
┌─────────┬─────────┐
│ Group 1 │ Group 2 │
└─────────┴─────────┘
```

and:

```text
┌────┬────┬────┬────┐
│ 1  │ 2  │ 3  │ 4  │
└────┴────┴────┴────┘
```

The internal implementation may use a concept such as:

```text
Grid Row / Block Group
```

but the merchant-facing UI should simply expose something like:

```text
Layout:
[ Two Columns ▼ ]
```

The user must not be required to understand CSS Grid.

---

## 6. Responsive Design

The merchant designs **one storefront**, not a separate desktop site and mobile site.

The system must automatically provide responsive behavior across:

```text
Desktop
Tablet
Mobile
```

In the initial version:

- Mobile block order remains the same as desktop.
- Mobile column counts are calculated automatically.
- Mobile typography scales automatically.
- Mobile spacing adapts automatically.
- Responsive image behavior is handled automatically.
- Horizontal page overflow must not occur.

Advanced responsive overrides may be introduced later, but normal users should not need to configure mobile separately.

---

## 7. Width and Container System

The storefront uses a standard global content container.

Each block can support one of two width modes:

```text
Contained
Full Width
```

A full-width block may use a full-width background while keeping its inner content constrained to the standard container.

Example:

```text
██████████████████████████████████████
████      Inner Content Container     ████
██████████████████████████████████████
```

This is required for sections such as the colored Product Rails in the V5 reference.

---

## 8. Spacing

### Basic Mode

The user sees simple options:

```text
Vertical Spacing:
Small
Normal
Large
```

### Advanced Mode

Advanced users may control precise values such as:

```text
Padding Top
Padding Bottom
Margin Top
Margin Bottom
```

Non-technical users must not be forced to work with CSS terminology.

---

## 9. Background System

Each block may support:

```text
Color
Image
Pattern
```

Example:

```text
Product Rail

Background Color:
#e62b35

Pattern:
Stationery
```

Patterns must be reusable system assets and must not depend on a specific preset's custom renderer.

---

## 10. Palette System

Each storefront has a global design palette.

At minimum, the system should expose semantic tokens such as:

```text
Primary
Secondary
Accent
Background
Surface
Text
Muted Text
Success
Warning
Danger
Border
```

Changing the Primary color should intelligently affect relevant visual states such as:

```text
Buttons
Active States
Underlines
Badges
Links
Selected Tabs
```

### 10.1 Ready-Made Palettes

The system must ship with at least **10 ready-made color palettes**.

Example starting set:

```text
Red
Green
Blue
Purple
Orange
Pink
Turquoise
Black / Gold
Cream / Brown
Minimal Light
```

The final merchant-facing names can later be localized and branded.

### 10.2 Custom Color Overrides

Merchants must not be limited to predefined palettes.

Individual block colors may be overridden through a simple UI:

```text
○ Use Theme Color
● Custom Color
  [ Color Picker ]
```

### 10.3 Layout Presets and Color Presets Are Separate

A layout composition and a palette must be independently selectable.

For example:

```text
V5 Layout Preset
+
Blue Palette
```

or:

```text
V5 Layout Preset
+
Green Palette
```

without changing the block structure.

---

## 11. Header Builder

The Header is composed of multiple regions.

The V5 reference includes:

```text
Utility Row
Main Row
Navigation Row
Mega Menu
```

Some header functionality is mandatory.

At minimum:

```text
Logo
Navigation Access
Cart
```

must remain available so the merchant cannot accidentally make the storefront unusable.

Other elements such as:

```text
Search
Account
Utility Row
Promo Buttons
Contact Information
```

may be shown or hidden.

---

## 12. Header Reordering

Elements such as:

```text
Logo
Search
Account
Cart
Promo Buttons
```

must be repositionable.

However, the Builder should constrain invalid combinations that would visibly break the storefront.

The product principle is:

> High design freedom, but not destructive freedom.

---

## 13. Header Size and Sticky Behavior

The merchant may configure header height with a precise value in advanced settings.

Logo configuration includes at least:

```text
Image
Width
Height
```

Sticky behavior should support configurable modes such as:

```text
Off
Main Header Sticky
Main + Navigation Sticky
```

---

## 14. Mega Menu

The Mega Menu must be a universal component.

Its main data source is:

```text
Real Category Tree
```

but the merchant may also add:

```text
Manual Navigation Items
```

The merchant must be able to:

```text
Hide Categories
Add Manual Items
Add a Promotional Image
Disable the Promotional Image
```

The Mega Menu should respect the core Catalog category order rather than maintaining a completely separate category-order system.

---

## 15. Hero Block

The Hero must support:

```text
Static Image
Slider
Video
```

Each slide may contain:

```text
Title
Subtitle
Image
CTA
CTA Link
Text Color
Text Alignment
Overlay
```

The Hero may be:

```text
Contained
Full Width
```

---

## 16. Hero Tabs

The tab row below the Hero, as seen in V5, must support:

```text
Show / Hide
```

Each tab may contain:

```text
Label
Target Slide
Optional Link
```

---

## 17. Instant Offer Block

The "Instant Offer" module must be an independent block rather than being hard-coded into the Hero.

Therefore the merchant can build:

```text
Hero + Instant Offer
```

or:

```text
Hero Only
```

or place the Instant Offer elsewhere.

In the V5 preset, the Hero and Instant Offer appear side by side.

---

## 18. Product Rail

Product Rail is one of the most important reusable blocks.

Supported product sources include:

```text
Category
Manual Selection
Newest
Best Selling
Discounted
Featured
```

### 18.1 Sorting

Supported sorting options:

```text
Manual
Newest
Best Selling
Price Low → High
Price High → Low
Random
```

### 18.2 Product Count

Product count must be configurable.

Examples:

```text
8
12
16
20
```

### 18.3 Responsive Visible Card Count

The number of visible cards should be calculated automatically from the viewport size.

A normal user should not need to configure:

```text
Desktop = 6
Tablet = 4
Mobile = 2
```

unless advanced responsive controls are introduced later.

---

## 19. Product Card Styles

Product cards should support multiple reusable styles.

The V5 product card becomes the first style.

Future styles may include:

```text
Minimal
Image Focused
Compact
Marketplace
Premium
```

### 19.1 Product Card Options

To keep the Builder simple, Basic Mode should initially expose a few prepared card configurations, for example:

```text
Simple
Standard
Detailed
```

Advanced Mode may later expose individual options such as:

```text
Secondary Hover Image
Old Price
Discount
Rating
Wishlist
Quantity
Cart Button
Badges
Brand
```

---

## 20. Product Rail Design Controls

Each Product Rail may independently define:

```text
Title
Data Source
Sorting
Product Count
Card Style
Background Color
Pattern
View All
Spacing
```

This allows one rail to be red, another green, another blue, etc.

---

## 21. Category Block

Required category display styles:

```text
Circular
Square Card
Large Image
Grid
```

Data sources:

```text
Category Tree
or
Manual Selection
```

Category display imagery uses the actual Category image in the initial version.

---

## 22. Multi-Banner Block

The Banner block must support:

```text
2 columns
3 columns
4 columns
```

Each banner may contain:

```text
Image
Title
CTA
Link
Overlay
```

Responsive sizing must be handled automatically.

The merchant should not be required to create separate mobile artwork for normal use.

---

## 23. Trust / Feature Block

Items such as:

```text
Fast Shipping
Product Guarantee
Secure Payment
In-Person Pickup
Best Price Guarantee
```

must be data-driven.

Each item contains:

```text
Icon
Title
Description
Optional Link
```

The number of items is not hard-coded to five.

The Trust Strip is an independent reusable block and may be placed on the Homepage or above the Footer.

---

## 24. Brands

Brand sections should read from actual Catalog brands.

Manual brands are not required in the initial version.

A carousel presentation should be supported.

---

## 25. Blog

Full Blog integration is not a priority in the current phase.

A simple Blog block may exist, but a complete blog/content-management system may be handled later.

---

## 26. Footer Builder

The Footer is block/column based.

Mandatory minimum content:

```text
Store Identity
Contact Information
Copyright
```

Optional modules may include:

```text
Navigation Column
Contact Column
Map
Trust Strip
Social Links
Enamad / Trust Logos
Payment Logos
Custom Text
Logo / About
```

Footer columns must support:

```text
Add
Remove
Reorder
```

---

## 27. Map

The Footer map is:

```text
Optional
```

It can be enabled or disabled.

---

## 28. Product Detail Page Architecture

The Product Detail Page must be designed with future block-based flexibility in mind.

Critical commerce components include:

```text
Gallery
Product Title
Variants
Price
Purchase Controls
```

These components require **logical protection**.

The Builder must not allow a merchant to accidentally make a product page impossible to purchase from.

---

## 29. PDP Blocks

The PDP architecture should gradually support blocks such as:

```text
Gallery
Title
Rating
Variants
Price
Buy Box
Features
Description
Videos
Reviews
Related Products
Recommendations
```

Many of these may eventually support:

```text
Show / Hide
Reorder
```

The Gallery keeps the standard RTL layout direction.

---

## 30. Sticky Purchase Bar

The PDP Sticky Purchase Bar must support:

```text
On / Off
```

---

## 31. Builder UX

The main Builder uses a three-column structure:

```text
┌───────────┬──────────────────┬───────────┐
│ Library   │ Live Canvas      │ Page Tree │
│           │                  │ / Tools   │
└───────────┴──────────────────┴───────────┘
```

Block-specific settings should open in a focused:

```text
Popup / Settings Panel
```

rather than permanently overloading the screen with every setting.

The goal is to keep editing approachable for non-technical users.

---

## 32. Block Library

The Library contains reusable blocks such as:

```text
Hero
Product Rail
Categories
Banner
Grid
Trust
Brands
Blog
Text
Image
Spacer
Instant Offer
```

Dragging a block from the Library into the Canvas must be supported.

---

## 33. Live Canvas

Changes must be reflected immediately in the Canvas.

There should be no mandatory "Apply" action for ordinary visual edits.

Example:

```text
Background = Green
```

must update the preview immediately.

---

## 34. Block Selection and Settings

Clicking a block opens its own settings interface.

For example:

```text
Product Rail
```

must show Product Rail settings rather than one enormous generic form.

---

## 35. Undo / Redo

Undo and Redo are required from the main Builder version.

Minimum actions:

```text
Undo
Redo
```

---

## 36. Duplicate

Any non-critical block may be duplicated.

Example:

```text
Product Rail
        ↓ Duplicate
Product Rail
Product Rail
```

The user can then change the data source of the duplicate.

---

## 37. Lock

A block may be locked.

When locked:

```text
It cannot be moved
It cannot be deleted
```

This helps prevent accidental layout damage.

---

## 38. Personal Presets

Merchants do **not** need the ability to save personal presets in the current version.

This may be added later.

---

## 39. Preset System

During store setup, the system supports both:

```text
Manual Preset Selection
+
System Recommendation
```

Industry-specific recommendations may be introduced later.

---

## 40. Critical Preset Rule

A Preset contains **no custom renderer code**.

A Preset is data/configuration only.

Conceptually:

```text
Preset X
{
  palette,
  header_config,
  blocks,
  block_order,
  block_settings,
  footer_config
}
```

The system must not create files such as:

```text
preset_x.html
preset_y.html
preset_z.html
```

for each visual preset.

---

## 41. V5 Preset

The Golden Reference V5 becomes:

```text
Default Preset #1
```

but not through a dedicated renderer.

It must be rendered as:

```text
Universal Engine
+
V5 Configuration
```

This is one of the system's major acceptance tests.

---

## 42. Changing Presets

Changing the preset of an existing store must not silently destroy its current Draft.

The system should ask what to preserve.

Example concept:

```text
What should be preserved?

☑ Products and content
☑ Current colors
☑ Header
☑ Footer

○ Fully apply the new preset
```

An equivalent simpler UX is acceptable.

---

## 43. Basic Mode

Basic Mode is for ordinary users.

A Product Rail may expose:

```text
Title
Products
Color
Card Style
Product Count
View All
```

---

## 44. Advanced Mode

Advanced Mode provides deeper design controls without code.

Examples:

```text
Spacing
Exact Height
Background Image
Pattern
Border Radius
Advanced Colors
Layout Details
```

---

## 45. Custom CSS

For the current version:

```text
NOT ALLOWED
```

---

## 46. Custom HTML / JavaScript

For the current version:

```text
NOT ALLOWED
```

The platform should provide design freedom through safe system capabilities, not arbitrary code injection.

---

## 47. Draft and Published States

All Builder changes are made in:

```text
Draft
```

The public storefront renders:

```text
Published
```

The merchant must be able to preview Draft changes without affecting the live storefront.

---

## 48. Publish Flow

Required flow:

```text
Edit Draft
↓
Preview
↓
Publish
↓
Published Version
```

Publish must be atomic.

---

## 49. Version History

The system must retain version history so that:

```text
Rollback
```

can be supported.

Undo/Redo handles editing-session actions.

Version History handles previously published versions.

---

## 50. Conceptual Data Model

Core concepts include at least:

```text
Store
StorefrontLayout
StorefrontLayoutVersion
Page
BlockInstance
BlockDefinition
Palette
Preset
```

A Homepage version contains an ordered list of Block Instances.

---

## 51. BlockDefinition

A BlockDefinition defines a reusable block type.

Examples:

```text
product_rail
hero
category_grid
multi_banner
trust_features
```

It contains:

```text
Schema
Allowed Settings
Default Settings
Validation
Renderer
```

---

## 52. BlockInstance

A BlockInstance is the configured use of a block inside one storefront.

Example:

```text
type:
product_rail

title:
Office Supplies

source:
category:12

background:
red

pattern:
stationery

order:
7
```

---

## 53. Settings Validation

All block configuration must be validated server-side.

Arbitrary user JSON must never be passed directly into rendering logic.

Each block type has a defined schema.

---

## 54. Tenant Safety

All merchant-facing selectors and rendering queries involving:

```text
Products
Categories
Brands
Media
Content
```

must be scoped to the current Store.

No picker or renderer may expose data belonging to another tenant.

---

## 55. Performance

Long homepages such as V5 must remain performant.

The platform should support:

```text
Lazy Loading
Responsive Images
Correct Image Sizing
Efficient Product Queries
Limited Prefetching
Caching
```

---

## 56. Image Handling

Merchants should usually upload a single source image.

The system should automatically manage:

```text
Desktop Sizing
Tablet Sizing
Mobile Sizing
Object Fit
Lazy Loading
```

---

## 57. Accessibility

Interactive components should provide at least:

```text
Keyboard Usability
Proper Button Semantics
ARIA Where Required
Visible Focus States
Readable Contrast
```

---

## 58. iPhone Input Rule

All mobile inputs must avoid unwanted Safari focus zoom.

Input typography must meet appropriate iPhone font-size behavior globally.

This is a storefront-wide frontend acceptance criterion.

---

## 59. Mandatory Components

The system must prevent merchants from accidentally creating a completely unusable storefront.

### Header

Protected minimum:

```text
Logo
Navigation Access
Cart
```

### Footer

Protected minimum:

```text
Store Identity
Contact
Copyright
```

### PDP

Protected minimum:

```text
Title
Gallery
Price / Purchase
```

Critical components receive logical protection.

---

## 60. Design Freedom vs. Safety

Core product rule:

> Merchants should have extensive design freedom, but the platform must prevent accidental creation of a broken or unusable storefront.

Therefore both must coexist:

```text
Design Freedom
+
Safe Constraints
```

---

## 61. Definition of Done for the Universal Engine

The Universal Engine is considered successful when materially different storefronts can be built **without writing a new renderer**.

Example target set:

```text
Store A
Dense V5-style marketplace

Store B
Minimal fashion storefront

Store C
Electronics catalog

Store D
Luxury perfume storefront
```

All must use:

```text
same engine
same block library
different configuration
```

---

## 62. Primary V5 Acceptance Criterion

A critical visual acceptance test is:

```text
Golden V5
        vs
Universal Engine + V5 Preset
```

These should be visually very close.

If reproducing V5 requires logic such as:

```text
if store == X
```

or a dedicated:

```text
beraito_renderer
```

then the architecture has failed.

---

## 63. No Permanent Beraito Dependency

V5 is a **design reference**, not a permanent technical dependency.

Production RastiSi must not depend on:

```text
beraito.com
WordPress
WooCommerce
Elementor
Owl Carousel as an unavoidable dependency
```

unless a general-purpose library is independently selected for the RastiSi architecture.

Reference assets are development/design inputs, not a production runtime dependency.

---

## 64. Recommended Implementation Roadmap

Suggested sequence:

```text
Phase 1
Block / Data Architecture

Phase 2
Universal Renderer

Phase 3
V5 Preset Reproduction

Phase 4
Layout / Grid / Reordering

Phase 5
Palette + Design Controls

Phase 6
Builder UX

Phase 7
Header / Footer Builder

Phase 8
Product Data Sources

Phase 9
Draft / Preview / Publish Hardening

Phase 10
Additional Presets
```

Each phase must produce something visible and testable before the next phase begins.

---

## 65. Development Governance Rule

No implementation agent should make significant architecture or UX decisions by guesswork.

If this Specification defines the behavior:

```text
Specification wins.
```

If a major architecture or UX decision is not defined:

```text
STOP
→ Ask the Owner
→ Record the Decision
→ Continue
```

---

## 66. Locked Product Decisions

The following major decisions are currently approved and locked:

### Visual Reference

```text
V5 — APPROVED
```

### Architecture

```text
Universal Engine — APPROVED
```

### Preset Architecture

```text
Configuration / Data Only — APPROVED
```

### Homepage Builder

```text
APPROVED
```

### Drag & Drop

```text
APPROVED
```

### Palette + Per-Block Overrides

```text
APPROVED
```

### Basic + Advanced Mode

```text
APPROVED
```

### Custom CSS / HTML / JavaScript

```text
NOT ALLOWED
```

### Responsive Strategy

```text
One Unified Design
Automatic Desktop / Tablet / Mobile Adaptation
```

---

# Final Product Definition

RastiSi is **not** a system for choosing between a small number of fixed templates.

The intended product is:

> A single universal storefront engine built from composable blocks, capable of starting from a highly polished preset and allowing a non-technical merchant to extensively rearrange, recolor, configure, hide, duplicate, and customize the storefront without writing code.

`Beraito Exact Frontend V5` is the first approved Golden Visual Reference and the first reference preset for this Universal Engine.

---

**End of Specification — Version 1.0**
