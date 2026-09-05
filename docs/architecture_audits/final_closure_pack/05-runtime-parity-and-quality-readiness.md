# 05 — Runtime parity and quality readiness

Baseline: `audit/storefront-appearance-g23`, HEAD `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`; 2026-09-05.

Evidence convention: **FACT** = source or executed read-only validation; **INFERENCE** = consequence, not an observed production incident; **RECOMMENDATION** = proposed architectural direction; **UNKNOWN** = needs deployment evidence or a Product Owner decision. Source paths are relative to `D:/Projects/RastiSi4_Golden_Manual/`; `:line` identifies the baseline source. No business database was queried or mutated. Existing audit remains unchanged.

Source locator shorthand used below: bare Builder modules (`models.py`, `views.py`, registries, schemas and `r4_views.py`) are under `apps/storefront_builder/`; service modules under `apps/storefront_builder/services/`; typed manifest modules under `apps/storefront_builder/storefront_appearance/`; bare test modules under `apps/storefront_builder/tests/`. Section/partial template names resolve beneath `apps/storefront_builder/templates/storefront_builder/`; `r4/editor.html` resolves to `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`. Catalog/Cart/Content template names resolve beneath the corresponding app's `templates/` directory. Root shells are `templates/base.html` and `templates/storefront_shell.html`. CSS: `apps/core/static/css/tokens.css`, `theme_palette.css`; `apps/catalog/static/css/home.css`, `product_card.css`, `product_list.css`, `product_detail.css`; `apps/storefront_builder/static/css/storefront_builder.css`, `storefront_builder_preview_v22.css`; `apps/cart/static/css/cart.css`.

## Runtime conclusion

**FACT:** Preview and Public share the section engine, trusted variant resolution and most scoped data/media loaders. They do not share every response envelope, stylesheet or interaction definition. “Same template” is not proof of computed-style, mobile or fragment parity. **RECOMMENDATION:** Close the rendering boundary gaps before adding variants; preserve domain price, visibility, variant and cart services.

## A. Route-by-route Preview/Public matrix

Common Preview source **PV**: `/admin-portal/storefront-builder/preview/?page=TYPE` → `views.storefront_preview:217–289`. Gets/creates Draft, sets request appearance version, builds representative page context, calls shared render engine, retains empty editor containers, uses preview.html. It is not a safe database-read-only audit request.

Common Public visual source **PU**: published-only resolver `services/page_resolution_service.py:49–112` → `storefront_context_service.build_universal_storefront_context:56–181`. Never intentionally chooses Draft. Global choices pass through the same typed resolver; live ShopSettings/menus/catalog inputs remain live. Without a resolved Published page, Home uses old Home; non-Home uses default ephemeral sections.

