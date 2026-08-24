# Universal Storefront Engine — U3–U11 Execution Ledger

Tracks each phase of the U3–U11 master execution contract: starting/ending
SHA, architectural decisions, migrations, and test results. Kept concise —
this is a ledger, not a code dump.

## Branch / scope note

The contract text names `feature/storefront-builder-v3-redesign` as the
official branch. This session's actual git operating instructions (from the
harness, not the task text) originally designated
`claude/storefront-engine-u3-u11-j5svas` instead. At the time this phase
started, both branches pointed at the same commit
(`5c1a2a55ce13a6ef57e75ed0d9725507d4fff30d`, matching the contract's required
starting HEAD), so there was no real divergence and the U3 checkpoint was
first committed on `claude/storefront-engine-u3-u11-j5svas`.

**Mid-phase event:** `claude/storefront-engine-u3-u11-j5svas` was deleted
from `origin` by something outside this session (confirmed via
`git ls-remote --heads origin` — the ref was simply gone, with no merged or
closed PR against it). Rather than silently force-recreating a deleted
remote branch, this was raised to the user; they chose to retarget all
checkpoints to `feature/storefront-builder-v3-redesign` — the branch the
contract itself names as canonical, still sitting untouched at the required
starting SHA. The two U3 commits were fast-forwarded onto it
(`5c1a2a5..0a1da0a`, verified `origin/feature/storefront-builder-v3-redesign`
== local `HEAD` after push). **All checkpoints from U3 onward go to
`feature/storefront-builder-v3-redesign`.**

Given the realistic scope of a 9-phase production commerce-engine program
(pricing/discount logic, product types affecting cart/order validation, a
template/reset engine, a full accessibility/performance closure), phases are
executed one at a time with a real audit, focused tests, and a regression
run each — not rushed together — so business-critical logic gets the
scrutiny the contract itself requires ("no fabricated commercial content",
"no giant conditional renderer", query-count discipline, etc.).

---

## U3 — Universal Product Card / Badge / Pricing System

