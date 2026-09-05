# 01 — Current product and capability inventory

Baseline: `audit/storefront-appearance-g23`, HEAD `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`; 2026-09-05.

Evidence convention: **FACT** = source or executed read-only validation; **INFERENCE** = consequence, not an observed production incident; **RECOMMENDATION** = proposed architectural direction; **UNKNOWN** = needs deployment evidence or a Product Owner decision. Source paths are relative to `D:/Projects/RastiSi4_Golden_Manual/`; `:line` identifies the baseline source. No business database was queried or mutated. Existing audit remains unchanged.

Source locator shorthand used below: bare Builder modules (`models.py`, `views.py`, registries, schemas and `r4_views.py`) are under `apps/storefront_builder/`; service modules under `apps/storefront_builder/services/`; typed manifest modules under `apps/storefront_builder/storefront_appearance/`; bare test modules under `apps/storefront_builder/tests/`. Section/partial template names resolve beneath `apps/storefront_builder/templates/storefront_builder/`; `r4/editor.html` resolves to `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`. Catalog/Cart/Content template names resolve beneath the corresponding app's `templates/` directory. Root shells are `templates/base.html` and `templates/storefront_shell.html`. CSS: `apps/core/static/css/tokens.css`, `theme_palette.css`; `apps/catalog/static/css/home.css`, `product_card.css`, `product_list.css`, `product_detail.css`; `apps/storefront_builder/static/css/storefront_builder.css`, `storefront_builder_preview_v22.css`; `apps/cart/static/css/cart.css`.

## What a merchant can do today

RastiSi can assemble a storefront from registered sections, select colors and global regions, preview a Draft, and publish a version. It supports Home, Product Listing, Search, Product Detail, Collection and Cart. The older editor covers more controls/pages; R4 supplies a narrower Home editing experience with stronger revision handling. This is a functioning product foundation with uneven control coverage, not a complete uniform design system.

**FACT:** There are 36 section types,50 latest Ready recipes,10 token profiles and64 palettes. Only 4 sections have R4 settings schemas. Backend support for a typed component command is not evidence that a merchant sees a corresponding R4 panel. **UNKNOWN:** deployed adoption and browser quality across all designs.

Status definitions: **WORKING** = a bounded source-backed capability exists with a coherent path, not a blanket visual certification; **PARTIAL** = available with a material coverage/safety gap; **LEGACY-ONLY** = direct merchant control exists only in older UI; **CONFLICTING** = active paths have incompatible authority/semantics; **MISSING** = target capability absent from inspected storage/control/render contracts; **UNKNOWN** = evidence cannot establish it.

The following **40 capability rows** are the counting unit. Do not add page-action cells or registry variants to these counts. Counts: PARTIAL=21; CONFLICTING=4; LEGACY-ONLY=6; MISSING=5; WORKING=3; UNKNOWN=1.

## Merchant capability catalog

All rows state source-backed current behavior; target gap is a **RECOMMENDATION**, not an implemented feature. Writer codes match Report02 (R=R4, F=legacy form, S=structure, T=recipe/reset, U=history, L=lifecycle, M=media, C/V=live content/identity).

