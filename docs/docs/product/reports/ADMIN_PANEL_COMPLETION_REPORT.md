# Admin Panel Completion Program — Status Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update, following the
same discipline established in every prior phase report in this session
— every claim below is either verified by a passing test or a command's
actual output, or named explicitly as a limitation, never asserted
without evidence.

---

## 1. Executive Summary

The request that produced this report ("RASTISI — ADMIN PANEL COMPLETION
PROGRAM") asks for production-ready completion of essentially the entire
Merchant Admin surface of this platform across 60 sections: every
subsystem from Store dashboard and settings through products, inventory,
orders, shipping, customers, promotions, content, theme, domains, SEO,
reports, notifications, audit logs, import/export, staff/permissions, and
a battery of cross-cutting audits (UI, accessibility, security, tenant
isolation, service-layer, DB constraints, migration safety), plus a
38-section completion report and named end-to-end workflow tests.

**This is not achievable to genuine production quality in a single
session**, and this report does not pretend otherwise. What follows is
an honest account of what this phase actually delivered, verified
against the codebase as it stood at the start of this phase (commit
`d6c822d`, the tip of the completed Phase 1F work), plus a complete,
evidence-based inventory of every other subsystem's real state.

**What this phase delivered, fully, with tests:**

1. **Staff & Membership Management** (§34) — a complete dashboard UI
   (add/change-role/revoke/reactivate/transfer-ownership) on top of the
   `StoreMembership` model and `STAFF_MANAGE` permission that have
   existed since Phase 1B but never had a view, route, or template
   anywhere in the codebase. Owner-only, fully tenant-isolated, 40 new
   tests. See §5.
2. **Inventory Ledger** (§16) — a new append-only `StockMovement` model
   and `inventory_service`, wired into order creation and cancellation,
   that **fixes two real, pre-existing correctness bugs** discovered
   while building it (detailed in §6): variant order lines decremented
   the wrong stock counter, and canceling an order never restocked
   anything. 29 new tests. See §6.

**Everything else in the 60-section request remains at whatever state it
was in before this phase** — for most subsystems, that is a working
partial implementation from earlier phases (Phase 1B–1F), not nothing;
for several (returns/refunds, coupons/promotions admin UI, tax settings,
audit logs, data import/export, customer segments, blog admin, warehouses)
it is genuinely missing. §7 is a complete, section-by-section inventory
using exactly the vocabulary the request specifies (Complete / Partial /
Placeholder / Broken / Missing / Not applicable) — nothing is glossed
over as "mostly done" when it is not.

---

## 2. Baseline Verification

Before any new code was written, the existing state was verified rather
than assumed:

```
git status --short         → clean, HEAD at d6c822d
python manage.py check     → System check identified no issues (0 silenced)
manage.py makemigrations --check --dry-run   → No changes detected
```

A focused baseline test run across the areas most relevant to this
phase's candidate subsystems (dashboard services, authorization,
catalog, product/order/customer/settings views, industry template
services, content) — 1,066 tests — passed cleanly (`OK`), matching the
full-suite result already recorded in the Phase 1F report (2,242/2,242).
This confirmed the platform was in the healthy state the prior phase's
report claimed, before this phase touched anything.

---

## 3. Methodology and Scope Selection

Given the infeasibility of fully completing 60 sections, this phase
applied the same discipline used in every prior phase of this session:
pick a small number of genuinely valuable, clearly-bounded, currently
incomplete subsystems and take them to real production quality — real
persistence, real service-layer logic, real permission/tenant-isolation
enforcement, real tests — rather than producing a shallow pass across
everything or, worse, a backlog with no code behind it.

Two subsystems were selected by direct code inspection (not guesswork):

* **Staff & Membership Management** — because `StoreMembership`'s own
  Phase 1B docstring explicitly named "dashboard integration" as
  deferred, `STAFF_MANAGE` existed in `apps.stores.authorization` marked
  `# reserved — no membership-management UI yet`, and a route grep
  (`grep -n "staff\|membership\|invit" apps/dashboard/urls.py`) returned
  zero matches — a clean, fully-bounded, completely-absent gap with all
  underlying model/permission infrastructure already correct.
