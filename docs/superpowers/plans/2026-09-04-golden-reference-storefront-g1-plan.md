# Golden Reference Storefront — G1 Executable Plan (Global Shell + Complete Home)

**Date:** 2026-09-04
**Branch:** `golden/g1-reference-storefront`
**Base commit:** `ac2fd5dcad7b4952b02ed42995143e2cfd2504e3`
**Authority:** `../specs/2026-09-04-golden-reference-storefront-design.md`
**Method:** subagent-driven TDD (RED → implement → GREEN), fresh reviewer per task, local commit
per independently-testable task, persistent ledger, final whole-G1 review.

> Baseline `ac2fd5d`. Phase-1 implementation absent/deferred. G1 uses only APIs present at
> `ac2fd5d` (notably `preset_service.apply_preset_with_checkpoint` + `layout_service.publish`,
> the same path the demo seed already uses). No 51st template. One renderer. Reuse-first.

---

## A. Reuse map (verified at `ac2fd5d`)

- **Renderer path:** `apps/catalog/views.py::home` → `storefront_context_service.build_universal_storefront_context(request, store, "home")` → `page_resolution_service.resolve_published_page` (PUBLISHED only) → `render_service.build_page_render_items` + `group_items_into_rows` + `build_container_render_items`; global chrome via `render_service.store_appearance_global_renderer_template(..., "header"|"footer"|"bottom_nav")`; template `catalog/home_visual.html`. **A store must have a PUBLISHED V2 layout or it falls back to legacy `catalog/home.html`.**
- **Compose/publish contract:** `layout_service.get_or_create_draft(store)`, `preset_service.apply_preset(draft, preset)` / `apply_preset_with_checkpoint(store, preset)`, `layout_service.publish(store)`. Section entries via `layout_preset_registry.PresetSectionEntry(section_key, settings, row_key, row_span)`.
- **Baseline Ready Template:** `fashion_promo_catalog` (unchanged; the demo seed already applies it via `--ready-template`).
- **Palette:** `theme-forest-cream` (registered).
- **Shell variants:** header `marketplace_search_first` (logo+search+nav+category **Mega Menu**+account/wishlist/cart+mobile burger/search/nav), footer `premium_columns`, mobile bottom nav `five_item`. Cart badge (`cart_count`) always renders on live storefront; cart cannot be disabled (`validate_header_config`).
- **Sections (all existing registered keys):** `hero_banner`, `category_grid`, `product_section` (data_source `newest`/`discounted`/`best_sellers`), `brand_carousel`, `multi_banner`, `story_rail` (max 1), `collection_tiles`, `trust_features` (max 1), `newsletter` (max 1), `image_text`, `promo_cards`, `catalog_product_wall`.
- **Content/Catalog models:** Catalog `Product/ProductImage/Category/Brand/MerchantCollection`; Content `HeroSlide/PromotionalBanner/StoryRailItem/MediaAsset/Menu/FooterSettings`. Hero/Banner/Story are store-scoped and optionally section-scoped.
- **Seed:** `apps/stores/management/commands/seed_ready_template_fashion_demo.py` (idempotent, `STORE_SLUG="rasti-mode-demo"`, seeds 10 categories / 6 brands / 50 products / images / 6 collections / hero / banners / story / nav / footer; `--ready-template <KEY>` applies+publishes). Companion `refresh_rasti_mode_demo_visuals.py` (curated media only; never ProductImage).

## B. Home Composition (commercial rhythm)

All sections are existing registered keys; settings use documented schema fields; **no catalog
IDs, prices, SKUs, or inventory are written into settings** (product data resolves at render
time from Catalog via `data_source`/store-scoped resolution).

