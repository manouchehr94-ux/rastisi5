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

---

## U5 — Universal Listing / Filter / Search Experience

- **Starting SHA:** `17e3da2abafa2d1f915fdbaac3523f549ba128cd`
- **Ending SHA:** `37f8a1c81a86a0d48f003bc1cd250677f5390ebc` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read `apps/catalog/views.py` (`_filtered_products`, `build_product_listing_context`,
`collection_index`, `collection_detail`), `apps/storefront_builder/services/render_service.py`
(`_product_listing_context`, `_CONTEXT_AWARE_BUILDERS`), and every public
catalog template. A prior (pre-session) "Phase 5" audit doc
(`docs/architecture/STOREFRONT_BUILDER_V2_PHASE_5_AUDIT.md`) had flagged
"`render_items` computed but never rendered on the 5 non-home page types" as
the single biggest gap in this area — checked whether that gap still exists:

- **It's already closed for 4 of 5 page types.** `product_detail.html`,
  `product_list.html`, `collection_detail.html`, and the cart templates all
  already consume `render_rows.html`/`render_items` — confirmed by grep, not
  assumed. `build_product_listing_context` is already the one shared
  listing-context builder used by both the public `product_list` route and
  the composable `product_listing` context-aware section (`_product_listing_context`
  in `render_service.py`) — exactly the "coherent reusable listing shell"
  U5 asks for, already built.
- Already centralized and working: result count (`plp-count`), sorting
  (`LIST_SORT_OPTIONS`), pagination (`Paginator`/`page_obj`), empty state
  (`plp-empty`), category/brand/price/search-query filters, and product-card
  rendering via `product_card.html` (which U3 already rewired onto
  `product_card_service`) — no rework needed for any of these.
- **Only `collection_index`** (list-of-collections, not a specific
  collection's products) stays outside the composable `render_items`
  architecture — a documented, deliberate pre-existing boundary (it has no
  "current collection" to be context-aware about; per the old Phase 5 audit
  §6, "left exactly as found"). Confirmed this is what the master
  contract's "collection_index has some hard-coded behavior" debt item
  refers to: it has **no pagination at all** — a store with many
  collections rendered every one of them on a single unbounded page. That's
  the concrete, real, in-scope gap this phase closes for it (see below);
  the render_items/context-aware-section boundary itself is untouched
  (correctly still out of scope — no "current collection" for it to be
  aware of).
- Real gaps found against the master brief's explicit filter-dimension list
  (price ✓, brand ✓, category ✓ already existed): **availability** (real
  `Product.stock` data) was missing — added. **Product attributes/options**
  faceting was missing — audited and deliberately **not** built this phase
  (see Known limitations): the master contract's own explicit caution ("do
  NOT load every possible attribute blindly") applies directly here — a
  safe, store-scoped, N+1-free attribute-value aggregation across a
  filtered queryset is a real, separate piece of design work, not a
  drop-in addition, and rushing a shallow version risked exactly the kind
  of blind-loading the contract warns against.
- Confirmed via test: no mobile-usable way to collapse the filter panel
  existed — on a phone, the entire filter form (search/category/brand/
  price/discount/sort) always rendered above the product grid with no
  collapse affordance, pushing every visible product below the fold.

### Architecture implemented

- **Availability filter**: `_filtered_products` gained `in_stock=1` (real
  `Product.stock__gt=0`, the same field U3's `ProductCardData.is_out_of_stock`
  already reads — no new data source). Threaded through
  `build_product_listing_context` (`in_stock_only`) and the `product_listing`
  section template (checkbox, reflects selection).
- **Mobile filter affordance**: `.plp-filters` (`product_listing.html`)
  became a native `<details>` disclosure with a `<summary>` toggle,
  reusing the exact idiom `.faq-item summary` already established
  (`::-webkit-details-marker` reset, no JS). Ships `open` by default —
  byte-identical default visibility to before this phase — but a shopper
  can now actually collapse the panel on a phone after using it;
  keyboard-operable natively.
- **`collection_index` pagination**: added `Paginator`/`page_obj` (same
  `PRODUCTS_PER_PAGE` constant every other listing page already uses) around
  the existing, unmodified `collection_service.public_collection_queryset(store)`
  — the query itself (already tenant-scoped, already N+1-free) is untouched;
  only the previously-missing page-boundary was added, plus pagination
  controls in the template reusing the `.pagination` CSS class already
  shared with `product_list_results.html`.

### Migrations

None. `in_stock`/pagination are request-param-driven, not new model fields.

### Focused test results

`apps/catalog/tests/test_u5_listing_filter_search.py` (new, 10 tests):
**10/10 passed.** Covers: in-stock filter correctness and no-regression
default behavior, checkbox state round-trip, zero added queries from the
new facet, store-boundary safety for the new filter (function-level,
proven directly against `_filtered_products` rather than relying on the
pre-existing store-scoping alone), the mobile disclosure's markup and that
it doesn't hide the real filter form, and `collection_index` pagination
(single page has no controls; 13 collections correctly split 12/1 across
two pages).

### Regression results

- `python manage.py test apps.catalog` — **792/792 passed** (789 + the 3 of
  10 new U5 tests that live outside the CI-run count already captured
  above — net new test file is 10 tests total).
- `python manage.py test apps.storefront_builder` — **1499 tests**, same
  **2 pre-existing known failures** as U3/U4 (deferred to U11), **zero new
  failures**.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **Product attribute/option faceting**: not built. Would need a real,
   separate design pass (safe aggregation of distinct attribute values
   across a filtered, store-scoped queryset without loading every
   attribute blindly or introducing N+1) — deferred rather than shipped
   shallow.
2. **Merchant-collection facet** on the product listing page (e.g. "filter
   by collection X"): not built this phase — same reasoning, and lower
   priority than availability given collections already have their own
   dedicated listing page (`collection_detail`).
3. **"Active filters" are shown via the filter controls' own state**
   (selected dropdown values, checked checkboxes, filled price inputs) —
   not a separate removable-chip summary row. Judged adequate for this
   phase; a chip-based summary would be a presentation-only enhancement,
   not a new capability, and was left out to keep this phase's diff scoped
   to real gaps rather than optional polish.
4. `collection_index`'s inline hardcoded styles (bypassing the shared
   appearance/token system every composable page uses) were **not**
   touched — that's a visual/appearance-system concern better scoped to a
   later phase (U9's advanced/appearance work), not a "listing/filter/
   search" gap; only the missing pagination (a genuine listing-experience
   gap) was fixed here.

---

## U6 — Universal PDP + Product Types

- **Starting SHA:** `1057bb5535ed2b218ce0f47970a68c959b44f4d6`
- **Ending SHA:** `fd78651c16b61c60a47eeeca7de8df415be9c727` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read `apps/catalog/views.py` (`build_product_detail_context`),
`apps/storefront_builder/templates/storefront_builder/sections/product_main.html`/
`product_description.html`, `apps/orders/services/shipping_service.py`
(`cart_requires_shipping`/`cart_shippable_weight_grams`),
`apps/orders/services/checkout_service.py` (`build_context`/`submit_order`),
`apps/orders/services/order_service.py` (`create_order_from_cart`), and
`apps/orders/models.py`'s `Order` fields.

- **`build_product_detail_context` was already comprehensive** — product
  identity, media gallery with variant→image switching, video (existing
  provider detection), variant/option selector, price, stock, description/
  specs (synthesized), reviews + rating breakdown, related products, gift
  wrap. No rework needed for any of this — confirmed by reading it, not
  assumed from the phase name.
- **Real bug found**: `product_main.html` (the PDP purchase area)
  unconditionally rendered two physical-shipping claims — "in stock, ready
  to ship" and "fast, insured shipping" — for **every** product, with zero
  connection to the existing, real `Product.requires_shipping` field. For
  any store selling a non-shippable item, this is a literal false shipping
  promise on the product's own purchase button — exactly what the master
  contract's "no fabricated... shipping promises" rule forbids. This is
  the concrete "no physical shipping claim" requirement for both DIGITAL
  and SERVICE product types.
- **No field distinguishes "digital" from "service" today** — `Product`
  only has `requires_shipping` (boolean) and `product_type`
  (`simple`/`variable`, an unrelated axis — variant structure, not
  fulfillment kind). Deliberately did **not** invent a new
  `fulfillment_type`/digital-vs-service split field this phase (see Known
  limitations) — the repository has no real capability or merchant-facing
  choice backing that distinction yet, and inventing one to show different
  cosmetic labels for two states with no real underlying difference would
  itself be a form of fabricated content.
- **Deeper gap found, audited but not fixed**: `shipping_service
  .cart_requires_shipping(items)`/`cart_shippable_weight_grams(items)`
  already exist, are already correct, and already have dedicated passing
  tests (`test_all_digital_cart_does_not_require_shipping`) — but neither
  is actually called from `checkout_service.py`. `submit_order` (`views.py`
  checkout flow) unconditionally raises `CheckoutError("هیچ روش ارسال فعالی
  موجود نیست")` when no shipping method is selected, regardless of whether
  the cart needs one. Tracing further: `Order.shipping_method` is a
  **mandatory** (`null=False`, `on_delete=PROTECT`) ForeignKey — an Order
  literally cannot exist in the database today without a real
  `ShippingMethod` row. Making an all-digital/all-service checkout actually
  completable would require a schema migration (nullable FK) plus auditing
  every `order.shipping_method` consumer (invoices, dashboard order views,
  notifications, `create_order_from_cart` itself, which unconditionally
  reads `shipping_method.store_id`/`.is_active`/`.is_pickup`/... several
  lines deep). This is real, business-critical order-creation logic — not
  safe to touch speculatively in this pass. **Not fixed — documented as a
  concrete, scoped follow-up**, not silently left unmentioned and not
  half-fixed in a way that would look done without actually working.

### Architecture implemented

- **`product_main.html`**: both shipping claims now gated on the existing
  `product.requires_shipping` field (server-side Django conditional — the
  fact is fixed per-product, not variant-dependent, so no Alpine/JS change
  needed). The non-shippable branch shows real, honest alternative copy
  ("available — purchasable" / "no physical shipping needed") rather than
  a blank gap in the trust-badge row, keeping the row's real content intact
  without fabricating a shipping claim.
- Physical products (the default, `requires_shipping=True`) render
  byte-identical copy to before this phase — zero visible change for every
  existing store.

### Migrations

None. No model changes — this phase reuses the existing `requires_shipping`
field.

### Focused test results

`apps/catalog/tests/test_u6_pdp_product_types.py` (new, 4 tests): **4/4
passed.** Covers: physical-product regression (byte-identical claims),
non-shippable product makes no shipping claim, non-shippable product shows
the real honest alternative copy, and the out-of-stock state stays
unaffected by the shipping flag either way.

### Regression results

- `python manage.py test apps.catalog apps.orders` — **1125 tests passed**,
  zero failures.
- `python manage.py test apps.storefront_builder` — **1499 tests**, same
  **2 pre-existing known failures** as U3–U5 (deferred to U11), **zero new
  failures**.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **No `fulfillment_type` (digital/service) split field** — deliberately
   not invented this phase; see audit findings above. A future phase
   wanting genuinely distinct digital vs. service PDP presentation (not
   just "non-shippable" framed identically for both) needs a real,
   merchant-facing field first, not a cosmetic label with no data behind
   it.
2. **All-digital/all-service checkout still requires a real, selected
   `ShippingMethod`** — `cart_requires_shipping` exists and is correct but
   isn't wired into `checkout_service.submit_order`'s validation, and
   `Order.shipping_method` is a mandatory FK. A store that sells only
   digital/service products cannot today complete a checkout unless it
   also configures at least one (possibly nominal/pickup) shipping method.
   Fixing this properly needs: `Order.shipping_method` migrated to
   nullable, `create_order_from_cart` guarded for `shipping_method=None`,
   every downstream consumer of `order.shipping_method` audited
   (invoices/dashboard/notifications), and `checkout_service` wired to
   skip the requirement via the already-correct `cart_requires_shipping`.
   Scoped out of this phase as a real, separate, higher-risk schema change
   — not silently left unmentioned.
3. **PDP capability visibility beyond the shipping-claim fix** (e.g.
   product-type-specific sections/CTAs) was not built, since it would
   depend on the same missing `fulfillment_type` field from limitation #1.

---

## U7 — Ready Template / Version / Baseline / Reset Engine

- **Starting SHA:** `57e03772f2aba46b7016f80cb262f9a73d56eca5`
- **Ending SHA:** `d9978ac818620891fbd4f02273053803b2412198` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read `apps/storefront_builder/layout_preset_registry.py`,
`apps/storefront_builder/services/preset_service.py`,
`apps/storefront_builder/variant_contract.py`'s provenance section
(`build_template_provenance`/`validate_template_provenance`/
`ENGINE_SCHEMA_VERSION` — explicitly commented "for U7... not written by
any Store/Draft in this phase"), `apps/storefront_builder/models.py`
(`StorefrontLayoutVersion`), and `apps/storefront_builder/services
/edit_history_service.py`.

- **The APPLY mechanism already exists and is exactly what U7 needs**:
  `LayoutPresetDefinition` (page composition + appearance overlay +
  header/footer config overlay) is already, structurally, the "versioned
  recipe" the master contract calls a Ready Template.
  `preset_service.apply_preset` already applies it to a Draft only,
  atomically, fully validated-before-write, lock-protected, never touching
  merchant content (media/product selections/announcement text) — the
  exact "Apply operates on Draft, never auto-publishes" contract U7
  requires. **Not rebuilt — reused as-is.**
- **Rollback/version history already exists**: `StorefrontLayoutVersion`
  (Draft/Publish/Restore, `Source.RESTORED`, immutable-after-publish) plus
  `edit_history_service.py`'s separate bounded (30-entry) undo/redo stack
  for the live Draft. **Not rebuilt.**
- **Real gaps found**: `LayoutPresetDefinition` had no `version` field at
  all — a Ready Template's identity was just its Python dict key, with no
  way to distinguish "the exact recipe a store was given" from "whatever
  this key's Python definition currently is" (which could change under a
  store in a future release). The U1A-scaffolded provenance contract
  (`build_template_provenance`) existed but was never actually written by
  any real code path. No reset-to-baseline function existed at all — a
  merchant could re-apply *a* preset, but nothing recorded/restored *the
  specific one they were already on*.
- Of the 5 existing presets, **none** set `header_variant`/`footer_variant`
  (U2A/U2B's global-region variant keys) — every preset used the same
  default global chrome, differing only in section content/appearance,
  not the "combinations of... global variants..." U10 will need for 8
  materially different Ready Templates. `layout_service.validate_header_config`/
  `validate_footer_config` (which `preset_service` already calls) already
  accept these keys — confirmed by the existing generic
  `test_all_built_in_presets_pass_validate_layout_preset` test — this was
  a real, low-risk, high-value gap to close, not a new mechanism to build.

### Architecture implemented

- **`LayoutPresetDefinition.version: str = "1"`** — validated non-empty at
  import time (`_validate_page_composition_shape`), matching
  `build_template_provenance`'s existing `str | None` contract.
- **`StorefrontLayoutVersion.template_provenance`** (new `JSONField`,
  default `{}`) — additive migration
  (`0016_storefrontlayoutversion_template_provenance`). Empty dict means
  "never had a Ready Template applied" — a valid state, not an error
  (legacy stores, hand-built Drafts).
- **`preset_service.apply_preset`** now also writes
  `build_template_provenance(template_key=preset.key, template_version=preset.version)`
  onto the Draft on every successful apply — same transaction, same
  validated-before-write ordering as everything else in that function.
- **`preset_service.reset_storefront_to_baseline(draft)`** (new) — reads
  the Draft's recorded provenance via `validate_template_provenance`
  (safe on legacy/missing data), resolves the *exact recorded* key+version,
  and re-applies it via the existing `apply_preset` — reset **is** apply,
  scoped to the recorded baseline rather than an arbitrary caller-supplied
  preset. Three explicit, distinct failure modes, each with its own
  exception (never a silent wrong-version reset): no provenance recorded
  (`NoTemplateBaselineError`), the recorded key no longer exists in the
  registry (`UnknownPresetError`), the recorded version no longer matches
  the preset's *current* version (`TemplateBaselineVersionChangedError` —
  directly implements the master contract's "Reset must restore the
  selected template VERSION baseline," not whatever the key currently
  means).
- **4 of 5 presets** (`clean_minimal`, `editorial_story`, `dense_catalog`,
  `premium_boutique`) now set real `header_variant`/`footer_variant`
  matched to each preset's identity (e.g. `dense_catalog` →
  `marketplace_search_first`/`marketplace_dense`, `premium_boutique` →
  `premium_three_column`/`premium_columns`). `v5_golden_homepage`
  deliberately left untouched — see Known limitations.

