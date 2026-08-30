# Admin V2 Phase 2 Prototype Alignment — Deferred Plan

**GATE:** Do not execute this plan until the human explicitly accepts Phase 1 browser QA.

## Branch

Create `claude/admin-v2-phase2-prototype-alignment` from the accepted HEAD of `claude/storefront-builder-phase1-repair`.

## Reference

Use `docs/prototypes/RastiSi_Admin_V2.2_Master_Prototype.html` as the approved UX reference. Reuse real RastiSi routes/endpoints/models; do not build fake parallel management screens.

## Target information architecture

- Global command search.
- Sidebar groups with direct one-click destinations:
  - عملیات: Overview, Orders, Products, Inventory, Customers
  - فروش: Shipping, Discounts, Marketing
  - فروشگاه: Storefront Builder, Appearance, Content
  - مدیریت: Reports, Settings
- Products tabs: همه کالاها، دسته‌بندی‌ها، ویژگی‌ها و متغیرها، برندها، موجودی، نقد و بررسی‌ها.
- Appearance tabs: قالب، رنگ‌ها، فونت و تایپوگرافی، چیدمان، هدر، فوتر، تنظیمات پیشرفته.
- Settings uses major horizontal tabs and simple internal panels.
- Storefront Builder remains its own major destination.
- Contextual page actions only:
  - Appearance/Content: Preview/Publish where meaningful.
  - Products: Add/Import/Export.
  - Orders: Export/Filter/Bulk.
  - Inventory: Adjust/Stock intake/Report.
- Nontechnical merchant language; no row/cell/container/grid jargon in normal UI.
- Important operations within two clicks.

## Execution order

1. Inventory existing Admin routes/templates and map every prototype destination to a real route.
2. Build the global shell/sidebar/search without changing business logic.
3. Align Products/Inventory/Orders/Customers.
4. Align Appearance/Content/Storefront Builder entry points without regressing Phase 1.
5. Align Shipping/Discounts/Marketing/Reports/Settings.
6. Browser QA desktop/mobile/RTL plus regression suites.

Each subsystem must be implemented with its own test-first cycle and review checkpoint. No broad rewrite of backend services is authorized solely for visual alignment.
