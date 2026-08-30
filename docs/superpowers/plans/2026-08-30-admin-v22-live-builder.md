# RastiSi Admin V2.2 Live Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the real RastiSi merchant admin to the approved V2.2 information architecture and full-screen live Storefront Builder without replacing the existing Django/HTMX business logic or removing the dashboard setup checklist.

**Architecture:** Keep `dashboard/base_admin.html` as the compatibility shell and layer a focused Admin V2 stylesheet/JavaScript command palette over existing pages. Keep the existing Storefront Builder engine, Draft/Preview/Publish lifecycle, section registry, media endpoints, HTMX autosave, and iframe preview; reshape the editor into a full-screen preview/edit workspace and expose contextual deep shortcuts to the existing real admin editors rather than creating parallel CRUD flows.

**Tech Stack:** Django 5.2 templates/views, HTMX, Alpine.js, vanilla JavaScript, existing RastiSi CSS, Python/Django TestCase.

**Spec:** User-approved `RastiSi_Admin_V2.2_Master_Prototype.html` behavior from the current conversation.

## Global Constraints

- Work only in dedicated worktree `D:\Projects\RastiSi4_Storefront_Palette64` on branch `qa/storefront-palette64` at base `6f4d21881af53490e621e6a45c90e84838da2aef`.
- Do not switch, merge, rebase, commit, push, or force-push.
- Preserve the five already-reviewed Palette64 changes exactly; Admin V2 must not rewrite `appearance_registry.py`, `palette_pack_64.py`, `appearance_panel.html`, `test_palette_pack_64.py`, or the third-party palette notice.
- Preserve `setup_checklist` behavior and rendering on the dashboard, including complete/incomplete states, progress, locked steps, and next-step action.
- Preserve current permission-aware navigation and all existing Dashboard URLs.
- Preserve Storefront Builder Draft/Preview/Publish, Undo/Redo, section/container operations, preview isolation, and existing media/product selection logic.
- Deep shortcuts must open existing real RastiSi editors in an embedded workspace; no duplicate product/category/brand/collection/media CRUD implementation.
- The embedded Deep Workspace must not disable clickjacking protection globally: only authenticated dashboard-namespace requests carrying `?embed=1` may be framed, and only as `SAMEORIGIN`.
- No database migration is introduced.

---

### Task 1: Lock Admin V2 compatibility contracts

**Files:**
- Create: `apps/dashboard/tests/test_admin_v22_shell.py`
- Modify: `apps/dashboard/templates/dashboard/base_admin.html`
- Preserve: `apps/dashboard/templates/dashboard/dashboard.html`

**Interfaces:**
- Consumes: current `base_admin.html` blocks and permission variables.
- Produces: `page_actions` block, command-palette markup, V2 asset includes, static expanded navigation behavior.

- [ ] **Step 1: Write failing tests** asserting V2 assets/command palette/page actions are absent before implementation and that dashboard source still contains `setup_checklist`.
- [ ] **Step 2: Run focused test and confirm RED.**
- [ ] **Step 3: Add V2 asset includes and command palette shell without changing existing page block names.**
- [ ] **Step 4: Run focused test and confirm GREEN.**

### Task 2: Build Admin V2 visual shell and global deep search

**Files:**
- Create: `apps/dashboard/static/css/admin_v2.css`
- Create: `apps/dashboard/static/js/admin_v2.js`
- Modify: `apps/dashboard/templates/dashboard/base_admin.html`

**Interfaces:**
- Consumes: existing `.sidebar`, `.nav-group`, `.topbar`, `.content`, `.search-box` markup.
- Produces: `window.RastiSiAdminV2`, Ctrl/Cmd+K command palette, embedded-page mode via `?embed=1`, static readable sidebar groups.

- [ ] **Step 1: Add tests for search terms `لوگو`, `سازنده فروشگاه`, `کالاها`, and `دسته‌بندی‌ها`.**
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Implement command registry using existing Django URL tags and client-side filtering.**
- [ ] **Step 4: Implement CSS override matching approved V2 shell while retaining old components.**
- [ ] **Step 5: Confirm GREEN.**

### Task 3: Convert Storefront Builder to full-screen Preview/Edit workspace

