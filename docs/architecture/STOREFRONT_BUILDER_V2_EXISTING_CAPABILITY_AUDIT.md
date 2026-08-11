# Storefront Builder V2 — Existing Capability Audit

**Phase:** Audit / Reconnaissance checkpoint (per `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md`) — documentation only, no application behavior changed.

> **Pointer note (added during the subsequent architecture-revision pass):** the factual findings in this document are unchanged and not re-litigated here. The owner has since locked nine architecture decisions that determine *what to do* with several findings below — most notably §2 (section-bound media clone bug: the fix direction described there as a possibility is superseded; see `STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` §5.2–5.3 for the rejected vs. approved fix) and §4 (Family system: "pending owner decision" language elsewhere in the docs is now resolved to a locked freeze — see `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md`). Read this document for **what exists and how it behaves today**; read the Implementation Plan for **what the owner has decided to do about it**. This document also originally used the term "TESTED" to mean "test assertions read, not executed" — later documents use the clearer term `SOURCE_WITH_TEST_COVERAGE` for this same meaning; this document's own wording is left as originally written for historical accuracy.

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit:** `152a6e440383dd5a0bdca1847a5eee0cb92ca9a0`
**Date:** 2026-08-11

> **Evidence-level legend (Step 17 of the task, mandatory on every capability):**
> - `SOURCE_ONLY` — confirmed by reading source/migrations/templates. Not executed.
> - `TESTED` — a repository test exists and its assertions were read and appear to cover the claim, but the test suite **could not be executed in this sandbox** (see §0). Treat as "author-verified in their own environment," not "verified by this audit."
> - `RUNTIME_VERIFIED` — executed against a real Django runtime/shell in this session. **None of the claims below reached this level** (see §0).
> - `BROWSER_VERIFIED` — observed in an actual browser. **None of the claims below reached this level.**
>
> No claim below is marked `RUNTIME_VERIFIED` or `BROWSER_VERIFIED`. This is stated explicitly per the audit's own requirement not to infer stronger evidence than what was actually collected.

---

## 0. Sandbox constraint (read this before trusting any "TESTED" label below)

This sandbox has no Django installed, `pip install` against PyPI fails (`network_mode=INTEGRATIONS_ONLY`, proxy returns `403 Forbidden` for `pypi.org`), and no cached Django wheel exists anywhere on disk (checked exhaustively). **No automated test in this repository could be executed this session.** Every "TESTED" label below means: *a test file exists, was opened, and its assertions were read and appear to target the claim* — not that the test was run and passed. This materially limits confidence versus a normal audit and is called out again in the final report (Step 24, Q12).

Prior audit documents already in the repo (`docs/reports/*.md`, `docs/template-references/live-audit/*.md`) are dated 2026-08-03 through 2026-08-08 and are **partially stale** — several of their "ABSENT" findings (store-scoping of `HeroSlide`/`PromotionalBanner`, absence of a real Collection model) are no longer true at current HEAD. This document supersedes them for the areas it covers; it does not re-litigate the still-current parts of `docs/template-references/live-audit/01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` and `08_TARGET_ARCHITECTURE_AND_FILE_PLAN.md` (both dated after the 11-family system existed), which are cited directly where relevant rather than duplicated.

---

## 1. Layout lifecycle (`apps/storefront_builder`)

### 1.1 Models (`apps/storefront_builder/models.py`)

| Model | Key fields | Evidence |
|---|---|---|
| `StorefrontLayout` | `store` (OneToOne, CASCADE), `published_version`/`draft_version` (FK → `StorefrontLayoutVersion`), `uses_visual_storefront_layout` (bool feature flag), `provision_for(store)` (idempotent) | SOURCE_ONLY |
| `StorefrontLayoutVersion` | `layout` FK, `version_number`, `status` (DRAFT/PUBLISHED/ARCHIVED), `source` (MANUAL/LEGACY_BOOTSTRAP/INDUSTRY_TEMPLATE/RESTORED), `header_config`/`footer_config`/`appearance_config` (JSONField, all three on the same row), `content_fingerprint` (SHA-256, `compute_fingerprint()`), `UniqueConstraint(layout, version_number)` | SOURCE_ONLY |
| `StorefrontSection` | `version` FK, `section_key` (allowlisted in Python registry, not a DB choices constraint), `order`, `is_active`, `collapsed_in_editor` (UI-only, independent of `is_active`), `settings` (JSONField) | SOURCE_ONLY |

