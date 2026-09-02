# A8 component evidence inventory

## Method and boundary

Evidence inspected on 2026-09-02: the Design Lab prototype at
`C:/Users/hp/Downloads/RastiSi_50_Storefront_Design_Lab_TABBED_THEMES (1).html`,
the R4 Store Appearance registry/adapters, global-region and section registries,
appearance registry, and Ready Template registry. Prototype markup, CSS, JS,
numeric IDs, copied copy, countdowns, and campaign state are evidence only; none
are production payloads. Production identities below are semantic, versioned keys.

Baseline command reported 46 components in ten families: header 10, mega_menu 1,
hero 6, layout 8, product_view 6, card 1, badge 1, motion 3, footer 8, bottom_nav
2. The current official catalog is eight presets: `dense_marketplace@2`,
`premium_leather@2`, `warm_boutique@2`, `fashion_promo_catalog@7`,
`playful_lifestyle@1`, `utility_catalog@1`, `editorial_jewelry@2`, and
`dark_digital@2`.

## Existing production vocabulary (reuse first)

| Family | Existing R4 primitives | A8 decision |
| --- | --- | --- |
| Header | `legacy_default`, `marketplace_search_first`, `premium_three_column`, `boutique_centered`, `dark_tech`, `promo_search_nav`, `beauty_search_nav`, `chocolate_centered_search`, `atelier_nav`, `luxury_search` | Reuse when topology matches; add only generic structural variants. |
| Hero | `legacy_default` plus registered `hero_banner` variants (6 total) | Reuse basic image/split/slider treatment; create semantic generic variants for bento, product-focus, search-first, mosaic, and editorial gallery. Countdown is excluded without domain timing truth. |
| Layout | Existing container layouts (8 total) | Reuse columns, rail, list, bento, and featured composition; generic zigzag/catalog variants only where no current equivalent exists. |
| Product view | `product_section` and `catalog_product_wall` variants (6 total) | Reuse data-backed grid/rail/wall; presentation additions must remain card overlays. |
| Card/badge | `card.legacy_default.v1`, `badge.none.v1`; underlying card styles: `standard`, `compact`, `minimal`, `fashion_sale`, `beauty_retail`, `chocolate_retail`, `retail_list`, `luxury_dark` | Register presentation-only card/badge styles; never change price, stock, variants, URLs, wishlist, rating, or quick-add truth. |
| Motion | `none`, `subtle`, `dynamic` | Reuse, respecting reduced motion. |
| Footer | `legacy_default`, `marketplace_dense`, `premium_columns`, `boutique_editorial`, `dark_tech`, `promo_columns`, `beauty_retail_columns`, `chocolate_dark_columns` | Reuse or add generic minimal/editorial/app/playful structures with real merchant links/data. |
| Bottom nav | `hidden`, one current mobile nav variant (2 total) | Add only accessible generic nav layouts; all use real named URLs/cart count, RTL, safe-area offset, and mobile-only display. |

## Prototype primitive normalization

The following inventory deliberately records prototype aliases as evidence in the
first column only. “New” means a future generic registered component, not a
template-specific partial. All renderer targets are platform-owned partials under
`storefront_builder/partials/` or existing trusted registry renderers.

