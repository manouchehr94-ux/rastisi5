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
