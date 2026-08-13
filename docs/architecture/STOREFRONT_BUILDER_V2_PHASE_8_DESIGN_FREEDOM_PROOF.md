# Storefront Builder V2 — Phase 8 Design-Freedom Proof

Status: evidence document for the mandatory Phase 8 deliverable. Everything
described below was produced by driving the real, production merchant-facing
Storefront Builder UI (Playwright automating an actual browser against the
running dev server — form fills, selects, clicks, submits). No store's
`StorefrontSection`/`appearance_config`/`header_config`/`footer_config` JSON
was written directly to the database, no fixture/JSON design payload was
loaded, no per-store template or Family concept was used, and no
Python-shell design manipulation occurred. Shell access was used only for
infrastructure that is not "design": creating/seeding a store's catalog data
(`seed_rastisi_fashion_demo`, `seed_shop`), resetting two pre-existing test
accounts' passwords so they could be logged into, and adding one missing
`StoreDomain` row so a store that had never been published publicly could be
reached — all recorded explicitly below, none of it touches section
composition, appearance config, or header/footer config.

All three stores render through the exact same `StorefrontLayout` →
`StorefrontLayoutVersion` → `StorefrontPage` → `StorefrontSection` engine,
the same `section_registry.py` allowlist, the same `layout_service.py`
validators, the same `responsive_section_wrapper.html`, and the same public
`catalog:home` template chain. Nothing store-specific exists in code for any
of the three — every difference below is merchant-authored data sitting in
each store's own `StorefrontLayoutVersion` row.

## The three stores

| | Demo A — "Editorial / Story" | Demo B — "Dense Catalog" | Demo C — "Minimal / Boutique" |
|---|---|---|---|
| Store slug | `rastisi-fashion-test` | `kianstock-qa` | `akhlaghi` |
| Vertical | Fashion / apparel | Stock-clearance / discount goods | Generic marketplace |
| Starting point | Layout Preset `editorial_story` (Phase 6 quick-start), then customized | Its existing Phase 6 QA composition (27 home sections), then customized | Never published through the Builder before Phase 8 — first-ever publish |
| Public URL | `http://rastisi-fashion-test.rastisi.localhost:8000/` | `http://kianstock-qa.rastisi.localhost:8000/` | `http://akhlaghi.rastisi.localhost:8000/` |

## Field-by-field diff (all set via the real Builder forms)

| Setting | Demo A | Demo B | Demo C | Builder surface used |
|---|---|---|---|---|
| Palette | `peach` (soft warm) | `digired` (bold shopping red) | `mono` (black & white) | Appearance → Palette gallery |
| Site content width | 1100 (narrow) | 1320 (wide) | 1200 (standard) | Appearance → تنظیمات بیشتر |
| Product grid density | 3 columns | 6 columns | 4 columns | Appearance → تنظیمات بیشتر |
| Card shadow | soft | strong | none | Appearance → تنظیمات بیشتر |
| Card hover effect | zoom | lift | none | Appearance → تنظیمات بیشتر |
| Hero style | tall | wide | split | Appearance → تنظیمات بیشتر |
| Header extra blocks | phone + CTA ("مجموعه جدید") | social links + CTA ("خرید ویژه") | spacer only | Header editor → بلوک‌های اضافی هدر |
| Footer extra block | custom-text ("درباره ما") | link ("پیگیری سفارش") | custom-text ("اخلاقی") | Footer editor → ستون‌های اضافی فوتر |
| Hero/featured section — content width | narrow | full | (no hero section in this composition) | Section settings → اندازه بخش |
| Hero/featured section — height | tall | compact | — | Section settings → اندازه بخش |
| Card image ratio (a product section) | portrait | square | landscape | Section settings → ظاهر کارت محصول |
| Card border | off | on | off | Section settings → ظاهر کارت محصول |
| Card quick-add reveal | hover-fade | always-visible | hover-slide (default) | Section settings → ظاهر کارت محصول |
| Card badge | shown | shown | hidden | Section settings → ظاهر کارت محصول |
| Home section count / composition | 6 sections (story_rail, hero_banner, image_text, featured_products, testimonials, newsletter) | 27 sections (dense hero→banners→9× product carousels→brand carousel→story rail→testimonials→FAQ→trust→newsletter→more banners/image-text) | 7 sections (category_grid, newest, best-sellers, discounted, amazing-offers, brand carousel, trust) | Existing per-store composition, edited/kept via the section list |

