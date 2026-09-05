# Storefront Appearance Phase 1 — Architecture & Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge Storefront Appearance write ownership so legacy/R4/template paths preserve unrelated state, Ready Template application produces `declared = persisted = effective` appearance DNA, and explicit local Section variant overrides can coexist safely with Store-level defaults.

**Architecture:** Reuse the existing StorefrontLayoutVersion, typed Store Appearance manifest, preset service, R4 mutation boundary, registries, and shared renderer. Introduce one focused authority service for appearance-state transformations; legacy and R4 entry points delegate to it instead of reconstructing overlapping state independently. Preserve current behavior for existing sections by making local-variant override intent explicit rather than globally flipping precedence for historical rows.

**Tech Stack:** Python 3.12, Django 5.2, Django TestCase/SimpleTestCase, existing Storefront Builder registries/services, PostgreSQL/SQLite-compatible Django ORM, PowerShell-compatible test commands.

**Spec:** `docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md`

## Global Constraints

- Code baseline for this plan: `93c5afea2ee32bef67cfb5923ffdb13bb61d7930`.
- The implementation branch MUST be created from `origin/docs/storefront-appearance-convergence` after verifying that branch is a documentation-only descendant of the approved code baseline. The executor's current `main` branch is irrelevant and MUST NOT be merged into Phase 1.
- Phase scope is **Phase 1 — Architecture & Authority only**.
- Preserve Products, Brands, Categories, Collections, pricing, stock, Cart, Orders, Auth, tenant/store authorization, and existing shared render engine.
- Do not create a second Preview/Public renderer.
- Do not add new component variants or Template 51+.
- Do not delete legacy routes in this phase.
- Normal precedence is `Template DNA → Store Global → Page → Section/Component`.
- Store-level force/lock behavior is out of scope unless represented explicitly; hidden global precedence is forbidden.
- Ready Template Apply must end with `declared = persisted = effective` for all declared Store Appearance selections.
- Legacy adapters may remain, but they must not remain independent co-equal owners of the same Appearance concept.
- Historical rows without new explicit-local metadata must preserve current effective behavior until edited/migrated; no silent visual flip for existing stores.
- Every behavior change follows RED → GREEN → focused regression → evidence.
- No migration file is expected for Phase 1 because new explicit-local intent is stored inside existing Section JSON settings. If implementation discovers a schema migration is actually required, STOP and return to architecture review.
- No physical media cleanup, lifecycle-wide revision migration, non-Home R4 rollout, Brand/Collection vertical-slice expansion, CSS redesign, or legacy retirement in this plan.

---

## File Structure

### New file

- `apps/storefront_builder/services/appearance_authority_service.py`
  - Owns normalized, preservation-aware transformations of Version appearance state.
  - Calls existing validators/persistence primitives.
  - Does not own HTTP authorization, transaction/revision locking, or rendering.

### Existing files expected to change

- `apps/storefront_builder/storefront_appearance/persistence.py`
  - Keep typed manifest validation/persistence and legacy-mirror projections.
  - Add only small helper(s) needed by the authority service if existing private maps must be exposed safely.

- `apps/storefront_builder/services/preset_service.py`
  - Apply the Ready Template's declared typed `store_appearance` manifest as part of preset application.
  - Do not change composition replacement semantics in Phase 1.

- `apps/storefront_builder/r4_mutation_service.py`
  - Delegate appearance/header/footer/component/template state transformations to the authority service.
  - Retain R4 transaction, active-Draft lock, base-revision and history responsibilities here.

- `apps/storefront_builder/views.py`
  - Legacy Appearance/Header/Footer forms delegate state transformation to the authority service.
  - Preserve legacy URLs/UI and history decorator in Phase 1.

- `apps/storefront_builder/services/render_service.py`
  - Respect explicit local Section variant intent while preserving legacy effective behavior for unmarked historical rows.

- `apps/storefront_builder/settings_schema.py`
  - When an R4 patch explicitly changes a section's registered variant-setting key, stamp local-override intent in managed settings.
  - Do not expose the metadata as a merchant-editable field.

### Tests

- Create: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Extend: `apps/storefront_builder/tests/test_r4_store_appearance_persistence.py`
- Extend: `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`
- Extend: `apps/storefront_builder/tests/test_r4_mutation_api.py`
- Extend: `apps/storefront_builder/tests/test_r4_settings_schema.py`
- Extend only if needed for renderer behavior: `apps/storefront_builder/tests/test_u4_component_variants.py`

---

## Canonical Interfaces

Phase 1 introduces these exact service interfaces:

```python
# apps/storefront_builder/services/appearance_authority_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.layout_preset_registry import LayoutPresetDefinition
from apps.storefront_builder.storefront_appearance.contracts import StoreAppearanceManifest


def apply_appearance_patch(
    *,
    version: StorefrontLayoutVersion,
    patch: Mapping[str, Any],
) -> StorefrontLayoutVersion:
    """Merge validated legacy/global appearance fields without dropping opaque canonical keys."""


def apply_header_variant(
    *,
    version: StorefrontLayoutVersion,
    header_variant: str,
) -> StorefrontLayoutVersion:
    """Update header mirror/config and synchronize the typed manifest selection."""


def apply_footer_variant(
    *,
    version: StorefrontLayoutVersion,
    footer_variant: str | None = None,
    mobile_nav_variant: str | None = None,
) -> StorefrontLayoutVersion:
    """Update footer/mobile-nav mirrors and synchronize typed manifest selections."""


def apply_store_appearance_manifest(
    *,
    version: StorefrontLayoutVersion,
    manifest: StoreAppearanceManifest | Mapping[str, Any],
) -> StorefrontLayoutVersion:
    """Validate/persist the complete typed manifest and compatibility mirrors."""


def apply_ready_template_appearance(
    *,
    version: StorefrontLayoutVersion,
    preset: LayoutPresetDefinition,
) -> StorefrontLayoutVersion:
    """Apply preset appearance/palette/header/footer plus its complete declared typed manifest."""
```

