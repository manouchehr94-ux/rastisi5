# Storefront Builder V2 — Implementation Plan (Proposal Only — Not Approved)

**Phase:** Audit checkpoint output. This document proposes a plan; it does **not** authorize implementation. Per the spec's Approval Gate (§56) and this task's mandatory stop (Step 24), implementation must not begin until the owner has explicitly reviewed and approved this plan alongside the other four audit documents.

This plan is evidence-based, derived from `STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md`, `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md`, `STOREFRONT_BUILDER_V2_ROUTE_RENDERER_MAP.md`, and `STOREFRONT_BUILDER_V2_DATA_LIFECYCLE.md`. All evidence underlying it is `SOURCE_ONLY` (no Django runtime was available in this sandbox this session — see the Existing Capability Audit §0).

---

## 1. Headline conclusion

**RastiSi4 is not a greenfield system for this feature.** A working, tenant-safe, Draft/Preview/Publish/Rollback-capable visual builder already exists (`apps/storefront_builder`), already renders the homepage through a shared engine, already has a 22-type Section Registry with a real Data Source contract, already has responsive per-section settings, and already has a real `MerchantCollection` model. **The gap between today's system and the V2 spec is narrower and more specific than "build a builder from scratch"** — it is:

1. The homepage-only scope of the existing Section/Layout system (spec wants Home + PDP + Listing + Collection + Search + Cart all Section-driven and Draft/Publish/Rollback-aware).
2. The shared-shell wiring gap (only 2 of ~11 templates include the Family-aware header/footer partials — see Route/Renderer Map).
3. The confirmed section-bound-media clone/CASCADE-delete bug (Data Lifecycle §5).
4. The coexistence of two parallel, historically-accumulated appearance systems (11 DOM-forking Families vs. 10 CSS-token-only legacy Templates) that both partially satisfy, and both partially conflict with, the spec's "one universal engine" principle.
5. The complete absence, today, of a "Page Template" data concept — everything Section-based is implicitly homepage-only.

None of the above requires discarding the existing engine. All of them are extensions or targeted refactors of it.

---

## 2. Models — reusable as-is, needing extension, needing a new relation, or genuinely new

### 2.1 Reusable as-is (no schema change)
- `StorefrontLayout` (1:1 Store anchor + published/draft pointers + feature flag)
- `StorefrontLayoutVersion` (immutable-after-publish, JSON config + fingerprint + Status/Source enums)
- `StorefrontSection` (key/order/active/collapsed/settings)
- `SECTION_REGISTRY` (22 types, Data Source contract, responsive settings)
- `MerchantCollection`/`MerchantCollectionItem`
- `storefront_visible_products`/`storefront_listing_products` (product_publish_service.py)
- `Menu`/`MenuItem` (navigation, already store-scoped, already destination-safe)
- Cart/Order/Coupon commerce services (must be consumed, never reimplemented — spec §14/§18 explicit requirement)