| Page / Public route | Version / context difference | Section/global renderer | CSS envelope | JS | Media | Containers / emptiness | Card / appearance |
|---|---|---|---|---|---|---|---|
| Home / | PV Draft/representative vs PU Published/live store; catalog.views.home:48 | PV shared sections/global; PU home_visual.html when resolved; catalog/home.html fallback otherwise | both Home/core Builder/card layers; PV adds storefront_builder_preview_v22.css | Hero/Product inline behavior; PV editor flags/iframe reload | shared scoped placement/asset fallback; live fallback can change | PV include_empty; PU hides optional empty product sections/containers | same manifest overlay and shared standard card on full visual path; legacy Home separate |
| Listing /products/ | PV listing context vs actual filters/pagination; catalog.views.product_list:353 | same product_listing on full page; HX bypasses universal setup | PV Home/card/builder/preview; PU product_list.css + card/builder shell | listing HTMX filters/pagination; public-only syncFilters mobile script | domain product DTO/media; category context | shared full-page containers; fragment not section pipeline | full settings.card supplied by section; HX omits it |
| Search /products/?q=… | PV search page context vs actual query; same product_list view selects search | same listing renderer, distinct stored search page | same mismatch as Listing | HTMX same route; query determines page | domain search result images | full page may have search-specific composition; HX only results | same missing appearance projection on HX |
| Product Detail /products/<slug>/ | PV newest representative visible product vs actual requested product/variants; catalog.views:443,500 | product_main/description/video/related through shared engine; globals shared | PV omits public product_detail.css | copied variantSelector registration in public page and section; PV gets section copy | actual domain gallery/variant image; shared section media | no representative product yields empty data; required section remains defined | shared related card; product domain prices/options preserved |
| Collection /collections/<slug>/ | PV latest public collection vs requested collection; catalog.views:594 | collection_header/products shared; global resolver shared | PV Home envelope; PU product_list.css/card | collection page links/cards; no dedicated collection detail HX branch found | live collection image + product images | shared containers; collection content emptiness from domain | shared standard product card and manifest on full page |
| Cart /cart/ | PV empty cart vs actual shopper cart; cart.views:17,63 | full shared cart sections/global resolver | PV omits public cart.css | update/remove use custom fragment path | live product/variant images; no placement snapshot of cart contents | PV empty fixture; PU real rows; fragment only rows and render_items, no container composition | line items use commerce context, not standard card; fragment lacks full appearance request setup |

**FACT:** Collection index `/collections/` (`catalog.views.collection_index:569–591`) is a companion direct template flow, not a seventh StorefrontPage type. Treat its global shell and cards/tiles separately during later certification; it is not evidence of a second collection detail composition.

**FACT:** Candidate `preview_template` proxy is installed after render items were built (`views.py:257–263`). It changes token-template context; it is not an exact simulation of a different full recipe/manifest. **INFERENCE:** this can compare different global and precomputed local appearance inputs.

Evidence for assets: `templates/base.html:3–39`; `apps/catalog/templates/catalog/home_visual.html`, `product_list.html`, `product_detail.html`, `collection_detail.html`; `apps/cart/templates/cart/cart_detail.html`; `apps/storefront_builder/templates/storefront_builder/preview.html`. Shared wrapper `partials/responsive_section_wrapper.html:44–80`; container build `render_service.py:926`; empty hiding `:906`.

## B. Full page versus fragment census

Scope: every distinct server partial response in the six catalog/cart flows, plus shared component actions reachable there (newsletter, wishlist and authentication modal). Error/success branches of one endpoint are recorded together. Account management, checkout and unrelated dashboard panels are outside the six-page rendering scope. No AJAX response in product/collection detail views was found beyond the listed component actions.

