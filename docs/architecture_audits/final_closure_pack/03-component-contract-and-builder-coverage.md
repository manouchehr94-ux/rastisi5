# 03 — Component contract and Builder coverage

Baseline: `audit/storefront-appearance-g23`, HEAD `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`; 2026-09-05.

Evidence convention: **FACT** = source or executed read-only validation; **INFERENCE** = consequence, not an observed production incident; **RECOMMENDATION** = proposed architectural direction; **UNKNOWN** = needs deployment evidence or a Product Owner decision. Source paths are relative to `D:/Projects/RastiSi4_Golden_Manual/`; `:line` identifies the baseline source. No business database was queried or mutated. Existing audit remains unchanged.

Source locator shorthand used below: bare Builder modules (`models.py`, `views.py`, registries, schemas and `r4_views.py`) are under `apps/storefront_builder/`; service modules under `apps/storefront_builder/services/`; typed manifest modules under `apps/storefront_builder/storefront_appearance/`; bare test modules under `apps/storefront_builder/tests/`. Section/partial template names resolve beneath `apps/storefront_builder/templates/storefront_builder/`; `r4/editor.html` resolves to `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`. Catalog/Cart/Content template names resolve beneath the corresponding app's `templates/` directory. Root shells are `templates/base.html` and `templates/storefront_shell.html`. CSS: `apps/core/static/css/tokens.css`, `theme_palette.css`; `apps/catalog/static/css/home.css`, `product_card.css`, `product_list.css`, `product_detail.css`; `apps/storefront_builder/static/css/storefront_builder.css`, `storefront_builder_preview_v22.css`; `apps/cart/static/css/cart.css`.

## Readiness answer

**FACT:** 36 registered section types; 4 R4 SettingsSchema types; **32 without**. All 36 have a legacy validator and a settings-form entry, but a form entry does not mean every validator/default field is editable. There are 30 explicit variant entries across 7 section types. Header22/Footer16/Mobile9 are global variants, not additional section types. Typed manifest family-specific settings allowlists are all empty.

**RECOMMENDATION:** **0 of the 18 requested product families is safe for unrestricted variant expansion now; 18 remain frozen pending convergence.** This uses an end-to-end gate: a family must have a bounded shared data contract, schema-defined settings, agreed global/local appearance precedence, preserved content on switch, one revision boundary including media, and full/fragment/Preview/Public browser evidence. “READY FOUNDATION” below means reuse the existing implementation as a starting foundation, not permission to expand. Brand Showcase is the strongest narrow shared-data/schema foundation; it still lacks the complete shared appearance and certification boundary.

Evidence: `section_registry.py:1957–2482`; `settings_schema.py:310–371`; `r4_mutation_service.py:132–186`; `storefront_appearance/validation.py:52`; `render_service.py:714–845`.

## Every registered section: contract census

Default paths below use the exact template key under `storefront_builder/sections/`, physically under `apps/storefront_builder/templates/`. Loader functions are in `apps/storefront_builder/services/render_service.py:52–651`. These tables jointly define every required field for every row. Shared renderer = yes for all rows when present and active on an allowed page; that is not outer-envelope parity. Usage counts distinct recipes out of **50 latest Ready Templates**, not section instances or deployed stores.

