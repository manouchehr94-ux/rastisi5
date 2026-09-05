# 04 — 50-template DNA reality check

Baseline: `audit/storefront-appearance-g23`, HEAD `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`; 2026-09-05.

Evidence convention: **FACT** = source or executed read-only validation; **INFERENCE** = consequence, not an observed production incident; **RECOMMENDATION** = proposed architectural direction; **UNKNOWN** = needs deployment evidence or a Product Owner decision. Source paths are relative to `D:/Projects/RastiSi4_Golden_Manual/`; `:line` identifies the baseline source. No business database was queried or mutated. Existing audit remains unchanged.

Source locator shorthand used below: bare Builder modules (`models.py`, `views.py`, registries, schemas and `r4_views.py`) are under `apps/storefront_builder/`; service modules under `apps/storefront_builder/services/`; typed manifest modules under `apps/storefront_builder/storefront_appearance/`; bare test modules under `apps/storefront_builder/tests/`. Section/partial template names resolve beneath `apps/storefront_builder/templates/storefront_builder/`; `r4/editor.html` resolves to `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`. Catalog/Cart/Content template names resolve beneath the corresponding app's `templates/` directory. Root shells are `templates/base.html` and `templates/storefront_shell.html`. CSS: `apps/core/static/css/tokens.css`, `theme_palette.css`; `apps/catalog/static/css/home.css`, `product_card.css`, `product_list.css`, `product_detail.css`; `apps/storefront_builder/static/css/storefront_builder.css`, `storefront_builder_preview_v22.css`; `apps/cart/static/css/cart.css`.

## Result and counting boundary

**FACT:** There are 50 latest Ready recipes, **50 exact normalized declared-DNA fingerprints**, **0 duplicate groups**, and **0 recipes differing only by the defined token/palette layer**. There are **27 Home structural compositions**, **49 Home settings/composition fingerprints**, and **1 composition each** for Listing, Search, Product Detail, Collection and Cart. These are comparisons of recipe definitions, not screenshots or deployed stores.

**FACT:** Declared implementation references use **12 Headers, 8 Footers, 7 Bottom Navigations and 6 Hero renderer implementations**. Hero sections actually occur in 45 recipes; five omit Hero. Hidden/virtual choices are not extra rendered visuals. Layout references use 7 geometry entries; product-view references use 5 entries; card references use 16 styles; badge uses 2 treatments; motion uses 3 settings.

**FACT — additional closure finding, A02:** A complete declared manifest is not the same as a complete applied manifest. `preset_service.apply_preset:275–460` reads appearance/header/footer/pages but never `preset.store_appearance`. `r4_mutation_service._apply_appearance_template:393–428` calls that service, then synchronizes only the four legacy selector families: header/footer/bottom_nav/motion (`:283–335`). It does not apply the recipe's hero/layout/product_view/card/badge/mega_menu selections. The older gallery apply route has no such synchronization. Existing non-default manifest selections can therefore survive a new recipe and override its section settings. This qualifies the original audit §15's broad recipe-application description; it does not change its registry counts.

**INFERENCE:** No single unconditional “effective full-store design after Apply” can be assigned to a recipe independently of starting Draft state and entry path. The counts below are explicitly **declared recipe DNA**. Twelve/eight/seven global references are actually referenced by recipes and resolvable; they are not a promise that every legacy Apply displays them when a conflicting manifest already exists.

## Deterministic normalization

Source: `layout_preset_registry.list_ready_templates:219`, `a8_ready_templates._SPECS:221`, `_build:198`, `_home:131`, `_common_pages:66`; `storefront_appearance.registry.require_component:45`; `preset_service._build_sections_for_page:258`.

For each latest recipe:

1. Exclude marketing key, label, description, provenance/slot identity and version from equality; display key/version for traceability. Identity alone must not make designs unique.
2. Resolve every component key through `require_component(key).registry_reference`. Keep virtual/no-op references explicit.
3. Normalize section settings exactly as section creation does: defaults for a null settings entry; otherwise the registered validator. Preserve ordered section keys, row keys/spans and container settings. All current recipe row keys are empty, spans 12, container settings null: ordinary full-width containers, irrespective of the manifest layout alias.
4. Keep recipe appearance overlay, palette, header/footer overlay and manifest settings. Omitted token profile means **retain current template_slug**, not an invented profile. All 50 omit template_slug; fresh-model fallback is modern. Applied token values can still be modified later.
5. Serialize with Python JSON sorted keys, compact separators, ensure_ascii=True; SHA-256 is the fingerprint. Equality is equality of normalized payload, not a subjective score.
6. Token-excluded comparison removes the whole appearance overlay and palette, but keeps all implementation references, including motion, plus section settings and global configs. This deliberately tests “tokens/palette only” without hiding component-choice differences.
7. Structure comparison removes section settings and all presentation selections, retaining page sequence/row/span/container configuration. The separate 49 Home settings fingerprints restore section settings but exclude globals.
8. Alias-only duplicate groups require equal normalized DNA with different raw component aliases: **0 whole-recipe groups**, since all full fingerprints differ. This does not mean aliases are unique implementations.

