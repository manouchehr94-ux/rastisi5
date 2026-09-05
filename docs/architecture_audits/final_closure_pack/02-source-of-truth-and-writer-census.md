# 02 — Source of truth and writer census

Baseline: `audit/storefront-appearance-g23`, HEAD `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`; 2026-09-05.

Evidence convention: **FACT** = source or executed read-only validation; **INFERENCE** = consequence, not an observed production incident; **RECOMMENDATION** = proposed architectural direction; **UNKNOWN** = needs deployment evidence or a Product Owner decision. Source paths are relative to `D:/Projects/RastiSi4_Golden_Manual/`; `:line` identifies the baseline source. No business database was queried or mutated. Existing audit remains unchanged.

Source locator shorthand used below: bare Builder modules (`models.py`, `views.py`, registries, schemas and `r4_views.py`) are under `apps/storefront_builder/`; service modules under `apps/storefront_builder/services/`; typed manifest modules under `apps/storefront_builder/storefront_appearance/`; bare test modules under `apps/storefront_builder/tests/`. Section/partial template names resolve beneath `apps/storefront_builder/templates/storefront_builder/`; `r4/editor.html` resolves to `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`. Catalog/Cart/Content template names resolve beneath the corresponding app's `templates/` directory. Root shells are `templates/base.html` and `templates/storefront_shell.html`. CSS: `apps/core/static/css/tokens.css`, `theme_palette.css`; `apps/catalog/static/css/home.css`, `product_card.css`, `product_list.css`, `product_detail.css`; `apps/storefront_builder/static/css/storefront_builder.css`, `storefront_builder_preview_v22.css`; `apps/cart/static/css/cart.css`.

## Scope, counts and counting rules

**FACT:** **86 mutation-capable HTTP routes** in the explicitly bounded Appearance/Builder scope: **76 explicit POST write endpoints** (45 Builder + 31 live identity/navigation/footer/placement endpoints), plus **10 additional Builder GET entry points** that can provision a layout or Draft/containers. Count one URL pattern once, even if it accepts several methods or two URLs share a view. Dynamic kind/ID values do not create additional endpoints. R4's 11 mutation commands are separately enumerated, not counted as 11 HTTP routes.

- **Canonical revision-safe explicit endpoints: 3**: R4 mutate, history, publish.
- **Legacy/non-revision-safe explicit endpoints: 73**: 42 Builder +31 live domain endpoints.
- **Additional initialization GET routes without edit-revision checks: 10**.
- **Total mutation-capable routes outside the R4 edit-revision boundary: 83**. Live business editing is intentionally live; “non-revision-safe” here means no Builder edit_revision protocol, not inherently defective domain behavior.
- **19 appearance concepts examined: 18 with multiple active write authorities/entry policies, 1 with a clear monotonic-update owner** (Draft revision). This is a concept census, not a count of databases or duplicate modules.

This is complete for registered Builder URLs plus direct storefront identity/menu/footer/placement editing. It does not count every catalog/product/order endpoint as an Appearance writer merely because live business data appears on a page. Those remain domain inputs. Industry installation updates catalog taxonomy rather than a Builder Draft (`catalog/services/industry_template_service.py:45`); the explicit Builder apply-industry route is counted. CLI tooling, bootstrap/services and domain provisioning are enumerated separately and are not HTTP endpoints. No registered Django admin for Builder/content models was found; core admin only registers read-only AuditLogEntry.