| Endpoint / consumer | Partial and context | Omitted compared with full page | Assessment |
|---|---|---|---|
| GET /home/best-products/?sort=…; legacy Home tabs | catalog/partials/product_grid.html; home_best_products:123–129 | no universal version/section/card-settings setup | legacy direct shelf, not visual Builder section replacement; styling projection separate |
| GET /products/ with HX-Request=true; listing/search filters, chips, clear, pagination | product_list_results.html; product_list:357–362; build_product_listing_context:300 | no shared section settings.card, manifest projection or composition setup before early return | **confirmed input omission**; page wrapper CSS may remain but card settings reset to defaults |
| POST /products/<slug>/review/ | review_form.html; product_review_create:530–566; product/form errors or success | no full layout/version/section settings | intentional narrow form replacement; styling inherits page; no proof of customized form contract across variants |
| POST /cart/add/<slug>/ from card/PDP | header_counts_oob.html; cart_add:96–143 plus error helper:85–92 | no full region/section renderer; only badge/count projection + toast trigger | intentional OOB contract; needs all Header/Nav DOM-target compatibility testing |
| POST /cart/items/<id>/update/ | cart_sections_body.html via _render_cart_container:37–60; quantity/stock errors share path | no container items/use-container flag; no full universal appearance setup | **confirmed container-envelope gap**, despite reuse of section/row renderer |
| POST /cart/items/<id>/remove/ | same cart_sections_body helper | same | same defect class, counted as separate endpoint but one architectural problem |
| GET /cart/preview/?mode=…; Header hover/click | cart_preview.html; cart_preview_partial:200–215 | not selected by Header manifest/config except client-provided allowlisted mode; no section composer | intentionally small preview projection; verify customized Headers keep mode/targets coherent |
| POST /pages/newsletter/subscribe/; Newsletter section | content/partials/newsletter_form.html; content.views.newsletter_subscribe:22–40 | response supplies error/subscribed only; original section include supplied button_label=settings.button_label | **FACT A04:** invalid/rate-limited response falls back to default button label, losing custom label; outer title/subtitle wrapper retained |
| POST wishlist toggle; card/PDP included wishlist button | customers/partials/wishlist_button.html; customers.views.wishlist_toggle:40–67 | product/wishlist IDs only; no full card appearance or shell | intentional button-only replacement; unauthenticated branch emits open-login; no whole-card rebuild |
| POST login/signup; Header or wishlist-triggered shared auth modal | customers/partials/auth_forms.html; customers.views:82–133 | auth form/error state only, no section/global render recomputation | intentional shared business modal; inherited styles remain, successful auth effects need interaction proof |
| OTP reset/request/login; shared modal | customers/partials/otp_login_body.html; customers.views:149–215 | OTP state/form context, no Builder appearance projection | intentional auth island; no new per-variant authentication engine |

Route definitions: `apps/catalog/urls.py`, `apps/cart/urls.py`, `apps/content/urls.py`, `apps/customers/urls.py`. Consumer attributes traced in `catalog/partials/product_list_results.html:20–62`, `storefront_builder/sections/product_listing.html:19,99`, `cart_items.html:40–44`, `product_main.html:72`, `catalog/partials/product_card.html:48–104`, `customers/partials/wishlist_button.html:3`.

**INFERENCE:** Fragment replacement is part of the appearance contract whenever it reconstructs merchant-customized content. Newsletter A04 is an additional closure example under original C09/R3; it does not imply subscriber business logic should change. Full-page/fragment differences are not all bugs: OOB counts and auth forms intentionally replace smaller islands.

## C. Material CSS ownership

| Owner/layer | Source / consumer | Material overlap | Readiness |
|---|---|---|---|
| Global resolved tokens | core.context_processors.shop_settings:119–218; base.html:3–15; appearance_registry:156–225 | version palette/colors/theme roles and legacy live color seed/fallback | token aliases legitimate; selection/write authority still conflicted |
| Token aliases | static CSS tokens.css; --brand-* → legacy --violet/--pink/--bg/--card and theme vars | multiple names can represent same resolved color | do not delete aliases without all consumers |
| Theme rules loaded after page CSS | base.html:33–39; theme_palette.css:32–84 | .header background/color forced with !important; inner variants also own geometry/colors | requires explicit role-vs-variant authority |
| Component rules | Builder/global/card styles; dark Header counter-rule | test_u2a_global_header_system:708–724 asserts theme forced rule and dark counter-rule | source test proves competition, not correct browser cascade |
| Local inline appearance | responsive_section_wrapper.html:44–56 | local background/spacing and layout data attrs vs inner component surfaces | local wrapper change need not color inner component |
| Inline Brand layout | brand_carousel.html:30–31 + home.css | G2.3 flex/grid fallback duplicates layout for resilience; fixed auto-fill grid/gap | intentional fix to preserve; responsive-column meaning still needs certification |
| Page assets | public detail/list/cart templates vs preview.html | Preview loads Home envelope for all page types, omits matching public page CSS | confirmed source mismatch; visual impact not measured |
| Preview-only rules | storefront_builder_preview_v22.css and editor markers | editor placeholders/device-frame behavior | isolate intentional editor affordances from shopper-style parity |

**RECOMMENDATION:** Agree token, component and local-scope responsibilities; retain necessary component geometry. Do not use “remove all hardcoded CSS” as an architectural policy. No CSS was changed or rendered in a browser during this pass.

