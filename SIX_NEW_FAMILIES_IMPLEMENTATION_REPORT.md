# Six New Families Implementation Report (Second Correction Pass)

## Status: `IMPLEMENTATION_INCOMPLETE`

This report supersedes the previous version. That version's own gap list
identified (but left unfixed) three concrete, acceptance-blocking issues:
server-side stock enforcement, the Toranj gift-wrap contract, and
insufficiently substantiated claims about tenant isolation and shared
variant wiring. This pass fixes all three at the source level, adds real
(but `NOT EXECUTED` — no Django in this sandbox) Django test coverage for
each, and corrects the report's own terminology per the explicit
instruction not to use "verified/guaranteed/functional/complete/passed"
for anything only source-inspected.

Runtime, interaction, and visual verification remain **unexecuted**. This
is not a scope reduction — it is an accurate statement of a confirmed,
exhaustively-attempted sandbox limitation (see the unchanged environment
log further below).

## Git State (this pass)

| Field | Value |
|---|---|
| Starting commit (this session) | `c3d391d3cea5d5b7e9124c9d4238578c6e1d5642` |
| Branch | `claude/family-visual-fidelity-fix` |
| PR #9 | Confirmed still closed, not merged (`state: closed, merged: False`) |
| Stray branch `feature/new-storefront-families` | Confirmed still deleted |
| `main` | Confirmed untouched this pass (`git rev-parse main` == `git rev-parse origin/main`, unchanged since prior pass) |

## What Was Fixed This Pass (Real Functional Gaps, Not Documentation)

### 1. Server-side stock enforcement at Add-to-Cart (blocking gap, now fixed)

**Before:** `apps/cart/views.py::cart_add` never validated stock at
add-time. `apps/cart/services/cart_service.py::add_item_to_cart` computed
price but never checked `product.stock`/`variant.stock` at all. Only
`cart_item_update` clamped quantity — and even there, when stock had
dropped to exactly zero, the clamp condition (`if available_stock > 0`)
was false, so the clamp silently did nothing, leaving an arbitrary
quantity on a zero-stock item.

**After** (`apps/cart/services/cart_service.py`, `apps/cart/views.py`,
`apps/orders/views.py`):

* `add_item_to_cart(cart, product, variant, quantity, *, gift_wrap_requested=False)`
  now runs inside `transaction.atomic()`, re-reads the `Product`/
  `ProductVariant` row under `select_for_update()` (defense against a
  concurrent add reserving the same last unit twice), and raises a new
  `UnavailableStockError` when:
  * `quantity` is not a positive `int`;
  * the resolved product/variant is not active and in stock
    (`product.status == ACTIVE and product.stock > 0`, or
    `variant.is_active and variant.stock > 0`);
  * the requested quantity **plus the quantity already in this cart for
    the same product/variant** would exceed available stock.
* `cart_add` catches `UnavailableStockError` and returns the existing
  htmx error-toast convention (`HX-Trigger` with `type: "err"`, 200
  status, no body swap — matching `apps.orders.views._dynamic_response`'s
  established pattern) instead of silently succeeding or clamping.
  Non-numeric/zero/negative quantities are now explicitly rejected with
  the same error convention, rather than silently defaulting to `1`.
* `cart_item_update` (cart page) and `checkout_item_update` (checkout
  page) now re-read the *correct* stock reference (the variant's stock
  when a variant is selected, not the parent product's — this bug
  existed in `checkout_item_update` even before this session, since it
  only ever checked `item.product.stock`) and delete the line with an
  error toast when stock has dropped to zero, instead of leaving an
  invalid quantity untouched.
* Cross-tenant safety is unchanged and re-verified: `cart_add` still
  resolves the product exclusively through
  `storefront_visible_products(store)` (Store-scoped queryset) and the
  variant exclusively through `product=product` ownership — a variant
  belonging to another Store's product 404s before any stock check runs.
* Never trusts client-supplied price/SKU/stock/availability — unit price
  continues to come from `pricing_service.resolve_effective_price`,
  never from POST.