None of these fields overlap with a "Template" concept — Template
(`template_slug`) is Phase 8 P0-7's internal-only fallback source and was
never touched by any of these three builds; every value above is either an
explicit merchant choice or (for fields the merchant never visited) falls
back to whatever `template_slug` default that store already had, exactly as
designed.

## What this proves

1. **Same engine, different output.** All three stores load through
   identical Django views (`catalog:home`, `catalog:product-detail`, etc.),
   identical section templates, and identical CSS files. The visual
   difference between a 3-column soft-shadow narrow-content editorial page
   and a 6-column strong-shadow full-width dense catalog page comes entirely
   from data in each store's `StorefrontLayoutVersion`, not from different
   code paths.
2. **No Family, no per-store template file.** grep across the diff shows no
   new template file, no `family_slug`, no per-store Python module — Phase 7
   already retired that architecture and Phase 8 did not reintroduce it.
3. **Composability is real, not cosmetic.** Header/footer extra blocks
   (P0-3/P0-4), per-section card settings (P0-2/P1), per-section layout
   width/height (P0-5), and site-level structural controls (P0-7) all
   independently varied across the three stores and all independently
   persisted and rendered correctly — confirmed both by re-reading each
   store's `effective_appearance_config()`/`effective_header_config()`/
   `effective_footer_config()` from the database after publish (table above)
   and by screenshot of the published public homepage.
4. **Merchant-facing surface only.** Every action was a real click/select/
   fill/submit against `/admin-portal/storefront-builder/...` — the same
   URLs, forms and CSRF-protected POSTs a real merchant uses. No
   `manage.py shell` call ever set `StorefrontSection.settings`,
   `appearance_config`, `header_config`, or `footer_config`.

## Honest caveats found during this pass

Building three real demos through the actual UI surfaced two genuine,
now-fixed issues — recorded here rather than glossed over:

- **Header extra blocks had no mobile-width handling.** Demo A's header
  (phone + CTA block, on top of the pre-existing search/cart/wishlist/
  account icons) caused a real ~19px page-level horizontal overflow at a
  390px mobile viewport — not the cosmetic per-item overflow of the
  legitimately horizontally-scrollable category-pill strip (that one is
  contained by its own `overflow-x` and does not move the page), but an
  actual overflow of `.h-actions` itself. Fixed with a
  `@media (max-width: 480px)` rule in `apps/core/static/css/layout.css`
  that hides the phone/social/CTA header blocks below that width (cart,
  wishlist, account and the hamburger menu — the primary purchase actions —
  stay untouched). Re-verified zero horizontal overflow on all three
  stores' mobile homepages after the fix.
- **Re-selecting a palette the store was already on is correctly a no-op.**
  Demo A's `editorial_story` preset ships `default_palette_slug="terracotta"`
  as its own starting point; the first build attempt "selected" terracotta
  again, which the appearance view correctly treats as `palette_changed =
  False` and therefore does not reset `color_overrides` — this is the
  designed behavior (re-picking the same palette should not discard other
  customization), not a bug, but it meant the first screenshot didn't show
  a real palette change. Re-built with a genuinely different palette
  (`peach`) to get a true before/after; confirmed `color_overrides` cleared
  to `{}` and the palette actually changed on the published page.
- One target store (`akhlaghi`) had zero `StoreDomain` rows and zero seeded
  products going into this phase — pre-existing gaps unrelated to Phase 8
  code, not something any merchant hit through the Builder. A `StoreDomain`
  row and `seed_shop` catalog data were added so the store had a reachable
  public URL and real products to render; neither action touches design.
- `kianstock-qa`'s public homepage shows ~200 pre-existing broken product
  thumbnail `<img>` 404s (missing files under `/media/products/thumbnails/`,
  unrelated to any JS/CSS/rendering code — likely ephemeral-storage media
  that never persisted from an earlier session). Zero JavaScript console
  errors were observed on any of the three stores' Builder or public pages
  in the final QA pass.

## Screenshots

Full-page desktop screenshots of all three published public homepages, plus
mobile (390px) screenshots after the header-overflow fix, were captured
during this pass and are included in the Phase 8 handoff bundle.