`collapsed_in_editor` is present — this closes a gap flagged as `❌ ABSENT` in the 2026-08-06 report (`docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md` §3); that finding is now obsolete.

### 1.2 Section Registry (`apps/storefront_builder/section_registry.py`, 970 lines)

- **22 section types** registered (grew from 16 documented in the 2026-08-06 report): `announcement_bar`, `hero_banner`, `image_slider`, `single_banner`, `multi_banner`, `category_grid`, `product_section`, `featured_products`, `newest_products`, `best_sellers`, `discounted_products`, `amazing_offers`, `brand_carousel`, `promo_cards`, `rich_text`, `image_text`, `trust_features`, `collection_tiles`, `quick_links`, `faq`, `testimonials`, `video_section`. — SOURCE_ONLY (per-key confirmation via `docs/template-references/live-audit/01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` §2.1, cross-checked directly against `section_registry.py`).
- `product_section` has a genuine **Data Source contract**: `PRODUCT_SECTION_DATA_SOURCES = ("collection", "category", "brand", "manual", "newest", "discounted", "best_sellers", "most_viewed")`, with `item_limit` (2–24 clamp), `display_mode` (`carousel`/`grid`), and Store-scoped reference validation delegated to `services/section_data_service.py`. This is exactly the "Data Source" capability the older architecture-plan report proposed as future work — **it is built now**. — SOURCE_ONLY.
- Responsive per-section settings exist (`templates/storefront_builder/partials/section_responsive_fields.html`, `responsive_section_wrapper.html`) — also previously proposed-as-future, now built. — SOURCE_ONLY.
- `featured_products` still has no independent data source — `render_service.py` aliases it to the newest-products query because `Product.is_featured` does not exist (confirmed comment in `render_service.py`, and independently by catalog audit sub-agent). — SOURCE_ONLY, confirmed gap (unchanged from 2026-08-06 finding).
- `amazing_offers`' countdown deadline is still computed fresh on every render (`timezone.now() + timedelta(hours=8)`, hardcoded, not merchant-configured or persisted) — confirmed by `docs/template-references/live-audit/01_...GAPS.md` §3.1, independently consistent with the 2026-08-03/08-06 reports' findings on this exact mechanism. — SOURCE_ONLY, confirmed unresolved gap.

### 1.3 Draft / Preview / Publish / Rollback services (`apps/storefront_builder/services/layout_service.py`)

| Operation | Function | Behavior | Evidence |
|---|---|---|---|
| Get-or-create Draft | `get_or_create_draft(store, *, user=None)` | Idempotent (returns existing draft if present); if the Store has never had any version, calls `bootstrap_service.apply_bootstrap_content` (not a clone — reconstructs the legacy hardcoded homepage as equivalent sections); otherwise clones the **published** version's `header_config`/`footer_config`/`appearance_config` + creates brand-new `StorefrontSection` rows (new PKs) via `_clone_version_content` | SOURCE_ONLY |
| Publish | `publish(store, *, user=None)` | Atomic; rate-limited (20/hour via `apps.core.services.rate_limit.enforce_rate_limit`, a pre-existing shared utility, not new infra); swaps `published_version`/`draft_version` pointers only (no content copy at publish time); archives the prior published version; computes/stores `content_fingerprint`; **only place** `uses_visual_storefront_layout` is set `True` | SOURCE_ONLY |
| Discard | `discard_draft(store)` | Deletes the current draft version row entirely (CASCADE consequences — see §2) | SOURCE_ONLY |
| Restore | `restore_version(store, version_id, *, user=None)` | **Never publishes directly** — always creates a new Draft (`source=RESTORED`) via the same `_clone_version_content` clone path; cross-store version id fails closed (`CrossStoreVersionError`) | SOURCE_ONLY |
| Apply industry layout | `apply_industry_layout(store, industry_template, *, user=None, force=False)` | Creates a new Draft from `IndustryTemplate.default_section_keys`; refuses to silently overwrite an existing published layout without `force=True`/`confirm=1` (`StorefrontAlreadyPublishedError`) | SOURCE_ONLY |

