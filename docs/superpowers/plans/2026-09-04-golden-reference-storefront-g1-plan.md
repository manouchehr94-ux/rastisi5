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

## C. Golden apply mechanism (idempotent, production contracts)

Add a **focused, idempotent Golden composition applier** that runs *after* the existing seed
establishes catalog/content + baseline template. It:

1. Loads the `rasti-mode-demo` store + its draft (`layout_service.get_or_create_draft`).
2. Selects palette `theme-forest-cream`, header `marketplace_search_first`, footer
   `premium_columns`, bottom nav `five_item` via the existing appearance/config contracts.
3. Sets the Home composition from §B via the existing preset/section services.
4. `layout_service.publish(store)`.

Re-running converges (idempotent): it rebuilds the Home page deterministically from the same
spec and re-publishes; it never creates duplicate stores/products/collections (those come from
the idempotent base seed). Preferred surface: extend the existing demo command with a
`--golden` composition step (or a thin dedicated `apply_golden_reference_storefront` command
that calls the base seed then applies §B), so `rasti-mode-demo` is reproducible with one
documented command. **Only** the `rasti-mode-demo` slug is ever touched; destructive
baseline-apply is never used on protected/real stores.

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
- **R5:** New Arrivals / Best Sellers / Special Offer are one reused `product_section` each with
  `data_source` = `newest` / `best_sellers` / `discounted` — no duplicated catalog truth.
