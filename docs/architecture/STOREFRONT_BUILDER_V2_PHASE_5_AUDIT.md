# Storefront Builder V2 — Phase 5 (Product/Listing/Collection/Search/Cart Composition) Read-Only Gap Audit

**Branch:** `claude/family-visual-fidelity-fix`
**Audited at commit:** `034b42d8e54d39e38db8accab325be6eefee03ab` (Phase 4 closure HEAD)
**Method:** Full reads of `apps/catalog/views.py` (product_detail/product_list/collection_index/collection_detail),
`apps/cart/views.py`, `apps/storefront_builder/section_registry.py`,
`apps/storefront_builder/services/render_service.py`,
`apps/storefront_builder/services/storefront_context_service.py`,
`apps/storefront_builder/services/page_resolution_service.py`,
`apps/storefront_builder/models.py` (`StorefrontPage`, `StorefrontSection`),
`apps/storefront_builder/services/layout_service.py` (`get_or_create_draft`,
`_clone_version_content`), `apps/storefront_builder/services/bootstrap_service.py`,
all five public templates (`catalog/product_detail.html`, `catalog/product_list.html`,
`catalog/collection_detail.html`, `catalog/collection_index.html`,
`cart/cart_detail.html` + `cart/partials/cart_page_body.html`),
`apps/storefront_builder/family_registry.py` and all 11 family template
directories, `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`,
`apps/storefront_builder/views.py` (page-tab/section-CRUD endpoints), and existing
test coverage across `apps/catalog/tests/`, `apps/cart/tests/`, `apps/storefront_builder/tests/`.

---

## 1. Executive summary

The infrastructure to make these 5 page types section-composable **already
exists end-to-end at the service layer**: routes call the universal context
builder with the correct `page_type`, `StorefrontPage` rows exist for all 6
types on every version (`StorefrontPage.ensure_version_pages`, called from
every version-creation path), `render_service.build_page_render_items` is
fully page-type-generic (not home-only), and the Builder dashboard UI
already has a page-type tab switcher (`editor.html:57`) that lets a merchant
add/reorder/configure sections on **any** of the 6 pages, with a live iframe
preview (`storefront_preview` → `preview.html`) that renders them correctly.

**But the public-facing templates for all 5 non-home page types never
consume `render_items`.** This is the headline, single biggest real gap:
a merchant can already open the Builder, switch to the "Listing" or "Cart"
tab, add sections, see them render correctly in the in-editor preview
iframe, publish — and the live public site for that page type shows **zero**
visible change, because no non-home template loops over `render_items`
(confirmed: the string `render_items` appears in zero of the five public
templates). This is a materially confusing, already-shippable-looking gap
in production today, not a theoretical one.

Secondary real gaps: no page-type restriction mechanism exists on
`SectionDefinition` (any of the 17 registered home-page-shaped section types
could technically be added to Cart or Search with zero server-side
rejection); no section type is scoped/purpose-built for these 5 pages; no
default composition exists for any of the 5 pages (their `StorefrontPage`
rows are structurally guaranteed to exist but have zero `StorefrontSection`
rows in practice, because the bootstrap/industry-default services are
home-only); `build_page_render_items(page, store)` has no signature surface
for route-resolved context (current product/collection/search query/cart) —
required for any context-aware section type.

## 2. Per-page-type audit table