## D. Media reference and lifetime graph

**FACT:** `MediaAsset.is_referenced:418–432` checks five reverse-FK relations, without filtering lifecycle state. Consequently real FK placements in Published, Draft and archived versions are counted. That protection does not extend to JSON, history payloads or arbitrary shared legacy file paths.

| Reference form | Stored/read by | Deletion/reference accounting | Consequence |
|---|---|---|---|
| Hero desktop/mobile asset FKs | HeroSlide; shared media URL properties | yes, two reverse relations | extant placements keep asset alive across versions |
| Banner desktop/mobile asset FKs | PromotionalBanner | yes, two reverse relations | same |
| Story image asset FK | StoryRailItem | yes, one reverse relation | same |
| JSON section background media_asset_id | Section.settings.background; resolve_background_media_url:132–156 | **no** in is_referenced | last placement deletion may remove a still-visible background |
| Published placement FK | cloned/promoted version-associated rows | yes while row exists | lifecycle status itself is not an exclusion |
| Draft placement FK | Draft section-associated rows | yes while row exists | direct old live form bypass remains possible (A03) |
| Archived placement FK | archived version sections | yes while row exists | archive data rows preserve shared assets; not a retention policy guarantee |
| Edit-history media IDs/files | edit_history_service._serialize_media:59; snapshot_draft:124; _restore_media:148 | **no history JSON traversal** in GC | saved undo state is not a physical-file reference counted by cleanup |
| Template baseline/settings snapshots | template_baseline_snapshot, nested settings | no JSON traversal | background/media URLs in a snapshot do not protect assets |
| Legacy desktop/mobile/image file names | placement FileFields; clone helper:589–635 | no complete cross-row filename accounting; replacement schedules storage.delete | sharing may break after one replacement; actual sharing incidence UNKNOWN |
| Generic image_url/video_url | section JSON for image_text/video_section | not a MediaAsset FK; no repository ownership of arbitrary URL | external lifetime outside asset GC |
| ProductImage/Brand.logo/Collection.image/Category.image | catalog/domain records | separate domain file ownership; not MediaAsset graph | preserve business editing and policies; no claim of complete domain GC |
| ShopSettings logo/favicon + footer badge/payment files | live identity/footer endpoints | direct old-file deletion on replacement | live by policy; no layout snapshot of file bytes |
| Template/static media | fashion_lifestyle_hero static paths; gallery captures/SVG | not merchant asset GC | source/deploy artifact lifetime; not proof of production rendering freshness |
| Store-wide placement fallback | section=null active placements selected when no scoped-active placement | FK assets counted if present; legacy paths not globally counted | hiding all scoped slides may expose live fallback instead of empty section |

Deletion chain: `media_views.storefront_section_media_delete:242–298` → `content.services.delete_media_asset_if_unreferenced:211–241` → `MediaAsset.is_referenced` → on-commit physical deletion. Replacement cleanup is a separate chain `media_views.py:202–220`; old dashboard Hero/Banner routes have direct cleanup too.

**RECOMMENDATION:** Define whether archived/history states promise media recovery (D11) before retirement or cleanup. Required evidence is a complete reachable-reference census plus retained-file policy. Do not query production or delete anything as part of this audit.

## E. Confirmed frontend behavior duplication

| Behavior | Evidence | Classification / effect |
|---|---|---|
| Alpine variantSelector definition | catalog/product_detail.html:38–165 and storefront_builder/sections/product_main.html:181–296 | **confirmed copied definition** after excluding blank/comment lines in original audit; public page can include both, Preview section one |
| Generic Hero slider autoplay/loop/navigation | Hero shared slider body + Hero templates | shared core partial exists; not every Hero variant uses the same behavior |
| Fashion static slider | fashion_lifestyle_hero.html:24–45 | separate settings/static media and timer, not byte-identical Hero engine |
| Product shelf carousel | product_section.html inline Alpine timer/options | similar playback responsibility but distinct product interaction; no claim of byte-identical copy |
| Luxury/Atelier Hero presentation | hero_banner_luxury.html and hero_banner_atelier.html | different behavior/controls; one Hero settings schema does not prove every option is honored |