### Migrations

One, additive: `0016_storefrontlayoutversion_template_provenance.py` — adds
`template_provenance` (`JSONField`, `default=dict`, `blank=True`) to
`StorefrontLayoutVersion`. No backfill needed (empty dict is the correct,
valid value for every pre-existing row). Forwards-safe, non-destructive.

### Focused test results

`apps/storefront_builder/tests/test_u7_ready_template_baseline.py` (new, 9
tests): **9/9 passed.** Plus the pre-existing `test_preset_service.py`
(incl. `test_all_built_in_presets_pass_validate_layout_preset`, which
exercises every registered preset including the 4 newly-added
`header_variant`/`footer_variant` keys) and `test_layout_preset_registry.py`
regression: **53/53 passed total, zero failures.** Covers: version field
presence/default, provenance recorded correctly on apply, fresh-draft
provenance is empty (not fabricated), reset with no provenance / unknown
key / stale version each raise their own distinct exception, reset
actually restores deleted home-page sections back to the preset's baseline
composition, and the 4 updated presets' variant keys are real currently-
registered `GLOBAL_HEADER_REGION`/`GLOBAL_FOOTER_REGION` entries (not
typo'd strings that would silently fail-safe to the default at render
time).

### Regression results

- `python manage.py test apps.storefront_builder` — **1510 tests**, same
  **2 pre-existing known failures** as U3–U6 (deferred to U11), **zero new
  failures** — U7's changes touch only preset/provenance/registry code,
  nothing in the container/inspector area those 2 failures come from.
- `python manage.py makemigrations --check --dry-run` — no changes detected
  (the one real migration was generated and applied cleanly).
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **Reset granularity is whole-storefront only.** Field/component/section/
   page/header/footer *individual* reset (the master contract's full list)
   needs a baseline snapshot stored at that same granularity — re-deriving
   a single section's baseline from the preset definition alone isn't
   reliable once a merchant has reordered/duplicated/added sections beyond
   what the preset originally specified. That's real, separate,
   non-trivial design work (what does "reset this one section" mean if the
   merchant duplicated it three times?) — not attempted this phase. The
   whole-storefront case implemented here is the one granularity where
   "re-apply the recorded preset" is unambiguously correct.
2. **No merchant-override-vs-baseline distinction is tracked per field.**
   `apply_preset`/`reset_storefront_to_baseline` both fully replace a
   page's sections — there's no record of "the merchant manually changed
   *this* setting after applying the template," so a future "template
   update without overwriting merchant edits" feature needs that tracking
   built first (a real, separate, larger piece of work).
3. **`v5_golden_homepage` was not given `header_variant`/`footer_variant`**
   — it already has extensive custom header/footer toggle configuration
   (`extra_blocks`, many `show_*` fields) and its own dedicated test file
   (`test_phase3_v5_golden.py`); verifying every one of those toggles
   still behaves identically under a non-`legacy_default` global-region
   renderer partial was judged out of scope for this pass's risk budget —
   left on the implicit default rather than risking an unverified visual
   regression in an already-tested, heavily-configured preset.

---

## U8 — Template-First Merchant Experience

- **Starting SHA:** `e2f82331bcd7667fce355157d4d88c4a79b32f5c`
- **Ending SHA:** `fe2d6cf77c86a942685f9e6fea2be6164ceb97f4` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read `apps/storefront_builder/views.py` in full for every existing preset/
appearance/editor view, `apps/storefront_builder/templates/dashboard
/storefront_builder/editor.html` (1153 lines — the existing Free Layout/V3
advanced builder), `apps/dashboard/templates/dashboard/base_admin.html`'s
sidebar nav, and `apps/storefront_builder/appearance_registry.py`.

- **The apply mechanism already had a working, safe backend endpoint**
  (`storefront_apply_layout_preset` — Draft-only, confirm-before-replace
  when content would be overwritten, never auto-publishes) — confirmed
  reused as-is, no new write path introduced this phase.
- **Zero merchant-facing surface referenced `list_layout_presets()`
  anywhere** — confirmed via grep across every template in the repo. A
  merchant had no way to discover or browse the 5 Ready Templates at all;
  the only way to apply one was already knowing the raw POST endpoint
  existed. This is the exact, concrete form of U8's stated goal ("the
  normal user must encounter a professional Template Gallery before
  needing to understand layout internals") — not a vague aspiration, a
  literal zero.
- **A second, separate, also-unused template-like registry was found**:
  `appearance_registry.TemplateDefinition`/`list_templates()` (9 entries —
  font/radius/density/motion/content_width/grid_density/card_shadow/
  hero_style + a `swatch` field explicitly commented "for gallery
  mini-preview"). It's already passed into
  `partials/appearance_panel.html`'s context (`"templates": ...`) but that
  partial never actually renders it — another dead-capability pattern,
  same shape as U4/U5's findings. This is a pure appearance-token concept
  (no page composition, no header/footer), narrower than
  `LayoutPresetDefinition`. **Deliberately not touched or merged into the
  new gallery this phase** — see Known limitations.
- Everything else U8 asks for (edit content, replace images, reorder
  sections, show/hide, add/delete, change colors/typography, publish)
  already exists in the advanced editor (`editor.html`) — confirmed by
  reading it, not assumed. U8's real, missing piece was specifically the
  *entry point* — a simple browse/preview/apply surface before that
  advanced editor, not a rebuild of editing capabilities that already work.

### Architecture implemented

- **`storefront_template_gallery`** (new view, `GET`, `@staff_required`
  `@permission_required(STOREFRONT_LAYOUT_MANAGE)`) — reads
  `layout_preset_registry.list_layout_presets()` and the Draft's U7
  `template_provenance` to mark the currently-applied template. Purely a
  read/render view — no new write path. Real, non-fabricated visual
  preview per template: actual palette colors (`appearance_registry
  .get_palette(preset.default_palette_slug)`) and actual registered
  header/footer variant labels (`global_region_registry.get_global_variant`)
  — never an invented screenshot or mockup.
- **`_preset_would_replace_content(draft, preset)`** (new, extracted
  helper) — the exact boolean `storefront_apply_layout_preset` already
  computed inline, now shared so the gallery's pre-click warning and the
  endpoint's actual server-side guard can never diverge.
- **`template_gallery.html`** (new template) — a card grid; each card
  shows the template's real palette swatch, label/description, real
  header/footer variant labels when the preset sets them, a "currently in
  use" state (disabled button, no form) or an apply form posting to the
  existing, unmodified `storefront-builder-apply-preset` endpoint — same
  `confirm_preset_apply`/JS `confirm()` safety gate as before, now
  surfaced *before* the click instead of only after.
- **Two navigation links added** (no existing routes/views changed):
  sidebar nav gets "قالب‌های آماده" (Ready Templates) positioned before the
  existing "سازنده بصری صفحه اصلی" (advanced editor) link — first thing a
  merchant sees; the advanced editor's topbar gets a "قالب‌های آماده" link
  back to the gallery. This is the NORMAL↔ADVANCED separation the master
  contract asks for, done via navigation rather than rebuilding either
  surface: the gallery is new-and-simple, the advanced editor is
  untouched-and-still-fully-available.

### Migrations

None. No model changes this phase.

### Focused test results

`apps/storefront_builder/tests/test_u8_template_gallery.py` (new, 11
tests): **11/11 passed.** Covers: every registered template listed, no
false "current" badge before any template is applied, correct "current"
state after applying one, real header/footer variant labels rendered for
an updated U7 preset, the gallery view makes zero writes (draft/provenance
unchanged after a GET), the confirm-before-replace guard renders when
content would be overwritten, anonymous access is rejected, and the two
new navigation links are present and correctly cross-linked in both
directions. Plus 2 tests proving the extracted `_preset_would_replace_content`
helper behaves identically to the endpoint's original inline logic.

### Regression results

- `python manage.py test apps.storefront_builder apps.dashboard` —
  **2961 tests**, same **2 pre-existing known failures** as U3–U7
  (deferred to U11), **zero new failures** across either app.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **The gallery only covers `LayoutPresetDefinition`** (composition +
   appearance overlay + header/footer variants) — the separate,
   also-currently-unused `appearance_registry.TemplateDefinition`
   (font/radius/density/motion/content_width/grid_density/card_shadow/
   hero_style) gallery concept was not merged in or wired up. Reconciling
   two parallel "template" registries into one coherent concept is real,
   separate design work (which one wins when both are applied? does a
   `LayoutPresetDefinition` reference a `TemplateDefinition` slug, or do
   they stay independent axes?) — not attempted this phase.
2. **No true NORMAL/ADVANCED *mode toggle* inside the editor itself** — the
   separation implemented is navigational (two distinct pages, cross-linked)
   rather than a single editor UI that reveals/hides advanced controls via
   a mode switch. The master contract's UI-language requirement ("do not
   expose renderer path/registry/JSON config to ordinary merchants") is
   satisfied by the gallery itself never showing any of that — but the
   advanced editor (`editor.html`) is unchanged and still shows builder
   internals to anyone who navigates into it, same as before this phase.
3. **No live preview thumbnail/screenshot per template** — the swatch +
   labels are real data, but not a rendered visual mockup of the actual
   composed page. Building real screenshot/preview rendering is
   infrastructure this phase didn't attempt (would need either a
   server-side render-to-image pipeline or an iframe-based live preview
   per card, both real, separate undertakings).

---

## U9 — Advanced Storefront Settings

- **Starting SHA:** `c8bf76b9824d2d3e51c249ec5c8c2bc3429143b8`
- **Ending SHA:** `4123b4b5bdefc99b01b836194f6489b9a471e7a7` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Read `apps/core/static/css/base.css` in full, `apps/storefront_builder
/templates/storefront_builder/partials/responsive_section_wrapper.html`,
`apps/storefront_builder/templates/dashboard/storefront_builder/partials
/section_settings_form.html` (680 lines), and `storefront_section_settings`
in `views.py`.

- **The central motion architecture already fully exists** — initial
  grep across `apps/catalog/static/css/*.css` missed it, but
  `apps/core/static/css/base.css` (loaded by every page via `base.html` →
  `storefront_shell.html`) already has a global
  `@media (prefers-reduced-motion: reduce)` override (forcing every
  transition/animation to near-zero duration regardless of the merchant's
  chosen `data-sfb-motion`), plus `html[data-sfb-motion="none"] *` and
  per-section `data-motion="{{ item.context.settings.motion.style }}"`
  already wired through `responsive_section_wrapper.html`. **Nothing built
  here — the phase's most commonly-expected task turned out to already be
  done**, confirmed by reading the actual files rather than trusting the
  absence of a first grep match. A regression tripwire test was added
  instead of new code.
- **Real gap found**: U4 registered two new section component variants
  (`hero_banner`'s `hero_style`: overlay/split; `collection_tiles`'s
  `tile_style`: grid/carousel) but never gave merchants a way to actually
  choose either. Two separate layers were missing: (1) the settings form
  template had no `<select>` for either key, and (2) even with a control
  added, `storefront_section_settings`'s POST handler builds an **explicit
  per-section-type field allowlist** (not a generic passthrough) that
  didn't include either key — a submitted value would have been silently
  dropped before reaching `validate_settings`. This is precisely U9's
  "section component variant swap" requirement, and precisely a
  continuation of U4's own work (a backend capability shipped without its
  UI is not yet a usable merchant capability).
- **"Global component variant swap"** (`header_variant`/`footer_variant`)
  was already fully wired end-to-end (`header_editor.html`/
  `footer_editor.html` — real `<select>` controls, already populated from
  `global_region_registry.list_global_variants`) — confirmed, not rebuilt.
- Column/layout/spacing/width/alignment/responsive-visibility/typography/
  appearance-override controls already exist throughout the advanced
  editor (`section_layout_fields.html`, `section_responsive_fields.html`,
  `section_motion_fields.html`, the appearance editor) — confirmed present
  by reading `section_settings_form.html`'s shared includes, not rebuilt.

### Architecture implemented

