# Storefront Builder V2 — Data / Lifecycle Map

**Phase:** Audit checkpoint. Documentation only. All evidence `SOURCE_ONLY` unless marked `TESTED` (test file read, not executed — see sandbox constraint in `STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md` §0).

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

All of the above executes inside a single `transaction.atomic()` block. Evidence: SOURCE_ONLY, cross-checked by two independent context-gatherer passes this session; `TESTED` per `test_layout_service.py::GetOrCreateDraftTests`.

---

## 2. Preview

**Entry point:** `apps/storefront_builder/views.py::storefront_preview` (staff-only, `@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)`, `@xframe_options_sameorigin` because it's embedded in the editor's own iframe).

- Calls `render_service.build_render_items(draft_version, store)` — **the exact same function** the public `home()` view calls for the published version. This is the mechanism that satisfies the spec's "Preview and Public must use the same rendering pipeline" requirement (§9) — but **only for the homepage today** (see §7 "Scope limitation").
- Supports a non-persistent, in-memory "candidate" preview: `?preview_template=<slug>` / `?preview_family=<slug>` query params build a throwaway `_CandidateAppearanceVersion` object (never written to the DB) so a merchant can preview a different Template/Family without touching the real Draft.
- No shareable link/token exists — session-based, staff-of-this-store only, by explicit design (documented in the view's own comments, referencing an "Owner Decision #11").
- Evidence: SOURCE_ONLY / TESTED (`test_views.py::EditorAccessTests`, `RenderedPreviewIntegrationTests`, `test_page_shell.py`).

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

Publish is a **pure pointer swap** — no content is copied at publish time (content was already fully formed on the Draft). This means a failed/partial publish can never leave the live storefront in a half-updated state — the only mutation is a small set of FK/flag fields inside one atomic transaction. Evidence: SOURCE_ONLY / TESTED (`test_layout_service.py::PublishTests`, `test_views.py::PublishDiscardRestoreViewTests::test_publish_redirects_and_sets_flag`).

---

## 4. Rollback

**Entry point:** `layout_service.restore_version(store, version_id, *, user=None)`

- Looks up the target version, **fails closed** (`CrossStoreVersionError`) if it belongs to a different store or doesn't exist.
- **Never publishes directly.** Always creates a **new Draft** (`source=RESTORED`) via `_clone_version_content(target_version, new_draft)` — the merchant must explicitly Preview and Publish the restored draft, exactly like any other edit. This is stricter/safer than the spec's minimum bar (spec §9 only requires "Merchant can restore an earlier published version," doesn't mandate the extra Draft step) — worth preserving, not weakening.
- Evidence: SOURCE_ONLY / TESTED (`test_layout_service.py::RestoreVersionTests::test_restore_clones_source_sections`, `test_views.py::PublishDiscardRestoreViewTests::test_restore_creates_draft_not_publish`, `test_restore_cross_store_returns_404`).

---

## 5. Clone (Published → Draft, and Restore, and Apply-Industry-Layout — all share one function)

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

**What this does NOT clone — confirmed bug, Step 6 finding:** `HeroSlide`, `PromotionalBanner`, `StoryRailItem` rows that are FK'd to a specific `StorefrontSection` instance. Because the new Draft's sections get new PKs, and the media models FK to the *old* section's PK, the new Draft's equivalent sections have zero scoped media immediately after cloning.

**Exact failure sequence:**

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

**Worse variant — actual data loss on discard/restore/apply-industry-layout:**

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

**Confirmed absent test coverage:** No test in `test_layout_service.py`, `test_media_views.py`, or `test_render_service.py` creates section-scoped media, then exercises a publish→re-draft (or discard, or restore) cycle to check whether the media survives. This was confirmed by direct inspection of every relevant test file's body, not just by their names.

**Evidence level: SOURCE_ONLY.** Traced precisely through source; not executed against a live Django runtime this session (no Django available in the sandbox). This is reported per the task's explicit Step 6 instruction to document, not silently patch, this exact failure mode.

---

## 6. Validation

- **Header/footer non-removable elements:** `layout_service.validate_header_config`/`validate_footer_config` enforce (at minimum) that the cart link and home link cannot both be hidden, and that the footer must retain at least one active column — validated at the service layer, not just the UI. `TESTED` per `test_views.py::HeaderFooterEditorTests` (cart-can't-be-hidden rule, footer-can't-be-fully-empty rule).
- **Appearance config:** `layout_service.validate_appearance_config` rejects unknown `family_slug`/`template_slug`/`preset_slug` values and enforces that a chosen `preset_slug` actually belongs to the chosen `family_slug`.
- **Section settings:** each of the 22 registered section types has its own `validate_settings` callable in `section_registry.py` (allowlisted keys, clamped numeric ranges, Store-scoped reference checks for anything pointing at a Product/Category/Brand/Collection ID via the shared `_get_scoped_*` pattern).
- **Rate limiting:** `enforce_rate_limit` gates Draft creation and Publish (20/hour), reusing pre-existing shared infrastructure — no new rate-limiting mechanism needed for V2.

---

## 7. Scope limitation — this entire lifecycle is homepage-only today

Every mechanism described in §1–§6 operates on `StorefrontLayoutVersion` → `StorefrontSection`, which is **implicitly a single, homepage-only page** per Store (`StorefrontLayout` is a 1:1 with `Store`, not a 1:many with a `page_type`/`page_slug` discriminator). The spec's "Page Template" concept (§5.3: Home, Product Detail, Product Listing, Collection, Search, Cart) does not exist as a data concept yet — those other page types are rendered by entirely separate views/templates that never touch `StorefrontSection` at all (see Route/Renderer Map document).

This is the single most consequential schema question for V2 Phase 1 planning: **does extending this lifecycle to other page types mean adding a `page_type` discriminator to the existing `StorefrontLayout`/`StorefrontLayoutVersion` (turning the 1:1 Store relationship into a 1:many), or does it require a new sibling model (`StorefrontPage`) sitting between `StorefrontLayout` and `StorefrontSection`?** Both are schema-level changes; neither has been decided or implemented today. See the Implementation Plan document §"Page concept" for a non-binding recommendation.

---

## 8. Section-bound media — ownership model summary (for lifecycle context)

```
Store (1) ----FK---- HeroSlide/PromotionalBanner/StoryRailItem (store, nullable-legacy on 2 of 3)
                              |
                            FK (nullable) — "section=None" means legacy store-global
                              v
Store (1) --(1:1)-- StorefrontLayout --FK--> StorefrontLayoutVersion --FK--> StorefrontSection (1) <---FK--- HeroSlide/etc (section-scoped instance)
```

Media ownership is a genuine FK (not a JSON ID list embedded in `StorefrontSection.settings`) — confirmed via `render_service._scoped_hero_slides`/`_scoped_banners`/`_story_rail_context`, which query `Model.objects.filter(section=section, ...)` directly. This means the clone-lifecycle gap in §5 is a **real relational-integrity gap**, not a config-serialization gap — any fix must operate at the FK-remapping level, not the JSON level.
