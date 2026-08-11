# Storefront Builder V2 — Implementation Plan (Revised — Owner Decisions Locked)

**Phase:** Documentation / architecture revision only. **Implementation is still NOT approved.** This document proposes a plan and locks in nine owner decisions; it does not authorize any migration, model, view, or production code change. Per the spec's Approval Gate (§56) and the owner's explicit instruction on this revision request, the owner must still separately approve implementation before any coding begins.

**Revision history:**
- v1 (this file's prior content, commit `6eac71b`): produced during the audit-only checkpoint. Left several architecture questions open for owner decision.
- v2 (this revision): the owner has now decided all nine of those questions. This document reflects the locked decisions. It supersedes v1's proposals wherever they conflict with a decision below — v1's *rejected* alternatives are recorded in §9 for traceability, not deleted from history (they remain visible in git history at commit `6eac71b`).

**Evidence-language note (owner-mandated correction):** this revision uses `SOURCE_ONLY`, `SOURCE_WITH_TEST_COVERAGE`, `RUNTIME_VERIFIED`, `BROWSER_VERIFIED`. The word "TESTED" used in the v1 documents meant "a test file exists and its assertions were read" — that is renamed `SOURCE_WITH_TEST_COVERAGE` going forward. No claim in this document is `RUNTIME_VERIFIED` or `BROWSER_VERIFIED` — no Django runtime was available in the sandbox that produced either version of this document.

---

## 0. How to read this document

Every section below is explicitly labeled as one of:

- **CURRENT STATE** — facts about the repository as it exists today, unchanged from the original audit. Not up for debate; cite the original audit documents for full detail.
- **OWNER-APPROVED TARGET ARCHITECTURE** — the locked shape the owner has now decided V2 must converge toward. Not a proposal; a decision.
- **IMPLEMENTATION PLAN** — this document's own proposal for *how* to get from CURRENT STATE to TARGET ARCHITECTURE safely. This part remains open to further owner refinement, but the destination it aims at is fixed.

---

## 1. OWNER-APPROVED TARGET ARCHITECTURE — Domain Hierarchy

```
Store
 └── StorefrontLayout                              (UNCHANGED — remains OneToOneField(Store); single root per store)
      ├── published_version ──┐
      └── draft_version ──────┤
                               ▼
                    StorefrontLayoutVersion          (UNCHANGED shape: immutable-after-publish, Status/Source enums,
                                                       content_fingerprint)
                         ├── global_design           (EXTEND: appearance_config JSON, as today)
                         ├── header_config            (STAYS on the Version — a Global Region, NOT a Page, NOT a Section)
                         ├── footer_config            (STAYS on the Version — a Global Region, NOT a Page, NOT a Section)
                         └── pages  ──────────────────  NEW relation: StorefrontPage (FK → StorefrontLayoutVersion)
                              ├── StorefrontPage(page_type="home")
                              ├── StorefrontPage(page_type="product_detail")
                              ├── StorefrontPage(page_type="listing")
                              ├── StorefrontPage(page_type="collection")
                              ├── StorefrontPage(page_type="search")
                              └── StorefrontPage(page_type="cart")
                                   └── sections  ──────  StorefrontSection (FK → StorefrontPage, replacing today's
                                                          FK → StorefrontLayoutVersion)
                                        └── settings (JSON, unchanged shape) + stable_id (NEW, see §3)
```

Key properties of this hierarchy, all owner-decided and locked:

1. **`StorefrontLayout` remains the single store-level root** (Owner Decision 1). It is not becoming one-per-page. `published_version`/`draft_version`/`uses_visual_storefront_layout`/Draft lifecycle/Publish/Rollback/version history all continue to belong to `StorefrontLayout` exactly as they do today — this whole subsystem (`layout_service.py`) is preserved, not replaced.
2. **One `StorefrontLayoutVersion` represents the complete storefront design** — global design tokens, header, footer, and every page type, together. Publishing one Draft atomically activates the complete set (global design + header + footer + Home + Product Detail + Listing + Collection + Search + Cart) in a single pointer-swap, exactly like today's publish already does for the homepage alone (Owner Decision 2).
3. **`StorefrontPage` is a new, page-type-scoped container living under a `StorefrontLayoutVersion`**, not a replacement for `StorefrontLayout`, not a second root, not a per-page Draft/Publish cycle. There is exactly one `StorefrontPage` row per `(version, page_type)`.
4. **Header and Footer are Global Regions of the `StorefrontLayoutVersion`, not `StorefrontPage`s and not `StorefrontSection`s** (Owner Decision 6). They do not get an `order` among pages; they are not one of the six `page_type` values; they are not edited through the page-selector/section-library UI concept. `header_config`/`footer_config` remain JSON fields on `StorefrontLayoutVersion`, but their **internal shape** is expected to evolve from today's flat toggle/config JSON into a structured Rows→Blocks composition (see §6).
5. **`StorefrontSection` moves one level down** — its FK target changes conceptually from `StorefrontLayoutVersion` to `StorefrontPage` (today it points directly at the Version, because there is only ever one implicit page — Home). This is the schema-level embodiment of "sections belong to a page, and a version has many pages."

## 1.1 OWNER-APPROVED TARGET ARCHITECTURE — Media Asset vs. Placement

```
Store
 └── MediaAsset  (NEW — store-scoped physical file: image/video, one row per uploaded file)
       ▲                                  ▲
       │ referenced by                    │ referenced by
       │                                  │
  Published placement                Draft placement
  (e.g. HeroSlidePlacement           (e.g. HeroSlidePlacement
   on Published StorefrontSection)    on Draft StorefrontSection)
```

Key properties, all owner-decided and locked (Owner Decision 4 and 5):

1. **A physical media file (`MediaAsset`) is store-scoped, not version-scoped and not section-scoped.** It can be referenced by more than one placement at once — a Published placement and a Draft placement may point at the *same* `MediaAsset` row simultaneously, or at different ones.
2. **A "placement" is version/page/section-scoped state that references a `MediaAsset`**, plus whatever per-placement fields today live directly on `HeroSlide`/`PromotionalBanner`/`StoryRailItem` (title, subtitle/description, button label, destination, display order, is_active). The placement is what belongs to a specific `StorefrontSection` instance; the asset it points at is shared, reusable infrastructure.
3. **Deleting a Draft placement must never delete a `MediaAsset` still referenced by a Published placement** (or by any other placement). Asset deletion is a separate, independently-safe operation — most naturally, only allowed once an asset has zero referencing placements (reference counting or a "safe to delete" check at deletion time), never as an automatic side effect of deleting one placement.
4. **Published and Draft must be independently renderable at all times** — this is the direct fix for the rejected re-homing approach (Owner Decision 4): cloning Published→Draft creates a **new placement row** that references the **same** `MediaAsset`, rather than moving/re-pointing any existing row. The Published placement is untouched by the clone; the new Draft placement is a sibling reference to the same underlying file.

---

## 2. CURRENT STATE — What exists today (unchanged facts, for context)

Restated briefly here for readability; full detail remains in `STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md` and is not re-litigated:

- `StorefrontLayout` (1:1 Store), `StorefrontLayoutVersion` (JSON `header_config`/`footer_config`/`appearance_config`, immutable-after-publish), `StorefrontSection` (FK directly to `StorefrontLayoutVersion` today, `section_key`/`order`/`is_active`/`collapsed_in_editor`/`settings`) — all real, working, `SOURCE_WITH_TEST_COVERAGE`.
- `HeroSlide`/`PromotionalBanner`/`StoryRailItem` each own their own image file field(s) directly (`desktop_image`/`mobile_image` on the first two, a single `image` on `StoryRailItem`) plus a `section` FK (nullable) and `store` FK — confirmed by direct re-inspection of `apps/content/models.py` this session (`HeroSlide` at line 313, `PromotionalBanner` at line 357, `StoryRailItem` at line 812). **No generic media asset/library abstraction exists anywhere in the repository** — re-confirmed this session via exhaustive grep for `class.*(Media|Asset|Gallery|Upload)` across every `models.py` in the repo: zero matches beyond the three content models above and the unrelated test-file class names (`MediaViewsTestCase`, `MediaPermissionTests`). This directly satisfies the owner's Decision 5 instruction to "audit once more whether any existing generic store media/library abstraction already exists before proposing a new model" — confirmed: **none exists**, so a new minimal `MediaAsset` model is the correct proposal, not a redundant one.
- `layout_service._clone_version_content(source, target)` clones `header_config`/`footer_config`/`appearance_config` (full dict copy) and `StorefrontSection` rows (brand-new PKs) but never touches `HeroSlide`/`PromotionalBanner`/`StoryRailItem` at all — this is the confirmed bug from the prior audit. **The previously-proposed fix (remap the old media rows' `section_id` to point at the new Draft's section PKs) is now rejected by Owner Decision 4** — that approach would, by construction, move a Published section's media reference into the Draft's section, leaving the Published section with nothing. This is now understood to be unsafe, not merely incomplete.
- `apps/storefront_builder/media_views.py` already contains a working, reusable storage-cleanup pattern worth preserving in the target design: on edit, it diffs old vs. new file names and only deletes the old file via `transaction.on_commit(...)` after a successful save; on delete, it captures file names before `item.delete()` and cleans them up the same way, gated on `storage.exists(name)`. This is the correct pattern to generalize for `MediaAsset` deletion (§4.3 below), not something to reinvent.
- Header/Footer are currently *not* structured Rows/Blocks — `header_config`/`footer_config` are flat toggle/config JSON dicts validated by `layout_service.validate_header_config`/`validate_footer_config` (non-removable-element rules: cart link, home link, ≥1 active footer column). This remains true and is the starting point for the structured evolution in §6 — not a defect, just an earlier stage of the same JSON-on-Version pattern the target architecture keeps.
- Two footer systems currently coexist: `apps.content.FooterSettings` (older, always rendered via `base.html` on every non-Builder route) and `StorefrontLayoutVersion.footer_config` (newer, Builder/Draft/Publish-aware, currently rendered only on the Builder-published homepage and Preview). This duplication was flagged as an open question in the prior plan; it is now resolved by Owner Decision 7 (§7 below).

---

## 3. OWNER-APPROVED TARGET ARCHITECTURE — Stable Section Identity

**Decision (Owner Decision 3):** the database primary key of a `StorefrontSection` row must not be treated as that section's logical identity across versions. Each logical section needs a `stable_id` that survives Published → Draft clone → Publish → Restore, while the underlying row (and its PK) is freely re-created at each of those steps, exactly as it is today.

**Proposed shape (not implemented yet):**

- `StorefrontSection.stable_id` — a `UUIDField`, generated once when a section is first created (whether by a merchant adding a new section, or by the system bootstrapping/seeding default sections), and copied verbatim (not regenerated) whenever a section is cloned as part of Published→Draft, Restore, or Apply-Industry-Layout.
- **Uniqueness scope, per the owner's explicit instruction not to make it globally unique:** `UniqueConstraint(fields=["page", "stable_id"])` — i.e., uniqueness is scoped to the `StorefrontPage` a section belongs to (which itself belongs to exactly one `StorefrontLayoutVersion`). This allows the *same* logical `stable_id` to exist simultaneously in the Published version's copy of a page and the Draft version's copy of the same page (each is a different `StorefrontPage` row, each with its own `(page, stable_id)` uniqueness scope) — which is precisely the "same logical identity, different version, different PK" property the owner asked for. It also prevents two *different* logical sections within the *same* page/version from accidentally sharing a `stable_id`, which would break the disambiguation the field exists to provide.
- **Duplication semantics (explicitly required by the owner's Test Plan item C):** when a merchant duplicates a section via the existing `storefront_section_duplicate` view, the new row must receive a **new** `stable_id` (it is a new logical section, not a copy of the same logical identity) — while a straight version-clone (Published→Draft, Restore) must **preserve** the existing `stable_id` on each cloned row (it is the same logical section, now existing in a new version). This distinction is the reason `stable_id` cannot simply be "copy `settings` and `order` like today" — the clone path and the duplicate path must diverge in exactly one respect: whether `stable_id` is preserved or regenerated.
- This `stable_id` is what a future `MediaAsset` placement or any other version-spanning reference should key off of when a merchant wants a setting/placement to "follow" a section across its Draft/Publish/Restore lifecycle — the placement's own model would reference the placement's owning `StorefrontSection` row (for that specific version) as normal, but any *cross-version* correspondence logic (e.g., "does this Draft section still represent the same logical section as this Published one, for a future 'copy this Published section's media into the Draft' merchant action') should be computed via `stable_id` matching, not PK matching or `(section_key, order)` positional matching (which the rejected v1 proposal relied on, and which the owner has implicitly superseded by asking for a real stable identity instead).

---

## 4. OWNER-APPROVED TARGET ARCHITECTURE — Media Lifecycle (full detail)

This expands §1.1 into the six explicit dimensions the owner required (physical asset ownership, placement, deletion lifecycle, storage-file cleanup, reference safety, Draft/Published isolation).

### 4.1 Physical media asset ownership

- **Proposed new model: `MediaAsset`** — store-scoped (`store` FK, CASCADE — consistent with every other store-owned model in the repo), holding the actual uploaded file (`ImageField`, reusing the existing `validate_image_size`/`validate_image_content` validators already used by `HeroSlide`/`PromotionalBanner`/`StoryRailItem`), plus minimal bookkeeping (`created_at`, `created_by`, maybe `alt_text` for accessibility — spec §33 requires alt text on images). It intentionally does **not** carry any placement-specific fields (no title/subtitle/button/destination/order/is_active) — those all belong to the placement, not the asset.
- An asset's lifecycle is independent of any single version/page/section. It is created once (on upload) and can be referenced by any number of placements over time, across both Published and Draft versions simultaneously.

### 4.2 Version/page/section placement

- **Proposed new/refactored model shape:** the current `HeroSlide`/`PromotionalBanner`/`StoryRailItem` models become (or are joined by) **placement** models — each still owns its section-specific fields (title, subtitle/description, button label/visibility, destination, display order, is_active) and its `section` FK (unchanged), but instead of owning an `ImageField` directly, each placement gets a FK to `MediaAsset` (e.g., `desktop_asset`, `mobile_asset` for Hero/Banner's two-image shape; a single `asset` FK for `StoryRailItem`'s one-image shape).
- A placement is meaningless without the `MediaAsset` it points at, but a `MediaAsset` is meaningful (and safely retained) even with zero placements pointing at it, right up until an explicit cleanup/prune decision is made (see §4.3).

### 4.3 Deletion lifecycle

- **Deleting a placement** (e.g., a merchant removes a Hero slide from a Draft section) deletes only the placement row. It must **never** cascade-delete the `MediaAsset` it referenced, because that asset might still be referenced by a Published placement (or another Draft's placement, or a not-yet-cleaned-up historical placement).
- **Deleting a `StorefrontSection`/`StorefrontPage`/`StorefrontLayoutVersion`** (e.g., Discard Draft) must cascade-delete the placements that belonged to it (this part of the CASCADE chain is fine and intentional — a placement without its owning section is meaningless) but must **not** cascade-delete the `MediaAsset` rows those placements referenced (`MediaAsset` FK from placement should be `on_delete=PROTECT` or `on_delete=SET_NULL`+explicit handling, never `CASCADE`, to make this structurally impossible rather than just procedurally discouraged).
- **Deleting a `MediaAsset` itself** is a separate, explicit merchant/system action, only safe once it has zero referencing placements (or the UI/service explicitly warns and confirms if it still has references) — this is the reference-safety mechanism in §4.5.

### 4.4 Storage-file cleanup

- The existing pattern in `media_views.py` (capture the old file name before mutation, delete via `transaction.on_commit(...)` only after the DB transaction commits successfully, gated on `storage.exists(name)`) is the correct, already-proven pattern to reuse for `MediaAsset` — cleanup of the actual file on disk/object-storage should happen only when a `MediaAsset` row itself is deleted (and only once nothing references it), not when a placement is deleted.
- This directly fixes the second half of the originally-confirmed bug (CASCADE-deleting a Draft silently destroys uploaded files with no cleanup hook) — under the target model, discarding a Draft deletes placement rows (fine, no file impact) and leaves the underlying `MediaAsset` rows and their files completely untouched, because nothing in that CASCADE chain reaches `MediaAsset` at all.

### 4.5 Reference safety

- A `MediaAsset` should expose (via a service function, not raw ORM access sprinkled through views) a way to check "is this asset currently referenced by any placement, in any version" before allowing deletion — this is a straightforward reverse-FK count/exists check across whatever placement models exist (Hero/Banner/Story placements, and any future placement types), centralized in one service function so new placement types don't each need to reinvent the safety check.
- Cross-store reference safety follows the same pattern already used everywhere else in the repo (`Product`/`Category`/etc.): a placement's `clean()` should reject being pointed at a `MediaAsset` belonging to a different store, mirroring `MerchantCollectionItem.clean()`'s existing cross-store rejection pattern.

### 4.6 Draft/Published isolation

- This is the core guarantee Owner Decision 4 protects: **cloning Published→Draft creates new placement rows that reference the same `MediaAsset`, never moves or re-points an existing Published placement.** Concretely, the clone step (once implemented) would, for each Published placement, create a new placement row on the corresponding cloned `StorefrontSection` (matched by `stable_id`, per §3), copying all of the placement's own fields (title/subtitle/button/destination/order/is_active) and pointing the new row's `MediaAsset` FK at the **same** asset the Published placement points at. The Published placement row is never read-modified, only read.
- Editing the Draft placement afterward (e.g., merchant swaps in a different image) only ever touches the Draft's own placement row and, if a new file is uploaded, creates a **new** `MediaAsset` row (or points at a different existing one) — it never mutates the `MediaAsset` the Published placement still points at. This is what makes "Published media remains visible while Draft media is edited" true by construction rather than by convention.

### 4.7 Migration path for existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem` data, without losing existing data

Proposed sequence (not implemented yet — see §5 for the full ordered migration plan):

1. Add the new `MediaAsset` model (additive, empty table, zero impact on existing data).
2. Add nullable `desktop_asset`/`mobile_asset`/`asset` FK fields to the existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem` models, **alongside** their existing `desktop_image`/`mobile_image`/`image` fields (not replacing them yet) — purely additive schema.
3. Run a one-time **data migration** that, for every existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem` row with a non-empty image field, creates a corresponding `MediaAsset` row (same store, referencing the same underlying file — this can be done without re-uploading or copying the physical file, just creating a `MediaAsset` row whose `ImageField` points at the same storage path) and sets the new FK field accordingly. Existing rows keep their original `desktop_image`/`mobile_image`/`image` fields untouched during this step (belt-and-suspenders — nothing is deleted yet).
4. Once the new FK fields are backfilled and the render/service code has been updated to read from `MediaAsset` via the FK (a code change, done carefully behind a feature flag or dual-read period), only **then** consider a later, separate migration to drop the old direct image fields — and only after confirming (via the new test plan in §8) that nothing still depends on them.
5. At no point in this sequence does any existing Published or Draft content become unreadable or lose its media — every step is additive until the final, separate, carefully-verified cleanup step.

---

## 5. IMPLEMENTATION PLAN — Proposed migration sequence (not implemented yet)

The owner asked for the safest backward-compatible sequence covering seven specific items. Proposed order (each step additive/non-destructive to existing Published content unless explicitly noted otherwise):

1. **`StorefrontPage`** — new model, FK to `StorefrontLayoutVersion`, `page_type` choice field (`home`/`product_detail`/`listing`/`collection`/`search`/`cart`), `UniqueConstraint(version, page_type)`. Purely additive. A **data migration** immediately follows that creates exactly one `StorefrontPage(page_type="home")` row for every existing `StorefrontLayoutVersion`, and re-points every existing `StorefrontSection` row's FK at that new `home` page instead of directly at the version (this is the one genuinely structural change — a FK target change — and must be done as a single atomic migration with a full backup/rollback plan, since it touches every existing section row across every store). No new `StorefrontPage` rows are created yet for the other five page types — those are created lazily/on-demand once a merchant (or a later migration phase) actually starts editing that page type, so stores that never touch V2 beyond the homepage see zero new rows.
2. **Existing homepage `StorefrontSection`s** — no field changes needed beyond the FK re-target in step 1 and the new `stable_id` field (step 3). A backfill migration assigns a freshly-generated UUID to `stable_id` for every existing section row (this is safe precisely because there is no pre-existing cross-version correspondence to preserve for rows that predate the field — they simply start their `stable_id` lineage from this migration onward).
3. **Stable section identity** — add `StorefrontSection.stable_id` (UUIDField, backfilled per store above) and the `UniqueConstraint(page, stable_id)`. Additive; no behavior change until the clone/duplicate service code (a later, separate change, not part of this migration) is updated to read/write it correctly.
4. **Existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem`** — per §4.7: add `MediaAsset` model, add nullable asset-FK fields to the three placement models, run the backfill data migration, keep old image fields intact. This step is independent of steps 1–3 and could be sequenced in parallel or after them.
5. **Header/footer migration** — no schema change required at the "Global Region on the Version" level (that's already true today — `header_config`/`footer_config` already live on `StorefrontLayoutVersion`, not on any Section). The only proposed schema evolution here is the **internal JSON shape** of `header_config`/`footer_config` moving from flat toggles to structured Rows/Blocks (§6) — this can be done as a versioned-JSON-shape migration (old shape read as "row 1: legacy toggles," new shape read natively) rather than a hard cutover, so existing Published versions with the old flat shape keep rendering correctly without a forced re-save.
6. **Legacy stores** — no migration is required for stores that have never published a Builder layout at all (they remain on the fully legacy `catalog/home.html` path, `uses_visual_storefront_layout=False`, completely unaffected by any of the above). Stores that *have* published a Builder layout keep rendering their existing Published version exactly as today (steps 1–4 above only ever add new, unused-until-referenced structures around their existing Published content; the FK re-target in step 1 is the only step that touches existing Published rows, and it is explicitly designed to be behavior-preserving — same sections, same settings, just now reachable via a `home` page hop instead of directly).
7. **Legacy families/templates** — no migration needed; `family_registry.py`/`preset_registry.py`/`appearance_registry.py` and their `family_slug`/`template_slug`/`preset_slug`/`palette_slug` keys inside `appearance_config` are left completely untouched by this entire sequence, consistent with Owner Decision 8 (freeze, don't touch).

**Explicit backward-compatibility guarantee for this whole sequence:** at every step, an existing store's Published storefront must render identical output before and after. The only step with any real risk to this guarantee is step 1's FK re-target migration (moving existing sections under a newly-created `home` page) — this step must ship with its own dedicated before/after rendering-equivalence test (see §8, Test Plan D) run against a copy of representative existing data before being considered safe, and the plan explicitly calls out that no other step in this sequence should be bundled into the same commit/migration as that one.

---

## 6. OWNER-APPROVED TARGET ARCHITECTURE — Header/Footer as Structured Global Regions

Per Owner Decision 6, restated precisely: Header and Footer remain fields on `StorefrontLayoutVersion` (not Pages, not Sections), but their internal JSON shape is expected to evolve from today's flat config/toggle dict into a structured composition:

```
header_config (JSON, target shape — not implemented yet):
{
  "rows": [
    {"blocks": ["logo", "search", "account", "wishlist", "cart"]},
    {"blocks": ["main_menu"]}
  ],
  "settings": { "sticky": true, "background": "...", ... }
}
```

Candidate block types, directly from the owner's list: Logo, Store Name, Search, Menu, Account, Wishlist, Cart, CTA, Internal link, External link, Social link, Phone, Spacer. Footer follows the identical Rows→Blocks principle.

**This document does not implement the composer.** It records the target shape so that Phase 4 (Header/Footer Composer, §10) has a concrete, owner-approved destination to build toward, and so that the migration plan in §5 item 5 already accounts for a future JSON-shape evolution rather than needing a second, unplanned migration later.

---

## 7. OWNER-APPROVED TARGET ARCHITECTURE — Legacy Footer System (Owner Decision 7)

- `apps.content.FooterSettings` → classified **`LEGACY_KEEP`** for the duration of the migration. It continues to render on every non-Builder-aware route (Product Detail, Listing, Collection, Cart, Wishlist, Content Pages) exactly as today, via `base.html`.
- `StorefrontLayoutVersion.footer_config` → becomes the **sole V2-authoritative footer** once a store has migrated. It evolves toward the structured Rows/Blocks shape in §6.
- Long-term classification, exactly as instructed: `FooterSettings` → `LEGACY_KEEP` now → `REMOVE_LATER`, but **only** after a store has explicitly migrated to V2 and the owner has separately approved removal — not automatically, not as a side effect of any Phase in this plan. No removal work is scheduled by this document.

---

## 8. IMPLEMENTATION PLAN — Required Test Plan (owner-specified categories, before any implementation)

All of the following are **new tests that do not exist today** (confirmed absent in the original audit's test cataloging) and must be written — and, unlike the original audit checkpoint, actually **executed** in a Django-capable environment — before the corresponding implementation work is considered done. None of these have been run in this sandbox (no Django runtime available); this section describes what must exist and pass, not a claim that it has been run.

**A. Published/Draft independence**
- `test_publishing_a_draft_does_not_alter_a_prior_published_version_object` — sanity check that Publish's pointer-swap never mutates the content of the version it swaps away from until it is later Archived-and-eventually-reused as a new Draft base.
- `test_editing_a_draft_section_setting_does_not_change_the_published_versions_equivalent_section` — Draft/Published are genuinely separate rows once cloned; mutating one's `settings` JSON must never affect the other.
- `test_discarding_a_draft_does_not_delete_or_alter_any_published_content` — Discard only ever touches the Draft's own tree (page/section/placement rows scoped to that Draft version), never reaches into Published.

**B. Media lifecycle**
- `test_published_to_draft_clone_creates_new_placement_referencing_same_media_asset` — the core Owner Decision 4/5 guarantee: after cloning, the Draft's placement is a *different row* pointing at the *same* `MediaAsset` as the Published placement, and the Published placement itself is completely untouched (same PK, same field values, same asset reference, before and after the clone).
- `test_editing_draft_media_placement_does_not_mutate_published_placement_or_asset` — swapping the Draft's image (creating/pointing at a different `MediaAsset`) must leave the Published placement's own `MediaAsset` reference unchanged.
- `test_deleting_a_draft_placement_does_not_delete_a_mediaasset_still_referenced_by_published` — the reference-safety guarantee from §4.5, explicitly tested with a shared asset.
- `test_orphan_mediaasset_with_zero_placements_can_be_safely_pruned_without_affecting_referenced_assets` — a cleanup/prune operation (if and when one is built) must only ever touch assets with zero references, verified by seeding both a zero-reference asset and a still-referenced asset in the same test and asserting only the former is removable.

**C. Stable section identity**
- `test_stable_id_survives_published_to_draft_clone` — the cloned Draft section has the *same* `stable_id` as its Published source.
- `test_duplicating_a_section_assigns_a_new_stable_id` — `storefront_section_duplicate` must produce a row whose `stable_id` differs from the original's, distinguishing "new logical section" from "same logical section, new version."
- `test_stable_id_uniqueness_is_scoped_per_page_not_global` — two different `StorefrontPage` rows (e.g., Published's `home` page and Draft's `home` page) can each have a section with the same `stable_id` without violating any constraint; two sections *within the same page* cannot share a `stable_id`.

**D. Multi-page lifecycle**
- `test_one_draft_version_can_hold_multiple_page_configurations_simultaneously` — create/edit sections across `home`, `product_detail`, and `listing` `StorefrontPage`s under the same Draft version, assert all three persist independently and correctly.
- `test_publish_atomically_activates_all_page_configurations_at_once` — publishing a Draft that has edits across multiple page types must make all of them live in the same atomic operation (no scenario where Home is updated but Listing is not, or vice versa).
- `test_rollback_restores_a_complete_multi_page_storefront_version` — Restore must bring back every page type's configuration from the target version, not just Home.
- `test_public_pages_never_read_draft_state` — for every one of the six page types, the public-facing view must be proven to only ever read `layout.published_version`, never `layout.draft_version`, even when a Draft with different content exists concurrently for the same store.

**E. Tenant isolation**
- Reject-cross-store tests for: `MediaAsset`, `StorefrontSection` (already covered today for the version-only shape; must be re-verified once sections belong to a `StorefrontPage`), `StorefrontPage` itself, and continue to enforce the already-existing coverage for `Product`/`Category`/`MerchantCollection`/`Menu` reference validation inside section/placement settings (no regression permitted here — the existing tests covering this today must keep passing unmodified).

**F. Route consistency**
- Once a store has explicitly migrated to V2 (i.e., published at least one `StorefrontLayoutVersion` containing all six page types), `test_all_six_page_types_resolve_through_the_v2_global_shell` — Home, Product Detail, Listing, Collection, Search, and Cart must each render via the same shared header/footer Global Region and the same global design tokens, for that store. This test must also assert the **negative** case: a store that has *not* migrated continues to render via its current legacy/Family templates, completely unaffected.

---

## 9. Rejected alternatives (recorded for traceability, not proposed again)

These were left as open options in the prior version of this document (commit `6eac71b`) and are now explicitly closed by the owner:

- ~~Change `StorefrontLayout.store` from `OneToOneField` to `ForeignKey`, using a `page_type` field directly on `StorefrontLayout` to support multiple pages.~~ **Rejected — Owner Decision 1/2.** `StorefrontLayout` stays a single root; `StorefrontPage` is the new page concept instead, nested under the Version.
- ~~Remap existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem.section_id` from the old (Published) section's PK to the new (Draft) section's PK during clone.~~ **Rejected — Owner Decision 4.** This would silently strip media from the live Published storefront while a merchant is only editing a Draft. The approved direction instead separates the physical asset from its per-version placement (§1.1, §4).
- ~~Turn Header/Footer into ordinary Page sections, composed the same way Home's sections are.~~ **Rejected — Owner Decision 6.** Header/Footer remain Global Regions on the `StorefrontLayoutVersion`, distinct from `StorefrontPage`/`StorefrontSection`, even though their *internal* JSON shape is expected to become more structured over time.
- ~~Use positional `(section_key, order)` matching as the clone-correspondence mechanism instead of a real stable identity field.~~ **Superseded — Owner Decision 3.** A real `stable_id` (UUID, scoped `(page, stable_id)`) is the approved mechanism; positional matching is fragile (breaks if two sections of the same type exist at different orders) and is no longer the proposed approach.

---

## 10. IMPLEMENTATION PLAN — Locked Phase Roadmap

This roadmap order is now locked by the owner (Owner Decision 9) and replaces the prior version's roadmap. **No implementation work of any kind has started; this is a plan only.**

### Phase 0.5 — Correctness Lock
**Goal:** make the existing foundation safe enough to build V2 on, without yet making all public pages editable.
**Must include planning for** (per the owner's explicit list): section/media lifecycle correctness (§4), Draft vs. Published isolation (§4.6), storage cleanup correctness (§4.4), stable section identity (§3), shared storefront shell consistency (already documented in `STOREFRONT_BUILDER_V2_ROUTE_RENDERER_MAP.md` — the finding that only 2 of ~11 templates include the shared shell partials stands unchanged), regression tests (§8 categories A/B/C), and runtime verification requirements (this plan must be executed against a real Django environment before being considered done — not possible in this sandbox).
**Explicitly does not include:** making Product Detail/Listing/Collection/Search/Cart editable via Sections yet — that is Phase 1's job, and depends on `StorefrontPage` existing first.

### Phase 1 — Universal Page Architecture
**Goal:** introduce the multi-page design model (`StorefrontLayoutVersion → StorefrontPage → StorefrontSection`) for the six initial page types (home, product_detail, listing, collection, search, cart), with every page sharing global design tokens, header, navigation, and footer, and the product-card design system where relevant. **Goal is architectural consistency and versioned page composition, not visual polish** — explicitly not required to look different or better yet, just structurally correct and consistently shelled.

### Phase 2 — Unified Single-Screen Builder
Implement the UX represented by `docs/prototypes/storefront-builder-v2/rastisi_builder_v2_prototype.html` (page selector, block/section library, live canvas, inspector, add/delete/reorder/duplicate/hide-show, desktop/mobile preview, header editor, footer editor, Draft preview, Publish, Rollback). The HTML file remains UX intent only — its implementation is not to be copied.

### Phase 3 — Home Block Library
Implement/refine reusable blocks (Hero, Slider, Banner, Category Grid, Product Grid, Product Carousel, Collection, Brands, Rich Text, Image+Text, CTA, Story Rail, Video, Spacer), reusing the existing 22-type Section Registry wherever it already fits.

### Phase 4 — Header/Footer Composer
Structured Rows + reusable Global-Region blocks, per the target shape in §6.

### Phase 5 — Commerce Page Composition
Complete configurable composition for Product Detail, Listing, Collection, Search, Cart. **Must reuse existing tenant-safe commerce/catalog services** (`storefront_visible_products`/`storefront_listing_products`, `cart_service`, `pricing_service`, `collection_service`) — must not reimplement commerce business logic, per the spec's own explicit requirement and the original audit's confirmation that these services are already correct and reusable as-is.

### Phase 6 — Presets
Only after the engine works: one neutral default preset, one complex real-world-inspired preset, and — later — migration of useful legacy Family designs into presets (Owner Decision 8's extraction goal).

### Phase 7 — Legacy Migration
Only after browser/runtime confidence has been established. Existing stores remain on Legacy until explicitly migrated — no forced cutover, ever, for a store that hasn't opted in.

---

## 11. Remaining architecture questions that genuinely still require owner input

Everything the prior version of this document flagged as open in §7 (its "Open questions requiring explicit owner decision") has now been resolved by Owner Decisions 1–9, **except** the following, which were not addressed by the nine decisions and remain genuinely open:

1. **Exact `MediaAsset` field set** — this document proposes a minimal shape (`store`, image file, `created_at`, `created_by`, optional `alt_text`). Whether it should also carry things like a caption, a "kind" discriminator (image vs. future video), or usage-tracking metadata is not decided.
2. **Whether the old `desktop_image`/`mobile_image`/`image` fields on `HeroSlide`/`PromotionalBanner`/`StoryRailItem` are ever actually removed**, or intentionally kept forever as a redundant/legacy-compat field once the FK-based `MediaAsset` reference is the real source of truth. §4.7 proposes keeping them until proven safe to drop, but does not commit to ever dropping them.
3. **The size-guide discrepancy** flagged in the original Existing Capability Audit (§8) — two sub-agent investigations disagreed on whether a size-guide mechanism exists via `ProductMetafield`. This still needs a runtime check in a Django-capable environment and is unrelated to the nine owner decisions in this revision.
4. **Whether `FooterSettings` (`LEGACY_KEEP` → `REMOVE_LATER`) removal is ever actually scheduled**, and under what condition a store is considered "safely migrated" enough to stop needing it — Owner Decision 7 fixes the *classification* but not the *exit criteria*.

None of these four block Phase 0.5 or Phase 1 planning; they are noted so they are not silently forgotten, not because they are urgent.
