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
- **Ending SHA:** _(recorded after commit, see below)_

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