| Capability | Status | Persistence owner | Current UI entry | Write path | Render path | Known limitation | Target gap / evidence |
|---|---|---|---|---|---|---|---|
| Choose a coordinated palette | PARTIAL | Version appearance_config | R4 Global Design / legacy Appearance | R appearance.update; F appearance | appearance_registry → base tokens | 64 palettes; old form can erase typed state | One safe write boundary — appearance_registry.py:115; views.py:2248; r4_mutation_service.py:431 |
| Customize colors and theme roles | CONFLICTING | Version color/theme overrides; live ShopSettings fallback | Legacy Appearance / Settings → appearance | F appearance; V settings-appearance | resolve_colors/resolve_theme_roles → CSS | Two editing authorities; role cascade may beat general colors | Agree scope and preserve typed state — views.py:2282–2371; apps/dashboard/views.py:4385 |
| Choose font and type scale | PARTIAL | Version appearance; limited section typography | R4 Global Design / Hero inspector / legacy Appearance | R appearance.update, section.update_settings; F | section_appearance_service + base CSS vars | One global font/scale; narrow local override | Complete common typography contract — r4_views.py:151; section_appearance_service.py:15 |
| Set corner and button radius | LEGACY-ONLY | Version appearance_config | Legacy Appearance | F appearance; recipes | base tokens + component CSS | No direct R4 radius patch; fixed variant shapes may differ | Schema and cascade ownership — views.py:2288; r4_mutation_service.py:237 |
| Set card shadow | LEGACY-ONLY | Version appearance_config.card_shadow | Legacy Appearance | F appearance; recipes | token/profile + card CSS | No universal per-section shadow contract | Shared appearance contract — views.py:2310; apps/core/context_processors.py:178 |
| Set content density | LEGACY-ONLY | Version appearance_config.density | Legacy Appearance | F appearance; profile/recipe apply | base data attributes / CSS | R4 only indirectly via token-profile change | Explicit supported control — views.py:2290 |
| Set global content width | LEGACY-ONLY | Version appearance_config.content_width | Legacy Appearance | F appearance; recipes | context processor → CSS | Global numeric width and local categorical width differ | Defined inheritance — views.py:2308 |
| Set image fit/hover/crossfade/zoom | LEGACY-ONLY | Version appearance_config | Legacy Appearance | F appearance; recipes | base/card CSS and templates | No corresponding direct R4 patch | Shared image behavior controls — views.py:2300–2305 |
| Set decorative motion | PARTIAL | Version motion + manifest + section wrappers | R4 Global Design / legacy section settings | R/F | CSS/data attributes + timers | Global motion does not unify slider autoplay | Separate animation/playback contracts — r4_mutation_service.py:431; render_service.py:714 |
| Choose Header | CONFLICTING | Manifest + version header_config | R4 Header selector / legacy Header | R header/component; F header; T reset | global_renderer_template | 22 choices; old save can be ignored by manifest | One selection writer — views.py:2497; rendering.py:105 |
| Configure Header content/visibility | PARTIAL | Version header config + live Menu/ShopSettings | Legacy Header / Menus / Settings | F header; C/V | global Header partials + live context | Versioned toggles and live content distinct | Explain publication scope — views.py:2497; apps/content/context_processors.py |
| Choose/configure Footer | CONFLICTING | Manifest + footer_config + live FooterSettings | R4 Footer / legacy Footer / Footer settings | R/F/C/T | global Footer partials | 16 variants; mirror and live visibility gates | One selector + clear live policy — views.py:2537; apps/dashboard/views.py:5390 |
| Choose mobile bottom navigation | PARTIAL | Manifest.bottom_nav + footer_config | Legacy Footer; typed component API | F footer; R component API | global mobile partials | 9 registered incl hidden; no dedicated R4 panel | Mobile editing/certification — global_region_registry.py:431; r4/editor.html:82 |
| Configure independent MegaMenu/MegaHeader | MISSING | No real typed family beyond virtual none | No dedicated merchant panel | No real family settings writer | Existing Header dropdowns only | Menu markup is not a configurable family contract | Product scope D07 — storefront_appearance/adapters.py:95 |
| Configure independent MegaFooter | MISSING | No separate family contract | No dedicated panel | Footer controls only | Footer columns exist | Cannot count columns as a new family | Product scope D07 — storefront_appearance/families.py:98 |
| Change button style | PARTIAL | Version button_style | R4 Global Design / legacy Appearance | R/F | base/theme/button CSS | Filled/outline/soft roles share cascade limitations | Certified token behavior — r4_mutation_service.py:431 |
| Set product grid density/card hover | LEGACY-ONLY | Version grid_density/card_hover | Legacy Appearance | F appearance; recipe | token context / card rules | Not container geometry; no direct R4 patch | Honest control semantics — views.py:2309–2311 |
| Choose token-template profile | PARTIAL | Version template_slug | R4 Global Design / legacy Appearance | R/F | profile/default/token context | 10 profiles; this selector is not the 50-recipe gallery | Separate product terminology — r4_views.py:151; appearance_registry.py:116 |
| Build six page types | PARTIAL | Page/Section/Container/Cell | Legacy Builder page selector; R4 Home only | S; R structure Home | shared render_service | Required commerce sections restricted; non-Home R4 absent | Page editing coverage — models.py:518; section_structure_service.py:30 |
| Edit structured section content | PARTIAL | Section.settings + live domain references | R4 inspector for4 types; legacy forms | R schema patch; F settings | shared context builders | 4/36 R4 schemas; form entries do not expose every default field | Schema coverage — settings_schema.py:310; views.py:780 |
| Switch local visual variant | PARTIAL | Section.settings selector | R4 Hero/Brand/Product; legacy variant controls | R/F | variant_contract + manifest overlay | 7 explicit variant axes; global selection may mask local | D02 precedence — render_service.py:743–761 |
| Apply common section appearance | PARTIAL | Section.settings wrappers | Legacy section form; limited R4 Hero typography | F; R Hero patch | responsive wrapper + inner CSS | Background/spacing/width/card support varies by section | Complete common contract — views.py:895–918; section_registry.py:2445 |
| Create/rearrange containers and blocks | PARTIAL | Container/Cell/Section placement | Legacy container controls; R4 Home structure | S; R structure | container render items | Some old section routes rebuild from rows | One geometry authority — views.py:389–669; container_service.py |
| Control device visibility/columns | PARTIAL | Section responsive settings | Legacy settings | F settings | wrapper/data attrs + CSS | All hide flags; columns only selected types; browser proof absent | Per-family responsive certification — views.py:1179; responsive_section_wrapper.html:44 |
| Select an official Ready Template | PARTIAL | Recipe catalog + Draft provenance/composition | Ready Template gallery; API command exists | T apply-preset; R template API | shared section/global renderers | 50 recipes; complete declared manifest not applied (A02) | Declared/applied fidelity — preset_service.py:275; r4_mutation_service.py:393 |
| Preserve compatible content across template switch | MISSING | No semantic transition contract | Current Apply replaces covered pages | T/R recipe apply | new sections rendered | Checkpoint recovery is not in-place preservation | D05 switch policy — preset_service.py:443–460 |
| Preview Draft on six page types | PARTIAL | Draft + representative live content | Builder Preview iframe/page selector | GET may initialize Draft | preview.html shared core | R4 iframe Home-only; non-Home assets differ; cart representative empty | Shared envelope/certification — views.py:217–289; r4/editor.html:67 |
| See gallery thumbnails | WORKING | Recipe metadata + static captures/SVG | Ready Template gallery | read resolver; capture CLI separately | template_preview_service | Thumbnail is not a certified store screenshot | Keep freshness metadata — template_preview_service.py:327,478 |
| Upload Hero/Banner media; manage existing Story placements | PARTIAL | Placement + MediaAsset + legacy file | Section media panels | M routes | shared media URL properties | Story add/edit form is incompatible with its single image field; no revision/history wrapper; old routes can target same-store version rows | Media write/lifetime convergence — media_views.py:165; apps/dashboard/views.py:4826 |
| Choose background media or palette tone | PARTIAL | Section.background JSON | Legacy section appearance picker | F settings with ownership check | background media resolver / wrapper | JSON reference absent from GC; G2.3 persistence fixed | Complete reference accounting — views.py:1041–1081; apps/content/models.py:418 |
| Select Brand/Product/Collection resources | PARTIAL | Section source keys; domain owns content | R4 Product/Brand picker; legacy selectors | R/F | scoped domain loaders | Typed ResourceSource bridge only 2 section types; domain images edited elsewhere | Contract coverage — resource_source.py:321; render_service.py:329 |
| Publish a Draft | PARTIAL | Layout pointers and Version status | R4 Publish / legacy Publish | R publish; L publish | public resolver reads Published | Same lifecycle; old route bypasses revision; live domains remain live | One publish boundary — layout_service.py:773; r4_mutation_service.py:655 |
| Keep shopper layout separate from Draft | WORKING | Version states + published pointer | Publish lifecycle | layout_service | page_resolution_service | Does not freeze domain data/media filenames | Preserve lifecycle scope — page_resolution_service.py:49–112 |
| Undo/redo editing | PARTIAL | Version edit-history snapshots | R4 / legacy history controls | R history; U undo/redo | restored Draft shared renderer | Old route no revision; placement edits not independently recorded | Universal history coverage — edit_history_service.py:303; media_views.py:165 |
| Restore an archived layout version | WORKING | Archived Version + cloned Draft | Builder History → restore | L restore_version | Draft Preview then publish | Same-store source; no stale-client protection; files must survive | Preserve recovery, converge revision — layout_service.py:826 |
| Reset field/section/page/store to baseline | PARTIAL | template_baseline_snapshot + provenance | Legacy reset controls | T reset helpers | restored Draft renderer | Manual sections may lack slots; replacement/reset semantics; mirror drift | Unified reset command contract — preset_service.py:742–900 |
| Remember each variant's prior customization | MISSING | No per-variant settings memory | No dedicated control | Undo is separate | One current settings object | Switch-back memory not implemented | D06 policy — models.py:608; settings_schema.py:310 |
| Override appearance at Page scope | MISSING | No Page appearance field | No dedicated control | Page-owned sections only | no general Page resolver | Page composition is not Page appearance override | D04 policy — models.py:518–575 |
| Use locks with one consistent meaning | CONFLICTING | Section.is_locked | Legacy lock; structure guards | S lock; R structure/settings | editor/structure guards | R4 settings helper does not check lock; structure does | D09 lock semantics — r4_mutation_service.py:132; section_structure_service.py:109 |
| Certify all 50 designs on browsers/mobile | UNKNOWN | No completed baseline certification matrix established | No certification artifact from this audit | No browser runs | all full/fragment paths needed | Source tests/thumbnail presence cannot prove visuals | QA gate — Report05 |