| # | Question | product_detail | listing | collection | search | cart |
|---|---|---|---|---|---|---|
| 1 | Renders through `StorefrontPage`? | Yes — `build_universal_storefront_context(..., PRODUCT_DETAIL)` | Yes — `..., LISTING` | Yes — `..., COLLECTION` (both index and detail views) | Yes — `..., SEARCH` (same view as listing, routed by presence of `q`) | Yes — `..., CART` |
| 2 | Has ordered `StorefrontSection` rows today? | **No** (0 rows, in practice) | **No** | **No** | **No** | **No** |
| 3 | Section types currently allowed | All 17 (no restriction) | All 17 | All 17 | All 17 | All 17 |
| 4 | Hardcoded in route template | Everything (gallery, price, variants, qty, add-to-cart, stock, description, specs tab, video, related products) | Everything (filters, sort, grid, pagination, breadcrumb) | Everything (hero/title/description, grid, pagination) | Everything (shares listing's template/view) | Everything (line items, qty/remove, totals, checkout CTA, empty state) |
| 5 | Already reusable typed blocks | `product_card.html` (product grid card, family-variant-aware) reused for related products | `product_card.html` reused for grid | `product_card.html` reused for grid | `product_card.html` reused for grid | none |
| 6 | Builder page-aware for this type | **Yes** — editor/preview/section-CRUD backend already page-type-generic; page tab exists in UI | Yes (same) | Yes (same) | Yes (same) | Yes (same) |
| 7 | Sections addable/removable/reorderable/duplicable/hideable/configurable | Yes (generic CRUD works), but **has zero live-storefront effect** | Yes (same caveat) | Yes (same caveat) | Yes (same caveat) | Yes (same caveat) |
| 8 | Section settings typed/validated | Yes for the 17 existing types (unchanged) | same | same | same | same |
| 9 | Responsive settings supported | Yes (`_with_responsive`, additive to all 17) | same | same | same | same |
| 10 | Data sources tenant-scoped | Yes, at every layer already touched (product/variant/cart security tests are extensive) | Yes (`_filtered_products` always scoped to `store`) | Yes (`collection_service.public_collection_queryset(store)`) | Yes (same as listing) | Yes (`cart_totals(cart, store=store)`, resolved via `resolve_store_for_storefront`) |
| 11 | Draft isolated from Published | Yes (structural — same `publish()` pointer-swap covers all pages uniformly, already tested by `PublishActivatesCompletePageSetTests`) | Yes | Yes | Yes | Yes |
| 12 | Public rendering always Published | Yes (`page_resolution_service.resolve_published_page`) | Yes | Yes | Yes | Yes |
| 13 | Preview and public use same renderer | **Partially** — both call `build_page_render_items`, but only the Preview iframe template (`preview.html`) actually consumes the result; the 5 public templates don't | same | same | same | same |
| 14 | Legacy family bypass | **Yes, full body** — 11 hand-authored `product_page_variant` templates | **No family variant field exists** — always canonical template | **No family variant field exists** | **No family variant field exists** (shares listing) | **No family variant field exists** |
| 15 | Hardcoded browser behavior | Variant→image swap (Alpine), qty stepper (Alpine, client-only), add-to-cart (htmx POST) | Filter form (htmx live-swap on submit/change), pagination links | Pagination links only | Same as listing | Qty update/remove (htmx, server round-trip), checkout link |
| 16 | Existing tests | Extensive (`test_product_detail_view.py`, `test_product_detail_videos.py`, security-adjacent variant/gallery tests) | Extensive (`test_product_list_view.py`) | Extensive (`test_collection_public_views.py`) | Covered inside `test_product_list_view.py` (search is the same view) | Extensive (`test_cart_views.py`, `test_cart_security.py`) |
| 17 | Real gaps vs. roadmap assumptions | Real: render_items not consumed; family body bypass; no context-aware section types; no defaults | Real: same first/third/fourth; no family variant (different kind of gap, see §7) | Real: same, plus route-vs-config collection identity discipline needed | Real: same as listing (shares its fix) | Real: same first/third/fourth; no family variant |

## 3. Classification: ALREADY EXISTS / PARTIAL / MISSING / OUT OF SCOPE / LEGACY BOUNDARY

### ALREADY EXISTS (confirmed correct, do not rebuild)

- `StorefrontPage` rows for all 6 types on every version, always
  (`ensure_version_pages`, called from `StorefrontLayoutVersion.save()`,
  `restore_version`, `apply_industry_layout`) — **no gap**.
- `build_universal_storefront_context(request, store, page_type)` is fully
  generic across all 6 page types, already invoked correctly by all 5 public
  routes with the correct `page_type` — **no gap**.
- `render_service.build_page_render_items(page, store)` is fully
  page-object-scoped (not home-hardcoded); `build_render_items(version,
  store)` is kept only as a thin home-only backward-compat wrapper — **no
  gap in the function itself**, though its signature needs an additive
  extension for context-aware sections (see §5.3).
- Section CRUD backend (`storefront_section_add`/`storefront_section_reorder`/
  duplicate/toggle/move, `views.py:37-673`) is already page-type-generic,
  threading `page_type`/`draft.get_page(page_type)` throughout — **no gap**.
- Dashboard editor UI already has a page-tab switcher
  (`editor.html:57`, `?page=<page_type>`) and the embedded live-preview
  iframe correctly renders whatever sections exist on the selected page
  type via `preview.html`'s `{% for item in render_items %}` — **no gap in
  the Builder UI itself**.
- Draft/Publish/Preview/Public lifecycle is uniform across all 6 page types
  already, proven by existing tests (`PublishActivatesCompletePageSetTests`,
  `RestoreRecreatesCompletePageSetTests`, `DraftDoesNotLeakIntoRoutesTests`,
  `AllSixPageTypesResolveFromSameVersionTests`) — **no gap**.
- Tenant scoping at every data-access layer already touched by these 5
  pages is real and tested (`TenantIsolationAcrossRoutesTests`,
  `CartAddSecurityTests`, `CollectionDetailViewTests` cross-store-slug→404,
  etc.) — **no gap in the existing hardcoded logic itself**; any new
  context-aware section must preserve this, not re-derive it.
- Product variant model, variant→image gallery switching, add-to-cart
  server-side re-validation (never trusting POSTed price), cart quantity
  re-clamping against live stock — all real, working, well-tested — **no
  gap, must be preserved exactly, not touched**.
- Header/Footer consistency across all 6 pages (Phase 4) — **no gap, not
  revisited this phase** unless Phase 5 work exposes a real regression.

### PARTIAL (real infrastructure exists, real piece missing)

- **`render_items` is computed but never rendered** for these 5 page types
  — the single largest gap. Fix: each of the 5 public templates needs a
  `{% for item in render_items %}...{% endfor %}` loop (the exact pattern
  `home_visual.html` already uses), gated the same way Home is (behind
  `uses_universal_shell`/family-absence where a family body bypass exists).
- **Preview vs. public use the "same renderer" only at the service-call
  level, not at the template-consumption level** — once the templates
  consume `render_items` the same way Home's do, this becomes fully true
  (no new renderer needed — reusing `responsive_section_wrapper.html`
  exactly as Home does).
- **`SectionDefinition` has no page-type field** — all 17 existing section
  types are implicitly "allowed everywhere," with zero server-side
  enforcement in `storefront_section_add`. This did not matter while
  `render_items` had no visible effect; it will matter the moment §above is
  fixed, because a merchant could otherwise add e.g. `hero_banner` to Cart.

### MISSING (does not exist at all, must be built)

- **Context-aware section types** for these 5 pages. Confirmed via grep:
  zero section keys in `section_registry.py` resemble
  `product_main`/`cart_items`/`listing_grid`/etc. — the registry is
  entirely home-page-shaped generic marketing/discovery blocks. New,
  purpose-built types are needed (design in §6).
- **`build_page_render_items` route-context passthrough.** Its current
  signature is `(page, store)` only — no way for a context-aware section's
  context-builder to know "the product being viewed," "the collection being
  viewed," "the current search query," or "the current cart." This must be
  added additively (an optional context dict), never by storing these
  transient values in `StorefrontSection.settings` (which would violate the
  master prompt's explicit tenant-safety rule and would break Draft/Publish
  semantics — a product's identity must remain route-derived, never
  version-baked).
- **Default compositions** for all 5 page types. Confirmed: the bootstrap
  service (`bootstrap_service.py` — `build_bootstrap_sections`,
  `apply_bootstrap_content`, `build_industry_default_sections`,
  `build_family_default_sections`) contains no reference to any
  `page_type` other than home; `_clone_version_content`'s own docstring
  states plainly that all non-home pages "stay exactly empty" today. A new
  store's product/listing/collection/search/cart pages must work
  immediately without requiring a merchant to build from an empty canvas —
  this needs new default-section-seeding logic scoped to these 5 types,
  version/page-owned so it clones correctly with Draft versions (reusing
  the existing `_clone_version_content` cloning mechanism, not a new one).
- **Server-side page-type allowlist enforcement** in `storefront_section_add`
  — currently only checks `max_instances`, never checks whether the
  section type is valid for the target page's `page_type`.

### OUT OF SCOPE (explicitly not attempted this phase)

- Refactoring the 11 family `product_page_variant` templates into composed
  sections — same reasoning as Phase 4's family-header/footer boundary:
  large, separate, high-risk, and the master prompt explicitly permits
  family-specific partials to remain temporarily (deferred to Phase 7).
- Building family-specific variants for listing/collection/search/cart
  bodies — **these don't exist today at all** (confirmed: no
  `listing_variant`/`collection_variant`/`search_variant`/`cart_variant`
  field exists on `FamilyDefinition`, and none of the four templates
  reference `SHOP_FAMILY`). Phase 5 will not introduce new family-specific
  body variants for these either — the canonical composed body is the only
  body these 4 page types get, regardless of family, consistent with "do
  NOT add new family-specific functionality."
