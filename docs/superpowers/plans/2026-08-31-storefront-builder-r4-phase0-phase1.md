# RastiSi R4 Phase 0 + Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the R4 storefront-builder architecture with one feature-gated editor shell, schema-driven settings, optimistic Draft concurrency, one shared Resource Picker contract, sparse local appearance override, and a real end-to-end Home-page vertical slice while preserving the existing renderer and Draft/Publish engine.

**Architecture:** R4 is a Strangler replacement for the R2/R3 editor layer only. It reuses `StorefrontLayout` / `StorefrontLayoutVersion`, `StorefrontPage`, `StorefrontSection`, `layout_service`, `container_service`, `edit_history_service`, `render_service`, the current Preview endpoint, Ready Templates, appearance registries, and existing Section/Variant contracts. New R4 code is additive and feature-gated; existing R3 routes remain operational and receive no new feature work.

**Tech Stack:** Django 5.2.x, Python 3.12, Django templates, existing Alpine.js/HTMX stack where useful, browser `fetch`, existing iframe Preview + `postMessage` bridge, Playwright/Chromium for focused browser smoke QA.

**Spec:** `docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md`

## Baseline

- R4 branch: `feature/storefront-builder-r4`
- Spec commit: `70ac7f72c82a8c1858ec541d88d762ece91c36f6`
- Parent architecture baseline: `37339c3d5c48304ca6b4a6047432802c3e9f81b3`
- Worktree on owner laptop: `D:\Projects\RastiSi4_R4`
- Existing R3 worktree must remain separate and untouched.

## Global Constraints

1. Do not rewrite `render_service.py`, the Draft/Published pointer model, Ready Template rendering, cart/checkout/inventory/order domains, or public storefront routing unless a failing architecture test proves that R4 cannot meet the Spec without a narrowly scoped change.
2. R3 is maintenance-only. Do not add new R3 UX, schema systems, variants, compatibility logic, or styling features.
3. R4 Phase 1 is Home-focused. Internal commerce pages remain controlled and are not turned into free-form builders.
4. No merchant HTML/CSS/JavaScript/raw-JSON escape hatch.
5. Every R4 mutation uses one optimistic Draft revision contract. Stale writes return HTTP 409 and do not mutate Draft state.
6. R4 Preview continues to use the existing shared renderer and existing `storefront_preview` endpoint.
7. Normal new Section Variants must not require a new View branch, save endpoint, modal, copied form template, JS save lifecycle, or validation pipeline.
8. The default Builder UI is simple. Inspector is closed on first load. Every editable component uses the same Basic/Advanced Inspector mental model.
9. Resource selection for Product/Brand in the vertical slice must use one shared component and one shared typed contract.
10. No full ~3300+ test suite during normal iteration. Every task below declares Level 1 and Level 2 checks. Level 3 is only for the Phase 1 architecture checkpoint.
11. Commit after every independently green task. Never force-push.
12. Before claiming a task complete, run `git diff --check` and the task's declared verification commands.

---

## File Structure Locked by This Plan

### New long-lived R4/domain files

- `apps/storefront_builder/settings_schema.py` — declarative settings-field/schema types, serialization and typed cleaning.
- `apps/storefront_builder/resource_source.py` — typed ResourceSource contract shared by Product/Brand/Category/Collection.
- `apps/storefront_builder/services/r4_mutation_service.py` — the only R4 Draft mutation transaction/concurrency boundary.
- `apps/storefront_builder/r4_views.py` — R4 editor/inspector/resource-picker/mutation HTTP endpoints. Keeps R4 request plumbing out of the already-large legacy `views.py`.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html` — one R4 shell.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/section_inspector.html` — Basic/Advanced Inspector shell generated from schema metadata.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html` — typed widget renderer.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/resource_picker.html` — one Product/Brand picker in Phase 1.
- `apps/storefront_builder/static/storefront_builder/r4_editor.js` — editor state, mutation queue, autosave, conflict handling, Preview bridge.
- `apps/storefront_builder/static/storefront_builder/r4_editor.css` — R4-only shell/Inspector styles. Do not pile R4 shell CSS into R3 styles.
- `tools/storefront_builder_r4_qa/run.mjs` — focused Playwright smoke suite.

### Existing files intentionally evolved

- `apps/storefront_builder/models.py` — additive feature-gate and Draft revision fields only.
- `apps/storefront_builder/section_registry.py` — optional `settings_schema` metadata and Phase 0/1 schema registrations; existing validators remain.
- `apps/storefront_builder/services/render_service.py` — only the smallest hook needed to expose effective section appearance to renderer context; no renderer rewrite.
- `apps/dashboard/urls.py` — R4 routes only.
- relevant Section templates for the vertical slice only when they must consume an effective appearance value.

### New focused tests

- `apps/storefront_builder/tests/test_r4_foundation.py`
- `apps/storefront_builder/tests/test_r4_settings_schema.py`
- `apps/storefront_builder/tests/test_r4_mutation_api.py`
- `apps/storefront_builder/tests/test_r4_inspector.py`
- `apps/storefront_builder/tests/test_r4_appearance_overrides.py`
- `apps/storefront_builder/tests/test_r4_resource_source.py`
- `apps/storefront_builder/tests/test_r4_resource_picker.py`
- `apps/storefront_builder/tests/test_r4_vertical_slice.py`

---

# Phase 0 — R4 Foundation Spike

## Task 1: Add R4 feature gate and optimistic Draft revision fields

**Files:**
- Modify: `apps/storefront_builder/models.py` — `StorefrontLayout`, `StorefrontLayoutVersion`
- Create: `apps/storefront_builder/migrations/0018_r4_editor_gate_and_edit_revision.py`
- Create: `apps/storefront_builder/tests/test_r4_foundation.py`

**Interfaces:**
- Produces: `StorefrontLayout.r4_editor_enabled: bool`
- Produces: `StorefrontLayoutVersion.edit_revision: int`
- Contract: existing rows default to `False` / `0`; existing R3 behavior is unchanged.

- [ ] **Step 1: Write failing model-contract tests**

