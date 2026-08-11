# Storefront Builder V2 — Data / Lifecycle Map

**Phase:** Architecture revision (v2). Documentation only — nothing in this document has been implemented. All evidence `SOURCE_ONLY` unless marked `SOURCE_WITH_TEST_COVERAGE` (test file read, not executed — see sandbox constraint in `STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md` §0). The original audit used the word "TESTED" for this same meaning; that wording is retired per owner instruction in favor of the clearer `SOURCE_WITH_TEST_COVERAGE` term used throughout this revision.

**Revision note:** §1–§4 and §6 below describe **CURRENT STATE** and are unchanged from the original audit (commit `6eac71b`). §5 has been revised — the original audit's proposed fix for the clone bug is now rejected by the owner and replaced with the approved target design. §7 has been resolved by owner decision (it was previously an open schema question). §9 is new — it describes the **OWNER-APPROVED TARGET ARCHITECTURE** for the multi-page lifecycle and the media asset/placement lifecycle. Full decision record: `STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md`.

---

## 1. Draft

**Entry point:** `apps/storefront_builder/services/layout_service.py::get_or_create_draft(store, *, user=None)`

```
1. layout = get_or_create_layout(store)          # idempotent StorefrontLayout provisioning
2. if layout.draft_version_id exists: return it  # idempotent — never creates a second concurrent draft
3. enforce_rate_limit(...)                        # shared infra, apps/core/services/rate_limit.py
4. is_first_ever = not layout.versions.exists()
5. new StorefrontLayoutVersion(status=DRAFT)      # brand-new PK
6. if is_first_ever:
       bootstrap_service.apply_bootstrap_content(draft)   # reconstructs legacy hardcoded homepage as sections; no clone source exists yet
   else:
       _clone_version_content(layout.published_version, draft)   # see §5 below
7. layout.draft_version = draft; layout.save()
```

All of the above executes inside a single `transaction.atomic()` block. Evidence: SOURCE_ONLY, cross-checked by two independent context-gatherer passes in the original audit session; `SOURCE_WITH_TEST_COVERAGE` per `test_layout_service.py::GetOrCreateDraftTests`.

**CURRENT STATE, unchanged by this revision** — this describes today's homepage-only Draft creation. Under the target architecture (§9), the same function's responsibilities extend to cloning every `StorefrontPage` under the source version, not just a flat list of sections.

---

## 2. Preview

**Entry point:** `apps/storefront_builder/views.py::storefront_preview` (staff-only, `@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)`, `@xframe_options_sameorigin` because it's embedded in the editor's own iframe).