| Section key | Product family | Default renderer | Explicit variants / selector | Data loader | Business owner | R4 schema / legacy validator | Ready use /50 | Recommended status |
|---|---|---|---|---|---|---|---:|---|
| announcement_bar | Ribbon/Promo | announcement_bar.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 4 | ADAPT |
| hero_banner | Hero | hero_banner.html | overlay, split, beauty_editorial, chocolate_carousel, atelier_triptych, luxury_showcase / hero_style | _hero_banner_context | Content placements/MediaAsset | Yes / Yes | 45 | ADAPT |
| fashion_lifestyle_hero | Hero | fashion_lifestyle_hero.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 0 | SPECIALIZED |
| image_slider | Slider | image_slider.html | 0 explicit; default | _image_slider_context | Content placements/MediaAsset | No / Yes | 0 | ADAPT |
| single_banner | Ribbon/Promo | single_banner.html | 0 explicit; default | _single_banner_context | Content placements/MediaAsset | No / Yes | 0 | ADAPT |
| multi_banner | Ribbon/Promo | multi_banner.html | 0 explicit; default | _multi_banner_context | Content placements/MediaAsset | No / Yes | 0 | ADAPT |
| category_grid | Category | category_grid.html | grid, carousel, circular, image_strip, fashion_flat, fashion_mosaic, beauty_icons, chocolate_story, chocolate_badges, atelier_mosaic, luxury_shortcuts / display_mode | _category_grid_context | Catalog Category | No / Yes | 49 | ADAPT |
| featured_products | Product Showcase | featured_products.html | 0 explicit; default | _featured_products_context | Catalog/pricing/collections | No / Yes | 0 | MIGRATE |
| newest_products | Product Showcase | newest_products.html | 0 explicit; default | _newest_products_context | Catalog/pricing/collections | No / Yes | 0 | MIGRATE |
| best_sellers | Product Showcase | best_sellers.html | 0 explicit; default | _best_sellers_context | Catalog/pricing/collections | No / Yes | 0 | MIGRATE |
| discounted_products | Product Showcase | discounted_products.html | 0 explicit; default | _discounted_products_context | Catalog/pricing/collections | No / Yes | 0 | MIGRATE |
| amazing_offers | Product Showcase | amazing_offers.html | 0 explicit; default | _amazing_offers_context | Catalog/pricing/collections | No / Yes | 0 | SPECIALIZED |
| brand_carousel | Brand Showcase | brand_carousel.html | grid, carousel, beauty_tabs / display_mode | _brand_carousel_context | Catalog Brand | Yes / Yes | 2 | READY FOUNDATION |
| promo_cards | Ribbon/Promo | promo_cards.html | 0 explicit; default | _category_context_for_promo_cards | Catalog Category | No / Yes | 0 | ADAPT |
| rich_text | Story/Editorial | rich_text.html | 0 explicit; default | _static_context | Section JSON / shared live context | Yes / Yes | 7 | ADAPT |
| image_text | Story/Editorial | image_text.html | right, left / image_position | _resolved_destination_context | Section JSON / shared live context | No / Yes | 17 | ADAPT |
| blog_posts | Story/Editorial | blog_posts.html | 0 explicit; default | _blog_posts_context | Blog domain | No / Yes | 0 | ADAPT |
| product_section | Product Showcase | product_section.html | carousel, grid, campaign_band / display_mode | _product_section_context | Catalog/pricing/collections | Yes / Yes | 40 | ADAPT |
| catalog_product_wall | Product Showcase | catalog_product_wall.html | rows, group_columns, featured_row / layout_mode | _catalog_product_wall_context | Catalog/pricing/collections | No / Yes | 13 | SPECIALIZED |
| trust_features | Other | trust_features.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 11 | ADAPT |
| collection_tiles | Collection | collection_tiles.html | grid, carousel / tile_style | _collection_tiles_context | MerchantCollection/catalog | No / Yes | 0 | ADAPT |
| quick_links | Other | quick_links.html | 0 explicit; default | _quick_links_context | Content Menu | No / Yes | 0 | ADAPT |
| faq | Other | faq.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 0 | ADAPT |
| testimonials | Story/Editorial | testimonials.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 6 | ADAPT |
| video_section | Story/Editorial | video_section.html | 0 explicit; default | _video_section_context | Section JSON / shared live context | No / Yes | 0 | ADAPT |
| story_rail | Story/Editorial | story_rail.html | 0 explicit; default | _story_rail_context | Content placements/MediaAsset | No / Yes | 1 | ADAPT |
| newsletter | Newsletter | newsletter.html | 0 explicit; default | _static_context | Section JSON / shared live context | No / Yes | 12 | ADAPT |
| product_main | Product Detail | product_main.html | 0 explicit; default | _product_main_context | Catalog/pricing/collections | No / Yes | 50 | SPECIALIZED |
| product_description | Product Detail | product_description.html | 0 explicit; default | _product_description_context | Catalog/pricing/collections | No / Yes | 50 | SPECIALIZED |
| product_video | Product Detail | product_video.html | 0 explicit; default | _product_video_context | Catalog/pricing/collections | No / Yes | 0 | SPECIALIZED |
| related_products | Product Detail | related_products.html | 0 explicit; default | _related_products_context | Catalog/pricing/collections | No / Yes | 50 | SPECIALIZED |
| product_listing | Listing/Search | product_listing.html | 0 explicit; default | _product_listing_context | Catalog/pricing/collections | No / Yes | 50 | SPECIALIZED |
| collection_header | Collection | collection_header.html | 0 explicit; default | _collection_header_context | MerchantCollection/catalog | No / Yes | 50 | SPECIALIZED |
| collection_products | Collection | collection_products.html | 0 explicit; default | _collection_products_context | MerchantCollection/catalog | No / Yes | 50 | SPECIALIZED |
| cart_items | Cart | cart_items.html | 0 explicit; default | _cart_items_context | Cart domain | No / Yes | 50 | SPECIALIZED |
| cart_summary | Cart | cart_summary.html | 0 explicit; default | _cart_summary_context | Cart domain | No / Yes | 50 | SPECIALIZED |