## All 50 declared component DNAs

Reference abbreviations below are lossless: Header `H:x = global_region:header:x`; Footer `F:x = global_region:footer:x`; Nav `N:x = global_region:mobile_bottom_nav:x`; Hero `hero:x = section_variant:hero_banner:x`; Product `ps:x = section_variant:product_section:x`, `wall:x = section_variant:catalog_product_wall:x`; Layout `L:x = composition:x`; Card `C:x = card_style:x`. Badge none is virtual; sale is badge_treatment:sale. Every row has virtual mega_menu:none and no manifest-specific settings. Hero reference in parentheses “omitted” is not a rendered Home Hero.

| Recipe/version | Header | Footer | Nav | Hero reference | Layout ref | Product ref | Card | Badge | Motion |
|---|---|---|---|---|---|---|---|---|---|
| dense_marketplace / 3 | H:marketplace_search | F:marketplace_columns | N:five_item | hero:chocolate_carousel | L:quarters | wall:group_columns | C:marketplace_price | sale | dynamic |
| premium_leather / 3 | H:editorial_row | F:minimal | N:minimal_icons | hero:overlay (omitted) | L:quarters | ps:grid | C:standard | none | none |
| warm_boutique / 3 | H:compact_menu | F:brand_story | N:floating_dock | hero:split | L:thirds | ps:grid | C:paper_frame | none | subtle |
| fashion_promo_catalog / 8 | H:promo_bar | F:marketplace_columns | N:raised_cart | hero:chocolate_carousel | L:quarters | wall:group_columns | C:price_first | sale | dynamic |
| playful_lifestyle / 2 | H:playful_canopy | F:playful_wave | N:five_item | hero:atelier_triptych | L:thirds | ps:grid | C:soft_capsule | none | dynamic |
| utility_catalog / 2 | H:marketplace_search | F:centered | N:four_item | hero:overlay (omitted) | L:single | wall:rows | C:retail_row | none | none |
| editorial_jewelry / 3 | H:editorial_row | F:minimal | N:minimal_icons | hero:luxury_showcase | L:thirds | ps:grid | C:luxury_dark | none | none |
| dark_digital / 3 | H:floating_compact | F:marketplace_columns | N:glass_dock | hero:overlay | L:single | ps:carousel | C:tech_neon | sale | dynamic |
| cedar_home / 1 | H:centered_brand | F:centered | N:four_item | hero:split | L:quarters | ps:grid | C:standard | none | subtle |
| street_drop / 1 | H:promo_bar | F:bold_columns | N:wide_cart | hero:split | L:single | ps:carousel | C:bold_outline | sale | dynamic |
| premium_leather_noir / 1 | H:centered_brand | F:editorial_wordmark | N:minimal_icons | hero:luxury_showcase | L:half | ps:grid | C:luxury_dark | none | none |
| search_market / 1 | H:marketplace_search | F:marketplace_columns | N:raised_cart | hero:split | L:quarters | wall:group_columns | C:price_first | sale | subtle |
| artisan_grain / 1 | H:editorial_masthead | F:brand_story | N:floating_dock | hero:split | L:half | ps:grid | C:editorial_minimal | none | none |
| pixel_play / 1 | H:category_tabs | F:minimal | N:raised_cart | hero:chocolate_carousel | L:quarter_left | wall:featured_row | C:soft_capsule | sale | dynamic |
| simorgh_market / 1 | H:centered_brand | F:marketplace_columns | N:five_item | hero:chocolate_carousel | L:quarters | ps:grid | C:marketplace_price | sale | subtle |
| coastal_product / 1 | H:overlay_transparent | F:centered | N:wide_cart | hero:beauty_editorial | L:quarters | ps:grid | C:standard | none | subtle |
| literary_catalog / 1 | H:editorial_masthead | F:editorial_wordmark | N:minimal_icons | hero:split | L:single | wall:rows | C:retail_row | none | none |
| gallery_minimal / 1 | H:editorial_row | F:minimal | N:minimal_icons | hero:luxury_showcase | L:single | wall:rows | C:editorial_minimal | none | none |
| handmade_luxe / 1 | H:editorial_row | F:brand_story | N:floating_dock | hero:split | L:thirds | ps:grid | C:luxury_dark | none | subtle |
| niloufar_glass / 1 | H:floating_compact | F:centered | N:raised_cart | hero:atelier_triptych | L:thirds | ps:grid | C:beauty_glass | none | subtle |
| tool_finder / 1 | H:marketplace_search | F:marketplace_columns | N:four_item | hero:overlay (omitted) | L:quarters | ps:grid | C:technical_spec | none | none |
| green_workshop / 1 | H:compact_menu | F:brand_story | N:floating_dock | hero:split | L:thirds | ps:grid | C:standard | none | subtle |
| tower_department / 1 | H:marketplace_search | F:marketplace_columns | N:five_item | hero:atelier_triptych | L:quarters | ps:grid | C:marketplace_price | sale | dynamic |
| beauty_dew / 1 | H:floating_compact | F:minimal | N:raised_cart | hero:beauty_editorial | L:single | ps:carousel | C:beauty_glass | none | subtle |
| horizon_story / 1 | H:overlay_transparent | F:brand_story | N:four_item | hero:chocolate_carousel | L:half | ps:grid | C:standard | none | subtle |
| mina_community / 1 | H:community_shortcuts | F:app_download | N:floating_dock | hero:atelier_triptych | L:half | ps:grid | C:soft_capsule | none | dynamic |
| silk_editorial / 1 | H:editorial_masthead | F:editorial_wordmark | N:minimal_icons | hero:luxury_showcase | L:half | ps:grid | C:editorial_minimal | none | none |
| tuska_bento / 1 | H:compact_menu | F:minimal | N:four_item | hero:chocolate_carousel | L:quarter_left | wall:featured_row | C:luxury_dark | sale | dynamic |
| rayan_tech / 1 | H:marketplace_search | F:app_download | N:four_item | hero:beauty_editorial | L:quarters | ps:grid | C:technical_spec | none | subtle |
| laleh_play / 1 | H:playful_canopy | F:playful_wave | N:five_item | hero:atelier_triptych | L:thirds | ps:grid | C:paper_frame | none | dynamic |
| city_classic / 1 | H:centered_brand | F:brand_story | N:four_item | hero:split | L:quarters | ps:grid | C:standard | none | subtle |
| collection_index / 1 | H:compact_drawer | F:minimal | N:minimal_icons | hero:overlay (omitted) | L:single | wall:rows | C:catalog_index | none | none |
| kamand_artisan / 1 | H:overlay_transparent | F:brand_story | N:floating_dock | hero:split | L:thirds | ps:grid | C:editorial_minimal | none | subtle |
| almas_luxury / 1 | H:floating_compact | F:marketplace_columns | N:glass_dock | hero:beauty_editorial | L:thirds | ps:grid | C:shelf_editorial | none | subtle |
| roosta_zigzag / 1 | H:playful_canopy | F:brand_story | N:four_item | hero:atelier_triptych | L:quarter_right | wall:featured_row | C:marketplace_price | none | subtle |
| mother_utility / 1 | H:compact_drawer | F:minimal | N:minimal_icons | hero:overlay (omitted) | L:quarters | ps:grid | C:technical_spec | none | none |
| aftab_price / 1 | H:category_tabs | F:minimal | N:raised_cart | hero:split | L:quarters | ps:grid | C:price_first | sale | dynamic |
| mist_quiet / 1 | H:editorial_row | F:minimal | N:minimal_icons | hero:split | L:thirds | ps:grid | C:standard | none | none |
| night_catalog / 1 | H:compact_drawer | F:editorial_wordmark | N:minimal_icons | hero:split | L:half | ps:grid | C:editorial_minimal | none | none |
| watchmaker_round / 1 | H:centered_brand | F:centered | N:minimal_icons | hero:beauty_editorial | L:half | ps:grid | C:portrait_round | none | subtle |
| kite_playful / 1 | H:playful_canopy | F:playful_wave | N:five_item | hero:atelier_triptych | L:quarters | ps:grid | C:soft_capsule | none | dynamic |
| pine_eco / 1 | H:compact_menu | F:centered | N:floating_dock | hero:split | L:thirds | ps:grid | C:soft_capsule | none | subtle |
| mirror_beauty / 1 | H:floating_compact | F:minimal | N:raised_cart | hero:beauty_editorial | L:thirds | ps:grid | C:beauty_glass | none | subtle |
| charcoal_grill / 1 | H:promo_bar | F:bold_columns | N:wide_cart | hero:beauty_editorial | L:quarters | ps:grid | C:bold_outline | sale | dynamic |
| calligraphy_paper / 1 | H:compact_drawer | F:editorial_wordmark | N:minimal_icons | hero:luxury_showcase | L:single | wall:rows | C:editorial_minimal | none | none |
| harbor_imports / 1 | H:marketplace_search | F:marketplace_columns | N:four_item | hero:atelier_triptych | L:quarters | ps:grid | C:shipping_label | sale | subtle |
| parnian_editorial / 1 | H:editorial_masthead | F:editorial_wordmark | N:minimal_icons | hero:luxury_showcase | L:half | ps:grid | C:shelf_editorial | none | none |
| racer_tech / 1 | H:promo_bar | F:marketplace_columns | N:wide_cart | hero:overlay | L:single | ps:carousel | C:technical_spec | sale | dynamic |
| ferdowsi_department / 1 | H:centered_brand | F:marketplace_columns | N:five_item | hero:atelier_triptych | L:third_right | wall:featured_row | C:marketplace_price | sale | subtle |
| anniversary_mosaic / 1 | H:editorial_row | F:editorial_wordmark | N:floating_dock | hero:chocolate_carousel | L:quarter_left | wall:featured_row | C:catalog_index | sale | dynamic |

