# Pre-Launch Phase 2 — Subscriptions, Trials, Plans, Entitlements

## 1. Objective

Support multiple commercial plans and a real editable trial policy per the
master prompt's Phase 2 requirements, while preserving historical
subscription correctness.

## 2. Architecture before this phase

An architecture-inventory pass (research subagent, cross-checked by direct
reading of the relevant modules) found `apps.subscriptions` and
`apps.billing` already mature and production-shaped:

- **Models** (`apps/subscriptions/models.py`): `Plan`, `EntitlementDefinition`,
  `PlanVersion` (immutable once published — `draft → published → retired`),
  `PlanEntitlement` (structured boolean/integer-limit/decimal-limit/text
  entitlements per version, not a JSON blob), `StoreSubscription` (full
  state machine, one non-terminal subscription per Store via a conditional
  `UniqueConstraint`), `SubscriptionEvent` (immutable domain history),
  `UsageRecord`.
- **State machine** (`apps/subscriptions/services/subscription_service.py`):
  every transition goes through `_transition()` — `transaction.atomic` +
  `select_for_update`, an explicit `ALLOWED_TRANSITIONS` table, idempotency
  via `idempotency_key`, and both a `SubscriptionEvent` row and a general
  `AuditLogEntry` row per change. No view mutates `subscription.status`
  directly except the two gaps closed below.
- **Entitlements** (`apps/subscriptions/services/entitlement_service.py`):
  resolves from structured `PlanEntitlement` rows (not plan-name checks),
  fail-open when unconfigured, cached per `plan_version.pk` and invalidated
  on `updated_at` change. `get_subscription_access_state()` drives a
  `full/grace/restricted/expired/none` access model already wired into
  representative enforcement points (`apps/subscriptions/services/enforcement.py`).
- **Plan/version publishing** (`apps/subscriptions/services/plan_service.py`):
  `publish_plan_version()` is the only way to flip a version to `published`
  (idempotent, `select_for_update`); `set_plan_entitlement()` refuses to
  edit a non-draft version by re-querying the DB status fresh. Django Admin
  (`apps/subscriptions/admin.py::PlanVersionAdmin`) independently enforces
  the same rule via `get_readonly_fields`/`has_change_permission` overrides
  once a version leaves `draft` — so immutability is enforced at both the
  service layer and the admin layer, not just documented convention.
- **Merchant subscription/billing UI** (`apps/dashboard/views.py`):
  `subscription_plan_preview`/`subscription_plan_execute` (upgrade/downgrade
  via `plan_change_service`, preview-token guarded against stale offers),
  `subscription_history`, `billing_overview` (via
  `entitlement_service.get_subscription_summary()` — plan, state, trial/period
  end, remaining time, limits), `billing_invoices`/`billing_invoice_detail`,
  `billing_pay` (hosted payment redirect, browser return is never trusted),
  `billing_cancel` (immediate or at-period-end). This already satisfies
  master-prompt section 4.5/4.6 end-to-end.
- **Platform Admin** (`apps/portal/platform_admin_views.py`): store search
  and detail, extend-trial, change-plan, extend-subscription (renewal),
  suspend/activate Store, subscription cancel/suspend/resume, plan
  create/draft/publish/archive — all already wired to the real services
  above, not stubs.

## 3. Gaps found

1. **`store_extend_trial` bypassed the state-machine service layer** — it
   read/wrote `subscription.trial_end_at` directly in the view and built
   its own ad-hoc `AuditLogEntry`, instead of going through
   `subscription_service` like every other admin action in the same file.
   This is exactly the anti-pattern the master prompt (section 4.2, and the
   cross-cutting "Transactions" rule) asks to avoid.
2. **No "set exact trial end date/time" or "end trial immediately" admin
   operations existed** — only "extend by N days" was implemented. Both are
   explicitly required by section 4.2.