## Every registered section: controls and safety

**FACT:** R4 shell is Home-only (`r4_views.storefront_r4_editor:189–252`); its section settings API can target a schema-enabled section anywhere in the active Draft, but that is not a non-Home merchant UI. R4 structural commands enforce Home (`section_structure_service.py:30–43`). Older editor accepts six page types. “R4 patch” below means the settings API has revision protection, not all editing of that section is protected. All rows have a store/Draft-scoped legacy settings route; media uses separate non-revision-safe routes.

Common appearance codes are actual registered capabilities: background=B, spacing=S, layout width=W, layout height=H, card=C. Responsive hide flags exist on all 36; columns only for registered column-capable rows. Motion means wrapper motion control, not guaranteed carousel behavior. Legacy spacing save preserves current spacing rather than reading a universal spacing editor. Typography `appearance_overrides` is an R4 declared field only for hero_banner in this census. Media “domain” means edit through its business owner, not a Builder upload control.

| Section | Content / component-specific controls | Variant control | Common appearance | Media controls | Responsive | Motion | Draft-safe path | Remove / duplicate |
|---|---|---|---|---|---|---|---|---|
| announcement_bar | responsive form; fixed shipping message reads live SHOP_FREE_SHIPPING_THRESHOLD | No explicit axis | responsive only | none dedicated | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| hero_banner | autoplay, interval, arrows, dots, loop, text position, hero_style; placement text/media | R4 + legacy hero_style | B, S, W, H; R4 typography | hero-slides desktop/mobile | hide flags | legacy wrapper | R4 patch + legacy; media separate | Yes / Yes |
| fashion_lifestyle_hero | responsive form; static template data; no dedicated slides form | No explicit axis | responsive only | static paths; no dedicated merchant uploader | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| image_slider | same legacy Hero controls; no registered slider variant axis | No explicit axis | B, S, W, H | hero-slides desktop/mobile | hide flags | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| single_banner | placement text/link/media; wrapper form | No explicit axis | B, S, W | banners desktop/mobile | hide flags | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| multi_banner | placement text/link/media; wrapper form; layout_variant passthrough lacks explicit selector | No explicit axis | B, S, W | banners desktop/mobile | hide flags; columns | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| category_grid | title, category IDs, limit, display_mode | legacy display_mode | B, S | live domain media; background asset | hide flags; columns | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| featured_products | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| newest_products | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| best_sellers | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| discounted_products | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| amazing_offers | wrapper/card controls; item_limit/deadline/title validator defaults not a matching content form branch | No explicit axis | B, S, C | live domain media; background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| brand_carousel | title, ordered brand source, display_mode, view-all; destination legacy | R4 + legacy display_mode | B, S | live domain media; background asset | hide flags; columns | legacy wrapper | R4 patch + legacy; media separate | Yes / Yes |
| promo_cards | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| rich_text | body_html | No explicit axis | B, S | background asset | hide flags | No wrapper motion | R4 patch + legacy; media separate | Yes / Yes |
| image_text | title, body_html, image_url, image_position, destination | legacy image_position | B, S, W | image_url; background asset | hide flags | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| blog_posts | responsive form; item_limit/title defaults not a matching content form branch | No explicit axis | responsive only | none dedicated | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| product_section | title, subtitle, source, limit, display_mode, view-all, carousel behavior, header position | R4 + legacy display_mode | B, S, C | live domain media; background asset | hide flags; columns | legacy wrapper | R4 patch + legacy; media separate | Yes / Yes |
| catalog_product_wall | wrapper/card controls; source_mode/layout_mode defaults/recipes exceed legacy form fields | legacy layout_mode | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| trust_features | wrapper form; items defaults not a matching content form branch | No explicit axis | B, S | background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| collection_tiles | title, collection IDs, tile_style | legacy tile_style | B, S | live domain media; background asset | hide flags | legacy wrapper | legacy Draft scope; no revision | Yes / Yes |
| quick_links | title, menu_id | No explicit axis | B, S | background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| faq | title, question/answer items | No explicit axis | B, S | background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| testimonials | title, name/quote/role items | No explicit axis | B, S | background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| video_section | title, video_url, caption | No explicit axis | B, S | video_url; background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / Yes |
| story_rail | existing placement lifecycle controls; wrapper form; generic Story add/edit unsupported | No explicit axis | B, S | existing Story image; generic add/edit unsupported | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| newsletter | title, subtitle, button_label | No explicit axis | B, S | background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| product_main | Domain content; wrapper/card fields only in Builder | No explicit axis | responsive only | live domain media | hide flags | No wrapper motion | legacy Draft scope; no revision | No / No |
| product_description | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S | live domain media; background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| product_video | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S | live domain media; background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| related_products | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S, C | live domain media; background asset | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| product_listing | Domain content; wrapper/card fields only in Builder | No explicit axis | C | live domain media | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | No / No |
| collection_header | Domain content; wrapper/card fields only in Builder | No explicit axis | B, S | live domain media; background asset | hide flags | No wrapper motion | legacy Draft scope; no revision | Yes / No |
| collection_products | Domain content; wrapper/card fields only in Builder | No explicit axis | C | live domain media | hide flags; columns | No wrapper motion | legacy Draft scope; no revision | No / No |
| cart_items | Domain content; wrapper/card fields only in Builder | No explicit axis | responsive only | none dedicated | hide flags | No wrapper motion | legacy Draft scope; no revision | No / No |
| cart_summary | Domain content; wrapper/card fields only in Builder | No explicit axis | responsive only | none dedicated | hide flags | No wrapper motion | legacy Draft scope; no revision | No / No |