- Multi-axis product attribute editing, coupon-on-cart-page UI, shipping
  estimate on the cart page, "recently viewed" — all confirmed to not exist
  today and are not implied by "composition" (composition means letting a
  merchant arrange/configure what already exists as reusable primitives,
  not building new commerce features).
- Splitting the product purchase area (gallery + price + variant + qty +
  add-to-cart + stock) into many tiny sections — the master prompt
  explicitly prefers "a main product purchase area may remain one
  structured block."
- A separate `search_results` section type distinct from listing's grid —
  since search is literally the same view/template/query pipeline as
  listing today (routed only by presence of `?q=`), Phase 5 will make one
  `product_listing` context-aware section type valid on **both** `LISTING`
  and `SEARCH` page types rather than duplicating an equivalent primitive,
  consistent with the explicit "do NOT create duplicate section types if
  equivalent primitives already exist" instruction.

### LEGACY COMPATIBILITY BOUNDARY (documented, not fixed this phase)

1. **product_detail family body bypass** — `catalog/product_detail.html:24`,
   `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.product_page_variant %}{% else %}...{% endif %}`,
   11 complete standalone templates (~2097 lines total) under
   `apps/catalog/templates/catalog/partials/product_pages/`. A store with a
   family selected will **not** see Phase 5's new composable product page —
   it keeps its hand-authored family body, exactly as Phase 4 documented for
   header/footer. New Phase 5 composability applies **only to the canonical
   (family-less) shell**, same boundary rule as Phase 4.
