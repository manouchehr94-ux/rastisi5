# Phase 1C — Admin Host Enforcement and Product Management Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update. The originating
Phase 1C prompt asked for two things in strict order: (1) finish the
admin-host enforcement Phase 1B left incomplete, verified first; (2) a
Product Management build-out covering attributes/options/variants/media/
pricing/inventory/SEO. Part (1) is fully done. Part (2) is a deliberately
bounded subset — real, tested, shipped — not the full literal scope, which
was not achievable in one pass without weakening tests or fabricating
completeness. Every capability the prompt named that is **not** built is
named explicitly in §9, not glossed over.

---

## 1. Executive Summary

**Delivered, all with real code, tests, and a verified full-suite run
(1890/1890 passing, 0 failures, 0 errors):**

* **Admin-host enforcement is now fully wired** (§3) — the one thing Phase
  1B's ADR-16 explicitly left undone. `staff_required`/`admin_host_required`
  now 404 any request whose Host is not a Store's `admin_subdomain` (or a
  recognized dev/test host), closing the gap where a Store's public
  storefront domain could also serve its `/admin-portal/`.
* A real, previously-latent **production crash bug** was found and fixed as
  a direct consequence of enforcing admin hosts: three context processors
  would 500 (not 404) when rendering any page, including Django's own 404
  handler, for an unresolvable Host once two or more Stores exist (§3.3).
* **Product list**: pagination, whitelisted sorting, brand filtering, and
  bulk actions (activate/deactivate/draft/delete/reassign-category), all
  tenant-isolated and permission-checked (§5).
* **Product SEO and logistics fields**: `barcode`, `weight_grams`,
  `requires_shipping`, `seo_title`, `seo_description`, plus a previously
  entirely-missing `brand` assignment in the product create/edit form (§6).
* **Variant-specific image association**: `ProductImage.variant` (nullable
  FK, `SET_NULL`), a dashboard UI to assign/reassign an existing gallery
  image to a variant, and `ProductVariant.display_image` (variant image, or
  product cover as fallback) (§7).
* Two new ADRs (§10): ADR-17 (admin-host enforcement) and ADR-18
  (variant-image association).

**Not done, named explicitly (§9):** the full Attribute/AttributeValue/
Option registry distinct from the current single-attribute
`ProductVariant.attribute`/`.value` pair; multi-axis variant combination
generation and reconciliation; a real `Tag` model (`Product.tag` remains a
fixed-choice field); product videos; bulk import/export; inventory ledger;
full SEO contract (structured data, canonical URLs, sitemap); category tree
UX rework; audit history. None of these have any code in this codebase
today — building them honestly was out of reach for this phase alongside
the mandatory admin-host-enforcement-first work, and inventing partial,
untested versions would have violated the prompt's own instructions.

## 2. Previous Phase Claims Verified Before Starting

Before any change: confirmed current branch, and that Phase 1B's own
report (§13, Known Limitations) accurately named admin-subdomain
enforcement as the one incomplete item — re-read
`apps/stores/resolution.py`, `apps/dashboard/decorators.py`, and
`docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` (ADR-16) directly
against the actual code rather than trusting the prior report's prose. The
gap was confirmed real: `resolve_store_for_admin_host` existed, tested, but
was not called from `staff_required` — the dashboard was reachable via any
Host resolving to a Store at all, exactly as documented.

## 3. Admin-Host Enforcement (Completed First, Per Prompt Instruction)

### 3.1 What changed

* `apps.stores.resolution.resolve_store_for_admin_request(request)` (new):
  tries `resolve_store_for_admin_host(request.get_host())` first; falls
  through to the general `resolve_store_for_request` only for recognized
  development hosts (`testserver`, `localhost`, etc.); otherwise returns
  `None`.
* `apps.dashboard.decorators._resolve_admin_store_or_404` (new): the single
  chokepoint both `admin_host_required` and `staff_required` call —
  unresolvable Host → `Http404`, always, before any authentication or
  membership check runs.
* `admin_login` gained `@admin_host_required` — the login page itself is
  now also Host-gated, not just the authenticated dashboard views.