```python
from django.test import TestCase

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion


class R4FoundationModelTests(TestCase):
    def test_r4_editor_is_disabled_by_default(self):
        field = StorefrontLayout._meta.get_field("r4_editor_enabled")
        self.assertFalse(field.default)

    def test_draft_edit_revision_starts_at_zero(self):
        field = StorefrontLayoutVersion._meta.get_field("edit_revision")
        self.assertEqual(field.default, 0)
```

- [ ] **Step 2: Run the focused test and prove RED**

Run:

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_foundation
```

Expected: FAIL because both fields are absent.

- [ ] **Step 3: Add the two additive model fields**

In `StorefrontLayout`:

```python
r4_editor_enabled = models.BooleanField(
    default=False,
    help_text="Feature gate for the R4 storefront-builder editor shell.",
)
```

In `StorefrontLayoutVersion`:

```python
edit_revision = models.PositiveBigIntegerField(
    default=0,
    help_text="Monotonic optimistic-concurrency token for Draft mutations.",
)
```

Do not alter `uses_visual_storefront_layout`, version status rules, `published_version`, or `draft_version` semantics.

- [ ] **Step 4: Create only migration 0018 and inspect it**

Run:

```powershell
python manage.py makemigrations storefront_builder --name r4_editor_gate_and_edit_revision
python manage.py makemigrations --check --dry-run
```

Expected migration operations: exactly two `AddField`s; no data migration and no unrelated model changes.

- [ ] **Step 5: Run Level 1 verification**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_foundation
python manage.py check
python manage.py makemigrations --check --dry-run
```

Expected: all green; no model drift.

- [ ] **Step 6: Run Level 2 compatibility checks**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_bootstrap_service `
  apps.storefront_builder.tests.test_admin_v22_live_builder `
  apps.storefront_builder.tests.test_phase7_family_retirement
```

Purpose: prove the additive fields did not change Draft bootstrap, current R3 entry, or the retired-registry contract.

- [ ] **Step 7: Verify diff and commit**

```powershell
git diff --check
git status --short
git add apps/storefront_builder/models.py apps/storefront_builder/migrations/0018_r4_editor_gate_and_edit_revision.py apps/storefront_builder/tests/test_r4_foundation.py
git commit -m "feat(storefront-builder): add R4 foundation state"
```

---

## Task 2: Add a feature-gated R4 shell that reuses the existing Preview

**Files:**
- Create: `apps/storefront_builder/r4_views.py`
- Modify: `apps/dashboard/urls.py`
- Create: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`
- Create: `apps/storefront_builder/static/storefront_builder/r4_editor.css`
- Create: `apps/storefront_builder/static/storefront_builder/r4_editor.js`
- Extend: `apps/storefront_builder/tests/test_r4_foundation.py`

**Interfaces:**
- Produces URL name: `dashboard:storefront-builder-r4-editor`
- Produces view: `r4_views.storefront_r4_editor(request)`
- Consumes existing URL: `dashboard:storefront-builder-preview`
- Gate: `StorefrontLayout.r4_editor_enabled is True`

- [ ] **Step 1: Write failing route/gate tests**

Add tests asserting:

```python
from django.urls import reverse


def test_r4_route_is_unavailable_when_gate_is_off(self):
    self.layout.r4_editor_enabled = False
    self.layout.save(update_fields=["r4_editor_enabled"])
    response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
    self.assertEqual(response.status_code, 404)


def test_r4_route_renders_one_shell_when_gate_is_on(self):
    self.layout.r4_editor_enabled = True
    self.layout.save(update_fields=["r4_editor_enabled"])
    response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'data-r4-shell="true"')
    self.assertContains(response, 'id="r4PreviewFrame"')
    self.assertContains(response, 'id="r4Inspector"')
    self.assertContains(response, 'data-r4-inspector-open="false"')
```

Use the same authenticated dashboard-store setup pattern already used by existing storefront-builder view tests; do not invent a second auth bypass.

- [ ] **Step 2: Prove RED**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_foundation
```

Expected: reverse/view/template failures.

- [ ] **Step 3: Implement the R4 read-only editor view**

Create `apps/storefront_builder/r4_views.py`:

```python
from django.http import Http404
from django.shortcuts import render

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from .models import StorefrontPage
from .services import container_service, layout_service


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_editor(request):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    draft = layout_service.get_or_create_draft(store, user=request.user)
    page = draft.get_page(StorefrontPage.PageType.HOME)
    container_service.ensure_page_containers(page)
    sections = page.sections.select_related("cell", "cell__container").order_by("order", "id")
    return render(
        request,
        "dashboard/storefront_builder/r4/editor.html",
        {
            "active_page": "storefront_builder",
            "layout": layout,
            "draft": draft,
            "page": page,
            "sections": sections,
            "r4_edit_revision": draft.edit_revision,
        },
    )
```

Do not call the R3 `storefront_editor` view and do not embed R3 editor markup.

- [ ] **Step 4: Add only the R4 editor route**

In `apps/dashboard/urls.py`, import `r4_views` and add:

```python
path(
    "storefront-builder/r4/",
    storefront_builder_r4_views.storefront_r4_editor,
    name="storefront-builder-r4-editor",
),
```

Do not modify the existing `storefront-builder/` route.

- [ ] **Step 5: Create one shell with Preview primary and Inspector closed**

`r4/editor.html` must include:

```html
<div class="r4-builder" data-r4-shell="true" data-r4-inspector-open="false"
     data-edit-revision="{{ r4_edit_revision }}">
  <header class="r4-topbar">
    <strong>طراحی فروشگاه</strong>
    <span id="r4SaveState" aria-live="polite">ذخیره شد</span>
    <button type="button" id="r4PublishButton">انتشار</button>
  </header>

  <main class="r4-workspace">
    <aside id="r4Structure" aria-label="ساختار صفحه"></aside>
    <section class="r4-preview-pane">
      <iframe
        id="r4PreviewFrame"
        title="پیش‌نمایش فروشگاه"
        src="{% url 'dashboard:storefront-builder-preview' %}?page=home">
      </iframe>
    </section>
    <aside id="r4Inspector" hidden aria-label="تنظیمات بخش"></aside>
  </main>