- **`section_settings_form.html`**: added a `hero_style` `<select>`
  (`hero_banner`-only — `image_slider` shares the same form block but has
  no registered variants, so the control is scoped out for it, matching
  U4's own deliberate scoping) and a `tile_style` `<select>`
  (`collection_tiles`), both using the exact same idiom already
  established for `display_mode`/`image_position`.
- **`storefront_section_settings`**: added `"hero_style"`/`"tile_style"`
  to the respective type's `raw` dict alongside every other field already
  read from `request.POST`, so the new form controls actually persist
  through `validate_settings` (previously would have been silently
  dropped even with the form control present).

### Migrations

None.

### Focused test results

`apps/storefront_builder/tests/test_u9_advanced_settings.py` (new, 9
tests): **9/9 passed.** Covers: the `hero_style` control appears for
`hero_banner` and is absent for `image_slider`, posting `split`/omitting
the field both persist correctly (split / default overlay), the form
reflects an already-saved selection, the `tile_style` control appears and
round-trips (carousel / default grid), and the `prefers-reduced-motion`
tripwire confirming the already-existing motion architecture stays intact.

### Regression results

- `python manage.py test apps.storefront_builder` — **1530 tests**, same
  **2 pre-existing known failures** as U3–U8 (deferred to U11), **zero
  new failures**.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **Capability-metadata-driven control visibility was audited, not
   extended.** `test_u1b2_capability_metadata_wiring.py` already exists
   and covers the general mechanism; this phase added two new concrete
   controls following the established manual per-type form pattern rather
   than building a new generic "capability → auto-rendered control" system
   — the existing form is already an explicit per-type dispatch (not a
   forbidden giant renderer conditional — it's UI form composition, a
   different concern from render-path dispatch), and extending that
   established pattern was lower-risk than introducing a second,
   competing mechanism.
2. **No new spacing/width/alignment/typography controls were added** —
   confirmed these already exist (`section_layout_fields.html` etc.); this
   phase's real, scoped contribution was specifically closing U4's
   variant-control gap, not re-auditing every existing advanced control
   for completeness (a much larger undertaking than remaining budget
   supports at real depth).

---

## U10 — Build the Real Ready Template Catalog

- **Starting SHA:** `d44a5210380fb641f96ae96ef67af89c84398e56`
- **Ending SHA:** `7535810cee0888388c06ca4cdf7880edb00f319c` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

### Audit findings (before implementing)

Confirmed `LayoutPresetDefinition` (the vehicle U7 added `version`/
provenance to) is exactly the correct, already-proven mechanism to build
these 8 templates on — no new registry, no new renderer, reusing the exact
same `register_layout_preset` pattern the 5 pre-U10 presets already use.
Checked `appearance_registry.py`'s full palette list (21 registered
palettes) and valid appearance enum values
(`FONT_CHOICES`/`DENSITY_CHOICES`/`MOTION_CHOICES`/`TYPE_SCALE_CHOICES`/
`BUTTON_STYLE_CHOICES`/`IMAGE_FIT_CHOICES`/`IMAGE_HOVER_CHOICES`) and
`product_section`'s real `data_source`/`card` schema before assigning any
values, so every template composes real, valid, already-registered engine
capabilities — never an invented enum value.

### Architecture implemented

All 8 required stable keys registered in `layout_preset_registry.py`,
alongside the 5 pre-U10 presets (13 total):
`dense_marketplace`, `premium_leather`, `warm_boutique`,
`fashion_promo_catalog`, `playful_lifestyle`, `utility_catalog`,
`editorial_jewelry`, `dark_digital`.

Each combines, per the master contract's explicit axis list:

- a **unique home-page section composition** (verified pairwise distinct
  by test) drawn from the 34-entry `SECTION_REGISTRY`, including U4's
  newer variant-capable types (`hero_banner` with `hero_style`,
  `collection_tiles`... — several use `hero_style: "split"` explicitly);
- a **real, currently-registered header/footer global variant pair**
  (U2A/U2B) — all 5 header/footer variants are used across the 8 (some
  pairs reused across 2 templates, since only 5 variants exist for 8
  templates — reuse there is expected, not a shortcut: differentiation is
  the *combination*, not every single axis being unique per template);
- a **distinct appearance token set** (font/radius/density/motion/
  type_scale/button_style/image_fit/image_hover/crossfade/zoom) — verified
  no two templates share an identical appearance dict;
- a **distinct, currently-registered palette** — verified pairwise
  distinct from each other and from all 5 pre-U10 presets' palettes;
- **product-card presentation** via a `product_section` entry with a real
  `data_source` (newest/discounted/best_sellers — no store-specific IDs)
  and `card.card_style` (standard/compact/minimal) chosen per template
  identity — verified not all identical across the 8.

`product_detail`/`listing`/`collection`/`search`/`cart` compositions are
shared across all 8 via one extracted helper
(`_u10_standard_non_home_pages`) — the same shape already used by all 5
pre-U10 presets (`product_main`+`product_description`+`related_products`,
`product_listing`, `collection_header`+`collection_products`,
`product_listing`, `cart_items`+`cart_summary`). Real product/cart data
already drives those pages far more than section arrangement does (per the
U6 audit), so bespoke per-template composition there would be difference
for its own sake — reusing one already-tested shape instead, per "reuse
existing capability, don't duplicate."

No fabricated commercial content anywhere: every section reads real store
data at render time exactly as it always has (no invented discount
percentages, no fake trust badges, no placeholder phone numbers) — the 8
templates only choose *which* real sections appear and how they're styled,
never what data they show.

### Migrations

None.

### Test/registry fix

`test_layout_preset_registry.py::test_exactly_five_built_in_presets`
hardcoded the total preset count — legitimately updated to
`test_exactly_thirteen_built_in_presets` (asserting 13, matching the
approved new architecture), not skipped or deleted.

### Focused test results

`apps/storefront_builder/tests/test_u10_ready_template_catalog.py` (new,
17 tests): **17/17 passed.** Covers: all 8 required keys registered and
key-name hygiene (no reference-store/brand-shaped names), full
`validate_layout_preset` passes for all 13 presets, palettes pairwise
distinct (and distinct from pre-U10 presets), density/motion not all
identical, home compositions pairwise distinct, header/footer variants are
real registered keys, card styles vary, no two appearance dicts identical,
every template covers all 6 page types, provenance recorded correctly on
apply, `reset_storefront_to_baseline` (U7) works for a U10 template, and 5
real end-to-end HTTP render smoke tests (one per header-variant family,
covering all 5 header/footer variants across the 13 presets) proving the
composed pages actually render without error, not just validate at import
time.

### Regression results

- `python manage.py test apps.storefront_builder` — **1547 tests**, same
  **2 pre-existing known failures** as U3–U9 (deferred to U11), **zero
  new failures**.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **Only 1 of 8 templates got a real Pattern-B rendering novelty this
   phase beyond composition/appearance/variant selection** — most
   differentiation is compositional/tokenal/variant-selection (real and
   substantial per the master contract's own explicit axis list), not new
   visual DOM per template; that's intentional (U4 already delivered the
   one real new structural variant this program built, `hero_split`), used
   across several of the 8 where it fits the template's identity.
2. **No live screenshot/preview thumbnail exists per template in the U8
   gallery** — still real palette swatches + header/footer variant labels
   (same honest-data approach as U8), not a rendered mockup of the actual
   composed page. Same limitation carried forward from U8, not
   re-attempted here.
3. **Product-card differentiation is via `product_section`'s `card_style`
   on one representative home-page entry per template**, not exhaustively
   set on every product-card-bearing section in every template (e.g.
   `best_sellers`/`discounted_products` on `dense_marketplace` use the
   default card style) — a deliberate scope choice to keep the diff
   real and reviewable rather than mechanically repetitive.

---

## U11 — Performance / Accessibility / Regression Closure

- **Starting SHA:** `b939b9ba741557bfb03119d5666c310a9305a37c`
- **Ending SHA:** `ea501e4f554e8b728a7b738aa8e1045aabf27f83` (verified equal
  to `origin/feature/storefront-builder-v3-redesign` after push)

This is the closure phase — hardening, not new features.

### 1. Closing the two named pre-existing test failures

Both were investigated to their actual root cause (not skipped, not
weakened blindly) — per-test findings:

