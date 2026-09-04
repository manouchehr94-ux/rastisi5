# Golden Reference Storefront — G2 Executable Plan (Search + Category + Product Listing)

**Date:** 2026-09-04
**Branch:** `golden/g2-catalog-browsing` (from G1 `c9b99de`)
**Authority:** `../specs/2026-09-04-golden-reference-storefront-design.md` (G1 identity) + this plan.
**Method:** subagent-driven TDD (RED → implement → GREEN), fresh reviewer, local commit per
independently-testable unit, persistent ledger, final whole-G2 review.
**Scope fence:** Search / Category / Product Listing only. **No G3 (Product Detail redesign)**,
no Cart/Checkout/Account/Orders, no Builder UX. No official-branch change. No force push.

> **Headline finding (reuse-first inventory, verified at this HEAD).** G2 is **largely already
> implemented and already wired into the Golden shell.** There is ONE unified view
> (`catalog:product-list`) that serves search / category / brand / listing; it renders through
> `storefront_shell.html` → the same universal Golden header/footer/bottom-nav as Home (via
> `build_universal_storefront_context`); it uses the single reusable product card; it is
> tenant-scoped and tested. **There is no legacy-shell leakage.** G2 is therefore a
> REUSE → WIRE → VERIFY → POLISH job, not a build. Only three genuine UX gaps remain.

---

## A. Verified current architecture (do not rebuild)

- **View / route:** `apps/catalog/views.py::product_list` at route `catalog:product-list`
  (`products/`). One code path for `?q=` (search), `?category=` (category), `?brand=`, price,
  `discounted`, `in_stock`, `sort`, `page`. Context via `build_product_listing_context` →
  `_filtered_products`. Page type = `SEARCH` if `q` else `LISTING`; always calls
  `build_universal_storefront_context`.
- **Shell:** `catalog/product_list.html` `{% extends "storefront_shell.html" %}`. When
  `uses_universal_shell` (always true for the published Golden store) the shared shell includes
  the same `header_variant_template` / `footer_variant_template` / `mobile_bottom_nav_template`
  Home uses. The Golden published layout already carries a `product_listing` section on both the
  `listing` and `search` pages (verified). **No shell work required.**
- **Filters (server/query + HTMX):** `q`, `category` (slug OR `parent__slug` → children),
  `brand`, `min_price`/`max_price`, `discounted=1`, `in_stock=1`. Reset = link to bare URL.
- **Sorting:** `LIST_SORT_OPTIONS` = newest / price_asc / price_desc / popular (`-sold_count`) /
  rating. Stable `order_by(field, "id")`.
- **Pagination:** Django `Paginator` (12/page), `?page=`, querystring preserved via
  `context["querystring"]`, HTMX `#product-results`. Not infinite scroll.
- **Product card:** single `catalog/partials/product_card.html` + `product_card_data` filter →
  links to `catalog:product-detail`. Same card as Golden Home.
- **Filter/results templates:** filter UI in
  `apps/storefront_builder/templates/storefront_builder/sections/product_listing.html`
  (variants `standard` + `sidebar_dense`; `<details class="plp-filters">` disclosure). Results +
  count + empty-state + pagination in `apps/catalog/templates/catalog/partials/product_list_results.html`.
- **Page template:** `apps/catalog/templates/catalog/product_list.html` — static breadcrumb
  "خانه › فروشگاه", no `<h1>` heading; loads `product_list.css`/`product_card.css`.
- **Tenant scoping:** `resolve_store_for_storefront` + `storefront_listing_products(store)`.
- **Tests:** `apps/catalog/tests/test_product_list_view.py`, `test_u5_listing_filter_search.py`.

Classification: Search **COMPLETE** · Listing **COMPLETE** · Filters **COMPLETE** (per-chip removal
**MISSING**) · Sorting **COMPLETE** · Pagination **COMPLETE** · Product-card **COMPLETE** · Shell
**COMPLETE (no leakage)** · Category **COMPLETE as a facet** but **MISSING** heading/breadcrumb context.

## B. The three genuine G2 gaps (the only implementation work)

1. **G2-a — Dynamic location context (breadcrumb + heading).** The page always shows the static
   "خانه › فروشگاه" breadcrumb and no `<h1>`. A customer in a category or on a search result can't
   tell where they are. **Fix:** derive a small, tenant-safe context (page title + breadcrumb
   trail) in `build_product_listing_context` from data the view already resolves
   (`query`, `selected_category` + `filter_categories`, `selected_brand` + `brands`), and render a
   dynamic breadcrumb + `<h1>` heading. Examples: category → "کتانی رانینگ" with breadcrumb
   خانه › فروشگاه › کتانی رانینگ (parent › child when a subcategory); search → heading
   "نتایج جستجو برای «کیف»"; brand → brand name; plain listing → "همه‌ی محصولات".
2. **G2-b — Visible, removable active-filter chips.** Only a global "حذف همه‌ی فیلترها" exists.
   **Fix:** render a chip row (inside `#product-results` so it updates with HTMX) listing each
   active filter (category, brand, price range, discounted, in_stock, q) as a chip with a
   remove-one link (a URL/`hx-get` that drops just that param, preserving the rest) plus the
   existing clear-all. Server/query canonical — no JS source of truth. Reuse `context["querystring"]`
   semantics; build per-chip "remove" querystrings in the context builder.
