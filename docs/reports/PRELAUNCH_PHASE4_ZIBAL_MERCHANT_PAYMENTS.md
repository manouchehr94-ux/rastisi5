# Pre-Launch Phase 4 — Merchant Zibal Configuration and Store Checkout Payment

## 1. Objective

Every merchant Store must be able to use its own Zibal account for
customer order payments — separate from RastiSi Platform Billing (Phase 3),
never mixing credential domains.

## 2. Architecture before this phase

Found **already fully built and tested**, contrary to the master prompt's
assumption that this needed net-new construction:

- `apps.orders.models.PaymentGatewayConfig` — `store` (FK), `gateway_code`
  (`GatewayCode.{ZIBAL,COD}`), `is_active`, `is_sandbox`,
  `encrypted_credentials` (Fernet, via `apps.orders.encryption` — the same
  utility Phase 3 reused for platform credentials, but a structurally
  separate field on a structurally separate model). Unique
  `(store, gateway_code)`. Properties `is_configured`/`can_activate`/
  `is_online` dispatch through `apps.orders.gateways.get_adapter`.
- `apps.orders.gateways.zibal.ZibalAdapter` — complete: `create_payment`
  (POST `/v1/request`, Toman→Rial ×10 conversion confined to this adapter),
  `build_redirect_url` (`/start/{trackId}`), `verify_payment` (POST
  `/v1/verify`, re-checks amount server-side, accepts `result` ∈
  `{100, 201}`), sandbox merchant override, explicit `(10, 30)` timeouts,
  structured error hierarchy (`GatewayConnectionError`/
  `GatewayResponseError`/`GatewayPaymentError`/`GatewayVerificationError`/
  `GatewayCredentialError`), no credential logging.
- `apps.orders.services.gateway_payment_service` — `initiate_payment`
  (validates order not already paid, resolves the gateway config
  **scoped to the requesting Store**, creates a `PaymentAttempt`, calls
  the adapter) and `process_callback_and_verify` (treats callback data as
  untrusted, re-verifies server-side, idempotent on duplicate callbacks,
  rejects verification for an attempt/order that doesn't belong to the
  claimed Store).
- Merchant Admin Settings → Payment Gateways UI: save/toggle Zibal & COD
  configs, blank-credential-preserves-existing, secret never redisplayed.
- Checkout view (`apps/orders/views.py::payment_initiate`) resolves the
  gateway config with `PaymentGatewayConfig.objects.filter(store=store,
  ..., is_active=True)` — an inactive or cross-store config is structurally
  unreachable, not just policy.

## 3. Gaps found

None in production code. Every item in the master prompt's Phase 4
checklist (section 6.4) already had passing test coverage **except** one
that only became a real risk *after* Phase 3 added a second, structurally
similar Zibal credential store
(`apps.portal.PlatformConfiguration.encrypted_zibal_credentials`, for
RastiSi's own subscription billing): explicit proof that merchant checkout
never falls back to reading the platform's own Zibal credentials (or vice
versa). This was previously untestable because no second Zibal credential
domain existed in the codebase yet.

## 4. Decisions

Added one new regression test rather than any production code change,
since the isolation is already structural (`gateway_payment_service`
imports nothing from `apps.portal`; `ZibalBillingProvider` imports nothing
from `apps.orders`) — the test exists to keep it that way as both areas
evolve independently.

## 5. Files changed

- `apps/orders/tests/test_gateway_payment_service.py` — added
  `PlatformCredentialIsolationTests`.

## 6. Migrations

None.

## 7. Models/services/views/templates/routes added or changed

None — this phase was verification-only.

## 8. Security decisions (verified, not newly added)

- Checkout never trusts query-string amount/order fields — `expected_amount`
  passed to `verify_payment` always comes from the server-side `Order`/
  `PaymentAttempt` record, and the adapter re-checks the Zibal-returned
  amount against it (`GatewayVerificationError` on mismatch).
- Only gateways active for the current Store are selectable — enforced at
  both the checkout view (`is_active=True` filter) and the service layer
  (`test_inactive_config_raises`).
- Callback cannot select an arbitrary Store/order — `process_callback_and_verify`
  is scoped to the calling Store and the specific `attempt_public_id`
  (`test_wrong_store_config_raises`, `test_nonexistent_attempt_raises`).
- Duplicate callback is idempotent — `test_duplicate_callback_is_idempotent`,
  `test_already_paid_by_another_attempt_cancels_this`.
- Platform Zibal credentials (Phase 3) are never usable for merchant
  checkout, and merchant Zibal credentials are never usable for platform
  billing — newly proven by `PlatformCredentialIsolationTests` (Section 9).

## 9. Tests added

- `apps/orders/tests/test_gateway_payment_service.py::PlatformCredentialIsolationTests::test_checkout_uses_only_the_stores_own_merchant_credential`
  — configures both `PlatformConfiguration` (Phase 3) and the Store's
  `PaymentGatewayConfig` with *different* Zibal merchant IDs, then asserts
  the actual HTTP payload sent to Zibal during checkout carries only the
  Store's own merchant ID.

All pre-existing Phase 4 coverage (68 tests across
`test_gateway_admin.py`, `test_payment_gateway_config.py`,
`test_gateway_payment_service.py`, `test_checkout_correctness.py`,
`test_checkout_integrity.py`) was read and mapped against the master
prompt's checklist (Section 6.4) — see the table below.

| Requirement | Existing test |
|---|---|
| Merchant can save Zibal config | `test_save_zibal_config_creates_record` |
| Secret masking | `test_secret_not_displayed_in_settings_page`, `test_mask_credential_hides_most_characters` |
| Blank edit preserves secret | `test_blank_credential_retains_existing_value` |
| Tenant isolation | `test_tenant_isolation_query`, `test_different_stores_can_have_same_gateway` |
| Inactive gateway unavailable at checkout | `test_inactive_config_raises` + view-level `is_active=True` filter |
| Correct Store credentials selected | `test_wrong_store_config_raises` |
| Request/trackId flow | `test_initiate_zibal_success`, `test_create_payment_success` |
| Verify success/failure | `test_verify_payment_success`, `test_verify_payment_failed_result` |
| Amount mismatch | `test_verify_payment_amount_mismatch` |
| Duplicate callback | `test_duplicate_callback_is_idempotent` |
| Callback tenant binding | `test_wrong_store_config_raises`, `test_nonexistent_attempt_raises` |
| Platform credentials never used | **new**: `PlatformCredentialIsolationTests` |
| No real external HTTP in tests | all Zibal tests `@patch("apps.orders.gateways.zibal.requests.post")` |

## 10. Exact commands run

```
python manage.py test apps.orders.tests.test_gateway_payment_service -v 1
python manage.py test apps.orders -v 1
```

## 11. Exact test counts/results

- `test_gateway_payment_service.py`: 14/14 passed (13 pre-existing + 1 new).
- Full `apps.orders` suite: see the final audit report for the
  consolidated count (run in background alongside this phase's work).

## 12. Browser QA

Not performed (no UI changes this phase).

## 13. Known limitations

None new. Existing limitations (if any) predate this phase and are outside
its scope.

## 14. Commit SHA

Local commit (pending push — see the final audit report for the push-access
blocker status).

## 15. Remaining production-only prerequisites

Real per-Store Zibal merchant credentials, entered by each merchant from
their own Merchant Admin → Settings → Payment Gateways screen.
