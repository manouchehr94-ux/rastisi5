# 01 — Repository Architecture and Gaps

All facts below are verified directly against the current checked-out code (`HEAD=4f424453d`), not against the dated planning documents in `docs/reports/` (see `00_REPOSITORY_BASELINE.md` for why those are stale). Every claim carries a `file:line` or exact symbol citation.

---

## 1. Tenant / storefront resolution

- **Single authoritative resolver.** `apps.stores.resolution` is the one module that decides "which Store" (`docs/docs/product/architecture/SAAS_ARCHITECTURE.md` §6, verified against code). `StoreResolutionMiddleware` (`apps/stores/middleware.py`) runs immediately after `SecurityMiddleware`, before `SessionMiddleware`/`AuthenticationMiddleware` (`shop_core/settings.py` `MIDDLEWARE` list) — tenant resolution structurally cannot depend on session/auth state.
- Resolution source of truth is the HTTP `Host` header only, matched against `StoreDomain.hostname`, gated by the store's `status=ACTIVE` and the domain's `verification_status=VERIFIED` (fail-closed). A narrow, exact-match, fails-closed development-host allowlist compatibility path exists for local dev with exactly one Store (documented in SAAS_ARCHITECTURE.md §6.3, still current — no code changed this area recently per `git log`).
- **Storefront-facing helper:** `apps.stores.resolution.resolve_store_for_storefront(request)` (`apps/stores/resolution.py:300`) — used by `apps/catalog/views.py` for every public storefront view (`home`, `product_list`, `product_detail`, `collection_index`, `collection_detail`).
- **Product visibility/tenant-safety helper:** `apps.catalog.services.product_publish_service.storefront_visible_products(store, *, now=None)` (`apps/catalog/services/product_publish_service.py:47`) and `storefront_listing_products` (same file, line 60) — every storefront product query is required to pass through one of these; they are the single choke point that guarantees a product from another Store, or an unpublished/scheduled product, is never returned to a public request. `apps/catalog/views.py:346` (`product_detail`) calls `storefront_visible_products(store)` directly, confirming the pattern is live, not just documented.
- **Admin/preview route split:** public storefront home is `apps/catalog/views.py:44 def home(request)`; the staff-only draft preview lives in `apps/storefront_builder/views.py` (`storefront_preview`), gated by `@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)` per the dashboard URL table (still accurate structurally, endpoint list re-verified present in `apps/dashboard/urls.py`).
- **Cache-key / caching:** confirmed still **absent** for storefront rendering — no `CACHES` override in `shop_core/settings.py`, no `cache_page`/`cache.get`/`cache.set` call found anywhere under `apps/storefront_builder` or `apps/catalog/views.py` (re-checked; matches the 2026-08-06 audit's finding, this one specific item has *not* changed since).
- **Tenant-owned media:** `ProductImage`/`ProductVariant` are Store-scoped indirectly via `Product.store` (see §3); no independent media-ownership bug found in the areas inspected.

**Classification: `reuse as-is`.** Tenant resolution, product-visibility scoping, and the preview/public route split are mature, tested, and must not be touched by the five-family work — every new renderer must consume `resolve_store_for_storefront` / `storefront_visible_products` exactly like the existing code, never invent a parallel lookup.

---

## 2. Builder and template system — the central finding for this task

### 2.1 What already exists (verified, current)

`apps/storefront_builder` is a large, mature, actively-developed app (`models.py` 249 lines, `section_registry.py` 948 lines, `services/render_service.py` 393 lines, `services/layout_service.py` 411 lines, `views.py` 827 lines — all have grown substantially since the 2026-08-06 audit's line counts, confirmed by direct `wc -l`).

- **`StorefrontLayout`** (`models.py:76`) — one-to-one per Store, `published_version`/`draft_version` FKs, `uses_visual_storefront_layout` feature flag, idempotent `provision_for`.
- **`StorefrontLayoutVersion`** (`models.py:116`) — immutable-after-publish version carrying `header_config`, `footer_config`, **and `appearance_config`** (all three JSONFields on the same versioned row, `models.py:149-158`) plus `content_fingerprint` (`compute_fingerprint`, `models.py:203`) for drift detection. `Status` = draft/published/archived; `Source` = manual/legacy_bootstrap/industry_template/restored.
- **`StorefrontSection`** (`models.py:219`) — `section_key` + `order` + `is_active` + `settings` JSONField + `collapsed_in_editor` (already added, `models.py:235` — this was still `❌ ABSENT` in the 2026-08-06 audit; it is done now).
- **`SECTION_REGISTRY`** (`section_registry.py`) — a fixed Python allowlist, now **22 section types** (grew from 16): `announcement_bar`, `hero_banner`, `image_slider`, `single_banner`, `multi_banner`, `category_grid`, `product_section` (a unified, data-source-aware product section — see below), `featured_products`, `newest_products`, `best_sellers`, `discounted_products`, `amazing_offers`, `brand_carousel`, `promo_cards`, `rich_text`, `image_text`, `trust_features`, `collection_tiles`, `quick_links`, `faq`, `testimonials`, `video_section` (verified via `grep 'key="' section_registry.py`, lines 748-883).
- **`product_section`** (`section_registry.py`, `templates/storefront_builder/sections/product_section.html`) has a real, validated **Data Source contract**: `PRODUCT_SECTION_DATA_SOURCES = ("collection", "category", "brand", "manual", "newest", "discounted", "best_sellers", "most_viewed")` (`section_registry.py:90-93`) with `item_limit` (2-24), `display_mode` (`carousel`/`grid`), title/subtitle length caps, and Store-scoped reference validation delegated to `services/section_data_service.py`. This is exactly the "Data Source" capability the 2026-08-06 architecture-plan document proposed as future work — **it is now built**.
- **Responsive settings** exist per-section (`templates/storefront_builder/partials/section_responsive_fields.html`, `responsive_section_wrapper.html`) — also proposed-as-future in the stale docs, now built.
- **Reorder is atomic** — `git log` shows `storefront-builder: make reorder operations atomic` (commit `79f4b1b`), closing the exact gap the stale audit flagged.
- **Header/footer config validation exists** — `storefront-builder: validate header and footer configuration` (commit `658a747`) closes the exact gap the stale architecture plan flagged (non-removable cart/home-link/footer-column enforcement).
- **Shared page shell exists** — `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html` and `page_shell_footer.html` (confirmed present on disk) are now included by both `preview.html` and the public path, closing the "preview.html vs. home_visual.html duplicate shell" risk the stale audit flagged as its #1 risk (commit `be8bb2a storefront-builder: share preview and live storefront shell`).
- **A "Template + Preset" system already exists** — see §2.2, this is the single most important fact for the rest of this task.

### 2.2 `appearance_registry.py` — an existing, mature Template+Palette system that is architecturally *not* what the master prompt's five families need

`apps/storefront_builder/appearance_registry.py` (297 lines) is a hand-written, code-reviewed, platform-owned registry — structurally the same pattern as `SECTION_REGISTRY` — containing:

- **`TEMPLATE_REGISTRY`**: 10 registered `TemplateDefinition`s (`modern`, `marketplace`, `minimal`, `boutique`, `luxury`, `tech`, `editorial`, `compact`, `playful`, `glass` — `appearance_registry.py:209-297`). Each defines `font`, `radius`, `button_radius`, `button_style`, `density`, `motion`, `type_scale`, `content_width`, `grid_density`, `card_shadow`, `card_hover`, `hero_style` (`"wide"|"tall"|"split"`), and a gallery `swatch`.
- **`PALETTE_REGISTRY`**: 20 registered `PaletteDefinition`s (8 colors each), independent of template.
- Per-store selection lives in `StorefrontLayoutVersion.appearance_config` (`template_slug`, `palette_slug`, `color_overrides`, `font`, `radius`, …, `appearance_registry.py:60-73`, defaults exactly matching pre-existing `ShopSettings` colors so un-migrated stores see zero visual change) — Draft/Publish/Rollback-aware, exactly like header/footer.
- **Explicitly, by design, not a DOM fork.** The commit that introduced it (`d08b762`) states outright: *"shared renderer + design tokens + closed CSS variants, not N templates × M sections = N×M forked Django templates… SECTION_REGISTRY is untouched — templates never gate which section types exist."* Every structural field becomes a CSS custom property (`--sfb-content-width`, `--sfb-radius`, …) or a `[data-sfb-*]` attribute selector, consumed by existing shared CSS files (`tokens.css`, `base.css`, `layout.css`, `product_card.css`, `home.css`).

**Verified proof that this is a single shared DOM, not per-template markup:**
- Exactly **one** header partial platform-wide: `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html` (confirmed — no per-template variant files exist alongside it).
- Exactly **one** footer partial: `page_shell_footer.html` (same directory, same finding).
- Exactly **one** product-card partial platform-wide: `apps/catalog/templates/catalog/partials/product_card.html` (44 lines, read in full) — a single fixed DOM (`<a class="pcard">` → `.img` with `object-fit:var(--sfb-image-fit, cover)` → wishlist button → badges → add-bar → `.body` with brand/name/rating/price stacked). Its image ratio, title alignment, and information layout are **not** switchable per template; only color/radius/shadow/hover-transition vary via CSS tokens.
- Exactly **one** product-detail page template/view: `apps/catalog/templates/catalog/product_detail.html`, rendered by the single `apps/catalog/views.py:346 def product_detail(...)` — there is no per-template product-page composition today, for any of the 10 existing templates.

### 2.3 Why this matters — the material conflict this audit must surface, not resolve silently

The master prompt requires, for the five new families, **"real component/partial/renderer branches"** for product cards (`square_centered_commerce`, `premium_portrait`/`premium_campaign`, `artisan_story_card`, `fashion_portrait_gallery`, `catalog_second_image`) with genuinely different image aspect ratios (1:1 vs. 3:4 vs. 9:12 vs. ~7:8), different title/price alignment (centered vs. split-left/right), different presence/absence of elements (wishlist icon, maker/region metadata, second-image crossfade, a bottom action rail) — and explicitly states *"A single DOM with five CSS class names fails the design requirement."* The same is true structurally for headers (three-tier utility+mega-menu vs. quiet two-level vs. story-rail+big-search) and for product-page composition (compact price-led vs. large-gallery-with-thumbnails vs. story-adjacent purchase panel).

The **existing, working, well-tested `appearance_registry.py` system does the opposite on purpose** — one shared header DOM, one shared footer DOM, one shared product-card DOM, one shared product-detail template, varied only through CSS tokens/data-attributes. This is a deliberate, documented, recent architectural decision (not a legacy gap), reviewed and merged as of `d08b762`/`276bc79`/`88f32a3`.

**This is a genuine, material, currently-unresolved conflict between (a) the master prompt's explicit acceptance criteria for the five families and (b) the repository's most recent, intentional design direction for "templates."** It changes visible behavior, Builder data shape, and implementation scope depending on how it is resolved, so per the source-precedence policy this is **not** something to resolve silently — it is written up as a blocking owner question (see `09_QUESTIONS_FOR_OWNER_FA.md`, the architecture-naming/coexistence question). Three broad resolution shapes exist (a new higher-level "family" concept that forks header/hero/card/product-page DOM and sits *above* the existing 10 CSS-token templates for cross-cutting color/font/radius/motion re-use; retrofitting some of the 10 existing template slugs to also carry DOM-fork identity; or replacing the existing 10-template system entirely) — this audit does not pick one.

**Classification:**
- Section Registry, Data Source contract, responsive settings, atomic reorder, header/footer validation, shared page shell, `MerchantCollection` (§6): **`reuse as-is`** — build the five families' homepage content on top of these unchanged.
- `appearance_registry.py` (`TEMPLATE_REGISTRY`/`PALETTE_REGISTRY`/`appearance_config`) for **color, font, radius, density, motion, button style within a family**: **`extend safely`** — very likely the right mechanism for "palette/typography/motion/density stay independently overrideable after choosing a family," which the master prompt requires (§ "Non-negotiable architecture").
- A DOM-forking concept above/alongside it for header/hero/product-card/product-page anatomy per family: **`new shared capability`** — does not exist today in any form; must be designed fresh (see `08_TARGET_ARCHITECTURE_AND_FILE_PLAN.md`).
- Whether the 10 existing CSS-token templates and the 5 new DOM-forked families are the same registry, two separate registries, or the 10 are superseded: **`blocked pending owner answer`.**

---

## 3. Content and commerce models

- **`Product`** (`apps/catalog/models.py:118`) — Store-scoped (`Vendor`/`Category`/`Brand`/`Product` are all Aggregate Roots with direct `store` FK per `docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md` §12.2, re-verified: `Product.store` present).
- **`ProductVariant`** (`apps/catalog/models.py:477`) — generic attribute/value engine (not hardcoded "color"/"size"), `value_hex` for swatch color, `sku`, `stock`, independent `price`/`compare_at_price` (falls back to `product.price + extra_price` when unset), `combination_key` for multi-axis combinations, `is_default`, `is_obsolete`. `store` FK is a denormalized mirror of `product.store` (required because SQLite can't express a cross-join `UniqueConstraint`), never independently settable.
- **`ProductImage`** (`apps/catalog/models.py:316`) — **already supports variant-aware image switching**: `variant` FK (image tied to one full variant combination) **and** a separate `option_value` FK (image tied to a single attribute value, e.g. "red", independent of other axes — enables color-swatch-driven image switching before size is chosen). This directly satisfies the master prompt's "product variant images must switch with the selected attribute combination, especially color" requirement **at the data layer already** — the five families only need to consume it in their gallery renderer, not build it.
- **`ProductVideo`** (`apps/catalog/models.py:362`) — `Source` choices already include `YOUTUBE` and `APARAT` (`models.py:369-370`), plus Instagram permalink support (`product_video_service.instagram_permalink`, referenced `models.py:395`) — the master prompt's "optional product video capability (Aparat/YouTube)" is **already built**, not a gap.
- **`Specification`** (`apps/catalog/models.py:1946`) and **`Review`** (`apps/catalog/models.py:2028`) exist as Store-scoped-through-`Product` children.
- **`Brand`**/`Vendor` exist as separate Aggregate Roots (supplier-like data available for product pages).
- **`MerchantCollection`/`MerchantCollectionItem`** (`apps/catalog/models.py:1232`, `1300`) — **a real, independent Collection model now exists** (not the `ProductTag(purpose="collection")` workaround the stale audit describes as the *only* option). Full stack present: `apps/catalog/services/collection_service.py`, dashboard CRUD (`apps/dashboard/templates/dashboard/collection*.html`), public collection pages (`apps/catalog/templates/catalog/collection_index.html`, `collection_detail.html`, `apps/catalog/views.py:401,410`), a legacy-tag migration tool (`apps/catalog/management/commands/migrate_legacy_product_tag_collections.py`), and dedicated tests. This closes the single largest gap the stale `STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md` flagged.
- **Cart/add-to-cart:** `product_card.html` posts via `hx-post="{% url 'cart:add' product.slug %}"` (htmx, no full page reload) — the five families' product cards should reuse this same interaction pattern, not invent a new cart endpoint.

### 3.1 Verified commerce-data gaps relevant to specific families

A second, independent pass (background research agent, cross-checked by me with the greps below) surfaced several concrete absences that matter for specific families' acceptance criteria, not just "presentation":

- **No `is_featured` field on `Product`.** Confirmed by the repository's own code comment: `apps/storefront_builder/services/render_service.py:159` — *"هیچ فیلد `is_featured`ای در `Product` وجود ندارد (شکاف تأییدشده…)"*. The `featured_products` section silently aliases to the newest-products query. Relevant to any family's "پیشنهادهای امروز"/featured-collection section — it will in practice always show newest, not merchant-curated-featured, unless a `data_source` of `collection`/`manual` is used instead (which does exist and does work).
- **`related_products` is a live query, not a stored field/relation** (`apps/catalog/views.py:312-333`, `apps/catalog/templates/catalog/product_detail.html:275`) — fine for reuse, but means a family's product-page "related products" section is always "system-computed similar products," never a merchant-curated list, unless new capability is added.
- **No size-guide field/model anywhere** (`grep -rni "size_guide|size guide|راهنمای سایز"` → zero results in `apps/catalog/models.py` and `product_detail.html`). This directly affects `heritage_premium` ("راهنمای سایز") and `modern_fashion` ("Size chart") from the lightweight package's contract — a size guide is not a data-layer gap that can be silently invented as a template default; it needs an owner decision (free-text/rich-text per product? per category? out of scope for v1?).
- **No installment/campaign-pricing field anywhere** (`grep -rni "installment|قسط"` → zero results). `amazing_offers`' countdown timer is **not driven by real campaign data** — `render_service.py:155` hardcodes `deadline = timezone.now() + timedelta(hours=8)` on every single render, unconditionally. This is a real, verified instance of exactly the anti-pattern the master prompt explicitly forbids for the new families ("campaign/discount/installment UI must be optional and provider-neutral," "no reference-domain… campaign content… hard-coded"). The five families must not copy this pattern; if `heritage_premium`'s optional campaign/installment badge is implemented, it needs a real, merchant-controlled data source (a section setting, not a hardcoded timer) — an explicit target-architecture decision, not a silent copy of the existing `amazing_offers` approach.
- **Two coexisting variant-attribute systems**, not one: the simple `ProductVariant.attribute`/`value` free-text pair (§3 above) **and** a separate, more structured multi-axis `ProductOption`/`ProductOptionValue` model pair (`apps/catalog/models.py:1339`, `:1394`) that `ProductImage.option_value` (§3 above) actually points at for option-driven image switching. Any family's variant/color selector UI must be built against whichever of these two is the one a given store actually has populated — this is an existing repository duality (pre-dating this task), not something the five families should try to unify or pick a side on without an explicit, separately-scoped decision; they should render whichever data the store has, exactly like the existing product-detail page does.

**Classification: `reuse as-is`** for the commerce-data capabilities the five families need directly (variants, variant images, video, collections, reviews, brand/vendor) — all exist and are Store-scoped correctly, so no new commerce model is justified by anything found in this audit. **`blocked pending owner answer`** specifically for size-guide content (no existing field to hang a family's "size guide" UI element off of) — see the questions document. **`extend safely`** for a real, merchant-controlled campaign/installment data source if `heritage_premium`'s optional campaign badge is approved in scope.

---

## 4. Publishing lifecycle

- `apps/storefront_builder/services/layout_service.py` (411 lines) — `get_or_create_draft`, `publish` (rate-limited, atomic, archives the prior published version, computes `content_fingerprint`, and is the **only** place `uses_visual_storefront_layout` is set True), `discard_draft`, `restore_version` (never publishes directly — always creates a new Draft with `source=RESTORED`, cross-store references fail closed), `apply_industry_layout`.
- `apps/storefront_builder/services/render_service.py` (393 lines) — `build_render_items(version, store)` is the single function consumed by **both** the staff preview and the public `home()` view; unknown section keys are silently skipped (a removed section type never breaks the public page); a per-request per-section-key cache avoids duplicate queries for repeated section types.
- **Migration safety for existing stores:** `apps/storefront_builder/services/bootstrap_service.py` converts a store's current hard-coded homepage into equivalent sections on first Draft creation; `apps.catalog.views.home()` still falls back to the legacy `catalog/home.html` until a store has **both** `uses_visual_storefront_layout=True` **and** a `published_version` — i.e., a store that never touches the Builder is provably unaffected.
- This entire lifecycle (Draft → Preview → Publish → Rollback, feature-flagged per store, non-destructive bootstrap) is exactly the mechanism the five families must plug into for their own selection (most likely as one more key inside `appearance_config`, or a sibling concept — see target architecture doc) — **no new Draft/Publish/Rollback machinery should be built.**

**Classification: `reuse as-is`.**

---

## 5. Frontend and quality infrastructure

- **RTL/Persian typography:** `dir="rtl"` is the platform default (confirmed in the lightweight package's own CSS and consistent with `apps/core` static assets); `FONT_CHOICES = ("Vazirmatn", "Tahoma", "Arial", "Georgia")` (`appearance_registry.py:34`) is the curated, RTL-appropriate font allowlist merchants pick from — "merchant picks a font by name, never uploads raw CSS," per the file's own docstring. `TYPE_SCALE_SIZES` (`appearance_registry.py:42-46`) gives a 5-role typographic scale (heading/body/product_name/price/muted) at three densities.
- **CSS architecture:** token-driven (`tokens.css`, `base.css`, `layout.css`, `product_card.css`, `home.css` — referenced by the appearance-registry docstring and commit messages; no CSS-in-JS, no bundler).
- **Accessibility / motion:** `prefers-reduced-motion` is already respected **globally**, independent of the active template's own motion setting (per `d08b762`'s commit message, i.e. a template cannot force motion on a user who has requested less).
- **Testing:** Django test runner, no pytest. `apps/storefront_builder/tests/` and `apps/catalog/tests/test_collection_*.py` are the most relevant existing suites; exact current file/line counts were not re-tallied in this pass (they have grown well past the 2026-08-06 figures given the 61 additional commits) — the five-family test plan should follow the same structure (model / service / view+permission / end-to-end / regression) documented in the (otherwise stale) `STOREFRONT_TEMPLATE_AND_BUILDER_IMPLEMENTATION_ROADMAP.md` §6, which remains valid *methodology* even though its subject-matter status table is outdated.
- **SEO/structured data:** JSON-LD (`application/ld+json`) is present on both `apps/catalog/templates/catalog/home.html` and `apps/catalog/templates/catalog/product_detail.html` (confirmed via grep on both files); `collection_detail`/`product_detail` are real per-store pages (a prerequisite for tenant-owned canonical URLs). Full schema completeness (Breadcrumb, Offer availability/price-currency correctness per family) was not traced field-by-field in this pass — flagged as a smaller open item for the target-architecture doc rather than a blocking question.
- **Media ownership is DB-row-only, not filesystem-namespaced by Store** — uploaded product/section images are not stored under a per-Store path prefix or bucket; ownership is enforced only by the owning row's `store` FK, not by storage-path isolation. Acceptable today because all such media is meant to be publicly servable storefront content (no private-media confidentiality requirement exists for it), but worth naming explicitly since the master prompt's security checklist asks about "tenant-owned media validation" — the answer is "row-level only," not "storage-path-level," and the five families should not assume path-level isolation exists.
- **CI:** none — no `.github/` directory (confirmed in `00_REPOSITORY_BASELINE.md`).

**Classification:** RTL/typography/motion infra: **`reuse as-is`**. Structured-data completeness: **`extend safely`** (verify and fill gaps per family during implementation, not a Gate-2 blocking question).

---

## 6. Gap classification summary

| Capability | Status | Classification |
|---|---|---|
| Tenant resolution, product visibility scoping | Mature, tested | `reuse as-is` |
| Draft/Preview/Publish/Rollback lifecycle | Mature, tested | `reuse as-is` |
| Section Registry (22 types) + Data Source contract | Mature, tested | `reuse as-is` |
| Responsive per-section settings | Built | `reuse as-is` |
| Merchant Collections (real model) | Built | `reuse as-is` |
| Product variant/option-value image switching | Built (data layer) | `reuse as-is` (families must consume, not rebuild) |
| Product video (YouTube/Aparat/Instagram) | Built | `reuse as-is` |
| Palette/font/radius/density/motion selection (`appearance_registry.py`) | Built, mature | `extend safely` — likely the right substrate for family-level palette/typography overrides |
| Genuinely different header/hero/product-card/product-page DOM per family | **Does not exist** — current system is explicitly one shared DOM + CSS tokens | `new shared capability` — and the central open architecture question of this task |
| Storefront render caching | Absent | `out of current scope` for this task unless the owner asks for it (not required by the master prompt) |
| Structured data (Product/Offer/Breadcrumb) completeness per family | Not fully traced | `extend safely` |
| CI workflows | Absent | `out of current scope` |

**No `blocked pending owner answer` items remain unclassified beyond the single architectural question in §2.3** — everything else in this section has a clear, evidence-backed classification.