</div>
```

CSS must establish layout only. Do not copy the R3 modal styles.

- [ ] **Step 6: Add a minimal JS bootstrap with no mutation behavior yet**

`r4_editor.js` must expose one state object and not attach per-section save handlers:

```javascript
window.RastiSiR4 = {
  selected: null,
  revision: Number(document.querySelector('[data-r4-shell]')?.dataset.editRevision || 0),
  inspectorOpen: false,
  saveState: 'saved',
};
```

- [ ] **Step 7: Run Level 1 and Level 2 tests**

Level 1:

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_foundation
```

Level 2:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_admin_v22_live_builder `
  apps.storefront_builder.tests.test_builder_iframe_navigation_guard `
  apps.storefront_builder.tests.test_desktop_canvas_viewport
```

- [ ] **Step 8: Owner screenshot checkpoint A**

Enable R4 only on the QA store through Django shell, load `/admin-portal/storefront-builder/r4/`, and capture:

- `docs/qa_evidence/storefront_builder/r4/phase0/01_r4_shell_preview_closed_inspector.png`

Evidence must show Preview visible and Inspector closed. Do not evaluate detailed styling yet.

- [ ] **Step 9: Commit**

```powershell
git diff --check
git add apps/storefront_builder/r4_views.py apps/dashboard/urls.py apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html apps/storefront_builder/static/storefront_builder/r4_editor.css apps/storefront_builder/static/storefront_builder/r4_editor.js apps/storefront_builder/tests/test_r4_foundation.py docs/qa_evidence/storefront_builder/r4/phase0/01_r4_shell_preview_closed_inspector.png
git commit -m "feat(storefront-builder): add gated R4 editor shell"
```

---

## Task 3: Build the declarative Settings Schema core

**Files:**
- Create: `apps/storefront_builder/settings_schema.py`
- Modify: `apps/storefront_builder/section_registry.py` — `SectionDefinition`
- Create: `apps/storefront_builder/tests/test_r4_settings_schema.py`

**Interfaces:**
- Produces: `SettingsField`, `SettingsSchema`, `SettingsSchemaError`
- Produces: `clean_schema_patch(schema, raw_patch, current_settings) -> dict`
- Produces: `serialize_schema(schema) -> dict`
- Extends: `SectionDefinition.settings_schema: SettingsSchema | None`
- Legacy `validate_settings` remains authoritative fallback/post-validation.

- [ ] **Step 1: Write failing schema-contract tests**

Cover:

```python
from apps.storefront_builder.settings_schema import SettingsField, SettingsSchema, clean_schema_patch


def test_integer_field_accepts_persian_digits(self):
    schema = SettingsSchema(fields=(SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),))
    cleaned = clean_schema_patch(schema, {"item_limit": "۱۲"}, {})
    self.assertEqual(cleaned["item_limit"], 12)


def test_unknown_key_is_rejected(self):
    schema = SettingsSchema(fields=(SettingsField("title", "عنوان", "text", "basic"),))
    with self.assertRaisesMessage(ValueError, "Unknown settings key"):
        clean_schema_patch(schema, {"not_allowed": "x"}, {})


def test_patch_preserves_unmanaged_legacy_keys(self):
    schema = SettingsSchema(fields=(SettingsField("title", "عنوان", "text", "basic"),))
    cleaned = clean_schema_patch(schema, {"title": "جدید"}, {"title": "قدیم", "responsive": {"hide_on_mobile": False}})
    self.assertEqual(cleaned["responsive"], {"hide_on_mobile": False})
```

- [ ] **Step 2: Prove RED**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_settings_schema
```

- [ ] **Step 3: Implement immutable schema dataclasses**

Use a closed field-type set:

```python
ALLOWED_FIELD_TYPES = frozenset({
    "text", "textarea", "rich_text", "integer", "boolean", "choice",
    "color", "media", "variant", "resource_source", "appearance_override",
})
ALLOWED_GROUPS = frozenset({"basic", "advanced"})
```

`SettingsField` must include at minimum:

```python
@dataclasses.dataclass(frozen=True)
class SettingsField:
    key: str
    label: str
    field_type: str
    group: str
    default: object = None
    required: bool = False
    choices: tuple[tuple[str, str], ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    max_length: int | None = None
    widget_hint: str | None = None
```

`SettingsSchema`:

```python
@dataclasses.dataclass(frozen=True)
class SettingsSchema:
    fields: tuple[SettingsField, ...]
    preserve_unmanaged: bool = True
```

Normalize tuples in `__post_init__`, reject duplicate field keys, invalid field types, invalid groups, and unbounded arbitrary code-like field types.

- [ ] **Step 4: Implement digit normalization centrally**

```python
_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(value: object) -> str:
    return str(value).translate(_DIGIT_TRANSLATION)
```

Every integer cleaning path uses this helper; the browser may normalize for UX, but server correctness cannot depend on browser behavior.

- [ ] **Step 5: Implement patch semantics**

`clean_schema_patch` must:

1. reject patch keys not declared in the schema;
2. clean only declared patch keys;
3. merge cleaned keys into `current_settings` when `preserve_unmanaged=True`;
4. never accept raw HTML/CSS/JS/JSON field types;
5. return a complete merged settings dict suitable for the existing validator.

- [ ] **Step 6: Extend `SectionDefinition` additively**

Add:

```python
settings_schema: SettingsSchema | None = None
```

Import `SettingsSchema` from `.settings_schema`. Do not remove `validate_settings` or `default_settings`.

- [ ] **Step 7: Level 1 and Level 2**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_settings_schema
python manage.py test `
  apps.storefront_builder.tests.test_section_registry `
  apps.storefront_builder.tests.test_u1b2_capability_metadata_wiring
