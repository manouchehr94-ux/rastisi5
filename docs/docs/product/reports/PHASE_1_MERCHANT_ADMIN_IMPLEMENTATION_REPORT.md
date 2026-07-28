# Phase 1 — Merchant Admin Portal: Progress Report

**Status of this report:** honest, scoped status update — **not** a claim that
"Phase 1" as defined by the originating prompt (full prototype parity across
~20 merchant-admin subsystems: attributes, variants, inventory, wallet,
cashback, referral, industry setup, CMS/page builder, subscriptions, etc.) is
complete. That scope is realistically months of engineering work. This
session delivered one concrete, tested, high-priority foundation stage and
is transparent about everything that remains.

---

## 1. Executive Summary

* **Delivered:** `StoreMembership`-based merchant-dashboard authorization,
  replacing the `is_staff`-only gate that let any staff account reach *any*
  Store's `/admin-panel/` once Host-based resolution picked that Store. This
  was recorded in `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` §10.2/§11.1
  as the highest-priority (`بسیار بالا`) gap in the entire platform and the
  explicit prerequisite ("add permissions") for every other admin feature
  listed in the originating prompt.
* **Not delivered, not started:** the ~20 prototype-parity feature areas
  the originating prompt asked for in the same pass (attribute/variant
  matrix, inventory ledger, wallet, cashback, referral, industry templates,
  CMS/page builder versioning, subscription/billing, etc.). These require
  dedicated follow-up work; see §7.
* The Merchant Admin Portal is **not** "complete" by the Phase 1 definition
  in the originating prompt. It is measurably safer: dashboard access is now
  scoped to the Store the requesting user actually belongs to, not just
  their global `is_staff` flag.

## 2. What Was Verified Before Changing Anything

Direct code inspection (not just the reference doc) confirmed:

* `apps/stores/middleware.py` resolves `request.store` per request but
  explicitly does not make any authorization decision — "nothing downstream
  currently consumes `request.store`" (module docstring, pre-existing).
* `apps/dashboard/decorators.py`'s `staff_required` checked only
  `user.is_authenticated` and `user.is_staff` — no `StoreMembership` check
  existed anywhere in the request path.
* `apps/stores/models.py` already had a fully-built `StoreMembership` model
  (roles, status, invariants, constraints) from an earlier PR, but nothing
  in `apps.dashboard` read from it. It was inert infrastructure.
* Baseline: `python manage.py test` → **1719 tests, 0 failures** before any
  change in this session (confirmed by an actual full run, not assumed).

## 3. What Was Implemented

### 3.1 `apps/stores/authorization.py` (new)

Central module deciding "may this User act on this Store's dashboard, and
with what permission":

* `get_active_membership(user, store)` — the user's `ACTIVE`
  `StoreMembership` row for that exact Store, or `None`. Never matches a
  membership in a different Store, nor an `INVITED`/`REVOKED` row.
* `user_can_access_dashboard(user, store)` — any active membership grants
  baseline dashboard access.
* `ROLE_PERMISSIONS` / `user_has_permission(user, store, permission)` — a
  role→permission registry (`CATALOG`, `ORDERS`, `CUSTOMERS`, `CONTENT`,
  `SETTINGS`, `REPORTS`, `MEMBERSHIP`) giving the existing
  `StoreMembership.Role` choices (owner/administrator/catalog_manager/
  order_manager/content_editor/analyst) real, centrally-defined meaning for
  the first time.

### 3.2 `apps/dashboard/decorators.py`

* `staff_required` now requires **both** `user.is_staff` (unchanged, existing
  bar) **and** an active `StoreMembership` for the Store resolved from the
  request's Host (via the same `resolve_store_for_service` every dashboard
  service call already uses — the Store being authorized is exactly the
  Store the view body acts on). A staff user with no membership in the
  resolved Store, or membership only in a *different* Store, is now
  redirected exactly as a non-staff user always was.