3. **G2-c — Mobile/responsive polish.** Verify at 390/768/1440 that the `<details>` filter
   disclosure is reachable, chips don't overflow badly, product grid is readable, and nothing is
   hidden behind the `five_item` bottom navigation (bottom padding/clearance). Polish CSS only in
   the existing `product_list.css` (and, if a token is needed, existing token CSS) — no parallel
   theme, no new card.

Everything else (Search, Sorting, Pagination, Product-card, Shell) is already correct; G2 tasks
for those are **verification + tests**, not new systems.

## C. TDD task breakdown (RED → GREEN → self-review → fresh reviewer → commit)

- **T3 (this doc)** — plan; committed first.
- **T4 Shell verification** — a behavior test asserting the published `listing` and `search`
  pages render the Golden shell (`marketplace_search_first` header, `premium_columns` footer,
  `five_item` bottom nav) and NOT the legacy base header/footer. (Verify-only; no code change
  expected.)
- **T5 Search experience** — tests: Persian `q` echoed in the filter input; a search heading
  "نتایج جستجو برای «…»"; count present; no-result empty state; clear/modify path. Implement
  heading as part of G2-a.
- **T6 Category experience** — tests: category heading + breadcrumb reflecting the selected
  category (parent › child for subcategory); count; subcategory options present; empty state;
  uses the Golden grid. Implement as G2-a.
- **T7 Filters + chips** — tests: each supported filter narrows results and is tenant-scoped;
  active-filter chips render for each active filter; remove-one drops only that param and
  preserves the rest; clear-all resets; stable URLs. Implement G2-b in the context builder +
  results partial.
- **T8 Sorting** — tests: each sort orders correctly and preserves the current filter/search/query
  state (querystring carries `sort`). (Verify; already backed.)
- **T9 Pagination** — tests: page navigation preserves query/filter/sort; count correct; stable
  ordering. (Verify; already backed.)
- **T10 Product card** — test: listing/search cards link to the existing `catalog:product-detail`
  route and show real Catalog truth; same partial as Home. (Verify.)
- **T11 Mobile polish** — CSS polish for chips/clearance; responsive tests where practical
  (existing `<details>` disclosure retained; a slide-in drawer is explicitly OUT unless the
  disclosure proves unusable).
- **T12 Browser QA** — desktop 1440 / tablet 768 / mobile 390 for search / category / listing /
  filters-visible / no-results; walk Home → header search → results → category → filtered/sorted
  → product link. Fix visible defects.
- **T13 Regression gate** — see §D.
- **T14 Whole-G2 review** — fresh reviewer; resolve CRITICAL/IMPORTANT; push backup branch.

## D. Verification gate (before G2 complete)

- New/updated G2 tests (heading/breadcrumb, chips remove-one/clear-all, search/category context).
- Neighboring: `test_product_list_view`, `test_u5_listing_filter_search`, public catalog view
  tests, renderer/shell (`test_public_homepage_integration`/`test_render_service`), product-card
  (`test_product_card_service`), store isolation (`test_store_isolation`).
- Golden G1 command tests (`test_apply_golden_reference_storefront_command`) — unchanged.
- A8 exact-50 (`test_a8_ready_template_catalog`), store-appearance shell
  (`test_u2a_global_header_system` / `test_u2b_global_footer_system`).
- `python manage.py check` · `makemigrations --check --dry-run` (expect **no** new migrations —
  G2 is presentation/query, no model changes) · `git diff --check`.
- Browser QA evidence captured.

## E. Guardrails / invariants

- Exactly 50 Ready Templates; one renderer; one product-card; one listing view. No new view,
  no second card, no category-merchandising model, no product-attribute facets (unless a later
  finding proves the existing architecture supports them cheaply), no infinite scroll, no new
  search index/autocomplete.
- No price/stock/SKU writes; no catalog IDs baked into settings; Catalog owns product truth;
  Commerce boundary intact; tenant isolation mandatory.
- Filter state stays server/query canonical (chips are links/`hx-get`, not a JS store).
- Preserve G1 identity exactly (palette `theme-forest-cream`, header `marketplace_search_first`,
  footer `premium_columns`, bottom nav `five_item`, RTL Persian, teal/green + charcoal + gold).
- No official-branch change; no merge; no force push; backup push only at the end.

## F. Recorded rulings

- **R1** Reuse the single `product_list` view + `build_product_listing_context` +
  `_filtered_products`; do not add a search/category view or a second query path.
- **R2** Heading/breadcrumb/chip data is derived in `build_product_listing_context` (server), so
  both the full page and the HTMX partial stay consistent and canonical.
- **R3** Active-filter chips live inside `#product-results` (updated by HTMX with the results),
  each with a "remove this filter" querystring computed server-side.
- **R4** Category context uses the existing `Category` (name/parent/slug) — no new banner or
  merchandising model. Category image is out of scope unless already surfaced by the section.
- **R5** Keep the existing `<details>` filter disclosure as the mobile model; only polish. A
  drawer/off-canvas sheet is out of scope for G2.