```

- [ ] **Step 8: Commit**

```powershell
git diff --check
git add apps/storefront_builder/settings_schema.py apps/storefront_builder/section_registry.py apps/storefront_builder/tests/test_r4_settings_schema.py
git commit -m "feat(storefront-builder): add declarative settings schema"
```

---

## Task 4: Register schemas for Rich Text and Hero without deleting legacy validators

**Files:**
- Modify: `apps/storefront_builder/section_registry.py`
- Extend: `apps/storefront_builder/tests/test_r4_settings_schema.py`

**Interfaces:**
- `rich_text.settings_schema` handles `body_html`.
- `hero_banner.settings_schema` handles only the existing high-level slider keys in Phase 0.
- Existing wrapped responsive/layout/motion/background keys survive via `preserve_unmanaged=True` and legacy validator post-validation.

- [ ] **Step 1: Write failing registry tests**

Assert:

```python
rich_text = section_registry.get_definition("rich_text")
self.assertIsNotNone(rich_text.settings_schema)
self.assertEqual([f.key for f in rich_text.settings_schema.fields], ["body_html"])

hero = section_registry.get_definition("hero_banner")
self.assertIsNotNone(hero.settings_schema)
self.assertIn("hero_style", {f.key for f in hero.settings_schema.fields})
self.assertIn("interval_ms", {f.key for f in hero.settings_schema.fields})
```

- [ ] **Step 2: Define the Rich Text schema**

```python
RICH_TEXT_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        key="body_html",
        label="متن",
        field_type="rich_text",
        group="basic",
        default="",
        max_length=_MAX_RICH_TEXT_LENGTH,
        widget_hint="merchant_rich_text",
    ),
))
```

The existing sanitizer/render behavior remains unchanged.

- [ ] **Step 3: Define only the existing Hero high-level keys**

```python
HERO_BANNER_SCHEMA = SettingsSchema(fields=(
    SettingsField("hero_style", "مدل نمایش", "choice", "basic", default="overlay", choices=tuple((x, x) for x in HERO_STYLE_CHOICES)),
    SettingsField("autoplay", "پخش خودکار", "boolean", "basic", default=True),
    SettingsField("interval_ms", "فاصله اسلاید", "integer", "advanced", default=4500, min_value=2000, max_value=10000),
    SettingsField("show_arrows", "نمایش فلش‌ها", "boolean", "advanced", default=True),
    SettingsField("show_dots", "نمایش نقاط", "boolean", "advanced", default=True),
    SettingsField("loop", "تکرار", "boolean", "advanced", default=True),
    SettingsField("text_position", "جای متن", "choice", "advanced", default="end", choices=(("start", "ابتدا"), ("center", "وسط"), ("end", "انتها"))),
))
```

Do not schema-migrate HeroSlide CRUD itself in Phase 0.

- [ ] **Step 4: Add a bridge cleaner used by R4 only**

In `settings_schema.py`:

```python
def clean_section_schema_patch(definition, raw_patch, current_settings):
    if definition.settings_schema is None:
        raise SettingsSchemaError("Section is not schema-enabled")
    merged = clean_schema_patch(definition.settings_schema, raw_patch, current_settings)
    return definition.validate_settings(merged)
```

This is the Strangler boundary: R4 uses schema first, then the existing validator. R3 remains unchanged.

- [ ] **Step 5: Prove legacy wrapped settings survive**

Test a Hero settings dict containing `responsive` or `motion`, patch only `autoplay`, then assert the legacy block survives and the existing validator still accepts the full merged result.

- [ ] **Step 6: Verification and commit**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_settings_schema
python manage.py test apps.storefront_builder.tests.test_section_registry
git diff --check
git add apps/storefront_builder/section_registry.py apps/storefront_builder/settings_schema.py apps/storefront_builder/tests/test_r4_settings_schema.py
git commit -m "feat(storefront-builder): register first R4 section schemas"
```

---

## Task 5: Implement the single optimistic R4 mutation boundary

**Files:**
- Create: `apps/storefront_builder/services/r4_mutation_service.py`
- Modify: `apps/storefront_builder/r4_views.py`
- Modify: `apps/dashboard/urls.py`
- Create: `apps/storefront_builder/tests/test_r4_mutation_api.py`

**Interfaces:**
- Produces endpoint: `dashboard:storefront-builder-r4-mutation`
- Request JSON:

```json
{
  "base_revision": 3,
  "mutation": {
    "type": "section.update_settings",
    "section_id": 42,
    "patch": {"autoplay": false}
  }
}
```

- Success JSON: `{"ok": true, "new_revision": 4, "mutation_type": "section.update_settings"}`
- Conflict: HTTP 409 with `{"ok": false, "code": "stale_revision", "current_revision": 4}`

- [ ] **Step 1: Write RED tests for success, tenant scoping, and conflict**

Tests must prove:

1. correct `base_revision` mutates a schema-enabled Draft section and increments revision once;
2. stale `base_revision` returns 409 and section settings remain unchanged;
3. section IDs belonging to another Store are rejected;
4. published versions cannot be mutated;
5. existing R3 section-settings POST does not start requiring `base_revision`.

- [ ] **Step 2: Implement explicit service exceptions**

```python
class R4MutationError(ValueError):
    pass


class R4StaleRevision(R4MutationError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("stale_revision")
```

- [ ] **Step 3: Implement one transactional mutation function**

```python
@transaction.atomic
def apply_mutation(*, store, actor, base_revision: int, mutation: dict) -> int:
    layout = StorefrontLayout.objects.select_for_update().get(store=store)
    draft = StorefrontLayoutVersion.objects.select_for_update().get(
        pk=layout.draft_version_id,
        layout=layout,
        status=StorefrontLayoutVersion.Status.DRAFT,
    )
    if draft.edit_revision != base_revision:
        raise R4StaleRevision(draft.edit_revision)

    before_state = edit_history_service.snapshot_draft(draft)
    _dispatch_mutation(store=store, draft=draft, mutation=mutation)
    draft.edit_revision += 1
    draft.save(update_fields=["edit_revision"])
    edit_history_service.record_change(
        draft=draft,
        actor=actor,
        action_label=_history_label(mutation),
        before_state=before_state,
    )
    return draft.edit_revision
```