**FACT — control proof:** `views.storefront_section_settings:780–924` has explicit content branches only for product_section, image_text, rich_text, hero_banner/image_slider, category_grid, brand_carousel, collection_tiles, quick_links, faq, testimonials, video_section and newsletter. Its else branch starts an empty dictionary before shared wrapper extraction. Thus old fixed shelves, wall source fields and static components must not be advertised as fully editable merely because defaults contain settings. Common controls are in `templates/dashboard/storefront_builder/partials/section_settings_form.html`, helper extraction `views.py:1041–1234`. Brand logo upload is domain-owned, and selecting brands in R4 does not upload logos.

**FACT:** R4 schema fields, verbatim:

| Section | Fields accepted in a patch |
|---|---|
| hero_banner | hero_style, autoplay, interval_ms, show_arrows, show_dots, loop, text_position, appearance_overrides |
| brand_carousel | title, source, display_mode, show_view_all |
| rich_text | body_html |
| product_section | title, source, item_limit, display_mode, show_view_all, subtitle, carousel_autoplay, carousel_interval_ms, carousel_show_arrows, header_position |

**FACT:** Registered variants are selector branches, not necessarily separate template files. Hero has six paths; Catalog Wall three paths; Category's eleven modes, Brand's three modes, Image/Text's two modes, Product Section's three modes and Collection Tiles' two modes branch through their default templates. The complete section renderer union is 43 paths (36 defaults + five extra Hero + two extra Wall). Adding global47 yields the prior **90 compiled template paths**, a different unit from the coincidentally **90 symbolic component references**. Neither number certifies distinct visuals.

