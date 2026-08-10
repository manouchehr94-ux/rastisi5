# Six New Families — Interactive Control Matrix

Statically inspected (source-level trace) — NOT Django-rendered, NOT
browser-tested. Each row lists: template path, visible condition,
destination/handler, server endpoint (if applicable), preview behavior,
public behavior, accessibility label, automated test, current status.

Legend for **Status**: `Source-implemented` (code exists, wired
correctly per source trace) · `Fixed this session` (a real gap was found
and corrected) · `Missing infrastructure` (feature has no backing model
anywhere in the codebase) · `NOT EXECUTED` (requires Django/browser to
verify, cannot be confirmed further here).

## Legend for shared context

* `hc` = `header_config` (per-Store dict, validated by
  `apps.storefront_builder.services.layout_service.validate_header_config`).
* `is_live_storefront` / `is_builder_preview` — mutually exclusive flags
  set by the renderer (`apps.storefront_builder.services.render_service`)
  distinguishing the live public page from the Builder's preview iframe.

---

## 1. Search

| Family | Template | Visible condition | Handler | Preview behavior | Public behavior | a11y | Test | Status |
|---|---|---|---|---|---|---|---|---|
| atlas_catalog | `.../atlas_catalog/header.html` | `hc.show_search` | `GET catalog:product-list?q=` | `disabled` input, `onsubmit="return false"` | live `<form>` submits | `aria-label="جستجو"` on submit button | `test_template_syntax_integrity.py` (aria-label check, header-level only) | Source-implemented |
| ava_fashion | `.../ava_fashion/header.html` | `hc.show_search` | same | same disabled pattern | same | icon-only button lacks a *visible* label but has icon + placeholder text; no explicit `aria-label` on the `<svg>` icon inside the search form (the search **input** itself has no `aria-label`, relies on `placeholder`) | none dedicated | Source-implemented; **placeholder-only labeling is a soft a11y gap** (not blocking, `placeholder` is not a substitute for `aria-label`/`<label>` per WCAG, but this matches the existing 5-family pattern — not new work introduced by the 6 families) |
| toranj_gifting | `.../toranj_gifting/header.html` | `hc.show_search` | same | same | same | same placeholder-only gap | none | Source-implemented (same soft gap) |
| sarv_stock | `.../sarv_stock/header.html` | `hc.show_search` | same | `disabled` icon button in preview | live search-mini form | `aria-label="جستجو"` on the submit button | none | Source-implemented |
| sepidar_handmade | `.../sepidar_handmade/header.html` | `hc.show_search` | same | preview correctly uses `<button type="button" disabled>` (valid) | live `<a href="{% url 'catalog:product-list' %}">` — **navigates to the listing page, not an inline search box** | `aria-label="جستجو"` | none | **Known Gap**: this is not an inline search input like the other 5 — it's a link to the product list. Functionally different from the `interactions.yaml` contract (`desktop: expand_or_dropdown_results_after_2_chars`). Documented, not fixed this session (scope: this session's mandate was stock/gift-wrap/tenant-isolation; flagging for the next pass) |
| zarrin_jewelry | `.../zarrin_jewelry/header.html` | `hc.show_search` | same `<a>` link pattern | same | same link-to-listing pattern | `aria-label="جستجو"` | none | Same known gap as sepidar_handmade |

**Known Gap (search-as-link, not inline expand/dropdown):** `sepidar_handmade` and `zarrin_jewelry` render search as a navigational link to `catalog:product-list`, not an inline expanding search box as `interactions.yaml`'s `header_search.desktop: expand_or_dropdown_results_after_2_chars` specifies. This is a real deviation from contract, not a decorative/dead control (the link works), but it does not match the specified interaction pattern. Not fixed in this session (out of the explicit stock/gift-wrap/tenant-isolation mandate) — flagged here rather than silently passed over.

(Correction: an earlier draft of this matrix incorrectly claimed `sepidar_handmade` used an invalid `disabled` attribute on an `<a>` tag. On re-inspection, the preview branch correctly uses a `<button type="button" disabled>`, not an anchor — this claim has been removed as inaccurate. The only real, confirmed gap for `sepidar_handmade`/`zarrin_jewelry` is the search-as-link-not-inline-box deviation noted above.)

---

## 2. Account

| Family | Handler | Preview behavior | Public (authenticated) | Public (anonymous) | a11y | Status |
|---|---|---|---|---|---|---|
| All 6 | `GET customers:account` / `@click="loginOpen = true"` (opens shared login modal, `templates/base.html`) | `disabled` button, `title="ورود در پیش‌نمایش غیرفعال است"` | Link to account page, shows `full_name` (atlas_catalog only — others just show the icon) | Button opens login modal | `aria-label="حساب من"` / `aria-label="ورود"` present on all 6 | Source-implemented, consistent with existing 5 families |