### 2.2 Needing extension (add fields/keys, no structural rewrite)
- `StorefrontLayoutVersion.appearance_config` — add whatever new global design-token keys V2 needs; the JSONField + registry-default pattern already used for `template_slug`/`family_slug`/`preset_slug` extends cleanly.
- `StorefrontSection` — **candidate** extension: a `page_type`/`page_key` field (see §3 below) if the "existing model can be extended" path is chosen for multi-page support, rather than introducing `StorefrontPage`.
- `layout_service._clone_version_content` — must be extended (this is a service/function fix, not a model fix) to also remap `HeroSlide`/`PromotionalBanner`/`StoryRailItem.section_id` from old to new section PKs during clone. Concretely: build an old-PK → new-PK correspondence map while creating the cloned sections (matching on `(section_key, order)` position, since that's the only stable identity across a clone today), then bulk-update the media rows' `section_id` accordingly, inside the same atomic block.

### 2.3 Needing a new relation (FK/through model addition, not a new root concept)
- Section-bound media models (`HeroSlide`/`PromotionalBanner`/`StoryRailItem`) already have the relation (`section` FK) — no new relation needed there; the gap is in the *service* that clones sections, not the schema.
- If Header/Footer Builder (spec §10.2/§10.4) needs to become "just more Sections" rather than staying as separate `header_config`/`footer_config` JSON blobs, that would be a new relation between `StorefrontLayoutVersion` and a `region` discriminator on `StorefrontSection` (e.g., `region` enum: `home_page` | `header` | `footer` | `announcement`) — **not decided by this document**, flagged as an open design question for the owner (see §7).

### 2.4 Genuinely new models — only if the "extend existing" path is rejected
- `StorefrontPage` — **only** if the owner decides `StorefrontLayout`'s 1:1-with-Store relationship should not be loosened into a 1:many. This is the spec's own suggested shape (§27: "Conceptually the system needs: `StorefrontLayout / StorefrontLayoutVersion / StorefrontPage / StorefrontSection / StorefrontBlock`"), but the spec **also explicitly says** (§20): "Prefer existing models where they already provide correct semantics" and "DO NOT assume all of these require new models." Given `StorefrontSection.settings` already carries an open JSON bag and `section_key` is just an allowlisted string, this document's non-binding recommendation is: **try extending `StorefrontLayout` to be `ForeignKey(Store)` instead of `OneToOneField(Store)` plus a `page_type` field, before introducing a wholly new `StorefrontPage` model** — smaller migration, reuses 100% of the existing Draft/Publish/Rollback/clone/render machinery unchanged. This needs explicit owner sign-off before any migration is written, and is called out as the single largest schema question in this whole audit.
- `StorefrontBlock` — the spec's `Block` concept (nested-inside-a-Section elements) does not exist today; `StorefrontSection.settings` currently holds block-like data inline (e.g., a hero's slide list, a product-section's data source) rather than as separate rows. **No evidence found that this needs to become a separate model for Phase 1** — the existing JSON-settings approach already satisfies the spec's Phase 1 non-goals (§4: "no arbitrary nested DOM trees... freedom must come from strong composable blocks, not uncontrolled DOM editing"). Recommend deferring a real `StorefrontBlock` model until a concrete Section type demonstrably needs it.

### 2.5 Migration risk assessment
- Extending `appearance_config`'s default dict: **zero migration risk** (no schema change, just a new default key, backward-compatible by construction — this is the exact pattern already used for `family_slug`/`preset_slug`).
- Fixing `_clone_version_content`: **zero migration risk** (pure service-code change), but **behavior-risk-bearing** — must ship with a new regression test that creates section-scoped media, clones, and asserts the media follows (this test does not exist today and must be added before this fix is considered done).
- `StorefrontLayout.store` OneToOne → ForeignKey + `page_type` field: **low-to-medium migration risk** — existing rows get a default `page_type="home"` via a data migration; the unique constraint changes from "one row per store" to "one row per (store, page_type)"; every existing query/service that assumes `store.storefront_layout` (singular reverse OneToOne accessor) needs updating to filter by `page_type` explicitly. This is a real, non-trivial refactor across `layout_service.py`, `render_service.py`, `bootstrap_service.py`, and every call site — must be scoped as its own dedicated phase, not bundled silently into an unrelated commit.
- A new `StorefrontPage` model instead: **higher new-surface-area but lower regression risk** to the existing homepage-only code paths (existing code simply keeps working unmodified against the untouched `StorefrontLayout`; new page types are additive). Trade-off is duplicated Draft/Publish/Rollback plumbing unless carefully abstracted.

**This document does not pick one of these two paths.** It is flagged as the primary decision the owner must make before Phase 1 scoping is finalized.

---

## 3. Backward compatibility strategy

- No existing store's published storefront may change appearance or behavior as a side effect of any V2 groundwork commit. The existing feature-flag pattern (`StorefrontLayout.uses_visual_storefront_layout`, only set `True` on first explicit Publish) is the proven mechanism for this and should be reused for any new page-type rollout, exactly as it was for the original homepage builder.
- Any schema change must ship with a data migration that produces byte-identical existing behavior for stores that have never touched the affected feature (this is the same discipline already documented and followed for `appearance_config` defaults, `collapsed_in_editor`, etc.).
- The `_clone_version_content` fix must not change the *shape* of cloned Section data for stores unaffected by section-scoped media (i.e., stores using only legacy store-global `HeroSlide`s, which are unaffected by this bug in the first place, must see zero behavior change).

---

## 4. Legacy Family system — archive/migration strategy

Per spec §23/§36/§43 and this audit's own findings (Existing Capability Audit §4, Reuse Matrix rows for Family/Preset/Template Registries):

1. **Do not delete or modify family-specific code as part of any V2 groundwork.** The 11 families are recent, heavily tested, and in active use by real merchant stores today (confirmed by the extensive dedicated test suite: `test_family_registry.py`, `test_eleven_families.py`, `test_six_families_tenant_isolation.py`, plus the per-family test files).
2. **Freeze new family-specific feature development** (spec §23 item 1) — no new 12th family, no new family-specific business logic, effective immediately per the spec's own instruction, independent of this audit's approval status.
3. **`family_slug` transition path:** keep `family_slug` exactly where it is today (`StorefrontLayoutVersion.appearance_config`) for the duration of the transition. V2's own appearance/design-token system should be additive alongside it, not a forced migration — a store currently on `family_slug="heritage_premium"` should keep rendering identically until a merchant *explicitly* opts into a V2 Draft (mirroring the spec's own preferred strategy in §36: "Existing storefronts stay functional on Legacy until explicitly migrated").
4. **Extraction, not disposal:** the 11 families' header/hero/category/footer/product-card/product-detail template variants are legitimate reference material for V2 Presets/block variants. This audit does not attempt the extraction itself (out of scope for an audit checkpoint) but confirms the source material is real, working, and cataloged (family_registry.py + the per-family template files listed in the Existing Capability Audit §4) and therefore extractable later without needing to reverse-engineer intent from scratch.
5. **The `appearance_registry.py` 10-Template/20-Palette system is a separate, still-live legacy path**, mutually exclusive with `family_slug` today. V2's design-token layer should aim to converge with this system's *mechanism* (CSS custom properties driven by a JSONField config, Draft/Publish/Rollback-aware) rather than inventing a third parallel token system — but whether the 10 legacy Templates themselves get retired, kept as V2 Presets, or left entirely alone is an explicit open question, not decided here (see §7).
6. **Do not archive families "in code" yet** — per the task's explicit Step 3 prohibition. This plan only proposes *freezing new work* on them, which is different from archiving/removing them from merchant-facing selection.

