# Storefront Builder V2 — Phase 1 Audit & Prototype Shell

## Baseline

- Source: verified Git bundle `RastiSi4-fix-v5-golden-visual-fidelity-v1-20260815-170316.bundle`
- Branch: `fix/v5-golden-visual-fidelity-v1`
- Baseline SHA: `4d97cfb3c57d46a183fd4e46bb8b3868037af8d3`
- UI reference: `rastisi_builder_v2_prototype(2).html`

## Phase 1 objective

Phase 1 intentionally changes the **editor shell and information architecture**, not the storefront renderer or the persistence model. The production editor now follows the approved prototype:

1. 64px dark topbar.
2. Three-pane desktop workspace: Library / Canvas / Inspector.
3. Real page selector for all six `StorefrontPage.PageType` values.
4. Permanent Library with searchable, registry-backed section cards.
5. Real Draft preview iframe in the center Canvas.
6. Permanent Inspector using the existing server-backed settings endpoints.
7. Header, Footer and Appearance use the same Inspector.
8. Floating Add button + add-section modal, both using the existing server allowlist/write endpoint.
9. Desktop/Mobile canvas switch and existing fullscreen mode.
10. Existing Draft / Publish / History / Discard lifecycle remains unchanged.

## Geometry copied from the prototype

| Prototype contract | Production Phase 1 |
|---|---|
| Topbar `64px` | `64px` |
| Main grid `290px 1fr 320px` | `290px minmax(0,1fr) 320px` |
| Workspace max width `1180px` | `1180px` |
| Mobile canvas max width `430px` | `430px` |
| Background `#f4f6fb` | `#f4f6fb` |
| Brand `#6d4aff` | `#6d4aff` |
| Panel border `#e5e9f2` | `#e5e9f2` |
| Panel radius `16px` | `16px` |

## Existing backend capabilities retained

The audit found that the backend is already substantially ahead of the prototype mock:

- `StorefrontLayout` has independent `published_version` and `draft_version` pointers.
- Every version owns six explicit `StorefrontPage` records.
- `StorefrontSection` is page-owned and has `stable_id`, `row_key`, `row_span`, `is_locked`, responsive settings and validated settings JSON.
- The Section Registry currently contains 34 registered section definitions.
- Add / reorder / move / duplicate / toggle / lock / remove / settings / media endpoints already exist and are store-scoped.
- Preview already sends same-origin `postMessage` events for direct section selection and reorder.
- Header, Footer and Appearance already participate in the Draft/Publish lifecycle.
- The preview iframe and public storefront use the shared renderer path; Phase 1 does not introduce a second renderer.

## Important Phase 1 implementation decision

The old visible section list is no longer part of the primary editor UI because it is not present in the approved prototype. It remains as a hidden `#storefrontSectionList` **mutation mirror** so all existing HTMX mutation endpoints continue to use the proven server response as source of truth. After a mutation, the existing `htmx:afterSwap` hook reloads the real preview iframe.

This avoids creating client-only section state or duplicating backend mutation logic during a visual-shell phase.

## Inspector integration

The old overlay `sfbDrawerBody` was replaced by the permanent `#sfbInspectorBody` pane. The same existing endpoints are reused:

- Section settings → `storefront-builder-section-settings`
- Header → `storefront-builder-header`
- Footer → `storefront-builder-footer`
- Appearance → `storefront-builder-appearance`

No new persistence endpoint was introduced.

## Deliberately deferred to Phase 2

These are behavioral features, not Phase 1 shell work:

- Real Undo / Redo stack (buttons are intentionally disabled but visually present).
- Dragging a Library block directly into an arbitrary Canvas insertion point.
- Inspector restructuring into Basic / Advanced tabs for every block type.
- Lock/unlock control surfaced directly in the Canvas toolbar.
- Full row/column composition controls directly on the Canvas.
- Autosave semantics for partially edited Inspector forms.
- Keyboard reordering and richer accessibility interactions.
- Dedicated mobile editor navigation between Library / Canvas / Inspector.

Existing server behaviors remain available where already implemented; Phase 2 will expose and unify them in the prototype interaction model.

## Validation performed in the build sandbox

The sandbox used for artifact construction does not have Django installed, therefore the Django test suite could not be executed here. The following static checks passed:

- Bundle verification: PASS.
- Baseline SHA verification: PASS.
- `git diff --check`: PASS.
- Python `compileall` for `apps/storefront_builder`: PASS.
- `tinycss2` parse of `storefront_builder.css`: 0 parse errors.
- `node --check` for the JavaScript extracted from `editor.html`: PASS.
- Django-template control-block count sanity check (`if/for/block`): balanced.
- Key prototype geometry markers found in the production CSS.

The Django checks/tests must be run on the user's project virtualenv after applying the Phase 1 patch.