Evidence: `apps/dashboard/urls.py:219–350`, settings routes earlier in that file; `shop_core/urls.py:41` prefixes all listed paths with **/admin-portal/**. Names below are in the **dashboard:** namespace. View ranges are baseline line numbers; underlying helpers are listed per row. AST enumeration of path() calls and view bodies was cross-checked against methods, decorators and persistence calls.

## Safety profiles used by the endpoint rows

Every row inherits the complete profile below, with explicit row exceptions. “Preserve unrelated” refers to state outside the operation's declared target; delete/reset intentionally changes its declared target.

| Profile | Authorization / tenant constraint | Lifecycle target | Revision / history | Unrelated state | Manifest / mirrors | Classification |
|---|---|---|---|---|---|---|
| R | staff + STOREFRONT_LAYOUT_MANAGE; R4 feature gate; store layout + locked active Draft; IDs constrained to it | active Draft, or promotion on publish | required base_revision, atomic locks; mutation snapshot/history; undo/redo advances revision; publish clears edit history | command-scoped preservation, except explicit template replacement | command-dependent; see next table | CANONICAL |
| F | staff + same layout permission; resolve request.store; scoped section requires same-store Draft status | Draft | no revision; _record_edit_history snapshots around POST | form reconstructs target dictionary; **not guaranteed** for omitted target fields | appearance form can erase manifest; header/footer do not synchronize; section settings may be masked by manifest | LEGACY |
| S | staff + layout permission; scoped container/cell/section by store and Draft; page ownership checked in operations | Draft sections/geometry/flags | no revision; _record_edit_history | limited by operation; row rebuild routes may replace container representation; locks/cardinality conditional | not a manifest writer; no sync needed for intended structural operation | COMPATIBILITY |
| T | staff + layout permission; current store Draft, baseline/provenance helpers; locks checked for recipe replacement | Draft/config/composition + checkpoint for destructive reset/apply | no revision; history decorator except apply-industry; checkpoints are recovery, not concurrency | granular target retained; whole-page/template apply replaces declared sections | reset replays snapshot; granular selector resets no typed sync; legacy recipe apply ignores declared manifest | LEGACY (industry initialization is MIGRATION) |
| U | staff + layout permission; current store Draft | current Draft restored from edit-history snapshot | no revision; moves undo/redo history cursor, not a new edit event | snapshot scope; may overwrite concurrent changes | restores saved dictionaries together, no reconciliation with external intervening writes | COMPATIBILITY |
| L | staff + layout permission; current layout; restore source scoped to layout | publish/archive/discard/clone-to-Draft | no revision; lifecycle recovery/archive, not ordinary undo entry | operation-defined lifecycle scope | clone preserves prior dictionaries including any inconsistency | LEGACY |
| M | staff + layout permission; _get_scoped_section (store + Draft status), item under that section; kind allowlist | section placement rows, shared assets/files | no revision; no edit-history wrapper | placement fields; file replacement/deletion can affect shared references | no manifest sync; background JSON separate | LEGACY |
| G | staff + layout permission; resolves store; R4 entries additionally feature-gated | provision layout or Draft + compatibility containers | no edit revision or ordinary user edit-history entry | initialization only, but GET is not guaranteed read-only | bootstrap seeds appearance; cloning copies saved dictionaries | COMPATIBILITY / MIGRATION |
| V | staff + SETTINGS_MANAGE; request.store; ShopSettings.load scoped | live identity/colors/files | no Builder revision/history | named identity fields retained except submitted replacement/reset | no version/manifest synchronization | LEGACY for colors; CANONICAL live identity responsibility |
| C | staff + CONTENT_MANAGE; object store or menu__store checks; full_clean on forms | live domain content; **legacy Hero/Banner edit/delete/toggle does not constrain section version status** | no Builder revision/history | named content records/files; delete intentionally removes record | no version/manifest synchronization | CANONICAL domain content, LEGACY for section-placement compatibility writes |

Authorization definitions: `apps/dashboard/decorators.py:48–135`; scope helpers `views.py:316–336,765–774`; mutation lock `r4_mutation_service.py:561–585`; media configuration `media_views.py:41–115`. A Draft-status filter on old routes is weaker than pinning the active Draft and revision. R4 layout provisioning happens before command execution in the view, so even those views have an initialization side effect outside the edit command; their **edit** operations remain revision-checked.

## Complete explicit Builder write endpoint table (45)

Method is POST for mutation. GET/POST means GET serves the form (and some forms initialize Draft); mutation still occurs only in POST. Service “direct” denotes model calls in the named view, not an omitted hidden service. History Yes means the legacy decorator unless profile R/U specifies otherwise.

| URL suffix (after /admin-portal/) | URL name | Mutation method | View / source line | Service or direct writer | State changed | Profile / history |
|---|---|---|---|---|---|---|
| storefront-builder/r4/mutate/ | storefront-builder-r4-mutation | POST | apps/storefront_builder/r4_views.py:262 storefront_r4_mutation | r4_mutation_service.apply_mutation | command-specific Draft JSON/sections/geometry | R / R rules |
| storefront-builder/r4/history/ | storefront-builder-r4-history | POST | apps/storefront_builder/r4_views.py:464 storefront_r4_history_command | r4_mutation_service.apply_history_command | Draft snapshot contents + history flags + revision | R / R rules |
| storefront-builder/r4/publish/ | storefront-builder-r4-publish | POST | apps/storefront_builder/r4_views.py:515 storefront_r4_publish | r4_mutation_service.publish_draft | version statuses; published/draft pointers; history cleared | R / R rules |
| storefront-builder/containers/add/ | storefront-builder-container-add | POST | apps/storefront_builder/views.py:389 storefront_container_add | container_service.create_empty_container | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/containers/<int:pk>/settings/ | storefront-builder-container-settings | GET/POST | apps/storefront_builder/views.py:414 storefront_container_settings | direct view/model; validation helpers | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/containers/<int:pk>/layout/ | storefront-builder-container-layout | POST | apps/storefront_builder/views.py:480 storefront_container_layout | container_service.change_container_layout | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/containers/<int:pk>/move/ | storefront-builder-container-move | POST | apps/storefront_builder/views.py:498 storefront_container_move | direct view/model; validation helpers | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/containers/<int:pk>/remove/ | storefront-builder-container-remove | POST | apps/storefront_builder/views.py:527 storefront_container_remove | container_service.get_cell_blocks | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/cells/add-section/ | storefront-builder-cell-add-section | POST | apps/storefront_builder/views.py:548 storefront_cell_add_section | container_service.add_block; container_service.create_empty_container; container_service.get_cell_blocks; container_service.place_section | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/cells/<int:pk>/clear/ | storefront-builder-cell-clear | POST | apps/storefront_builder/views.py:624 storefront_cell_clear | container_service.get_cell_blocks | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/sections/add/ | storefront-builder-section-add | POST | apps/storefront_builder/views.py:676 storefront_section_add | container_service.rebuild_page_from_legacy_rows | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/sections/reorder/ | storefront-builder-section-reorder | POST | apps/storefront_builder/views.py:1762 storefront_section_reorder | container_service.rebuild_page_from_legacy_rows | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/blocks/<int:pk>/move/ | storefront-builder-block-move | POST | apps/storefront_builder/views.py:1664 storefront_block_move | container_service.get_cell_blocks; container_service.move_block | section locked flag | S / Yes |
| storefront-builder/blocks/<int:pk>/remove/ | storefront-builder-block-remove | POST | apps/storefront_builder/views.py:1727 storefront_block_remove | container_service.remove_block | section locked flag | S / Yes |
| storefront-builder/sections/<int:pk>/settings/ | storefront-builder-section-settings | GET/POST | apps/storefront_builder/views.py:780 storefront_section_settings | direct view/model; validation helpers | Section.settings (variant/background/card/content) | F / Yes |
| storefront-builder/sections/<int:pk>/row-layout/ | storefront-builder-section-row-layout | POST | apps/storefront_builder/views.py:1274 storefront_section_row_layout | container_service.rebuild_page_from_legacy_rows | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/sections/<int:pk>/remove/ | storefront-builder-section-remove | POST | apps/storefront_builder/views.py:1532 storefront_section_remove | container_service.rebuild_page_from_legacy_rows; row_service.is_row_member | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/sections/<int:pk>/toggle/ | storefront-builder-section-toggle | POST | apps/storefront_builder/views.py:1568 storefront_section_toggle | direct view/model; validation helpers | section active flag | S / Yes |
| storefront-builder/sections/<int:pk>/collapse/ | storefront-builder-section-collapse | POST | apps/storefront_builder/views.py:1579 storefront_section_collapse_toggle | direct view/model; validation helpers | section collapsed flag | S / Yes |
| storefront-builder/sections/<int:pk>/lock/ | storefront-builder-section-lock | POST | apps/storefront_builder/views.py:1593 storefront_section_lock_toggle | direct view/model; validation helpers | section locked flag | S / Yes |
| storefront-builder/sections/<int:pk>/duplicate/ | storefront-builder-section-duplicate | POST | apps/storefront_builder/views.py:1608 storefront_section_duplicate | container_service.add_block; container_service.get_cell_blocks; container_service.rebuild_page_from_legacy_rows | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/sections/<int:pk>/move/ | storefront-builder-section-move | POST | apps/storefront_builder/views.py:1818 storefront_section_move | container_service.rebuild_page_from_legacy_rows | Section/Container/Cell identities, placement and ordering | S / Yes |
| storefront-builder/appearance/ | storefront-builder-appearance | GET/POST | apps/storefront_builder/views.py:2248 storefront_appearance_editor | direct view/model; validation helpers | Version.appearance_config | F / Yes |
| storefront-builder/apply-preset/ | storefront-builder-apply-preset | POST | apps/storefront_builder/views.py:2008 storefront_apply_layout_preset | preset_service.apply_preset_with_checkpoint | Draft composition/config/provenance/baseline; checkpoint depending operation | T / Yes |
| storefront-builder/sections/<int:pk>/reset/ | storefront-builder-section-reset | POST | apps/storefront_builder/views.py:2060 storefront_section_reset | preset_service.reset_section_to_baseline | Section.settings (variant/background/card/content) | T / Yes |
| storefront-builder/sections/<int:pk>/reset-field/ | storefront-builder-section-field-reset | POST | apps/storefront_builder/views.py:2084 storefront_section_field_reset | preset_service.reset_section_setting_to_baseline | Section.settings (variant/background/card/content) | T / Yes |
| storefront-builder/appearance/reset-field/ | storefront-builder-appearance-field-reset | POST | apps/storefront_builder/views.py:2107 storefront_appearance_field_reset | preset_service.reset_appearance_setting_to_baseline | Version.appearance_config | T / Yes |
| storefront-builder/header/reset/ | storefront-builder-header-reset | POST | apps/storefront_builder/views.py:2128 storefront_header_reset | preset_service.reset_header_to_baseline | Version.header_config | T / Yes |
| storefront-builder/footer/reset/ | storefront-builder-footer-reset | POST | apps/storefront_builder/views.py:2148 storefront_footer_reset | preset_service.reset_footer_to_baseline | Version.footer_config incl mobile_nav_variant | T / Yes |
| storefront-builder/page/reset/ | storefront-builder-page-reset | POST | apps/storefront_builder/views.py:2166 storefront_page_reset | preset_service.reset_page_with_checkpoint | Draft composition/config/provenance/baseline; checkpoint depending operation | T / Yes |
| storefront-builder/reset-to-baseline/ | storefront-builder-reset-to-baseline | POST | apps/storefront_builder/views.py:2188 storefront_reset_to_baseline | preset_service.reset_storefront_with_checkpoint | Draft composition/config/provenance/baseline; checkpoint depending operation | T / Yes |
| storefront-builder/header/ | storefront-builder-header | GET/POST | apps/storefront_builder/views.py:2497 storefront_header_editor | direct view/model; validation helpers | Version.header_config | F / Yes |
| storefront-builder/footer/ | storefront-builder-footer | GET/POST | apps/storefront_builder/views.py:2537 storefront_footer_editor | direct view/model; validation helpers | Version.footer_config incl mobile_nav_variant | F / Yes |
| storefront-builder/undo/ | storefront-builder-undo | POST | apps/storefront_builder/views.py:1879 storefront_undo | edit_history_service.undo | snapshot-restored Draft JSON/sections/media/containers | U / cursor only |
| storefront-builder/redo/ | storefront-builder-redo | POST | apps/storefront_builder/views.py:1891 storefront_redo | edit_history_service.redo | snapshot-restored Draft JSON/sections/media/containers | U / cursor only |
| storefront-builder/publish/ | storefront-builder-publish | POST | apps/storefront_builder/views.py:1903 storefront_publish | layout_service.publish | version statuses; published/draft pointers; history cleared | L / No |
| storefront-builder/discard/ | storefront-builder-discard | POST | apps/storefront_builder/views.py:2238 storefront_discard | layout_service.discard_draft | active Draft/version/pointer lifecycle | L / No |
| storefront-builder/apply-industry-layout/ | storefront-builder-apply-industry-layout | POST | apps/storefront_builder/views.py:2209 storefront_apply_industry_layout | layout_service.apply_industry_layout | Draft composition/config/provenance/baseline; checkpoint depending operation | T / No |
| storefront-builder/history/<int:pk>/restore/ | storefront-builder-restore | POST | apps/storefront_builder/views.py:2596 storefront_restore | layout_service.restore_version | active Draft/version/pointer lifecycle | L / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/add/ | storefront-builder-section-media-add | GET/POST | apps/storefront_builder/media_views.py:165 storefront_section_media_form | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/<int:item_pk>/edit/ | storefront-builder-section-media-edit | GET/POST | apps/storefront_builder/media_views.py:165 storefront_section_media_form | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/<int:item_pk>/delete/ | storefront-builder-section-media-delete | POST | apps/storefront_builder/media_views.py:242 storefront_section_media_delete | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/<int:item_pk>/toggle/ | storefront-builder-section-media-toggle | POST | apps/storefront_builder/media_views.py:304 storefront_section_media_toggle | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/<int:item_pk>/move/ | storefront-builder-section-media-move | POST | apps/storefront_builder/media_views.py:316 storefront_section_media_move | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |
| storefront-builder/sections/<int:pk>/media/<str:kind>/reorder/ | storefront-builder-section-media-reorder | POST | apps/storefront_builder/media_views.py:338 storefront_section_media_reorder | direct view/model; validation helpers | HeroSlide/Banner/Story placement + asset/file state | M / No |

## R4 command-level census (11 commands; 1 mutate endpoint)

All use profile R and `r4_mutation_service._dispatch_mutation:519–558`. The settings API can edit schema-enabled non-Home sections, but the shipped R4 shell and structure commands are Home-only. The component/manifest/template commands are callable APIs; the inspected R4 Global Design UI exposes only six appearance fields and header/footer selectors (`r4_views.py:151–184`; `r4/editor.html:82–148`). Do not count backend APIs as shipped merchant panels.

| Command | Helper line | Target / preservation | Synchronization / limitation |
|---|---:|---|---|
| section.update_settings | 132 | declared schema patch merged with current settings; section identity preserved | only 4 schemas; source ownership checked when patched; no section-lock guard here |
| section.add | 189 | Home section + new container/cell; siblings preserved | trusted library allowlist/instance limits |
| section.remove | 199 | Home section/placement deletion | structure lock/removable checks; no global sync required |
| section.duplicate | 209 | Home duplicate; original retained | duplicable constraints; clone behavior delegated |
| section.move | 219 | Home placement/order | container operation; does not rebuild all legacy rows |
| appearance.update | 431 | six patch keys: template_slug,palette_slug,font,type_scale,motion,button_style; retains other JSON | template profile copies seven fields; palette clears colors/theme overrides; motion/template sync four legacy families |
| header.update | 479 | header_variant patch; other header fields preserved | synchronizes manifest from live selectors |
| footer.update | 499 | footer_variant patch; other footer fields preserved | synchronizes manifest from live selectors; bottom-nav has no direct patch field |
| appearance.component.update | 341 | one selected family; requires pinned Draft ID | persists manifest + mirrors; may reconcile live legacy siblings |
| appearance.manifest.apply | 366 | whole validated manifest; requires pinned Draft ID | mirrors header/footer/nav/motion; typed family settings all empty |
| appearance.template.apply | 393 | replaces recipe page composition and token/header/footer overlays; requires exact latest recipe version and pinned Draft | **A02: only four mirrored families synchronized; declared full recipe manifest never applied** |

History endpoint accepts undo/redo (`apply_history_command:615`); publish calls `publish_draft:655`. They are separate two endpoints, not mutation commands.

## Additional Builder GET initialization entry points (10)

These are additional URL patterns not counted among45. Appearance/header/footer form GET initialization is already counted in the explicit table and is not counted twice. `get_or_create_layout → StorefrontLayout.provision_for`; `get_or_create_draft:722` may clone/bootstrap and ensure containers.

| URL | Name | View | Initialization target | Profile |
|---|---|---|---|---|
| storefront-builder/ | storefront-builder-editor | apps/storefront_builder/views.py:100 storefront_editor | layout/Draft/pages; compatibility containers | G |
| storefront-builder/r4/ | storefront-builder-r4-editor | apps/storefront_builder/r4_views.py:189 storefront_r4_editor | layout/Draft/pages; compatibility containers | G |
| storefront-builder/r4/sections/<int:pk>/inspector/ | storefront-builder-r4-section-inspector | apps/storefront_builder/r4_views.py:306 storefront_r4_section_inspector | layout provisioning only | G |
| storefront-builder/r4/resources/picker/ | storefront-builder-r4-resource-picker | apps/storefront_builder/r4_views.py:413 storefront_r4_resource_picker | layout provisioning only | G |
| storefront-builder/templates/ | storefront-builder-templates | apps/storefront_builder/views.py:1927 storefront_template_gallery | layout/Draft/pages; compatibility containers | G |
| storefront-builder/preview/ | storefront-builder-preview | apps/storefront_builder/views.py:217 storefront_preview | layout/Draft/pages; compatibility containers | G |
| storefront-builder/sections/ | storefront-builder-section-list | apps/storefront_builder/views.py:294 storefront_section_list_partial | layout/Draft/pages; compatibility containers | G |
| storefront-builder/containers/ | storefront-builder-container-state | apps/storefront_builder/views.py:338 storefront_container_state_partial | layout/Draft/pages; compatibility containers | G |
| storefront-builder/edit-history/state/ | storefront-builder-edit-history-state | apps/storefront_builder/views.py:1870 storefront_edit_history_state | layout/Draft/pages; compatibility containers | G |
| storefront-builder/history/ | storefront-builder-history | apps/storefront_builder/views.py:2584 storefront_history | layout provisioning only | G |

The two remaining Builder URLs, section product-search and section media-list, perform scoped reads without a Builder creation call. Thus **57 total Builder route patterns =45 explicit writes +10 initialization routes +2 read routes**. This catches initialization routes a POST-only census would miss.

## Direct live storefront content/identity endpoints (31)

Profile V or C supplies authorization, tenant, lifecycle, history, synchronization and preservation rules. Add/edit share form functions but are separate URL patterns. All listed mutations occur on POST; delete forms without require_POST explicitly branch on request.method. Model form validation is not an edit revision.

| URL | Name | Method | View / line | Changed state | Profile |
|---|---|---|---|---|---|
| settings/shop-info/ | settings-shop-info | POST | apps/dashboard/views.py:4302 settings_shop_info | ShopSettings name/tagline/contact/description; direct model save/delete | V |
| settings/appearance/ | settings-appearance | POST | apps/dashboard/views.py:4385 settings_appearance | ShopSettings identity/colors/logo/favicon; direct model save/delete | V |
| homepage/hero/add/ | hero-add | GET/POST | apps/dashboard/views.py:4826 hero_form | HeroSlide fields/legacy files; direct model save/delete | C |
| homepage/hero/<int:pk>/edit/ | hero-edit | GET/POST | apps/dashboard/views.py:4826 hero_form | HeroSlide fields/legacy files; direct model save/delete | C |
| homepage/hero/<int:pk>/delete/ | hero-delete | POST | apps/dashboard/views.py:4901 hero_delete | HeroSlide fields/legacy files; direct model save/delete | C |
| homepage/hero/<int:pk>/toggle/ | hero-toggle | POST | apps/dashboard/views.py:4927 hero_toggle | HeroSlide fields/legacy files; direct model save/delete | C |
| homepage/banners/add/ | banner-add | GET/POST | apps/dashboard/views.py:4950 banner_form | PromotionalBanner fields/legacy files; direct model save/delete | C |
| homepage/banners/<int:pk>/edit/ | banner-edit | GET/POST | apps/dashboard/views.py:4950 banner_form | PromotionalBanner fields/legacy files; direct model save/delete | C |
| homepage/banners/<int:pk>/delete/ | banner-delete | POST | apps/dashboard/views.py:5023 banner_delete | PromotionalBanner fields/legacy files; direct model save/delete | C |
| homepage/banners/<int:pk>/toggle/ | banner-toggle | POST | apps/dashboard/views.py:5049 banner_toggle | PromotionalBanner fields/legacy files; direct model save/delete | C |
| social-links/add/ | social-link-add | GET/POST | apps/dashboard/views.py:5078 social_link_form | SocialLink; direct model save/delete | C |
| social-links/<int:pk>/edit/ | social-link-edit | GET/POST | apps/dashboard/views.py:5078 social_link_form | SocialLink; direct model save/delete | C |
| social-links/<int:pk>/delete/ | social-link-delete | GET/POST | apps/dashboard/views.py:5116 social_link_delete | SocialLink; direct model save/delete | C |
| social-links/<int:pk>/toggle/ | social-link-toggle | POST | apps/dashboard/views.py:5135 social_link_toggle | SocialLink; direct model save/delete | C |
| menus/add/ | menu-add | GET/POST | apps/dashboard/views.py:5164 menu_form | Menu; direct model save/delete | C |
| menus/<int:pk>/edit/ | menu-edit | GET/POST | apps/dashboard/views.py:5164 menu_form | Menu; direct model save/delete | C |
| menus/<int:pk>/delete/ | menu-delete | GET/POST | apps/dashboard/views.py:5210 menu_delete | Menu; direct model save/delete | C |
| menus/<int:pk>/toggle/ | menu-toggle | POST | apps/dashboard/views.py:5237 menu_toggle | Menu; direct model save/delete | C |
| menus/<int:menu_id>/items/add/ | menu-item-add | GET/POST | apps/dashboard/views.py:5276 menu_item_form | MenuItem destination/order/active; direct model save/delete | C |
| menu-items/<int:pk>/edit/ | menu-item-edit | GET/POST | apps/dashboard/views.py:5276 menu_item_form | MenuItem destination/order/active; direct model save/delete | C |
| menu-items/<int:pk>/delete/ | menu-item-delete | GET/POST | apps/dashboard/views.py:5339 menu_item_delete | MenuItem destination/order/active; direct model save/delete | C |
| menu-items/<int:pk>/toggle/ | menu-item-toggle | POST | apps/dashboard/views.py:5361 menu_item_toggle | MenuItem destination/order/active; direct model save/delete | C |
| footer/settings/ | footer-settings | GET/POST | apps/dashboard/views.py:5390 footer_settings_page | FooterSettings fields; direct model save/delete | C |
| footer/trust-badges/add/ | footer-trust-badge-add | GET/POST | apps/dashboard/views.py:5460 footer_trust_badge_form | FooterTrustBadge/file; direct model save/delete | C |
| footer/trust-badges/<int:pk>/edit/ | footer-trust-badge-edit | GET/POST | apps/dashboard/views.py:5460 footer_trust_badge_form | FooterTrustBadge/file; direct model save/delete | C |
| footer/trust-badges/<int:pk>/delete/ | footer-trust-badge-delete | GET/POST | apps/dashboard/views.py:5509 footer_trust_badge_delete | FooterTrustBadge/file; direct model save/delete | C |
| footer/trust-badges/<int:pk>/toggle/ | footer-trust-badge-toggle | POST | apps/dashboard/views.py:5538 footer_trust_badge_toggle | FooterTrustBadge/file; direct model save/delete | C |
| footer/payment-logos/add/ | footer-payment-logo-add | GET/POST | apps/dashboard/views.py:5560 footer_payment_logo_form | FooterPaymentLogo/file; direct model save/delete | C |
| footer/payment-logos/<int:pk>/edit/ | footer-payment-logo-edit | GET/POST | apps/dashboard/views.py:5560 footer_payment_logo_form | FooterPaymentLogo/file; direct model save/delete | C |
| footer/payment-logos/<int:pk>/delete/ | footer-payment-logo-delete | GET/POST | apps/dashboard/views.py:5608 footer_payment_logo_delete | FooterPaymentLogo/file; direct model save/delete | C |
| footer/payment-logos/<int:pk>/toggle/ | footer-payment-logo-toggle | POST | apps/dashboard/views.py:5637 footer_payment_logo_toggle | FooterPaymentLogo/file; direct model save/delete | C |

**FACT — additional closure finding, A03:** `dashboard.views.hero_form:4831` and Banner equivalent scope by pk+store, with no section/status predicate; delete/toggle paths likewise scope by store. They can address a placement attached to a Published/archived section of that store, unlike Builder media routes. **INFERENCE:** knowing such an ID permits modification of version-associated placement data without Builder publish/revision; this is a same-store lifecycle bypass, not a demonstrated cross-tenant leak. The list UI indicating visual Builder mode is not a write guard. This strengthens original P1 R2/R4 and must be included in retirement evidence. No request was sent.

**FACT — media-kind exception:** The add/edit URL patterns remain counted because they successfully serve Hero/Banner kinds. For story-items, the generic form assumes desktop_image/mobile_image although StoryRailItem has image; its add/edit path is incompatible (media_views.py:165–200). Existing Story list/delete/toggle/move/reorder are separate supported paths. A registered kind is not proof of working upload UI.

## Non-HTTP writer and tooling boundary

Do not add these to86. These are the source entry points capable of writing the same appearance concepts outside the HTTP edit protocol; caller authority is operational/process permission, not merchant decorators.

| Path/symbol | Caller / classification | Writes and target | Revision/history/mirror behavior |
|---|---|---|---|
| layout_service.get_or_create_draft:722; _clone_version_content:636; publish:773; restore_version:826; checkpoint:925; apply_industry_layout:969 | endpoints above, seed/capture commands; CANONICAL lifecycle + MIGRATION initialization | layout/version pointers, cloned configs/pages/sections/media/container identities | direct service callers need external revision protocol; copies intentionally retain historical state |
| bootstrap_service.apply_bootstrap_content:156; apply_industry_content:198 | first Draft / industry replacement; MIGRATION | initial section composition and seeded appearance | no stale-client protocol; not a competing immutable snapshot |
| preset_service apply/reset functions:275,487,558,659,742–900 | legacy/R4/tool callers; CANONICAL recipe primitives | Draft replacement or granular baseline replay | transaction/validation is not universal revision check; A02 applies |
| edit_history_service.restore_draft_state:159, undo/redo:303–349 | old/R4 history; COMPATIBILITY | current Draft dictionaries/sections/placements/containers | restores snapshots, no automatic mirror reconciliation; R4 wrapper adds revision |
| storefront_appearance.persistence.persist_store_appearance_manifest:106 | R4 commands; golden reference service; CANONICAL typed persistence | Draft manifest and four mirrors | rejects Published; alone does not lock active Draft or validate base_revision |
| golden_reference_service.apply_golden_reference_storefront:435; overlay:246–271 | stores/management/commands/apply_golden_reference_storefront.py:91; TOOLING | apply baseline, explicit manifest/custom overlay/Home composition, publish | operator-selected store; operational atomicity; no editor revision |
| storefront_builder/management/commands/capture_ready_template_previews.py:246–247 | management command; TOOLING | applies recipes and publishes selected capture store; screenshot files | **not a read-only screenshot command**; not run |
| storefront_builder/management/commands/qa_storefront_builder.py:252; qa_storefront_builder_r4.py:307–317 | management commands; TOOLING | creates Draft; R4 QA can clear published pointer | test/demo operational assumptions; not run |
| stores/management/commands/seed_rastisi_fashion_demo.py:1279–1281; seed_ready_template_fashion_demo.py:422–423 | demo seed commands; TOOLING | Draft/preset/publish, business fixtures | no universal revision wrapper; not run |
| stores/management/commands/seed_kianstock_qa_demo.py:577–638 | demo seed command; TOOLING | direct appearance/header/footer and page setup, publish | direct dictionary writes; not run |
| StorefrontLayout.provision_for; ShopSettings.provision_for; FooterSettings.provision_for | store creation / service initialization; MIGRATION | per-store singleton/layout defaults | initial creation distinct from deliberate editing; deployment provisioning callers are operational |

**FACT:** Legacy /admin-panel/ compatibility routes redirect to the dashboard (`shop_core/urls.py:43–44`); they are not extra independent writer controllers. No CLI or HTTP mutation was executed.

## Concept-level source of truth

Writer codes: **R**=R4 command service; **F**=legacy dictionary forms; **S**=legacy structure/containers; **T**=preset/reset/industry; **U**=old/R4 snapshot replay or version restore; **M**=Builder media; **V/C**=live endpoints; **B**=bootstrap/clone; **O**=operational tooling. Readers refer to all appearance consumers at the architecture boundary; domain internals remain domain-owned. Immutable snapshot storage is not counted as a competing live writer, but replay into the active Draft is a live write policy.

| Concept | Canonical storage now | Secondary/mirrored storage | All active writer groups | Readers/consumers | Current precedence | Duplication / danger | Recommended future owner |
|---|---|---|---|---|---|---|---|
| Token-template identity | Version.appearance_config.template_slug | defaults, profile catalog | R,F,U,B,O | core.context_processors; effective appearance; editor | stored slug; default modern; recipe does not set slug | profile vs Ready identity ambiguity | one appearance command owner |
| Ready recipe identity | layout_preset_key + template_provenance | baseline snapshot + slot keys | R,T,F (omission reset),U,O | reset/provenance/gallery | persisted provenance and stored baseline; not necessarily effective selected manifest | A02 and identity drift | versioned recipe application contract |
| Palette | appearance_config.palette_slug | baseline/default palette | R,F,T,U,B,O | appearance_registry resolve_colors/roles; context processor | palette plus overrides | multiple apply/reset policies | appearance command owner |
| Colors | appearance_config overrides/theme_overrides | ShopSettings live colors, baseline | R (palette reset),F,T,U,V,B,O | context processors; base token injection; CSS roles | version colors when visual version; live fallback; role override layering | intentional fallback + competing old editor | appearance owner; preserve live identity separately |
| Typography | appearance_config font/type_scale | section appearance_overrides; profile defaults | R,F,T,U,B,O | section_appearance_service; context; wrapper | enabled supported local typography beats global | no general scope hierarchy | one scope-aware appearance resolver/writer |
| Header | manifest selection + header_config content/toggles | header_variant mirror | R,F,T,U,B,O; C/V live content | global_renderer_template; global partials; context processors | nondefault manifest beats legacy selector; safe default delegates | saved-but-not-visible selector | one selection writer; explicit live content |
| Footer | manifest + footer_config | footer_variant, FooterSettings live gates | R,F,T,U,B,O,C | global partials; footer context | manifest renderer; both live/version visibility gates | two merchant visibility concepts | selection owner + documented domain gates |
| Bottom nav | manifest.bottom_nav | footer_config.mobile_nav_variant; NAV_MOBILE live menu | R,F,T,U,B,O,C | mobile global renderer; live menu/cart badge | manifest nondefault, else legacy | API/UI/mirror mismatch | global nav selection writer |
| Component selection | appearance_config.store_appearance | old selectors, recipe manifest | R,F (erase),T (retain/replay),U,B,O | resolve_store_appearance_render_state and R4 data projection | persisted manifest else legacy-derived defaults | A01/A02; API capability exceeds UI | typed selection boundary |
| Section variant | Section.settings selector | manifest.hero/product_view, recipe aliases | R,F,T,U,B,O | render_service + variant_contract | nondefault global manifest overlays local at render | local save can be masked | decision D02, one effective resolver |
| Card style | Section.settings.card; manifest.card | global card tokens | R,F,T,U,B,O | card_settings_for; card template/DTO; product-grid | manifest overlays section card for card-aware sections; HX omits section settings | scope and response mismatch | shared card appearance projection |
| Badge style | Section.settings.card; manifest.badge | domain sale/eligibility data | R,F,T,U,B,O | badge_settings_for; ProductCardData / special offer | manifest treatment plus domain truth; special panel separate | do not overwrite commerce badge truth | appearance treatment owner; domain eligibility preserved |
| Motion | appearance_config.motion | manifest.motion; section.motion; carousel options | R,F,T,U,B,O | base attributes/wrapper/CSS/inline JS | concept-specific tokens and timers; no one autoplay winner | no shared behavior contract | distinguish decorative motion from playback |
| Section appearance | Section.settings wrappers/typography/card | global tokens, container settings | R,F,T,U,B,O | responsive wrapper + inner templates/CSS | local typography narrow; global variant/card may win | schema gaps; replacement omits keys | common appearance contract under R |
| Section content | Section.settings + domain references | source adapter projection, placement rows | R,F,T,U,B,O; M/C for placements | render context builders/domain services | active saved settings and live domain data | template replacement vs content preservation | schema content command + domain references |
| Layout/container geometry | Container/Cell + Section.cell/cell_order | row_key,row_span,legacy cell.section,flat order; manifest layout reference | R,S,T,U,B,O | build_container_render_items; row fallback | blocks first; stored containers win; manifest no rebuild | destructive legacy reconstruction | one container composition writer, compatibility projection |
| Media | MediaAsset + placement FKs; domain image fields | JSON background IDs; legacy files; snapshots/static paths | M,C,F (background),R/T/U/B/O (clone/replay/delete relationships) | shared scoped loaders/URL properties/background resolver | asset URL then legacy file; scoped active then store fallback | reference graph incomplete; same-store lifecycle bypass | complete reachability/lifetime owner, separate domain media |
| Draft revision | Version.edit_revision | client base_revision | R only for monotonic editing; defaults initialize new versions | _lock_active_draft; JS conflict state | server integer | **one clear update owner**, but other writers fail to advance it | R as universal edit boundary |
| Published pointer | Layout.published_version + version.status | archived previous version | R publish wrapper,L direct publish,O tooling | page_resolution_service; universal context | visual flag + published pointer, never Draft fallback | one storage service, multiple caller concurrency policies | lifecycle service behind one command boundary |

Reference map: storage `models.py:142–316,518–940`; colors/roles `appearance_registry.py:156–225`; manifest `persistence.py:57–145`; rendering `rendering.py:67–190`, `render_service.py:714–845`; context `apps/core/context_processors.py:119–218`; media `apps/content/models.py:418`; writers in exhaustive tables above.

**Counting clarification:** “Multiple writer” counts distinct active authority/policy entry paths for a concept, including lossy erase and restoration to live state. It does not claim that19 different physical stores exist. Published has one low-level promotion service but multiple protected/unprotected entry policies; revision has one monotonic owner despite two functions in that same R4 boundary. Initialization values are not competing revision incrementers.

## Paths that violate one canonical writer policy

**FACT:** F/S/T/U/L/M are callable outside R4 revision checks; V's color writes compete with version appearance; C's Hero/Banner paths can mutate version-associated placements; O bypasses the editor protocol by operational design. R itself exposes both selector-specific and full-manifest commands but funnels them into shared typed persistence. Those commands are not duplicate engines; their synchronization needs explicit policy.

**RECOMMENDATION:** Converge the active editing boundary, not the business domains. Preserve pricing, cart calculations, product visibility, store membership, navigation ownership and immutable recovery records. Do not count snapshots as live competitors or delete compatibility callers without Report06's evidence.

**UNKNOWN:** deployed endpoint usage, overlapping editor sessions, affected existing manifests, legacy placement IDs/files, and stores dependent on fallback. Source establishes capability/reachability, not production incidence.