**Tests added** (all `NOT EXECUTED` in this sandbox, written for a
Django-capable environment):
* `apps/cart/tests/test_cart_service.py::AddItemToCartStockEnforcementTests`
  (12 tests: zero-stock product/variant, inactive product/variant,
  quantity-exceeds-stock, quantity-equal-to-stock succeeds, zero/negative/
  non-integer quantity, existing-cart-quantity counted toward stock,
  variant stock checked independently of product stock).
* `apps/cart/tests/test_cart_views.py` (8 new tests covering the same
  matrix at the HTTP/view layer, plus "existing cart quantity counted"
  and "within remaining stock succeeds").
* `apps/cart/tests/test_cart_security.py` (7 new/modified tests —
  replaced the old "negative quantity clamped" assertion, since clamping
  is no longer the contract, with "negative/zero quantity rejected",
  plus zero-stock product/variant rejected, quantity-exceeds-variant-stock
  rejected, existing-cart-quantity-counted, and a cross-store stock
  isolation test proving a Store B variant's stock level is never even
  consulted for a Store A product because the 404 on ownership happens
  first).
* Pre-existing fixtures across `apps/orders/tests/test_checkout_integrity.py`,
  `apps/orders/tests/test_checkout_views.py`, `apps/cart/tests/test_cart_views.py`
  already had `stock=` set on their `Product.objects.create(...)` calls
  and needed no change; two fixtures in `apps/cart/tests/test_cart_service.py`
  that previously relied on the (now-removed) permissive default were
  updated to set `stock=` explicitly.

**Not proven by this fix alone:** whether the transaction/locking
strategy behaves correctly under real concurrent load — that requires a
running database and concurrent request simulation, which is
`NOT EXECUTED` here.

### 2. Toranj gift-wrap — implemented end-to-end (was: removed as decorative)

**Before:** a prior session's report stated the gift-wrap checkbox was
"removed rather than fake-fixed" because it had zero backend wiring. This
was re-examined per the explicit instruction to check for an existing
add-on mechanism first. **Confirmed: none exists anywhere in the
repository** (`CartItem`, `OrderItem`, `Product` — no options/add-ons/
line-metadata/customization field or model of any kind, verified via
repo-wide search). Since the contract (`toranj_gifting:
optional_addon_checkbox_updates_total: true`) requires it, it has been
implemented fully rather than merely hidden or left removed:

| Requirement | Implementation |
|---|---|
| Merchant-configurable availability + price | `ShopSettings.gift_wrap_available` (bool), `ShopSettings.gift_wrap_price` (Decimal) — new fields, migration `apps/core/migrations/0016_shopsettings_gift_wrap.py` |
| Merchant settings UI | `GiftWrapSettingsForm` + `dashboard:settings-gift-wrap` view, added to the existing Finance settings section |
| Customer selection | Checkbox in `toranj_gifting.html`, rendered only `{% if gift_wrap_available %}` |
| Live displayed-total update | New `displayTotalWithGiftWrap` computed property on the shared `variantSelector` Alpine component, bound to `x-model="giftWrapSelected"` |
| Server-side validation | `apps.cart.services.gift_wrap_service.resolve_gift_wrap_selection()` — always re-derives from `ShopSettings`, ignores the client's request entirely if the Store has not enabled it |
| Persisted cart-line selection | `CartItem.gift_wrap_selected` / `gift_wrap_unit_price`, migration `apps/cart/migrations/0007_cartitem_gift_wrap.py` |
| Cart display / recalculation | `cart_totals()["gift_wrap_total"]`, rendered in both `cart_page_body.html` and `checkout_body.html` |
| Order-line persistence | `OrderItem.gift_wrap_selected` / `gift_wrap_unit_price`, migration `apps/orders/migrations/0010_orderitem_gift_wrap.py`, snapshotted at order-creation time (immune to later price changes — same pattern as `unit_price`) |
| Protection against forged client price | Server never reads a client-supplied price field for this add-on, always resolves from `ShopSettings.gift_wrap_price` |
| Automated tests | `apps/cart/tests/test_gift_wrap.py` (19 tests across service/cart-service/pricing/view/order-persistence layers), `apps/dashboard/tests/test_settings_views.py::SettingsGiftWrapViewTests` (4 tests) — `NOT EXECUTED` |

