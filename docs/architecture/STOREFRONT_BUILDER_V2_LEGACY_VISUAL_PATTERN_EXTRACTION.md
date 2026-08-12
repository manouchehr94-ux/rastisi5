# Storefront Builder V2 — Legacy Family Visual Pattern Extraction

Read before any Family source deletion, per the Phase 7 master instruction. Every distinctive
visual/structural idea found in the 11 legacy families' header/hero/category/footer/product-card/
product-detail-page templates and CSS, classified so nothing genuinely useful is lost once the
source files are removed (Git history remains the full archive of the exact implementation).

Classifications: `ALREADY_AVAILABLE_IN_V2` · `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` ·
`CAN_BE_EXPRESSED_AS_PALETTE` · `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` ·
`REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT` · `NOT_WORTH_PRESERVING`.

**Scope note**: this document only inventories and classifies. Implementing any of these ideas
into V2 (new block variants, new preset options) is explicitly out of scope for Phase 7 — that
is Phase 8 ("Spec & Prototype Fidelity Audit"), per the master instruction. Phase 7 only ensures
none of this is forgotten before the source is deleted.

---

## 1. modern_fashion — "مد امروز"

- Circular "quick category" avatar rail in the header, horizontally scrollable — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (a header variant option).
- 4-up quad-banner grid directly under the hero slider — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Portrait product card with real secondary-image crossfade on hover — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` (see cross-family §A).
- **Fixed 5-tab mobile bottom navigation bar** (home/categories/search/cart/profile), replacing a drawer — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. Not present anywhere in V2 today; a genuinely distinct mobile navigation pattern worth a future dedicated Global Region variant, not a one-off.
- PDP: side thumbnail column (vs. below-image), sticky mobile CTA bar — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (PDP gallery-position variant).

## 2. artisan_editorial — "روایت هنر"

- Symmetric 3-column header with logo dead-center — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (header archetype, see cross-family §D).
- Asymmetric portrait mosaic hero (alternating tile aspect ratios) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Maker/region metadata line on product card, sourced from a real `ProductMetafield` — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` (a data-driven optional line, not a visual-only idea).
- Trust-badge strip placed above the footer columns (unusual ordering) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Story/description excerpt rendered beside title/price on PDP, left-accent-border styling — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`.

## 3. nordic_living — "خانه آرام"

- 3-row stacked header (announcement → utility → main) with a heavily bordered search box — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Circular/pill hero image treatment (forced 1:1 + `border-radius:50%`) — `CAN_BE_EXPRESSED_AS_PALETTE` (a shape/radius token applicable to any hero, not family-specific markup).
- No default homepage category section — category access lives only in the header mega-menu — `ALREADY_AVAILABLE_IN_V2` (a section is simply omittable; V2 already supports a page composition with zero category-grid section).
- **"Action Rail" hover-reveal add-to-cart button, sliding up from below the card** (slow 0.6s), no hover-lift on the card itself, always-visible on touch — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT` (see cross-family §A — one of three distinct hover-reveal implementations worth consolidating into one configurable variant).
- 3-cell "facts strip" built from real `spec_variant_summary` data (not hardcoded) — `ALREADY_AVAILABLE_IN_V2` — V2's `product_description` section already surfaces spec data generically; this is a layout variant of existing data, not new capability.

## 4. heritage_premium — "پرمیوم اصیل"

- Per-root-category individual hover dropdowns (vs. one mega-menu trigger) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- **Hover-triggered floating cart-preview panel in the header** — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. Genuinely useful, not present in V2's header today; worth a future Global Region (Header) capability.
- Arched-top category tiles (`border-radius:120px 120px 12px 12px`) — `CAN_BE_EXPRESSED_AS_PALETTE` (shape token).
- **Dual product-card mode (standard vs. campaign)**, gated on real discount data, via `product_card_campaign_variant` — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`. This is the reference case: V2's product card block should be able to express "campaign/discount overlay mode" as a setting rather than a second family-specific template.
- "Factory identity" footer column (address/hours/phone, not just a generic contact link) — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`.

## 5. vibrant_catalog — "کاتالوگ رنگی"

