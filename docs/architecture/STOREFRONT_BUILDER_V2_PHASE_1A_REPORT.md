# Storefront Builder V2 — Phase 1A (Universal Page Architecture) Implementation Report

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit for this phase:** `4b6d110de12e822247d1dc65364dc208dd7aa720`
**Status:** Implemented, **NOT executed against a live Django runtime** in this sandbox. Awaiting the owner's local test run before this phase is considered verified — exactly the same posture as Phase 0.5.

This phase introduces `StorefrontPage` beneath `StorefrontLayoutVersion`, per the owner's locked decisions. It does **not** build the single-screen Builder UI, does **not** build Presets, and does **not** redesign the 11 legacy Families.

---

## 0. Evidence-level note

Same discipline as the Phase 0.5 report: `SOURCE_ONLY` / `SOURCE_WITH_TEST_COVERAGE` / `RUNTIME_VERIFIED` / `BROWSER_VERIFIED`. Everything in this report is `SOURCE_ONLY` or `SOURCE_WITH_TEST_COVERAGE` — no Django runtime was available in this sandbox this session (re-confirmed: no PyPI access, no cached wheel). Nothing here is claimed as `RUNTIME_VERIFIED`.

---

## 1. Files changed

### Models
- `apps/storefront_builder/models.py` — added `StorefrontPage` (new model); changed `StorefrontSection.page` to be the sole database FK (replacing the direct `version` FK); added a `version` read-only `@property` and a `version=` constructor-kwarg compatibility shim on `StorefrontSection`; added `StorefrontLayoutVersion.home_page()` and an aggregating `.sections` `@property`; added `StorefrontLayoutVersion.save()` override that calls `StorefrontPage.ensure_version_pages()` on first save; updated `compute_fingerprint()` to hash across all pages.