Only variantSelector is claimed as verified copied code. Slider rows are shared-responsibility divergence, matching C12, not invented copy counts. **RECOMMENDATION:** one behavior definition where semantics match; explicit family capability metadata where interaction intentionally differs.

**FACT — envelope behavior difference:** `catalog/product_list.html:16–35` registers syncFilters using matchMedia and htmx:afterSwap; Preview's template does not include this page extra_js block. This is an additional source-level mobile behavior difference, not measured browser output.

**FACT — Story editing exception:** `media_views.py:165–200` hardcodes desktop/mobile fields while StoryRailItem owns image. The generic Story add/edit form is unsupported even though its renderer, clone/delete and ordering paths exist. Include it in media/schema convergence; do not certify Story uploads from FK lifecycle tests.

## F. Appearance-related query/performance risks only

| Pattern | Source fact | Inference / bounded risk |
|---|---|---|
| Representative Category media | render_service._category_grid_context:126–165 conditionally calls section_data_service.resolve_category_representative_media:54; helper does ordered .first() with images prefetch per category | work grows with category count for selected display modes; no latency/query benchmark claimed |
| Grouped product wall | render_service._catalog_product_wall_context:169–254 queries groups and resolves sibling product selections for exclusion | group/sibling-dependent work can repeat; aggregation is partly intentional, not a reason to remove domain rules |
| Per-instance loader cache | render_service.PER_INSTANCE_SECTION_KEYS:481 and _build_items_from_sections:769 | protects distinct section settings, but duplicate sections intentionally execute distinct data work; cache is request-local |
| ORM-shaped card DTO input | catalog/services/product_card_service.py:100 uses product media/brand properties | callers without appropriate prefetch may pay extra queries; do not claim all callers fail prefetch |
| Listing children traversal | product_listing.html:50,113 uses cat.children.all; catalog.views listing context prefetches children | inspected counterexample: traversal alone is **not** evidence of an N+1 here |
| Full then HTMX work | product_list:353 builds fresh filter context for each request; cart helper separately builds composition rows | distinct requests repeat business work by design; architectural defect is omitted appearance/container state, not a proven simultaneous double-query bug |
| History snapshot cost | edit_history_service.snapshot_draft:124 walks pages/sections/media/containers before and after recorded mutations | grows with editable content; no measured production limit or performance incident established |

No broad performance audit, load test or production query trace was performed. **UNKNOWN:** store sizes, request latency, actual query budgets and warm caches.

## G. QA proof status

Codes: **RUN** = executed during closure pass; **INS** = existing automated assertions inspected, not executed here; **GAP** = target guarantee absent from inspected coverage; **BROWSER** = requires later real-browser certification. INS does not mean failing, and GAP does not assert no test exists anywhere in the repository.