All lifecycle mutations are wrapped in `transaction.atomic()`. Rate limiting reuses pre-existing shared infrastructure (`apps/core/services/rate_limit.py`), consistent with the platform's other rate-limited operations (SMS, portal handoffs) — no new rate-limiting mechanism would be required for V2.

### 1.4 Shared renderer (`apps/storefront_builder/services/render_service.py`)

- `build_render_items(version, store)` is the **single function** consumed by both the staff-only Draft preview (`storefront_preview` view) and the public `home()` view (published version) — this satisfies the spec's "Preview must render the actual Draft through the same universal storefront engine used by public rendering" requirement (§9 of the V2 spec), **already true for the homepage today**. — SOURCE_ONLY.
- Unknown/removed section keys are silently skipped (a removed section type never 500s the public page). Per-request per-section-key caching avoids duplicate queries for repeated section instances of the same type. — SOURCE_ONLY.
- **Gap closed since 2026-08-06**: the page *shell* (header/footer HTML) duplication between `preview.html` and `home_visual.html` — flagged as the #1 risk in the 2026-08-06 report — has been fixed. Both now `{% include %}` the same `storefront_builder/partials/page_shell_header.html` / `page_shell_footer.html` (confirmed present on disk, confirmed included by both templates by two independent sub-agent investigations, and referenced by `docs/template-references/live-audit/01_...GAPS.md` §2.1 citing commit `be8bb2a`). — SOURCE_ONLY.
- **Important scope caveat, load-bearing for the V2 design**: this shared shell is used only by the homepage (`home_visual.html`) and the Builder's own preview (`preview.html`). **No other public route includes it.** See §6 (Route/Renderer map document) for the full route-by-route trace — this is the concrete, evidence-based explanation for the "homepage and collection pages look like different storefronts" QA observation the owner already flagged.

### 1.5 Bootstrap / migration of existing stores (`apps/storefront_builder/services/bootstrap_service.py`)

- `build_bootstrap_sections(store)` converts a store's current hard-coded homepage (hero, discounted products, etc., only if that content actually exists) into equivalent Section rows on first-ever Draft creation. No data is deleted. `catalog.views.home()` continues to fall back to the legacy `catalog/home.html` template until a store has **both** `uses_visual_storefront_layout=True` **and** a `published_version` — i.e., a store that never touches the Builder is provably unaffected by its existence. — SOURCE_ONLY, consistent across three independent sources (2026-08-06 report, live-audit doc 01, and this session's own read of `layout_service.get_or_create_draft`).

### 1.6 Tests covering this subsystem

All in `apps/storefront_builder/tests/`, enumerated (not executed) this session: `test_models.py`, `test_layout_service.py`, `test_bootstrap_service.py`, `test_public_homepage_integration.py`, `test_render_service.py`, `test_section_registry.py`, `test_views.py` (~1235 lines, includes `SectionActionTests`, `PublishDiscardRestoreViewTests`, `HeaderFooterEditorTests`, `RenderedPreviewIntegrationTests`), `test_responsive_rendering.py`, `test_page_shell.py`, `test_template_syntax_integrity.py`, `test_section_data_service.py`, `test_media_views.py`, `test_shared_capabilities.py`, `test_preset_registry_import.py`, plus 6 family-specific test files. — **TESTED** (assertions read, not executed) for: idempotent draft creation, atomic publish, archiving prior version, rate limiting, unknown-section-type-doesn't-crash-public-page, cross-store rejection at model/service/view layers, real (independent, not toggle-only) duplication, atomic reorder with duplicate-id rejection, header/footer non-removable-element validation (cart link, home link, ≥1 active footer column), shared page-shell inclusion by both Preview and Public.