Section local-variant intent uses this exact metadata key inside existing `StorefrontSection.settings`:

```python
settings["appearance_overrides"]["variant_explicit"] = True
```

Renderer rule:

```text
if a compatible section has variant_explicit=True:
    use the saved local section selector
else:
    a non-default Store-level manifest selection may provide the inherited/default selector
```

This preserves historical behavior for existing rows without the marker while making future explicit local changes obey the approved hierarchy.

---

# Task 0: Repository Bootstrap, Baseline Lock, and Safety Guard

**Files:**
- Read: `docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md`
- Read: `docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`
- Read: `docs/architecture_audits/final_closure_pack/07-master-current-state-blueprint.md`
- Create during execution evidence only: `docs/qa_evidence/storefront_appearance_convergence/phase1/baseline.md`

**Interfaces:**
- Consumes: approved five-phase architecture spec, approved implementation plan, documentation source branch, and G2.3 code baseline.
- Produces: an isolated Phase-1 worktree based on the approved documentation-only descendant, a reproducible Python/Django environment, and an explicit Phase-1 baseline record.

- [ ] **Step 1: Verify the remote documentation source branch, not the executor's current branch**

Run from the existing clone without switching or cleaning its current worktree:

```bash
git status --short
git branch --show-current
git fetch origin --prune
git rev-parse origin/docs/storefront-appearance-convergence
git merge-base --is-ancestor 93c5afea2ee32bef67cfb5923ffdb13bb61d7930 origin/docs/storefront-appearance-convergence
```

Expected:
- the current worktree may contain the prior untracked architecture-review document; do not modify, stash, reset, clean, or discard it;
- `origin/docs/storefront-appearance-convergence` exists;
- the ancestry command exits 0;
- the executor's current `main` HEAD does not need to descend from G2.3 and is not an implementation base.

If the docs branch is not a descendant of the approved baseline, STOP.

- [ ] **Step 2: Verify all required authoritative documents exist on the docs branch**

Run:

```bash
git cat-file -e origin/docs/storefront-appearance-convergence:docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md
git cat-file -e origin/docs/storefront-appearance-convergence:docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md
git cat-file -e origin/docs/storefront-appearance-convergence:docs/architecture_audits/final_closure_pack/07-master-current-state-blueprint.md
```

Expected: all three commands exit 0.

If either the spec or plan is missing, STOP. Do not execute Phase 1 from prompt-only copies.

- [ ] **Step 3: Create an isolated implementation worktree directly from the approved docs branch**

From the original repository directory:

```bash
git worktree add ../rastisi5_phase1 -b feature/storefront-appearance-convergence-phase1 origin/docs/storefront-appearance-convergence
cd ../rastisi5_phase1
git status --short
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 93c5afea2ee32bef67cfb5923ffdb13bb61d7930 HEAD
```

Expected:
- new worktree is clean;
- branch is exactly `feature/storefront-appearance-convergence-phase1`;
- G2.3 baseline is an ancestor;
- no merge from `main` has occurred.

If the branch already exists unexpectedly, STOP and report it rather than deleting or reusing it blindly.

- [ ] **Step 4: Provision the isolated Python 3.12 environment if the worktree has none**

First inspect repository setup files:

```bash
ls -la
sed -n '1,220p' requirements.txt
```

Use the existing pyenv Python 3.12 interpreter already present in the executor environment:

```bash
PYENV_VERSION=3.12.13 pyenv exec python --version
PYENV_VERSION=3.12.13 pyenv exec python -m venv ../rastisi5_phase1_venv
../rastisi5_phase1_venv/bin/python -m pip install --upgrade pip
../rastisi5_phase1_venv/bin/python -m pip install -r requirements.txt
../rastisi5_phase1_venv/bin/python --version
../rastisi5_phase1_venv/bin/python -m django --version
```

Expected:
- Python 3.12.x;
- Django satisfies the repository requirement (`>=5.2.17,<6` at this baseline);
- the virtual environment lives outside the Git worktree (`../rastisi5_phase1_venv`) and cannot become a repository change.

Verify:

```bash
git status --short
```

Expected: still clean.

Environment provisioning is authorized for Task 0 only to reproduce the repository's declared dependencies. Do not edit `requirements.txt`, lock files, application settings, or tracked source to make installation pass. If dependency installation fails, STOP with the exact package/error.

- [ ] **Step 5: Read the committed authority documents before recording policy**

Read, in order:

```text
docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md
docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md
docs/architecture_audits/final_closure_pack/07-master-current-state-blueprint.md
```

Do not rely on prompt copies when the committed document differs.

- [ ] **Step 6: Run baseline Django checks**

```bash
../rastisi5_phase1_venv/bin/python manage.py check
../rastisi5_phase1_venv/bin/python manage.py makemigrations --check --dry-run
```

Expected:
- system check clean;
- `No changes detected`.

- [ ] **Step 7: Record the Phase-1 policy decisions**

Write `docs/qa_evidence/storefront_appearance_convergence/phase1/baseline.md` with this exact policy set plus the actual source-branch HEAD and environment versions:

```markdown
# Phase 1 Baseline

- Source branch: origin/docs/storefront-appearance-convergence
- Approved code baseline ancestor: 93c5afea2ee32bef67cfb5923ffdb13bb61d7930
- Implementation branch: feature/storefront-appearance-convergence-phase1
- Normal precedence: Template DNA -> Store Global -> Page -> Section/Component.
- Explicit local Section variant wins an inherited Store-level family default.
- Historical sections without explicit-local metadata preserve their current inherited/global behavior until edited or migrated.
- Legacy editors remain temporarily and must delegate to canonical state transformations; no route retirement in Phase 1.
- Template Apply remains replacement/reset semantics in Phase 1; content-preserving Switch is not implemented here.
- Lock semantics, live identity publication policy, and full media-retention mechanics remain Phase 2 concerns.
- No new variants, no new renderer, no commerce rewrite.
```

Append the actual outputs for Python, Django, `manage.py check`, and migration dry-run.

- [ ] **Step 8: Commit the Task-0 documentation evidence only**

```bash
git add docs/qa_evidence/storefront_appearance_convergence/phase1/baseline.md
git diff --cached --name-only
git diff --cached --check
git commit -m "docs: lock phase1 appearance authority baseline"
git status --short
```

Expected:
- staged/committed file is documentation only;
- worktree clean afterward;
- no push unless separately authorized.


# Task 1: Characterize the Three Phase-1 Authority Failures

**Files:**
- Create: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Read: `apps/storefront_builder/views.py`
- Read: `apps/storefront_builder/services/preset_service.py`
- Read: `apps/storefront_builder/r4_mutation_service.py`
- Read: `apps/storefront_builder/services/render_service.py`

**Interfaces:**
- Consumes: current baseline behavior.
- Produces: failing regression tests that prove the exact authority defects before implementation.

- [ ] **Step 1: Add a legacy Appearance preservation regression**

Add a Django test that:
1. creates a Draft version;
2. persists a non-default typed manifest;
3. submits the existing legacy Appearance form changing only `font`;
4. reloads the version;
5. asserts `appearance_config["store_appearance"]` is unchanged.

Test shape:

```python
def test_legacy_appearance_edit_preserves_typed_manifest(self):
    version = self.make_draft()
    original = self.persist_manifest(
        version,
        selections={
            "header": "header.dark_tech.v1",
            "hero": "hero.split.v1",
            "card": "card.luxury_dark.v1",
        },
    )

    response = self.client.post(
        self.appearance_url,
        {
            "font": "Tahoma",
            # include all other fields required by the existing form fixture
        },
    )

    self.assertEqual(response.status_code, 302)
    version.refresh_from_db()
    self.assertEqual(
        version.appearance_config["store_appearance"],
        original.to_dict(),
    )
```

Expected before implementation: FAIL because the legacy form reconstructs/replaces appearance JSON and can omit the typed manifest.

- [ ] **Step 2: Add a legacy global selector synchronization regression**

Add tests for both Header and Footer:

```python
def test_legacy_header_edit_updates_effective_manifest_selection(self):
    version = self.make_draft_with_manifest()
    self.client.post(self.header_url, {"header_variant": "dark_tech", ...})
    version.refresh_from_db()
    state = resolve_store_appearance_render_state(version)
    self.assertEqual(state.manifest.selections["header"], "header.dark_tech.v1")
```

```python
def test_legacy_footer_edit_updates_effective_manifest_selection(self):
    version = self.make_draft_with_manifest()
    self.client.post(self.footer_url, {"footer_variant": "minimal", ...})
    version.refresh_from_db()
    state = resolve_store_appearance_render_state(version)
    self.assertEqual(state.manifest.selections["footer"], "footer.minimal.v1")
```

Expected before implementation: at least one FAIL because legacy mirrors can diverge from the typed manifest.

- [ ] **Step 3: Add Ready Template full-manifest fidelity regression**

Choose a Ready Template whose manifest contains non-default values for at least:
- header;
- footer;
- bottom_nav;
- hero;
- layout;
- product_view;
- card;
- badge;
- motion.

Seed the Draft with deliberately conflicting selections first.

```python
def test_ready_template_apply_replaces_all_declared_manifest_selections(self):
    preset = get_layout_preset("dense_marketplace")
    version = self.make_draft_with_conflicting_manifest()

    apply_preset(version=version, preset=preset)

    version.refresh_from_db()
    state = resolve_store_appearance_render_state(version)

    self.assertEqual(
        state.manifest.selections,
        preset.store_appearance["selections"],
    )
```

Expected before implementation: FAIL because current preset apply does not persist the full declared manifest.

- [ ] **Step 4: Add historical-vs-explicit local variant characterization**

Create two Hero sections:
- historical row: local selector present, no `appearance_overrides.variant_explicit`;
- explicit row: same selector plus marker set to `True`.

Use a non-default Store-level Hero selection.

Target assertions:

```python
def test_historical_unmarked_variant_keeps_legacy_inherited_behavior(self):
    item = self.render_item(
        local_variant="overlay",
        variant_explicit=False,
        global_component="hero.split.v1",
    )
    self.assertEqual(item.active_variant.key, "split")
```

```python
def test_explicit_local_variant_wins_store_default(self):
    item = self.render_item(
        local_variant="overlay",
        variant_explicit=True,
        global_component="hero.split.v1",
    )
    self.assertEqual(item.active_variant.key, "overlay")
```

Expected before implementation:
- historical test PASS under current behavior;
- explicit-local test FAIL until Task 6.

- [ ] **Step 5: Run only the new tests**

```powershell
python manage.py test apps.storefront_builder.tests.test_phase1_appearance_authority --verbosity 2
```

Expected:
- intentional RED failures for preservation, legacy sync, recipe fidelity, and explicit-local precedence;
- no unexpected unrelated failures.

- [ ] **Step 6: Commit RED tests**

```powershell
git add apps/storefront_builder/tests/test_phase1_appearance_authority.py
git commit -m "test: characterize phase1 appearance authority gaps"
```

---

