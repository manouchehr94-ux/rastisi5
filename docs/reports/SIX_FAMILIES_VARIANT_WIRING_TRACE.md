# Six New Families — Variant Selector DOM Wiring Trace

Source-level trace only (statically inspected — file paths and line-level
evidence below). Not Django-rendered, not browser-tested. Each row
documents where in the actual per-family template a given
`variantSelector` Alpine property is bound, or notes its absence.

Shared component: `Alpine.data('variantSelector', ...)` defined once in
`apps/catalog/templates/catalog/product_detail.html` (lines ~292-415).
Every family's product page (`{% include SHOP_FAMILY.product_page_variant %}`)
instantiates it with the SAME two JSON payloads
(`variant_selector`/`product_price_json`, both built server-side per
request in `apps.catalog.views.build_product_detail_context`) — so the
*data* is always tenant-correct. This trace verifies each family's *own*
markup actually reads from the resulting Alpine state (rather than reading
static, non-reactive `product.*` fields that never change on selection).

| Alpine property | atlas_catalog | ava_fashion | toranj_gifting | sarv_stock | sepidar_handmade | zarrin_jewelry |
|---|---|---|---|---|---|---|
| Primary image (`updateGallery()` / `data-slide`) | Present — `x-show="activeSlide === N"` on `<img>`, same pattern as base | Present | Present | Present | Present | Present |
| Thumbnails | Present — `.ac-thumb` `@click="activeSlide = N"` | Present — `.av-thumb` | Present — `.tj-thumb` | Present — `.sv-thumb` | Present — `.sp-thumb` | Present — `.zr-thumb` |
| Current price (`displayPrice.price`) | Present — `.ac-price-now` | Present — `.av-price-current` | Present — `.tj-price-current` (uses `displayTotalWithGiftWrap`, a superset that includes gift wrap when selected) | Present — `.sv-price-now` | Present — `.sp-price-current` | Present — `.zr-price-current` |
| Old/compare price (`displayPrice.regular`) | Present — `.ac-price-old`, gated `x-show="displayPrice.savings > 0"` | Present — `.av-price-was` | Present — `.tj-price-was` | Present — `.sv-price-old` | Present — `.sp-price-was` | Present — `.zr-price-was` |
| SKU (`current.sku`) | **Was MISSING — fixed this session.** Added `.ac-sku-line` bound to `current.sku` | **Was MISSING — fixed.** Added `.av-sku-line` | **Was MISSING — fixed.** Added `.tj-sku-line` | **Was MISSING — fixed.** Added `.sv-sku-line` | **Was MISSING — fixed.** Added `.sp-sku-line` | **Was MISSING — fixed.** Added `.zr-sku-line` |
| Availability/stock text (`displayStock`) | Present — `.ac-stock` `x-if` block | Present — `.av-stock` | Present — `.tj-stock` | Present — `.sv-stock` | Present — `.sp-stock` | Present — `.zr-stock` |
| Quantity limit (`Math.min(Math.max(displayStock,1), qty+1)`) | Present — `.ac-qty` stepper | Present — `.av-qty` | Present — `.tj-qty` | Present — `.sv-qty` | Present — `.sp-qty` | Present — `.zr-qty` |
| Add-to-cart eligibility (`canAddToCart`, `:disabled`) | Present — `.ac-btn-add :disabled="!canAddToCart"` | Present — `.av-btn-add` | Present — `.tj-btn-add` | Present — `.sv-btn-add` | Present — `.sp-btn-add` | Present — `.zr-btn-add` |
| Submitted variant id (`current.variant_id` → hidden `variant_id` input) | Present — `<input type="hidden" name="variant_id" :value="current ? current.variant_id : ''">` | Present (identical pattern) | Present | Present | Present | Present |

## Finding fixed this session: missing live SKU binding

Before this session, **none of the 6 new family product pages** (nor the
existing 5) bound `current.sku` anywhere — they only rendered the static,
non-reactive `{{ product.sku }}` inside the spec table. Selecting a
different variant therefore never updated the displayed SKU on any of the
11 families, even though `storefront_variant_service._variant_payload()`
(`apps/catalog/services/storefront_variant_service.py:44-56`) has always
computed a per-variant `sku` field and the shared base template
(`product_detail.html`, `.sku-line`) already demonstrated the correct
binding. This has been added to all six new family templates (see the
`x-show="current && current.sku"` lines referenced in the table above).

**Not fixed in this pass** (out of the narrow "six new families" scope,
documented as a pre-existing, cross-cutting gap): the same missing binding
also affects the 5 existing families (`modern_fashion`, `heritage_premium`,
`artisan_editorial`, `vibrant_catalog`, `nordic_living`) — confirmed absent
via `grep_search` for `current.sku` across their product-page templates.

## Server-side guarantee that out-of-stock variants cannot be submitted

Regardless of what the client-side Alpine state shows or how the DOM is
manipulated:

* `apps/cart/views.py::cart_add` resolves the variant via
  `get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True)`
  — an inactive variant 404s unconditionally, independent of any
  client-supplied stock/price/availability field.
* `apps/cart/services/cart_service.py::add_item_to_cart` (this session's
  fix) re-reads `variant.stock` under `select_for_update()` and raises
  `UnavailableStockError` if `stock <= 0` or the requested+existing
  quantity would exceed it — this happens AFTER the `is_active` ownership
  check and BEFORE any `CartItem` row is created or updated.
* This means: manually editing the DOM to re-enable a disabled
  `:disabled="!canAddToCart"` button, or hand-crafting a `variant_id` that
  belongs to an out-of-stock variant, or POSTing directly with curl/fetch
  bypassing the Alpine component entirely, all still hit the same
  server-side checks — there is no code path where `add_item_to_cart` is
  called without first passing the `ProductVariant.objects.select_for_update()`
  + `is_purchasable` re-check.

This guarantee is **source-verified** (traced through the exact code
path) but **NOT Django-test-executed** in this sandbox — see
`apps/cart/tests/test_cart_security.py` and
`apps/cart/tests/test_cart_service.py` (`AddItemToCartStockEnforcementTests`)
for the corresponding real Django tests, marked `NOT EXECUTED` in the
implementation report pending a Django-capable environment.

## What this trace does NOT prove

* That the DOM actually re-renders correctly in a real browser (no browser
  runtime available in this sandbox).
* That Alpine's reactivity graph (`x-show`/`x-text`/`:disabled`) is wired
  without a typo that only manifests at runtime (static grep can miss
  subtle binding errors, e.g. a typo'd property name that Alpine would
  silently treat as `undefined`).
* Image/thumbnail swap timing, CSS transitions, or any visual behavior.

Real confidence requires the browser/E2E tests referenced in
`SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` (NOT EXECUTED in this sandbox).