- **`test_container_settings_explains_hidden_is_not_empty`** — the test
  reflects a genuine, still-valid product contract that was simply never
  finished: the container settings panel already distinguished a hidden
  section ("— مخفی") from a truly empty cell ("خالی") visually, but never
  explained *why* hiding a section doesn't remove it from its cell — a
  real, plausible source of merchant confusion ("did hiding this delete
  my layout?"). **Fixed the implementation**: added one explanatory note
  to `container_settings_form.html` — "«مخفی کردن» یک بخش یعنی در
  فروشگاه نمایش داده نمی‌شود؛ این کار آن خانه را خالی نمی‌کند...".
- **`test_settings_inspector_keeps_content_tabs_but_layout_moves_to_container_inspector`**
  — root-caused by reading the actual current HTMX partial response
  in full: the Content/Advanced tab *switcher* nav
  (`sfb-v3-inspector-tabs`) was centralized into the editor shell
  (`editor.html`) during the V3 sidebar rework instead of being
  duplicated into every per-section partial — the test's assumption
  (a nav element inside the isolated partial) was superseded by that
  architecture, confirmed genuinely superseded rather than broken. The
  partial still correctly participates in the shared tab state (its root
  carries `:class="{ 'is-advanced-tab': inspectorTab === 'advanced' }"`,
  driven by the shell's single `inspectorTab` Alpine variable) — that
  binding is the real, current signal. **Updated the test** to assert on
  `is-advanced-tab` instead of the no-longer-present duplicated nav, with
  the reasoning recorded inline as a code comment, not just in this
  ledger.

Both fixes verified: `python manage.py test apps.storefront_builder` now
reports **zero failures** (previously: failures=2 on every phase's
regression run from U3 through U10).

### 2. The named N+1: `container_service.get_cell_blocks`

Root-caused precisely: `get_cell_blocks` is *deliberately* always a live
query — its own docstring documents a real write-path correctness
guarantee (a caller can hold a stale `StorefrontCell` right after another
code path mutated the same Cell's placement elsewhere, e.g.
`place_section`) — `.order_by()` on a Django related manager never honors
a prefetch cache, only a bare `.all()` does, so this function can never be
prefetch-safe by construction. That guarantee is correct and was **left
untouched** for every write-adjacent call site.

But three read-only call sites were calling it in a per-Cell loop
*immediately after* prefetching `cells__blocks`/`cells__section` on the
very same queryset — discarding that prefetch and firing one extra live
query per Cell, on **every public page render**
(`render_service.build_page_render_items`) and **every builder panel
refresh** (`storefront_container_state_partial`,
`storefront_container_settings`). Added
`container_service.blocks_from_prefetched_cell(cell)` — the identical
precedence rule (`cell.blocks` wins when non-empty, else legacy
`cell.section`), but reading from the caller's already-loaded relations
instead of re-querying — and wired it into exactly those three confirmed
hot loops. Every other `get_cell_blocks` call site (write-path adjacent:
`place_section`, cell-merge-on-shrink, block move/reorder) is unchanged.

Verified query-count flatness directly: `apps/storefront_builder/tests
/test_u11_query_efficiency.py` (new, 4 tests) proves `build_page_render_items`
issues the same query count for 2 containers as for 8, and a real
end-to-end HTTP homepage render issues the same query count for 2
containers as for 10 (both previously scaled 1:1 with container count).

### 3. Full-suite run

- `python manage.py test apps.storefront_builder` — **1551 tests, 0
  failures.**
- `python manage.py test` (complete project suite, every app) —
  **6276 tests, 3 errors, 4 skipped.** The 3 errors are all in
  `apps/customers/tests/test_auth_views.py`
  (`test_signup_merges_guest_cart`, `test_login_merges_guest_cart`,
  `test_otp_login_merges_guest_cart`) — **confirmed pre-existing and
  unrelated to U1-U11**:
  - `git diff <U2B-start-SHA>..HEAD --stat -- apps/cart/ apps/customers/ apps/orders/`
    is **empty** — zero files in any of those three apps were touched
    anywhere across U3-U11.
  - The failures reproduce identically running just that one test file in
    isolation (22 tests, same 3 errors) — not a full-suite test-order
    artifact.
  - Root cause: each test creates a `Product` without setting `stock=`
    (defaults to `0`), then posts to `cart:add` expecting it to succeed.
    `cart_add`'s call to `add_item_to_cart` correctly raises
    `UnavailableStockError` for an out-of-stock product (per an existing,
    documented ADR-referenced rule in `apps/cart/views.py`, predating this
    entire program) and the view returns an error response without adding
    anything — so `cart.items.first()` is `None`. This is a stale test
    (written before or without accounting for that stock-validation rule)
    in a completely different subsystem (customer signup/auth cart-merge),
    not a Storefront Engine regression.

  Per the master contract's own scope boundary ("Only modify completed
  architecture where U3-U11 genuinely requires... Do not reopen completed
  architecture without cause"), this was **not fixed** — it is outside
  the Universal Storefront Engine's scope, in unrelated code this program
  never touches, and touching customer-auth/cart-merge logic without a
  mandate carries its own risk. Flagged here transparently rather than
  either hidden or silently "fixed" outside scope; the platform team
  should track it as a separate, pre-existing issue.
- The 4 skips in the full run are consistent with the same
  environment/condition-gated skip pattern already observed in every
  storefront_builder-only run throughout U3-U10 (1 skip there,
  consistently, unrelated to any change) — not investigated further as a
  new U11 finding.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `git diff --check` — clean.

### 4. Other U11 checklist items — audited, findings recorded

- **Semantic landmarks**: spot-checked all 8 global header/footer variant
  partials (U2A/U2B). All 4 footer variants correctly use `<footer>` (an
  implicit `contentinfo` landmark) — an initial grep for explicit
  `role=`/`aria-label` attributes suggested a gap, but reading the actual
  root elements showed this was a false alarm: semantic HTML5 elements
  are the more correct choice over redundant explicit ARIA roles. No
  change needed — verified, not assumed.
- **`family_registry.py`/family renderer system**: confirmed already
  fully retired (Phase 7, pre-session) — no dead family code remains to
  remove.
- **`preset_registry.py`** (the older, frozen, single-Family-scoped
  preset system predating `layout_preset_registry.py`): confirmed it is
  not imported by any live code path this session touched, but per "do
  not delete compatibility code without proving it is obsolete," no
  investigation was done into whether any legacy store's data still
  depends on it — **not removed, left exactly as found**.
- **Dark-mode contrast nuance found in U10's `dark_digital` template**:
  the `appearance_registry` palette system has no dark-mode axis — every
  registered palette (including `ocean`, chosen for `dark_digital`) has a
  light `background`/`text` token pair. `dark_digital`'s "darkness" is
  therefore real but scoped to the header/footer chrome (`dark_tech`
  variant, which has its own dark CSS) — the rest of the page (sections,
  product cards) renders on the same light background every other
  template uses. This is an honest, definable design (many real sites
  have a dark header/footer over a light body) but is worth naming
  explicitly rather than leaving the "dark_digital" label to imply a full
  dark theme it doesn't fully deliver — a genuine structural gap (a
  page-wide dark-mode token axis) for a future phase, not something safe
  to add speculatively in a closure pass.

### Migrations

None this phase.

### Known limitations (explicit capability boundaries, not gaps to hide)

1. **No page-wide dark-mode appearance token axis** — see the
   `dark_digital` finding above; would need a real new capability in
   `appearance_registry.py`, not a closure-phase fix.
2. **Accessibility audit was targeted, not exhaustive** — keyboard
   operability, contrast ratios per component state, and responsive/
   horizontal-overflow regressions across all 13 presets × 3 breakpoints
   were not mechanically re-verified pixel-by-pixel; the master contract
   itself defers full visual/browser QA to after U11. This phase closed
   the specific, concrete gaps it found evidence for (the two named
   tests, the named N+1, the landmark spot-check) rather than performing
   a full manual accessibility audit without browser tooling.
3. **`preset_registry.py`** left untouched — see above; removal would
   need a live-data audit this phase didn't have scope for.

## Post-U11 Acceptance Fix Batch 1 — Ready Template Integrity + Public Presentation

- **Starting SHA:** `a6c4f2d071c35d9d104e467e50e7c0b796a8c48d` (the U11
  checkpoint above)
- One coherent commit on top of that SHA, per the batch's own explicit
  instruction (not the usual work-commit + ledger-SHA-commit pair used
  for U3-U11) — see the session's final response for this commit's hash.

Real Windows/browser QA against the completed U3-U11 engine surfaced four
small, explicitly-scoped acceptance gaps — not a new phase, not a
redesign of U1-U11.

### Issue 1 — stale palette after applying a Ready Template

**QA evidence:** applying `dense_marketplace`/`dark_digital` (whose
`default_palette_slug` is `digired`/`ocean`) left the Draft showing
whatever palette the store had before (e.g. `theme-forest-cream`),
despite `template_provenance` correctly recording the new Template.

**Root cause:** `preset_service.apply_preset()` only ever applied a
preset's `default_palette_slug` when the Draft had *no* palette yet
(`current_appearance.get("palette_slug") is None`). That rule was correct
for the original Phase 6 concept — applying a legacy, composition-only
Preset as a one-time content suggestion — but a U7/U10 Ready Template is
a full baseline (composition + appearance + default palette + header/
footer variants + provenance); explicitly switching one is a deliberate
merchant action that must replace the *entire* previous baseline, exactly
like it already replaces section composition.

**Fix:** `apply_preset()` now applies `preset.default_palette_slug`
unconditionally whenever the preset defines one — never conditioned on
whether the Draft already has a palette. Because `reset_storefront_to_baseline()`
is implemented as a re-`apply_preset()` call against the recorded
provenance preset, this single change also fixes reset-to-baseline for
free. The palette remains a fully free merchant override *after* this
point — the fix only fires at the moment of an explicit apply/reset.

**Tests:** `test_preset_service.py::PaletteSeparationTests` —
`test_applying_a_template_replaces_the_previous_palette_baseline` (was
`test_preset_never_overrides_merchants_existing_palette`, rewritten to
assert the corrected contract; `color_overrides` — a separate
customization layer — is confirmed untouched by the apply) and the new
`test_merchant_can_still_freely_change_palette_after_applying_template`.
`test_u10_ready_template_catalog.py` already exercises `dense_marketplace`/
`dark_digital`/others end-to-end and continues to pass unchanged.

### Issue 2 — header/nav contrast after the Issue 1 fix

**Audit:** with Issue 1 fixed, a Ready Template's *actual* default
palette is now always the one in effect — so the QA-reported "nearly
invisible" marketplace nav text was re-audited against real palettes,
including the five required header variants
(`marketplace_search_first`/`premium_three_column`/`boutique_centered`/
`dark_tech`/`legacy_default`) and their intended U10 Ready Template
palettes.

**Root cause found — a real, general CSS specificity bug**, not a
palette-specific issue: `apps/storefront_builder/static/css/storefront_builder.css`
had `.gh a,.gh button{color:inherit}` (specificity `0,1,1` — a class +
element-type selector) written *before* the single-class semantic color
tokens `.gh-nl`/`.gh-btn`/`.gh-account-link` (each `0,1,0`). Because
`0,1,1 > 0,1,0`, the generic fallback always won, so real nav/header
links inherited the ancestor `<header>`'s `--theme-header-text` role
(paired with `header_bg`) while actually sitting on `--gh-surface`
(paired with `--gh-ink`/`colors.text`) — two different semantic pairings
that only coincide for a palette with no independently-defined header/nav
roles. Traced to the exact CSS custom-property chain: `--brand-*`
(`templates/base.html`, from `SHOP_*` context variables) → `--theme-*`
(`apps/core/static/css/theme_palette.css`, `!important` on `.header`/
`.nav`) → `--gh-*` (`.gh-shell` in `storefront_builder.css`). Confirmed
against `theme-forest-cream` (the palette named in the QA report) — a
"تم کامل"/full-site-theme with independent `roles.header_text` (`#FFF8E7`,
cream) meant to pair with the *dark* `roles.header_bg`, not the *light*
`--gh-surface` a nav link actually renders on — cream-on-near-white,
exactly matching the reported symptom.

**Scope check:** none of the 8 official U10 Ready Template palettes
(`digired`/`amber`/`rose`/`sunset`/`mint`/`navy`/`plum`/`ocean`) define
independent `theme_roles` — they're all plain palettes where
`header_text == colors.text`, i.e. exactly what `--gh-ink` already
resolves to. So this specific bug never manifested for any of the 8
official templates even before this fix (verified by
`HeaderNavContrastSpecificityTests.test_no_official_ready_template_relies_on_independent_theme_roles`).
It was, however, a live, general defect for any merchant manually
selecting a full-site-theme through the (unrelated, pre-existing)
appearance editor with the newer U2A header — a latent trap, not
hypothetical.

**Fix — the smallest central correction, not a redesign:** the fallback
rule was changed to `.gh :where(a,button){color:inherit}` — `:where()`
gives it zero specificity, so it can never again out-rank any component's
own semantic color token, for any palette, without touching the token
rules themselves. No store/Template-specific CSS was added; no magic
per-palette values; a full sweep of the `.gh` namespace confirmed this
was the only instance of this defect shape.

**Tests:** `HeaderNavContrastSpecificityTests` in the new
`test_acceptance_batch1.py` — asserts the broken selector is gone (as an
actual rule, comment-stripped so the fix's own explanatory comment
doesn't false-positive), the `:where()` fallback is present, the three
component color rules are byte-unchanged, and the official-Ready-Template
scope-check above.

### Issue 3 — Ready Template Gallery must show only the 8 official recipes

**Problem:** the merchant-facing "قالب‌های آماده" Gallery
(`storefront_template_gallery`) listed all 13 registered
`LayoutPresetDefinition`s — the 8 official U10 recipes mixed with 5
historical/internal ones (`clean_minimal`/`editorial_story`/
`dense_catalog`/`premium_boutique`/`v5_golden_homepage`) kept for
Advanced-mode/direct-apply use.

**Fix — a registry-level distinction, not a hardcoded filter:** added
`is_ready_template: bool = False` to `LayoutPresetDefinition`
(`layout_preset_registry.py`), set `True` on exactly the 8 official keys,
and added `list_ready_templates()` (filters `list_layout_presets()` by
that flag). `storefront_template_gallery()` in `views.py` now calls
`list_ready_templates()` instead of `list_layout_presets()` — a one-line
call-site change. The 5 historical presets remain fully registered,
validated, and directly applicable via the existing apply-preset endpoint
and Advanced mode; nothing about them was removed or hidden anywhere
except this one Gallery view. A future Ready Template only ever needs
this one flag, never a parallel registry to keep in sync.

**Current-template clarity:** the Gallery template
(`template_gallery.html`, built in U8) already marked the currently-applied
card with a `قالبِ فعلی` badge and rendered a disabled `در حال استفاده`
button instead of the apply form for that card — confirmed this already
satisfies the batch's requirement and needed no change.

**Tests A-F** — `ReadyTemplateGallerySeparationTests` in
`test_acceptance_batch1.py`: (A) the Gallery returns exactly the 8
official keys (checked via `response.context["template_cards"]`, not by
scanning rendered text — `editorial_jewelry`'s own description happens to
share a word with `editorial_story`'s historical label, which would
false-fail a naive text-absence check); (B) all 5 historical presets
remain registered (`is_ready_template=False`) and directly applicable
(`apply_preset` + provenance check); (C) the selected Ready Template is
marked current and never carries the apply-form action for its own
preset; (D) a different Ready Template remains applicable from the same
Gallery response; (E) a second store's currently-applied Template never
leaks into another store's Gallery view; (F) all 8 keys are lowercase,
space-free, non-reference-store strings (the same tripwire U10 already
enforces).

### Issue 4 — empty data-driven sections must not render on the public storefront

**QA evidence:** "پرفروش‌ترین‌ها" (a `product_section` sourced from
`best_sellers`) rendered publicly with its heading and the merchant-facing
"فعلاً کالایی برای نمایش وجود ندارد." empty-state message when the store
had zero qualifying products — correct/useful behavior in the Builder
(so a merchant understands *why* a section looks empty while composing a
page), but not something a real shopper should ever see on the live site.

**Fix — a registry-level distinction plus one call in the single public
context builder, not a template-level special case for one Persian
title:** added `render_service.OPTIONAL_PRODUCT_DATA_SECTION_KEYS` (a
mapping of section key → the context key each one's own context builder
already exposes its resolved product list under) covering
`product_section`, `featured_products`, `newest_products`,
`best_sellers`, `discounted_products`, `amazing_offers`, and
`related_products`. `render_service.hide_empty_public_sections(items)`
drops any render item in that set whose resolved data is empty. It is
called exactly twice, both inside
`storefront_context_service.build_universal_storefront_context()` —
the module's own documented single central entry point for **all**
public-page rendering (`apps.catalog.views`, `apps.cart.views`, and the
staff-only-but-shell-identical `product_preview` in `apps.dashboard.views`)
— once for the "store never published" branch and once for the normal
published-page branch, immediately after building `items` and before
`group_items_into_rows`/`build_container_render_items`, so a dropped item
never produces a wrapper `<div class="rsec">`, a heading, a Cell, or a
Container anywhere downstream. The Builder/editor preview
(`storefront_preview` in `storefront_builder/views.py`) calls
`build_page_render_items` directly and never passes through
`build_universal_storefront_context`, so it is architecturally untouched
— the Builder keeps showing every section, including its own explanatory
empty-state, without depending on a runtime flag any call site could
forget to pass.

`product_listing`/`collection_products` (the listing/collection/search
pages' own body) were deliberately **excluded** from this set — an empty
result there is itself meaningful shopper feedback ("no results for this
filter"), not an optional promotional row that should just vanish;
hiding it would leave the whole page blank instead. Static/editorial
sections (rich_text, testimonials, trust_features, banners, etc.) were
never in scope — they were never touched.

**Tests A-E** — `EmptyDataDrivenSectionsHiddenOnPublicTests` in
`test_acceptance_batch1.py`, built around `dense_marketplace` applied to
a fresh store (its home page includes a `best_sellers`-sourced
`product_section`, `discounted_products`, and `amazing_offers`, all
genuinely empty with no products yet): (A) all three are absent from the
published public home page — no heading, no empty-state text; (B) the
same Draft, viewed through the Builder preview endpoint, still shows the
heading and the empty-state text; (C) adding one real discounted product
and republishing makes `discounted_products` render normally, with no
empty-state text; (D) no `data-section-key` wrapper attribute for the
hidden section survives in the public HTML at all (Builder-only attribute
regardless, but confirms no dangling wrapper); (E) a second store's own
product never leaks into the first store's public page, and the first
store's hidden section stays correctly hidden regardless of the other
store's data.

**Regression fallout from this fix (expected, fixed in this batch):**
five pre-existing tests encoded the old "every section always renders
regardless of emptiness" assumption on a fresh/product-less test store
and needed updating to the corrected contract — not weakened, each
re-verified against the fix's actual intent:
- `test_preset_service.py::test_publish_activates_preset_publicly` —
  `dense_catalog`'s home has 7 sections, 4 of them empty data-driven ones
  for a fresh store; updated the expected public `.rsec` count from 7 to
  3 (documented why).
- `test_phase3_v5_golden.py::test_publishing_v5_preset_makes_it_appear_publicly`
  and `::test_repeated_product_rails_show_distinct_titles` — both asserted
  V5 preset product-rail titles appear publicly with zero products in the
  store; added a real discounted product to each test's setup (satisfies
  the `discounted`/`newest`/`most_viewed` data sources these titles use)
  so the assertion tests real rendering, not the bug being fixed.
- `test_public_homepage_integration.py::test_published_product_section_with_deleted_collection_does_not_crash` —
  its own point (no crash on a deleted collection reference) is preserved
  and still asserted (`status_code == 200`); the title-presence assertion
  was inverted to `assertNotContains`, matching the corrected contract.
- `test_responsive_rendering.py::test_multi_banner_gets_grid_rsec_cols_class` —
  investigation showed this test's literal string match
  (`class="grid rsec-cols"`, no extra classes) was never actually matching
  `multi_banner`'s own div (which always renders extra `promo-grid`
  classes) — it was coincidentally matching the *default bootstrap*
  `best_sellers`/`newest_products` sections' own empty grid, which this
  fix now correctly hides. Fixed to assert against `multi_banner`'s own
  actual rendered class attribute, which is what the test always meant to
  verify.

### Files changed

- `apps/storefront_builder/services/preset_service.py` — Issue 1 fix.
- `apps/storefront_builder/layout_preset_registry.py` — Issue 3
  (`is_ready_template` field, `list_ready_templates()`), plus an updated
  `default_palette_slug` docstring reflecting the Issue 1 fix.
- `apps/storefront_builder/views.py` — Issue 3 (`storefront_template_gallery`
  now calls `list_ready_templates()`).
- `apps/storefront_builder/static/css/storefront_builder.css` — Issue 2
  fix.
- `apps/storefront_builder/services/render_service.py` — Issue 4
  (`OPTIONAL_PRODUCT_DATA_SECTION_KEYS`, `hide_empty_public_sections`).
- `apps/storefront_builder/services/storefront_context_service.py` —
  Issue 4 (two call sites).
- `apps/storefront_builder/tests/test_acceptance_batch1.py` — new; Issues
  2, 3, 4.
- `apps/storefront_builder/tests/test_preset_service.py` — Issue 1 tests
  updated/added; one Issue 4 regression fallout fix.
- `apps/storefront_builder/tests/test_u8_template_gallery.py` — two tests
  updated for the Issue 3 Gallery-scope change (one previously asserted
  against all 13 presets; one applied a historical preset that's no
  longer shown in the Gallery it was testing).
- `apps/storefront_builder/tests/test_phase3_v5_golden.py`,
  `test_public_homepage_integration.py`, `test_responsive_rendering.py` —
  Issue 4 regression fallout fixes (see above).

### Testing

Ran, all green: the new `test_acceptance_batch1.py` (15 tests); the full
`test_preset_service.py`/`test_u7_ready_template_baseline.py`/
`test_u8_template_gallery.py`/`test_u10_ready_template_catalog.py`/
`test_u2a_global_header_system.py`/`test_u2b_global_footer_system.py`/
`test_render_service.py`/`test_layout_preset_registry.py` combined (287
tests); the entire `apps.storefront_builder` suite (1567 tests, 1
pre-existing skip, unrelated); the entire `apps.catalog` suite (796
tests). `python manage.py makemigrations --check --dry-run` → "No changes
detected" (expected — `is_ready_template` is a plain dataclass field on a
Python registry object, not a Django model field; no new model/field was
introduced). `git diff --check` → clean.

### Known limitations (explicit, unchanged from the batch's own scope)

1. Broken category/product/trust/payment images in the original QA
   screenshots are a QA-environment artifact (media directory not copied
   with the SQLite DB) — not touched, not a real production defect.
2. Builder-only outlines/"افزودنِ کامپوننت" controls were re-confirmed to
   never leak into public rendering — no change made.
3. True digital/service product semantics, granular field/component/
   section reset, non-home Ready Template differentiation, and real
   Template Gallery thumbnails remain out of scope for this batch, per
   its own explicit exclusions — deferred to a future acceptance batch,
   not started here.

## Post-U11 Acceptance Fix Batch 2 — Ready Template Lifecycle / History / Baseline / Granular Reset

- **Starting SHA:** `5dddc3fa0bff3fd3130f83c78e7f4b3e5f40516b` (the Batch 1
  commit above)
- One coherent commit on top of that SHA, per the batch's own explicit
  instruction — see the session's final response for this commit's hash.

Real QA against a live database found: before applying another Ready
Template, `DRAFT=42 PUBLISHED=41 VERSION_COUNT=10`; after explicitly
applying another Ready Template, `DRAFT=42 PUBLISHED=41 VERSION_COUNT=10` —
unchanged. `preset_service.apply_preset` mutates the current Draft row
in-place with no recoverable pre-switch checkpoint. Three problems this
batch fixes, all built on the **existing** `StorefrontLayoutVersion`
version/history/`restore_version` lifecycle — no parallel history system,
no new top-level model.

### Issue 1 — safe pre-apply/pre-reset recovery checkpoint

**Root cause:** `apply_preset(draft, preset)` always writes onto the exact
`StorefrontLayoutVersion` row it's given. The merchant-facing entry point
(`storefront_apply_layout_preset`) always passes the *current* Draft, so an
explicit Template switch silently destroyed the previous baseline with
nothing recorded in version history.

**Fix — `layout_service.checkpoint_draft_before_replacement(store, *,
reason_label, user=None)`:** reuses the exact `restore_version` idiom
(clone full content into a **new** `StorefrontLayoutVersion` row, make it
`layout.draft_version`) with one deliberate difference — instead of
deleting the old Draft, it **archives** it (`status=ARCHIVED`, labeled with
`reason_label`), so it stays a normal entry in `layout.versions`, restorable
through the unmodified `restore_version`. If the current Draft has no
`StorefrontSection` at all (`_draft_has_any_content`), nothing is
checkpointed and the *same* Draft row is reused — "no meaningful change, no
checkpoint" (no version-history spam for a fresh/empty store's first
apply). `_clone_version_content` (already used by `get_or_create_draft`/
`restore_version`) was extended to also copy `template_provenance`/
`template_baseline_snapshot` — a real, previously-latent gap: without it, a
checkpoint's resulting new Draft would have silently lost "which Template
it's built from," breaking Issue 2/3's reset entirely for any Draft that
had ever gone through a clone.