## Per-recipe tokens, Home sequence and fingerprint

Every row's non-Home code **P** expands to: Listing=[product_listing]; Search=[product_listing]; Product Detail=[product_main, product_description, related_products]; Collection=[collection_header, collection_products]; Cart=[cart_items, cart_summary]. Thus each row explicitly references all five non-Home compositions. All token profiles are **retained**, because the recipe supplies no template_slug. Static/media code **S** means shared domain/placement loaders and shared CSS; no recipe-specific static Hero component, uploaded IDs or filenames. The separate fashion_lifestyle_hero remains registered but is used by zero Ready recipes.

The compact token tuple is font / density / width / radius. Every remaining appearance value is deterministically derived by `a8_ready_templates._appearance:162–195`: button_radius=radius; type_scale=compact/large/normal for compact/relaxed/normal density; button_style=outline for radius0, soft for radius≥14, otherwise filled; image_fit=contain for dense_grid/catalog_list product-view aliases, otherwise cover; motion none disables image_hover/zoom/card_hover, dynamic enables crossfade; grid_density=6 for dense_five,4 for four_column,3 for two/three_column,otherwise4; card_shadow=none at radius0,otherwise soft; hero_style=tall/split/wide according to the explicit map there. These token-derived differences remain in full fingerprints.

| Recipe/version | Palette | Tokens | Home ordered sections | Other pages / media | SHA-256 |
|---|---|---|---|---|---|
| dense_marketplace/3 | marketplace-spectrum | Vazirmatn / compact / 1500 / 8 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=circular) → product_section(data_source=discounted,display_mode=grid) → catalog_product_wall(layout_mode=group_columns) → trust_features → brand_carousel → testimonials | P / S | `6fc028631cfb77caa6a024bbd80bfd1a78fbf3f30a816fe66c18673e12e93019` |
| premium_leather/3 | mono | Arial / normal / 1200 / 0 | announcement_bar → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → rich_text | P / S | `76e76a5f01d67ebf94925f012805a1de416d26c788bde4b52144e6ee1ba63cbc` |
| warm_boutique/3 | terracotta | Vazirmatn / relaxed / 1100 / 4 | hero_banner(hero_style=split) → image_text → product_section(data_source=newest,display_mode=grid) → testimonials → newsletter | P / S | `34d8349605b7939d58b0f0773da5c41d83bf5377f1e0a414bdf49b702b0069c3` |
| fashion_promo_catalog/8 | magenta-pop | Vazirmatn / compact / 1500 / 8 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=carousel) → product_section(data_source=discounted,display_mode=grid) → catalog_product_wall(layout_mode=group_columns) | P / S | `afd0fc641ec254ed35712743cf5e1244101059bd74dc32ff03b6827bd56dadac` |
| playful_lifestyle/2 | mint | Vazirmatn / relaxed / 1200 / 22 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → testimonials → newsletter | P / S | `d6298ff0139ffcd35398e8198c40a4dd8288f03dc7b4b0f3a903bcb2e2302b8e` |
| utility_catalog/2 | slate | Arial / compact / 1320 / 4 | category_grid(display_mode=grid) → catalog_product_wall(layout_mode=rows) → trust_features | P / S | `2f32704bc2c6399805d180491860191d559becbda7c93c62c1d292ddb407a21b` |
| editorial_jewelry/3 | atelier-ivory | Vazirmatn / relaxed / 1200 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text → rich_text | P / S | `9aae9400738471c28826746570270e929f1cd70c8026d0d3bc0512998cfb0351` |
| dark_digital/3 | theme-purple-neon | Vazirmatn / normal / 1200 / 10 | hero_banner(hero_style=overlay) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=carousel) → product_section(data_source=discounted,display_mode=grid) → newsletter | P / S | `a0cbcd324bf7616a5bd527d8110b60281dca8f57d6bf1c6ab10f9eb01428135c` |
| cedar_home/1 | forest | Vazirmatn / normal / 1200 / 12 | hero_banner(hero_style=split) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → trust_features | P / S | `4b03b1c65b03808490ae27acccbe760b7b03f6c70be066d91312d82e58a0f3ed` |
| street_drop/1 | theme-graphite-orange | Vazirmatn / compact / 1320 / 0 | announcement_bar → hero_banner(hero_style=split) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=carousel) → product_section(data_source=discounted,display_mode=grid) | P / S | `5315e473b49c2622550cb7990df95c5f586fa312eb7fc74ce1c7e8e8c6848141` |
| premium_leather_noir/1 | theme-black-gold | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=atelier_mosaic) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `0862ef6d75a5998820e475c027dd982ad472afd04018f9b94093f6144673617d` |
| search_market/1 | theme-cobalt-snow | Vazirmatn / compact / 1500 / 8 | hero_banner(hero_style=split) → category_grid(display_mode=circular) → catalog_product_wall(layout_mode=group_columns) → trust_features | P / S | `fc70ed8067a13ebd83f34b787f6a7552dcca26a822eac0ebca2ff1bf6238c7fa` |
| artisan_grain/1 | olive | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=split) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `01126ba5465454b6423d205250d684821fe52928e106a6148241389bf1a3568a` |
| pixel_play/1 | violet-pop | Vazirmatn / normal / 1200 / 14 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=grid) → catalog_product_wall(layout_mode=featured_row) → newsletter | P / S | `eb9caf9beb07fe96f2836d3ad51c069fa7f12a13ca419b5d18bfcd8e0ce51f34` |
| simorgh_market/1 | royal | Vazirmatn / normal / 1320 / 8 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → trust_features | P / S | `0c39e14a28aec813c1a236add0282a7e2023b3ce15e0d9057654a33be5f911db` |
| coastal_product/1 | ocean | Vazirmatn / normal / 1200 / 12 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `48fb67d5f2bb6158ee4c5a17c74ec9ddb6884f766f264f7695e5e162482a07e1` |
| literary_catalog/1 | amber | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=split) → category_grid(display_mode=fashion_flat) → catalog_product_wall(layout_mode=rows) → rich_text | P / S | `50dba4ef9597b3f31dc0e6228ce608c02e666e1f859dd35e934c855e69451b1e` |
| gallery_minimal/1 | theme-ice-cyan | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=fashion_flat) → catalog_product_wall(layout_mode=rows) → rich_text | P / S | `00f12f50d1e8398ccf70853450ad16dcaf2f65e6246acd91c3386bd890db68b0` |
| handmade_luxe/1 | theme-terracotta-cream | Vazirmatn / relaxed / 1100 / 10 | hero_banner(hero_style=split) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `bc5101bd38596b15d089a320561782742677d6d23df4c33af709bb60d5d3a2f4` |
| niloufar_glass/1 | rose | Vazirmatn / relaxed / 1200 / 18 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → newsletter | P / S | `380c00dcb62be4f50cb97a174898c6ae6fed82c22ae5ababd14ad349193acc9f` |
| tool_finder/1 | navy | Arial / compact / 1320 / 4 | category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → trust_features | P / S | `991bbc5b5dfffc5b27e0da66f51a513d68f059ff57da0708e4bdc8e2d902a3fd` |
| green_workshop/1 | sage | Vazirmatn / relaxed / 1100 / 16 | hero_banner(hero_style=split) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → image_text → newsletter | P / S | `22ab42cec7b0fdd5c8e8507cc3b56ac1188a2aaf96827076d7dddaa7632b4d9b` |
| tower_department/1 | theme-crimson-charcoal | Vazirmatn / compact / 1500 / 8 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → product_section(data_source=discounted,display_mode=grid) → trust_features | P / S | `22d94a3f030011d26ec1a85637e2a88f137fdd01a7c718232a7d3ee85a9cec2e` |
| beauty_dew/1 | beauty-magenta | Vazirmatn / relaxed / 1200 / 18 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=carousel) → newsletter | P / S | `f39581bf839ebfa5c85d883a84de03d12e72deff5af6e459bff99868636d3973` |
| horizon_story/1 | peach | Vazirmatn / relaxed / 1100 / 14 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `f71b31e7da0a3d413d3efcf1ee7159596a36ea8032c84275e047e62080a8c944` |
| mina_community/1 | uupm-social-rose | Vazirmatn / relaxed / 1100 / 20 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → story_rail | P / S | `83f0b10a735d9574d2fbe61764d6992d1fbb7d9d4fdbda918b61644418f1e7da` |
| silk_editorial/1 | atelier-ivory | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `bc79af95218cb2f382355a4509ed1c8777bd6772d73f15b47482478b3834fe54` |
| tuska_bento/1 | plum | Vazirmatn / normal / 1200 / 12 | hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=grid) → catalog_product_wall(layout_mode=featured_row) → testimonials | P / S | `554b4ef87819c80e9340e53531082ce13e52f3966582ef380459d29ce901e06c` |
| rayan_tech/1 | theme-midnight-electric | Vazirmatn / compact / 1320 / 6 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → trust_features | P / S | `33145d263b2525131bf3cbb2383fd2567cd1c25e097914a0facfb993f124b072` |
| laleh_play/1 | sunset | Vazirmatn / relaxed / 1200 / 22 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → newsletter | P / S | `a98bdc71feac843ee34cc0477bb1f80a0d4bbebcf3015b195582409fb70c367f` |
| city_classic/1 | uupm-professional-navy | Vazirmatn / normal / 1200 / 8 | hero_banner(hero_style=split) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `dfc01e751e1e9230c414afbaa2fe733f5d977f24c6d7592d77d69b38b1dbda6f` |
| collection_index/1 | catalog-colorful | Arial / compact / 1100 / 0 | category_grid(display_mode=fashion_flat) → catalog_product_wall(layout_mode=rows) → rich_text | P / S | `a24df259470bf0daeae19385df61e8a501e0173ec6357835808c87ddcd6d40ef` |
| kamand_artisan/1 | terracotta | Vazirmatn / relaxed / 1100 / 6 | hero_banner(hero_style=split) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `d09f945311b0af360709fa39a83a092cc8d229102e89d0dc5601b54f9501cc16` |
| almas_luxury/1 | theme-ice-cyan | Vazirmatn / relaxed / 1200 / 18 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → newsletter | P / S | `6e83338cbcc65b437c58a32adb1c186496e125e2ca18c3407c6c5c87ab05c335` |
| roosta_zigzag/1 | forest | Vazirmatn / relaxed / 1200 / 16 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=circular) → catalog_product_wall(layout_mode=featured_row) → image_text | P / S | `4db775f074c888219fb5d437af4c24f88289df70e30f7f5bfbc8d15b9140f248` |
| mother_utility/1 | slate | Arial / compact / 1200 / 4 | category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → trust_features | P / S | `e3233f7476625b6b033b6d269cb424b46d68f6dab4bdb8e5d9ffca5ff1cb7ea6` |
| aftab_price/1 | amber | Vazirmatn / compact / 1320 / 8 | hero_banner(hero_style=split) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → product_section(data_source=discounted,display_mode=grid) | P / S | `305b5083930855acb3471fd7442cac1904bb84feadb42131c5ff58bbb74c6ca5` |
| mist_quiet/1 | mono | Vazirmatn / relaxed / 1100 / 14 | hero_banner(hero_style=split) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → rich_text | P / S | `b8634d953c8e0804b3350c1da86f31fe2b5b58c05a6fc07ce52d8205bc71afcb` |
| night_catalog/1 | theme-black-gold | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=split) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → rich_text | P / S | `8e3aa6f483b81df430da11e1d2743be90d6aaf445e5a8fac44bd521d44c47e2d` |
| watchmaker_round/1 | uupm-gold-purple-tech | Vazirmatn / relaxed / 1100 / 12 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=fashion_flat) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `3b5d738856e22fd44ba525e80e187d560128fa02906a2e9652e1f29cd2065c84` |
| kite_playful/1 | uupm-playful-orange | Vazirmatn / relaxed / 1200 / 22 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → testimonials | P / S | `4e5ad0818336e21d175ee02a8d56e72edd2e715441005040430c1914c1114c96` |
| pine_eco/1 | sage | Vazirmatn / relaxed / 1200 / 16 | hero_banner(hero_style=split) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → image_text → newsletter | P / S | `d6b021b2037ab7bf4bee432d3405af4abe6a791ce2ac6f45bf66b7282d20c25a` |
| mirror_beauty/1 | beauty-magenta | Vazirmatn / relaxed / 1200 / 18 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=circular) → product_section(data_source=newest,display_mode=grid) → image_text → newsletter | P / S | `649ae63cdce38cc13e8644adba1cd97c90a561730f9671faebb2ce3c3bb1dca7` |
| charcoal_grill/1 | theme-graphite-orange | Vazirmatn / compact / 1200 / 0 | hero_banner(hero_style=beauty_editorial) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=grid) → product_section(data_source=discounted,display_mode=grid) | P / S | `91bd01e3db6299b81fb3c325e046293bfc1bb9893435390529a99830f9f998af` |
| calligraphy_paper/1 | mono | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=fashion_flat) → catalog_product_wall(layout_mode=rows) → image_text | P / S | `4c802a34cd6e173abe3c88dc6733cc88a663a25ab440e0aecb1e439471e1a4aa` |
| harbor_imports/1 | navy | Vazirmatn / compact / 1320 / 6 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=grid) → product_section(data_source=newest,display_mode=grid) → product_section(data_source=discounted,display_mode=grid) → trust_features | P / S | `c32f2fefa7c07b5034989e836bb6c89c776433a79d53da56087f37db1a209e09` |
| parnian_editorial/1 | uupm-bakery-cream | Vazirmatn / relaxed / 1100 / 0 | hero_banner(hero_style=luxury_showcase) → category_grid(display_mode=atelier_mosaic) → product_section(data_source=newest,display_mode=grid) → image_text | P / S | `bb9860eaa13fe4c02938e33ce4297482789786a5d4758cf837d96013cead5c48` |
| racer_tech/1 | uupm-gaming-neon | Vazirmatn / compact / 1320 / 6 | announcement_bar → hero_banner(hero_style=overlay) → category_grid(display_mode=carousel) → product_section(data_source=newest,display_mode=carousel) → product_section(data_source=discounted,display_mode=grid) | P / S | `5a56c5ede19e6a5ed62473c840f474cbf3bbff157b20249c14b7533552f8adc6` |
| ferdowsi_department/1 | uupm-burgundy-gold | Vazirmatn / normal / 1320 / 8 | hero_banner(hero_style=atelier_triptych) → category_grid(display_mode=grid) → catalog_product_wall(layout_mode=featured_row) → product_section(data_source=newest,display_mode=grid) → brand_carousel → trust_features | P / S | `7472b68ab06dc1e4c2a480ae46cc4027b717fb256240f0cf9f710cc31c828c0a` |
| anniversary_mosaic/1 | uupm-creative-pink | Vazirmatn / normal / 1320 / 12 | announcement_bar → hero_banner(hero_style=chocolate_carousel) → category_grid(display_mode=circular) → catalog_product_wall(layout_mode=featured_row) → testimonials → newsletter | P / S | `f650471d8c874eb7bfbf9d0a3d7b73cac08c29dcfea7cbd50736b84fcb2abaa6` |