* New `permission_required(permission)` decorator, layered inside
  `staff_required`, for future per-action role gating. **Built but not yet
  applied to any of the 84 existing `@staff_required` view functions** —
  wiring granular per-feature permissions (e.g. only `CATALOG_MANAGER`+ may
  edit products) is follow-up work, not done in this pass.
* The admin login view (`apps.dashboard.views.admin_login`) was
  deliberately left unchanged — it still gates on `is_staff` only. This is a
  known, explicitly tracked asymmetry (see §6).

### 3.3 Tests

* `apps/stores/tests/test_authorization.py` (new) — 16 unit tests on the
  authorization module in isolation (membership lookup, role/permission
  matrix, invited/revoked/cross-store negatives).
* `apps/dashboard/tests/test_membership_authorization.py` (new) — 7
  end-to-end adversarial tests using two real Stores with distinct verified
  domains and Host headers: membership in Store A denied at Store B's host,
  is_staff-without-membership denied, invited/revoked membership denied,
  membership-without-is_staff still denied, dual-membership user allowed at
  both, and a platform superuser *without* a Store membership still denied
  the merchant dashboard (superuser access is a separate, already-gated
  concern — `/admin/`, not `/admin-panel/`).

### 3.4 Existing test fixtures updated

The authorization change is a real, enforced behavior change, so every
existing test that logged in a bare `is_staff=True` user to reach a
dashboard view needed an explicit `StoreMembership` row added — no test was
weakened or skipped to make the suite pass. Updated (all reviewed for the
correct Store scope per test, including multi-Store isolation tests where a
user must be a member of both Stores under test):

* `apps/dashboard/tests/`: `test_views.py`, `test_invoice_views.py`,
  `test_gateway_shipping_store_isolation.py`, `test_product_image_views.py`,
  `test_admin_login.py`, `test_category_views.py`, `test_sms_admin_views.py`,
  `test_customer_views.py`, `test_report_views.py`, `test_order_store_isolation.py`,
  `test_settings_views.py`, `test_payment_views.py`, `test_product_views.py`,
  `test_product_variant_views.py`, `test_decorators.py`, `test_order_views.py`,
  `test_admin_ux.py`, `test_catalog_store_isolation.py`
* `apps/content/tests/`: `test_content_pages.py`, `test_footer_config.py`,
  `test_social_links.py`, `test_navigation.py`, `test_homepage_media.py`
* `apps/orders/tests/`: `test_gateway_admin.py`
* `apps/stores/tests/`: `test_admin_superuser_gate.py`

Two files with `is_staff=True` fixtures were reviewed and confirmed
**not** affected (no change made): `apps/stores/tests/test_middleware.py`
(doesn't touch dashboard views) and `apps/orders/tests/test_order_service.py`
(`self.staff` is passed as a service-layer `by=` actor argument, never through
an HTTP view).

## 4. Verification (commands actually run)

```text
python manage.py check                        → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run → No changes detected
```

Test runs actually executed (all green, run as separate batches due to
suite runtime, not because of any skip):

| Batch | Tests | Result |
|---|---|---|
| `test_decorators` + `test_admin_login` | 17 | OK |
| `test_views` + `test_invoice_views` + `test_gateway_shipping_store_isolation` + `test_category_views` | 35 | OK |
| `test_sms_admin_views` + `test_customer_views` + `test_report_views` | 26 | OK |
| `test_settings_views` | 101 | OK |
| `test_payment_views` + `test_product_views` + `test_product_variant_views` + `test_order_views` | 148 | OK |
| `apps.content` + `test_gateway_admin` + `test_admin_superuser_gate` + `test_catalog_store_isolation` + `test_order_store_isolation` + `test_admin_ux` | 485 | OK (after fixing one fixture bug, see below) |
| `test_authorization` (new) + `test_membership_authorization` (new) | 23 | OK |
| **Full suite** (`python manage.py test`) | 1743 (1719 baseline + 24 new) | OK — 0 failures, 0 errors |

One real bug was caught and fixed during this verification: the first draft
of `test_admin_superuser_gate.py`'s fixture granted `OWNER`+`ACTIVE`
membership to **two** users for the same Store, which violates the existing
`uniq_active_owner_per_store` database constraint (correctly — a Store must
have exactly one active Owner). Fixed by giving the second user
(`platform-superuser`) the `ADMINISTRATOR` role instead; re-ran and confirmed
green.

## 5. Files Created

* `apps/stores/authorization.py`
* `apps/stores/tests/test_authorization.py`
* `apps/dashboard/tests/test_membership_authorization.py`
* `docs/docs/product/reports/PHASE_1_MERCHANT_ADMIN_IMPLEMENTATION_REPORT.md` (this file)

## 6. Known Limitations / Deliberate Non-Changes

* **Login-view asymmetry:** `admin_login` still authenticates on `is_staff`
  alone, independent of `StoreMembership`. A user with an active membership
  but `is_staff=False` cannot sign in through the admin login form at all
  (though they'd now correctly pass the dashboard's own membership check if
  they somehow had a session). Aligning login eligibility with membership
  existence is follow-up work, not done here, to keep this change minimal
  and reviewable.
* **`permission_required` is unused in production views.** All 84 existing
  `@staff_required` views still only get the coarse "any active member of
  this Store" gate, not per-role gating (e.g. an `ANALYST` can currently
  still reach product-edit forms). Wiring per-view permission checks by
  feature area is real, separate work.