---

## 3. Wishlist

| Family | Header control | Product-card control | Product-page control | Handler | Preview | Public | a11y | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| atlas_catalog | `.ac-action-btn` (was missing, **fixed this session**) | none on card (`atlas_dense_card.html` has no wishlist icon) | `{% include "customers/partials/wishlist_button.html" %}` in gallery | `POST customers:wishlist-toggle` | disabled link | toggles, session-persisted, merges on login | `aria-label` present (fixed) | `test_wishlist_control_present_when_configured` | Fixed this session |
| ava_fashion | present | none | present | same | disabled | same | present | same | Source-implemented |
| toranj_gifting | `.tj-action-btn` (was missing, **fixed this session**) | none | present | same | disabled | same | present (fixed) | same | Fixed this session |
| sarv_stock | `.sv-action-btn` (was missing, **fixed this session**) | present — `sarv_stock_card.html` has a wishlist action | present | same | disabled | same | present (fixed) | same | Fixed this session |
| sepidar_handmade | `.sp-action-btn` (was missing, **fixed this session**) | none | present | same | disabled | same | present (fixed) | same | Fixed this session |
| zarrin_jewelry | present | none | present | same | disabled | same | present | same | Source-implemented |

**Cross-family gap (documented, not newly introduced):** none of the 6 new families' product **cards** show a wishlist toggle except `sarv_stock` — this matches the existing 5-family pattern where wishlist is primarily a product-page/header feature, so it is not treated as a regression.

---

## 4. Comparison ("Compare")

| Family | Status |
|---|---|
| All 6 | **Missing infrastructure** — no `Compare`/`CompareList` model, view, URL, or template fragment exists anywhere in the repository (confirmed via repo-wide grep). This is a platform-wide gap, not specific to these 6 families; the 5 existing families also lack it. Cannot be implemented as part of this narrow session without a new migration + model + service + UI across all 11 families, which is a distinct scope of work. |

---

## 5. Cart / Mini-cart

| Family | Header cart control | Mini-cart / preview mode | Add-to-cart (card) | Add-to-cart (PDP) | Server endpoint | Stock enforcement | Test | Status |
|---|---|---|---|---|---|---|---|---|
| atlas_catalog | `.ac-action-btn` w/ badge | `count_link` (default; only `heritage_premium` uses `mini_cart`) | `atlas_dense_card.html` — `hx-post="cart:add"` | `.ac-btn-add`, gated `:disabled="!canAddToCart"` | `POST cart:add` | **Fixed this session** — see §Stock Enforcement below | `test_cart_gift_wrap.py`, `test_cart_security.py`, `test_cart_views.py` | Fixed this session (shared logic) |
| ava_fashion | present | count_link | `ava_fashion_card.html` | `.av-btn-add` | same | same | same | same |
| toranj_gifting | present | count_link | `toranj_gift_card.html` — gated `{% if product.stock > 0 %}` | `.tj-btn-add` + gift-wrap checkbox (fixed this session, see §7) | same | same | same | same |
| sarv_stock | present | count_link | `sarv_stock_card.html` — gated `{% if product.stock > 0 %}` | `.sv-btn-add` | same | same | same | same |
| sepidar_handmade | present | count_link | none found (`sepidar_editorial_card.html` — needs separate audit, not part of stock-enforcement fix) | `.sp-btn-add` | same | same | same | same |
| zarrin_jewelry | present | count_link | `zarrin_minimal_card.html` | `.zr-btn-add` | same | same | same | same |

### Stock enforcement fix (applies to all 11 families identically — shared `apps/cart` logic)

Before this session, `cart_add` (`apps/cart/views.py`) never validated stock at add-time; only `cart_item_update` clamped quantity, and it silently skipped clamping when stock was exactly zero. Fixed:

* `apps/cart/services/cart_service.py::add_item_to_cart` now re-reads `Product`/`ProductVariant` under `select_for_update()`, rejects with `UnavailableStockError` when: quantity is not a positive int; the product/variant is not active+in-stock; requested+existing cart quantity exceeds available stock.
* `apps/cart/views.py::cart_add` catches `UnavailableStockError` and returns an error toast (`type: "err"`) instead of silently succeeding or clamping.
* `apps/cart/views.py::cart_item_update` and `apps/orders/views.py::checkout_item_update` now delete the line and toast an error when stock has dropped to zero since the item was added, instead of leaving an invalid quantity untouched.
* Real Django tests added: `apps/cart/tests/test_cart_service.py::AddItemToCartStockEnforcementTests` (12 tests), `apps/cart/tests/test_cart_views.py` (8 new tests), `apps/cart/tests/test_cart_security.py` (7 new tests) — all `NOT EXECUTED` in this sandbox (no Django), written for the owner's Django-capable environment.