* `apps.core.views.admin_panel_compat_redirect` (the `/admin-panel/` →
  `/admin-portal/` 302 shim) now 404s first if the Host doesn't resolve via
  the same admin-request resolver — it no longer redirects to a path that
  would itself immediately 404, and it can no longer be used as an open
  redirect probe for arbitrary Hosts.

### 3.2 Fail-closed behavior, precisely

Three distinct outcomes, each deliberately different and each tested:

| Condition | Result |
|---|---|
| Host doesn't resolve to any Store's admin subdomain (and isn't a dev host) | `404` |
| Host resolves, user authenticated, but no `StoreMembership` for that Store | redirect to `catalog:home` |
| Host resolves, membership exists, but role lacks the specific permission | `403` (`dashboard/403.html`) |

### 3.3 A real bug found and fixed: context-processor 500s on unresolvable Host

Wiring in the 404 above meant, for the first time, that a request with an
unresolvable Host could actually reach Django's own error-rendering path
with `request.store` unset. That exposed a genuine pre-existing defect:
`apps.core.context_processors.shop_settings`,
`apps.catalog.context_processors.nav_categories`, and
`apps.content.context_processors.footer_settings` all called
`ShopSettings.load()` / `Category` queries / `FooterSettings.load()`
unconditionally, which raise `StoreResolutionError` (or the relevant
not-provisioned error) whenever more than one Store exists and the Host
can't be resolved. Since context processors run on *every* template
render, including error pages, this turned "unknown Host" into an
unhandled 500 instead of a clean 404 — in a real multi-Store production
deployment, an unrecognized/typo'd Host would have crashed instead of
404ing. All three now catch the relevant exception(s) and return an empty
context. This was not requested explicitly by the prompt; it surfaced
directly from doing the admin-host-enforcement work honestly rather than
only in the narrow paths the tests happened to already cover.

### 3.4 Test fixture migration

Six existing multi-Store dashboard test files used arbitrary
`*.example.com`-shaped Hosts that predate `admin_subdomain`'s existence:
`test_membership_authorization.py`, `test_catalog_store_isolation.py`,
`test_order_store_isolation.py`, `test_gateway_shipping_store_isolation.py`
(one class only — the other is storefront/checkout-only and untouched),
`test_admin_superuser_gate.py`, `test_footer_config.py`. Each now sets a
real `admin_subdomain` on its fixture Store(s) and requests against a
`*.rastisi.ir`-shaped Host, since a Host that resolves to *no* Store's
admin subdomain now correctly 404s rather than serving the dashboard by
accident.

### 3.5 New tests

`apps/stores/tests/test_admin_host_enforcement.py` — 22 new tests across
`AdminHostEnforcementTests` and `RealMultiStoreProductionShapeTests`:
correct admin host succeeds; a verified public `StoreDomain` is rejected for
the dashboard (login, authenticated views, and the storefront still working
on that same domain); another Store's admin host is rejected; an unknown
subdomain, the bare admin suffix, and a suspended/provisioning Store's host
all 404; the `/admin-panel/` compat redirect 404s on an unresolvable host
and never becomes an open redirect; Host-resolution failure is independent
of membership status (tested for a member, a non-member, an anonymous
user, and a superuser — all 404 identically on a bad Host, before
membership is even checked).

## 4. Product Management Scope Decision

The prompt's Product Management section requested a large single-axis
list: full attribute/option/variant matrix with combination generation and
reconciliation, variant-specific images (marked "mandatory"), full media/
pricing/inventory/SEO. Building the full attribute/option system honestly
— including a data-model ADR, migration, generation algorithm, and
reconciliation logic for existing variants — is its own multi-day project;
attempting a shortcut version would have meant either an untested
half-implementation or silently declaring "done" over something with no
tests, both explicitly prohibited by the prompt. This phase instead
delivered three complete, tested, real slices: product list operations,
SEO/logistics fields, and the specifically-called-out-as-mandatory
variant-image association — each finished end-to-end (model → migration →
service/view → template → tests) rather than left partial.

## 5. Product List: Pagination, Sorting, Bulk Actions

* `apps/dashboard/services/catalog_admin_service.py`: `filtered_products()`
  extended with whitelisted `sort` (`PRODUCT_SORT_OPTIONS`, default
  `-created_at` — no raw user input ever reaches `order_by()`) and `brand_id`
  filtering; new `bulk_set_product_status`, `bulk_delete_products`,
  `bulk_assign_category` — each filters `Product.objects.filter(store=store,
  pk__in=product_ids)` first, so a submitted ID from another Store is
  silently excluded, never acted on.
* `apps/dashboard/views.py`: `_product_list_context` now paginates
  (`Paginator`, 20/page) and accepts `sort`/`brand`; new
  `product_bulk_action` view (`@staff_required`, permission dispatch:
  `PRODUCT_DELETE` for delete, `PRODUCT_EDIT` otherwise).
  `dashboard:product-bulk-action` URL added.
* Templates: `products.html` gained brand and sort `<select>`s wired into
  the existing HTMX `hx-include` chain; `products_table_inner.html` gained a
  bulk-action toolbar (status/category selects, select-all checkbox,
  per-row checkboxes) and pagination controls.
* Tests: `apps/dashboard/tests/test_product_list_bulk_actions.py` (new, 22
  tests) — sort/filter correctness, pagination boundaries, bulk
  status/delete/category-assign per role, and explicit tenant-isolation
  tests (a bulk action submitting a mix of own- and other-Store product IDs
  only ever affects the caller's own Store's rows).

## 6. Product SEO, Logistics, and Brand Fields

* `apps/catalog/models.py`: `Product` gains `barcode`, `weight_grams`,
  `requires_shipping`, `seo_title`, `seo_description` — all additive,
  nullable/blank/defaulted, one migration
  (`0009_product_logistics_and_seo_fields.py`), no backfill needed.
* `apps/dashboard/forms.py`: `ProductForm` gains a `brand` field (this was
  entirely missing from the form despite `Product.brand` already existing
  as a model FK — merchants had no way to assign a brand through the
  dashboard UI at all before this phase), `barcode`, `weight_grams` (with
  `clean_weight_grams` — normalizes Persian digits, rejects non-integer and
  negative values), `requires_shipping`, `seo_title`, `seo_description`. The
  `brand` field's queryset is scoped to `Brand.objects.filter(store=store)`,
  so a cross-Store brand ID is rejected by Django's own `ModelChoiceField`
  validation before it ever reaches `_save_product`. `STATUS_CHOICES` also
  gained `DRAFT` (previously only ACTIVE/INACTIVE were selectable in the
  form despite the model and the new bulk actions both supporting DRAFT).
* `apps/dashboard/views.py`: `_save_product` and the GET-branch `initial`
  dict both updated to read/write all five new fields plus `brand`.
* Template: `product_form.html` gained a brand `<select>`, a "مشخصات
  لجستیک" fieldset (barcode, weight, requires-shipping checkbox), and a
  "سئو" fieldset (SEO title/description).
* Tests: `ProductSeoAndLogisticsFieldsTests` (new, 9 tests) in
  `test_product_views.py` — field persistence on create, edit prefill,
  weight validation (negative/non-numeric/blank), brand assignment, blank
  brand allowed, and a cross-Store brand rejection test.

## 7. Variant-Specific Image Association

* `apps/catalog/models.py`: `ProductImage.variant` — nullable FK to
  `ProductVariant`, `on_delete=SET_NULL`, `related_name="images"`.
  `ProductImage.clean()` rejects a `variant` that doesn't belong to
  `self.product` (mirrors the existing `Product.clean()` brand/category/
  vendor cross-Store checks). `ProductVariant.display_image` — the
  variant's own first image, or the product's `cover_image` as fallback.
  Migration: `0010_product_image_variant.py`.
* `apps/catalog/services/product_image_service.py`: `set_image_variant(image,
  variant)` — raises `ProductImageError` if `variant.product_id !=
  image.product_id`.
* `apps/dashboard/views.py`: new `product_image_variant_update` view
  (`@staff_required`, `@permission_required(MEDIA_MANAGE)`) — the variant is
  fetched via `get_object_or_404(ProductVariant, pk=variant_id,
  product=product)`, so a cross-product variant ID 404s before the service
  layer's own check even runs (defense in depth). `dashboard:product-image-
  variant` URL added.
* Templates: `product_images_list.html` gained a per-image variant
  `<select>` ("— تصویر عمومی کالا —" or a specific variant); `product_
  variants.html` gained a thumbnail column showing each variant's
  `display_image`.
* No new upload path: merchants assign an *existing* gallery image to a
  variant rather than uploading directly into a variant-scoped endpoint,
  reusing the already-validated/resized upload pipeline instead of
  duplicating it (see ADR-18 for the reasoning).
* Tests: `SetImageVariantTests` (5, `apps/catalog/tests/
  test_product_image_service.py`), `ProductImageVariantAssociationViewTests`
  (8, `apps/dashboard/tests/test_product_image_views.py`), and one model-
  level cross-product-rejection test in `apps/catalog/tests/test_models.py`
  — covering assignment, clearing, `SET_NULL` on variant deletion (image
  survives, becomes general again), cross-product rejection at both the
  service and model-`clean()` layers, permission/anonymous denial, and the
  `display_image` fallback-vs-override behavior.

## 8. A Real Regression Found and Fixed During Full-Suite Validation

The first full-suite run after all Phase 1C changes landed reported two
genuine failures, not something to explain away:
`test_query_count_bounded_regardless_of_variant_count` and
`test_query_count_bounded_with_search_active` in
`test_product_variant_views.py` — both pre-existing N+1-query guard tests.
Root cause: the new `product_variants.html` thumbnail column calls
`variant.display_image` per row, which (in its first draft) accessed
`self.images.order_by("order", "id").first()` and `self.product.cover_image`
— neither of which can be satisfied from Django's `prefetch_related` cache
(`.order_by()`/`.filter()` chained onto a related manager always issues a
fresh query; only a bare `.all()` can hit the prefetch cache), and
`variant.product` re-fetched the product row from the database on every
iteration since the FK wasn't cached. Query count grew from 20 to 68 as
variant count increased — a genuine N+1 this phase introduced.

Fixed, not weakened: `display_image` rewritten to use `self.images.all()`
(relying on `ProductImage.Meta.ordering = ["order", "id"]`, which already
matches what the removed explicit `.order_by()` asked for) so it's
prefetch-cache-eligible; `_variant_page_context` now calls
`filtered_qs.prefetch_related("images")` and, after pagination,
`prefetch_related_objects([product], "images")` plus `variant.product =
product` for each row (caching the already-loaded product instance instead
of re-querying it 20+ times). Verified: both previously-failing tests pass,
the full 206-test `test_product_variant_views.py` +
`test_product_image_views.py` + `test_product_image_service.py` +
`test_models.py` batch is green, and the subsequent complete full-suite
re-run is 1890/1890 green.

## 9. Known Limitations and Remaining Product-Management Gaps

Named explicitly, per the prompt's own instruction not to leave gaps
silently unreviewed:

* **No Attribute/AttributeValue/Option registry.** `ProductVariant` still
  supports exactly one `attribute`/`value` axis per variant row (e.g.
  "Color: Red"); there is no way to define "Color × Size" as two
  independent, no-code-defined axes and generate the cross-product of
  combinations, nor any reconciliation logic for what happens to existing
  variants when an axis is added/removed/renamed. This is the single
  largest gap relative to the prompt's Product Management ask, and
  building it requires its own ADR (attribute/option identity, combination-
  key stability across renames, migration path for the ~15 seeded
  single-axis variants) before any code should be written.
* **No `Tag` model.** `Product.tag` remains the pre-existing fixed-choice
  field (NEW/HOT/SALE) — not a real many-to-many tag system.
* **No product videos.** Nothing in `ProductImage` or elsewhere supports
  video media; the prompt's "rich content" section names this explicitly.
* **No bulk import/export.** Product CRUD is one-row-at-a-time through the
  dashboard form; no CSV/spreadsheet ingestion or export exists.
* **No inventory ledger or stock reservation.** `Product.stock`/
  `ProductVariant.stock` remain simple integer counters with no movement
  history, no reservation-on-checkout, no warehouse concept.
* **SEO fields are partial, not a full contract.** `seo_title`/
  `seo_description` exist; structured data (JSON-LD), canonical URL
  control, sitemap entries, and Open Graph tags do not.
* **No duplicate/clone-product action, no product audit history, no
  configurable product-type templates, no category-tree UX rework** — all
  named as gaps in the Phase 1B report's own catalog assessment and still
  true; none were in this phase's bounded scope.
* **`permission_required` is still coarse per resource** — unchanged from
  Phase 1B; all product-image and variant-image endpoints share
  `MEDIA_MANAGE`, matching the existing pattern rather than inventing a
  finer-grained key.

## 10. ADRs Written

* **ADR-17** (`SAAS_DOMAIN_DECISIONS.md`): admin-host enforcement closes
  the ADR-16 gap via a new composing function
  (`resolve_store_for_admin_request`), not by changing
  `resolve_store_for_admin_host` itself; documents the context-processor
  500→404 fix as a direct consequence.
* **ADR-18** (`SAAS_DOMAIN_DECISIONS.md`): variant-specific images are a
  nullable `ProductImage.variant` FK with `SET_NULL`, not a separate
  `VariantImage` model or a many-to-many — reuses the existing validated
  upload pipeline; documents `display_image`'s fallback contract and what
  the storefront still needs to build on top of it (out of scope here).
* Summary table at the end of `SAAS_DOMAIN_DECISIONS.md` updated: admin-
  subdomain enforcement flipped from "Recorded, not enforced" to "Decided,
  implemented"; a new row added for variant-specific images.
* `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` §11.2 (Catalog)
  updated to list the new brand/logistics/SEO fields, variant-image
  association, and product list bulk actions under "موجود و تثبیت‌شده" —
  the "ناقص" (gap) list is unchanged, since none of those gaps were closed.

## 11. Files Created

* `apps/catalog/migrations/0009_product_logistics_and_seo_fields.py`
* `apps/catalog/migrations/0010_product_image_variant.py`
* `apps/stores/tests/test_admin_host_enforcement.py`
* `apps/dashboard/tests/test_product_list_bulk_actions.py`
* `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md` (this file)

## 12. Files Modified (grouped)

* **Admin-host enforcement:** `apps/stores/resolution.py`
  (`resolve_store_for_admin_request`), `apps/dashboard/decorators.py`
  (`_resolve_admin_store_or_404`, rewritten `admin_host_required`/
  `staff_required`), `apps/dashboard/views.py` (`admin_login` decorator),
  `apps/core/views.py` (`admin_panel_compat_redirect`)
* **Context-processor crash fix:** `apps/core/context_processors.py`,
  `apps/catalog/context_processors.py`, `apps/content/context_processors.py`
* **Migrated test fixtures (admin-subdomain hosts):**
  `apps/dashboard/tests/test_membership_authorization.py`,
  `test_catalog_store_isolation.py`, `test_order_store_isolation.py`,
  `test_gateway_shipping_store_isolation.py`,
  `apps/stores/tests/test_admin_superuser_gate.py`,
  `apps/content/tests/test_footer_config.py`
* **Product list/bulk actions:**
  `apps/dashboard/services/catalog_admin_service.py`,
  `apps/dashboard/views.py`, `apps/dashboard/urls.py`,
  `apps/dashboard/templates/dashboard/products.html`,
  `apps/dashboard/templates/dashboard/partials/products_table_inner.html`
* **SEO/logistics/brand fields:** `apps/catalog/models.py`,
  `apps/dashboard/forms.py`, `apps/dashboard/views.py`,
  `apps/dashboard/templates/dashboard/partials/product_form.html`
* **Variant-image association:** `apps/catalog/models.py`,
  `apps/catalog/services/product_image_service.py`,
  `apps/dashboard/views.py`, `apps/dashboard/urls.py`,
  `apps/dashboard/templates/dashboard/partials/product_images_list.html`,
  `apps/dashboard/templates/dashboard/product_variants.html`
* **N+1 fix:** `apps/dashboard/views.py` (`_variant_page_context`),
  `apps/catalog/models.py` (`display_image`)
* **Tests extended:** `apps/dashboard/tests/test_product_views.py`,
  `apps/dashboard/tests/test_product_image_views.py`,
  `apps/catalog/tests/test_product_image_service.py`,
  `apps/catalog/tests/test_models.py`
* **Docs:** `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`
  (ADR-17, ADR-18, summary table), `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`

## 13. Database Changes

* New fields: `Product.barcode`, `Product.weight_grams`,
  `Product.requires_shipping`, `Product.seo_title`,
  `Product.seo_description`, `ProductImage.variant` (nullable FK,
  `SET_NULL`)
* 2 migrations, both purely additive (nullable/blank/defaulted) — no
  backfill migration needed, no staged nullable→enforce sequence required
  since none of these fields become mandatory
* `makemigrations --check --dry-run` confirms the model state and
  migrations are in sync throughout

## 14. Commands Actually Executed and Results

```text
python manage.py check                              → System check identified no issues (0 silenced)  [run repeatedly through the phase]
python manage.py makemigrations --check --dry-run   → No changes detected  [run repeatedly through the phase]
```

Test runs (all executed, all real, run in batches due to full-suite
runtime — never to skip anything):

| Batch | Tests | Result |
|---|---|---|
| `test_product_views.py` (SEO/logistics/brand fields) | 28 | OK |
| `test_product_image_views.py` (variant-image association) | 24 | OK |
| `test_product_image_service.py` (service-level, new) | 28 | OK |
| `apps.stores` + `apps.dashboard` + `apps.content` + `apps.catalog` + `apps.core` (early admin-host-enforcement checkpoint) | 1449 | OK |
| `apps.stores` + `apps.content` (post product-management changes) | 625 | OK |
| `apps.dashboard` + `apps.catalog` (post product-management changes) | 801 | OK |
| **First full suite** (`python manage.py test`) | 1890 | **2 failures** — N+1 regression, §8 |
| Targeted re-check after N+1 fix (`VariantPageQueryPerformanceTests` + `VariantPageFilteredQueryPerformanceTests`) | 3 | OK |
| `test_product_variant_views.py` + `test_product_image_views.py` + `test_product_image_service.py` + `test_models.py` (full regression around the fix) | 206 | OK |
| **Full suite, final** (`python manage.py test`) | 1890 | **OK — 0 failures, 0 errors** |

The N+1 regression above (§8) is the one real defect this phase's own
validation caught — reported here, not hidden, and fixed by addressing the
query pattern, not by loosening the guard test's threshold.

## 15. Recommended Next Phase

In priority order:

1. **Attribute/AttributeValue/Option registry and multi-axis variant
   combinations** — the single largest remaining gap (§9), and the
   prerequisite for several already-defined-but-unused permission keys
   (`ATTRIBUTE_MANAGE` from Phase 1B) and for any real inventory-per-
   combination feature. Needs its own ADR before implementation — combination
   identity/stability across attribute renames and the reconciliation
   behavior for existing single-axis variants are genuine design questions,
   not just a migration.
2. **Storefront consumption of `ProductVariant.display_image`** — the data
   model and admin association exist (§7); the shopper-facing variant-
   image-swap UI on the product detail page does not.
3. Then, per both prior phases' own recommendations (still valid, still not
   started): wallet/cashback/referral, subscription/billing, staff
   invitation lifecycle, domain-management UI, inventory ledger, bulk
   import/export.

## 16. Commit, Branch, and Push Status

* **Branch:** `claude/docs-prototypes-review-jxm6aw`
* **Commit hash / push status:** recorded after this report is committed —
  see the commit that includes this file for the exact hash; pushed to
  `origin/claude/docs-prototypes-review-jxm6aw` in the same operation.