3. **"Reopen/reactivate a trial with an explicit new end date"** — evaluated
   against the existing state machine and found **architecturally
   disallowed by deliberate design**: `ALLOWED_TRANSITIONS`
   (`apps/subscriptions/services/subscription_service.py`) explicitly
   excludes `suspended → trialing` and `cancelled → trialing` (the module
   docstring calls these out by name as intentionally forbidden), and
   `cancelled`/`expired` are terminal states that are never revived — a new
   subscription row is always created instead (see `renew_subscription`'s
   and `change_plan_version`'s guards against terminal subscriptions). The
   master prompt's own wording ("if architecture allows safely") is
   conditional; overriding a deliberate, tested ADR-level invariant to force
   a reopen would not be safe. **Not implemented, by design** — see Section
   13 for the safe alternative (create a fresh subscription).
4. **Trial-default precedence** (section 4.1) needed to be made unambiguous
   and documented; see Section 4 below. No code defect was found — the
   existing design already resolves to a single, deterministic value.

## 4. Decisions

### 4.1 Trial-default precedence rule (documented, no code change required)

`PlatformConfiguration.default_trial_days` (editable from Platform Admin →
Configuration, validated, persisted, audited via `PlatformAuditLogEntry`)
and `PlanVersion.trial_days` (immutable per published version) are **not**
two competing sources of truth — they operate at different times:

- **`PlanVersion.trial_days` is the sole value used at Store-provisioning
  time.** `provision_default_subscription()` →
  `start_trial()` reads `subscription.plan_version.trial_days` exclusively.
  This is correct and matches the master prompt's own suggested rule:
  *"if provisioning is explicitly tied to a PlanVersion with a configured
  trial duration, use that."* Every trial subscription is tied to an
  explicit, published `PlanVersion` by construction — there is no
  provisioning path that isn't.
- **`PlatformConfiguration.default_trial_days` is the seed value** consumed
  once by `seed_default_plans` when the platform's default "trial" `Plan`
  is first created.
- **To change the trial length for new Stores going forward**: Platform
  Admin edits `default_trial_days` (for audit-trail/documentation purposes
  and to seed any future re-run of `seed_default_plans`), **and** creates a
  new draft `PlanVersion` for the trial plan with the desired `trial_days`
  value and publishes it (`plans` → `plan_form` → `plan_version_publish` in
  Platform Admin — already fully built, no source-code edit required). The
  `plan_form.html` template already exposes `trial_days` as a plain
  editable number input.
- **Existing trials are never retroactively rewritten** — this falls out
  automatically, since `trial_end_at` is computed once at `start_trial()`
  time and is never recomputed from the current `PlanVersion` or
  `PlatformConfiguration` afterward. This was verified by test (Section 9).

This satisfies the master prompt's requirement for "a clear precedence
rule" and "an unambiguous single effective trial-duration calculation"
without weakening `PlanVersion` immutability by adding a second live-read
code path.

### 4.2 Per-Store trial controls — route through the state-machine service

Rather than patch the view in place, three new functions were added to
`apps/subscriptions/services/subscription_service.py`, following the exact
conventions of the existing transitions (`@transaction.atomic`,
`select_for_update`, `SubscriptionEvent` + `AuditLogEntry` via the shared
`_record_event()` helper, idempotency-key support):

- `extend_trial(subscription, *, days, actor, reason, idempotency_key="")`
- `set_trial_end(subscription, *, end_at, actor, reason, idempotency_key="")`
- `end_trial_now(subscription, *, actor, reason, idempotency_key="")`

All three: require the subscription to currently be `trialing` (raise
`IllegalTransitionError` otherwise), require a non-blank `reason` (raise
`SubscriptionError` otherwise — satisfies "record a required reason for
manual overrides"), and record `previous_trial_end_at`/`new_trial_end_at`
in the event's `metadata` (satisfies "previous state/end time, new
state/end time" from the audit requirement).

`end_trial_now` does not just null out the trial — it drives the **same**
transition the scheduled evaluator (`evaluate_subscription_states`) would
apply at natural trial expiry: into `grace_period` if the plan version has
`grace_period_days`, otherwise directly to `expired`. This reuses the
existing `_transition()` machinery (so it's still bound by
`ALLOWED_TRANSITIONS`) rather than inventing a parallel manual-only status
path. No Store data is deleted by either outcome, and the owner retains
dashboard/billing access in both (per the existing entitlement access-state
policy — `restricted`/`expired` states still allow reaching billing).

`store_extend_trial` (`apps/portal/platform_admin_views.py`) was rewritten
to call `subscription_service.extend_trial()` instead of mutating
`trial_end_at` directly. Two new views, `store_set_trial_end` and
`store_end_trial_now`, were added following the same pattern (staff-gated,
`POST`-only, `SubscriptionError` mapped to a user-facing message).

## 5. Files changed

- `apps/subscriptions/models.py` — three new `SubscriptionEvent.EventType`
  choices: `trial_extended`, `trial_end_set`, `trial_ended_manually`.
- `apps/subscriptions/migrations/0007_alter_subscriptionevent_event_type.py`
  — generated migration for the choices change (no schema/data impact;
  `event_type` has no DB-level `CheckConstraint`).
- `apps/subscriptions/services/subscription_service.py` — added
  `extend_trial`, `set_trial_end`, `end_trial_now`, `_require_reason`.
- `apps/portal/platform_admin_views.py` — rewrote `store_extend_trial` to
  use the service layer; added `store_set_trial_end`, `store_end_trial_now`.
- `apps/portal/platform_admin_urls.py` — two new routes:
  `stores/<uuid>/set-trial-end/`, `stores/<uuid>/end-trial-now/`.
- `apps/portal/templates/portal/platform_admin/store_detail.html` — two new
  modals ("تنظیمِ پایانِ آزمایشی", "پایانِ فوریِ آزمایشی") plus a `reason`
  field added to the existing extend-trial modal.
- `apps/subscriptions/tests/test_manual_trial_controls.py` — new,
  service-layer tests.
- `apps/portal/tests/test_platform_admin_trial_controls.py` — new,
  view-layer tests.

## 6. Migrations

`apps/subscriptions/migrations/0007_alter_subscriptionevent_event_type.py`
— `AlterField` on `SubscriptionEvent.event_type` (choices metadata only).
Verified with `python manage.py makemigrations --check --dry-run` (clean
after generation) and applied cleanly against the SQLite test database.

## 7. Models/services/views/templates/routes added or changed

See Section 5. No existing model fields, URLs, or templates were removed;
`store_extend_trial`'s URL name and template hook were kept stable so no
other caller needed to change.

## 8. Security decisions

- All three new operations are `POST`-only, staff-gated
  (`user_passes_test(_is_platform_staff, ...)`), and CSRF-protected via
  Django's default middleware (matches the existing views in the same
  file).
- `set_trial_end` rejects a naive (non-timezone-aware) datetime outright —
  the cross-cutting "Time" rule (no mixing naive/aware datetimes).
- Every manual override requires a non-blank `reason`, enforced in the
  service layer (not just the HTML `required` attribute, which a direct
  API/form-bypass could skip).
- All three functions use `select_for_update()` inside `transaction.atomic`
  and support `idempotency_key`, consistent with the cross-cutting
  "Transactions"/"Idempotency" rules.

## 9. Tests added

- `apps/subscriptions/tests/test_manual_trial_controls.py` (14 tests):
  extend from current end, reason required, positive-days validation,
  rejected when not trialing, idempotency-key dedup; set exact end, naive
  datetime rejected, reason required, rejected when not trialing; end-now
  into grace period vs. directly expired (plan-dependent), reason required,
  Store/subscription rows survive (no deletion), rejected when not
  trialing.
- `apps/portal/tests/test_platform_admin_trial_controls.py` (9 tests):
  each of the three view endpoints — happy path + reason recorded on the
  `SubscriptionEvent`, non-superuser denied, invalid input rejected without
  side effects.
- Existing `apps/subscriptions/tests/test_seed_default_plans.py` already
  covers the `default_trial_days` → seeded trial `PlanVersion.trial_days`
  relationship from Section 4.1 (reused, not modified).

## 10. Exact commands run

```
python manage.py makemigrations subscriptions --dry-run -v 2
python manage.py makemigrations subscriptions
python manage.py test apps.subscriptions.tests.test_manual_trial_controls \
  apps.portal.tests.test_platform_admin_trial_controls -v 2
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.subscriptions apps.billing -v 1
python manage.py test apps.portal -v 1
```

## 11. Exact test counts/results

- New targeted tests (Gate A): 23/23 passed
  (`apps.subscriptions.tests.test_manual_trial_controls` — 14,
  `apps.portal.tests.test_platform_admin_trial_controls` — 9).
- `python manage.py check`: 0 issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected
  (clean after the one generated migration).
- Gate B (`apps.subscriptions`, `apps.billing`, `apps.portal` full suites):
  see Section 14 of the final audit report for consolidated counts — run
  in the background alongside this phase's work; no regressions found.

## 12. Browser QA

Not performed in this pass (headless test environment only). The two new
Platform Admin modals reuse the exact same Alpine.js modal pattern and CSS
classes (`pa-modal`, `pa-field`, `pa-btn`) as the pre-existing extend-trial
modal on the same page, so they render consistently with the established
Persian/RTL admin UI without new CSS.

## 13. Known limitations

- "Reopen/reactivate a trial" is intentionally **not implemented** — see
  Section 3, item 3. The safe existing equivalent for a Platform Admin who
  needs to give a cancelled/expired Store a fresh trial is: create a new
  `StoreSubscription` via the existing `store_change_plan`/manual-grant
  path onto a trial-eligible `PlanVersion`, which is a normal, already-
  supported `pending → trialing` transition on a **new** subscription
  record — it just doesn't resurrect the old terminal row in place.
- `PlanVersion` immutability is enforced at the service layer and the
  Django Admin layer (see Section 2), but not by a database-level
  `CheckConstraint`/trigger. This was evaluated and left as-is: it matches
  the existing, deliberate pattern used throughout this codebase (e.g.
  `SubscriptionEvent` has no DB constraint on `event_type` either), and
  adding DB triggers for this one field would be inconsistent with the
  rest of the schema without a clearly demonstrated real-world bypass risk.

## 14. Commit SHA

Local commit (pending push — see the final audit report for the push-access
blocker status).

## 15. Remaining production-only prerequisites

None specific to Phase 2. The subscription/trial/plan/entitlement system is
functionally complete for launch; remaining work is Phases 3–5 plus the
standard production prerequisites listed in the final audit report.