# Task 2: Introduce the Preservation-Aware Appearance Authority Service

**Files:**
- Create: `apps/storefront_builder/services/appearance_authority_service.py`
- Modify if needed: `apps/storefront_builder/storefront_appearance/persistence.py`
- Test: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`

**Interfaces:**
- Consumes:
  - `validate_appearance_config`
  - `APPEARANCE_CONFIG_DEFAULTS`
  - `persist_store_appearance_manifest`
  - existing typed registry/adapters
- Produces:
  - `apply_appearance_patch`
  - `apply_header_variant`
  - `apply_footer_variant`
  - `apply_store_appearance_manifest`
  - `apply_ready_template_appearance`

- [ ] **Step 1: Add unit tests for merge preservation**

Add service-level tests:

```python
def test_apply_appearance_patch_preserves_unmanaged_canonical_keys(self):
    version = self.make_draft()
    version.appearance_config = {
        **APPEARANCE_CONFIG_DEFAULTS,
        "store_appearance": self.sample_manifest_dict(),
        "layout_preset_key": "dense_marketplace",
    }
    version.save(update_fields=["appearance_config"])

    apply_appearance_patch(version=version, patch={"font": "Tahoma"})

    version.refresh_from_db()
    self.assertEqual(version.appearance_config["font"], "Tahoma")
    self.assertEqual(
        version.appearance_config["store_appearance"],
        self.sample_manifest_dict(),
    )
    self.assertEqual(
        version.appearance_config["layout_preset_key"],
        "dense_marketplace",
    )
```

- [ ] **Step 2: Implement a pure merge helper**

In `appearance_authority_service.py`:

```python
from copy import deepcopy

from apps.storefront_builder.appearance_registry import (
    APPEARANCE_CONFIG_DEFAULTS,
    validate_appearance_config,
)