---

## 6. Navigation / Mobile drawer

| Family | Desktop nav | Mobile drawer trigger | a11y | Status |
|---|---|---|---|---|
| atlas_catalog | `.ac-catnav` row 3 | `.h-btn.burger`, `aria-label="منو"` | present | Source-implemented |
| ava_fashion | `.av-catnav` | same | present | Source-implemented |
| toranj_gifting | `.tj-catnav` (two-row) | same | present | Source-implemented |
| sarv_stock | `.sv-nav` inline in header | same | present | Source-implemented |
| sepidar_handmade | `.sp-nav` inside capsule | same | present | Source-implemented |
| zarrin_jewelry | `.zr-nav` centered | same | present | Source-implemented |

---

## 7. Sliders / Carousels / Gallery / Thumbnails / Zoom / Video / Share

| Control | Families with it | Handler | Status |
|---|---|---|---|
| Product gallery (main image + thumbnails) | All 6 | Alpine `variantSelector.activeSlide`, `@click="activeSlide = N"` | Source-implemented, identical pattern to base template |
| Zoom (`desktop_only_pointer_zoom_plus_lightbox` per interactions.yaml) | **None of the 6** | — | **Missing** — no zoom/lightbox interaction found in any of the 6 new product-page templates, nor in the 5 existing ones (repo-wide grep for `zoom`/`lightbox` in `product_pages/*.html` returns nothing). Pre-existing, cross-cutting gap, not introduced by this work. |
| Video (`play_button_over_thumbnail`) | **Was missing on all 6 — fixed this session** | `{% include "catalog/partials/product_videos_block.html" %}` (new shared partial, extracted from the pattern already used by `artisan_editorial`/`heritage_premium`/`modern_fashion`/`nordic_living`/`vibrant_catalog`/base `product_detail.html`) | **Fixed this session** — all 6 new families were completely missing the product-video block; a merchant-uploaded video would never render for any of these 6 families even though the data (`product_videos`) was already being computed and passed into context. Confirmed via `_product_video_render_data()` in `apps/catalog/views.py` — the data was always there, only the template block was absent. |
| Story rail (home page, not PDP) | `ava_fashion` (`story_rail_required: true`), `toranj_gifting` (`story_rail` in `default_section_keys`) | `storefront_builder` `story_rail` section type, `StoryRailItem` model | Source-implemented (existing `story_rail` section infrastructure, not per-family new code) |
| Share (social) | `zarrin_jewelry` only | `.zr-share` — Telegram/WhatsApp links + `navigator.clipboard.writeText` | Source-implemented for zarrin_jewelry; **absent from the other 5 new families** — not in `interactions.yaml`'s baseline `interactions:` block either, so this is family-specific by design, not a gap |

---

## 8. Variants / Quantity / Add to cart

See dedicated trace: `docs/reports/SIX_FAMILIES_VARIANT_WIRING_TRACE.md`. Summary: image/thumbnails/price/old-price/availability/qty-limit/add-to-cart-eligibility/submitted-variant-id were all already correctly wired in all 6 families; **SKU was missing in all 6 (and all 5 existing families) — fixed this session for the 6 new families** by adding a `current.sku`-bound line to each product page.

---

## 9. Tabs / FAQ / Size guide / Story rail / Add-ons