| Prototype evidence / family | Visual evidence | Nearest R4 primitive / decision | Proposed stable semantic key | Renderer / responsive contract / compatibility | Used by prototype recipes |
| --- | --- | --- | --- | --- | --- |
| h1 row-minimal; header | single quiet row, logo/nav/actions | `atelier_nav`; reuse | `header.editorial_row.v1` | existing global header; collapse nav to menu | 01,04,17,18,23,27,38,50 |
| h2 marketplace-multiline; header | utility/search/category rows | `marketplace_search_first`; reuse | `header.marketplace_search.v1` | existing global header; search stacks on mobile | 02,09,11,20,22,24,29,46 |
| h3 centered-brand; header | announcement + centered logo | `premium_three_column`; reuse | `header.centered_brand.v1` | existing global header; actions retain labels | 06,08,14,31,40,49 |
| h4 floating-pill; header | floating compact nav | no exact match; new generic | `header.floating_compact.v1` | trusted global partial; becomes solid/flow layout on narrow widths | 05,19,23,34,43 |
| h5 sidebar/compact; header | hamburger-led compact shell | `legacy_default`; reuse as compact mode | `header.compact_drawer.v1` | existing header; drawer accessibility required | 16,32,36,39,45 |
| h6 bold-news; header | ticker plus bold nav | `promo_search_nav`; reuse announcement only with real message | `header.promo_bar.v1` | existing global header; no fake scarcity | 07,24,44,48 |
| h7 social-story; header | story shortcut rail | no exact match; new generic discovery strip | `header.community_shortcuts.v1` | trusted partial; horizontally scrollable and labelled | 26 |
| h8 transparent-image; header | overlay row | no exact match; new generic | `header.overlay_transparent.v1` | trusted partial; solid fallback/contrast on mobile | 15,25,33 |
| h9 newspaper; header | masthead and editorial nav | `atelier_nav`; generic editorial variant | `header.editorial_masthead.v1` | trusted partial; hides issue/date metadata unless real | 12,16,27,47 |
| h10 compressed-menu; header | hamburger plus short links | `legacy_default`; reuse | `header.compact_menu.v1` | existing global header; accessible menu | 03,21,28,42 |
| h11 tabbed-nav; header | category tabs | no exact match; new generic | `header.category_tabs.v1` | trusted partial; scrollable tabs on mobile | 13,37 |
| h12 playful-awning; header | decorative canopy | `boutique_centered`; generic playful decoration | `header.playful_canopy.v1` | trusted partial; decoration omitted in reduced/mobile layout | 10,30,35,41 |
| x0–x13; hero | none, immersive, split, bento, type, product, offer, collage, slider, video, calm, search, mosaic, social grid | existing hero where equivalent; otherwise generic, data-backed | `hero.none`, `hero.immersive`, `hero.editorial_split`, `hero.promo_bento`, `hero.typographic`, `hero.product_focus`, `hero.image_collage`, `hero.side_offer_slider`, `hero.media_feature`, `hero.quiet`, `hero.search_first`, `hero.campaign_mosaic`, `hero.social_gallery` (all `.v1`) | trusted section variants; stack/crop safely; media requires merchant media; offer/countdown states are suppressed without truth | all base recipes |
| x14–x19; Lab-only heroes | product orbit, Persian arch, wholesale, social post, triptych, dual deal | evidence only; not selected by base 50 | documented Lab-only | no production renderer in A8 mapping | none |
| circle/tile/arch/chip/list; category discovery | round shortcuts, tiles, arches, pills, numbered list | `category_grid` modes where equivalent; add generic modes as needed | `discovery.circular`, `tile`, `editorial_arch`, `chips`, `indexed_list` (all `.v1`) | section renderers; horizontal scroll or 2-up at mobile | all base recipes |
| icon/strip/mosaic/index/mini; category discovery | compact icons, strip, mosaic, index, mini cards | Lab-only and unused by base 50 | documented Lab-only | no A8 production selection | none |
| c-flat/c-market/c-edit/c-row/c-lux/c-pill/c-glass/c-polaroid/c-price/c-circle/c-index/c-label/c-shelf/c-spec/c-neon/c-brutal; card | sixteen presentation compositions | map to existing styles first; add generic presentation styles where necessary | `card.standard`, `marketplace_price`, `editorial_minimal`, `retail_row`, `luxury_dark`, `soft_capsule`, `beauty_glass`, `paper_frame`, `price_first`, `portrait_round`, `catalog_index`, `shipping_label`, `shelf_editorial`, `technical_spec`, `tech_neon`, `bold_outline` (all `.v1`) | shared product-card partial only; 2-up mobile except list rows; commerce truth unchanged | all base recipes |
| g2/g3/g4/g5/rail/list/bento/feat/zig; product composition | 2–5 columns, rail, list, bento, feature, zigzag | current layouts/product views first; add generic composition variants | `layout.two_column`, `three_column`, `four_column`, `dense_five`, `horizontal_rail`, `catalog_list`, `bento_grid`, `featured_split`, `editorial_zigzag` (all `.v1`) | registered composition; columns reduce to 2/1, rails scroll | all base recipes |
| p01–p10; promotional treatment | flash, coupon, delivery, seasonal, inventory, member, marquee, dual, quiet | generic only; countdown/stock/season claims require real data | `promo.flash`, `coupon`, `delivery_note`, `member_note`, `brand_marquee`, `dual_campaign`, `quiet_notice` (all `.v1`) | trusted sections; conditional omission where truth absent; no occasion overlay | evidence only in base sequence aliases |
| min/mega/edit/story/brutal/center/app/wave; footer | minimal, dense columns, wordmark, story, bold, centered, app, playful | existing footer variants first; generic variants where missing | `footer.minimal`, `marketplace_columns`, `editorial_wordmark`, `brand_story`, `bold_columns`, `centered`, `app_download`, `playful_wave` (all `.v1`) | trusted global partial; columns stack, real links/contact only | all base recipes |
| m4/m5/mfab/mdock/mglass/micon/mbig; mobile nav | 4/5 item, raised cart, floating/glass dock, icon, wide cart | current mobile nav plus generic variants | `bottom_nav.four_item`, `five_item`, `raised_cart`, `floating_dock`, `glass_dock`, `minimal_icons`, `wide_cart` (all `.v1`) | mobile-only, RTL, focus labels, safe-area/content offset, real URLs/cart count | all base recipes |
| palette/type/density/width/radius | 50 palettes; 8 type, 5 density, 5 width, 6 radius concepts | typed appearance registry only | palette slug + registered font/density/content-width/radius | bounded tokens, no raw CSS; mobile width is fluid | all base recipes |
| 38 section sequences | hero/category/product/promo/trust/story/news combinations | existing sections and bounded recipes | `composition.home_*` semantic recipes | merchant-ID-free section entries; no demo data | 01–50 |

## Decisions and concerns

* The prototype has 12 headers, 20 heroes, 10 category modes, 16 cards, 9 product
  layouts, 10 promotion treatments, 8 footers, 7 mobile navs, 50 palettes, and 38
  distinct section sequences. It is not a runtime dependency.
* Base recipes use only x0–x13 and category circle/tile/arch/chip/list. x14–x19
  and icon/strip/mosaic/index/mini remain Lab-only evidence.
* Promotional countdown, stock, coupon, occasion, and member claims cannot be
  represented until commerce truth exists. A8 may render only real data-backed
  generic treatments or omit them.