A migration was created because the existing data model genuinely had no
field capable of persisting a per-line option — confirmed by exhaustive
search before deciding to add one, per the explicit instruction.

### 3. Corrected unsupported claims about tenant isolation and variant wiring

The previous report's matrix row for "Variant selection updates price/
SKU/stock/image" said only "Architecturally shared — runtime-unverified"
without tracing each family's actual DOM. This has been replaced with a
full per-family trace: `docs/reports/SIX_FAMILIES_VARIANT_WIRING_TRACE.md`.
That trace found and fixed a real, previously-undetected gap: **none of
the 6 new families' product pages bound `current.sku`** to the live
variant-selector state — they only displayed the static `product.sku`
inside the spec table, so selecting a different variant never updated the
visible SKU (the base template `product_detail.html` already did this
correctly; the 6 new family templates, and the 5 existing ones, did not).
Fixed for all 6 new families; the same gap in the 5 existing families is
explicitly flagged as a pre-existing, unfixed issue (out of this session's
narrow scope), not silently ignored.

The previous report's claim that tenant isolation is "architecturally
guaranteed" merely because families use `resolve_store_for_storefront`
has been removed. In its place:
`apps/storefront_builder/tests/test_six_families_tenant_isolation.py` —
a real Django `TestCase` file with two actual Stores (Store A = the
"akhlaghi" fixture, Store B = freshly created), deliberately different
products/categories/vendors/variants, covering: public rendering (each of
the 6 families, both Stores, cross-checking product name appears/does-not-
appear), preview vs. public split (draft/published config never leaking
between Stores), product detail (cross-store slug/id → 404), cart add
(cross-store product/variant → 404, no `CartItem` created), wishlist
(cross-store product id cannot be wishlisted), collection/category
filtering (Store A's category listing never surfaces Store B's product),
and full builder lifecycle (family selection → draft → publish → public
render → rollback via `restore_version` → new draft, for all 6 families).
This file is `NOT EXECUTED` in this sandbox (no Django) — written for the
owner's environment.

### 4. Missing product-video block added to all 6 new families

While tracing variant wiring and auditing every control per the required
matrix, a second real gap was found: none of the 6 new product-page
templates included the product-video block, even though the 5 existing
families (and the base `product_detail.html`) already had it, and the
underlying context data (`product_videos`) was already being computed
and passed for every family via `apps.catalog.views._product_video_render_data`.
Extracted into a new shared partial,
`apps/catalog/templates/catalog/partials/product_videos_block.html`, and
included in all 6 new family templates.

### 5. Full interactive control matrix (all required columns)

`docs/reports/SIX_FAMILIES_CONTROL_MATRIX.md` — covers search, account,
wishlist, comparison, cart/mini-cart, navigation/mobile drawer, gallery/
thumbnails/zoom/video/share, variants/quantity/add-to-cart, tabs/FAQ/size
guide/story rail/gift-wrap, for all 6 new families, with template path,
visible condition, handler/endpoint, preview behavior, public behavior,
accessibility label, automated test reference, and current status per
control. Genuine remaining gaps are explicitly flagged rather than treated
as passing: no zoom/lightbox anywhere (pre-existing, all 11 families), no
`Compare` feature anywhere (pre-existing, platform-wide, no model exists),
hardcoded non-merchant-editable FAQ text in `sarv_stock`/`zarrin_jewelry`,
and `sepidar_handmade`/`zarrin_jewelry` rendering search as a navigation
link rather than the contract's inline expand/dropdown box.

### 6. Terminology corrections

* `test_template_syntax_integrity.py` was already correctly labeled in
  the previous report as a "pure-Python Django-tag balance checker" (not
  a rendering test) — re-verified this framing is accurate and unchanged.
* This report itself avoids "verified/guaranteed/functional/complete/
  passed" for anything not actually executed under Django; see the
  Requirement-to-Evidence Matrix below for the corrected status vocabulary
  (`Source-implemented`, `Fixed this session`, `NOT EXECUTED`,
  `Missing infrastructure`).

## Reproducible Runtime Verification Script