| Control | Families | Status |
|---|---|---|
| Tabs (spec/description/reviews) | All 6 | Source-implemented, `x-data="{ tab: '...' }"` pattern |
| FAQ accordion | `sarv_stock`, `zarrin_jewelry` (per `faq_accordion_required_when_configured` contract) | Source-implemented — static demo Q&A, **not merchant-configurable** (hardcoded questions, not backed by the `FAQ`/`content.faqs` model referenced in `dynamic-data-mapping.yaml`'s `faqs: content.faqs.published` binding). **Documented gap**: these are decorative placeholder FAQs, not wired to real merchant-entered FAQ content — a merchant cannot edit these questions. Not fixed this session (would require wiring `zarrin_jewelry`/`sarv_stock` product pages to the real `content.faqs` binding, a distinct scope). |
| Size guide | All 6 (was missing on 4 of 6 — **fixed prior session**, confirmed present in this session's re-audit) | `{% include "catalog/partials/size_guide.html" %}` inside the variant-selector form | Fixed (prior session), re-confirmed present this session |
| Story rail | `ava_fashion`, `toranj_gifting` (home page section, not PDP) | Shared `storefront_builder` section infrastructure | Source-implemented |
| Gift-wrap add-on | `toranj_gifting` only | **Implemented end-to-end this session** — see §10 | Fixed this session (real implementation, not removal) |

**Correction on the hardcoded FAQ finding:** this is a newly-identified gap during this session's audit (the FAQ accordions in `sarv_stock.html`/`zarrin_jewelry.html` contain static Persian Q&A text hardcoded directly in the template, e.g. "🚚 زمان ارسال چقدر است؟" / "معمولاً ۲ تا ۵ روز کاری." — not `{% for %}` over any queryset). This is flagged here per the explicit instruction not to treat presence of a `<button>`/Alpine directive as proof of working behavior; it is a decorative-but-functional control (it does toggle open/closed correctly) but is not merchant-editable content as the `dynamic-data-mapping.yaml` contract implies. Not fixed in this session — out of the explicit stock/gift-wrap/tenant-isolation mandate; documented rather than silently passed over.

---

## 10. Gift wrap (toranj_gifting — `optional_addon_checkbox_updates_total`)

**Implemented end-to-end this session** (previously: decorative checkbox with zero backend wiring, removed entirely in a prior session; now: real merchant-configurable feature).

| Layer | Implementation | File |
|---|---|---|
| Merchant-configurable availability/price | `ShopSettings.gift_wrap_available` (bool), `ShopSettings.gift_wrap_price` (Decimal) | `apps/core/models.py` + migration `apps/core/migrations/0016_shopsettings_gift_wrap.py` |
| Merchant settings UI | `GiftWrapSettingsForm`, `dashboard:settings-gift-wrap` view, rendered in the Finance settings section | `apps/dashboard/forms.py`, `apps/dashboard/views.py`, `apps/dashboard/templates/dashboard/partials/settings_finance.html` |
| Customer selection (checkbox) | `<input type="checkbox" name="gift_wrap" x-model="giftWrapSelected">`, only rendered `{% if gift_wrap_available %}` | `apps/catalog/templates/catalog/partials/product_pages/toranj_gifting.html` |
| Live displayed-total update | `displayTotalWithGiftWrap` computed property added to the shared `variantSelector` Alpine component | `apps/catalog/templates/catalog/product_detail.html` |
| Server-side validation | `apps.cart.services.gift_wrap_service.resolve_gift_wrap_selection()` — re-derives availability/price from `ShopSettings`, never trusts client-supplied price; a Store that has not enabled it silently ignores the client's request | `apps/cart/services/gift_wrap_service.py` |
| Persisted cart-line selection | `CartItem.gift_wrap_selected` / `CartItem.gift_wrap_unit_price` | `apps/cart/models.py` + migration `apps/cart/migrations/0007_cartitem_gift_wrap.py` |
| Cart display / live total | `cart_totals()["gift_wrap_total"]`, rendered in `cart_page_body.html` and `checkout_body.html` | `apps/cart/services/pricing.py` |
| Order-line persistence | `OrderItem.gift_wrap_selected` / `OrderItem.gift_wrap_unit_price`, snapshotted at order-creation time (immune to later `ShopSettings` price changes) | `apps/orders/models.py` + migration `apps/orders/migrations/0010_orderitem_gift_wrap.py`, `apps/orders/services/order_service.py` |
| Protection against forged client price | Server always resolves price from `ShopSettings`, never reads `request.POST["gift_wrap_price"]` even if present | `apps/cart/services/cart_service.py::add_item_to_cart` |
| Automated tests | `apps/cart/tests/test_gift_wrap.py` (19 tests: service, cart-service, pricing, view, order-persistence layers), `apps/dashboard/tests/test_settings_views.py::SettingsGiftWrapViewTests` (4 tests) | Written, `NOT EXECUTED` in this sandbox (no Django) |

---

## Summary of fixes made this session (beyond stock enforcement, already covered in the report)

1. **Gift wrap implemented end-to-end** (was previously removed as "decorative"; now real, merchant-gated, server-validated feature). See §10.
2. **Missing SKU binding added to all 6 new product pages** (`current.sku`, previously entirely absent from all 11 families' family-specific templates). See `SIX_FAMILIES_VARIANT_WIRING_TRACE.md`.
3. **Missing product-video block added to all 6 new product pages** — extracted into a shared `product_videos_block.html` partial and included in all 6 (previously present in the 5 existing families and the base template, but completely absent from all 6 new ones).
4. **Documented, not fixed this session** (flagged per the explicit "no silently passed over" instruction):
   - `sepidar_handmade`/`zarrin_jewelry` search-as-link instead of inline expand/dropdown (contract deviation).
   - Hardcoded, non-merchant-editable FAQ text in `sarv_stock`/`zarrin_jewelry`.
   - No zoom/lightbox anywhere (pre-existing, all 11 families).
   - No `Compare` feature anywhere (pre-existing, platform-wide, no model).

None of the items in bullet 4 were silently treated as "working" — they are explicitly called out here as known, unresolved gaps.