| # | section_key | key settings | Role |
|---|---|---|---|
| 1 | `announcement_bar` | (store announcement) | Announcement |
| 2 | `hero_banner` | `hero_style=overlay`, autoplay, dots | Editorial hero (store/section HeroSlides) |
| 3 | `category_grid` | `display_mode=circular`, `item_limit=8` | Quick categories (discovery) |
| 4 | `multi_banner` | promotional banners | Featured campaign / editorial promotion |
| 5 | `product_section` | `data_source=newest`, `display_mode=carousel`, `title="جدیدترین‌ها"` | New arrivals |
| 6 | `brand_carousel` | `display_mode=carousel` | Brand strip |
| 7 | `multi_banner` | 2–3 promo banners | Promo banners |
| 8 | `product_section` | `data_source=best_sellers`, `display_mode=grid`, `title="پرفروش‌ترین‌ها"` | Best sellers |
| 9 | `story_rail` | store StoryRailItems | Story / editorial rail |
| 10 | `product_section` | `data_source=discounted`, `display_mode=campaign_band`, `title="پیشنهاد ویژه"` | Special offer / promotion |
| 11 | `collection_tiles` | `tile_style=grid` | Curated collections |
| 12 | `trust_features` | service items | Trust / services |
| 13 | `newsletter` | title/subtitle/button | Newsletter |
| (14) | Footer | `premium_columns` (global region) | Footer |

Rhythm: hero/editorial impact → discovery → products (new) → brand → campaign → products
(best) → story → promotion → collections → trust → newsletter/footer.

## C. Golden apply mechanism (idempotent, production contracts) — CORRECTED MODEL

A Ready Template's identity+version must always describe its **actual registered authored
DNA**. Therefore the Golden setup must **not** hand a modified preset object to `apply_preset`
while keeping the official `fashion_promo_catalog` key/version — that would make
`template_baseline_snapshot` (the pure authored template truth the future Phase‑1 reset relies
on) lie. The Golden setup instead mirrors exactly what a real merchant does:

1. Seed the resettable `rasti-mode-demo` (real catalog/content).
2. Obtain the **REAL registered** `fashion_promo_catalog` recipe.
3. Discard any stale draft, create a fresh draft, and apply that **unmodified** real preset via
   `preset_service.apply_preset` → the Draft now carries **honest `template_provenance`** AND a
   **truthful `template_baseline_snapshot`** = the authored `fashion_promo_catalog` baseline.
4. **Customize the resulting Draft** the way a merchant would, through existing production
   contracts — and these writes **never touch `template_baseline_snapshot`/`template_provenance`**:
   - Store‑Appearance manifest (header `marketplace_search_first`, footer `premium_columns`,
     bottom‑nav `five_item`; `mega_menu` inherited = `mega_menu.none.v1`) via
     `storefront_appearance.persistence.persist_store_appearance_manifest` (Draft‑only).
   - Identity palette `theme-forest-cream` via the validated `appearance_config`
     (mirrors `apply_preset` palette semantics: set `palette_slug`, clear a
     non‑merchant‑customized `color_overrides`).
   - Header capability flags via `layout_service.validate_header_config`.
   - Home composition (§B) via `section_registry` + `container_service.rebuild_page_from_legacy_rows`,
     replacing **only** the Home page's sections/containers.
5. `layout_service.publish(store)`.

Result: the live Draft/Published = **authored baseline + Golden merchant divergences**, exactly
the model future Phase‑1 semantics expect. Re-running converges (fresh draft each run → re-apply
authored baseline → re-apply Golden customizations); it never duplicates stores/products/
collections (those come from the idempotent base seed). Surface: a thin dedicated
`apply_golden_reference_storefront` command that runs the base seed (`--ready-template
fashion_promo_catalog`) then the Golden apply. **Only** the `rasti-mode-demo` slug is ever
touched; destructive baseline-apply is never used on protected/real stores. No 51st template,
no second preset identity, no second renderer.

### Mega Menu (verified source truth)

The visible category mega menu is an **intrinsic authored feature of the
`marketplace_search_first` header** (its partial renders the real Store category tree,
`nav_categories`). Its truthful, future‑Builder‑editable source is therefore the **Header
selection** (`header.marketplace_search_first.v1`), not a separate component. The `mega_menu`
Store‑Appearance family exposes a single registered component `mega_menu.none.v1`
(`virtual:mega_menu:none` — "no separate mega‑menu overlay"), which is the correct, consistent
selection here; the render pipeline does not consume a `mega_menu` selection for the header, and
`global_region_registry` has no mega‑menu region. No new Mega Menu architecture is introduced.