| Family/page boundary | Contract tested | Server render tested | Preview/Public roundtrip | Browser visual | Mobile | Fragment | Tenant | Revision |
|---|---|---|---|---|---|---|---|---|
| Typed registry/manifest | RUN52 aggregate contract suites | template compilation only | INS persistence suite | BROWSER | BROWSER | GAP application envelope | INS mutation ownership | INS R4 mutation tests |
| Hero/Slider/media | INS variants/schema | INS G22 | INS G22 clone/preview, selected lifecycle | BROWSER | INS media-source markup; BROWSER layout | GAP all behavior paths | INS scoped assets | INS schema subset; GAP media/old routes |
| Brand | INS schema/variant | INS G23 | INS G23 publish into public | BROWSER | BROWSER | GAP general section replacement | INS G23/source ownership | INS R4 patch; GAP old writer |
| Category/Collection | INS registry/validators | INS G23 Collection | INS Collection roundtrip | BROWSER | BROWSER | GAP generic parity | INS scoped source tests | GAP uniform page/legacy control |
| Product Showcase/card | INS ProductCardData/source | INS card/variant markup | selected tests; not all 50 | BROWSER | BROWSER | GAP card settings on listing HX | INS domain/selection ownership | INS product_section only |
| Header/Footer/Nav | RUN registry identity subset; INS config validators | INS global shell/variant tests | INS same-template shell assertions | BROWSER | source/CSS checks only; BROWSER | GAP all OOB target combinations | INS context scoping | INS R4; GAP legacy mirror routes |
| Listing/Search | INS listing context tests | INS full/partial templates | GAP full customization roundtrip | BROWSER | BROWSER | INS response shape; GAP card appearance preservation | INS scoped catalog | GAP page UI |
| Product Detail | INS domain/variant/card tests | INS page/section markup | GAP asset/interaction parity | BROWSER | BROWSER | INS review response shape; no visual proof | INS scoped product | GAP page UI |
| Cart | INS business/cart tests | INS section/partial shape | GAP custom container roundtrip | BROWSER | BROWSER | INS shape; GAP container fidelity | INS cart ownership | GAP page UI |
| Newsletter/Story/Other | INS registry/media subset | INS selected templates | GAP end-to-end family matrix | BROWSER | BROWSER | A04 label omission; GAP custom response proof | shared domain scoping inspected | GAP complete schemas/media |
| Ready Templates50 | RUN A8 declaration contracts | template paths compile | **GAP declared→applied full manifest**, A02 | BROWSER | BROWSER | GAP all designs | no deployment census | INS R4 template wrapper; GAP other apply paths |

Important existing assertion sources: `test_r4_mutation_api.py:46–277` (including explicit legacy write without revision), `test_r4_store_appearance_mutations.py:75–291`, `test_r4_store_appearance_persistence.py:70,113,139`, `test_r4_settings_schema.py:469–492`, `test_r4_appearance_overrides.py:277–389`, `test_u4_component_variants.py:79–289`, `test_g23_builder_public_content_appearance.py:107–335`, `test_g22_preview_media_render_consistency.py:134–358`, `test_media_asset_lifecycle.py:57,63,431`, `test_page_shell.py:60–79`, `test_phase2c_content_preserving_layout_changes.py`. Tests are under `apps/storefront_builder/tests/` unless domain paths are named.

Executed closure validation:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B manage.py test apps.storefront_builder.tests.test_r4_store_appearance_contracts apps.storefront_builder.tests.test_r4_store_appearance_registry apps.storefront_builder.tests.test_r4_store_appearance_validation apps.storefront_builder.tests.test_r4_store_appearance_compatibility apps.storefront_builder.tests.test_a8_ready_template_contracts --verbosity 1
```

Result: **52 tests passed**, Django system check no issues, no test database setup. Original audit executed 42 of these; the 10 A8 contract tests account for the difference. These are declaration/validation contracts, not proof of recipe persistence. Imports, registry enumeration, validators and hashing made no database queries. Original audit compiled90 renderer paths; closure verification recompiles the same union (recorded in final validation).

No database-backed suite, browser session, screenshot comparison, public product request (view-count write), cart request (cart creation), Preview request (Draft creation), screenshot capture command or QA seed command was run.

## Runtime gates before variant expansion

**RECOMMENDATION:** Preserve the current engine, then require evidence of (1) manifest-preserving writes and full recipe application fidelity; (2) all editing/media/publication entering the revision boundary; (3) full/fragment card, container and customized form context fidelity; (4) complete asset reachability; (5) matching Preview/Public page assets and agreed CSS authority; (6) declared Hero/slider behavior compatibility; and (7) desktop/mobile/accessibility interaction proof with customized data. Original P0/P1 risks all remain represented in Report07.
