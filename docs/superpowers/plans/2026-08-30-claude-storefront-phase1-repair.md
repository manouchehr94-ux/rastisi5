# Claude Storefront Builder Phase 1 Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose and repair the current R3 Storefront Builder modal interaction lifecycle so all settings work reliably and the two save controls share one correct persistence path.

**Architecture:** Keep the existing Storefront Builder persistence and R3 full-screen editor. Treat the modal as an orchestration layer over existing settings forms; fix the shared initialization/save lifecycle at its source rather than adding per-control patches.

**Tech Stack:** Django 5.2, Django templates, HTMX, Alpine.js, vanilla JavaScript, existing RastiSi Storefront Builder services/tests.

**Spec:** `docs/superpowers/specs/2026-08-30-claude-storefront-phase1-repair-design.md`

## Global Constraints

- Work only on `claude/storefront-builder-phase1-repair`.
- Never force push, merge, rebase, pull, `reset --hard`, or `clean`.
- Do not touch `feature/storefront-builder-v3-redesign` or auth/onboarding branches.
- Preserve Draft/Preview/Publish, Palette64, current storefront templates, and current database schema.
- Phase 1 is behavior repair only; do not begin Phase 2 without explicit human approval.
- Use TDD: reproduce each shared failure with a failing regression before implementing the fix.

---

### Task 1: Establish a reproducible baseline and trace the modal lifecycle

**Files:**
- Read: `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`
- Read: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html`
- Read: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html`
- Read: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html`
- Read: `apps/storefront_builder/views.py`
- Test: existing R2/R3/R3.2/Universal Selection tests

**Interfaces:**
- Consumes: existing `openR3*`, HTMX target/swap behavior, Alpine component helpers, form endpoints.
- Produces: a written root-cause note identifying exactly where initialization or event/save flow breaks.

- [ ] Run the existing focused Storefront Builder tests and `manage.py check` to establish the automated baseline.
- [ ] Reproduce at least Universal Selection mode switching and background interaction in a real browser or equivalent DOM-capable test environment.
- [ ] Trace HTMX events (`htmx:beforeSwap`, `htmx:afterSwap`, `htmx:afterSettle`) and Alpine initialization for modal-loaded content.
- [ ] Trace both save affordances to the final Django POST endpoint and preview reload behavior.
- [ ] Record one root-cause hypothesis supported by runtime evidence before modifying production code.

### Task 2: Add regression coverage for modal-loaded interactive controls

**Files:**
- Modify/Create test files under `apps/storefront_builder/tests/` following existing naming patterns.
- Production files: none in the RED step.

**Interfaces:**
- Consumes: the proven root cause from Task 1.
- Produces: a failing test that proves modal-loaded Alpine/HTMX settings become interactive exactly once.

- [ ] Write the smallest failing regression that loads/inserts the same settings markup path used by R3 and proves mode switching/background interaction is initialized.
- [ ] Run only that regression and confirm it fails for the observed reason, not because of a fixture/import error.
- [ ] Keep the test focused on the shared lifecycle; do not encode one-off fixes for category/brand/collection/product separately unless evidence shows independent bugs.

### Task 3: Repair the shared modal initialization lifecycle

**Files:**
- Modify only the smallest shared R3/HTMX/Alpine orchestration files identified by Task 1.
- Test: regression from Task 2 plus R3/R3.2/Universal Selection contracts.

**Interfaces:**
- Consumes: HTMX-inserted settings partials.
- Produces: correctly initialized interactive controls after every modal load/reload, with no duplicate initialization/listeners.

- [ ] Implement the minimal root-cause fix.
- [ ] Run the new regression and confirm GREEN.
- [ ] Run existing R3/R3.2 and Universal Selection tests.
- [ ] Browser-check category, brand, collection, product, and background controls before proceeding.

### Task 4: Unify `ذخیره تنظیمات` and `انجام شد` behind one save operation

**Files:**
- Modify: R3 modal/editor JavaScript and/or form orchestration identified by Task 1.
- Modify endpoint handling only if runtime evidence requires it.
- Test: new save-contract regressions.

**Interfaces:**
- Produces one operation conceptually equivalent to `saveActiveR3Settings({ closeOnSuccess: boolean })` (exact function name may follow existing code style).
- Inner submit calls it with `closeOnSuccess=false` or delegates to the same underlying form submit path.
- Footer Done calls it with `closeOnSuccess=true`.

- [ ] Write a failing regression proving inner Save persists and keeps the modal open.
- [ ] Write a failing regression proving Done persists, waits for success, then closes and refreshes preview.
- [ ] Write a failing regression proving validation/error responses keep the modal open.
- [ ] Implement one shared save path with a double-submit guard.
- [ ] Run the three save regressions to GREEN.
- [ ] Verify no second persistence implementation remains in the modal footer.

### Task 5: Run cross-section browser QA and automated regression

**Files:**
- Test/report only unless a new independently reproduced defect is found; any new defect must repeat RED -> GREEN.

**Interfaces:**
- Produces: Phase 1 acceptance evidence.

- [ ] Category: switch automatic/manual; select/reorder; save; verify preview.
- [ ] Brand: select 5 from a larger set; reorder; save; verify only selected brands.
- [ ] Collection: automatic/manual; select/reorder; save.
- [ ] Product: automatic source and manual product selection.
- [ ] Background, display mode, item limit, responsive, motion, destination.
- [ ] Header/footer edit popups and back button.
- [ ] Verify edit-mode actions never trigger customer login.
- [ ] Run `manage.py check`.
- [ ] Run `manage.py makemigrations --check --dry-run`.
- [ ] Run the full Storefront Builder test suite required by the current project baseline.
- [ ] Run `git diff --check`.

### Task 6: Commit, push, and stop at the Phase gate

**Files:**
- No new behavior.

**Interfaces:**
- Produces: reviewable Phase 1 branch with root-cause report and test/browser evidence.

- [ ] Review `git status` and ensure only intended Phase 1 files changed.
- [ ] Commit with a focused message describing the root cause, not merely symptoms.
- [ ] Push normally to `rastisi5/claude/storefront-builder-phase1-repair` with no force.
- [ ] Report: root cause, files changed, tests run/counts, browser QA results, commit SHA, remaining known issues.
- [ ] STOP. Do not start Phase 2 until the human explicitly approves Phase 1.