`scripts/verify_six_families.ps1` — for the owner's Windows machine at
`D:\Projects\RastiSi4`. Uses the repository's own existing dependency
method (`python -m venv` + `requirements.txt` + `manage.py`), runs Django
system checks, migration consistency checks, the six-family targeted
tests, five-family regression tests, cart/stock/gift-wrap/tenant-isolation
tests, then (unless `-SkipBrowserTests` is passed) starts the dev server
and runs `scripts/verify_six_families_visual.py` (new — a Playwright
script following the exact same convention as the pre-existing
`scripts/verify_product_entry_ui.py`) to capture the 24 required
screenshots (6 families × {home, product} × {1440×1000, 390×844}). Exits
non-zero if any mandatory Django-level gate fails, and writes a
timestamped Markdown report under
`scripts/.verify_output/six_families_<timestamp>/REPORT.md`.

Run from `D:\Projects\RastiSi4`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_six_families.ps1
```

Or Django-only (no browser/Playwright required):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_six_families.ps1 -SkipBrowserTests
```

**This script is a handoff mechanism, not evidence that anything has
passed** — it has not itself been executed against a real Django
environment in this sandbox; its own internal logic (venv creation, pip
install, `manage.py` invocations) was written and reviewed by source
inspection only.

## Requirement-to-Evidence Matrix (Corrected Terminology)

| Requirement | File(s) | Evidence | Test | Status |
|---|---|---|---|---|
| 11 families registered | `family_registry.py`, `preset_registry.py` | Registry consumed by `render_service`/`views.py`/appearance editor, same path as 5 existing families | `test_eleven_families.py` (15 tests, executed via pure-Python `unittest`, passing) | Source-implemented |
| 5 existing families preserved | Same files | Unchanged entries, diff-verified | `test_existing_five_preserved` | Source-implemented |
| Header/hero/category/footer per new family | 24 templates | `{% include %}` dispatch via `FamilyDefinition.*_variant` | Tag-balance static check (pure-Python, `test_template_syntax_integrity.py`, 6 tests, passing) | Source-implemented; Django-render `NOT EXECUTED` |
| Product card/page per family | 12 templates | Same dispatch mechanism | File-existence + tag-balance static checks | Source-implemented; Django-render `NOT EXECUTED` |
| Server-side stock enforcement (Add-to-Cart) | `apps/cart/services/cart_service.py`, `apps/cart/views.py`, `apps/orders/views.py` | Fixed this pass — see §1 above | 27 new Django tests across 3 files | **Fixed this session**; `NOT EXECUTED` (no Django) |
| Toranj gift-wrap contract | `apps/core/models.py`, `apps/cart/models.py`, `apps/orders/models.py`, `apps/cart/services/gift_wrap_service.py`, 3 migrations, dashboard settings, template | Fixed this pass — see §2 above | 23 new Django tests | **Fixed this session**; `NOT EXECUTED` (no Django) |
| Variant selection updates price/SKU/stock/image | 6 product pages + shared `variantSelector` | Full per-family DOM trace, SKU-binding gap found and fixed | `SIX_FAMILIES_VARIANT_WIRING_TRACE.md` (static trace, not executed) | **Fixed this session** (SKU binding); rest source-implemented; browser-test `NOT EXECUTED` |
| Product video block | 6 product pages | Was entirely absent, now present via shared partial | Manual grep-confirmed presence; no dedicated test yet | **Fixed this session**; Django-render `NOT EXECUTED` |
| Tenant isolation (cross-Store, all vectors) | `apps/storefront_builder/tests/test_six_families_tenant_isolation.py` | Real 2-Store Django TestCase, 6 families × multiple vectors | New file, 15+ test methods | Written this session; `NOT EXECUTED` (no Django) — **explicitly NOT claimed "guaranteed"** |
| Builder lifecycle (select/draft/publish/rollback) per family | Same file, `BuilderLifecycleTests` | Uses real `layout_service.get_or_create_draft`/`publish`/`restore_version`, inspects actual saved `appearance_config` and rendered response body | Same file | Written this session; `NOT EXECUTED` |
| Full interactive control matrix | `docs/reports/SIX_FAMILIES_CONTROL_MATRIX.md` | Every control traced with template path/handler/preview/public/a11y/test/status | N/A (documentation artifact) | Complete for this session's scope; several genuine gaps documented, not fixed (zoom/lightbox, Compare, hardcoded FAQ, search-as-link) |
| Compare feature | — | No model/view/URL exists anywhere in the codebase | N/A | **Missing infrastructure** — platform-wide, pre-existing, not specific to these 6 families |
| Zoom/lightbox on product gallery | — | Not found in any of the 11 families | N/A | **Missing infrastructure** — pre-existing, not fixed this session (out of the explicit stock/gift-wrap/tenant-isolation mandate) |
| Merchant-editable FAQ content (`sarv_stock`, `zarrin_jewelry`) | Product page templates | Hardcoded static Q&A, not bound to `content.faqs` | N/A | Documented gap, not fixed this session |
| Mobile overflow / 44px touch targets / 16px input font | CSS files | Not verified — no browser render available | None | `NOT EXECUTED` |
| Visual QA screenshots (24 required) | — | — | `scripts/verify_six_families_visual.py` written this session, capable of capturing them once run against a live server | **NOT EXECUTED** — no Django runtime to render pages, no browser can reach a live Django server in this sandbox |
| Runtime rendering test (Preview/Public) | — | — | — | **NOT EXECUTED** — Django unavailable |