## Exact Home structure groups

Group membership means identical section-key sequence and row/container geometry, **not** identical appearance or content-selection settings. The 27 groups include singleton groups so the inventory accounts for all 50 recipes.

| Group | Recipes |
|---|---|
| H01 | dense_marketplace |
| H02 | premium_leather |
| H03 | warm_boutique |
| H04 | fashion_promo_catalog |
| H05 | playful_lifestyle |
| H06 | utility_catalog |
| H07 | editorial_jewelry |
| H08 | dark_digital |
| H09 | cedar_home, simorgh_market, rayan_tech |
| H10 | street_drop, racer_tech |
| H11 | premium_leather_noir, artisan_grain, coastal_product, handmade_luxe, horizon_story, silk_editorial, city_classic, kamand_artisan, watchmaker_round, parnian_editorial |
| H12 | search_market |
| H13 | pixel_play |
| H14 | literary_catalog, gallery_minimal |
| H15 | niloufar_glass, beauty_dew, laleh_play, almas_luxury |
| H16 | tool_finder, mother_utility |
| H17 | green_workshop, pine_eco, mirror_beauty |
| H18 | tower_department, harbor_imports |
| H19 | mina_community |
| H20 | tuska_bento |
| H21 | collection_index |
| H22 | roosta_zigzag, calligraphy_paper |
| H23 | aftab_price, charcoal_grill |
| H24 | mist_quiet, night_catalog |
| H25 | kite_playful |
| H26 | ferdowsi_department |
| H27 | anniversary_mosaic |