* **Membership provisioning/invitation lifecycle is still absent** — this PR
  authorizes against `StoreMembership` rows that already exist; it does not
  add any UI or service to invite, accept, revoke, or transfer membership.
  That is explicitly listed as "ناقص" (incomplete) in the master reference
  doc §11.1 and remains so.
* **Full `03/28`, i.e. §10.2, is not resolved** — this closes the specific
  cross-Store *authorization* gap, not the broader role-based-permission
  target architecture described there.

## 7. Remaining Work (from the originating request, in priority order)

The originating prompt asked for full prototype parity across the merchant
admin portal in one pass. None of the following were started in this
session — each is a substantial, independent body of work requiring its own
model/service/view/test/migration cycle:

**Critical/High**
* Attribute & option definitions, multi-attribute variant matrix, variant
  images tied to storefront selection
* Inventory ledger (on-hand/reserved/committed, adjustment history, atomic
  reservation)
* Full order lifecycle: fulfillment workflow, cancellation/refund, invoice
  lifecycle, per-Store order numbering
* Customer ownership ADR (Store-scoped vs. global identity +
  Store-profile) — blocking for CRM features
* Cart/coupon full tenantization (direct Store FK, session isolation)

**Medium**
* Discounts/campaigns beyond the basic coupon (eligibility, usage ledger,
  concurrency-safe usage counts)
* Cashback (ledger-based, not a mutable balance)
* Wallet (ledger-based transactions, idempotent credit/debit)
* Referral/invite-friends (conversion-conditioned rewards, fraud basics)
* Industry setup templates (categories/attributes provisioning, non-destructive
  re-application)
* Rich product content blocks, product videos
* CMS/page builder versioning (draft/publish, rollback, section registry)
* Reports/analytics beyond the existing basic dashboard charts

**Lower priority / explicitly deferred until commerce core is stable**
* SaaS billing/subscription/entitlement/plan enforcement
* Custom-domain lifecycle beyond what `StoreDomain` already models

## 8. Recommended Next Step

Given this PR closes the authorization foundation, the next highest-leverage
piece — per the master reference doc's own staged plan and because nearly
every feature area above says "add permissions" as a requirement — is to
wire `permission_required` into the existing 84 dashboard views by feature
area (start with Settings and Membership management, the most
security-sensitive), before starting net-new feature build-out like
attributes/variants/wallet/cashback. Building new merchant-facing features on
top of an authorization layer that isn't yet applied per-action would mean
re-touching every new view again once granular permissions land.