The only Phase 0 dispatcher operation is `section.update_settings`. Unknown mutation types return a controlled 400, not dynamic imports/eval.

- [ ] **Step 4: Implement schema-driven section update**

Scope the section through the locked Draft:

```python
section = StorefrontSection.objects.select_for_update().get(
    pk=section_id,
    page__version=draft,
)
definition = section_registry.get_definition(section.section_key)
cleaned = clean_section_schema_patch(definition, patch, section.settings or {})
section.settings = cleaned
section.save(update_fields=["settings"])
```

Do not call the legacy R3 view internally.

- [ ] **Step 5: Add JSON endpoint in `r4_views.py`**

Use `@require_POST`, existing `staff_required`/permission decorators, strict JSON-object validation, and map `R4StaleRevision` to HTTP 409.

- [ ] **Step 6: Run Level 1 and Level 2**

Level 1:

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_mutation_api
```

Level 2:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_settings_schema `
  apps.storefront_builder.tests.test_acceptance_batch1 `
  apps.storefront_builder.tests.test_acceptance_batch2
```

- [ ] **Step 7: Commit**

```powershell
git diff --check
git add apps/storefront_builder/services/r4_mutation_service.py apps/storefront_builder/r4_views.py apps/dashboard/urls.py apps/storefront_builder/tests/test_r4_mutation_api.py
git commit -m "feat(storefront-builder): add optimistic R4 mutation API"
```

---

## Task 6: Render one schema-driven Basic/Advanced Inspector and wire Preview selection

**Files:**
- Modify: `apps/storefront_builder/r4_views.py`
- Modify: `apps/dashboard/urls.py`
- Create: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/section_inspector.html`
- Create: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html`
- Modify: `apps/storefront_builder/static/storefront_builder/r4_editor.js`
- Create: `apps/storefront_builder/tests/test_r4_inspector.py`

**Interfaces:**
- Produces GET: `dashboard:storefront-builder-r4-section-inspector`, path `storefront-builder/r4/sections/<int:pk>/inspector/`
- Consumes existing Preview `postMessage` event `sfb:selectSection`.
- Inspector mutation always goes through Task 5 endpoint.

- [ ] **Step 1: Write RED inspector tests**

For a schema-enabled `rich_text` and `hero_banner`, assert:

- Basic tab exists;
- Advanced tab exists;
- fields render from schema metadata;
- no R3 form action is present;
- no nested iframe exists;
- no inline section-specific save endpoint exists.

- [ ] **Step 2: Implement inspector context**

The GET view must resolve the active Draft, scope the section to it, require `definition.settings_schema`, and pass:

```python
{
    "section": section,
    "definition": definition,
    "basic_fields": tuple(f for f in schema.fields if f.group == "basic"),
    "advanced_fields": tuple(f for f in schema.fields if f.group == "advanced"),
}
```

- [ ] **Step 3: Implement typed widget partial**

Phase 0 widgets are only:

- `text`
- `rich_text`
- `integer` with `inputmode="numeric"`
- `boolean`
- `choice`

Any unsupported type raises a developer-visible template/contract error in tests; do not silently render a free text box.

- [ ] **Step 4: Wire Preview click to Inspector open**

In `r4_editor.js`:

```javascript
window.addEventListener('message', async (event) => {
  const data = event.data || {};
  if (data.type !== 'sfb:selectSection' || !data.sectionId) return;
  await RastiSiR4.openSection(Number(data.sectionId));
});
```

`openSection` fetches the R4 inspector URL, injects only into `#r4Inspector`, unhides it, and updates one selected-section state. It must not open a modal.

- [ ] **Step 5: Implement one serialized mutation queue**

All Inspector field changes call one function:

```javascript
RastiSiR4.enqueueMutation = function(mutation) {
  this.queue = (this.queue || Promise.resolve()).then(() => this.sendMutation(mutation));
  return this.queue;
};
```

`sendMutation` posts JSON with the current `this.revision`. On 200 it replaces `this.revision`; on 409 it sets save state to `conflict`, stops automatic retries, and offers a reload action. Never silently replay stale form state.

- [ ] **Step 6: Implement Basic/Advanced tabs only**

Default tab: Basic. Advanced remains one click away. Do not add extra nested accordions in Phase 0.

- [ ] **Step 7: Level 1/2 + screenshot checkpoint B**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_inspector `
  apps.storefront_builder.tests.test_r4_mutation_api
```

Level 2:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_admin_v22_live_builder `
  apps.storefront_builder.tests.test_r3_simple_live_editor `
  apps.storefront_builder.tests.test_section_registry
```

Capture:

- `02_rich_text_basic_inspector.png`
- `03_hero_advanced_inspector.png`

Owner must confirm the interaction direction before Phase 1 continues.

- [ ] **Step 8: Commit**

Commit only after screenshots and tests are green.

---

# Phase 1 — Architecture Vertical Slice

## Task 7: Add sparse per-section appearance overrides and prove Hero typography inheritance

**Files:**
- Extend: `apps/storefront_builder/settings_schema.py`
- Create: `apps/storefront_builder/services/section_appearance_service.py`
- Modify: `apps/storefront_builder/services/render_service.py` only to expose the resolved value in render context/items
- Modify: the existing `hero_banner` renderer template root only as needed to consume CSS variables
- Extend: `apps/storefront_builder/section_registry.py` Hero schema
- Create: `apps/storefront_builder/tests/test_r4_appearance_overrides.py`

**Interfaces:**
- Stored shape:

```json
{
  "appearance_overrides": {
    "typography": {
      "enabled": true,
      "font": "...",
      "type_scale": "..."
    }
  }
}
```

- Inheritance rule: absent/disabled override means use global `appearance_config` unchanged.

- [ ] **Step 1: Write RED pure tests for sparse inheritance**

Test:

```python
resolved = resolve_section_appearance(global_appearance, {})
self.assertEqual(resolved["font"], global_appearance["font"])