## Aliases and semantics that must not count as new visuals

**FACT:** Across the complete typed catalog, 119 keys map to 90 symbolic references. That 90 includes geometry/enums/virtual references, so it is not a visual-design count. Hero has 19 keys/6 references; layout17/8; product_view13/6. Header22/Footer16/Nav9 are registry totals, while 12/8/7 above are used by the 50 recipes. This explains all differences from the original audit.

| Alias group | Existing implementation | Product implication |
|---|---|---|
| hero.legacy_default, hero.none, hero.media_feature | Hero overlay | none does not hide an existing Hero through live component selection; recipe generator separately omits it |
| hero.split, editorial_split, typographic, quiet, search_first | Hero split | five names, one renderer |
| beauty_editorial, product_focus | Hero beauty | two names, one renderer |
| chocolate_carousel, promo_bento, side_offer_slider | Hero chocolate | three names, one renderer |
| atelier_triptych, image_collage, campaign_mosaic, social_gallery | Hero atelier | four names, one renderer |
| luxury_showcase, immersive | Hero luxury | two names, one renderer |
| layout.four_column, dense_five, quarters | composition:quarters | dense_five also sets grid_density6; no five-cell geometry follows from its name |
| layout.horizontal_rail, catalog_list, legacy_default | composition:single | no live container rebuild |
| product_view.grid, standard_grid, editorial_grid | product_section:grid | three selectors, one reference |
| product_view.dense_grid, catalog_group_columns | wall:group_columns | same implementation |
| product_view.bento, featured_wall, catalog_featured_row | wall:featured_row | same implementation |
| mega_menu.none | virtual no-op | not an implemented configurable menu family |