**Entry points:** `preset_service.apply_preset_with_checkpoint(store,
preset, *, user=None)` (wired into `storefront_apply_layout_preset` —
Issue 1's merchant-facing fix), `reset_page_with_checkpoint`, and
`reset_storefront_with_checkpoint` (Issue 3's "page reset"/"storefront
reset must preserve a recoverable pre-reset state" requirement) all share
this one helper.

**Undo/Redo interaction (a real, deliberate behavior change, not a
regression):** `StorefrontEditHistoryEntry` rows are scoped to one Draft
row's continuous lifetime (`draft_version` FK, `select_for_update(pk=...)`
in `edit_history_service.record_change`) — `publish()` already wipes them
for exactly this reason at its own Draft-identity boundary. A checkpoint is
the same kind of boundary: once one fires, there is nothing correct to
attach a local Undo entry to (the old row's timeline ends there; the new
row starts clean, exactly like `restore_version`'s own result always has).
The pre-switch/pre-reset state is not lost — it is durably recoverable via
History → Restore, a strictly more robust mechanism (survives navigation/
reload) than a local Undo stack entry. Two pre-existing tests encoded the
old assumption and were updated to assert the new, intentional contract:
`test_u1a_preset_edit_history_characterization.py` (rewritten with the
full rationale in its module docstring) and
`test_phase35_reference_editable_backgrounds.py::test_reference_preset_apply_is_one_undo_step_and_restores_previous_draft`.
When nothing is checkpointed (empty Draft), Undo/Redo is completely
unaffected — verified by a dedicated test.

**Tests A-H** — `PreApplyCheckpointTests` in the new
`test_acceptance_batch2.py`: (A) a different-Template apply creates a
recoverable checkpoint; (B) the active Draft becomes a distinct version
when (and only when) there was something to protect; (C) the published
version's id/fingerprint are untouched; (D) the pre-switch state is
recoverable via the unmodified `restore_version`; (E) restore always
produces a `DRAFT`-status version and never touches `published_version`;
(F) `CrossStoreVersionError` on a cross-store restore attempt; (G) a
`LockedSectionsPresentError` mid-apply leaves the version count and
`draft_version` pointer completely unchanged; (H) a mid-write-loop failure
(mocked `rebuild_page_from_legacy_rows`) proves the whole checkpoint+apply
transaction rolls back atomically, including the checkpoint itself.

### Issue 2 — immutable Ready Template baseline snapshot

**Root cause / motivating risk (as specified):** `template_provenance` only
ever recorded `{key, version}`; a reset re-read the *live* `preset.pages`/
`appearance`/`header`/`footer` from `layout_preset_registry` by that key. A
future edit to a Preset's Python definition that forgets to bump `version`
would silently change what an *already-applied* Draft resets to.

**Data model — additive migration `0017_add_ready_template_baseline_snapshot_and_slot_key`:**
- `StorefrontLayoutVersion.template_baseline_snapshot` (`JSONField`,
  `default=dict`, `blank=True`) — an immutable, normalized record of the
  *exact* baseline actually applied: `template_key`, `template_version`,
  `default_palette_slug`, the fully-resolved `appearance`/`header_config`/
  `footer_config`, and per-page section composition (`pages: {page_type:
  [{slot_key, section_key, settings, row_key, row_span,
  container_settings}, ...]}`). Contains only stable registry keys and
  normalized configuration — no renderer template path, ever (verified by
  a dedicated test).
- `StorefrontSection.template_slot_key` (`CharField`, `blank=True,
  default=""`) — see Stable Section Identity below.

Both fields are nullable/default-safe for every historical row; the
migration is purely additive (no data migration, no destructive
operation) — verified by a clean forward `migrate` and an unchanged
`makemigrations --check --dry-run`.

**`preset_service.apply_preset`** now assembles and stores this snapshot
on every call (Gallery apply, direct apply-preset endpoint, and
`reset_storefront_to_baseline`'s legacy-compatibility path below all go
through it) — computed from the exact same already-validated
`cleaned_appearance`/`cleaned_header`/`cleaned_footer`/built
`StorefrontSection` rows the write phase was already producing, so there is
no second, possibly-diverging computation.

**`preset_service.apply_baseline_snapshot(draft, snapshot)`** — the reset
counterpart of `apply_preset`'s write phase, sourced entirely from a stored
snapshot dict; it never reads `layout_preset_registry` for content (only
`reset_storefront_to_baseline`'s *return value* — Persian label metadata —
still does, harmlessly).

**`reset_storefront_to_baseline(draft)`** now checks
`draft.template_baseline_snapshot` first: if present and its recorded
`template_key`/`template_version` match `template_provenance`, restores
from it via `apply_baseline_snapshot` (registry-immune — Issue 2's core
requirement). Otherwise it falls back to the **exact pre-Batch-2 behavior**
(re-read from the live registry by key+version, `TemplateBaselineVersionChangedError`
on mismatch) — the documented backward-compatibility path for a version
created before this batch (`template_provenance` present, snapshot absent
or empty). This never fabricates a baseline: it is the same trusted
registry-read path the system already used exclusively before this batch.
As a harmless side effect, that fallback's `apply_preset` call also records
a snapshot going forward, so the *next* reset of that same Draft no longer
needs the fallback.

**Tests A-H** — `ImmutableBaselineSnapshotTests`: (A) an applied Ready
Template stores an exact snapshot; (B) mutating the in-memory
`LAYOUT_PRESET_REGISTRY` entry afterward (the literal motivating scenario —
a temporarily swapped `LayoutPresetDefinition` with a changed `density`,
restored in a `finally` block) does not change the reset result; (C)
palette baseline included; (D) header/footer baseline included; (E) page/
section baseline (including every section's `slot_key`) included; (F) the
serialized snapshot contains no `.html`/`template_name`/section template
path; (G) two stores applying different Templates get distinct,
independently-scoped snapshots; (H) a simulated pre-Batch-2 Draft
(snapshot cleared, provenance kept) resets safely via the fallback and
"heals" its snapshot, and a version-mismatched legacy Draft still raises
`TemplateBaselineVersionChangedError` rather than silently substituting.

### Issue 3 — granular reset to Ready Template baseline

All granular resets read from `template_baseline_snapshot` — never from
`layout_preset_registry` — added to `preset_service.py` (no new module;
reuses the same "preset baseline" home):

- `reset_section_to_baseline(draft, section)` — RESET SECTION: restores
  `section_key`/`settings`/`row_key`/`row_span` from the section's baseline
  slot entry. Leaves `order`, Container/Cell placement, `is_active`,
  `is_locked`, `collapsed_in_editor` untouched (layout position and editor
  state are merchant decisions, not Template content) and never rebuilds
  Containers — a single-section content reset must never disturb a
  merchant's custom Free-Layout placement elsewhere on the page.
- `reset_section_setting_to_baseline(draft, section, key)` — RESET FIELD
  *and* RESET COMPONENT are the same operation in this architecture: a
  "component" (`card`, `responsive`, `background`, ...) is just a named,
  possibly-nested key inside a section's `settings`; restoring one key
  wholesale while leaving every sibling key alone is exactly what a scalar
  field-reset does too.
- `reset_appearance_setting_to_baseline(draft, key)` — RESET FIELD for a
  top-level `appearance_config` key, re-validated through the existing
  `validate_appearance_config`.
- `reset_page_to_baseline(draft, page_type)` — RESET PAGE: a full,
  intentional replacement of one page's composition from its baseline —
  the one granularity explicitly allowed to remove a merchant-added
  section **on that same page** (documented, tested exception — "Do not
  reset another section" does not mean "do not reset another page's rule
  applies to a full page reset too").
- `reset_header_to_baseline(draft)` / `reset_footer_to_baseline(draft)` —
  independent, each restores only its own `*_config` from the snapshot.
- `reset_storefront_to_baseline(draft)` (Issue 2, unchanged signature) —
  RESET STOREFRONT's in-place primitive.

**Stable Section Identity — `template_slot_key`:** a new,
deterministic-at-apply-time identity
(`f"{preset.key}:v{preset.version}:{page_type}:{index}"`, `index` being the
section's fixed position in the Preset's authored `pages[page_type]`
tuple) stamped onto every `StorefrontSection` `apply_preset` creates. It is
**not** `stable_id` (an existing, unrelated field tracking "same logical
section across a version clone", regenerated randomly on every fresh
`apply_preset`/`apply_baseline_snapshot` call) and **not** derived from
`order` (which a merchant freely changes by reordering) — a granular
section reset looks the section up by this key inside
`template_baseline_snapshot["pages"][page_type]`, so it keeps finding the
right baseline entry after the merchant reorders, inserts, or deletes
unrelated sections. An empty `template_slot_key` (the default, and what
every merchant-created section keeps forever — `storefront_section_add`/
`storefront_section_duplicate` never set it) means "not a Template-baseline
section" — `reset_section_to_baseline`/`reset_section_setting_to_baseline`
raise `NotABaselineSectionError` rather than silently no-op or guessing.
`_clone_version_content` copies it like every other section field, so a
checkpoint/restore/first-draft-bootstrap never loses this identity for the
sections that survive.

**Merchant-created content — explicit semantics, tested both ways:** a
section/field/component reset never touches any section other than the one
targeted (a merchant-added section on the same page survives a sibling
baseline section's reset — tested directly). A whole-PAGE or whole-
STOREFRONT reset **does** intentionally restore full Template-controlled
composition, which can remove a merchant-added section on an affected page
— this is the documented, confirmation-gated exception, never silent (the
Builder's confirm dialogs say so explicitly; see UI below).

**Merchant reset UI** — Persian-labeled controls, absent/disabled when
their scope has no baseline, never exposing JSON/registry keys/renderer
paths/internal IDs:
- «⟲ بازنشانی این بخش به قالب» — `section_settings_form.html`'s existing
  action toolbar, shown only when `section.template_slot_key` is set.
- «⟲ بازنشانی عنوان به قالب» — one illustrative field-reset control on
  `product_section`'s shared "title" field (RESET FIELD in the one
  inspector location every product-section type shares).
- «⟲ بازنشانی هدر به قالب» / «⟲ بازنشانی فوتر به قالب» —
  `header_panel.html`/`header_editor.html` and their footer counterparts,
  shown only when the snapshot defines that region's baseline.
- «⟲ بازنشانی این صفحه به قالب» / «⟲ بازنشانی کل ظاهر فروشگاه به قالب» —
  `editor.html`'s existing "صفحات فروشگاه" sidebar panel, next to "تاریخچه
  نسخه‌ها".

Every destructive control (section/page/storefront/header/footer reset)
requires a native `confirm()` dialog stating in Persian exactly what will
be lost before the POST fires.

**Versioning interaction — proportional strategy (as required, documented
here rather than left implicit):** page and storefront reset go through
`reset_page_with_checkpoint`/`reset_storefront_with_checkpoint` (a full
history checkpoint, same as Issue 1) — their blast radius (an entire page
or the whole storefront's composition) matches the cost of a version row.
Field/component/section/header/footer reset never create a checkpoint —
only the lightweight, already-existing `@_record_edit_history`
Undo/Redo entry — their blast radius (one key, one section, one config
blob) does not justify permanent version-history rows, and this matches
the explicit instruction against "excessive full-version history spam."
No reset of any granularity ever auto-publishes.

**Transaction/failure safety:** every mutating function above
(`apply_preset`, `apply_baseline_snapshot`, `reset_page_to_baseline`, the
three `*_with_checkpoint` wrappers) is `@transaction.atomic`; every
destructive scope validates (locked-sections, unknown-page-type,
unknown-field, not-a-baseline-section) **before** any write, matching the
engine's existing "validate everything, then write" invariant. Verified
directly for the checkpoint paths (Issue 1's G/H); granular resets raise
before writing by construction (checked, not separately fuzz-tested beyond
the direct error-path tests already listed).

**Tests** — `GranularResetTests` (field/component/appearance-field resets;
stable identity across reorder+insert+delete; merchant-created-section
rejection and survival; stale-slot detection; page reset's documented
merchant-content exception and its page/header/footer isolation; unknown-
page-type and missing-header/footer-baseline errors) and
`ResetCheckpointIntegrationTests` (page/storefront reset create a
checkpoint, publish untouched) in `test_acceptance_batch2.py`;
`MerchantResetUITests` covers the Persian labels, confirm dialogs, scope-
based visibility, and the no-internal-detail-leak requirement end-to-end
through the real views.

### Files changed

- `apps/storefront_builder/models.py` — the two new fields.
- `apps/storefront_builder/migrations/0017_add_ready_template_baseline_snapshot_and_slot_key.py` — new, additive.
- `apps/storefront_builder/services/layout_service.py` —
  `checkpoint_draft_before_replacement`, `_draft_has_any_content`,
  `_clone_version_content` now also copies `template_provenance`/
  `template_baseline_snapshot`/`template_slot_key`.
- `apps/storefront_builder/services/preset_service.py` — snapshot
  assembly in `apply_preset`; `apply_baseline_snapshot`;
  `apply_preset_with_checkpoint`; `reset_storefront_with_checkpoint`;
  `reset_page_with_checkpoint`; `reset_page_to_baseline`;
  `reset_section_to_baseline`; `reset_section_setting_to_baseline`;
  `reset_appearance_setting_to_baseline`; `reset_header_to_baseline`;
  `reset_footer_to_baseline`; `reset_storefront_to_baseline` rewritten for
  snapshot-first/legacy-fallback; new `BaselineResetError` hierarchy.
- `apps/storefront_builder/views.py` — `storefront_apply_layout_preset`
  now calls `apply_preset_with_checkpoint`; six new reset views.
- `apps/dashboard/urls.py` — seven new URLs.
- `apps/storefront_builder/templates/dashboard/storefront_builder/{editor.html,header_editor.html,footer_editor.html,partials/header_panel.html,partials/footer_panel.html,partials/section_settings_form.html}` —
  the merchant reset controls.
- `apps/storefront_builder/tests/test_acceptance_batch2.py` — new; all
  three issues.
- `apps/storefront_builder/tests/test_u1a_preset_edit_history_characterization.py`,
  `test_phase35_reference_editable_backgrounds.py` — updated for the
  intentional checkpoint-vs-Undo/Redo interaction (see Issue 1).

### Testing

Ran, all green: the new `test_acceptance_batch2.py` (50 tests); that
combined with `test_acceptance_batch1.py`/`test_layout_service.py`/
`test_u7_ready_template_baseline.py`/`test_u8_template_gallery.py`/
`test_u10_ready_template_catalog.py`/`test_preset_service.py`/
`test_u1a_preset_edit_history_characterization.py`/
`test_layout_preset_registry.py` (213 tests); the entire
`apps.storefront_builder` suite (1618 tests, 1 pre-existing unrelated
skip). `apps.catalog` was not re-run — no file under `apps/catalog`
changed this batch. `python manage.py migrate storefront_builder` applied
0017 cleanly forwards; `makemigrations --check --dry-run` → "No changes
detected" both before recording data and after. `git diff --check` →
clean.

### Known limitations (explicit, not gaps to hide)

1. Field/component reset UI is illustrative, not exhaustive — one shared
   field (`product_section`'s title) got a real control; the service layer
   (`reset_section_setting_to_baseline`) supports any settings key for any
   baseline-origin section, so adding more controls to other section types'
   forms is a template-only follow-up, not a new capability.
2. A single-section content reset intentionally never rebuilds Container/
   Cell placement (to avoid disturbing a merchant's custom Free-Layout
   column structure elsewhere on the page) — if the restored baseline
   `row_key`/`row_span` differ from the section's current placement, the
   legacy row metadata and the actual Cell/Container structure can end up
   cosmetically out of sync until the merchant manually adjusts layout;
   this never affects public rendering (Container/Cell is the render
   source of truth once Containers exist).
3. Template Gallery screenshots/thumbnails, digital/service product
   semantics, non-home Template differentiation, and general color-system
   changes remain explicitly out of scope, per the batch's own exclusions
   — not started here.

## Post-U11 Acceptance QA Hotfix — PDP Thumbnail Theme-Palette Regression

- **Starting SHA:** `842cd40bd4ea2b7dc0c7e73590edb58548901068` (the Batch 2
  commit above)

**Real browser symptom:** on `rastisi-fashion-test`, product «شلوار کتان
مدل دنیز» (3 `ProductImage` rows) rendered its large PDP image correctly
and three thumbnail button slots, but all three thumbnails were blank/
white.

**Verified media/storage health (ruled out first):** `PRODUCTS=100
BAD_IMAGE_COUNT=0 BAD_COVER_COUNT=0 BAD_ORDER=0 MISSING_FILES=0`; for this
product specifically, all 3 images and all 3 thumbnail files existed on
disk with correct `order`/`is_cover`. Not a media/database problem.

**CSS root cause:** `apps/core/static/css/theme_palette.css`'s Product
Detail rule matched `.gallery .thumbs .th` (the PDP gallery thumbnail
button in `product_main.html`, which sets its own inline
`background-image:url(...)`) and used the `background` **shorthand** with
`!important`. The shorthand resets every background sub-property —
including `background-image` — to its initial value even when only a
color is written; combined with `!important`, it silently overrode the
thumbnail's own inline `background-image`, leaving only an empty surface
color.

**Fix (one property, one rule, no other changes):**
```css
/* before */
background:var(--theme-card-bg,var(--theme-surface))!important;
/* after  */
background-color:var(--theme-card-bg,var(--theme-surface))!important;
```
`background-color` only ever sets the theme's fallback surface color —
never `background-image`. `!important` was kept (not implicated — the
shorthand vs. longhand distinction was the entire bug); no other
`background:` declaration in the file was touched.

**Regression test** — `test_phase39_full_site_palette_system.py::Phase39GlobalThemeCssContractTests`:
`test_product_detail_rule_does_not_reset_thumbnail_background_image` (CSS
source: asserts the Product Detail rule contains the `background-color`
form and not the exact `background:...!important` shorthand fragment —
scoped to that one rule block, not a file-wide replace) and
`test_pdp_thumbnail_inline_background_image_is_untouched_by_the_palette_rule`
(confirms `product_main.html` still emits the inline
`background-image:url(...)` the fix protects). Confirmed failing against
parent SHA `842cd40`'s original CSS (`git show 842cd40:apps/core/static/css/theme_palette.css`)
before writing the fix, passing after.

**Test results:** the 2 new tests + the full
`test_phase39_full_site_palette_system.py`/`test_acceptance_batch2.py`/
`test_acceptance_batch1.py`/`test_u2a_global_header_system.py`/
`test_u2b_global_footer_system.py`/`test_appearance.py` combined (278
tests) — all pass. Full `apps.storefront_builder` suite (1620 tests, 1
pre-existing unrelated skip) — all pass. `apps.catalog` untouched, not
re-run. `makemigrations --check --dry-run` → "No changes detected" (no
model/schema change — CSS + test only). `git diff --check` → clean.

## Post-U11 Acceptance Fix Batch 3 — Real Ready-Template Gallery Previews/Thumbnails

- **Starting SHA:** `0c425d499f7905adc66a36f49de715c5cb619d47` (the PDP
  hotfix commit above)

**Original Gallery gap:** each of the 8 official Ready Template cards
(U8's `template_gallery.html`) only showed a flat 3-color swatch strip
(`_palette_swatch` — three of the palette's `primary`/`secondary`/`accent`
hex values as solid bars). Zero structural information — a merchant could
not tell one Template's header style, hero presence, section composition,
or footer character from another before applying it.

**Selected thumbnail architecture:** a new pure function,
`services/template_preview_service.build_template_thumbnail_svg(preset)`,
returns a deterministic inline `<svg>` schematic computed live from real
registry data on every Gallery request — no screenshot, no static asset
file, no database row, no Playwright/browser process anywhere in the
request path. Wired into `storefront_template_gallery`'s existing
`template_cards` construction as one new key (`thumbnail_svg`) per card,
alongside the untouched 3-swatch strip (kept, not replaced, to avoid
disturbing anything U8 already relied on).

**Why this is not a parallel renderer / not arbitrary art:** every visual
fact the SVG draws traces to a real registered source, reused directly
rather than re-derived:
- Colors: `appearance_registry.resolve_colors`/`resolve_theme_roles` — the
  *exact same functions* the real context processors call — applied to
  `{**preset.appearance, "palette_slug": preset.default_palette_slug}`,
  i.e. precisely the state a fresh `apply_preset` would produce.
- Layout/composition: the preset's own real `pages["home"]` tuple, in its
  real order, capped at 6 displayed rows (disclosed, not hidden) with each
  row's relative height weighted by an archetype keyed on the section's
  real `section_key` (`hero_banner` → dominant block, `category_grid`/
  `story_rail` → chip row, any `section_registry.CARD_AWARE_SECTION_KEYS`
  member → a product-card grid reusing that existing allowlist rather
  than a second one, etc.) — a section type this module hasn't been
  taught yet safely falls back to a generic content block, never a crash.
- Header/footer density cues: real toggle counts
  (`show_search`/`show_account`/`show_wishlist`/`show_cart`,
  `show_about`/`show_contact`/`show_categories`/`show_quick_links`/
  `show_social`) and the real `announcement_enabled` flag decide line
  counts and whether an announcement strip is drawn.
- The one deliberate exception, and it is a *variant-level*, not a
  Template-level, fact: the registered `dark_tech` global header/footer
  variant renders its own always-dark chrome via a dedicated CSS shell
  (`storefront_builder.css`'s `.gh-shell--dark`) independent of the
  active palette (documented in the Batch 1 ledger's Issue 2 audit) — the
  thumbnail reads that variant's real, already-shipped hex values
  (`#121218`/`#1b1b24`/`#f1f0f5`/`#2a2a37`, literally copied from that CSS
  rule with a source comment) so `dark_digital`'s preview isn't
  dishonestly light. This branches on the registered *variant key*
  (`header_variant == "dark_tech"`), the same generic dispatch axis
  `global_region_registry.resolve_global_renderer_template` already uses
  for every Preset that ever selects that variant — never on a Preset/
  Template key, never on a store slug. A source-level audit for
  `preset.key ==`/`template_key ==`/`store.slug ==` patterns in the new
  module found none.

**Source/data safety:** the function takes only a `LayoutPresetDefinition`
— no `request`, no `store`, no database query — so it is structurally
incapable of leaking another store's products/categories/media/
identity/orders. No product photography, no text strings, no external
`<image>`/`xlink:href` references, no reference-store names anywhere in
the generated markup (verified by a dedicated test). Two different stores
requesting the Gallery for the same Template key get byte-identical
thumbnail markup (determinism verified directly).

**No-mutation behavior:** the thumbnail computation and its Gallery
wiring add zero writes — `resolve_gallery_thumbnail` (the safe wrapper)
never touches `layout_service`/`preset_service`. Verified end-to-end: a
Gallery GET leaves the Draft's id/`appearance_config`/`header_config`/
`footer_config`/`template_provenance`/`template_baseline_snapshot`
byte-identical, leaves `Published`'s id/fingerprint untouched, creates no
new `StorefrontLayoutVersion` row, and (via a mocked
`preset_service.apply_preset`/`apply_preset_with_checkpoint`) never calls
the mutation service at all.

**Template/version mapping:** keyed purely by the stable
`LayoutPresetDefinition.key` object identity already passed to the
function — there is no separate manifest/lookup table that could drift
out of sync with a key, so "Template A's thumbnail rendering on Template
B's card" is structurally impossible (there is nothing to mismatch).
`preset.version` is implicitly honored too: because the thumbnail is a
pure function of the *live* preset object (never a cached/stored asset),
it automatically reflects whatever that object's current fields are —
there is no stale-version risk to guard against, unlike a generated file
that would need its own version-keyed filename.

**Performance:** zero database queries, zero template rendering, zero
nested storefront requests — pure string-building over in-memory Python
objects already loaded at import time. Confirmed manually: all 8 official
Ready Templates' thumbnails render in a single `python manage.py shell`
call as a batch with no measurable per-call cost; the Gallery view's own
query count is unchanged from before this Batch (`_palette_swatch`/
`_variant_label` were already O(1) per card; `thumbnail_svg` adds another
O(1) per card, no new query source).

**Accessibility:** each card's `<div class="tpl-thumb">` carries
`role="img"` and a Persian `aria-label` naming the specific Template
(`"پیش‌نمایشِ چیدمانِ قالبِ «...»"`); the inner `<svg>` itself is
`aria-hidden="true" focusable="false"` so its dozens of decorative
`<rect>`/`<circle>` primitives never produce per-shape screen-reader
noise — assistive tech announces exactly one meaningful label per card.
No existing keyboard-operable control (the Apply/current-state
button, the Gallery↔Editor links) was touched.

**Tests** — `test_acceptance_batch3.py` (15 tests): A (exactly the 8
official keys), B (every official Template resolves a well-formed,
non-trivial SVG, both at the service level and rendered into the real
Gallery HTML), C (all 8 thumbnails are pairwise distinct and each is
individually deterministic — rules out a broken shared constant), D (a
forced exception in the real builder degrades to the safe placeholder,
never propagates), E-H (the full no-mutation contract above), I (current-
Template badge/disabled-action still correct, and the current card still
gets a real thumbnail), J (no forbidden reference-store string or
embedded/linked external image anywhere in any of the 8 thumbnails), K
(the thumbnail's CSS uses percentage width, not a fixed pixel box, so it
scales on mobile), L (thumbnail markup contains no store identity, and is
byte-identical across two different stores requesting the same Template).
Tests M-P from the master contract ("if implementing a thumbnail
generation command/tool") do not apply — this Batch deliberately has no
static-asset generation command, manifest, or file pipeline; the
thumbnail is always computed live, so there is nothing to regenerate,
version-stamp, or corrupt.

### Files changed

- `apps/storefront_builder/services/template_preview_service.py` — new;
  the whole thumbnail architecture.
- `apps/storefront_builder/views.py` — `storefront_template_gallery` adds
  one `thumbnail_svg` key per card.
- `apps/storefront_builder/templates/dashboard/storefront_builder/template_gallery.html` —
  the new `.tpl-thumb` preview block (added above the existing swatch
  strip, which is unchanged).
- `apps/storefront_builder/tests/test_acceptance_batch3.py` — new.

### Testing

Ran, all green: the new `test_acceptance_batch3.py` (15 tests); that
combined with `test_u8_template_gallery.py`/`test_u10_ready_template_catalog.py`/
`test_acceptance_batch1.py`/`test_acceptance_batch2.py`/
`test_phase39_full_site_palette_system.py` (the PDP-hotfix theme-palette
regression tests)/`test_layout_preset_registry.py`/`test_render_service.py`
(195 tests); the entire `apps.storefront_builder` suite (1635 tests, 1
pre-existing unrelated skip). `apps.catalog` was not re-run — no file
under `apps/catalog` changed and the new preview code never touches
catalog models/services. `python manage.py check` → clean.
`makemigrations --check --dry-run` → "No changes detected" (no model
field was added — the thumbnail is computed, never stored). `git diff
--check` → clean.

### Known remaining limitations (explicit, not gaps to hide)

1. The schematic caps displayed home-page rows at 6 — a Preset with more
   than 6 home sections (none of the 8 official ones today; the max is
   7, `premium_leather`) shows its first 6 in real order, not all of
   them; disclosed here rather than silently truncated without mention.
2. The preview is an abstract structural schematic, not photorealistic —
   it communicates real header/hero/composition/footer differences
   faithfully but does not (and is not meant to) simulate real product
   photography or typography rendering.
3. Non-home pages (listing/collection/search/product_detail/cart) are not
   separately previewed — explicitly out of this Batch's scope (per its
   own "Do NOT redesign PDP or Listing variants" exclusion); the Gallery
   card represents the home-page baseline only, exactly as the old
   3-swatch strip did.

## Post-U11 Acceptance Fix Batch 4 — Rasti Mode Demo Real Catalog, Media, Content & All 8 Ready Template Real Previews

- **Starting SHA:** `63c490de765a51a7bb17924f3e7d00a1055486f4` (the commit
  that added the raw 345-image QA catalog, immediately preceding this
  Batch's own work).

**Context.** Two earlier, narrower missions (untracked in this ledger —
their own final reports are the record) built a *placeholder-data*
version of the isolated `rasti-mode-demo` Store: "Phase 1" seeded 50
apparel-only products with locally PIL-generated solid-color placeholder
images; "Phase 1.1" fixed an unused demo brand and audited the currency
contract. This Batch replaces that placeholder foundation entirely: the
project owner supplied 345 real product photographs, and the mandate was
to build the *real* Rasti Mode Demo catalog/media/content around what
those photographs actually show, then render that same completed demo
through all 8 official Ready Templates with real captured screenshots
replacing the Batch 3 abstract SVG as the Gallery's normal preview.

### Step 1 — Image forensics (345 raw photos)

Verified the committed raw pool at
`apps/stores/demo_assets/rasti_mode_demo/raw_user_catalog/`: folder 1 = 66
JPG, folder 2 = 55, folder 3 = 70, folder 4 = 66, folder 5 = 88 — total
345, matching `QA_SOURCE_ASSETS.md` exactly (preserved verbatim, not
edited).

Built `scripts/build_inventory.py` (Pillow-based, one-off, not a
management command): computed per-image width/height/aspect-ratio,
SHA-256, an average-hash for near-duplicate flagging, and dominant colors
for all 345 files, and rendered 10 contact sheets (grids of labeled
thumbnails, ≤48 images each) under a git-ignored `_work/` scratch
directory. Every one of the 345 images was visually reviewed via these
contact sheets (not filenames — the raw filenames are opaque scraper
artifacts like `1_org_zoom-43.jpg` with no reliable per-product grouping).
Two forensic findings worth recording:
- All 345 raw files share the identical 401×601 pixel size (a
  scraper-normalized "zoom" preview size) — this initially made the
  average-hash near-duplicate detector flag many genuinely *different*
  products as nightmarish near-duplicate clusters, since centered
  studio product photography on a plain background produces very similar
  coarse luminance hashes regardless of the actual product. Direct visual
  inspection (not the hash) was treated as authoritative, per the
  mission's own "do not rely on filenames alone" instruction extended to
  "do not blindly trust a naive perceptual hash either."
- The raw pool is a flat collection of single studio photos — one real
  photograph per item, not multi-angle photo sets of the same product.
  This confirmed upfront that nearly every one of the 50 selected products
  would need the mission's explicitly-sanctioned "01 = real photo, 02/03 =
  derived non-destructive crops of that same photo" fallback, rather than
  three independent real angles.
- Confirmed (matching the mission's own folder hypotheses): folder 1 =
  sneakers (running + casual/lifestyle, several real, unverified brand
  logos visible — New Balance, Puma, Adidas Samba, Converse, Nike);
  folder 2 = men's trousers/chinos/jeans (mostly on-model shots); folder 3
  = jackets (bomber/varsity/leather/overshirt — **only one genuine hoodie
  photo in the entire 345**); folder 4 = a genuine *mix* of women's
  footwear (flats/heels/sandals/boots) interleaved with handbags; folder 5
  = handbags/totes/shoulder bags (several with visible luxury-brand-style
  logos/plaques).

### Step 2 — Taxonomy (one disclosed refinement)

Final 10 categories: کتانی رانینگ, کتانی کژوال, شلوار کژوال, شلوار جین,
**کاپشن و بامبر**, **ژاکت چرم و اورشرت**, کفش زنانه, صندل و دمپایی, کیف
دستی و Tote, کیف دوشی و مجلسی.

**Refinement (mission-authorized, explained per its own instruction):**
the suggested 6th category was "هودی و سویشرت" (hoodie/sweatshirt). With
only one real hoodie photo in the whole 345-image pool, forcing 5 hoodie
products would have meant fabricating 4 out of 5 products' core identity
— the exact "never call a sneaker a shirt" failure mode the mission
explicitly forbids. Folder 3's actual, well-populated content splits
cleanly into two real jacket-style clusters instead: bomber/varsity
jackets (plus the one real hoodie, folded in as a casual-outerwear
member) and leather jackets/denim jacket/overshirts. Categories 5–6 were
relabeled accordingly; all 8 other suggested category labels are used
verbatim. 10 categories × 5 products × 50 total preserved exactly.

### Step 3 — 50 real products (SKUs reused, FSH-001…FSH-050)

Every one of the 50 SKUs was reassigned to a genuinely different real
photograph (verified unique `(folder, filename)` per SKU — see the
`assert` in `select_and_process_media.py`'s `SELECTION` table). Each
product got a Persian title/description honestly derived from what its
own photo shows (color + category + style), never copied from any
retailer, and never describing a feature the photo doesn't show. Real
color per product = the one visible color in its one real photo (see
Step 8 below on why no product was given fabricated multi-color
variants). Brand: since several raw photos show unverified real
third-party trademarks (Nike/Adidas/Puma/Converse/New Balance-style
sneakers; unverified luxury-style handbag hardware/logos), the decision
was to use **only the 6 recommended fictional brands** — Demo Motion,
Demo Urban, Demo Denim, Demo Layer, Demo Carry, Demo Muse — for every
single product, never a guessed real brand name, and product copy never
names a real brand even where one is visually suggested by the photo.
Final distribution: Motion 6, Urban 11, Denim 8, Layer 7, Muse 10, Carry
8 (sums to 50; every brand has products — the mission's own explicit
"don't leave an unused brand like Demo Vero last time" callout).

### Step 4/5 — 150 final images + manifest

`scripts/select_and_process_media.py` (one-off, not a management command)
processes the 50 selected raw photos into
`apps/stores/demo_assets/rasti_mode_demo/products/<SKU>/01|02|03.webp` —
1200×1600, 3:4 neutral canvas (light `#F7F6F3` letterboxing, never a
destructive crop of the product itself), WebP quality 88:
- `01.webp` = the real source photo, canvas-normalized only (full frame,
  zero crop).
- `02.webp`/`03.webp` = deterministic derived crops of that *same* real
  photo (82%/70% centered zoom, slightly offset) — explicitly flagged
  `"derived": true` in the manifest with a plain-text transformation
  description, per the mission's own fallback contract for products
  without three true source photos (which is every product here).

`selected_product_media_manifest.json` records exactly 150 entries, each
with `sku`/`image_order`/`cover`/`raw_source_relpath`/
`raw_source_sha256`/`final_relpath`/`final_sha256`/`derived`/
`transformation`/`category`/`product_title_fa`/`brand`/
`dominant_color_fa`/`provenance_status` (always
`"user_supplied_qa_source"`). Verified: exactly 1 cover per SKU, no
duplicate `final_relpath` values, every `final_relpath` file physically
exists and its SHA-256 matches the recorded value.

### Steps 6–11 — Brands / Tags / Colors / Sizes / Prices / Discount-Stock Matrix

- **Tags:** 9 meaningful tags (جدید, پرفروش, تخفیف‌دار, انتخاب فصل, اسپرت,
  کژوال, روزمره, مینیمال, پریمیوم), assigned by a small deterministic rule
  keyed on each row's own real structure (discount → تخفیف‌دار; 5th
  product per category → جدید; 3rd → پرفروش; sneaker/bomber categories →
  اسپرت; trouser/jacket/shoe categories → روزمره; bag categories →
  مینیمال; 5 specific seasonal picks → انتخاب فصل; 6 highest-value SKUs →
  پریمیوم) — never meaningless noise tags.
- **Colors:** exactly the one real visible color per product (see Step 8
  below) — no invented second colorway.
- **Sizes:** category-correct per mission Step 9 — sneakers/women's
  shoes/sandals use numeric EU sizes in the 36–46 range; trousers/jeans
  use numeric waist sizes; jackets use S/M/L/XL/XXL subsets; **bags get no
  size option at all** (`ProductType.SIMPLE`, no `ProductOption` rows) —
  not even a fake "one-size" value, since the model does not require one.
- **Prices:** varied, non-round-number values within the mission's
  suggested per-category ranges (sneakers 2.5–9M, trousers 2–6M, jackets
  4–14M, women's shoes/sandals 2–8M, bags 2.5–12M تومان).
- **Discount/stock matrix:** 22 discounted / 28 non-discounted; exactly 10
  fully out-of-stock (one per category); exactly 8 partial-variant-stock
  products (one per apparel/footwear category — bag categories are
  `SIMPLE` products, so "partial variant stock" is not a meaningful state
  for them and was not forced), each verified to have at least one
  zero-stock and one purchasable real `ProductVariant` combination; the
  remaining 32 fully in-stock. All spread across categories, not
  clustered.

### Step 12/13 — Real media import + color-image mapping

`_seed_product_images` imports the 150 pre-processed WebP files through
the real `add_product_image` service (never touching `raw_user_catalog/`
— verified structurally: `_load_processed_image` only ever builds paths
from `PRODUCT_MEDIA_DIR`). Every product ends with exactly 3
`ProductImage` rows and exactly 1 cover. Since every product in this
real-photo dataset has exactly one genuine visible color, the color→image
`option_value` mapping is applied only to the cover image of each
variable product (structurally correct, honest single-color mapping) —
no fabricated multi-color mapping was created anywhere, per the mission's
explicit "do not fake mappings for single-color products."

### Step 14 — Category visuals

10 real category tile images, each a Pillow composite (gradient +
one real representative product photo, no external fetch) built from the
category's own first real product image — `apps/stores/management/
commands/seed_ready_template_fashion_demo.py::_seed_category_images`.

### Steps 15–17 — Store identity, homepage content, hero/banner visuals

Store identity: `Rasti Mode Demo`, neutral demo contact info (a placeholder
phone/email/address, never a real merchant's). Content built from the real
catalog: 4 `HeroSlide`s, 6 `PromotionalBanner`s, 10 `StoryRailItem`s (one
per category, real category destination), a 10-category header `Menu`, a
footer quick-link `Menu`, `FooterSettings`, and 6 `MerchantCollection`s
(جدیدترین‌ها, پرفروش‌ها, تخفیف‌های منتخب, انتخاب فصل, plus two bonus
category-flavored collections — کفش و کتانی, کیف و اکسسوری). Hero/banner
visuals are Pillow compositions of 2–3 real processed product photos on a
neutral gradient background — **no text is baked into these images**: the
actual Persian headline/subtitle/CTA text lives in `HeroSlide.title`/
`subtitle`/`button_label` model fields, rendered by the real template with
the browser's own font (this sandbox has no Persian-capable font for
Pillow to draw with — baking text into the raster would have produced
garbled glyphs; the real architecture already separates copy from image
for exactly this reason).

**Real bug found and fixed during this step:** the real PDP view
(`build_product_detail_context` → `is_gift_wrap_available` →
`ShopSettings.load`) raised `ShopSettingsNotProvisionedError` for the demo
store — discovered only by actually loading a real PDP, not by unit
testing the seed command in isolation. Fixed by adding
`ShopSettings.provision_for(store)` (`_seed_shop_settings`) to the seed
command, with demo tagline/description/contact fields.

### Step 18 — Seed command

Kept the established name `seed_ready_template_fashion_demo` (renaming
would break every previously-documented Windows QA command and existing
test); "fashion" is read as the standard broad retail umbrella covering
apparel/footwear/bags, which the new catalog still is. Deterministic,
idempotent (a second run creates zero duplicate rows/images/content —
verified), safe `--reset` (only ever deletes `Store.objects.filter(
slug="rasti-mode-demo")`, structurally cannot target another Store — no
CLI argument accepts a different slug), never touches
`rastisi-fashion-test` or any real merchant Store (tested against a live
fixture Store carrying that exact slug).

**A second real bug found and fixed:** `--reset` raised `ProtectedError`
on `MenuItem.menu` (that FK is `PROTECT`, not `CASCADE`, unlike every
other content model's `store` FK) once real navigation content existed —
discovered only by actually running `--reset` against a fully-seeded
store, not by reasoning about the schema. Fixed by explicitly deleting
`MenuItem.objects.filter(menu__store=existing)` before deleting `Product`s
and the `Store` itself, in the same safe-ordering spirit as the existing
`ProductVariant`-before-`Product` step.

A separate `StoreDomain` was added for the *public* storefront
(`shop-{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`, `is_primary=False`),
independent of the existing admin-dashboard `StoreDomain`
(`is_primary=True`) — mirroring the codebase's own established
`AdminSubdomainIndependentOfPublicDomainTests` pattern. Both hostnames
resolve to `127.0.0.1` locally with zero hosts-file editing because they
live under the `.localhost`-suffixed `RASTISI_ADMIN_DOMAIN_SUFFIX` DEBUG
override, which itself sits under the RFC 6761-reserved `.localhost` TLD.

### Step 19 — Real storefront verification (actually executed, not asserted)

Ran the actual local dev server (`manage.py runserver`) and hit it with
real HTTP requests (both Django's test client with `override_settings`
*and*, separately, plain `curl`/a real browser against the unmodified
`ALLOWED_HOSTS` — to prove the public host resolves for real, not just
under a test-only override) against `shop-rasti-mode-demo.rastisi.
localhost`: HOME (200, real hero/product content), LISTING (200, plus
`?q=`, `?discounted=1`, `?in_stock=1` filters all 200), a variable
product's PDP (price/size-options/color-option/"ناموجود" badge all
present for an OOS product), a `SIMPLE` bag's PDP (price present, no
size selector), COLLECTION detail (200), and a real cart-add POST for an
in-stock variant (HTMX cart-count response confirms the add succeeded).

### Steps 20–21/29 — All 8 official Ready Templates, same demo content

`layout_preset_registry.list_ready_templates()` returns exactly the same
8 official keys used throughout this ledger (`dense_marketplace`,
`premium_leather`, `warm_boutique`, `fashion_promo_catalog`,
`playful_lifestyle`, `utility_catalog`, `editorial_jewelry`,
`dark_digital`) — the capture tool (below) iterates this list directly,
never a second hard-coded Gallery list. Each Template was Applied +
Published (via the existing real `preset_service.apply_preset_with_checkpoint`
+ `layout_service.publish` — the same production merchant flow) onto the
*same* `rasti-mode-demo` Store, one at a time, so all 8 captures show the
exact same 50 products/150 media/10 categories/brands/prices/discounts/
stock/6 collections/hero/nav/footer — only the registered Template
configuration differs. Visual inspection of the 8 resulting captures
(see below) confirms genuinely distinct header styles, hero treatment,
section density, and color roles per Template — no `if template_key ==
"..."` special-casing was added to any renderer; differentiation comes
entirely from each Preset's own registered configuration.

### Steps 22–28 — Screenshot architecture (implemented AND executed)

**Architecture:** `apps/storefront_builder/services/template_preview_service.py`
gained an additive resolution layer (the pre-existing Batch 3 pure-SVG
functions are byte-for-byte untouched — all 15 `test_acceptance_batch3.py`
tests still pass unmodified): `resolve_real_screenshot(preset)` does a
pure filesystem check (`ready_template_previews/<key>/v<version>.webp` +
a `.meta.json` sidecar recording a SHA-256 **content hash of exactly the
registry data the screenshot visually depends on** — appearance/palette,
header, footer, home section-key order) and returns the static-relative
path only if both the file and a matching hash exist; otherwise `None`.
This function does zero browser/network/database work — the anti-
staleness contract (Step 24: "do NOT silently show an old version
screenshot") is enforced by the hash comparison, not by trusting a
version number alone.

The actual capture tool,
`apps/storefront_builder/management/commands/capture_ready_template_previews.py`,
is a **dev/build-time-only** script (never imported by the Gallery view
or the preview service): it requires an already-running real
`manage.py runserver` (it never starts/stops one itself), targets *only*
the hardcoded `rasti-mode-demo` Store (no CLI argument can redirect it —
tested), and for each of the 8 Templates: Applies+Publishes it (skipping
the call if already current, mirroring the existing rate-limit-aware
`seed_rastisi_fashion_demo._seed_builder` pattern) then uses Playwright +
the sandbox's pre-installed Chromium to navigate to the real public host
and capture a 1440×1100 JPEG, converts it to WebP (quality 88) via
Pillow, and writes it + the hash sidecar.

**This was actually run in this sandbox**, not merely built:
`pip install playwright` (the browser binary was already pre-installed;
only the Python wrapper needed installing) and 8 real canonical HOME
captures were generated and are committed under
`apps/storefront_builder/static/ready_template_previews/<key>/v1.webp`,
plus (via `--full-qa`) 24 additional QA-evidence captures (HOME-mobile,
LISTING-desktop, PDP-desktop per Template) under
`docs/qa_evidence/ready_template_previews/<key>/` (not part of the
Gallery; QA evidence only, `git`-tracked images, ~2.3 MB total).

**Three real bugs found and fixed while actually running the capture, not
anticipated in advance:**
1. `sync_playwright()` installs a running asyncio event loop in the
   calling thread; Django's ORM refuses `SynchronousOnlyOperation` for any
   sync query issued from inside that thread. Fixed by running the
   Apply+Publish DB write via a genuine separate OS thread
   (`concurrent.futures.ThreadPoolExecutor`) for each Template iteration.
2. The very first full run produced **8 byte-identical WebP files**
   despite each Template genuinely differing server-side (proven via
   direct `curl`) — root cause: the capture code navigated Playwright to
   the bare `--base-url` IP (`http://127.0.0.1:8123/`) instead of the
   Store's real public hostname, so Django's Host-based routing never saw
   `shop-rasti-mode-demo...` and served an unrelated/default Store's page
   every single time, regardless of which Template was actually applied
   to the demo Store. Fixed by reconstructing the navigation URL from the
   resolved public host (with `--host-resolver-rules=MAP <host> 127.0.0.1`
   at the Chromium launch level so the name-based request still reaches
   the local server). Verified after the fix: all 8 WebP files have
   distinct sizes and hashes, and were visually confirmed to show
   genuinely different header/hero/layout treatments of the same real
   catalog.
3. The QA-evidence PDP capture's "click a product" selector
   (`a[href*='/products/']`) matched a category-filter link on the
   listing page (which also contains `/products/` in its href) instead of
   a real product card, producing a filtered-listing screenshot mislabeled
   as a PDP. Fixed by targeting the real product-card link class
   (`a.pcard-hitarea`, confirmed from `product_card.html`) — verified the
   regenerated PDP captures show a genuine product detail page (price,
   stock badge, gallery thumbnails, add-to-cart).

### Step 30 — Gallery UX integration

`storefront_template_gallery`'s `template_cards` now resolves
`resolve_real_screenshot` first for each card; only when it returns `None`
does the existing Batch 3 SVG (`resolve_gallery_thumbnail`) render as
before. `template_gallery.html`'s `.tpl-thumb` branches on the new
`thumbnail_kind` field: a real screenshot renders as an `<img>` wrapped in
a plain `<a href>` to the same static image (opens larger in a new tab —
a structurally non-mutating plain link, no view logic) with
`object-fit:cover`; the SVG fallback path is completely unchanged.
Persian names/descriptions, the current-Template badge, and the disabled
"already applied" action are all unchanged from Batch 1/3. All 8 official
cards currently render the real screenshot branch (verified: 0 SVG
fallbacks in the live Gallery HTML today); a Template whose screenshot
goes missing or stale still degrades safely to the SVG schematic — never
a broken image, never a stale/misleading one.

### No-mutation contract (re-verified under the new code path)

`resolve_real_screenshot` contains no `import playwright`/`selenium`
statement anywhere (checked structurally, not just by absence of a call).
New tests re-prove, with real committed screenshots now present (so the
"nothing to resolve, trivially passes" loophole does not apply): a Gallery
GET creates no new `StorefrontLayoutVersion`, never calls
`apply_preset`/`apply_preset_with_checkpoint`, and — swapping
`sys.modules["playwright"]` to `None` for the duration of the request —
the Gallery page still renders 200. All 15 pre-existing
`test_acceptance_batch3.py` tests (the original no-mutation contract) were
re-run unmodified and still pass.

### Files changed

- `apps/stores/demo_assets/rasti_mode_demo/scripts/build_inventory.py` — new (forensics tool).
- `apps/stores/demo_assets/rasti_mode_demo/scripts/select_and_process_media.py` — new (media selection/processing tool).
- `apps/stores/demo_assets/rasti_mode_demo/products/FSH-001…FSH-050/0{1,2,3}.webp` — new, 150 files.
- `apps/stores/demo_assets/rasti_mode_demo/selected_product_media_manifest.json` — new.
- `apps/stores/management/commands/seed_ready_template_fashion_demo.py` — fully rewritten catalog/content data and seeding logic (real media import, ShopSettings/public-domain provisioning, safe `--reset` MenuItem fix).
- `apps/stores/tests/test_seed_ready_template_fashion_demo_command.py` — fully rewritten for the new real-catalog contract.
- `apps/stores/tests/test_rasti_mode_demo_media_pipeline.py` — new (raw/manifest/media static tests).
- `apps/storefront_builder/services/template_preview_service.py` — additive real-screenshot resolver (Batch 3 code untouched).
- `apps/storefront_builder/management/commands/capture_ready_template_previews.py` — new (dev/build-time capture tool).
- `apps/storefront_builder/static/ready_template_previews/<key>/v1.webp` + `.meta.json` — new, 8 real captures + sidecars.
- `docs/qa_evidence/ready_template_previews/<key>/{home_mobile,listing_desktop,pdp_desktop}.jpg` — new, 24 QA-evidence captures.
- `apps/storefront_builder/views.py` — `storefront_template_gallery` resolves a real screenshot before falling back to the SVG.
- `apps/storefront_builder/templates/dashboard/storefront_builder/template_gallery.html` — `.tpl-thumb` branches on `thumbnail_kind`.
- `apps/storefront_builder/tests/test_ready_template_real_previews.py` — new.

### Testing

Ran and green: `test_rasti_mode_demo_media_pipeline.py` (18 tests, static
filesystem/manifest checks); `test_ready_template_real_previews.py` (19
tests, resolver + Gallery integration + capture-command safety);
`test_acceptance_batch3.py` re-run unmodified (15 tests, still green —
the pre-existing no-mutation/SVG contract). `test_seed_ready_template_
fashion_demo_command.py` (41 tests covering the full new real-catalog
contract) — see the final report for its concrete pass count. Broader
`apps.stores`/`apps.catalog`/`apps.content`/`apps.storefront_builder`
regression suites, `manage.py check`, `makemigrations --check --dry-run`,
and `git diff --check` results are recorded in the final report rather
than duplicated here.

### Known remaining limitations (explicit, not gaps to hide)

1. The 345 raw source images' third-party licensing provenance has not
   been independently verified, and several show visible real-brand
   trademarks (sneakers, handbag hardware). They remain strictly QA/demo
   internal material: never claimed copyright-free, never deployed to
   production, never served directly to the public storefront (only the
   processed, normalized `products/` copies are), and `QA_SOURCE_ASSETS.md`'s
   warnings are preserved verbatim. All 50 assigned brands are fictional —
   no real brand name is used or implied in any product title/description.
2. Every product's "second/third image" is a derived crop of its single
   real photo, not an independent real angle — disclosed explicitly in
   the manifest (`"derived": true` + a transformation description) per
   the mission's own fallback contract, not hidden as if it were a real
   second photograph.
3. The 8 real screenshots capture the canonical HOME page only, at one
   fixed desktop viewport (1440×1100) — matching the mission's own
   Gallery requirement (only the canonical HOME preview is required
   there); the 24 additional mobile/listing/PDP captures are QA evidence
   in `docs/qa_evidence/`, not wired into the Gallery.
4. The capture command leaves the demo Store published on whichever
   Template it processed last in a given run (currently `dark_digital`,
   the final key `list_ready_templates()` yields) — this has no effect on
   the Gallery (which reads static files, not the Store's live published
   state) and is a reasonable, disclosed side effect of a dev/build-only
   tool that intentionally cycles the *same* isolated demo Store through
   all 8 Templates.