def _merge_appearance_config(
    current: Mapping[str, Any] | None,
    patch: Mapping[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(dict(current or {}))
    merged.update(dict(patch))

    validated = validate_appearance_config(merged)

    managed_keys = set(APPEARANCE_CONFIG_DEFAULTS)
    opaque = {
        key: deepcopy(value)
        for key, value in merged.items()
        if key not in managed_keys
    }
    validated.update(opaque)
    return validated
```

Do not hard-code only `store_appearance`; preserve every non-legacy-managed canonical key.

- [ ] **Step 3: Implement `apply_appearance_patch`**

```python
def apply_appearance_patch(*, version, patch):
    version.appearance_config = _merge_appearance_config(
        version.appearance_config,
        patch,
    )
    version.save(update_fields=["appearance_config"])
    return version
```

- [ ] **Step 4: Implement manifest delegation**

```python
from apps.storefront_builder.storefront_appearance.persistence import (
    persist_store_appearance_manifest,
)


def apply_store_appearance_manifest(*, version, manifest):
    persist_store_appearance_manifest(version=version, manifest=manifest)
    return version
```

Use the exact existing parameter names from the persistence function. If its signature differs, adapt the call without changing its public semantics.

- [ ] **Step 5: Implement global-region selection helpers by reusing existing adapter maps**

Do not duplicate component-key maps in the new service.

The implementation must:
1. update the legacy mirror/config field;
2. derive/synchronize the typed manifest through existing persistence/adapters;
3. preserve unrelated config keys.

Representative structure:

```python
def apply_header_variant(*, version, header_variant):
    header = dict(version.header_config or {})
    header["variant"] = header_variant
    version.header_config = header
    version.save(update_fields=["header_config"])
    sync_store_appearance_manifest_from_legacy(version)
    return version
```

Use the repository's actual legacy selector key (`header_variant` vs `variant`) and actual existing sync helper after inspecting `persistence.py`; do not introduce a second selector map.

Implement Footer/Mobile Nav with the same rule.

- [ ] **Step 6: Run service tests**

```powershell
python manage.py test apps.storefront_builder.tests.test_phase1_appearance_authority --verbosity 2
```

Expected:
- merge-preservation/service tests GREEN;
- route/template/renderer tests that depend on later wiring may still be RED.

- [ ] **Step 7: Run existing manifest contract suites**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_store_appearance_contracts `
  apps.storefront_builder.tests.test_r4_store_appearance_registry `
  apps.storefront_builder.tests.test_r4_store_appearance_validation `
  apps.storefront_builder.tests.test_r4_store_appearance_compatibility `
  --verbosity 1
```

Expected: GREEN.

- [ ] **Step 8: Commit authority service**

```powershell
git add apps/storefront_builder/services/appearance_authority_service.py apps/storefront_builder/storefront_appearance/persistence.py apps/storefront_builder/tests/test_phase1_appearance_authority.py
git commit -m "feat: add canonical appearance authority service"
```

---

# Task 3: Route Legacy Appearance/Header/Footer Writers Through the Authority Service

**Files:**
- Modify: `apps/storefront_builder/views.py`
- Test: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Extend: `apps/storefront_builder/tests/test_r4_store_appearance_persistence.py`

**Interfaces:**
- Consumes:
  - `apply_appearance_patch`
  - `apply_header_variant`
  - `apply_footer_variant`
- Produces:
  - legacy URLs with unchanged HTTP/UI behavior but canonical state transformation.

- [ ] **Step 1: Update the legacy Appearance POST**

Replace direct whole-dictionary assignment:

```python
version.appearance_config = validate_appearance_config(payload)
version.save(update_fields=["appearance_config"])
```

with:

```python
apply_appearance_patch(
    version=version,
    patch=payload,
)
```

Keep the existing form parsing, authorization, history decorator, redirect, messages and validation error behavior unchanged.

- [ ] **Step 2: Update the legacy Header POST**

After existing form validation, call:

```python
apply_header_variant(
    version=version,
    header_variant=cleaned_header_variant,
)
```

If the form also edits visibility/content options, keep those values in the same header config update, but ensure selection synchronization occurs in the authority service.

- [ ] **Step 3: Update the legacy Footer POST**

Use:

```python
apply_footer_variant(
    version=version,
    footer_variant=cleaned_footer_variant,
    mobile_nav_variant=cleaned_mobile_nav_variant,
)
```

Preserve unrelated Footer config and live FooterSettings responsibilities.

- [ ] **Step 4: Run the route regressions**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_phase1_appearance_authority `
  apps.storefront_builder.tests.test_r4_store_appearance_persistence `
  --verbosity 2
```

Expected:
- legacy Appearance manifest-preservation test GREEN;
- legacy Header/Footer effective-manifest tests GREEN;
- recipe/explicit-local tests may remain RED until later tasks.

- [ ] **Step 5: Run focused existing legacy/global-region tests**

Run the current suites that cover Header/Footer/page shell behavior. Use the repository's existing test module names discovered by `python manage.py test apps.storefront_builder.tests --pattern ...` or direct known modules; minimum include the global Header system and page shell tests.

Expected: GREEN; no visual selector regression.

- [ ] **Step 6: Commit legacy writer delegation**

```powershell
git add apps/storefront_builder/views.py apps/storefront_builder/tests/test_phase1_appearance_authority.py apps/storefront_builder/tests/test_r4_store_appearance_persistence.py
git commit -m "refactor: route legacy appearance writes through authority service"
```

---

# Task 4: Route R4 Appearance/Global-Region Commands Through the Same Authority Service

**Files:**
- Modify: `apps/storefront_builder/r4_mutation_service.py`
- Test: `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`
- Test: `apps/storefront_builder/tests/test_r4_mutation_api.py`
- Test: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`

**Interfaces:**
- Consumes authority-service functions.
- Produces one state-transformation path while retaining R4 locking/revision/history behavior.

- [ ] **Step 1: Add a preservation test around R4 global Appearance patch**

```python
def test_r4_appearance_patch_preserves_manifest_and_unrelated_keys(self):
    version = self.make_draft_with_manifest()
    old_manifest = deepcopy(version.appearance_config["store_appearance"])

    self.post_r4_mutation(
        version,
        {
            "type": "appearance.update",
            "patch": {"font": "Tahoma"},
        },
    )

    version.refresh_from_db()
    self.assertEqual(version.appearance_config["store_appearance"], old_manifest)
```

Expected on baseline: likely GREEN for some R4 paths; keep it as a permanent invariant.

- [ ] **Step 2: Replace duplicated Appearance update transformation**

In `_apply_appearance_update`, delegate final state transformation:

```python
apply_appearance_patch(
    version=draft,
    patch=validated_patch,
)
```

Retain:
- command validation;
- transaction;
- base revision check;
- history snapshot;
- revision increment;
- response payload.

- [ ] **Step 3: Delegate Header/Footer selection transformations**

Replace direct selector+manifest synchronization logic with:

```python
apply_header_variant(version=draft, header_variant=header_variant)
```

and:

```python
apply_footer_variant(
    version=draft,
    footer_variant=footer_variant,
    mobile_nav_variant=mobile_nav_variant,
)
```

Only pass fields actually present in the command.

- [ ] **Step 4: Keep component/whole-manifest commands on canonical persistence**

Route `appearance.component.update` and `appearance.manifest.apply` through `apply_store_appearance_manifest`.

Do not change command schemas in this task.

- [ ] **Step 5: Run R4 focused tests**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_r4_store_appearance_mutations `
  apps.storefront_builder.tests.test_r4_mutation_api `
  apps.storefront_builder.tests.test_phase1_appearance_authority `
  --verbosity 2
```

Expected:
- all R4 revision/tenant/rollback tests GREEN;
- no-op behavior unchanged;
- authority preservation tests GREEN.

- [ ] **Step 6: Commit R4 delegation**

```powershell
git add apps/storefront_builder/r4_mutation_service.py apps/storefront_builder/tests/test_r4_store_appearance_mutations.py apps/storefront_builder/tests/test_r4_mutation_api.py apps/storefront_builder/tests/test_phase1_appearance_authority.py
git commit -m "refactor: share appearance authority across R4 mutations"
```

---

# Task 5: Make Ready Template Apply Persist the Complete Declared Manifest

**Files:**
- Modify: `apps/storefront_builder/services/appearance_authority_service.py`
- Modify: `apps/storefront_builder/services/preset_service.py`
- Modify: `apps/storefront_builder/r4_mutation_service.py`
- Test: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Extend: `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`
- Extend: `apps/storefront_builder/tests/test_a8_ready_template_contracts.py`

**Interfaces:**
- Consumes:
  - `LayoutPresetDefinition.store_appearance`
  - existing preset composition application
  - typed manifest validation/persistence
- Produces:
  - deterministic recipe appearance application independent of starting manifest.

- [ ] **Step 1: Add a service-level declared→persisted test**

```python
def test_apply_ready_template_appearance_persists_declared_manifest(self):
    version = self.make_draft_with_conflicting_manifest()
    preset = get_layout_preset("dense_marketplace")

    apply_ready_template_appearance(version=version, preset=preset)

    version.refresh_from_db()
    persisted = version.appearance_config["store_appearance"]

    self.assertEqual(
        persisted["selections"],
        preset.store_appearance["selections"],
    )
    self.assertEqual(
        persisted["settings"],
        preset.store_appearance["settings"],
    )
```

- [ ] **Step 2: Implement `apply_ready_template_appearance`**

Representative implementation:

```python
def apply_ready_template_appearance(*, version, preset):
    if preset.appearance:
        apply_appearance_patch(
            version=version,
            patch=preset.appearance,
        )

    if preset.header:
        # preserve existing non-selector Header config while applying the preset's selector/config
        header = dict(version.header_config or {})
        header.update(dict(preset.header))
        version.header_config = header
        version.save(update_fields=["header_config"])

    if preset.footer:
        footer = dict(version.footer_config or {})
        footer.update(dict(preset.footer))
        version.footer_config = footer
        version.save(update_fields=["footer_config"])

    apply_store_appearance_manifest(
        version=version,
        manifest=preset.store_appearance,
    )
    return version
```

Use the preset's palette field through the existing canonical appearance/preset logic rather than adding a second palette writer.

- [ ] **Step 3: Integrate it into the canonical preset application path**

In `preset_service.apply_preset`, call `apply_ready_template_appearance` exactly once inside the same transaction that applies composition/config/provenance.

The order must guarantee that compatibility mirrors generated by the full typed manifest are not overwritten later by stale selector values.

Preferred order:

```text
validate preset
→ apply composition
→ apply ordinary appearance/header/footer payload
→ persist complete typed manifest + mirrors
→ provenance/baseline finalization
```

If current baseline snapshot semantics require a different ordering, add a regression proving reset still returns to the newly applied recipe baseline.

- [ ] **Step 4: Remove R4's partial four-family post-apply synchronization**

Once `preset_service.apply_preset` applies the full manifest, delete only the redundant R4 template-apply synchronization branch that handles just:

```python
("header", "footer", "bottom_nav", "motion")
```

Do not delete generic compatibility maps used elsewhere.

R4 remains responsible for:
- exact preset version validation;
- active Draft lock;
- base revision;
- history;
- atomic rollback.

- [ ] **Step 5: Add R4 and legacy entry-path equivalence tests**

For the same preset and same conflicting initial manifest:
1. apply via legacy gallery/preset route;
2. apply via R4 `appearance.template.apply`;
3. compare persisted manifest selections and effective resolver output.

```python
self.assertEqual(legacy_state.manifest.to_dict(), r4_state.manifest.to_dict())
self.assertEqual(
    r4_state.manifest.selections,
    preset.store_appearance["selections"],
)
```

- [ ] **Step 6: Enumerate all 50 Ready Templates in a no-DB contract test**

Add/extend a SimpleTestCase:

```python
def test_all_ready_templates_declare_valid_complete_manifest(self):
    for preset in list_ready_templates():
        manifest = validate_store_appearance_manifest(preset.store_appearance)
        self.assertEqual(
            set(manifest.selections),
            set(COMPONENT_FAMILIES),
            preset.key,
        )
```

This validates declarations only; DB-backed apply tests prove persistence separately.

- [ ] **Step 7: Run focused recipe tests**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_phase1_appearance_authority `
  apps.storefront_builder.tests.test_r4_store_appearance_mutations `
  apps.storefront_builder.tests.test_a8_ready_template_contracts `
  --verbosity 2
```

Expected:
- `declared → persisted` GREEN;
- R4/legacy entry equivalence GREEN;
- no atomic rollback regressions.

- [ ] **Step 8: Commit recipe fidelity**

```powershell
git add apps/storefront_builder/services/appearance_authority_service.py apps/storefront_builder/services/preset_service.py apps/storefront_builder/r4_mutation_service.py apps/storefront_builder/tests/test_phase1_appearance_authority.py apps/storefront_builder/tests/test_r4_store_appearance_mutations.py apps/storefront_builder/tests/test_a8_ready_template_contracts.py
git commit -m "fix: make ready template appearance application authoritative"
```

---

# Task 6: Add Explicit Local Variant Intent Without Breaking Historical Stores

**Files:**
- Modify: `apps/storefront_builder/settings_schema.py`
- Modify: `apps/storefront_builder/views.py`
- Modify: `apps/storefront_builder/services/render_service.py`
- Test: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Test: `apps/storefront_builder/tests/test_r4_settings_schema.py`
- Test: `apps/storefront_builder/tests/test_u4_component_variants.py`

**Interfaces:**
- Consumes:
  - registered `variant_setting_key`
  - approved precedence hierarchy
  - existing Section settings JSON
- Produces:
  - `appearance_overrides.variant_explicit=True` when a merchant explicitly changes a local variant;
  - renderer inheritance that preserves old unmarked behavior.

- [ ] **Step 1: Add a pure helper for local-variant intent**

In `settings_schema.py` or a focused existing settings helper module:

```python
def mark_explicit_variant_override(
    *,
    settings: dict[str, Any],
    variant_setting_key: str | None,
    patch: Mapping[str, Any],
) -> dict[str, Any]:
    if not variant_setting_key or variant_setting_key not in patch:
        return settings

    updated = deepcopy(settings)
    overrides = dict(updated.get("appearance_overrides") or {})
    overrides["variant_explicit"] = True
    updated["appearance_overrides"] = overrides
    return updated
```

- [ ] **Step 2: R4 schema patch stamps intent only when variant changes**

After successful schema validation/merge, call the helper using the SectionDefinition's `variant_setting_key`.

A title-only, source-only or typography-only patch must not set the flag.

Add tests:

```python
def test_variant_patch_marks_local_override_explicit(self):
    ...
    self.assertTrue(
        updated["appearance_overrides"]["variant_explicit"]
    )
```

```python
def test_non_variant_patch_does_not_mark_variant_override(self):
    ...
    self.assertNotIn(
        "variant_explicit",
        updated.get("appearance_overrides", {}),
    )
```

- [ ] **Step 3: Legacy section form stamps the same intent**

In `storefront_section_settings`, detect whether the POST includes the definition's variant-setting field and its submitted value differs from the stored value.

Then set:

```python
appearance_overrides = dict(new_settings.get("appearance_overrides") or {})
appearance_overrides["variant_explicit"] = True
new_settings["appearance_overrides"] = appearance_overrides
```

Do not mark it merely because a hidden/default HTML field is always posted; compare against stored value or the form's actual editable control branch.

- [ ] **Step 4: Change renderer overlay precedence**

Current logic broadly does:

```python
if appearance_variant:
    effective_settings[variant_setting_key] = appearance_variant
```

Replace with:

```python
overrides = effective_settings.get("appearance_overrides") or {}
variant_explicit = bool(overrides.get("variant_explicit"))

if appearance_variant and not variant_explicit:
    effective_settings[variant_setting_key] = appearance_variant
```

Do not remove the global manifest selection; it remains the inherited Store default.

- [ ] **Step 5: Preserve historical output**

Keep the characterization invariant:
- no marker → current global overlay behavior;
- explicit marker → local wins.

Do **not** bulk-mark or bulk-rewrite existing rows in Phase 1.

- [ ] **Step 6: Run variant-focused tests**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_phase1_appearance_authority `
  apps.storefront_builder.tests.test_r4_settings_schema `
  apps.storefront_builder.tests.test_u4_component_variants `
  --verbosity 2
```

Expected: GREEN.

- [ ] **Step 7: Commit explicit-local precedence**

```powershell
git add apps/storefront_builder/settings_schema.py apps/storefront_builder/views.py apps/storefront_builder/services/render_service.py apps/storefront_builder/tests/test_phase1_appearance_authority.py apps/storefront_builder/tests/test_r4_settings_schema.py apps/storefront_builder/tests/test_u4_component_variants.py
git commit -m "feat: make local variant overrides explicit"
```

---

# Task 7: Prove Declared = Persisted = Effective for Representative Recipes

**Files:**
- Extend: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`
- Extend as appropriate: `apps/storefront_builder/tests/test_r4_store_appearance_persistence.py`
- Create evidence: `docs/qa_evidence/storefront_appearance_convergence/phase1/recipe_fidelity.md`

**Interfaces:**
- Consumes completed Tasks 2–6.
- Produces evidence that the P0 recipe-authority gap is closed.

- [ ] **Step 1: Add deterministic DB-backed recipe roundtrip cases**

Use at least these materially different Ready recipes:

```text
dense_marketplace
premium_leather
dark_digital
warm_boutique
anniversary_mosaic
```

For each:
1. start from a Draft with conflicting manifest selections;
2. apply the recipe;
3. reload from DB;
4. resolve effective Store Appearance;
5. compare every declared family selection.

Test helper:

```python
def assert_recipe_fidelity(self, preset_key):
    preset = get_layout_preset(preset_key)
    version = self.make_draft_with_conflicting_manifest()

    apply_preset(version=version, preset=preset)

    version.refresh_from_db()
    state = resolve_store_appearance_render_state(version)

    self.assertEqual(
        state.manifest.selections,
        preset.store_appearance["selections"],
        preset_key,
    )
    self.assertEqual(
        state.manifest.settings,
        preset.store_appearance["settings"],
        preset_key,
    )
```

- [ ] **Step 2: Add one idempotence case**

Apply the same Ready Template twice to equivalent Draft starting state and assert effective manifest equality.

Do not assert content preservation; Apply remains replacement semantics.

- [ ] **Step 3: Add one rollback case**

Force an exception after preset composition begins but before transaction completion using the existing test patch/mocking convention from `test_r4_store_appearance_mutations.py`.

Assert:
- original manifest restored;
- original composition restored;
- revision/history behavior unchanged.

- [ ] **Step 4: Run representative recipe fidelity tests**

```powershell
python manage.py test apps.storefront_builder.tests.test_phase1_appearance_authority --verbosity 2
```

Expected: GREEN.

- [ ] **Step 5: Write evidence report**

`docs/qa_evidence/storefront_appearance_convergence/phase1/recipe_fidelity.md` must contain:

```markdown
# Phase 1 Recipe Fidelity Evidence

## Baseline
<HEAD>

## Recipes exercised
- dense_marketplace
- premium_leather
- dark_digital
- warm_boutique
- anniversary_mosaic

## Proven invariant
Declared Store Appearance selections = persisted manifest selections = effective resolved selections.

## Entry paths
- canonical preset service
- R4 template apply
- legacy Ready Template apply

## Rollback
<test name and result>

## Non-goals
- content-preserving template switch not implemented
- visual/browser certification not claimed
```

- [ ] **Step 6: Commit evidence**

```powershell
git add apps/storefront_builder/tests/test_phase1_appearance_authority.py docs/qa_evidence/storefront_appearance_convergence/phase1/recipe_fidelity.md
git commit -m "test: prove ready template appearance fidelity"
```

---

# Task 8: Phase-1 Regression Gate and Architecture Review

**Files:**
- Create: `docs/qa_evidence/storefront_appearance_convergence/phase1/final_gate.md`
- No application change unless a failing focused test exposes a Phase-1 regression.

**Interfaces:**
- Consumes all Phase-1 tasks.
- Produces Phase-1 PASS/FAIL evidence. A PASS is required before Phase 2 planning.

- [ ] **Step 1: Run Django integrity checks**

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Expected:
- clean system check;
- `No changes detected`.

- [ ] **Step 2: Run Phase-1 focused test matrix**

```powershell
python manage.py test `
  apps.storefront_builder.tests.test_phase1_appearance_authority `
  apps.storefront_builder.tests.test_r4_store_appearance_contracts `
  apps.storefront_builder.tests.test_r4_store_appearance_registry `
  apps.storefront_builder.tests.test_r4_store_appearance_validation `
  apps.storefront_builder.tests.test_r4_store_appearance_compatibility `
  apps.storefront_builder.tests.test_r4_store_appearance_persistence `
  apps.storefront_builder.tests.test_r4_store_appearance_mutations `
  apps.storefront_builder.tests.test_r4_mutation_api `
  apps.storefront_builder.tests.test_r4_settings_schema `
  apps.storefront_builder.tests.test_u4_component_variants `
  apps.storefront_builder.tests.test_a8_ready_template_contracts `
  apps.storefront_builder.tests.test_g23_builder_public_content_appearance `
  --verbosity 1
```

Expected: all GREEN.

Do not substitute the entire repository suite for this gate unless a reviewer requests it.

- [ ] **Step 3: Verify no schema migration**

```powershell
python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 4: Inspect change scope**

```powershell
git status --short
git diff --stat 93c5afea2ee32bef67cfb5923ffdb13bb61d7930...HEAD
git diff --name-only 93c5afea2ee32bef67cfb5923ffdb13bb61d7930...HEAD
```

Verify no changes in:
- catalog pricing/domain models;
- cart/order/auth business logic;
- unrelated CSS/templates;
- migrations;
- new renderer engines.

- [ ] **Step 5: Write final Phase-1 gate**

Create `final_gate.md`:

```markdown
# Phase 1 — Architecture & Authority Final Gate

## Result
PASS / FAIL

## Canonical ownership
- Legacy Appearance delegates to authority service
- Legacy Header/Footer selection delegates to authority service
- R4 Appearance/global-region commands delegate to authority service
- Typed manifest persistence remains canonical

## Recipe fidelity
- Declared = Persisted = Effective: PASS
- R4 and legacy Apply entry paths converge: PASS
- Conflicting starting manifest does not leak into applied recipe: PASS

## Precedence
- Historical unmarked section behavior preserved: PASS
- Explicit local variant wins inherited Store default: PASS

## Safety preserved
- R4 revision tests: PASS
- Tenant isolation tests: PASS
- Atomic rollback tests: PASS
- Django check: PASS
- Migration check: PASS

## Explicit Phase-1 non-goals
- Phase 2 lifecycle-wide migration not started
- media reference graph not redesigned
- Brand/Collection vertical slices not started
- non-Home R4 expansion not started
- no legacy route deleted
- no new visual variants
```

Fill PASS only from actual command output.

- [ ] **Step 6: Request architecture/code review**

Reviewer must answer:
1. Is there still any active Appearance transformation duplicated between legacy/R4/preset paths?
2. Does the authority service own transformation only, leaving revision/HTTP/render responsibilities in existing layers?
3. Does preset apply now persist the full typed manifest once, with no later stale overwrite?
4. Does explicit-local metadata preserve historical stores?
5. Did Phase 1 accidentally enter Phase 2/3 scope?

If any answer is adverse, Phase 1 remains open.

- [ ] **Step 7: Commit final evidence after review fixes**

```powershell
git add docs/qa_evidence/storefront_appearance_convergence/phase1/final_gate.md
git commit -m "docs: close storefront appearance convergence phase1"
```

Do not begin Phase 2 until the Product Owner/Architect accepts this gate.

---

# Phase-1 Completion Criteria

Phase 1 is complete only when all are true:

- [ ] Legacy Appearance edits preserve typed manifest and opaque canonical keys.
- [ ] Legacy Header/Footer selections synchronize the typed manifest.
- [ ] R4 and legacy paths share one appearance-state transformation layer.
- [ ] Ready Template Apply persists the complete declared manifest.
- [ ] R4 no longer performs a partial four-family template sync that can diverge from preset behavior.
- [ ] Conflicting starting manifests cannot leak into an applied Ready recipe.
- [ ] Explicit local Section variant intent is represented separately from inherited/default selection.
- [ ] Historical unmarked sections retain legacy effective output.
- [ ] Explicit local Section variant wins Store Global default.
- [ ] Existing R4 revision, tenant, rollback, persistence and G2.3 regressions remain GREEN.
- [ ] No migration file is created.
- [ ] No business-domain rewrite occurs.
- [ ] No new renderer is introduced.
- [ ] No visual variant is added.
- [ ] Final Phase-1 evidence is reviewed and accepted.

---

# Self-Review Against the Five-Phase Spec

## Spec coverage

Phase 1 requirements covered:
- one canonical state/write owner: Tasks 2–4;
- Ready Template `declared = persisted = effective`: Tasks 5 and 7;
- approved normal precedence: Task 6;
- legacy as compatibility adapter, not deleted: Tasks 3 and 4;
- no second renderer/business rewrite: global constraints + Task 8;
- evidence gate: Task 8.

Explicitly deferred to later phases:
- lifecycle-wide revision convergence: Phase 2;
- complete media reference/lifetime system: Phase 2;
- Brand/Collection end-to-end family proof: Phase 3;
- 32 remaining Section schema migration: Phase 4;
- non-Home R4 UI migration: Phase 4;
- legacy route retirement: Phase 4;
- new variants/seasonal themes/50-template browser certification: Phase 5.

## Placeholder scan

This plan intentionally contains no `TBD`, `TODO`, “implement later”, or generic “add tests” steps. Every deferred item is assigned to a later approved phase rather than left undefined inside Phase 1.

## Type/interface consistency

The same five authority-service interfaces are used throughout:
- `apply_appearance_patch`
- `apply_header_variant`
- `apply_footer_variant`
- `apply_store_appearance_manifest`
- `apply_ready_template_appearance`

The local override metadata key is consistently:

```python
appearance_overrides["variant_explicit"]
```

No alternate name is used elsewhere in the plan.