## Desired product families: eight contract questions

Columns answer: Q1 one data contract? Q2 presentation-only variants? Q3 variant-dependent queries? Q4 same complete appearance contract? Q5 schema-defined specific settings? Q6 content/common settings preserved when switching? Q7 R4 versus legacy UI? Q8 required convergence. “Partial” is deliberately narrower than “yes”; none has full browser certification.

| Family | Q1 data | Q2 presentation-only | Q3 query variation | Q4 appearance | Q5 schema | Q6 preserve | Q7 UI | Q8 before expansion |
|---|---|---|---|---|---|---|---|---|
| Header | shared live identity/menus + version config | largely, eligibility/toggles vary | live context shared; ORM consumption possible | partial; forced CSS roles | validated legacy config, no typed family settings | R4 selector patch preserves config; old mirrors conflict | R4 variant; legacy full settings | one writer, effective-source UI, live identity policy, CSS proof |
| MegaHeader/MegaMenu | no independent implemented family | no real axis | N/A virtual none | missing | no | N/A | no configurable family UI | decide product/data contract; no aliases as new functionality |
| Hero | HeroSlide common; fashion static exception | no, controls/interactions differ | scoped shared loader; static exception | partial | hero_banner yes; fashion no | R4 patch retains; old form can discard; global overlay wins | R4 Hero; legacy media/fashion | media lifetime, autoplay capability, precedence, static strategy |
| Slider | delegates HeroSlide loader | single registered default | shared Hero loader | partial | no | legacy settings replacement | legacy | schema + shared slider behavior contract |
| Category | common category list with enrichment | conditional data enrichment | representative-media query per category in selected modes | partial | no | legacy replacement; compatible IDs validated | legacy | schema, batch data budget, image policy |
| Collection | tile contract plus detail-page context | tile grid/carousel mostly | common list/count loading; page products separate | partial | no | legacy replacement; IDs retained only by represented fields | legacy | distinguish tiles/detail contract, schema, full-page assets |
| Product Showcase | source resolver plus fixed shelves + grouped wall | not uniformly; grouping changes aggregation | wall/group/sibling exclusion; old shelf queries | partial | only product_section | R4 source shelf partial; template Apply replaces | R4 product_section; rest legacy | shared domain-owned result contract; card/fragment and aggregation policies |
| Brand Showcase | yes, one ordered store-scoped brand list | yes at loader boundary | no separate mode query; shared builder | partial shared wrapper; inline grid constraints | yes content/source; no full common schema | R4 yes for managed patch; legacy risks | R4 + legacy | strongest foundation; common appearance, revision coverage and browser proof |
| Ribbon/Promo | several placement/static/category contracts | no unified axis | shared banners versus category promo | partial | no | legacy media/settings | legacy | define placement versus category promotion; typed content contract |
| Story/Editorial | JSON text, blog, video, placement story differ | heterogeneous components | blog/stories have distinct domain loads | partial | rich_text only | only R4 text patch is narrow safe path | R4 rich_text; rest legacy | separate semantic subcontracts before a shared visual variant promise |
| Newsletter | section labels + subscription service | single default | static rendering; subscription POST domain-owned | partial | no | legacy fields present | legacy | schema; custom labels on response fragment; form/accessibility proof |
| Footer | shared FooterSettings/menu/social/trust context | largely; version/live gates overlap | common context | partial competing CSS | legacy validator only | R4 variant preserves; legacy mirror conflict | R4 variant; legacy config/content | live visibility policy + one selector writer |
| MegaFooter | not a distinct family | no independent axis | N/A | missing distinct contract | no | N/A | footer columns are not MegaFooter API | product definition before implementation |
| Mobile Bottom Navigation | live menus/cart counts + config | mostly presentation | shared count/menu context | partial | no family-specific settings | typed API selection preserves; legacy mirror writes compete | legacy footer selector; typed API, no dedicated R4 panel | choose scope/live policy; mobile/OOB proof |
| Product Detail | shared requested product/variant domain context | fixed parts; layout passthrough | shared page context; card ORM access | partial | no | fixed section flags; no general switch contract | legacy only for page editing | single variantSelector + detail Preview assets + schema |
| Listing/Search | shared listing/filter domain context | fixed product_listing; layout branches | full versus fragment setup differs | partial | no | custom card settings lost from HX envelope | legacy page editing | shared fragment contract and page controls |
| Cart | shared cart services/context | fixed required parts | fragment builds rows separately | partial | no | required parts cannot remove/duplicate | legacy page editing | container-aware fragments; preserve commerce behavior |
| Other | FAQ/trust/links are different semantic data | no single variant axis | menu context vs static JSON | partial | no | legacy controls vary | legacy | bounded subcontracts; no generic “other renderer” engine |