2. **listing/collection/search/cart have no family variant at all** — a
   distinct, pre-existing (not newly discovered) visual-consistency
   asymmetry: a family-selected store gets a fully re-skinned
   header/footer/product-cards/product-page but generic-looking
   listing/collection/cart pages. Phase 5 does not change this asymmetry in
   either direction — it neither adds family variants for these 4 page
   types nor removes the existing product_detail family bypass. Left
   exactly as found, to be dealt with systematically in Phase 7 per
   instruction.
3. `product_card.html`'s `SHOP_FAMILY.product_card_variant` continues to
   apply inside any product grid (listing/collection/related-products),
   regardless of Phase 5's changes — unrelated to this phase, confirmed
   unaffected.

## 4. Product Detail — composable elements decision

Following the master prompt's explicit "prefer sensible compositional
primitives... a main product purchase area may remain one structured block
rather than 15 tiny blocks," and "preserve existing variant-image behavior,"
"preserve existing product video support," Phase 5 defines exactly **three**
new context-aware section types for `product_detail`:

- **`product_main`** — gallery (with existing variant→image switching,
  untouched), title, price/discount, variant selector, quantity, add-to-cart,
  stock state, SKU. One structured block, reusing the existing Alpine
  component and `build_variant_selector_context`/`product_price_json`
  server-side logic verbatim — not decomposed further.