- 3-layer header separating a dark utility topbar from the announcement bar, with a pinned "⚡ flash sale" label — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- **"Promo Dashboard" hero** — one large deal tile + up to 2 stacked side tiles, built directly from real `hero_slides` data — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (a genuinely reusable multi-tile hero composition, already expressible as data since it's driven by existing `hero_slides`, not a bespoke model).
- Dense 8-column icon category grid — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (density variant).
- Persistent (non-hover-only) "Add" bar overlaying the card image — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` (see cross-family §A).
- **Price shown before variant selectors on PDP** (intentional inversion of the usual info→price order) — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` (an ordering toggle on the existing `product_main` block).

## 6. atlas_catalog — "اطلس"

- 3-row dense header (utility → main → dedicated category nav) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Split hero (3fr main slider / 1fr "flash offer" side panel with a graceful empty-state fallback) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`; the empty-state fallback specifically is a good UX detail worth remembering for any future multi-slot hero.
- Inline qty stepper directly on the product card body (not just an Add button) — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`.
- **3-column PDP split (42% gallery / 30% content / 28% purchase)** with a live-bound SKU line reflecting the selected variant — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` for the column ratio; the live SKU binding itself is `ALREADY_AVAILABLE_IN_V2` (data-only — `product_main`'s existing Alpine `variantSelector` component already tracks the selected variant; only the extra visible SKU line is new markup, trivially portable).
- 4-item trust-badge strip below the purchase panel — `ALREADY_AVAILABLE_IN_V2` (V2 already has a general-purpose `trust_features` section type).

## 7. ava_fashion — "آوا"

- Catnav row merging root categories and generic nav-menu items into one row — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Dense 4×2 category mosaic — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Rounded-pill discount badge with explicit "٪ تخفیف" suffix text — `CAN_BE_EXPRESSED_AS_PALETTE`/small block-setting (badge text/shape variant).
- 3-part PDP split (8% thumbnails / 42% gallery / 50% configurator) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- **Note**: this family's CSS class names (`.av-card`, `.av-header-row`) don't fully match the class names actually used in its templates (`.av-fashion-card`, `.av-main-row-inner`) — flagged as a likely stale/dead CSS fragment within the family's own source, `NOT_WORTH_PRESERVING` (an implementation bug, not a design idea).

## 8. toranj_gifting — "ترنج"

- Warm-brown header with a pill-shaped translucent search box — `CAN_BE_EXPRESSED_AS_PALETTE`.
- **Scroll-snap 3-card carousel below the hero** — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`/future Hero Block variant; a clean, reusable interaction technique (`scroll-snap-type:x mandatory`) not used elsewhere in the codebase.
- Pill-shaped category chips with a circular icon avatar — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- **Wave-shaped footer top edge via CSS `clip-path: ellipse(...)`** — `CAN_BE_EXPRESSED_AS_PALETTE`/shape token; cheap to reproduce, the only non-rectangular footer silhouette found.
- Accordion-collapsible footer columns (always togglable, not just on mobile) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (footer density variant).
- **Gift-wrap addon checkbox with live total update**, server-validated against `ShopSettings`/`gift_wrap_service` — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. This is a real functional commerce capability, not a purely visual pattern — flagged distinctly for whoever scopes future cart/PDP capability work, not just visual design.

## 9. sarv_stock — "سرو"

- Dense grid-based header combining a "store menu" (nav-menu-driven) with a separate CMS-content-page row (home/products/quick-access/customer-service) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` for the header shape; the CMS-page surfacing itself is `ALREADY_AVAILABLE_IN_V2` if `apps/content.Menu`/`MenuItem` already supports a Content Page destination (confirmed in the Phase 5/6 audits — Menu/MenuItem already support Category/Product/Brand/Collection/External destinations; worth Phase 8 confirming Content Page too).
- Photo-first hero with a blurred translucent text panel (`backdrop-filter:blur`) — `CAN_BE_EXPRESSED_AS_PALETTE`/hero treatment variant.
- Circular category tiles with zoom-on-hover — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`.
- Cart button hidden-by-default, fade+translateY reveal on hover — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING` (third of the three hover-reveal variants, cross-family §A).
- **Sticky purchase column on PDP** (`position:sticky` while scrolling through description/specs) — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. A genuinely valuable "sticky buy box" UX pattern not present in V2's `product_main` today.
- CMS-page-driven footer links (quick-access/customer-service) also repeated on PDP — same classification as the header note above.

## 10. sepidar_handmade — "سپیدار"

- **Entire header rendered as a floating rounded capsule** (inset margins, fully pill-shaped, sticky with a top offset) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`. The single most distinctive and cleanly reusable idea in the whole set — trivially expressible as a "header container: inset + fully rounded" preset option, no bespoke markup required.
- Secondary search bar placed below the hero, duplicating the header's search entry point — `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`.
- Muted/quiet discount badge styling (tan, not a loud accent) — `CAN_BE_EXPRESSED_AS_PALETTE` (badge color-intensity token, not structural).
- 4-tile plain icon+text "service guarantee" row under the buy form — `ALREADY_AVAILABLE_IN_V2` (same reasoning as atlas_catalog's trust strip — `trust_features` section already covers this shape).

## 11. zarrin_jewelry — "زرین"

- Minimal single-row header, no inline search input, no utility/announcement rows — `ALREADY_AVAILABLE_IN_V2` (V2's header composer already supports hiding search/announcement via existing toggles — this is a configuration of existing capability, not new capability).
- **Fully centered, single-column footer** (the only family with this — all others use multi-column grids) — `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET` (footer alignment/density variant).
- Understated 1:1 product card, small non-pill discount tag — `CAN_BE_EXPRESSED_AS_PALETTE`.
- **Social-share row (Telegram/WhatsApp/copy-link) on the PDP purchase column** — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. Genuinely useful commerce/marketing capability, not present in V2's `product_main` today.
- **Inline accordion FAQ block specific to the PDP** (authenticity/size-guide/shipping) — `REQUIRES_FUTURE_REUSABLE_BLOCK_OR_VARIANT`. V2 has a general-purpose `faq` section type for page-level FAQ, but not an inline PDP-embedded variant tied to the purchase flow — worth Phase 8 evaluating whether the existing `faq` section can simply be added to the `product_detail` page's allowlist (cheap) rather than needing new code.

---

## Cross-family consolidated findings

### A. Hover-reveal "add to cart" affordance (3 independent implementations)

`nordic_living` (full slide-up rail, 0.6s), `vibrant_catalog` (persistent always-visible bar, not hover-gated), `sarv_stock` (fade+translateY, 0.6s) all separately solve the same problem, and all three already comply with the platform's "no hover-only critical action on mobile" rule (falling back to always-visible on touch). **Classification: `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`** — worth consolidating into one configurable product-card setting (e.g. `add_to_cart_reveal: always | hover-fade | hover-slide`) rather than three bespoke templates, if Phase 8 decides to build it.

### B. Secondary-image crossfade on hover (5 independent implementations)

`modern_fashion`, `nordic_living`, `ava_fashion`, `sarv_stock`, `zarrin_jewelry` — varying only in speed (0.25s-0.6s) and card aspect ratio. **Classification: `CAN_BE_EXPRESSED_AS_BLOCK_SETTING`** — a single configurable product-card capability (toggle + transition speed), not 5 separate ideas.

### C. Shape/radius language (Palette-level, not structural)

Circular/pill hero images (nordic_living), arched category tiles (heritage_premium), wave clip-path footer (toranj_gifting), floating capsule header (sepidar_handmade), varying card aspect ratios across nearly every family. **Classification: `CAN_BE_EXPRESSED_AS_PALETTE`** — nearly all reduce to a small set of shape/radius tokens rather than bespoke markup.

### D. Header structural archetypes (reduces 11 families to ~5 reusable shapes)

1. Single-row logo+search+actions (`modern_fashion`, `ava_fashion`, `zarrin_jewelry` in its minimal form)
2. 3-column centered-logo (`artisan_editorial`, `heritage_premium`)
3. 3-row utility+main+catnav (`vibrant_catalog`, `atlas_catalog`, `sarv_stock`)
4. Floating capsule (`sepidar_handmade`)
5. Ultra-minimal single-row, no search (`zarrin_jewelry`)

**Classification: `CAN_BE_EXPRESSED_AS_LAYOUT_PRESET`** — Phase 8 should consider these 5 archetypes as the candidate Header Layout Preset set, rather than treating each of the 11 families' headers as a separate idea.

### E. Data-driven, not visual (flagged for a different track, not lost)

Live-bound SKU line reflecting the selected variant (`atlas_catalog`, `ava_fashion`) and CMS-content-page-driven footer/PDP links (`sarv_stock`) are functional/data patterns, already substantially supported by existing V2 data plumbing (`variantSelector` Alpine component; `apps.content.Menu`/`MenuItem`). Classified `ALREADY_AVAILABLE_IN_V2` or near-zero-cost additions, not lost knowledge requiring a new block.

### F. Not worth preserving

`ava_fashion.css`'s stale class-name mismatch (`.av-card` vs. the template's actual `.av-fashion-card`) is an implementation bug in the legacy source, not a design idea — `NOT_WORTH_PRESERVING`.

---

## Summary for Phase 8

Strongest candidates for future V2 capability work, ranked by how distinctly they extend beyond
what a Layout Preset/Palette can already express without new block code:

1. Hover-triggered floating cart-preview panel in the header (`heritage_premium`)
2. Sticky "buy box" purchase column on PDP (`sarv_stock`)
3. Fixed mobile bottom tab-bar navigation (`modern_fashion`)
4. Gift-wrap addon with live total update (`toranj_gifting`) — commerce capability, not pure visual
5. Social-share row on PDP (`zarrin_jewelry`)
6. Inline PDP-embedded FAQ accordion (`zarrin_jewelry`) — likely cheap: extend the existing `faq` section's page-type allowlist rather than build new
7. Consolidated hover-reveal add-to-cart Block Setting (§A above)
8. Consolidated secondary-image-crossfade Block Setting (§B above)

Everything else catalogued above is either already achievable with existing V2 primitives
(sections, Palette, Layout Preset composition) or is a shape/color token best captured the next
time the Palette/Layout Preset set is extended — none of it requires keeping any legacy Family
source code alive.