---

## 5. Smallest safe Phase 1

Based strictly on the evidence gathered (not aspiration), the smallest Phase 1 that meaningfully advances toward "one universal storefront shell" without requiring the large `StorefrontLayout`/`StorefrontPage` schema decision to be resolved first:

### Phase 1 goal
Prove that Home, Product Detail, Product Listing/Category, and Collection can share **one consistent page shell** (header/footer/design tokens), without yet making those other pages Section/Block-editable. This directly targets the browser-QA problem the owner already observed, with the lowest schema risk.

### Phase 1 scope
1. **Fix the confirmed media-clone bug** (`_clone_version_content` remapping + a CASCADE-delete storage-file cleanup hook) — this is a correctness fix to the *existing* homepage builder, independent of any new page types, and should ship first since every subsequent phase builds on top of a Draft/Publish/Clone cycle that is currently silently lossy.
2. **Wire every public route's shell through the existing shared partials** (`page_shell_header.html`/`page_shell_footer.html`) instead of `base.html`'s own hardcoded blocks — i.e., make Product Detail, Product Listing, Collection Index/Detail, Cart, Wishlist, and Content Pages all `{% block header %}{% include "storefront_builder/partials/page_shell_header.html" %}{% endblock %}` (and the footer equivalent), exactly like `home_visual.html` already does. This alone, with **zero new models**, closes the largest visible inconsistency this audit found.
3. **Do not yet make these other pages Section-editable.** Phase 1 proves shell consistency only; Section/Block composition of Product Detail/Listing/Collection is Phase 2+, after the owner has decided the `StorefrontLayout` extension-vs-`StorefrontPage` question (§2.4).
4. **Regression-test the "no family selected" path stays byte-identical** for every route touched, before and after — this mirrors the exact discipline already used for prior additive changes in this codebase (`collapsed_in_editor`, `appearance_config` defaults).

### Files expected to change in Phase 1
- `apps/storefront_builder/services/layout_service.py` (`_clone_version_content` fix)
- `apps/content/models.py` or a new small migration (storage-cleanup signal/hook for CASCADE-deleted media, if the owner wants automatic file cleanup rather than accepting orphaned files as a lower-priority follow-up)
- `apps/catalog/templates/catalog/product_detail.html`, `product_list.html`, `collection_index.html`, `collection_detail.html` (header/footer block overrides)
- `apps/cart/templates/cart/cart_detail.html`, `apps/customers/templates/customers/wishlist.html`, `apps/content/templates/content/page_detail.html` (same)
- No changes expected to: `apps/orders`, `apps/cart/services/*` (commerce logic), `apps/stores/*` (tenant resolution), `family_registry.py`/`preset_registry.py`/`appearance_registry.py` (left untouched per the freeze in §4.2)