Source: `storefront_appearance/adapters.py:31–278`; runtime overlay `rendering.py:171` and `render_service.py:743–761`. The original audit §13 contains the exhaustive 119-key map.

## What these numbers establish

**FACTUAL CODE DIFFERENCE:** All 50 recipes differ in normalized declared inputs even after removing tokens/palette. They offer 27 Home structures and substantial recombination of global regions and existing variants. Their five non-Home section sequences are identical. Forty-five recipes instantiate Hero; six existing Hero renderer paths occur among those recipes.

**VISUAL DIFFERENCE NOT PROVEN:** Different tuples of refs, card classes or tokens do not establish 50 visually distinct, accessible, responsive, interactive full-store designs. Applied-manifest convergence is also unproven and source inspection exposes A02. No screenshots were treated as certification.

**RECOMMENDATION — enough raw material:** Header, Footer, Bottom Navigation, Hero and Category already have many implementation choices; Brand has three and Product Showcase has both source-driven shelves and grouped walls. Converge their contracts before adding names.

**RECOMMENDATION — new real variants only after product scope:** MegaMenu/MegaHeader/MegaFooter have no separate functional family contract. Newsletter, Cart and Product Detail have few or no explicit registered variant axes; deciding whether they need more designs is a product decision, not a numerical obligation. Collection Tiles already has two shared-loader variants despite zero Ready-recipe usage.

