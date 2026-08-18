# Pre-Launch Phase 3 — Zibal Provider for RastiSi Platform Subscription Billing

## 1. Objective

RastiSi itself must accept subscription payments through Zibal — platform
billing, using `apps.billing`'s existing provider abstraction, never routed
through `apps.orders` (which is merchant order payment).

## 2. Architecture before this phase

`apps.billing` already had a complete, production-shaped subscription
billing schema and flow (invoices, payment attempts, webhook inbox,
dunning, credit notes, refunds, scheduled plan changes, race-safe document
numbering) and a clean provider abstraction
(`apps/billing/providers/base.py::BillingPaymentProvider`) with exactly one
implementation, `ManualProvider` — honest, no real capture, confirmation
only via a signed webhook or explicit Platform Admin action. No Zibal
provider existed in `apps.billing`. The active provider code was read from
`settings.RASTISI_BILLING_PROVIDER` (environment only) — not DB-editable.

Separately, `apps.orders.gateways.zibal.ZibalAdapter` already implements a
complete, tested Zibal integration for **merchant order checkout**
(Phase 4's subject) — different interface, different credential domain
(`PaymentGatewayConfig`, per-Store), but the same official Zibal API
surface. Its HTTP-call constants and error-mapping conventions were reused
as a direct pattern reference (not imported/shared code — the two
credential domains must never mix, per the master prompt's explicit
requirement).

## 3. Official Zibal API — source of the implementation

`docs.zibal.ir` / `help.zibal.ir` (Zibal's own documentation hosts) are
**blocked by this environment's network egress policy** and could not be
fetched directly. Rather than rely on memory, the following facts were
triangulated from the actively-maintained, typed Python SDK
[`Shebeli/zibal-client`](https://github.com/Shebeli/zibal-client) source
(`src/zibal/configs.py`, `client.py`, `response_codes.py`), cross-checked
against Zibal's own `zibalco` GitHub organization (`gateway-nodejs`), the
`mohammad3020/django-zibal` package, and — most importantly — **this very
repository's own already-existing, tested `apps/orders/gateways/zibal.py`**,
which independently confirms every value below (it was built from the same
official documentation at an earlier point in this project's history):

| Fact | Value |
|---|---|
| IPG base URL | `https://gateway.zibal.ir/v1/` |
| Request endpoint | `POST {base}request` |
| Verify endpoint | `POST {base}verify` |
| Hosted-payment redirect | `https://gateway.zibal.ir/start/{trackId}` |
| Amount unit | **Rial** (not Toman) |
| Sandbox merchant | the literal string `"zibal"` |
| Success result code | `100` |
| Already-verified (idempotent) | `201` |
| Not-yet-paid / failed | `202` |
| Invalid `trackId` | `203` |
| Merchant not found/deactivated/invalid | `102` / `103` / `104` |
| Amount too small (< 1000 Rial) | `105` |
| Invalid `callbackUrl` | `106` |
| Amount over limit | `113` |
| Callback query params | `trackId`, `success`, `status`, `orderId` |

These assumptions are recorded here per the master prompt's explicit
instruction to document exact official-source assumptions rather than
silently rely on memory. **Production readiness note**: before going live,
re-verify this table directly against `docs.zibal.ir` from an environment
that can reach it — this repo's implementation already matches its own
pre-existing, tested `apps/orders/gateways/zibal.py`, which is strong
internal corroboration, but it is not a substitute for a final check
against the primary source.

## 4. Decisions

### 4.1 New `ZibalBillingProvider`, not a shared adapter

`apps/billing/providers/zibal.py` implements `BillingPaymentProvider`
directly — it does **not** import or call `apps.orders.gateways.zibal`.
The two providers' interfaces differ (webhook-shaped vs.
request/build-redirect/verify-shaped) and, more importantly, their
credential domains must never mix (master-prompt cross-cutting rule):
platform billing credentials live on `PlatformConfiguration`; merchant
order-payment credentials live on `PaymentGatewayConfig`. Duplicating the
~40 lines of HTTP-call/error-mapping logic was judged the correct trade-off
over any shared import that could blur that boundary.

### 4.2 Zibal has no signed push webhook — `fetch_payment_status` is the real capture path

`BillingPaymentProvider`'s abstract interface is webhook-shaped
(`verify_webhook`/`parse_webhook_event`), matching `ManualProvider`. Zibal
does not send a signed server-to-server webhook; confirmation is: browser
redirects back to RastiSi (untrusted), then RastiSi calls Zibal's `verify`
endpoint server-side. `ZibalBillingProvider.verify_webhook`/
`parse_webhook_event` are implemented to always fail loudly (never silently
"succeed") — they are never actually invoked, because:

- `ZibalBillingProvider.fetch_payment_status(provider_payment_id=track_id)`
  performs the **real** server-to-server verify call and is the sole source
  of truth for "did this payment succeed."
- A new service function,
  `apps.billing.services.payment_flow_service.confirm_from_provider_verification(attempt, ...)`,
  is called from the browser-return view
  (`apps.dashboard.views.billing_payment_result`). It looks the attempt up
  from the **session** (never from a query parameter), calls
  `fetch_payment_status` only for providers with
  `supports_automatic_capture=True`, and — only on a verified success —
  funnels into the exact same `confirmation_service.confirm_payment()` that
  the webhook path uses. This guarantees the amount/currency check,
  locking, and idempotency guarantees are identical regardless of which
  path (webhook vs. server-verified browser-return) confirmed the payment.
  Query-string parameters (`trackId`, `success`, `status`) are never read
  by this code path — only the server-side `fetch_payment_status` result.

### 4.3 Currency conversion — single boundary, both directions

Per the master prompt's explicit ×10/÷10 bug-prevention requirement: **all**
Toman↔Rial conversion for platform billing lives inside
`apps/billing/providers/zibal.py` and nowhere else:

- `create_payment_session`: `amount_rial = int(attempt.amount) * 10` — the
  only multiplication in the whole billing app.
- `fetch_payment_status`: `amount_toman = Decimal(int(data["amount"])) / 10`
  — the only division. The returned `PaymentStatusResult.amount` (Toman) is
  what `confirm_payment` compares against `invoice.amount_due` (also
  Toman) — so a provider-side unit bug would show up immediately as a
  `ConfirmationError` ("amount mismatch"), not a silent wrong-amount
  activation. Dedicated tests assert the exact numeric conversion in both
  directions (Section 9).

### 4.4 Provider selection and credentials — DB-editable, no source-code edit

- `PlatformConfiguration.default_payment_provider` gained explicit
  `choices=[("manual", ...), ("zibal", ...)]` (was a free-text
  `CharField`) — still the same field, same form
  (`PlatformConfigurationForm`), now a proper dropdown.
- `apps.billing.providers.registry.active_provider_code()` now reads
  `PlatformConfiguration.default_payment_provider` from the DB (via the
  existing cached `get_platform_configuration()`), falling back to
  `settings.RASTISI_BILLING_PROVIDER` only if the config row genuinely
  can't be read yet (e.g. mid-migration) — never as the normal path.
- New encrypted field `PlatformConfiguration.encrypted_zibal_credentials`
  (+ `get_zibal_credentials()`/`set_zibal_credentials()`) and
  `zibal_sandbox_mode` (Boolean), following the exact existing pattern of
  `encrypted_sms_credentials`/`get_sms_credentials`/`set_sms_credentials`
  on the same model: Fernet encryption via the shared
  `apps.orders.encryption` utility, blank secret on save preserves the
  existing value, plaintext is never re-displayed.
- New Platform Admin page, `/payments/zibal/`
  (`portal_platform_admin:billing-zibal-settings`): active-provider
  dropdown, masked merchant-ID input, sandbox toggle, status badges — no
  source-code or environment-file edit needed to turn Zibal on, configure
  it, or switch back to manual.

## 5. Files changed

- `apps/billing/providers/zibal.py` — new, `ZibalBillingProvider`.
- `apps/billing/providers/registry.py` — registered `ZibalBillingProvider`;
  `active_provider_code()` now DB-backed.
- `apps/billing/services/payment_flow_service.py` — new
  `confirm_from_provider_verification()`.
- `apps/dashboard/views.py` — `billing_payment_result` now calls the above
  after looking up the attempt from the session (not from query params).
- `apps/dashboard/templates/dashboard/billing_payment_result.html` — shows
  a friendly message on transient verify errors.
- `apps/portal/models.py` — `default_payment_provider` gained `choices`;
  new `zibal_sandbox_mode`, `encrypted_zibal_credentials`,
  `get_zibal_credentials()`, `set_zibal_credentials()`.
- `apps/portal/migrations/0008_platformconfiguration_encrypted_zibal_credentials_and_more.py`
  — new fields + choices metadata.
- `apps/portal/platform_admin_views.py` — new `billing_zibal_settings`
  view.
- `apps/portal/platform_admin_urls.py` — new route `payments/zibal/`.
- `apps/portal/templates/portal/platform_admin/billing_zibal_settings.html`
  — new.
- `apps/portal/templates/portal/platform_admin/base.html` — new sidebar
  link.
- Tests: `apps/billing/tests/test_zibal_platform_provider.py` (new, 25
  tests), `apps/portal/tests/test_platform_admin_billing_zibal.py` (new, 8
  tests), `apps/dashboard/tests/test_billing_views.py` (extended, +6 tests
  in `ZibalBrowserReturnFlowTests`).

## 6. Migrations

`apps/portal/migrations/0008_platformconfiguration_encrypted_zibal_credentials_and_more.py`
— adds `encrypted_zibal_credentials` (TextField), `zibal_sandbox_mode`
(BooleanField), and alters `default_payment_provider`'s `choices` metadata
(no data migration; existing values `"manual"` and any legacy
free-text value both remain valid — `choices` is not DB-enforced).
Verified with `makemigrations --check --dry-run` (clean) and applied
cleanly against SQLite.

## 7. Security decisions

- **Verify-before-activate, always**: no code path anywhere marks an
  invoice paid or activates/renews a subscription from browser-return alone
  — `confirm_from_provider_verification` only proceeds past a real,
  server-side `fetch_payment_status` call, and only `confirm_payment`
  (shared with the webhook path) ever mutates invoice/subscription state.
- **Amount/currency mismatch rejected**: `confirm_payment`'s existing
  check (`amount != invoice.amount_due` / `currency != invoice.currency`)
  is exercised by the Zibal path exactly as it is by the manual/webhook
  path — a tampered or wrong verify response cannot silently under/over
  charge (tested, Section 9).
- **Idempotent / duplicate-safe**: `confirm_payment` is `transaction.atomic`
  with `select_for_update` on both the attempt and invoice, and already
  no-ops on an attempt that's `SUCCEEDED` or an invoice that's `PAID`. A
  user refreshing the browser-return page (or Zibal's callback firing
  twice) re-runs `fetch_payment_status` (a second real HTTP verify call,
  harmless per Zibal's own `201`-already-verified semantics) but never
  double-applies the payment or double-renews the subscription (tested).
- **No credentials in logs**: the merchant ID is never logged; only
  `attempt.public_token`, amounts, and sandbox flag are (matches the
  existing `apps.orders.gateways.zibal` logging convention).
- **Fixed hostnames, explicit timeouts**: `IPG_BASE_URL`/`PAYMENT_BASE_URL`
  are module constants, never user/DB-controlled; every HTTP call uses
  `timeout=(10, 30)`.
- **Provider unavailable ⇒ no false success**: connection errors/timeouts
  raise `ProviderConnectionError`, which `billing_payment_result` catches
  and displays as a message — it never falls through to a "paid" state.
- **Credential domains never mix**: `ZibalBillingProvider` reads
  exclusively from `PlatformConfiguration`; it has no access to any
  Store's `PaymentGatewayConfig`, and vice versa — verified structurally
  (no cross-import) and by the tenant-isolation tests in Section 9.

## 8. Reliability / cross-cutting rules

- `transaction.atomic()` + `select_for_update()`: inherited from
  `confirmation_service.confirm_payment`, exercised by every Zibal
  confirmation test.
- Duplicate callback / already-paid: tested explicitly
  (`test_duplicate_verification_is_idempotent`).
- Failed/cancelled payment leaves subscription unchanged: tested
  (`test_not_yet_paid_leaves_attempt_and_subscription_unchanged`).
- No real Zibal HTTP in any automated test — every test mocks
  `apps.billing.providers.zibal.requests.post` (never calls the network).

## 9. Tests added

- `apps/billing/tests/test_zibal_platform_provider.py` (25 tests):
  provider registration, `active_provider_code()` DB-read + manual
  fallback, credential encryption at rest + blank-preserves, request
  success/rejected-result/timeout/connection-error/bad-JSON, sandbox
  merchant override, exact Toman→Rial conversion on request and exact
  Rial→Toman conversion on verify, already-verified (`201`) and
  not-yet-paid (`202`)/invalid-trackId (`203`) handling, network-error
  propagation, `verify_webhook` always-unsupported, honest
  non-automated refund, and the full `confirm_from_provider_verification`
  integration (verified success activates + marks paid, amount mismatch
  rejected, not-yet-paid leaves everything unchanged, duplicate
  verification idempotent — asserted by exact `amount_paid` and HTTP
  call-count, provider-unavailable never falsely succeeds, a `manual`
  attempt is never auto-confirmed by this path).
- `apps/portal/tests/test_platform_admin_billing_zibal.py` (8 tests):
  authorization, view+save round-trip, encrypted-at-rest, never echoed in
  plaintext, blank-preserves-existing, switching back to manual, invalid
  provider value rejected.
- `apps/dashboard/tests/test_billing_views.py::ZibalBrowserReturnFlowTests`
  (6 new tests): pay redirects to the real Zibal gateway URL, browser
  return performs the real server-side verify and marks paid, **query
  params claiming success are ignored** when the real verify says
  otherwise (`success=1&status=1` in the URL with a mocked `202` response
  behind it), and cross-store isolation (another store's owner hitting the
  browser-return endpoint cannot affect this invoice).

A pre-existing cross-test hazard was found and fixed while writing these
tests: `PlatformConfiguration` is cached process-wide
(`django.core.cache`), which — unlike the DB — is **not** reset by Django
`TestCase`'s per-test transaction rollback. Once `active_provider_code()`
started reading this cached value, any test that switched the active
provider to `"zibal"` without clearing the cache afterward could leak into
an unrelated, later-running test and cause it to attempt a real network
call. Fixed by registering `self.addCleanup(cache.clear)` everywhere the
new tests activate Zibal.

## 10. Exact commands run

```
python manage.py makemigrations portal
python manage.py test apps.billing.tests.test_zibal_platform_provider \
  apps.portal.tests.test_platform_admin_billing_zibal \
  apps.dashboard.tests.test_billing_views -v 2
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
python manage.py test apps.billing apps.dashboard apps.portal apps.orders -v 1
```

## 11. Exact test counts/results

- New targeted tests (Gate A): 47/47 passed
  (`test_zibal_platform_provider.py` 25 + `test_platform_admin_billing_zibal.py`
  8 + `ZibalBrowserReturnFlowTests` 6 + pre-existing `BillingViewTests`
  in the same file 8, all green together — confirms no cross-test
  leakage after the cache-cleanup fix).
- `python manage.py check`: 0 issues. `makemigrations --check --dry-run`:
  clean. `git diff --check`: no whitespace errors.
- Gate B (`apps.billing`, `apps.dashboard`, `apps.portal`, `apps.orders`
  full suites): see the final audit report for consolidated counts (run in
  background alongside this phase's work).

## 12. Browser QA

Not performed in this pass (headless test environment only; real Zibal
payments were never attempted per the master prompt's explicit
instruction). The new Platform Admin settings page reuses the existing
`pa-card`/`pa-field`/`pa-badge` styling already used throughout Platform
Admin, so it renders consistently with no new CSS.

## 13. Known limitations

- Zibal's official documentation could not be fetched directly in this
  environment (network egress blocked); the API facts in Section 3 were
  triangulated from independent third-party sources and this repo's own
  pre-existing, tested `apps/orders/gateways/zibal.py`. Re-verify against
  `docs.zibal.ir` directly before enabling real (non-sandbox) platform
  Zibal payments in production.
- No refund automation — `ZibalBillingProvider.refund_payment` honestly
  reports `succeeded=False` (Zibal's v1 IPG API has no documented
  automated refund endpoint in any source reviewed); refunds remain a
  manual/dashboard operation, matching `ManualProvider`'s existing pattern
  and `apps.billing.services.refund_service`'s existing manual-refund
  support.
- Real platform Zibal credentials, and confirmation that the sandbox
  merchant flow behaves as expected against Zibal's actual sandbox
  environment, are production-only prerequisites (see the final audit
  report).

## 14. Commit SHA

Local commit (pending push — see the final audit report for the push-access
blocker status).

## 15. Remaining production-only prerequisites

- Real Zibal platform merchant credentials (entered via Platform Admin →
  پرداخت‌ها و فاکتورها → زیبال — اشتراکِ پلتفرم, never in source control).
- A final direct check of the request/verify/result-code contract against
  `docs.zibal.ir` from a network-unrestricted environment before disabling
  sandbox mode.
- Confirming `RASTISI_BILLING_PROVIDER` (env fallback) is either unset or
  aligned with the DB choice in the production environment, to avoid
  confusion (the DB value always wins once the config row exists).