**Files:**
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`
- Modify: `apps/storefront_builder/templates/storefront_builder/preview.html`
- Create: `apps/storefront_builder/static/css/storefront_builder_v22.css`
- Create: `apps/storefront_builder/static/css/storefront_builder_preview_v22.css`
- Create: `apps/storefront_builder/tests/test_admin_v22_live_builder.py`

**Interfaces:**
- Consumes: existing `storefrontEditor()`, `fullscreen`, `sidebarCollapsed`, `inspectorCollapsed`, `selectSection()`, iframe preview.
- Produces: `builderMode`, `setBuilderMode(mode)`, topbar Preview/Edit switch, Structure button, default full-screen workspace.

- [ ] **Step 1: Write tests for default full-screen state, Preview/Edit controls, Structure control, and preserved Publish/Undo/Redo contracts.**
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Extend existing Alpine state minimally; do not replace editor engine.**
- [ ] **Step 4: Add V2.2 CSS override that makes the canvas primary and panels drawers.**
- [ ] **Step 5: Confirm GREEN.**

### Task 4: Add contextual deep shortcuts to existing real editors

**Files:**
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/container_state.html`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/header_panel.html`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/partials/footer_panel.html`
- Modify: `apps/catalog/templates/catalog/partials/product_card.html`
- Modify: `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`
- Test: `apps/storefront_builder/tests/test_admin_v22_live_builder.py`

**Interfaces:**
- Consumes: section key, existing Dashboard URL names, existing section media endpoints.
- Produces: `openDeepWorkspace(url, title)`, `closeDeepWorkspace()`, embedded iframe workspace, section-specific shortcuts.

- [ ] **Step 1: Write failing tests for section-key metadata and shortcuts for product, category, brand, collection, hero slider, and banner sections.**
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Add `data-section-key` to placement state.**
- [ ] **Step 4: Add shortcut buttons to inspector that open existing pages/endpoints with `openDeepWorkspace`.**
- [ ] **Step 5: Add deep workspace overlay preserving the Builder underneath and a clear return action.**
- [ ] **Step 6: Add exact Product-card → Product editor bridge plus Header/Footer deep editors.**
- [ ] **Step 7: Confirm GREEN.**

### Task 5: Preserve and verify existing live-edit behaviors

**Files:**
- Test: `apps/storefront_builder/tests/test_admin_v22_live_builder.py`
- No production rewrite unless a regression is found.

**Interfaces:**
- Consumes: existing autosave and `htmx:afterSwap` preview refresh logic.
- Produces: regression assertions that product manual selection, media management, Preview frame, and Draft/Publish URLs remain present.

- [ ] **Step 1: Add regression assertions for `productSectionForm`, `storefront-builder-section-product-search`, `storefront-builder-section-media-list`, preview iframe, publish form, and history URLs.**
- [ ] **Step 2: Run focused tests.**
- [ ] **Step 3: Run `python manage.py check`.**
- [ ] **Step 4: Run `python manage.py makemigrations --check --dry-run`.**
- [ ] **Step 5: Run Storefront Builder regression suite and Admin UX tests.**
- [ ] **Step 6: Run `git diff --check` and exact changed-path validation.**

### Task 6: Browser review handoff

**Files:**
- No new production files.

**Interfaces:**
- Consumes: successful local automated QA.
- Produces: uncommitted worktree ready for browser review on the isolated QA database snapshot.

- [ ] **Step 1: Start the dedicated worktree server on port 8010.**
- [ ] **Step 2: Verify Dashboard checklist remains visible and functional.**
- [ ] **Step 3: Verify Ctrl+K search for `لوگو` routes to Appearance/Header.**
- [ ] **Step 4: Verify Builder opens full-screen, Preview/Edit switch works, clicking a section opens its real inspector.**
- [ ] **Step 5: Verify product section manual selection and hero/banner media deep shortcuts open real editors and return to the same Builder session.**
- [ ] **Step 6: Do not commit/push until browser review is explicitly accepted.**

### Exact visible-item routing

Builder-preview-only metadata is attached to product cards, category tiles, brand tiles, collection tiles, hero slides, and promotional banners. Clicking those visible objects in Edit mode sends one generic `sfb:openEntityEditor` message; the parent resolves it to the existing product/category/brand/collection/media edit endpoint inside the Deep Workspace. Public storefront markup gets no edit metadata.