## Six-page action matrix

Codes: **P=PARTIAL**, **L=LEGACY-ONLY**, **W=WORKING**, **M=MISSING**. A page cell describes merchant UI at this baseline. It does not imply that every section on that page permits the action. Ordinary eligible sections can be added/removed/duplicated, but required product_main/product_listing/collection_products/cart_items/cart_summary cannot be removed or duplicated. Other singleton sections also disallow duplication. Registry-specific restrictions are in Report03.

| Page | Add | Remove | Duplicate | Reorder | Move containers | Content | Variant | Common appearance | Specific appearance | Media | Preview | Publish | Undo/redo | Revision-safe editing |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Home | P | P | P | P | P | P | P | P | P | P | P | P | P | P: R4 subset only |
| Listing | L | P | P | L | L | P | P | P | P | P | P | P | P | M in page UI |
| Search | L | P | P | L | L | P | P | P | P | P | P | P | P | M in page UI |
| Product Detail | L | P | P | L | L | P | P | P | P | P | P | P | P | M in page UI |
| Collection | L | P | P | L | L | P | P | P | P | P | P | P | P | M in page UI |
| Cart | L | P | P | L | L | P | P | P | P | P | P | P | P | M in page UI |

Evidence: `views.storefront_editor:100–139` selects requested page; legacy operations `:389–1865`; registry page eligibility `section_registry.py:1957–2482`; R4 shell `r4_views.py:189–252` selects Home and iframe URL is page=home; R4 structural service `:30–43` enforces Home. R4 section.update_settings API can target schema-enabled sections on another active Draft page if addressed directly, but there is no matching non-Home shell. R4 publish acts on the whole Draft, including all pages.