- Calls `render_service.build_render_items(draft_version, store)` — **the exact same function** the public `home()` view calls for the published version. This is the mechanism that satisfies the spec's "Preview and Public must use the same rendering pipeline" requirement (§9) — but **only for the homepage today** (see §7 "Scope limitation").
- Supports a non-persistent, in-memory "candidate" preview: `?preview_template=<slug>` / `?preview_family=<slug>` query params build a throwaway `_CandidateAppearanceVersion` object (never written to the DB) so a merchant can preview a different Template/Family without touching the real Draft.
- No shareable link/token exists — session-based, staff-of-this-store only, by explicit design (documented in the view's own comments, referencing an "Owner Decision #11").
- Evidence: SOURCE_ONLY / SOURCE_WITH_TEST_COVERAGE (`test_views.py::EditorAccessTests`, `RenderedPreviewIntegrationTests`, `test_page_shell.py`).

**CURRENT STATE, unchanged by this revision.** Owner Decision 6 confirms Preview should eventually cover all six page types via the same shared mechanism — no change to how Preview itself works, only to how much content it has to render once `StorefrontPage` exists.

---

## 3. Publish

**Entry point:** `layout_service.publish(store, *, user=None)`

```
1. enforce_rate_limit(..., limit=20, period="hour")
2. draft = layout.draft_version   (must exist, else raises)
3. atomic:
     a. compute_fingerprint() on draft content, store on draft.content_fingerprint
     b. draft.status = PUBLISHED
     c. if layout.published_version exists: layout.published_version.status = ARCHIVED
     d. layout.published_version = draft
     e. layout.draft_version = None
     f. layout.uses_visual_storefront_layout = True     # ONLY place this flag is set True
     g. layout.save()
```

Publish is a **pure pointer swap** — no content is copied at publish time (content was already fully formed on the Draft). This means a failed/partial publish can never leave the live storefront in a half-updated state — the only mutation is a small set of FK/flag fields inside one atomic transaction. Evidence: SOURCE_ONLY / SOURCE_WITH_TEST_COVERAGE (`test_layout_service.py::PublishTests`, `test_views.py::PublishDiscardRestoreViewTests::test_publish_redirects_and_sets_flag`).

**CURRENT STATE, unchanged mechanism, expanded scope under the target architecture (Owner Decision 2, locked):** this exact pointer-swap mechanism is what makes "publishing one Draft atomically activates the complete set of pages together" possible — because Publish only ever swaps which `StorefrontLayoutVersion` is pointed at, and a version will contain all of its `StorefrontPage`s at once, there is nothing to add here to satisfy that requirement. The atomicity the owner asked for falls out of the existing pointer-swap design for free once `StorefrontPage` exists underneath the version.

---

## 4. Rollback

**Entry point:** `layout_service.restore_version(store, version_id, *, user=None)`

- Looks up the target version, **fails closed** (`CrossStoreVersionError`) if it belongs to a different store or doesn't exist.
- **Never publishes directly.** Always creates a **new Draft** (`source=RESTORED`) via `_clone_version_content(target_version, new_draft)` — the merchant must explicitly Preview and Publish the restored draft, exactly like any other edit. This is stricter/safer than the spec's minimum bar (spec §9 only requires "Merchant can restore an earlier published version," doesn't mandate the extra Draft step) — worth preserving, not weakening.
- Evidence: SOURCE_ONLY / SOURCE_WITH_TEST_COVERAGE (`test_layout_service.py::RestoreVersionTests::test_restore_clones_source_sections`, `test_views.py::PublishDiscardRestoreViewTests::test_restore_creates_draft_not_publish`, `test_restore_cross_store_returns_404`).

**CURRENT STATE, unchanged mechanism.** Restore shares `_clone_version_content` with Draft creation, so the §5 revision below applies identically to Restore — it must also preserve `stable_id` and create new media placements referencing existing assets, never re-point a source version's placements.

---

## 5. Clone (Published → Draft, and Restore, and Apply-Industry-Layout — all share one function)

### 5.1 CURRENT STATE — unchanged factual trace

**Entry point:** `layout_service._clone_version_content(source, target)`

```python
target.header_config = dict(source.header_config or {})
target.footer_config = dict(source.footer_config or {})
target.appearance_config = dict(source.appearance_config or {})
target.save(...)
sections = [
    StorefrontSection(
        version=target, section_key=s.section_key, order=s.order,
        is_active=s.is_active, settings=dict(s.settings or {}),
    )
    for s in source.sections.order_by("order", "id")
]
StorefrontSection.objects.bulk_create(sections)
```

**What this clones correctly:** header/footer/appearance JSON config (full dict copy, no shared-reference bugs), and Section structure (key/order/active/settings — each field individually copied, brand-new PKs).

**What this does NOT clone — confirmed bug, Step 6 finding of the original audit:** `HeroSlide`, `PromotionalBanner`, `StoryRailItem` rows that are FK'd to a specific `StorefrontSection` instance. Because the new Draft's sections get new PKs, and the media models FK to the *old* section's PK, the new Draft's equivalent sections have zero scoped media immediately after cloning.

