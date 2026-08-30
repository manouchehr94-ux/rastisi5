# Claude Storefront Builder Phase 1 Repair — Design

## Purpose

Freeze the exact current RastiSi Storefront Builder/Admin V2/Palette64/R3.3.2 working-tree state on a dedicated GitHub branch, then let Claude Code diagnose and repair the live Builder interaction layer from the real code instead of from patch descriptions.

## Baseline branch

- Repository: `manouchehr94-ux/rastisi5`
- Trusted remote: `rastisi5`
- Current QA worktree: `D:\Projects\RastiSi4_Storefront_Palette64`
- Required current branch: `qa/storefront-palette64`
- Required base HEAD: `6f4d21881af53490e621e6a45c90e84838da2aef`
- Official storefront branch that must remain untouched: `feature/storefront-builder-v3-redesign`
- Claude Phase 1 branch: `claude/storefront-builder-phase1-repair`
- No force push, merge, rebase, pull, reset --hard, or clean.

The baseline commit is created from the current working tree using a temporary Git index. The current QA branch, index, and uncommitted files are not switched or rewritten.

## Phase 1 problem statement

The approved R3 live-editor shell is visible in the browser, but editor controls loaded inside the R3 modal do not behave reliably:

1. Universal Selection controls show `انتخاب خودکار` and `انتخاب دستی`, but clicking them does not reveal/change the corresponding controls.
2. Background settings and apparently other settings inside the same modal do not reliably apply.
3. There are two save affordances with unclear/inconsistent semantics: the inner `ذخیره تنظیمات` and the modal footer `انجام شد`.
4. Required save contract:
   - `ذخیره تنظیمات`: save the active settings form and keep the modal open.
   - `انجام شد`: save the exact same active settings form, and only after a successful save close the modal and refresh the preview.
   - Validation/server errors must keep the modal open and show the error.
   - No double-submit and no separate persistence implementation for the two buttons.
5. Because multiple controls fail together, Claude must trace the shared lifecycle before changing individual controls.

## Diagnostic boundary

Claude must trace the end-to-end path:

`Preview click -> parent R3 modal -> HTMX content load/swap -> Alpine/component initialization -> field interaction -> form submit/autosave -> server validation/save -> preview refresh -> modal close/keep-open semantics`.

Primary files to inspect include:

- `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html`
- shared background/responsive/motion/destination partials
- `apps/storefront_builder/views.py`
- existing R2/R3/R3.2/Universal Selection tests

The likely class of failure may involve HTMX/Alpine hydration or modal event ownership, but this is a hypothesis only. Claude must prove the root cause from runtime/code evidence.

## Constraints

- Preserve existing Draft/Preview/Publish data model and endpoints unless evidence proves an endpoint bug.
- Preserve StorefrontSection/StorefrontContainer/StorefrontCell architecture.
- Preserve Palette64 behavior and published theme semantics.
- Preserve current templates including dark_digital.
- No model or migration change unless root-cause evidence demonstrates it is unavoidable.
- No redesign in Phase 1. Repair behavior first.
- Do not touch authentication/onboarding work or unrelated branches.

## Acceptance criteria — Phase 1

Browser QA must verify at minimum:

- Category section: automatic/manual selection switches visibly and works.
- Brand section: select only a subset (e.g. 5 of many brands), reorder, save, preview reflects selection.
- Collection section: same manual/automatic behavior.
- Product section: automatic sources and manual product selection both work.
- Background mode/color/palette controls interact and persist.
- Display mode and item-count controls persist.
- Responsive, motion, destination, and other settings available to the section continue to work.
- `ذخیره تنظیمات` saves but keeps modal open.
- `انجام شد` saves, waits for success, closes modal, and refreshes preview.
- Error response does not close modal.
- Header/footer/other edit popups still open with the R3 modal contract.
- Customer login must not appear from edit-mode interactions.

Automated regression must cover the root cause and both save-button contracts before implementation is considered complete.

## Phase gate

Claude must stop after Phase 1, commit/push the repair branch, and report evidence. Phase 2 may not start until the human explicitly approves browser QA.

## Phase 2 direction after approval

After Phase 1 acceptance, create a separate branch from the accepted Phase 1 HEAD:

`claude/admin-v2-phase2-prototype-alignment`

Use `reference/RastiSi_Admin_V2.2_Master_Prototype.html` (also committed under `docs/prototypes/` by the handoff publisher) as the visual/interaction reference, while preserving real RastiSi endpoints and data flows.

The target IA is:

- Global command search.
- Sidebar groups, with each major destination one click away:
  - عملیات: Overview, Orders, Products, Inventory, Customers
  - فروش: Shipping, Discounts, Marketing
  - فروشگاه: Storefront Builder, Appearance, Content
  - مدیریت: Reports, Settings
- Products internal tabs: همه کالاها، دسته‌بندی‌ها، ویژگی‌ها و متغیرها، برندها، موجودی، نقد و بررسی‌ها.
- Appearance internal tabs: قالب، رنگ‌ها، فونت و تایپوگرافی، چیدمان، هدر، فوتر، تنظیمات پیشرفته.
- Contextual top actions instead of one global action set.
- Important operations reachable within two clicks and understandable by a nontechnical merchant.

Phase 2 is a separate implementation and review cycle, not part of the repair commit.