For content/media cells: Builder edits appearance/content presentation and selected references. Product titles/prices/images, Brand logos, Collection details and Cart calculations remain in their existing domain editors/services. Merchants can insert eligible generic sections on non-Home pages, so “no variant/media on Cart” would be misleading; the required Cart parts themselves have no explicit variant axis.

## Global regions, library and templates in product terms

**FACT:** Header and Footer are global regions, not removable page sections. Their variant selectors coexist with live identity/navigation/footer content. Mobile navigation is selected under Footer config and the typed manifest. MegaMenu has only virtual none; there is no separate configurable MegaHeader or MegaFooter family. Source: `global_region_registry.py:285–448`, `storefront_appearance/families.py:98`.

**FACT:** The library is allowlisted, page-aware and subject to singleton/remove/duplicate constraints. Announcement Bar is hidden from new library selection but occurs in4 Ready recipes. Zero-use types such as Collection Tiles and Image Slider remain registered and available where allowed. A settings form on every section does not mean complete content controls; several legacy branches only edit wrappers (Report03).

**FACT:** Gallery Apply changes all six recipe-covered pages by deleting/recreating their sections/containers. It records baseline/recovery metadata; it does not map old content into new compatible section instances. R4 template API also replaces composition. Additionally, declared full manifest fidelity is incomplete (Report04 A02). “Choose a look” and “preserve all my existing content while switching” are therefore different current capabilities.