resolved = resolve_section_appearance(global_appearance, {
    "appearance_overrides": {"typography": {"enabled": True, "font": "custom-font"}}
})
self.assertEqual(resolved["font"], "custom-font")
self.assertEqual(resolved["palette_slug"], global_appearance["palette_slug"])
```

- [ ] **Step 2: Implement only typed allowlisted typography override keys**

Allow `font` and `type_scale` initially. Reject arbitrary style/CSS keys. Add one shared `validate_appearance_overrides(raw) -> dict` plus a `_with_appearance_overrides(section_key, validate_fn, default_fn)` wrapper in `section_registry.py`, following the existing `_with_responsive` / `_with_motion` wrapper pattern. Apply it only to schema-enabled sections that explicitly support appearance overrides. This is required so the legacy validator does not silently drop the new `appearance_overrides` block when it returns its cleaned dict.

Persisted shape for the first slice:

```python
{
    "appearance_overrides": {
        "typography": {
            "enabled": True,
            "font": "vazirmatn",
            "type_scale": "compact",
        }
    }
}
```

The wrapper must preserve the exact current settings contract when the block is absent.

- [ ] **Step 3: Add an `appearance_override` schema field to Hero Advanced**

The widget renders typed select controls sourced from existing appearance registries, not a JSON textarea.

- [ ] **Step 4: Pass effective section appearance through the existing renderer**

Do not fork Preview/Public rendering. Both must receive the same effective result because both call the shared renderer.

- [ ] **Step 5: Add a renderer assertion**

Test that global font is used with no override and only Hero receives the override when enabled; a sibling section remains global.

- [ ] **Step 6: Run Level 1/2 and commit**

Level 1:

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_appearance_overrides
```

Level 2:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_appearance `
  apps.storefront_builder.tests.test_u1b1_variant_runtime_wiring `
  apps.storefront_builder.tests.test_ready_template_real_previews
```

Do not run full visual capture here unless the focused Hero screenshot changes.

---

## Task 8: Add semantic R4 mutations for add/remove/duplicate/reorder

**Files:**
- Modify: `apps/storefront_builder/services/r4_mutation_service.py`
- Modify: `apps/storefront_builder/static/storefront_builder/r4_editor.js`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`
- Create/extend: `apps/storefront_builder/tests/test_r4_vertical_slice.py`

**Interfaces:**
- Add mutation types:
  - `section.add`
  - `section.remove`
  - `section.duplicate`
  - `section.move`
- These delegate to existing service functions; R4 does not reimplement ordering/domain rules.

- [ ] **Step 1: Write RED tests for one revision per semantic operation**

For each mutation, assert:

- operation succeeds on current revision;
- revision increments exactly once;
- existing min/max/duplicable/removable/locked rules remain enforced;
- stale replay returns 409.

- [ ] **Step 2: Delegate to existing domain services**

Do not copy logic from old Views. `_dispatch_mutation` should call the same underlying section/container/row service used by existing endpoints wherever such service exists.

- [ ] **Step 3: Add a simple structure list and controls**

R4 structure panel may display existing Home sections with:

- select
- move up/down
- duplicate when allowed
- hide/remove as permitted
- add section button

Drag-and-drop can be added only if it uses the same `section.move` mutation. Buttons remain available as deterministic fallback.

- [ ] **Step 4: Preview refresh strategy**

After a successful structural mutation, reload the existing Preview iframe. Do not introduce a second renderer or client-side fake DOM renderer.

- [ ] **Step 5: Level 1/2 and commit**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_vertical_slice
python manage.py test `
  apps.storefront_builder.tests.test_acceptance_batch1 `
  apps.storefront_builder.tests.test_phase30_container_cell_foundation `
  apps.storefront_builder.tests.test_phase31_container_cell_builder `
  apps.storefront_builder.tests.test_row_service `
  apps.storefront_builder.tests.test_section_registry
```

---

## Task 9: Define one ResourceSource contract shared by Product and Brand

**Files:**
- Create: `apps/storefront_builder/resource_source.py`
- Create: `apps/storefront_builder/tests/test_r4_resource_source.py`
- Modify: `apps/storefront_builder/section_registry.py` schemas for `product_section` and `brand_carousel`

**Interfaces:**

```python
@dataclasses.dataclass(frozen=True)
class ResourceSource:
    kind: str
    mode: str
    auto_rule: str | None = None
    auto_parameters: Mapping[str, object] = dataclasses.field(default_factory=dict)
    manual_ids: tuple[int, ...] = ()
```

Kinds: `product`, `category`, `brand`, `collection`.
Modes: `auto`, `manual`.

- [ ] **Step 1: Write RED pure contract tests**

Prove:

- invalid kind/mode rejected;
- IDs are positive, deduplicated while preserving order;
- max-items enforced;
- Product auto rules may include `newest`, `discounted`, `best_sellers`, `most_viewed`, `by_category`, `by_brand`, `by_collection`;
- Brand auto rules remain limited to rules the current system can actually resolve;
- serialization round-trips.

- [ ] **Step 2: Implement no database access in the dataclass module**

Ownership/query resolution belongs to services/views. `resource_source.py` is a typed validation/serialization contract only.

- [ ] **Step 3: Map existing Product/Brand persisted settings without data migration**

R4 adapts the current settings shape to/from `ResourceSource` in a compatibility adapter. Do not rename persisted keys for existing stores in Phase 1.

For Product, preserve current `data_source`, `source_id`, `product_ids`.
For Brand, preserve current `brand_ids`; auto mode remains empty IDs/current behavior.

- [ ] **Step 4: Register R4 schema fields**

Product Basic must expose:

- title
- source (`resource_source`)
- item_limit
- display/variant choice
- relevant safe show/hide controls already supported

Brand Basic must expose:

- title
- source (`resource_source`)
- display/variant choice
- relevant existing show/hide controls

Do not remove their current validators.

- [ ] **Step 5: Level 1/2 and commit**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_resource_source
python manage.py test `
  apps.storefront_builder.tests.test_universal_selection_pattern `
  apps.storefront_builder.tests.test_section_registry