**Exact failure sequence (unchanged, still accurate as a description of today's code):**

```
[Published v1] --publish--> [ARCHIVED v1]
     Section A (pk=10) <---- HeroSlide "X" (section_id=10)
                                              |
[Draft v2 created via get_or_create_draft]    |  (old FK still points here — v1's Section A
     Section A' (pk=55, cloned from pk=10)    |   still exists, just archived, not deleted)
     <-- HeroSlide "X" does NOT follow -->  (still section_id=10, not 55)

Render of Draft v2's Section A' (pk=55):
  render_service._scoped_hero_slides(store, section=Section A' pk=55)
    -> HeroSlide.objects.filter(section_id=55, is_active=True)  => EMPTY
    -> falls back to HeroSlide.objects.filter(store=store, section__isnull=True, ...)
    -> shows legacy global slide (if any) or nothing — "X" is invisible
```

**Worse variant — actual data loss on discard/restore/apply-industry-layout (unchanged, still accurate):**

```
Merchant adds HeroSlide "Y" scoped to Draft v3's Section B (pk=60)
Merchant clicks "Discard Draft"
  -> layout_service.discard_draft(store) -> old_draft.delete()
  -> StorefrontLayoutVersion.delete() CASCADEs to StorefrontSection (on_delete=CASCADE)
  -> StorefrontSection.delete() CASCADEs to HeroSlide.section (on_delete=CASCADE)
  -> HeroSlide "Y" row is PERMANENTLY DELETED from the database
  -> its uploaded image file is NEVER cleaned up (no storage-cleanup hook on this path,
     unlike media_views.py's manual single-item delete which does clean up files)
```

**Confirmed absent test coverage (unchanged):** No test in `test_layout_service.py`, `test_media_views.py`, or `test_render_service.py` creates section-scoped media, then exercises a publish→re-draft (or discard, or restore) cycle to check whether the media survives.

**Evidence level: SOURCE_ONLY.** Traced precisely through source; not executed against a live Django runtime in any session so far (no Django available in the sandbox). Still not patched — this revision only changes the *proposed fix*, described next.

### 5.2 REJECTED fix (from the prior version of this plan — do not implement)

The original audit proposed fixing this by **remapping** the existing `HeroSlide`/`PromotionalBanner`/`StoryRailItem.section_id` from the old (Published) section's PK to point at the new (Draft) section's PK during clone. **The owner has explicitly rejected this approach (Owner Decision 4):** it would move the Published section's media reference into the Draft, leaving the live Published storefront's section with zero media the moment a merchant merely opens a Draft to edit something unrelated. This violates the fundamental guarantee that Published and Draft must be independently, simultaneously renderable.

### 5.3 OWNER-APPROVED TARGET ARCHITECTURE — the correct fix

Per Owner Decisions 3, 4, and 5, the corrected clone algorithm (not implemented yet) would look conceptually like:

```python
# Proposed shape — NOT IMPLEMENTED. For planning purposes only.
def _clone_version_content(source, target):
    target.header_config = dict(source.header_config or {})
    target.footer_config = dict(source.footer_config or {})
    target.appearance_config = dict(source.appearance_config or {})
    target.save(...)

    for source_page in source.pages.all():                       # NEW: iterate StorefrontPage
        target_page = StorefrontPage.objects.create(
            version=target, page_type=source_page.page_type,
        )
        section_pk_map = {}
        for s in source_page.sections.order_by("order", "id"):
            new_section = StorefrontSection.objects.create(
                page=target_page, section_key=s.section_key, order=s.order,
                is_active=s.is_active, settings=dict(s.settings or {}),
                stable_id=s.stable_id,                             # NEW: preserved, not regenerated
            )
            section_pk_map[s.pk] = new_section

            # NEW: for every media placement on the SOURCE section, create a
            # new placement on the CLONED section referencing the SAME asset.
            # The source (Published) placement is only ever read here, never
            # written to, never deleted, never re-pointed.
            for placement in s.hero_placements.all():
                HeroPlacement.objects.create(
                    section=new_section,
                    asset=placement.asset,          # same MediaAsset, shared reference
                    title=placement.title, subtitle=placement.subtitle,
                    button_label=placement.button_label, show_button=placement.show_button,
                    destination_type=placement.destination_type, ...,
                    display_order=placement.display_order, is_active=placement.is_active,
                )
            # ...identical pattern for banner/story-rail placements
```

**Why this satisfies all three owner decisions at once:**
- **Decision 3 (`stable_id`):** the cloned section keeps the same logical identity as its source, even though it has a new PK — `stable_id=s.stable_id` (copied, not regenerated).
- **Decision 4 (no re-homing):** the source `StorefrontSection`/placement rows are only ever *read* in this loop (`s.hero_placements.all()`), never mutated or deleted. The Published version remains exactly as rich in media after this runs as it was before.
- **Decision 5 (asset vs. placement):** a brand-new placement row is created for the target, but it points at the exact same `MediaAsset` (`asset=placement.asset`) rather than duplicating the underlying file. Deleting the new Draft placement later can never delete the shared `MediaAsset`, so the Published placement (which still points at the same asset) remains valid regardless of what happens to the Draft afterward.

**This is a proposal for future implementation, not a description of current code.** No part of §5.3 exists in the repository today.

### 5.4 Storage cleanup — target behavior

Under the target model, `old_draft.delete()` on Discard still CASCADE-deletes the Draft's own placement rows (that part of the CASCADE chain is fine — a placement without its section is meaningless), but it **cannot** reach `MediaAsset` rows, because the placement→asset FK must be `on_delete=PROTECT` (or `SET_NULL` with explicit handling), never `CASCADE`. This structurally prevents the "orphaned uploaded file with no cleanup" failure mode described in §5.1's worse variant — there is no longer any path by which discarding a Draft can delete a physical file that a Published (or any other) placement might still be using. See Implementation Plan §4.3/§4.4 for the full deletion-lifecycle and storage-cleanup design.

---

## 6. Validation (CURRENT STATE, unchanged by this revision)

- **Header/footer non-removable elements:** `layout_service.validate_header_config`/`validate_footer_config` enforce (at minimum) that the cart link and home link cannot both be hidden, and that the footer must retain at least one active column — validated at the service layer, not just the UI. `SOURCE_WITH_TEST_COVERAGE` per `test_views.py::HeaderFooterEditorTests` (cart-can't-be-hidden rule, footer-can't-be-fully-empty rule). Owner Decision 6 confirms these validations stay exactly where they are — Header/Footer remain Global Regions on the Version, not Pages or Sections, so this validation logic does not need to move.
- **Appearance config:** `layout_service.validate_appearance_config` rejects unknown `family_slug`/`template_slug`/`preset_slug` values and enforces that a chosen `preset_slug` actually belongs to the chosen `family_slug`.
- **Section settings:** each of the 22 registered section types has its own `validate_settings` callable in `section_registry.py` (allowlisted keys, clamped numeric ranges, Store-scoped reference checks for anything pointing at a Product/Category/Brand/Collection ID via the shared `_get_scoped_*` pattern).
- **Rate limiting:** `enforce_rate_limit` gates Draft creation and Publish (20/hour), reusing pre-existing shared infrastructure — no new rate-limiting mechanism needed for V2.

---

## 7. Scope limitation — this entire lifecycle is homepage-only today (CURRENT STATE unchanged; the open question it raised is now RESOLVED)

Every mechanism described in §1–§6 operates on `StorefrontLayoutVersion` → `StorefrontSection`, which is **implicitly a single, homepage-only page** per Store (`StorefrontLayout` is a 1:1 with `Store`, not a 1:many with a `page_type`/`page_slug` discriminator). The spec's "Page Template" concept (§5.3: Home, Product Detail, Product Listing, Collection, Search, Cart) does not exist as a data concept yet — those other page types are rendered by entirely separate views/templates that never touch `StorefrontSection` at all (see Route/Renderer Map document).

**This was flagged as the single most consequential open schema question in the prior version of this document. It is now resolved (Owner Decisions 1 and 2):** `StorefrontLayout` stays a `OneToOneField(Store)` — it does NOT become a `ForeignKey`. Instead, a new `StorefrontPage` model is introduced as a sibling layer sitting between `StorefrontLayoutVersion` and `StorefrontSection` (`StorefrontSection`'s FK target moves from the Version down to the Page). See §9 below and `STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` §1/§5 for the full target model and migration sequence.

---

## 8. Section-bound media — ownership model summary (CURRENT STATE, unchanged)

```
Store (1) ----FK---- HeroSlide/PromotionalBanner/StoryRailItem (store, nullable-legacy on 2 of 3)
                              |
                            FK (nullable) — "section=None" means legacy store-global
                              v
Store (1) --(1:1)-- StorefrontLayout --FK--> StorefrontLayoutVersion --FK--> StorefrontSection (1) <---FK--- HeroSlide/etc (section-scoped instance)
```

Media ownership is a genuine FK (not a JSON ID list embedded in `StorefrontSection.settings`) — confirmed via `render_service._scoped_hero_slides`/`_scoped_banners`/`_story_rail_context`, which query `Model.objects.filter(section=section, ...)` directly. This means the clone-lifecycle gap in §5 is a **real relational-integrity gap**, not a config-serialization gap — any fix must operate at the reference level (asset vs. placement, per §5.3/§9.2), not the JSON level.

---

## 9. OWNER-APPROVED TARGET ARCHITECTURE — Multi-page lifecycle and media asset/placement lifecycle (NEW, proposal only)

Nothing in this section is implemented. It records the target shape referenced throughout §5's revision and cross-references the full detail already written in `STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` (§1, §1.1, §3, §4) rather than duplicating it — this section exists so the Data/Lifecycle document remains a complete, self-contained trace of Draft/Preview/Publish/Rollback/Clone once V2 is built, without requiring a reader to cross-reference the Implementation Plan for the target shape of each lifecycle step.

### 9.1 Multi-page Draft/Publish/Rollback (target)

- **Draft** creation clones every `StorefrontPage` under the source version (not just a flat section list) — each source page produces one target page with the same `page_type`, and that target page's sections are cloned exactly as described in §5.3.
- **Publish** is unchanged in mechanism (pure pointer swap) — because a version already contains all of its pages, swapping `published_version`/`draft_version` inherently activates every page type at once. No per-page publish exists or is planned.
- **Rollback/Restore** shares the same multi-page-aware clone as Draft creation — restoring an old version restores every page type it contained, not just Home.
- **Public rendering** must, for every one of the six page types, only ever resolve content through `layout.published_version` — never through `layout.draft_version`, even for a store that currently has an in-progress Draft with different content. This is a direct carry-over of a guarantee the current homepage-only system already provides (confirmed in the original audit: the legacy/visual homepage branch only ever reads `published_version` for public requests) and must hold unchanged once extended to all six page types.

### 9.2 Media asset/placement lifecycle (target)

Full detail in Implementation Plan §4; summarized here for lifecycle-document completeness:

```
MediaAsset (store-scoped, physical file)
   ▲                                ▲
   │                                │
Published placement            Draft placement
(FK → Published StorefrontSection)  (FK → Draft StorefrontSection)
```

- A placement's `asset` FK is `on_delete=PROTECT` (never `CASCADE`) — deleting a placement's owning section/page/version cascades to the placement row itself, but never reaches the `MediaAsset`.
- Cloning (§5.3) creates a new placement referencing the same asset; it never moves or re-points an existing placement.
- An asset is only safe to delete once a reference-safety check (Implementation Plan §4.5) confirms zero placements reference it, across every version (Published, Draft, and any Archived versions still holding a reference).