---

## 2. Section-bound media — HIGH PRIORITY FINDING (Step 6 of the task)

### 2.1 Current model shape

`HeroSlide`, `PromotionalBanner` (`apps/content/models.py`), and `StoryRailItem` (same file, newer) each carry **both**:
- a `store` FK (CASCADE; nullable on the two older models for legacy pre-scoping rows, non-nullable on `StoryRailItem` since it was added after the store-scoping convention matured), **and**
- a `section` FK → `storefront_builder.StorefrontSection` (CASCADE, nullable — `section=None` means "legacy store-global slide/banner," a populated value means "owned by one specific Section *instance*").

This is a real Django foreign key, not an ID list embedded in `StorefrontSection.settings` JSON. — SOURCE_ONLY, confirmed via direct model-field citation and via `render_service.py`'s `_scoped_hero_slides`/`_scoped_banners`/`_story_rail_context` functions, which filter `HeroSlide.objects.filter(section=section, is_active=True)` and fall back to `HeroSlide.objects.filter(store=store, section__isnull=True, ...)` when the scoped queryset is empty.

**This contradicts the 2026-08-03 audit's finding** ("`HeroSlide`/`PromotionalBanner`... have no `store` field... platform-global") — that finding was accurate on 2026-08-03 but is stale; store-scoping was retrofitted (`apps/content/migrations` checkpoint commit, confirmed via `git log --oneline -- apps/content/migrations`), and section-scoping was added even later (`apps/content/migrations/0017_scope_hero_slides_and_banners_to_section.py`, `0018_storyrailitem.py`).

### 2.2 The clone algorithm — traced exactly

`layout_service._clone_version_content(source, target)` is the single function used by `get_or_create_draft` (new Draft after Publish), `restore_version`, and `apply_industry_layout`. It:

1. Copies `header_config`/`footer_config`/`appearance_config` dicts onto `target`.
2. Builds a list of **brand-new** `StorefrontSection(version=target, section_key=..., order=..., is_active=..., settings=dict(...))` objects and `bulk_create()`s them.

**It never references `HeroSlide`, `PromotionalBanner`, or `StoryRailItem` at all** (confirmed by exhaustive grep of `layout_service.py` for all three model names — zero matches).

### 2.3 Exact failure mode

Because the new Draft's sections get **new primary keys**, and media→section is a real FK pointing at the **old** section's PK:

- The old section row still physically exists (it belongs to `source`, the version being archived, not deleted) — so this is **not** a DB integrity error, not a `DoesNotExist`, no crash.
- But it is **semantically orphaned**: the new Draft's equivalent section (same `section_key`, same `order`, different PK) has zero `HeroSlide`/`PromotionalBanner`/`StoryRailItem` rows pointing at it.
- `render_service`'s scoped lookups then silently fall back to the **store-global** (`section__isnull=True`) queryset. Effect for a merchant who used the Builder to add section-scoped slides/banners: **the media becomes invisible** on the next draft/eventual next-published version, reverting to whatever legacy global media exists (or nothing). The rows are not deleted — they become unreachable dead rows, accumulating with every publish→re-draft cycle (no cleanup/purge job exists for ARCHIVED versions; confirmed absent by grep for `prune`/`cleanup`/`purge` across `apps/storefront_builder/**`).
- **A second, more severe variant is actual permanent data loss.** `discard_draft`, `restore_version`, and `apply_industry_layout` all call `old_draft.delete()` when replacing an existing draft. `StorefrontSection.version` is `on_delete=CASCADE`, and `HeroSlide.section`/`PromotionalBanner.section`/`StoryRailItem.section` are also `on_delete=CASCADE`. So: merchant adds section-scoped media to the **current, unpublished** draft → discards that draft (or triggers restore/apply-industry-layout, which delete the stale draft the same way) → the CASCADE chain `StorefrontLayoutVersion.delete() → StorefrontSection (CASCADE) → HeroSlide/PromotionalBanner/StoryRailItem (CASCADE)` **permanently deletes those media rows**, and the underlying uploaded image files are never cleaned up (no `transaction.on_commit` storage-cleanup hook on this path, unlike `media_views.py`'s manual single-item delete path, which does clean up storage files).

### 2.4 Test coverage — confirmed absent

No existing test creates section-scoped media, publishes, then calls `get_or_create_draft`/`restore_version`/`apply_industry_layout` again to check whether the media survives. Specifically checked and confirmed **not** to cover this:
- `test_layout_service.py::GetOrCreateDraftTests::test_new_draft_clones_published_content` — only asserts on `StorefrontSection` fields, never touches `HeroSlide`/`PromotionalBanner`/`StoryRailItem`.
- `test_layout_service.py::test_restore_clones_source_sections` — same limitation.
- `test_media_views.py` (`HeroSlideCrudTests`, `BannerCrudTests`, `MediaCrossStoreIsolationTests`) — creates media directly against a draft section, never calls `publish()` followed by a subsequent draft/restore cycle.
- `test_render_service.py` (`ScopedHeroSlidesTests`, `ScopedBannersTests`) — proves the fallback-to-global behavior works when a section has *no* scoped media, but never publishes-and-reclones to check whether scoped media survives the *next* draft.

**Evidence level: SOURCE_ONLY.** This is a real, source-traceable bug with an exact, reproducible mechanism, but it has **not** been executed against a live Django runtime this session (see §0) — it cannot be labeled `RUNTIME_VERIFIED`. It is reported here per the spec's explicit instruction to document (not silently patch) this exact failure mode.

---

## 3. Route / renderer consistency (full detail in the companion `STOREFRONT_BUILDER_V2_ROUTE_RENDERER_MAP.md`)

Headline finding: **only the Builder-published homepage (`home_visual.html`) and the staff Draft preview (`preview.html`) include the shared, Family-aware `page_shell_header.html`/`page_shell_footer.html` partials.** Every other public route — Product Detail, Product Listing/Search/Category-filter, Collection Index/Detail, Cart, Wishlist, Content pages, and the **legacy** (unpublished) homepage — extends `templates/base.html` directly with **zero** `{% block header %}`/`{% block footer %}` override, rendering `base.html`'s own hardcoded generic header/footer DOM regardless of the merchant's selected Family. — SOURCE_ONLY, confirmed independently by two separate investigation passes (this session's route-map sub-agent, and the pre-existing `docs/template-references/live-audit/01_...GAPS.md` §2.2, which states the same thing in different words: "Exactly one header partial platform-wide... no per-template product-page composition today").

This is the concrete, source-level explanation for the owner's browser-QA observation that "the homepage and collection/listing pages can visually behave like different storefronts": the homepage (once published via the Builder) gets a genuinely Family-forked header/hero/category/footer; every other route gets the same one generic shell regardless of Family, with only the product **card** partial and the Product Detail page **body** (not its header/footer) being Family-aware.

---

## 4. Current Family system (11 families)

`apps/storefront_builder/family_registry.py` registers **11 families**: `modern_fashion`, `artisan_editorial`, `nordic_living`, `heritage_premium`, `vibrant_catalog`, `atlas_catalog`, `ava_fashion`, `toranj_gifting`, `sarv_stock`, `sepidar_handmade`, `zarrin_jewelry` — matching the spec's expected list exactly. — SOURCE_ONLY.

Each `FamilyDefinition` controls, via literal template-path strings (not an abstract key resolved elsewhere): `header_variant`, `hero_variant`, `category_variant`, `footer_variant`, `product_card_variant`, `product_page_variant`, `default_preset_slug`, `default_section_keys` (the homepage section list auto-applied on family selection), and (only for `heritage_premium`) `product_card_campaign_variant`.

**Selection mechanism:** there is no `family_slug` field on `Store`/`ShopSettings`. It lives inside `StorefrontLayoutVersion.appearance_config` (the same JSONField that already carries `template_slug`/`palette_slug`), edited via the `storefront_appearance_editor` view. Family and the older 10-Template system (`appearance_registry.py`) are **mutually exclusive** — selecting one resets the other. Switching family replaces the Draft's homepage sections (`bootstrap_service.apply_family_default_sections`), gated behind an explicit `confirm_family_switch=1` if the Draft already has sections.

**Dispatch mechanism:** a global template-context variable `SHOP_FAMILY` (injected by `apps.core.context_processors.shop_settings`), consumed via `{% include SHOP_FAMILY.header_variant %}`-style Django template includes — a pure template-level Strategy pattern, not a Python `if/elif` dispatch in any view.

**Per-surface reach (confirmed by direct template trace):**

| Surface | Family-aware? |
|---|---|
| Home page (once Builder-published) | ✅ header/hero/category/footer |
| Home page (legacy/unpublished) | ❌ |
| Product Detail body | ✅ (`product_detail.html` `{% block content %}`) |
| Product Detail header/footer | ❌ (plain `base.html`) |
| Product card (anywhere it's included: home, listing, collection, related-products) | ✅ |
| Product Listing/Search page shell | ❌ (cards only) |
| Collection page shell | ❌ (cards only) |
| Cart | ❌ (not even the card partial is used) |

`preset_registry.py` supplies 11 per-family token bundles (font/radius/density/motion/type_scale/card_shadow/hero_style + a default palette), explicitly scoped to one family each (`family_slug` field on `PresetDefinition`) — this is a *token* layer sitting inside a chosen Family, distinct from `appearance_registry.py`'s older, DOM-agnostic 10-`TemplateDefinition`/20-`PaletteDefinition` system.

`ShopSettings` (`apps/core/models.py`) still has **no** font/radius/spacing/density field — those now live entirely in `StorefrontLayoutVersion.appearance_config`, resolved via `apps/core/context_processors.py`. This remains true at current HEAD (re-confirmed, not just carried over from older reports).

Prior art directly relevant here: `docs/template-references/live-audit/01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` §2.2–2.3 and `08_TARGET_ARCHITECTURE_AND_FILE_PLAN.md` already document this exact family/template/preset architecture in more implementation-level detail (for a different, still-open initiative to add further families) and flag the "one shared DOM + CSS tokens" vs. "DOM-forked-per-family" tension as an **explicit, still-unresolved owner question** in that other initiative. This V2 audit does not resolve that open question either — it is directly relevant to V2's "one universal engine, not N coded families" goal and is called out again in the Implementation Plan document.

---

## 5. Builder merchant UI

~20 routes registered in `apps/dashboard/urls.py`, implemented in `apps/storefront_builder/views.py` + `media_views.py`. Full route table, behavior-by-route, and reusability classification is in the companion `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md`. Headline facts:

- **Real duplication** (deep-copied settings, independently editable afterward — not a toggle), **real atomic reorder** (drag-and-drop + explicit up/down fallback buttons for mobile/keyboard), **separate concerns** for `is_active` (storefront visibility) vs. `collapsed_in_editor` (editor-only UI state).
- **Autosave** for structural operations (add/remove/reorder/toggle/duplicate/move/collapse) — saved immediately, no explicit save step. **Explicit save** for settings-forms/header/footer/appearance (form POST).
- **No undo/redo.** Only coarse-grained recovery: Discard Draft (destroys the whole draft) and Version History + Restore (creates a new Draft from an old *published* snapshot).
- **No scheduled publish.** Publish is synchronous/immediate only.
- **Preview is staff-session-only, not a shareable link/token.** Explicitly documented in the view's own comments as an intentional owner decision ("هرگز برای بازدیدکننده عمومی در دسترس نیست").
- **Device preview toggle** (desktop/tablet/mobile) exists in the editor UI itself (`editor.html`, `.sfb-device-toggle`), independent of a separate "mobile edit mode" switch for the admin's own layout.

---

## 6. Design system / appearance

- `ShopSettings` (7 hex colors + logo/favicon) is the color fallback for stores that have never published a Builder layout; once a layout is published, `apps/core/context_processors.py`'s `_global_identity_version()` reads colors/fonts/etc. from the published `StorefrontLayoutVersion.appearance_config` instead, and applies them **globally** (every route, not just the Builder-aware homepage) — this is the one appearance mechanism that is already universal across all routes, unlike the DOM/structural Family split in §4.
- `apps/core/theme_presets.py` is a small, older, unrelated 6-entry color-only preset list (`THEME_PRESETS`), used only to detect whether `ShopSettings`'s current 4 colors match a known preset — has no font/radius/spacing field and is not wired to `family_registry.py`/`preset_registry.py` despite the similar name. This is a naming collision risk for V2 documentation, not a functional overlap.

---

## 7. Content / navigation

- `Menu`/`MenuItem`/`FooterSettings`/`SocialLink`/`ContentPage`/`HeroSlide`/`PromotionalBanner`/`StoryRailItem` are **all store-scoped today** (direct `store` FK, or transitively via `menu.store` for `MenuItem`). The 2026-08-03 audit's claim that these are "platform-global" is stale and superseded by a dedicated store-scoping migration checkpoint (confirmed via `git log --oneline -- apps/content/migrations`).
- `MenuItem` supports internal destinations to `Category`/`Product`/`Brand`/`MerchantCollection` (added in migration `0016_add_collection_destination.py`) plus `external` URLs, via a shared `DestinationMixin`. URL safety is enforced by `validate_external_url()` (rejects `javascript:`/`data:`/`vbscript:` schemes and protocol-relative URLs, restricts to `https/http/mailto/tel`).
- Nested menus (mega-menu) are supported but **capped at exactly 2 levels** (`MenuItem.parent` self-FK with an explicit `_validate_hierarchy()` guard).
- `FooterSettings` has ~15 boolean/content toggles (branding, contact, navigation, social links, newsletter, trust badges, payment logos, copyright) — separate `FooterTrustBadge`/`FooterPaymentLogo` models, directly store-owned (not nested under `FooterSettings`).
- **Note:** there are now **two, separately-validated** footer toggle systems in the repo — `apps.content.FooterSettings` (older, always-on for every route via `base.html`) and `StorefrontLayoutVersion.footer_config` (`FOOTER_TOGGLE_FIELDS`, Builder-Draft/Publish-aware, only rendered on the homepage/preview). This duplication is a genuine finding for V2 (see Reuse Matrix and Implementation Plan) — not previously documented this precisely in older reports.

---

## 8. Catalog / product data

- `MerchantCollection`/`MerchantCollectionItem` (`apps/catalog/models.py`) is a **real, independent model now** — `store` FK, `name`/`slug` (unique per store), `image`, `is_active`, `collection_type` (MANUAL live; SMART reserved field, no service/UI consumes it yet), SEO fields, and a genuine `through` model (`MerchantCollectionItem.order`) for manual product ordering — closing the single largest gap the 2026-08-06 report flagged (`ProductTag(purpose="collection")` was the only option then). Full service layer (`collection_service.py`), public routes (`/collections/`, `/collections/<slug>/`), dashboard CRUD, and a dedicated legacy-tag migration command all exist. `ProductTag(purpose="collection")` still exists, untouched, as a legacy/secondary path.
- `storefront_visible_products(store)` / `storefront_listing_products(store)` (`apps/catalog/services/product_publish_service.py`) are the tenant-safe, publish-safe choke-point query services used consistently by home, product detail, product listing, collections, and related-products — confirmed as the correct reuse target for any V2 data resolver.
- `ProductImage` already supports **both** `variant` FK and `option_value` FK — i.e., variant-driven and single-attribute-driven (e.g., color-only, before size is chosen) image switching is a data-layer capability that already exists; a V2 gallery/variant-selector block would consume it, not rebuild it.
- `ProductVideo` already supports YouTube, Aparat, and Instagram permalink embeds with provider-allowlist validation.
- **Not implemented anywhere in the platform:** a "Compare" feature (no model/view/template found by exhaustive grep) and product-sharing (no share button/service found). Both are pre-existing, cross-cutting gaps, not something V2 would be regressing.
- Size guide: content-layer support exists via `ProductMetafield` (namespace `size_guide`), rendered through the existing HTML sanitizer, with dedicated XSS-prevention tests (`test_metafield_xss_prevention.py`) — **this contradicts** a claim in `docs/template-references/live-audit/01_...GAPS.md` §3.1 that "no size-guide field/model exists anywhere." Both findings are SOURCE_ONLY from this session's read; the discrepancy could stem from the metafield mechanism being generic (not size-guide-specific by name) and therefore missed by that document's grep pattern. **This needs a runtime check before being treated as fully resolved** — flagged explicitly rather than picking one silently.
- FAQ: not implemented as a real merchant-editable feature on the Product Detail page (only static hardcoded demo Q&A exists in two of the eleven family templates, per `docs/reports/SIX_FAMILIES_CONTROL_MATRIX.md` §9, itself dated but this specific finding is structural/still plausible and was not contradicted by anything found this session).

---

## 9. Cart / commerce

- `apps/cart/services/cart_service.py::add_item_to_cart` enforces stock atomically (`select_for_update()` on `Product`/`ProductVariant`), rejects non-positive quantities outright, and always resolves unit price server-side via `pricing_service.resolve_effective_price` — never trusts a client-supplied price (this exact protection is under adversarial test in `test_cart_security.py`, per its docstrings, not executed this session).
- Gift wrap is resolved server-side only (`gift_wrap_service.resolve_gift_wrap_selection`), fails closed to `(False, 0)` if the store hasn't enabled it.
- `OrderItem`/`Order` snapshot extensively at order-creation time (price, tax, shipping, gift-wrap unit price) — later `ShopSettings`/`Product` changes never retroactively alter historical orders, by design (explicit code comments throughout `order_service.py`).
- `Coupon` is store-scoped (a fixed prior global-coupon leak, per the model's own docstring).
- `Cart`/`Wishlist` have **no direct `store` FK** — isolation is enforced entirely at the service/view layer (scoping every product/variant lookup through `storefront_visible_products(store)`). This is a documented, intentional pattern, not an unaddressed gap, but it is fragile: `Wishlist` had a real cross-store leak once (fixed per PR21, guarded by `test_wishlist_store_isolation.py`) precisely because a view forgot to scope through the Store. **Any V2 code that touches Cart/Wishlist must repeat this scoping discipline explicitly — it does not come "for free" from a FK.**

---

## 10. Tenant isolation summary

Every model/service reviewed enforces store scoping via a direct `store` FK (`Product`, `Category`, `Brand`, `MerchantCollection`, `Coupon`, `Order`, `HeroSlide`, `PromotionalBanner`, `StoryRailItem`, `Menu`, `ContentPage`, `FooterSettings`) or a verified transitive chain (`ProductVariant` derived from `product.store` with direct mutation blocked at the queryset level; `MenuItem` via `menu.store`; `ProductImage`/`ProductMetafield`/`ProductVideo` via `product.store`; `Cart`/`Wishlist` via service/view-layer product scoping). No new tenant-isolation gap was found beyond the already-known, already-guarded Cart/Wishlist pattern. — SOURCE_ONLY throughout; the specific regression tests that guard each of these boundaries are cataloged in the Reuse Matrix document.