- **`product_description`** — long description + specs/attributes tab
  content + product video grid. Combining these three (all "supporting
  detail" content, not purchase-critical) into one block keeps the primitive
  count sensible; specs continue to be the existing synthesized
  category/brand/SKU/variant-summary content (the `Specification` model
  wiring gap noted in the research is a pre-existing gap independent of
  composability and is not in scope this phase).
- **`related_products`** — same-category related products grid, reusing the
  existing `related_products` queryset logic verbatim.

All three are `PRODUCT_DETAIL`-only in the new page-type allowlist.

## 5. Listing / Search — composable elements decision

**One** new context-aware section type, valid on both `LISTING` and
`SEARCH`:

- **`product_listing`** — title/breadcrumb + filter/sort controls + product
  grid + pagination, reusing `_filtered_products`'s existing query logic
  verbatim (unchanged — filtering/sorting/pagination stay exactly as they
  are; the section only decides where this block sits relative to other
  merchant-added content, e.g. a promotional banner above it). The existing
  generic content blocks (`rich_text`, `single_banner`, `multi_banner`,
  `image_slider`, `trust_features`, etc.) remain addable above/below it on
  these two page types for merchant-authored supplementary content — this
  satisfies "custom reusable content above/below grid" without a new
  section type.

No separate `listing_header`/`search_header`/`search_results` type — merged
per the "do not duplicate equivalent primitives" instruction (§3, Out of
Scope). Search term is never stored in this section's settings — it is read
fresh from `request.GET.get("q")` on every render, exactly as today (see
§8 rendering-safety rule).

## 6. Collection — composable elements decision

**Two** new context-aware section types, both `COLLECTION`-only:

- **`collection_header`** — hero/title/description/image, resolved from the
  route's current collection (via the same `collection_service` lookup the
  view already performs) — **never** a collection ID stored in
  `StorefrontSection.settings`. The page layout describes HOW a collection
  renders; the route determines WHICH collection, exactly as instructed.
- **`collection_products`** — product grid for the same route-resolved
  collection, reusing the existing `collection_service.public_collection_queryset`/
  pagination logic verbatim, including the existing empty-visible-products
  state.