### Models expected to change in Phase 1
- **None**, if the fix in item 1 is implemented purely as a service-layer change (remapping logic inside `_clone_version_content`, no new field needed since the correspondence can be computed in-memory during the clone using `(section_key, order)` matching).
- **One optional new field** if the owner wants a more robust remap mechanism than positional `(section_key, order)` matching — e.g., a `client_section_uuid` or similar stable identity field on `StorefrontSection` that survives cloning by being copied verbatim (rather than relying on order-matching, which could misfire if two sections of the same type at different orders exist). This is a **candidate, not a requirement** — flagged for the owner to weigh in on before implementation.

### Migrations
- Zero, under the "positional matching" approach to the clone fix.
- One small, additive migration (`AddField`, nullable/defaulted) if the "stable identity field" approach is preferred instead.

### Risks
- Item 2 (shell wiring) touches the visual presentation of every non-homepage public route — must be verified (once a Django-capable environment is available) that no existing template block/variable dependency breaks when the header/footer block is overridden. This is a real regression-risk area precisely because it is high-value; must not be rushed.
- The clone-fix regression test must be written *before* the fix (or at minimum alongside it) since no such test exists today — without it, a future regression could silently reintroduce the exact same bug.

### Tests required before Phase 1 work begins (baseline / regression-lock)
- Full existing `apps/storefront_builder/tests/` suite, `apps/catalog/tests/test_collection_*.py`, `apps/cart/tests/*`, `apps/customers/tests/test_wishlist_*` — as a "before" baseline, once a Django-capable environment is available (not possible in this sandbox this session).

### Tests required after Phase 1 work
- New: a clone-preserves-section-scoped-media regression test (publish → new draft → assert `HeroSlide`/`PromotionalBanner`/`StoryRailItem` still resolve against the new section).
- New: a shell-consistency test per migrated route (Product Detail/Listing/Collection/Cart/Wishlist/Content Page all render the same header/footer DOM structure as Home, for a store with no family selected — i.e., byte-comparable generic markup).
- Re-run of the full existing suite to confirm zero regression in tenant isolation, commerce rules, and family-specific rendering (which must remain visually unchanged for stores currently using a Family, since Phase 1 only touches the *shell*, not the Family-aware body content).

### Backward compatibility strategy for Phase 1
- Every touched template's existing `{% block content %}` (or family-body-equivalent) is left untouched — only the header/footer block wiring changes. A store with no Family/Template selected today should see the exact same generic header/footer content it sees now, just sourced from the shared partial instead of `base.html`'s inline blocks (i.e., `page_shell_header.html`'s `{% else %}` branch must be verified to produce equivalent markup to `base.html`'s current hardcoded header before the switch is made — this may require a small content audit/diff, not assumed identical by default).

---

## 6. Test audit — what exists, what must be run before/after Phase 1

Per Step 16 of the task, existing tests were cataloged (not executed — no Django runtime available). The full list, organized by concern, is already detailed in the Existing Capability Audit document §1.6, §8, §9, §10. Before Phase 1 begins in a Django-capable environment, the owner (or a subsequent session with network/package access) must:

1. Run the full suite once, unmodified, to establish a real (not just source-inferred) baseline.
2. Add the two new tests described in §5 above.
3. Re-run the full suite after Phase 1 changes land, comparing pass/fail against the baseline.

This audit explicitly cannot perform steps 1–3 itself this session (see Existing Capability Audit §0) and does not claim to have done so.

---

## 7. Open questions requiring explicit owner decision before Phase 1 implementation

1. **`StorefrontLayout` extension vs. new `StorefrontPage` model** (§2.4) — the single largest schema decision.
2. **Clone-fix remap strategy** — positional `(section_key, order)` matching (zero migration) vs. a new stable identity field (one small migration) (§2.5, §5).
3. **Header/Footer Builder's long-term home** — stay as `header_config`/`footer_config` JSON on `StorefrontLayoutVersion`, or become Sections with a `region` discriminator (§2.3)?
4. **Two coexisting footer toggle systems** (`apps.content.FooterSettings` vs. `StorefrontLayoutVersion.footer_config`) — converge, or intentionally keep separate (one for non-Builder routes, one for Builder-aware ones) permanently?
5. **Legacy `appearance_registry.py` (10 Templates) fate** — retire, convert to V2 Presets, or leave permanently as-is alongside a new V2 token system?
6. **Storage-file cleanup on CASCADE-delete** — build the cleanup hook as part of the clone-bug fix (item 1 of Phase 1), or treat it as a separate, lower-priority follow-up?
7. **Size guide discrepancy** (Existing Capability Audit §8) — needs a runtime check to resolve conflicting findings between this session's sub-agents before being relied upon in any V2 Product Detail block design.

This document deliberately does not answer these questions — per the spec's explicit instruction (§56, Approval Gate), the owner reviews and decides before any implementation begins.