**Verdict:** 50 curated, code-distinct recipes with substantial reuse; not 50 certified independent full-store designs.

## Reproduction (read-only; no database calls)

Run this from the baseline repository with `python -B`; it enumerates definitions and validators only. The full-output hash is in the table above. Group by hash for duplicates; group by nt for token-excluded equality. Home structures are grouped by ordered (section_key,row_key,row_span,container_settings) before settings normalization.

```python
import os,json,hashlib,collections
os.environ.setdefault('DJANGO_SETTINGS_MODULE','shop_core.settings')
import django; django.setup()
from apps.storefront_builder.layout_preset_registry import list_ready_templates
from apps.storefront_builder.section_registry import get_definition
from apps.storefront_builder.storefront_appearance.registry import require_component
def encode(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)
out=[]
for p in list_ready_templates():
 refs={f:require_component(k).registry_reference for f,k in p.store_appearance['selections'].items()}
 pages={page:[{'section':e.section_key,'settings':get_definition(e.section_key).default_settings() if e.settings is None else get_definition(e.section_key).validate_settings(e.settings),'row':e.row_key,'span':e.row_span,'container':e.container_settings} for e in es] for page,es in p.pages.items()}
 dna={'refs':refs,'settings':p.store_appearance['settings'],'appearance':p.appearance,'palette':p.default_palette_slug,'header':p.header,'footer':p.footer,'pages':pages}
 no_tokens={k:v for k,v in dna.items() if k not in ('appearance','palette')}
 out.append({'key':p.key,'hash':hashlib.sha256(encode(dna).encode()).hexdigest(),'nt':hashlib.sha256(encode(no_tokens).encode()).hexdigest(),'home_render':hashlib.sha256(encode(pages['home']).encode()).hexdigest()})
print(json.dumps(out))
```