`collection_index` (the list-of-collections page, currently sharing the
same `COLLECTION` page type with every individual collection-detail page —
see the research's §7/audit table row 1 note) is **not** given its own new
`StorefrontPage.PageType` this phase — that would be a schema change beyond
"composition" scope and isn't called for by the master prompt's five named
targets. It continues to resolve the same `StorefrontPage.COLLECTION` row;
its own template stays hardcoded (it has no "current collection" to be
context-aware about). This is noted as a pre-existing, minor structural
overlap, not fixed this phase.

## 7. Cart — composable elements decision

**Two** new context-aware section types, both `CART`-only:

- **`cart_items`** — line items, quantity controls (htmx, existing
  `cart:item-update`/`cart:item-remove` endpoints, unchanged), and the
  empty-cart state (shown here instead of a separate section, since "empty"
  is a property of the same data this block already owns).
- **`cart_summary`** — subtotal/totals (via the existing `cart_totals`
  service, unchanged), checkout CTA, continue-shopping link. Renders
  nothing (or a minimal "cart is empty" note) when the cart has zero items,
  rather than duplicating empty-state logic.

Coupon/shipping-summary UI is confirmed absent from the cart page today
(§9 of the research) and is out of scope — composability does not imply
building new checkout features. Core cart business logic
(`cart_totals`, stock re-validation, session/customer cart resolution)
is not touched — the builder only controls where these two blocks sit and
whether either is present, never how a total is computed.

## 8. Rendering-safety rules for all new context-aware sections

- Fail safely (render nothing / a safe empty state) if the expected route
  context is absent — must never crash the page.
- Never accept a tenant ID from `StorefrontSection.settings` for anything
  route-derived (current product/collection/cart) — always resolved from
  the request/route the same way the existing hardcoded view code already
  does it.
- Never query another store — reuse the exact existing store-scoped
  queries (`storefront_visible_products(store)`,
  `collection_service.public_collection_queryset(store)`,
  `_filtered_products(request, store)`, `cart_totals(cart, store=store)`)
  rather than writing new ones.
- No N+1 regressions — reuse the existing `select_related`/`prefetch_related`
  calls already present in the hardcoded views; the existing
  `FooterQueryCountTests`-style query-count assertions are the precedent
  to follow for these new context builders too.
- CSRF preserved for all mutating actions (add-to-cart, quantity
  update/remove) — unchanged, since the underlying forms/htmx endpoints are
  reused verbatim, not rebuilt.

## 9. Draft/Published verification plan (all five page types)

Already structurally proven at the `StorefrontPage`/`publish()` level
(§3, Already Exists). What Phase 5 implementation must additionally prove,
per page type, once `render_items` is actually consumed publicly:

- A section added to a page's Draft is invisible on the live public route
  for that page type before publish.
- The same section becomes visible on the correct public route after
  publish.
- Preview (staff-only) always reflects Draft; public always reflects
  Published — for all 5 non-home page types, mirroring the existing
  `DraftDoesNotLeakIntoRoutesTests` pattern but this time asserting an
  actual section marker appears/doesn't appear, not just that the
  page still 200s.

## 10. Page-specific section allowlist — mechanism to add

`SectionDefinition` gains one new field:

```python
page_types: frozenset[str] = ALL_PAGE_TYPES  # sentinel meaning "every page type" — no behavior change for the existing 17
```

The 17 existing section types keep the default (available on every page
type, exactly as today — this is a deliberate, additive, non-breaking
choice: they are all generic marketing/content blocks, and the master
prompt explicitly allows "Home-only sections may be reusable where
appropriate"). The 8 new context-aware types (§4/§5/§6/§7) each set an
explicit, narrow `page_types` — e.g. `product_main` → `frozenset({"product_detail"})`.

Enforcement point: `storefront_section_add` (`views.py:201`) gains one
check — `if page.page_type not in definition.page_types: reject` — server-side,
not merely hidden from the UI's "add section" library for that page tab
(the library itself will also only list types valid for the currently
selected page tab, but the server check is what actually closes the gap,
per the explicit "Validation must enforce them server-side, not only in
the UI" instruction).

## 11. Prioritized real-gap list for this phase

1. **Consume `render_items` in the 5 non-home public templates** — the
   core "genuinely composable" gap. Highest priority.
2. **Add `page_types` allowlist to `SectionDefinition` + server-side
   enforcement** — must land before/alongside #1, otherwise #1 makes the
   pre-existing "any section on any page" gap actually visible/exploitable.
3. **8 new context-aware section types** (§4/§5/§6/§7) with their
   context-builders, templates, and route-context passthrough into
   `build_page_render_items`.
4. **Default compositions** for all 5 page types, seeded once (mirroring
   today's exact hardcoded behavior as the default, so publishing never
   silently changes an existing store's look), version/page-owned so
   `_clone_version_content` clones them into new Drafts automatically
   (no new cloning mechanism needed).
5. Test coverage proving all 30 items in the master prompt's "Required
   Test Areas" list.
6. Focused browser QA across all 5 page types, desktop + mobile.

## 12. Explicitly not done (per master prompt's own scope boundaries)

- No new renderer architecture (reusing `render_service`/
  `responsive_section_wrapper.html` exactly as-is).
- No new family system, no 12th family, no new family variants for
  listing/collection/search/cart.
- No refactor of the 11 existing family templates.
- No move of Header/Footer into `StorefrontPage` (untouched, still owned by
  `StorefrontLayoutVersion.header_config`/`footer_config`).
- No duplication of Home's block architecture beyond what's reused
  (responsive/motion/destination wrappers apply automatically via
  `_finalize_registry` to any new section type that opts in the normal way
  — no new wrapper mechanism needed).