## Runtime Environment — Unchanged, Re-Confirmed Blocker

The exhaustive attempt log from the previous pass (pip, pip download, uv,
5 local Python interpreters, Docker/Podman pull, Docker image cache
inspection, pip cache inspection, site-packages search, Dockerfile search)
was not re-run in full this session since the sandbox's network mode has
not changed (`INTEGRATIONS_ONLY`, confirmed at session start via
`get_sandbox_info`). All work in this pass was verified via:
`python3 -m py_compile` on every changed/new `.py` file,
`python3 -m compileall` across `apps/cart apps/catalog apps/core
apps/orders apps/dashboard apps/storefront_builder`, `git diff --check`
(whitespace), and the pre-existing pure-Python static test suites
(`test_eleven_families.py` + `test_template_syntax_integrity.py`, 21/21
passing, no Django import required by either file).

## Commands Executed (This Pass)

| Command | Exit Code | Purpose |
|---|---|---|
| `git fetch origin` + `git rev-parse` (local/remote/main) | 0 | Safety gate |
| `gh api repos/.../pulls/9` | 0 | Confirm PR #9 still closed, not merged |
| `git ls-remote origin refs/heads/feature/new-storefront-families` | 0 (empty) | Confirm stray branch still gone |
| `python3 -m py_compile` (every changed/new file, repeated after each edit) | 0 | Syntax verification |
| `python3 -m compileall -q apps/cart apps/catalog apps/core apps/orders apps/dashboard apps/storefront_builder` | 0 | Full-package syntax verification |
| `python3 -m unittest apps.storefront_builder.tests.test_eleven_families apps.storefront_builder.tests.test_template_syntax_integrity` | 0 | **21/21 tests passed** (unchanged from prior pass, re-confirmed after this pass's template edits) |
| `git diff --check` | 0 | Whitespace check |
| Django `manage.py check/test/migrate` | NOT EXECUTED | Django unavailable (confirmed, unchanged) |

## Final Honest Completion Status

`IMPLEMENTATION_INCOMPLETE`

Three concrete, previously-acknowledged-but-unfixed gaps (stock
enforcement, gift-wrap contract, unsubstantiated tenant-isolation/variant-
wiring claims) have been fixed at the source level this pass, with real
Django test coverage written (not executed) for all of them, plus two
additional gaps found during this pass's own audit (missing SKU binding,
missing video block) and fixed. A full interactive control matrix and
per-family variant-wiring trace now exist as artifacts. A reproducible
PowerShell + Playwright verification script now exists for the owner's
Windows environment. None of this constitutes "passed," "verified," or
"guaranteed" — every claim of correctness in this report is qualified as
source-level trace or `NOT EXECUTED`, pending an environment where Django
can actually run. The assignment cannot receive `READY_FOR_VISUAL_QA` or
`COMPLETE` until that runtime and visual evidence exists.