### Services
- `apps/storefront_builder/services/layout_service.py` — rewrote `_clone_version_content()` to iterate every source page, clone each page's sections onto the matching target page (matched by `page_type`), and clone section-scoped media per-page (unchanged Phase 0.5 guarantees, just looped per page now).
- `apps/storefront_builder/services/bootstrap_service.py` — `apply_bootstrap_content`, `apply_industry_content`, `apply_family_default_sections` all now explicitly target `version.home_page()` rather than the version directly.
- `apps/storefront_builder/services/render_service.py` — `build_render_items(version, store)` now explicitly resolves `version.home_page()` internally; signature unchanged (per the owner's own note that this is the correct minimal-diff shape).

### Views
- `apps/storefront_builder/views.py` — `_get_scoped_section` (the tenant/draft-scoping guard used by every section-mutation endpoint and `media_views.py`) now filters via `page__version__layout__store`/`page__version__status` instead of `version__layout__store`/`version__status`. `storefront_section_add`, `storefront_section_duplicate`, `storefront_section_reorder`, `storefront_section_move`, `storefront_editor`, `storefront_section_list_partial`, and `storefront_appearance_editor`'s family-switch confirmation check were all updated to operate on `draft.home_page().sections`/`section.page.sections` rather than the version directly.

### Migrations (6, in the exact sequence the owner specified)
See §5 below.

### Tests (all new; see §12 for execution status)
- `apps/storefront_builder/tests/test_storefront_page.py`
- `apps/storefront_builder/tests/test_page_backfill_migration.py`

### Tests updated (pre-existing files, minimal targeted edits only)
- `apps/storefront_builder/tests/test_stable_section_identity.py` — one docstring clarification; no assertion logic changed (both sections in the affected test resolve to the same home page, so the test's outcome is unaffected).
- `apps/storefront_builder/tests/test_media_asset_lifecycle.py` — 4 queryset lookup chains (`section__version__...` → `section__page__version__...`) updated to match the one-level-deeper FK chain; no assertion logic changed.
- `apps/storefront_builder/tests/test_stable_id_migration.py` — 1 queryset lookup chain (`.filter(version=...)` → `.filter(page__version=...)`) updated in one test's assertions; a docstring note added.
- `apps/storefront_builder/tests/test_bootstrap_service.py` — 1 explanatory comment added (no code change — the aggregating `.sections` property already produces the correct result here).

**No other test file needed changes.** ~178 pre-existing `StorefrontSection.objects.create(version=..., ...)` call sites across `test_render_service.py`, `test_views.py`, `test_models.py`, `test_responsive_rendering.py`, `test_public_homepage_integration.py`, `test_layout_service.py`, `test_media_views.py`, `test_media_write_path.py`, `test_family_default_section_reset.py`, `test_family_heritage_premium.py`, and `test_media_asset_lifecycle.py` (the remaining, non-lookup ones) all continue to work unmodified, because the `version=` constructor kwarg is still accepted (see §4).

### Documentation
- This file (new).
- No other architecture document required correction — the Implementation Plan document already described exactly this target shape; this report implements it and does not need to revise it.

---

## 2. Compatibility blocker investigation (per the owner's explicit instruction to STOP and report rather than force a removal)

The owner's brief explicitly required: *"If you discover a concrete compatibility blocker that makes removing `section.version` unsafe in this phase, STOP and report the blocker rather than creating an ambiguous permanent dual-ownership model."*

**Investigation performed:** a dedicated context-gathering pass inventoried every production code site (4 files: `models.py`, `layout_service.py`, `bootstrap_service.py`, `views.py`) and every test file (13 files, ~178+ call sites) that constructs a `StorefrontSection` or reads `.version`/`version_id`/`.sections` on it or its parent. Full findings are in §1 above and §4 below.

**Conclusion: no blocker was found that makes removing the physical `version` column unsafe.** The database column is genuinely removed (migration `0010`, see §5) — there is exactly **one** ownership source in the schema (`page_id`). What *was* found is a **volume** risk, not a **safety** risk: ~178 pre-existing test call sites use the `StorefrontSection(version=X, ...)` constructor pattern, and none of them could be executed in this sandbox to verify a mass rewrite. Rather than either (a) leaving a second real database column (which the owner explicitly forbade) or (b) blindly rewriting ~178 call sites across 13 files with no way to run them afterward, this report's approach is:

- The **database schema** has exactly one ownership column (`page_id`) — `version` is removed at the schema level in migration `0010`.
- The **Python model class** provides a constructor-level convenience shim (`StorefrontSection(version=X, ...)` resolves `X`'s home page and passes it through as `page=`) and a read-only `@property` (`section.version` returns `self.page.version`). This is **not** a second database column and **not** a second source of truth — it is a Python-level convenience so that the large body of pre-existing test code (written before this phase, exercising real, valuable regression coverage) continues to exercise the same behavior without requiring a blind, unverifiable mass edit in a sandbox that cannot run the result.
- All **production code** (the only code that matters for actual runtime correctness and the only code an owner or future engineer would reasonably audit for "is there dual ownership here") was updated to use `page=`/`.page` directly — never `version=`/`.version` — with exactly one exception: nothing, there is no exception; every production call site was migrated (see §4's inventory table).

This is reported explicitly rather than silently done, per the instruction. If the owner considers even this Python-level shim unacceptable, the alternative is a mechanical rewrite of all ~178 test call sites — the report recommends this only be attempted in an environment where the result can actually be executed and verified, given the volume involved.

---

## 3. Final model hierarchy

```
Store
 └── StorefrontLayout (unchanged: OneToOneField(Store))
      ├── published_version
      └── draft_version
            └── StorefrontLayoutVersion
                 ├── header_config / footer_config / appearance_config (unchanged — Global Regions)
                 ├── save() override -> StorefrontPage.ensure_version_pages() on first save
                 ├── home_page() -> explicit accessor for new code
                 ├── .sections (aggregating property, all six pages — legacy-test-compat only)
                 └── pages (NEW, related_name="pages")
                      └── StorefrontPage  [UniqueConstraint(version, page_type)]
                           ├── page_type: home | product_detail | listing | collection | search | cart
                           └── sections (related_name="sections")
                                └── StorefrontSection  [UniqueConstraint(page, stable_id)]
                                     ├── page (FK, sole DB ownership column)
                                     ├── version (read-only @property -> self.page.version)
                                     └── __init__(version=...) constructor shim -> resolves to page=
```

---

## 4. Final StorefrontSection ownership model

| Aspect | Before Phase 1A | After Phase 1A |
|---|---|---|
| Database FK | `version` → `StorefrontLayoutVersion` | `page` → `StorefrontPage` (sole column) |
| `related_name` | `version.sections` | `page.sections` |
| Python `.version` access | direct field | read-only `@property`, derived (`self.page.version`) |
| Constructor `version=` kwarg | the field itself | accepted by `__init__`, resolved to `page=version.pages.get(page_type=HOME)` |
| Uniqueness scope for `stable_id` | `(version, stable_id)` | `(page, stable_id)` |

**Full production call-site inventory** (all updated in this commit):

| File | Call site | Before | After |
|---|---|---|---|
| `layout_service.py` | `_clone_version_content` | `StorefrontSection(version=target, ...)`, `source.sections`, `target.sections` | Per-page loop: `StorefrontSection(page=target_page, ...)`, `source_page.sections`, `target_page.sections` |
| `bootstrap_service.py` | `apply_bootstrap_content` | `StorefrontSection(version=version, ...)` | `StorefrontSection(page=home_page, ...)` where `home_page = version.home_page()` |
| `bootstrap_service.py` | `apply_industry_content` | same | same pattern |
| `bootstrap_service.py` | `apply_family_default_sections` | `version.sections.all().delete()`, `StorefrontSection(version=version, ...)` | `home_page.sections.all().delete()`, `StorefrontSection(page=home_page, ...)` |
| `render_service.py` | `build_render_items` | `version.sections.filter(...)` | `version.home_page().sections.filter(...)` |
| `models.py` | `StorefrontLayoutVersion.compute_fingerprint` | `self.sections.order_by(...)` (flat) | `self.sections.select_related("page").order_by("page__page_type", "order", "id")` (all pages, deterministic order) |
| `views.py` | `_get_scoped_section` | `version__layout__store`, `version__status` | `page__version__layout__store`, `page__version__status` |
| `views.py` | `storefront_section_add` | `draft.sections.*`, `StorefrontSection(version=draft, ...)` | `draft.home_page().sections.*`, `StorefrontSection(page=home_page, ...)` |
| `views.py` | `storefront_section_duplicate` | `section.version.sections.*`, `StorefrontSection(version=section.version, ...)` | `section.page.sections.*`, `StorefrontSection(page=section.page, ...)` |
| `views.py` | `storefront_section_reorder` | `draft.sections.values_list(...)`, `.filter(pk=..., version=draft)` | `home_page.sections.values_list(...)`, `.filter(pk=..., page=home_page)` |
| `views.py` | `storefront_section_move` | `section.version.sections.*` | `section.page.sections.*` |
| `views.py` | `storefront_editor` / `storefront_section_list_partial` | `draft.sections.*` | `draft.home_page().sections.*` |
| `views.py` | `storefront_appearance_editor` (family-switch confirm check) | `draft.sections.exists()` | `draft.home_page().sections.exists()` |

`media_views.py` and `section_data_service.py` required **zero** changes — confirmed by direct inspection, neither file touches `StorefrontSection`/`StorefrontLayoutVersion`/`.sections`/`.version` at all; they only ever receive an already-resolved `section`/`store` object from `views.py`.

---

## 5. Migration sequence (exact, as implemented)

Six migrations, each single-purpose per the owner's instruction:

| # | File | Purpose | Data touched |
|---|---|---|---|
| 1 | `0005_storefrontpage.py` | `CreateModel(StorefrontPage)` + `UniqueConstraint(version, page_type)` | None — new, empty table |
| 2 | `0006_ensure_pages_for_existing_versions.py` | Data migration: create the six `StorefrontPage` rows for **every** existing `StorefrontLayoutVersion` (Draft, Published, **and** Archived) | Creates new `StorefrontPage` rows only |
| 3 | `0007_storefrontsection_page.py` | `AddField(page, null=True)` — **no default**, same discipline as the Phase 0.5 repair | None — every row starts `NULL` |
| 4 | `0008_backfill_section_page.py` | Data migration: every existing `StorefrontSection` with `page IS NULL` gets `page_id` set to its version's `home` page | Sets `page_id` only; touches no other field |
| 5 | `0009_storefrontsection_page_not_null_and_stable_id_scope.py` | `RemoveConstraint(unique_stable_id_per_version)` → `AlterField(page, not-null)` → `AlterField(stable_id, extended help_text)` → `AddConstraint(unique_stable_id_per_page)` | None — schema/constraint only |
| 6 | `0010_remove_storefrontsection_version.py` | `RemoveField(version)` | Drops the now-unused column |

**Why step 2 (page creation) happens for Archived versions too:** the owner's brief explicitly required this ("This includes: Draft, Published, Archived... Historical versions must remain internally complete enough for Restore"). `0006` iterates `StorefrontLayoutVersion.objects.all()` with no status filter.

**Why the `page` AddField in `0007` has no default:** direct application of the exact lesson from the Phase 0.5 repair — a callable/static default on a nullable `AddField` risks SQLite's table-rebuild strategy applying it to every pre-existing row during the rebuild itself, defeating a later per-row backfill. `0007`'s field has `null=True` and no `default=` at all; `0008` is the only thing that ever assigns `page_id` to a pre-existing row. A dedicated static test (`SectionPageAddFieldHasNoDefaultTests` in `test_page_backfill_migration.py`) checks this directly against the migration's own `Migration.operations` list, mirroring the Phase 0.5 repair's `MigrationOperationOrderTests` pattern.

**Migration-state precision:** the `page` field's final `AlterField` (in `0009`) and the `StorefrontPage` model's fields (in `0005`) were verified byte-for-byte against the live model declarations in `apps/storefront_builder/models.py` (not just visually) before being committed — the same discipline the Phase 0.5 repair required, applied proactively here to avoid recreating that exact class of bug. `stable_id`'s extended help_text (Phase 1A adds a sentence explaining the new page-scoped uniqueness) is deliberately given its **own** `AlterField` in `0009` rather than silently rewritten into the already-applied Phase 0.5 migration `0004` — this is a genuine, deliberate model change for this phase, not an accidental metadata drift, so it gets its own migration entry.

---

## 6. StorefrontPage schema (final)

```python
class StorefrontPage(TimeStampedModel):
    class PageType(models.TextChoices):
        HOME = "home", "صفحه اصلی"
        PRODUCT_DETAIL = "product_detail", "جزئیات محصول"
        LISTING = "listing", "لیست محصولات"
        COLLECTION = "collection", "کالکشن"
        SEARCH = "search", "نتایج جستجو"
        CART = "cart", "سبد خرید"

    version = models.ForeignKey(StorefrontLayoutVersion, on_delete=models.CASCADE, related_name="pages")
    page_type = models.CharField(max_length=20, choices=PageType.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "page_type"], name="storefront_page_unique_type_per_version")]

    @classmethod
    def ensure_version_pages(cls, version) -> None:
        # idempotent: creates only the page_types missing for this version
        ...
```

`ensure_version_pages` is the single centralized page-creation function, per the owner's explicit instruction ("Centralize this behavior. Do NOT scatter page-creation logic across views"). It is called automatically from `StorefrontLayoutVersion.save()` on first save (`is_new = self.pk is None`), which means **every** code path that creates a new version — the official `layout_service.get_or_create_draft`/`restore_version`/`apply_industry_layout`, any test that calls `StorefrontLayoutVersion.objects.create(...)` directly, and any future code that does the same — automatically gets all six pages, with no possibility of a call site "forgetting" to invoke a separate helper. `ensure_version_pages` is itself idempotent (`bulk_create(..., ignore_conflicts=True)` plus a pre-check of existing `page_type`s), so calling it redundantly is always safe.

---

## 7. Version clone algorithm (final)

`_clone_version_content(source, target)`:

1. Copies `header_config`/`footer_config`/`appearance_config` (unchanged).
2. Builds `target_pages_by_type = {p.page_type: p for p in target.pages.all()}` — these six pages already exist because `target` was just created via `StorefrontLayoutVersion.objects.create(...)`, which triggered `save()` → `ensure_version_pages()`.
3. For **every** `source_page` in `source.pages.all()` (all six, not just home):
   - Looks up the matching `target_page` by `page_type`.
   - Clones that page's sections (preserving `stable_id`, exactly as Phase 0.5 established) onto `target_page`.
   - Clones section-scoped media placements for those sections (unchanged Phase 0.5 guarantees: new placement rows, same `MediaAsset` references, source placements never mutated).
4. Pages with zero sections (currently every non-home page, since the Builder UI only edits home) end up with zero sections on the target too — no synthetic content invented, per the owner's explicit "Empty Commerce Pages" instruction.

---

## 8. Publish / Restore / Discard behavior

- **Publish** (`layout_service.publish`) — **unchanged mechanism**. Still a pure pointer-swap (`layout.published_version = draft`). Because a version now owns all six pages via the `pages` relation, this single pointer-swap **atomically** activates every page's content at once — there is no `published_home`/`published_product`/`published_cart` field anywhere (confirmed by a dedicated test, `test_publish_is_a_single_pointer_swap_not_a_per_page_operation`, which inspects `StorefrontLayout._meta.get_fields()` directly).
- **Restore** (`layout_service.restore_version`) — unchanged mechanism (creates a new Draft via `_clone_version_content`), now inherits the multi-page-aware clone automatically since it shares the same function. Restoring an old version recreates all six pages and their compositions.
- **Discard** (`layout_service.discard_draft`) — unchanged mechanism (`draft.delete()`). CASCADE now flows `StorefrontLayoutVersion → StorefrontPage (CASCADE) → StorefrontSection (CASCADE) → media placements (Phase 0.5's PROTECT-on-asset guarantee unchanged)`. Discarding a Draft removes only that Draft's own pages/sections/placements; the Published version's pages/sections/assets are never reachable from this CASCADE chain (they belong to a different `StorefrontLayoutVersion` row entirely) — verified by `test_discard_removes_only_draft_pages_keeps_published_intact`.

---

## 9. Tenant isolation approach

`StorefrontPage` ownership resolves transitively: `StorefrontPage → StorefrontLayoutVersion → StorefrontLayout → Store`. No new direct `store` FK was added to `StorefrontPage` or `StorefrontSection` — this mirrors the existing pattern already used for `StorefrontSection`'s old `version → layout → store` chain (never a direct `store` FK on the section itself), so no new class of tenant-scoping bug is introduced.

The one production code path that enforces this boundary at the query level is `_get_scoped_section` (`views.py`), updated to filter via `page__version__layout__store=store` — one hop deeper than before, same store-scoping guarantee. `test_get_scoped_section_rejects_a_section_belonging_to_another_store` (in `test_storefront_page.py`) directly exercises this through the real view layer (a POST to `storefront-builder-section-toggle` for a section belonging to a different store, asserting `404`).

---

## 10. Renderer API changes

**`render_service.build_render_items(version, store)` — signature unchanged**, per the owner's explicit preference for "an explicit page-aware contract" without needing to touch either of its two production callers (`apps/catalog/views.py::home()`, `apps/storefront_builder/views.py::storefront_preview()`). Internally, it now calls `version.home_page()` explicitly (not the aggregating `.sections` property) — this is the "explicit page-aware contract" requirement satisfied at the one call site that actually renders content, while the external signature stays exactly what both existing callers already pass.

**No second render engine, no six unrelated render pipelines were created** — there remains exactly one `SECTION_REGISTRY`, one `_CONTEXT_BUILDERS` dict, one `build_render_items` function. Extending rendering to non-home pages (a Phase 1B/Phase 2 concern) would mean this same function gaining a `page_type` parameter or a sibling function reusing the same `_CONTEXT_BUILDERS`/registry — not a parallel system.

---

## 11. Legacy compatibility / public routes

- No public route's rendering behavior changes as a result of this phase. `catalog/views.py::home()` still calls `build_render_items(published, store)` exactly as before; the function's externally observable behavior (which sections render, in what order, with what content) is byte-for-byte identical to before this phase for any store that has only ever used the home page (i.e., every existing store, since Phase 1A introduces no new UI for editing the other five pages).
- The 11 legacy Families were not touched — `family_registry.py`, `preset_registry.py`, `appearance_registry.py` have zero references to `StorefrontSection`/`.version`/`.page` (confirmed by direct grep — only docstring comments mention `StorefrontSection` by name, no executable code path).
- Commerce logic (`apps/cart`, `apps/orders`) was not touched.
- No `StorefrontPage`-specific Family model or renderer was introduced — `StorefrontPage` is a generic, family-agnostic container; nothing about it is family-specific.

---

## 12. Tests added and their execution status

**Added, all NOT EXECUTED in this sandbox** (no Django runtime — same constraint as every prior checkpoint):

- `test_storefront_page.py` — Parts A (model), E (multi-page sections), F (stable_id page-scoped uniqueness), G (duplicate stays on same page), H (publish activates complete page set atomically, and there is no per-page publish pointer), I (restore recreates all six pages), J (discard doesn't damage published pages), K (tenant isolation, including a real view-layer 404 check).
- `test_page_backfill_migration.py` — Part B (migration/backfill): a static check that migration `0007`'s `AddField` has no default (mirroring the Phase 0.5 repair's own regression test pattern); direct exercise of migration `0008`'s actual backfill function against constructed scenarios; and an end-to-end proof (via the current, already-integrated model/service code) that a version with multiple sections ends up with all of them correctly on `home`, ordering/settings/is_active/stable_id preserved, no section lost, and the other five pages confirmed empty.

**Updated** (targeted lookup-chain fixes only, no new test scenarios): `test_stable_section_identity.py`, `test_media_asset_lifecycle.py`, `test_stable_id_migration.py`, `test_bootstrap_service.py` — see §1 for the exact diffs.

**Verification performed without execution:** every new/changed queryset lookup chain (`page__version__...`, `page__version=`) and every migration's field declaration were checked by direct source inspection against the live model declarations — the same "read it back carefully" discipline used throughout Phase 0.5, but this is explicitly **not** a substitute for running `python manage.py test` and `python manage.py makemigrations --check --dry-run` locally.

---

## 13. Exact local validation commands

```bash
python manage.py check

python manage.py makemigrations --check --dry-run
# ^ must report "No changes detected" — confirms all six new/altered
#   migrations exactly match the final model state (page field, stable_id
#   help_text, StorefrontPage fields/constraint).

python manage.py migrate
# ^ full graph, including the six new storefront_builder migrations
#   (0005-0010) on top of the already-applied Phase 0.5 state
#   (content 0019-0021, storefront_builder 0004).

python manage.py test \
  apps.storefront_builder.tests.test_layout_service \
  apps.storefront_builder.tests.test_render_service \
  apps.storefront_builder.tests.test_media_views \
  apps.storefront_builder.tests.test_page_shell \
  apps.storefront_builder.tests.test_public_homepage_integration \
  apps.storefront_builder.tests.test_views \
  --verbosity 2
# ^ the original 220-test baseline — must remain fully green, same shape
#   (220 pass / 1 skip / 0 fail / 0 error) as before this phase, since no
#   observable behavior of these routes/tests should have changed.

python manage.py test \
  apps.storefront_builder.tests.test_stable_section_identity \
  apps.storefront_builder.tests.test_media_asset_lifecycle \
  apps.storefront_builder.tests.test_media_write_path \
  apps.storefront_builder.tests.test_stable_id_migration \
  apps.storefront_builder.tests.test_storefront_page \
  apps.storefront_builder.tests.test_page_backfill_migration \
  --verbosity 2
# ^ the full Phase 0.5 + Phase 1A test suite.

python manage.py test apps.storefront_builder --verbosity 2
# ^ the ENTIRE storefront_builder app test suite (all family/section/
#   bootstrap/appearance/registry tests not explicitly listed above) —
#   the strongest possible confirmation that nothing outside this
#   phase's direct scope regressed.

python manage.py test apps.content apps.dashboard --verbosity 2
# ^ confirm no cross-app regression (content models/migrations, dashboard
#   views that route into storefront_builder).
```

---

## 14. Remaining Phase 1B work

Per the Implementation Plan's locked roadmap, everything below remains explicitly out of scope for this checkpoint:

- **The single-screen Builder UI** (Phase 2) — page selector, block library, live canvas, inspector for the five non-home page types. Phase 1A only establishes the data model; the existing editor UI still only edits the home page (unchanged).
- **Home Block Library refinement** (Phase 3).
- **Header/Footer Composer** (Phase 4) — `header_config`/`footer_config` remain flat toggle JSON on `StorefrontLayoutVersion`, unchanged; the structured Rows/Blocks evolution described in the Implementation Plan §6 was not started.
- **Commerce Page Composition** (Phase 5) — the five non-home `StorefrontPage`s exist and participate correctly in the version lifecycle (clone/publish/restore/discard), but have zero editable sections and zero rendering wiring into the actual public Product Detail/Listing/Collection/Search/Cart routes. Wiring those routes to read from their corresponding `StorefrontPage` (once they have real content) is Phase 1B/5 work, not done here.
- **Presets** (Phase 6).
- **Legacy Family migration/retirement** (Phase 7).
- **Route/shell consistency work** — the Route/Renderer Map document's finding (only `home_visual.html`/`preview.html` share the Family-aware shell) is completely unaddressed by this phase, exactly as intended — Phase 1A was data/domain architecture only, not rendering-shell unification.

**Immediate technical debt flagged for whoever picks up Phase 1B:** the `version=` constructor-kwarg compatibility shim on `StorefrontSection` (§2) should be revisited once the ~178 pre-existing test call sites can actually be run and, ideally, mechanically rewritten to use `page=` directly — at which point the shim could be removed entirely, leaving `StorefrontSection.__init__` with no special-casing. This was explicitly reported as a volume-risk decision, not silently deferred.