```

---

## Task 10: Build one R4 Resource Picker for Product and Brand

**Files:**
- Modify: `apps/storefront_builder/r4_views.py`
- Modify: `apps/dashboard/urls.py`
- Create: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/resource_picker.html`
- Modify: `apps/storefront_builder/static/storefront_builder/r4_editor.js`
- Create: `apps/storefront_builder/tests/test_r4_resource_picker.py`

**Interfaces:**
- One picker endpoint accepts an allowlisted `kind` and search query.
- One UI component receives `kind`, `mode`, ordered IDs, max items.
- Picker returns a typed `ResourceSource` result to the active Inspector. It never saves the Section itself.

- [ ] **Step 1: Write RED ownership and shared-template tests**

Prove Product and Brand search:

- use the same R4 picker template;
- never return another Store's resources;
- manual selection preserves order;
- max-items is enforced server-side;
- picker HTML has no Section save form/action.

- [ ] **Step 2: Implement a small resolver map, not four editor lifecycles**

Example boundary:

```python
RESOURCE_SEARCHERS = {
    "product": _search_products,
    "brand": _search_brands,
}
```

Phase 1 only exposes Product and Brand through the UI. The contract already supports Category/Collection for Phase 2.

- [ ] **Step 3: Implement Builder-owned overlay**

The overlay is visually above R4 but remains in the same page. No iframe and no admin CRUD page.

- [ ] **Step 4: Return selection to Inspector and autosave through mutation queue**

The picker emits one result object. Inspector converts it through the compatibility adapter and enqueues `section.update_settings`. There is still exactly one mutation API.

- [ ] **Step 5: Level 1/2 + screenshot checkpoint C**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_resource_picker `
  apps.storefront_builder.tests.test_r4_resource_source
```

Level 2:

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_universal_selection_pattern `
  apps.storefront_builder.tests.test_u1b1_variant_runtime_wiring
```

Screenshots:

- `04_product_resource_picker_manual.png`
- `05_brand_resource_picker_manual.png`

Owner must verify both clearly look/behave like the same control.

- [ ] **Step 6: Commit**

Commit after browser evidence.

---

## Task 11: Wire Global Design, Header/Footer selection, Undo/Redo and Publish into the single shell

**Files:**
- Modify: `apps/storefront_builder/r4_views.py`
- Modify: `apps/storefront_builder/services/r4_mutation_service.py`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`
- Modify: `apps/storefront_builder/static/storefront_builder/r4_editor.js`
- Extend: `apps/storefront_builder/tests/test_r4_vertical_slice.py`

**Interfaces:**
- Global Design reuses `appearance_registry` and existing persisted `appearance_config`.
- Header/Footer options reuse `global_region_registry`.
- Undo/Redo reuse `edit_history_service`.
- Publish reuses `layout_service.publish` but R4 publish request must include current Draft revision and reject stale publish state.

- [ ] **Step 1: Write RED tests for no duplicated domain behavior**

Tests assert the R4 endpoints call existing domain services and do not create separate published data or separate Header/Footer models.

- [ ] **Step 2: Add mutation types only where semantic Draft editing is required**

Add allowlisted operations:

- `appearance.update`
- `header.update`
- `footer.update`

All remain under the same revision lock and increment.

Undo/Redo may use dedicated R4 wrappers around existing service commands but must return the current `edit_revision`; after a successful Undo/Redo, increment or otherwise rebase the revision monotonically so stale clients cannot overwrite restored state.

- [ ] **Step 3: Add stale-aware Publish wrapper**

Request:

```json
{"base_revision": 12}
```

Server locks/reads the active Draft, rejects mismatch with 409, validates/publishes through existing `layout_service.publish`, and returns success. Do not recreate publish copying logic.

- [ ] **Step 4: Keep Global Design separate from section Inspector**

R4 top-level navigation may open Global Design in the same Inspector area, but Section overrides remain inside the selected Section Advanced tab.

- [ ] **Step 5: Run Level 1/2**

```powershell
python manage.py test apps.storefront_builder.tests.test_r4_vertical_slice
python manage.py test `
  apps.storefront_builder.tests.test_appearance `
  apps.storefront_builder.tests.test_phase27_history_identity `
  apps.storefront_builder.tests.test_u2a_global_header_system `
  apps.storefront_builder.tests.test_u2b_global_footer_system `
  apps.storefront_builder.tests.test_layout_service `
  apps.storefront_builder.tests.test_acceptance_batch3
```

- [ ] **Step 6: Commit**

Commit only after focused Preview/Public rendering comparisons confirm no public renderer fork.

---

## Task 12: Add deterministic Playwright smoke QA for the full vertical slice

**Files:**
- Create: `tools/storefront_builder_r4_qa/run.mjs`
- Create: `docs/qa_evidence/storefront_builder/r4/phase1/` screenshots from the run
- Extend: `apps/storefront_builder/tests/test_r4_vertical_slice.py` only for server contracts not browser behavior

**Interfaces:**
- Script accepts base URL and authenticated QA strategy already used by existing builder QA tooling.
- Script must fail non-zero on console errors, failed saves, conflict contract failure, missing persistence, or navigation away from R4.

- [ ] **Step 1: Implement these exact browser scenarios**

1. Open R4 Home Builder; Inspector is closed.
2. Click Hero in Preview; one Inspector opens.
3. Change a Basic Hero setting; autosave reaches `Saved`; reload and prove persistence.
4. Open Advanced; enable Hero typography override; reload and prove only Hero override persists.
5. Add a Product section; reorder it.
6. Open Product; choose auto source and valid Persian-digit count; save/persist.
7. Open Product Resource Picker; choose manual products; reorder selection; persist.
8. Open Brand; use the same picker UI/contract; persist.
9. Undo one semantic operation; Redo it.
10. Force a stale mutation using an old `base_revision`; prove HTTP 409 and UI `Conflict`, with no silent overwrite.
11. Resolve conflict by reload; continue editing normally.
12. Publish; open public storefront separately; prove published state matches intended Draft.
13. Make one new Draft-only change; prove public storefront does not change until next Publish.

- [ ] **Step 2: Capture required screenshots**

Save:

- `01_r4_initial.png`
- `02_hero_basic.png`
- `03_hero_advanced_typography_override.png`
- `04_product_added_reordered.png`
- `05_product_manual_picker.png`
- `06_brand_manual_picker.png`
- `07_conflict_detected.png`
- `08_publish_success.png`
- `09_public_storefront_after_publish.png`
- `10_draft_changed_public_unchanged.png`

- [ ] **Step 3: Browser console/network assertions**

Fail the script on:

- uncaught page errors;
- `console.error` attributable to R4;
- any R4 mutation response outside expected 2xx/409 contract;
- full-page navigation caused by Inspector save;
- nested iframe creation inside the Inspector/Resource Picker.

- [ ] **Step 4: Level 1/2 automated tests before browser run**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_foundation `
  apps.storefront_builder.tests.test_r4_settings_schema `
  apps.storefront_builder.tests.test_r4_mutation_api `
  apps.storefront_builder.tests.test_r4_inspector `
  apps.storefront_builder.tests.test_r4_appearance_overrides `
  apps.storefront_builder.tests.test_r4_resource_source `
  apps.storefront_builder.tests.test_r4_resource_picker `
  apps.storefront_builder.tests.test_r4_vertical_slice