## D. Task breakdown (each: RED → implement → GREEN → self-review → fresh reviewer → commit)

1. **Golden docs** (this file + design + roadmap) — committed first.
2. **Golden composition applier** — the idempotent mechanism in §C + Golden-specific tests
   (published layout exists; provenance = `fashion_promo_catalog`; palette/header/footer/
   bottom-nav selections; Home section order = §B; re-run convergence / no duplicate rows).
3. **Shell verification** — assert the published store resolves the universal shell and the
   selected header/footer/bottom-nav variants render (renderer/appearance tests).
4. **Home render verification** — assert all §B sections render on the public Home via the
   universal renderer (no legacy fallback), RTL, no empty-section leakage.
5. **Responsive/polish** — verify responsive wrappers + mobile bottom-nav clearance; any CSS
   polish stays in existing token/style files, no parallel color system.
6. **Browser visual QA** — run the dev server, capture desktop (1440) + mobile (390) + tablet
   (768) evidence for Home/Header/Hero/products/campaign/story/bottom-nav/footer; fix defects.
7. **Regression gate** — §E.

## E. Verification gate (before G1 complete)

- Golden-specific tests (new).
- Neighboring: `test_seed_ready_template_fashion_demo_command`, `test_render_service`,
  `test_public_homepage_integration`/`test_phase2_universal_renderer`,
  `test_u2a_global_header_system`, `test_u2b_global_footer_system`, `test_appearance`,
  `test_preset_service`.
- A8 exact-50 contracts: `test_a8_ready_template_catalog`, `test_a8_template_diversity`.
- Seed idempotence check (run seed/golden apply twice; assert row counts converge).
- `python manage.py check`.
- `python manage.py makemigrations --check --dry-run` (expect **no** new migrations).
- `git diff --check`.
- Browser visual QA evidence committed.
- Fresh whole-G1 independent review; resolve CRITICAL/IMPORTANT.

## F. Guardrails

- Do not add to `A8_READY_TEMPLATES`; do not alter the `fashion_promo_catalog` recipe or any
  official template identity.
- Do not introduce a second renderer/registry/lifecycle or a Golden-only engine.
- Do not modify Phase-1 areas (`preset_service`/`r4_mutation_service`/`persistence`) unless
  independently necessary; if unavoidable, justify in the ledger.
- No commerce truth in templates/Builder JSON; no duplicated catalog data.
- Local commits only. **No push. No merge.** Recovery bundle after major milestones.

## G. Recorded small-decision rulings

- **R1:** Baseline template = `fashion_promo_catalog` (already the seed's template; test-backed).
- **R2:** Palette = `theme-forest-cream` (registered; encodes teal/charcoal/gold/warm-neutral).
- **R3:** Header = `marketplace_search_first` (only premium header rendering the real category
  Mega Menu + search + full action cluster + mobile affordances).
- **R4:** Footer = `premium_columns`; Bottom nav = `five_item` (search + cart badge).
- **R5:** New Arrivals / Most-Popular / Special Offer are one reused `product_section` each
  with `data_source` = `newest` / `most_viewed` / `discounted` — no duplicated catalog truth.
- **R6 (visual-QA):** The announcement is rendered by the global header
  (`header_config.announcement_enabled`), not as a separate `announcement_bar` section —
  rendering both duplicated the strip. Home is therefore 12 sections + footer.
- **R7 (visual-QA):** The "Best Sellers" slot uses `data_source=most_viewed` (backed by
  `views_count`, a production-written metric that the Golden setup seeds deterministically),
  not `best_sellers`. Rationale: `best_sellers` is computed live from real `OrderItem` rows
  (the only permitted algorithm), which would require seeding full `Order` + `PaymentGateway`
  + `ShippingMethod` + `Customer` checkout infrastructure purely to populate one Home section
  — disproportionate scaffolding that also reaches further into the Commerce domain than a G1
  *storefront-visual* deliverable should. `views_count`-backed "most popular" is a legitimate,
  boundary-respecting merchandising section. Real order-history-backed Best Sellers is
  deferred to commerce-seeding scope.