* **Inventory Ledger** — because a direct read of
  `apps.orders.services.order_service.create_order_from_cart` surfaced a
  real correctness bug (stock decremented on the wrong model for variant
  order lines) and `change_order_status` had no restock path at all for
  cancellations. No ledger/audit-trail model existed anywhere in the
  codebase. This is squarely inside the request's own §16 and directly
  named prohibited behaviors ("do not mutate inventory without a
  ledger").

Both were carried to completion with migrations, service layers, views,
templates, permission enforcement, tenant-isolation enforcement, and
tests, per this session's standing engineering discipline. Checkpoint
commit `48e6542` captures both.

---

## 4. Delivered This Phase — Staff & Membership Management (§34)

### 4.1 What existed before

`apps.stores.models.StoreMembership` (Phase 1B): full `Role`/
`MembershipStatus` choices, DB-level "exactly one active Owner per Store"
constraint, invite/accept/revoke timestamp fields — but its own docstring
says dashboard integration was deferred. `STAFF_MANAGE` existed as a
permission key in the owner-only permission set with no view behind it.
No nav entry, no route, no template.

### 4.2 What was built

* `apps.stores.services.membership_service` — `add_staff_member`,
  `change_role`, `revoke_membership`, `reactivate_membership`,
  `transfer_ownership`, `list_memberships`, `active_owner_count`.
* Five new dashboard views (`staff_list`, `staff_add`,
  `staff_change_role`, `staff_revoke`, `staff_reactivate`,
  `staff_transfer_ownership`), all gated by `staff_required` +
  `permission_required(STAFF_MANAGE)` — owner-only, since `STAFF_MANAGE`
  is in `apps.stores.authorization._OWNER_ONLY`.
* Two templates (`staff_list.html`, `staff_form.html`) plus a
  generalized `confirm_delete.html` (now accepts an `action_label`
  override so it reads correctly for "لغو عضویت"/"انتقال مالکیت", not
  just "حذف").
* A "اعضای تیم" nav entry, gated by a new `can_manage_staff` context flag.

### 4.3 Key decision (ADR-30)

Adding a staff member grants **immediate `ACTIVE` access** — there is no
token-based invitation the recipient must separately accept. This was a
deliberate choice, not an oversight: building a safe, reachable,
tokenized acceptance flow would require its own delivery-channel decision
(SMS vs. email), a signed-token model, and a genuinely hard reachability
problem (`staff_required` denies every admin-portal route, including a
hypothetical "accept your invite" page, to anyone without an
already-`ACTIVE` membership in that exact Store). This is documented as
an explicit, named limitation, not hidden. See ADR-30 in
`SAAS_DOMAIN_DECISIONS.md` for the full reasoning and alternatives
considered.

### 4.4 Enforcement verified by tests (40 tests, all passing)

* Only `OWNER`-role members can reach any staff-management view or
  action (`ADMINISTRATOR`, `CATALOG_MANAGER`, `ORDER_MANAGER`,
  `CONTENT_EDITOR`, `ANALYST` all get `403`).
* Cross-Store isolation: a membership belonging to another Store 404s on
  every action (change-role, revoke, transfer-ownership); an owner of a
  different Store gets redirected (no membership at all) when visiting
  this Store's admin host.
* The Owner role can never be changed or revoked directly — only via
  `transfer_ownership`, which atomically demotes the current owner and
  promotes the target inside one `select_for_update`-guarded transaction,
  so the DB-level "exactly one active Owner" constraint is never at risk
  of a transient violation.
* Re-adding a previously-revoked member reactivates the same row (no
  duplicate-row `IntegrityError` against `uniq_membership_per_store_user`).
* Invalid phone numbers and attempts to assign the `OWNER` role via the
  generic add/change-role paths are rejected with a clear error, not a
  500.

---

## 5. Delivered This Phase — Inventory Ledger (§16)

### 5.1 What existed before, and the two bugs found

Stock was a bare `PositiveIntegerField` counter on both `Product` and
`ProductVariant`, mutated via direct `F()` updates with no audit trail.
Reading `apps.orders.services.order_service` in full surfaced two real,
previously-undiscovered bugs:

1. **Wrong counter for variant order lines.** `create_order_from_cart`
   decremented `Product.stock` unconditionally, even when the order line
   carried a `variant_id`. `ProductVariant.stock` (the Phase 1D variant
   engine's own per-variant counter) was never touched by checkout. The
   pre-checkout validation (`_lock_and_revalidate_items`) had the
   matching bug: it checked `item.quantity > product.stock`, so an order
   for a variant with `stock=0` could still pass validation as long as
   the *parent* product's stock happened to be positive. This bug was
   silent under the pre-existing test suite only because every existing
   checkout test used simple (non-variant) products.
2. **No restock on cancellation.** `change_order_status` had no code
   path that returned stock when an order transitioned to `CANCELED` —
   canceling a `PENDING`/`PROCESSING`/`SHIPPED` order permanently lost
   the stock decremented at order placement.

### 5.2 What was built

* `apps.catalog.models.StockMovement` — append-only ledger row per
  mutation: `store`, `product`, `variant` (nullable), `order` (nullable),
  `actor` (nullable), `reason` (`order_placed` / `order_canceled` /
  `manual_adjustment`), signed `delta`, `stock_before`, `stock_after`,
  `note`. Migration `0014_stockmovement`.
* `apps.catalog.services.inventory_service` —
  `decrement_stock_for_order_item` (targets variant stock when a variant
  is present, product stock otherwise — fixing bug 1 at its root),
  `restock_order` (reverses every `ORDER_PLACED` movement for an order's
  items — fixing bug 2), `adjust_stock_manually` (absolute-value
  adjustment for a future manual-recount UI), `list_stock_movements`.
* `order_service.py` rewired: `_lock_and_revalidate_items` now validates
  against the correct counter; `create_order_from_cart` calls
  `decrement_stock_for_order_item` per line instead of a raw `F()`
  update; `change_order_status` calls `restock_order` on any transition
  to `CANCELED`.
* Read-only `StockMovementAdmin` in Django admin (mirrors the existing
  `StoreIndustryInstallationAdmin` read-only pattern — no add/change/
  delete, inspection only).
* New dashboard "دفتر موجودی" (Inventory Ledger) page —
  `apps.dashboard.views.inventory_list`/`inventory_table` — paginated,
  searchable by product name/SKU, filterable by reason, gated by the
  existing `INVENTORY_MANAGE` permission (already granted to
  `OWNER`/`ADMINISTRATOR`/`CATALOG_MANAGER`). New nav entry.

### 5.3 Key decision (ADR-31)

The ledger is enforced by convention (one service module owns every
stock mutation) rather than a database trigger, matching this codebase's
existing pattern for every other cross-cutting invariant
(`template_update_service`, `membership_service`) — the reasoning stays
visible in Python, covered by ordinary Django tests, and does not need a
separate SQLite/PostgreSQL trigger implementation. See ADR-31 for full
reasoning and alternatives considered.

### 5.4 Verified by tests (29 tests, all passing)

* A simple-product order decrements `Product.stock` and writes exactly
  one ledger row with the correct `stock_before`/`stock_after`.
* A variant order decrements `ProductVariant.stock`, **not**
  `Product.stock` — verified directly, including a test that sets
  `Product.stock=100` and confirms an order for 999 units of a
  5-in-stock variant is still rejected (proving the fix, not just the
  absence of a crash).
* Canceling a `PENDING` or `PROCESSING` order fully restores stock and
  writes an `ORDER_CANCELED` ledger row referencing the order; delivering
  an order (not canceling it) never restocks.
* `restock_order` safely no-ops for an order with no items, and skips
  (rather than crashing on) an `OrderItem` whose `product` was
  since deleted (`SET_NULL`).
* `adjust_stock_manually` records signed deltas correctly and returns
  `None`/writes nothing when the new value equals the current one.
* Cross-Store isolation: `list_stock_movements` and the dashboard ledger
  page never surface another Store's movements; non-privileged roles
  (`ANALYST`) get `403` on the ledger page, `CATALOG_MANAGER` is allowed.

---

## 6. Capability Inventory Matrix

Per the request's own mandated vocabulary. "Backend state" = persistent
model + service layer; "Frontend state" = dashboard view/template;
"Test state" = automated coverage exists. This is a subsystem-level
inventory (the request's literal ask — a row per UI button across the
entire platform — would be thousands of rows and is not the useful unit
of truth here); each row is grounded in a specific file/route checked
during this phase, not a guess.

| Subsystem | Backend | Frontend | Tenant isolation | Tests | Status |
|---|---|---|---|---|---|
| Store dashboard (metrics, sales chart) | Complete | Complete | Enforced | Yes | Complete |
| Store settings (shop info, appearance, finance) | Complete | Complete | Enforced | Yes | Complete |
| Industry templates (install/preview/update) | Complete | Complete | Enforced | Yes | Complete (Phase 1F) |
| Categories + Category Attribute Schema | Complete | Complete | Enforced | Yes | Complete |
| Attributes + values | Complete | Complete | Enforced | Yes | Complete |
| Brands | Complete | Partial (no dedicated CRUD page found; used via product form filter) | Enforced | Partial | Partial |
| Products (CRUD, publish, media, specs) | Complete | Complete | Enforced | Yes | Complete |
| Options/Variants engine | Complete | Complete | Enforced | Yes | Complete (Phase 1D) |
| **Inventory ledger** | **Complete** | **Complete** | **Enforced** | **Yes** | **Complete (this phase)** |
| Warehouses / stock locations | Missing | Missing | N/A | N/A | Not applicable — single-location stock model throughout; no warehouse concept exists anywhere in the schema |
| Orders (list/detail/status transitions) | Complete | Complete | Enforced | Yes | Complete |
| Payments (gateways, transactions) | Complete | Partial (list/detail only, no manual reconciliation UI) | Enforced | Yes | Partial |
| Returns and Refunds | Missing | Missing | N/A | N/A | Missing — no `Return`/`Refund` model exists; `Order.PaymentStatus.REFUNDED` is a terminal status value with no workflow, no partial-refund tracking, no restock-on-refund path |
| Shipping methods | Complete (model) | Placeholder (toggle-only; no add/edit/zone UI) | Enforced | Partial | Partial |
| **Staff / Memberships / Roles** | **Complete** | **Complete** | **Enforced** | **Yes** | **Complete (this phase)** |
| Customers (list/detail, addresses, wishlist) | Complete | Complete | Enforced (via Order relation) | Yes | Complete |
| Customer notes / segments | Missing | Missing | N/A | N/A | Missing — no model, no UI |
| Coupons / Discounts / Promotions | Complete (model exists) | Missing | **Not enforced — `Coupon` has no `store` FK; global across all tenants** | Partial (service-level tests only) | Partial, with a real tenant-isolation gap flagged in §8 |
| Content pages | Complete | Complete | Enforced | Yes | Complete |
| Menus / navigation | Complete | Complete | Enforced | Yes | Complete |
| Banners / hero slides | Complete | Complete | Enforced | Yes | Complete |
| Footer settings | Complete | Complete | Enforced | Yes | Complete |
| Social links | Complete | Complete | Not Store-scoped (global, like `SmsTemplate`) | Yes | Partial |
| Blog | Complete (model) | Missing | N/A | Partial (model tests only) | Missing (no dashboard admin UI) |
| Storefront theme / appearance | Complete | Complete | Enforced | Yes | Complete |
| Domain / subdomain settings | Complete (model + resolution) | Missing (no dashboard CRUD for `StoreDomain`) | Enforced at resolution layer | Partial | Partial |
| SEO (product-level) | Complete | Complete | Enforced | Yes | Complete |
| Tax settings | Missing | Missing | N/A | N/A | Missing — no tax model/config anywhere |
| Currency settings | Missing | Missing | N/A | N/A | Missing — all amounts are Toman-only, no currency model |
| Invoice settings | Partial (invoices derived from Order) | Complete (view-only list/detail) | Enforced | Yes | Partial |
| Legal / policy pages | Complete (via generic ContentPage) | Complete | Enforced | Yes | Complete (no dedicated policy-page type, but the generic CMS covers it) |
| SMS notifications | Complete | Complete (templates, logs, test-send) | Not Store-scoped (global `SmsTemplate`, pre-existing design) | Yes | Partial |
| Audit logs (admin actions) | Partial (`OrderStatusHistory`, `StoreTemplateUpdate` history, `StockMovement` all exist as domain-specific logs) | Partial (each shown in its own context, no unified audit log view) | Enforced per-domain | Yes (per-domain) | Partial — no single cross-cutting "who did what" log |
| Data import | Missing | Missing | N/A | N/A | Missing |
| Data export | Missing | Missing | N/A | N/A | Missing |
| Bulk actions | Complete (products only: status/category/delete) | Complete (products only) | Enforced | Yes | Partial — only products has bulk actions; orders/customers do not |
| Reports / analytics | Complete | Complete | Enforced | Yes | Complete |
| Subscription / plan visibility | Missing | Missing | N/A | N/A | Missing — `SUBSCRIPTION_MANAGE` permission key exists, reserved, no model or view |

---

## 7. Cross-Cutting Audits

A full line-by-line audit of every dashboard template/view against
WCAG/OWASP checklists (the request's §42–48) was not performed this
phase — that is itself a multi-day effort at genuine rigor and was not
where this phase's limited time was spent. What can be stated with
evidence from this phase's own work and direct inspection:

* **Tenant isolation** — every view touched or added this phase
  (staff management, inventory ledger) enforces Store scoping via
  `_resolve_dashboard_store`/`request.store` and is covered by an
  explicit cross-Store 404/redirect test. Two **pre-existing** tenant-
  isolation gaps were found during this phase's inventory pass and are
  flagged, not fixed (out of this phase's selected scope): `Coupon` has
  no `store` FK at all (global across every tenant on the platform), and
  `SmsTemplate` is likewise global-not-per-Store. Both predate this
  phase and are not touched by it.
* **Migration safety** — the one new migration this phase added
  (`0014_stockmovement`) is a pure `CreateModel`, no data migration, no
  backfill needed, verified via `makemigrations --check --dry-run`
  returning "No changes detected" after being applied.
* **Service-layer discipline** — both new subsystems keep all business
  logic (role transitions, ownership transfer, stock ledger writes) in
  `apps/*/services/*.py`, never in views, matching the pattern audited
  and confirmed in every prior phase report.
* **DB constraints** — `StockMovement` has an index on
  `(store, product, -created_at)` for the ledger page's query pattern;
  `StoreMembership`'s pre-existing constraints (`uniq_active_owner_per_store`,
  `uniq_membership_per_store_user`) were relied on, not duplicated.

---

## 8. Test Results

New tests this phase, all passing:

| Test file | Count |
|---|---|
| `apps/stores/tests/test_membership_service.py` | 20 |
| `apps/dashboard/tests/test_staff_views.py` | 20 |
| `apps/catalog/tests/test_inventory_service.py` | 14 |
| `apps/dashboard/tests/test_inventory_views.py` | 8 |
| New cases in `apps/orders/tests/test_order_service.py` | 7 |
| **Total new tests this phase** | **69** (plus 2 pre-existing fixtures fixed, §8) |

Verification runs performed this phase:

```
python manage.py check                                    → 0 issues
python manage.py makemigrations --check --dry-run         → No changes detected
python manage.py test apps.stores.tests.test_membership_service \
    apps.dashboard.tests.test_staff_views                 → 40/40 OK
python manage.py test apps.orders                          → 215/215 OK (post-fix)
python manage.py test apps.orders.tests.test_order_service \
    apps.catalog.tests.test_inventory_service              → 39/39 OK
python manage.py test apps.dashboard.tests.test_inventory_views  → 8/8 OK
python manage.py test apps.stores apps.dashboard            → 988/988 OK
python manage.py seed_industry_templates                   → 30 templates, all production_ready
python manage.py validate_industry_templates --strict      → 30/30 valid, 0 errors, 15 warnings
```

A full-suite run (`python manage.py test`) was launched as the final
validation step; its result is recorded in §9 once complete (background
task, not fabricated ahead of completion).

Two **pre-existing** test fixtures required a one-line fix each — not a
new bug, but a test that had been silently relying on the bug this phase
fixed: `apps/orders/tests/test_checkout_correctness.py`'s
`VariantRevalidationTests`/`OrderSnapshotSurvivesLaterChangesTests` created
variants via `create_variant(...)` without specifying `stock`, defaulting
to `stock=0`; before this phase's fix, the code checked `product.stock`
(non-zero in these fixtures) and the tests passed by coincidence. After
fixing the code to check `variant.stock` correctly, these two tests
failed exactly as expected — this is the fix working, not a regression —
and were corrected to pass `stock=10` explicitly, matching their actual
intent (testing variant validity/snapshotting, not insufficient stock).

---

## 9. Full-Suite Validation Result

<!-- FULL_SUITE_RESULT_PLACEHOLDER -->

---

## 10. Architecture Decisions Added

* **ADR-30** — Staff management grants immediate `ACTIVE` access on add;
  token-based invitation acceptance is explicitly out of scope, with
  reasoning and alternatives considered documented in full.
* **ADR-31** — Inventory is an append-only `StockMovement` ledger, not a
  bare counter; order-level stock mutation targets the correct field
  (variant vs. product) and cancellation restocks. Both bugs found and
  fixed are documented with the exact failure scenario.

Both are recorded in `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`,
with a summary-table row each, following the same format as every prior
ADR in this document.

---

## 11. Known Limitations (Complete List, Not Buried)

1. No token-based staff invitation/acceptance flow (ADR-30) — adding
   staff grants immediate access.
2. `adjust_stock_manually` exists in the service layer but has no
   dashboard view yet — a manual stock-recount UI is a natural, small
   follow-up but was not this phase's selected scope.
3. `Coupon` and `SmsTemplate` are global, not Store-scoped — a real,
   pre-existing tenant-isolation gap, unrelated to this phase's changes,
   flagged for a future dedicated PR.
4. Returns/Refunds, tax settings, currency settings, customer segments,
   warehouses/stock locations, subscription/plan visibility, data
   import/export, and a unified cross-cutting audit log all have **no
   model and no UI** — genuinely missing, not partially built.
5. Shipping methods, brands, domains, and invoices have models and
   partial read-only or toggle-only dashboard surfaces but no full CRUD
   UI.
6. A full WCAG/OWASP line-by-line audit of the entire existing dashboard
   template set was not performed this phase (§7).
7. The 5 named end-to-end workflow tests requested (New Store Setup,
   Order Operations, Refund and Restock, Template Update, Staff
   Security) were not all written as dedicated end-to-end test classes
   this phase — the equivalent coverage exists distributed across the
   unit/integration tests listed in §8 and prior phase reports, but a
   "Refund and Restock" test cannot exist yet since no Refund model
   exists (see limitation 4).

---

## 12. Recommended Next Checkpoints

In priority order, based on what this phase's inventory pass found to be
both high-value and well-bounded (the same criteria used to select this
phase's two subsystems):

1. **Returns/Refunds** — a `Refund` model plus a service that reverses
   payment status and calls `inventory_service.restock_order` (already
   built) or a partial-quantity variant of it.
2. **Coupon Store-scoping** — add `store` FK to `Coupon`, migrate
   existing rows, close the multi-tenant leak flagged in §11.3.
3. **Shipping method + Domain full CRUD UI** — the models and
   permissions already exist; this is UI-only work, similar in shape to
   this phase's staff-management build.
4. **Manual stock-adjustment dashboard view** — wire the already-built
   `adjust_stock_manually` service function into a view/template.
5. **Unified audit log** — a cross-cutting view over the existing
   per-domain history tables (`OrderStatusHistory`, `StoreTemplateUpdate`,
   `StockMovement`) rather than a new logging system from scratch.

---

## 13. Conclusion

This phase delivered two complete, tested, production-quality subsystems
— Staff & Membership Management and the Inventory Ledger — chosen because
they were the clearest, most valuable, most fully-bounded gaps found by
direct code inspection, and because building the Inventory Ledger
surfaced and fixed two real correctness bugs in the existing order
pipeline. Everything else in the 60-section request is inventoried
honestly in §6 with no subsystem's state overstated. The full-suite
result in §9 is the final gate before this checkpoint is considered done.