```

Then run a relevant neighboring Level 2 set only.

- [ ] **Step 5: Run Playwright smoke and owner review checkpoint D**

Use the same real QA store and media root already used for Storefront Builder manual QA. Owner reviews the 10 screenshots before the architecture gate is declared PASS.

- [ ] **Step 6: Commit smoke tooling and evidence**

```powershell
git diff --check
git add tools/storefront_builder_r4_qa/run.mjs docs/qa_evidence/storefront_builder/r4/phase1 apps/storefront_builder/tests/test_r4_vertical_slice.py
git commit -m "test(storefront-builder): prove R4 vertical slice in browser"
```

---

## Task 13: Phase 1 architecture gate and checkpoint verification

**Files:**
- No feature code unless verification reveals a concrete failing contract.
- Update this plan/checkpoint notes only if a real discrepancy is found.

**PASS criteria — all must be true:**

1. R4 uses the existing Draft/Published and renderer infrastructure.
2. One R4 shell only; R2/R3 markup is not embedded inside it.
3. Rich Text and Hero settings are schema-driven.
4. Normal settings save goes through one mutation endpoint/service.
5. Product and Brand use the same Resource Picker component/contract.
6. Add/remove/duplicate/reorder use the same revisioned mutation boundary.
7. Hero typography override is sparse and does not mutate global appearance or sibling sections.
8. Preview and public storefront still share the existing renderer.
9. Stale `base_revision` is rejected with 409; no silent overwrite.
10. Public storefront changes only on Publish.
11. No normal R4 flow opens an admin iframe or second save lifecycle.
12. Focused Playwright smoke passes with evidence.
13. R3 routes still work for non-R4 stores.
14. `git diff --check`, `manage.py check`, and migration drift checks are clean.

- [ ] **Step 1: Run final Phase 1 focused/neighboring verification**

Do not immediately run all 3300+ tests. First run all R4 tests plus directly touched subsystem suites.

- [ ] **Step 2: Decide whether Level 3 full suite is justified**

A Level 3 run is justified here because this is the end of the Phase 1 architecture checkpoint and touches shared Draft mutation, Section metadata, appearance resolution, and publish wrappers. Run it once, after all focused/browser checks are already green.

Record exact counts and pre-existing unrelated failures separately; do not repeatedly rerun the full suite for a one-line follow-up unless the follow-up changes shared architecture.

- [ ] **Step 3: Final Git evidence**

```powershell
git status --short
git diff --check
git log --oneline --decorate -15
python manage.py check
python manage.py makemigrations --check --dry-run
```

- [ ] **Step 4: Produce the Phase 1 gate report**

Create:

`docs/qa_evidence/storefront_builder/r4/PHASE1_ARCHITECTURE_GATE.md`

It must contain:

- exact HEAD;
- task commit list;
- Level 1/2/3 test commands and counts;
- Playwright result;
- screenshot paths;
- PASS/FAIL table for all 14 criteria;
- remaining known issues;
- explicit recommendation: proceed to Phase 2 or revise architecture.

- [ ] **Step 5: Commit the gate report**

```powershell
git add docs/qa_evidence/storefront_builder/r4/PHASE1_ARCHITECTURE_GATE.md
git commit -m "docs(storefront-builder): record R4 Phase 1 architecture gate"
```

Stop after this commit. Do **not** start Phase 2 Product/Category/Brand/Collection family migration until the product owner reviews the gate report and screenshots.

---

# Implementation Review Checklist

Before execution begins, the implementer must confirm:

- [ ] current branch is `feature/storefront-builder-r4`
- [ ] current HEAD includes spec commit `70ac7f7`
- [ ] worktree is clean
- [ ] R3 repair worktree is not being used
- [ ] `python manage.py check` passes
- [ ] `python manage.py makemigrations --check --dry-run` passes
- [ ] no full suite is started before a task requires it

# Owner Review Checkpoints

1. **Checkpoint A — Shell:** Preview-first R4 shell, Inspector closed.
2. **Checkpoint B — Inspector:** clicking Preview opens one Basic/Advanced Inspector; no modal chain.
3. **Checkpoint C — Resource Picker:** Product and Brand visibly share the same picker.
4. **Checkpoint D — Vertical slice:** 10 Playwright evidence screenshots + conflict + Publish proof.
5. **Architecture Gate:** owner reviews `PHASE1_ARCHITECTURE_GATE.md` before Phase 2.

# Explicit Out-of-Scope for This Plan

- Building the full 50-template library.
- Migrating Category/Collection Resource Picker UI beyond defining the shared contract.
- Mega Menu presets.
- Full compatibility/recommendation engine.
- Full responsive-contract enforcement across every existing Variant.
- R3 deletion/cleanup.
- Multiple simultaneous Drafts.
- Free-form internal-page builder.
- Render caching.
- Custom merchant code.