Evidence map: Header/Footer/Nav `global_region_registry.py:285–448`, `storefront_appearance/rendering.py:105–142`, `content/context_processors.py:127–137`; Hero/Category/Product/Brand/Collection `render_service.py:52–604`; shared wrapper `responsive_section_wrapper.html:44–80`; old/R4 settings `views.py:780`, `settings_schema.py:310`; pages/fragments Report05.

## Prioritized DO NOT EXPAND YET

1. **P0 — all families:** eliminate lossy parallel writers and establish declared-to-applied recipe manifest fidelity (Report02 A01/A02). New selectors currently increase ambiguous state.
2. **P1 — Hero/Slider/Ribbon/Story:** reconcile placement writes, shared files/background/history lifetimes and interaction capabilities.
3. **P1 — Product Showcase/Listing/Search/Cart/Product Detail:** converge full/fragment/Preview envelopes, cards and assets before more variants.
4. **P1 — Header/Footer/Mobile/Brand/Category/Collection:** settle global/local precedence, shared appearance and CSS ownership; certify desktop/mobile.
5. **P2 — Mega families/Newsletter/Other:** define missing product contracts and schema coverage. Lack of a real family is not a reason to add marketing aliases.

## Count reconciliation with the first audit

All catalog counts remain unchanged. The prior per-section use table counted **55 latest presets including five internal presets**. This report counts **50 Ready Templates only**. Every difference is listed:

| Section | Prior /55 | Ready /50 | Difference explained by five excluded internal presets |
|---|---:|---:|---:|
| hero_banner | 49 | 45 | 4 |
| multi_banner | 1 | 0 | 1 |
| category_grid | 52 | 49 | 3 |
| featured_products | 2 | 0 | 2 |
| newest_products | 2 | 0 | 2 |
| best_sellers | 1 | 0 | 1 |
| discounted_products | 1 | 0 | 1 |
| amazing_offers | 2 | 0 | 2 |
| brand_carousel | 4 | 2 | 2 |
| promo_cards | 1 | 0 | 1 |
| image_text | 18 | 17 | 1 |
| product_section | 41 | 40 | 1 |
| trust_features | 15 | 11 | 4 |
| testimonials | 8 | 6 | 2 |
| story_rail | 3 | 1 | 2 |
| newsletter | 14 | 12 | 2 |
| product_main | 54 | 50 | 4 |
| product_description | 54 | 50 | 4 |
| product_video | 2 | 0 | 2 |
| related_products | 53 | 50 | 3 |
| product_listing | 54 | 50 | 4 |
| collection_header | 54 | 50 | 4 |
| collection_products | 54 | 50 | 4 |
| cart_items | 54 | 50 | 4 |
| cart_summary | 54 | 50 | 4 |

Excluded keys: clean_minimal, editorial_story, dense_catalog, premium_boutique, v5_golden_homepage. Zero recipe use is not dead-code evidence. Deployment usage remains **UNKNOWN**.

**FACT — Story media control qualification:** `media_views.py:165–200` and the generic section_media_form.html hardcode desktop/mobile fields; StoryRailItem instead has `image`. Existing Story rendering/delete/toggle/move/reorder remain, but the add/edit form is not a working single-image uploader. This narrows the first audit's generic media-controls description; it does not change endpoint counts or the registered Story renderer.