- **Starting SHA:** `5c1a2a55ce13a6ef57e75ed0d9725507d4fff30d`
- **Ending SHA:** `0a1da0a9e51f7650fb4eb58350af702a8a3d57f9` (on
  `feature/storefront-builder-v3-redesign`, verified equal to
  `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

- The legacy per-store "family" renderer system (`family_registry.py`, 11
  hand-authored `product_card_variant` templates) is already fully retired
  (confirmed via `apps/storefront_builder/tests/test_phase7_family_retirement.py`
  — `RegistryModulesAreGoneTests`). `catalog/partials/product_card.html` is
  already the single universal card template, with visual differences
  expressed as a closed settings enum (`card_settings.card_style`:
  `standard`/`compact`/`minimal`) — this is already Pattern A of the U1
  `variant_contract` convention ("same renderer, different settings/CSS
  class"), so no second/competing variant registry was introduced for card
  style; that would have duplicated an already-compliant system.
- Business logic (price, discount, sale badge, new/hot/sale tag badge) was
  previously read directly from `Product` fields *inside* the template
  (`product.discount_percent`, `product.final_price`, `product.tag`, ...) —
  duplicated business semantics baked into a specific renderer, exactly the
  anti-pattern U3 exists to remove.
- `card_settings` (toggles: `show_brand`/`show_price`/`show_badge`/
  `show_wishlist`/`show_quick_add`/`show_rating`/`card_border`, plus
  `image_ratio`/`quick_add_reveal`/`card_style` enums) is validated centrally
  by `section_registry.validate_card_settings` and already shared by every
  card-bearing section (`product_section`, `featured_products`,
  `newest_products`, `best_sellers`, `discounted_products`,
  `amazing_offers`, `related_products`, `product_listing`,
  `collection_products` — `CARD_AWARE_SECTION_KEYS`). This visual-toggle
  layer is untouched by U3 (it is presentation, not business data).
- No `is_featured` field exists on `Product` — confirmed existing precedent
  (`render_service._featured_products_context`) already documents this and
  intentionally falls back to "newest" rather than fabricate a featured set.
  U3 preserves this; no featured badge was fabricated.
- No product-level (or store-level) low-stock threshold exists — only
  `ProductVariant.low_stock_threshold`/`WarehouseInventory.low_stock_threshold`
  (Phase 1D) do. Computing an accurate low-stock signal for a product-grid
  card would require either an arbitrary per-variant choice or a per-card
  query (N+1 regression). **Documented capability boundary, not built**:
  `ProductCardData.is_low_stock` always resolves `False` today.
- Listing/section product querysets (`storefront_listing_products(store)
  .select_related("brand").prefetch_related("images", "metafields")`)
  already avoid N+1 for brand/images; no variant prefetch exists anywhere
  in `render_service.py`'s product contexts, so a variant-aware minimum
  price ("from ...") was intentionally **not** wired into the resolver this
  phase — it would need touching every listing call site's queryset to add
  `prefetch_related("variants")` without introducing N+1, which is a larger,
  separate change. `build_product_card_data` reads `product.final_price`
  (existing single-price behavior, unchanged) as a safe default.

### Architecture implemented

- **`apps/catalog/services/product_card_service.py`** (new) — the shared,
  pure, query-free business-data resolver. `build_product_card_data(product)`
  returns a frozen `ProductCardData` (price, `compare_at_price`, `is_on_sale`,
  `discount_percent`, `badges` — real `Product.Tag`-backed only, image URLs
  read from the existing prefetch-cached `cover_image`/`secondary_image`
  properties, `is_out_of_stock` from `product.stock` — no extra query,
  `is_low_stock` — always `False`, documented boundary, `is_quick_add_eligible`
  — `False` for variable products or out-of-stock, `is_wishlist_eligible`,
  `brand_name`, `rating`, `reviews_count`, canonical `url`).
- **`apps/catalog/templatetags/catalog_extras.py`** — added the
  `product_card_data` filter wiring the resolver into templates without
  touching the 6+ existing include call sites.
- **`apps/catalog/templates/catalog/partials/product_card.html`** — now
  reads `card.*` (resolved data) for all business facts instead of
  `product.*` directly; `card_settings.*` (visual toggles) untouched. Added,
  as new capability, an out-of-stock badge (`ناموجود`) and quick-add gating
  (hidden when out of stock or when the product is variable, since a grid
  card cannot let the shopper pick a variant) — CSS class `pill-outofstock`
  added to `product_card.css` so this doesn't ship unstyled. The `sale` tag
  badge deliberately keeps reusing the pre-existing `pill-new` CSS class
  (verified via `product_card.css`/`theme_palette.css` — no `pill-sale`
  class exists) — a preserved quirk, not a new decision.

### Migrations

None. No model fields added — this phase only reorganizes existing,
already-stored field reads into one resolver.

### Focused test results

`apps/catalog/tests/test_product_card_service.py` (new, 16 tests) +
`apps/catalog/tests/test_product_card_cover_image.py` (existing, 9 tests):
**25/25 passed.** Covers: sale/no-sale pricing, tag→badge mapping (including
the preserved `sale`→`pill-new` quirk), out-of-stock flag and quick-add
gating, variable-product quick-add ineligibility even in stock, the
documented always-`False` low-stock boundary, wishlist eligibility, image
resolution (prefetch-cache based, no query), and end-to-end rendering
regression (`catalog:product-list` route) proving price/discount markup is
byte-identical to before and that the new out-of-stock/variable-gating
capabilities render correctly.

### Regression results

- `python manage.py test apps.catalog` — **782/782 passed.**
- `python manage.py test apps.storefront_builder` — **1480 tests, 2 known
  pre-existing failures, 1 skipped, zero new failures.** The 2 failures are
  exactly the two named in the master contract as pre-existing and deferred
  to U11 (`test_container_settings_explains_hidden_is_not_empty`,
  `test_settings_inspector_keeps_content_tabs_but_layout_moves_to_container_inspector`)
  — confirmed by name match, not newly introduced by U3 (U3 touches
  `apps/catalog`, not `apps/storefront_builder`'s container/inspector code).
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **Low-stock badge**: not built — no product-level threshold field exists;
   see audit findings above. Future phase: add a product-level (or
   query-batched) threshold before wiring this up.
2. **Variant/minimum-price ("from ...") display**: resolver falls back to
   `product.final_price` (single price) for variable products in listing
   grids — no listing queryset currently prefetches variants. Wiring this up
   requires an additive `prefetch_related("variants")` across
   `render_service.py`'s product-section context builders, deliberately
   deferred to keep this phase's diff scoped and N+1-safe rather than
   touching every listing call site speculatively.
3. **Installment/tier pricing**: no underlying capability/data exists in the
   repository for this — per the "no fabricated financing" rule, not built.
4. Card *style* variants (`standard`/`compact`/`minimal`) were left on the
   existing, already-compliant `card_settings.card_style` closed-enum
   mechanism rather than migrated into a new `VariantDefinition`-based
   registry — that would have been a second, competing registry for the
   same three keys, which the U1 `variant_contract.py` docstring already
   explicitly warns against for section variants.

---

## U4 — Hero / Category / Content / Promotion Component System

- **Starting SHA:** `51afac91a1259d50cc7073944e86758e8539e58c`
- **Ending SHA:** `3c6cf9ecfa070f450b904a7ee60db83f67dd851d` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read all 34 `SECTION_REGISTRY` entries and every `validate_settings`
function. Of the "hero/category/content/promotion" family:

- `category_grid`, `brand_carousel`, `product_section` **already comply**
  with the U1 variant-contract mechanism (Pattern A, `display_mode` enum) —
  no work needed, confirmed unchanged.
- `image_text` already has a genuine, already-coerced, already-safe closed
  2-value enum (`image_position`: `left`/`right`) that was **never wired**
  into `variants=` — a zero-risk formalization candidate.
- `multi_banner`'s historical `layout_variant` values (`promo-4`,
  `wide-single`, `mini-4`, `strip`) are **deliberately not a closed enum**
  today — an explicit prior R1 finding (`section_registry.py` comment,
  `MULTI_BANNER_KNOWN_LAYOUT_VARIANTS`) states the complete write-path
  cannot be proven closed from source alone (no editor UI control writes
  it), so narrowing it into `variants=` (which enforces write-time
  rejection of unrecognized values via `_with_variant_validation`) would
  violate that explicit "do not narrow without live-data proof" decision
  and the master contract's own "preserve historical multi_banner values"
  rule. **Left completely untouched** — guarded by a new tripwire test
  (`MultiBannerNotNarrowedTests`) so a future phase doesn't "helpfully"
  narrow it by mistake.
- `hero_banner`/`image_slider`, `single_banner`, `promo_cards`,
  `story_rail`, `trust_features`, `testimonials`, `faq`, `newsletter`,
  `quick_links`, `collection_tiles`, `video_section` had **zero** existing
  variant concept — one fixed template/treatment each. Building genuine new
  Pattern-B (different DOM) variants for all of them in one phase would mean
  many new untested templates; scoped this phase to the two highest-value,
  safest additions instead (see below), documenting the rest as an open
  gap rather than rushing shallow variants for all 11.
- Confirmed via `render_service.py`: `hero_banner` and `image_slider` are
  literally the same reusable partial (`hero_slider_body.html`) mounted in
  two places — the new hero variant is deliberately scoped to `hero_banner`
  only, not forced onto `image_slider` too.
- Confirmed the exact write-time enforcement mechanism
  (`section_registry._with_variant_validation`, wraps a definition's own
  `validate_settings` with `variant_contract.validate_variant_selection`
  *after* it runs) — so each new variant-selecting key needed adding to its
  section's own validator, not just the registry tuple, or the key would be
  silently stripped before a merchant's choice could ever persist.

### Architecture implemented

- **`hero_banner`** — new Pattern B variant `split` (alongside untouched,
  still-default `overlay`): a new renderer partial
  (`storefront_builder/sections/hero_banner_split.html`) presenting the
  exact same real Store-scoped `HeroSlide` data (title/subtitle/button/
  image — nothing invented) as a text-beside-image layout instead of
  text-over-image. Renders exactly one real slide (the first, by
  `display_order`) — a deliberate scope choice documented in the template
  and ledger, not a bug: re-implementing the overlay layout's full carousel
  controls for a two-column layout was judged not worth duplicating for
  this phase. `_validate_slider_settings`/`default_slider_settings` (shared
  with `image_slider`) gained `hero_style` (`overlay`/`split`, coerced,
  default `overlay`); `image_slider`'s own `SectionDefinition` was **not**
  given `variants=`, so the key is inert there — confirmed by test.
- **`collection_tiles`** — new Pattern A variant `carousel` (alongside
  untouched, still-default `grid`): same template, `tile_style` (`grid`/
  `carousel`, coerced, default `grid`) added to
  `_validate_collection_tiles_settings`/`default_collection_tiles_settings`;
  template branches container CSS class exactly like `category_grid`
  already does for `display_mode`. Reuses the existing `.tiles-carousel`
  scroll-container convention (`category_grid`/`brand_carousel` already
  established it) with one new scoped CSS rule for `.pcard` sizing (the
  existing rule only sizes `.tile` children).
- **`image_text`** — formalized the existing `image_position` enum into
  `variants=`. Zero template/behavior change — `image_text.html` already
  branched on this exact setting.
- New CSS: `.hero-split*` rules and `.collection-tiles-carousel .pcard`
  sizing in `apps/catalog/static/css/home.css`, following the file's
  existing responsive-breakpoint conventions.

### Migrations

None. No model fields added — new settings keys live in the existing
`StorefrontSection.settings` JSON field, additive and defaulted.

### Focused test results

`apps/storefront_builder/tests/test_u4_component_variants.py` (new, 19
tests): **19/19 passed.** Covers: registered-variant metadata for all three
touched sections, Pattern A/B renderer resolution, invalid/legacy stored
value coercion (never raises), the `multi_banner` non-narrowing tripwire,
`image_slider` non-contamination, and full HTTP end-to-end rendering proof
for both the unchanged default (overlay/grid) and new (split/carousel)
paths — including a no-fabrication check that a second real `HeroSlide`
never appears in the single-slide `split` layout.

### Regression results

- `python manage.py test apps.storefront_builder` — **1499 tests** (1480 +
  19 new), same **2 pre-existing known failures** as U3 (deferred to U11
  per the master contract), **zero new failures**.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.
- `apps.catalog` not re-run this phase — U4 touched no `apps/catalog` Python
  code (only a shared static CSS file and `apps/storefront_builder`
  templates/registry); U3's catalog regression (782/782) already covers the
  catalog surface this phase doesn't touch.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **9 of the 11 "no existing variant concept" section types remain
   single-treatment**: `single_banner`, `promo_cards`, `story_rail`,
   `trust_features`, `testimonials`, `faq`, `newsletter`, `quick_links`,
   `video_section`. Each would need a genuine new Pattern-B template
   designed, styled, and tested — deliberately not rushed in this phase to
   keep every shipped variant real and verified rather than shallow.
2. **`multi_banner` still has no registered variant metadata** — correct
   per the explicit R1 finding, not an oversight (see audit findings
   above). A future phase could close this properly by first auditing live
   `layout_variant` values in production data.
3. **`hero_banner`'s `split` variant shows only the first slide** — a
   documented design constraint of the two-column metaphor, not a data-loss
   bug; additional slides remain fully visible/editable in the Builder.