## Media and recovery behavior

**FACT:** Hero/Slider and Banner forms edit section placements with shared assets and legacy file fallback. Existing Story placements render and support list/delete/toggle/move/reorder, but the generic add/edit form is incompatible with StoryRailItem.image (media_views.py:165–200); it assumes desktop_image/mobile_image. Brand/Product/Collection images remain live domain media. Background selection stores a JSON asset ID, which current asset cleanup does not count. Editing live Hero/Banner routes can reach same-store version-associated placements without checking Draft status (Report02 A03).

**FACT:** Publish promotes a Draft, archives the prior Published version and clears the Draft pointer/history. Future editing clones the Published configuration. Restore creates a Draft from a chosen same-store historical version; it does not immediately publish it. Undo/redo is short-lived edit history, not per-variant customization memory. Baseline resets are tied to recipe/slot provenance. These distinct recovery operations should remain available while write safety converges.

**UNKNOWN:** historical layouts' actual asset recoverability and deployed use of older editors require a storage/database/traffic census. No production usage inference is made.

## Concise owner review table

| Capability | Status | Current owner | Main limitation | Target gap |
|---|---|---|---|---|
| Choose a coordinated palette | PARTIAL | Version appearance_config | 64 palettes; old form can erase typed state | One safe write boundary |
| Customize colors and theme roles | CONFLICTING | Version color/theme overrides; live ShopSettings fallback | Two editing authorities; role cascade may beat general colors | Agree scope and preserve typed state |
| Choose font and type scale | PARTIAL | Version appearance; limited section typography | One global font/scale; narrow local override | Complete common typography contract |
| Set corner and button radius | LEGACY-ONLY | Version appearance_config | No direct R4 radius patch; fixed variant shapes may differ | Schema and cascade ownership |
| Set card shadow | LEGACY-ONLY | Version appearance_config.card_shadow | No universal per-section shadow contract | Shared appearance contract |
| Set content density | LEGACY-ONLY | Version appearance_config.density | R4 only indirectly via token-profile change | Explicit supported control |
| Set global content width | LEGACY-ONLY | Version appearance_config.content_width | Global numeric width and local categorical width differ | Defined inheritance |
| Set image fit/hover/crossfade/zoom | LEGACY-ONLY | Version appearance_config | No corresponding direct R4 patch | Shared image behavior controls |
| Set decorative motion | PARTIAL | Version motion + manifest + section wrappers | Global motion does not unify slider autoplay | Separate animation/playback contracts |
| Choose Header | CONFLICTING | Manifest + version header_config | 22 choices; old save can be ignored by manifest | One selection writer |
| Configure Header content/visibility | PARTIAL | Version header config + live Menu/ShopSettings | Versioned toggles and live content distinct | Explain publication scope |
| Choose/configure Footer | CONFLICTING | Manifest + footer_config + live FooterSettings | 16 variants; mirror and live visibility gates | One selector + clear live policy |
| Choose mobile bottom navigation | PARTIAL | Manifest.bottom_nav + footer_config | 9 registered incl hidden; no dedicated R4 panel | Mobile editing/certification |
| Configure independent MegaMenu/MegaHeader | MISSING | No real typed family beyond virtual none | Menu markup is not a configurable family contract | Product scope D07 |
| Configure independent MegaFooter | MISSING | No separate family contract | Cannot count columns as a new family | Product scope D07 |
| Change button style | PARTIAL | Version button_style | Filled/outline/soft roles share cascade limitations | Certified token behavior |
| Set product grid density/card hover | LEGACY-ONLY | Version grid_density/card_hover | Not container geometry; no direct R4 patch | Honest control semantics |
| Choose token-template profile | PARTIAL | Version template_slug | 10 profiles; this selector is not the 50-recipe gallery | Separate product terminology |
| Build six page types | PARTIAL | Page/Section/Container/Cell | Required commerce sections restricted; non-Home R4 absent | Page editing coverage |
| Edit structured section content | PARTIAL | Section.settings + live domain references | 4/36 R4 schemas; form entries do not expose every default field | Schema coverage |
| Switch local visual variant | PARTIAL | Section.settings selector | 7 explicit variant axes; global selection may mask local | D02 precedence |
| Apply common section appearance | PARTIAL | Section.settings wrappers | Background/spacing/width/card support varies by section | Complete common contract |
| Create/rearrange containers and blocks | PARTIAL | Container/Cell/Section placement | Some old section routes rebuild from rows | One geometry authority |
| Control device visibility/columns | PARTIAL | Section responsive settings | All hide flags; columns only selected types; browser proof absent | Per-family responsive certification |
| Select an official Ready Template | PARTIAL | Recipe catalog + Draft provenance/composition | 50 recipes; complete declared manifest not applied (A02) | Declared/applied fidelity |
| Preserve compatible content across template switch | MISSING | No semantic transition contract | Checkpoint recovery is not in-place preservation | D05 switch policy |
| Preview Draft on six page types | PARTIAL | Draft + representative live content | R4 iframe Home-only; non-Home assets differ; cart representative empty | Shared envelope/certification |
| See gallery thumbnails | WORKING | Recipe metadata + static captures/SVG | Thumbnail is not a certified store screenshot | Keep freshness metadata |
| Upload Hero/Banner media; manage existing Story placements | PARTIAL | Placement + MediaAsset + legacy file | Story add/edit form is incompatible with its single image field; no revision/history wrapper; old routes can target same-store version rows | Media write/lifetime convergence |
| Choose background media or palette tone | PARTIAL | Section.background JSON | JSON reference absent from GC; G2.3 persistence fixed | Complete reference accounting |
| Select Brand/Product/Collection resources | PARTIAL | Section source keys; domain owns content | Typed ResourceSource bridge only 2 section types; domain images edited elsewhere | Contract coverage |
| Publish a Draft | PARTIAL | Layout pointers and Version status | Same lifecycle; old route bypasses revision; live domains remain live | One publish boundary |
| Keep shopper layout separate from Draft | WORKING | Version states + published pointer | Does not freeze domain data/media filenames | Preserve lifecycle scope |
| Undo/redo editing | PARTIAL | Version edit-history snapshots | Old route no revision; placement edits not independently recorded | Universal history coverage |
| Restore an archived layout version | WORKING | Archived Version + cloned Draft | Same-store source; no stale-client protection; files must survive | Preserve recovery, converge revision |
| Reset field/section/page/store to baseline | PARTIAL | template_baseline_snapshot + provenance | Manual sections may lack slots; replacement/reset semantics; mirror drift | Unified reset command contract |
| Remember each variant's prior customization | MISSING | No per-variant settings memory | Switch-back memory not implemented | D06 policy |
| Override appearance at Page scope | MISSING | No Page appearance field | Page composition is not Page appearance override | D04 policy |
| Use locks with one consistent meaning | CONFLICTING | Section.is_locked | R4 settings helper does not check lock; structure does | D09 lock semantics |
| Certify all 50 designs on browsers/mobile | UNKNOWN | No completed baseline certification matrix established | Source tests/thumbnail presence cannot prove visuals | QA gate |

**Product verdict:** Keep the existing storefront, commerce domains and shared rendering foundation. Before adding variants, make saving, applying templates, media lifetime and Preview/Public behavior predictable. Product decisions D01–D12 are recorded in Report07; this inventory does not silently choose those policies.
