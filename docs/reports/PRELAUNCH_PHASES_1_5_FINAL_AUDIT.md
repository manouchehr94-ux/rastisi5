# RastiSi Pre-Launch Phases 1–5 — Final Audit

## 0. Branch / baseline

- Branch: `claude/new-session-85jij5` (per this session's harness
  configuration — the master prompt's suggested name,
  `claude/prelaunch-phases-1-5`, was superseded by the branch already
  provisioned for this session).
- Starting `main` SHA: `d0682d7759886f3367054b01625efeba1b21ee61`.
- Final branch SHA: `6acf8cc39397d81b55c83902c87071f33895d850`.
- Baseline confirmed present as ancestors on `main` before any work began:
  Turnstile/owner-flow hardening (`50988e0`) and the safe eNamad
  technical-verification baseline (`a07fe73`, migration
  `portal.0007_platformconfiguration_enamad_verification_meta_tag`) —
  verified via `git merge-base --is-ancestor 50988e0 origin/main` (YES)
  and direct inspection of the migrations directory.
- `git status --short`, `git log -10 --oneline`, `python manage.py check`,
  and `python manage.py makemigrations --check --dry-run` were all run and
  recorded before any edits, per the mandatory pre-work checklist.

## 1. Commit list (8 commits, oldest first)

| SHA | Subject |
|---|---|
| `256be51` | chore: gitignore local Claude Code agent worktree scaffolding |
| `21e9dbb` | prelaunch: close enamad verification baseline |
| `d3bdced` | docs: add phase 1 enamad baseline engineering report |
| `f84580b` | subscriptions: complete trials plans and entitlements |
| `e25e078` | billing: add zibal platform subscription provider |
| `10cee8a` | payments: complete merchant zibal gateway configuration |
| `6a1f886` | prelaunch: complete enamad platform and merchant lifecycle |
| `6acf8cc` | test: update generic integration_service tests off retired enamad_code field |

## 2. Architecture inventory (Phase 0, before any implementation)

A research pass across `apps.portal`, `apps.subscriptions`, `apps.billing`,
`apps.orders`, `apps.stores` found this repository substantially further
along than the master prompt's own framing assumed:

- **Phase 1 (eNamad technical verification)**: essentially complete
  already (safe meta-tag parser, host/path-scoped rendering on both
  platform and merchant sides, encrypted merchant storage).
- **Phase 2 (subscriptions/trials/plans/entitlements)**: mature and
  production-shaped — a full `transaction.atomic` + `select_for_update`
  state machine, immutable published `PlanVersion`s enforced at both the
  service and Django-Admin layers, structured (non-JSON-blob)
  `PlanEntitlement` resolution, and a complete merchant subscription/
  billing UI.
- **Phase 3 (Zibal platform billing)**: genuinely missing — only a
  `ManualProvider` existed; the provider abstraction was ready to receive
  Zibal but no implementation exists, and the active-provider selection
  was environment-only, not DB-editable.
- **Phase 4 (merchant Zibal checkout)**: already fully built and tested —
  `PaymentGatewayConfig`, `ZibalAdapter`, tenant-scoped
  `gateway_payment_service`, generic merchant settings UI.
- **Phase 5 (eNamad completion)**: genuinely missing — the post-issuance
  "badge" was a free-text, never-rendered field with only a length cap.

This inventory directly shaped where implementation effort went: heavy
net-new work in Phases 3 and 5, targeted gap-filling in Phase 2, and
verification-plus-one-regression-test in Phases 1 and 4.

## 3. Phase summaries

### Phase 1 — eNamad verification baseline (report: `PRELAUNCH_PHASE1_ENAMAD_BASELINE.md`)

Audited against the full Phase 1 checklist; found complete. Closed two
test-coverage gaps (unverified custom domain, cross-tenant leakage on the
storefront-rendering path). No production code changed.

**Tests**: 12/12 targeted; 2368/2368 in the `apps.portal` + `apps.stores`
+ `apps.dashboard` combined Gate B run performed at the time.

### Phase 2 — Subscriptions, trials, plans, entitlements (report: `PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md`)

Documented the trial-default precedence rule (`PlanVersion.trial_days` as
the sole provisioning-time source; `PlatformConfiguration.default_trial_days`
as a one-time seed — no code change needed, already unambiguous). Closed
two real gaps: `store_extend_trial` was rewritten onto the state-machine
service layer instead of mutating `trial_end_at` directly, and two new
per-Store trial operations (`set_trial_end`, `end_trial_now`) were added
alongside it, both with mandatory reasons and full audit trails.
"Reopen a cancelled/expired trial" was evaluated and deliberately **not**
implemented — the existing state machine explicitly forbids
`suspended→trialing`/`cancelled→trialing` by design.

**Tests**: 23/23 new; 236/236 in `apps.subscriptions`+`apps.billing`;
413/413 in `apps.portal` (pre-Phase-3 baseline).

### Phase 3 — Zibal platform subscription billing (report: `PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md`)

New `ZibalBillingProvider` (request/verify against Zibal's official v1
IPG API — endpoints and result codes triangulated from an actively
maintained third-party SDK and cross-checked against this repo's own
pre-existing `apps/orders/gateways/zibal.py`, since `docs.zibal.ir` is
blocked by this environment's network egress). Since Zibal has no signed
push webhook, a new `confirm_from_provider_verification()` performs the
real server-side verify on browser return and funnels into the same
`confirm_payment()` the webhook path uses. Currency conversion (Toman↔Rial)
is confined to one file, both directions, with exact-value tests. Provider
selection and credentials are now Platform-Admin editable
(`/payments/zibal/`) without any source/env-file change.

**Tests**: 47/47 new, all HTTP mocked at the provider boundary.

### Phase 4 — Merchant Zibal checkout gateway (report: `PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md`)

Found already fully built and tested. Added one regression test proving
the platform's own Zibal credentials (new in Phase 3) can never be used
for merchant checkout, and vice versa — a risk that only became testable
once a second Zibal credential domain existed in the codebase.

**Tests**: 14/14 (13 pre-existing + 1 new).

### Phase 5 — eNamad platform + merchant completion (report: `PRELAUNCH_PHASE5_ENAMAD_COMPLETION.md`)

The final eNamad badge is now two validated structured identifiers
(numeric `id` + alphanumeric `Code`), never a raw HTML/script fragment —
RastiSi builds the trusted `<a>`/`<img>` markup itself against the fixed
`trustseal.enamad.ir` origin. Independent of the technical-verification
meta on both platform and merchant sides; sitewide rendering (not
home-only, unlike the meta) but the exact same verified-custom-domain
tenant guard, factored into one shared helper so the two can't drift
apart. Platform side gained an explicit enable/disable switch.

**Tests**: 33/33 new/updated in the eNamad-specific files; 34/34 in
`apps.dashboard.tests.test_integration_views` + `apps.portal.tests.test_platform_configuration`.

## 4. Migrations added

| Migration | Purpose |
|---|---|
| `apps/subscriptions/migrations/0007_alter_subscriptionevent_event_type.py` | Three new `SubscriptionEvent.EventType` choices for manual trial controls (Phase 2). |
| `apps/portal/migrations/0008_platformconfiguration_encrypted_zibal_credentials_and_more.py` | Platform Zibal credentials + sandbox flag + `default_payment_provider` choices (Phase 3). |
| `apps/portal/migrations/0009_platformconfiguration_enamad_auth_code_and_more.py` | Platform eNamad badge identifiers + enable switch (Phase 5). |

All three verified clean against `python manage.py makemigrations --check
--dry-run` after generation, and applied cleanly against SQLite in every
test run. No merchant-side migration was needed for the eNamad badge
change — `StoreIntegrationConnection.encrypted_credentials` is already a
flexible encrypted JSON blob.

## 5. Security controls added

- **Zibal platform billing** (Phase 3): verify-before-activate on every
  path (no browser-return-alone confirmation anywhere), amount/currency
  mismatch rejected via the existing `confirm_payment` check exercised
  identically by both the webhook and server-verify paths, idempotent
  duplicate-verification handling, fixed hostnames/explicit timeouts, no
  credential logging, structural non-overlap between platform and
  merchant Zibal credential domains (now proven by tests on both sides).
- **eNamad badge** (Phase 5): no `mark_safe()`/raw-HTML anywhere; only two
  regex-validated identifiers ever reach a template, inside a fixed markup
  structure pointed at a hardcoded origin; explicit script/HTML-injection
  rejection tests; fail-closed on corrupt/partial legacy values; strict
  tenant and platform/merchant host separation.
- **Manual trial controls** (Phase 2): mandatory reason on every override,
  `select_for_update`-locked, idempotency-key-safe, full
  `SubscriptionEvent` + audit-log trail with before/after end times.
- Cross-cutting: every new admin/merchant endpoint is `POST`-only with
  Django's default CSRF middleware and existing `staff_required`/
  `user_passes_test` authorization gates; no new endpoint trusts
  client-supplied identifiers for tenant scoping.

## 6. Browser QA

Not performed for any phase — this session's environment is a headless
test runner only, and the master prompt explicitly forbids real Zibal
payments. All new Platform Admin and Merchant Admin UI reuses existing CSS
classes/component patterns already used throughout each panel, so no new
styling was introduced. This is a genuine limitation relative to Section
13's request for real-route QA; a follow-up session with browser access
should click through: Platform Admin trial policy, Store trial override
modals, plan creation/versioning, merchant subscription screen, Platform
Zibal config screen, Merchant Zibal config screen, Platform eNamad config,
Merchant eNamad config, and the eNamad meta/badge actually rendering in a
real page `<head>`/footer on the correct host.

## 7. Testing gates — what was actually run

### Gate A (targeted, per phase)
All new/changed test files run in isolation after each phase; every one
green before moving to the next phase. See each phase report's own
Section 10/11 for exact commands and counts.

### Gate B (related app suites)
- `apps.portal` + `apps.stores` + `apps.dashboard`: **2368/2368** passed
  (Phase 1 checkpoint).
- `apps.subscriptions` + `apps.billing`: **236/236** passed, 1 skipped
  (Phase 2/3 checkpoint).
- `apps.portal` (standalone): **413/413** passed (Phase 2 checkpoint).
- `apps.orders` (standalone): **329 tests, 323 passed, 6 pre-existing
  failures** — see Section 8.
- `apps.stores` (standalone, after the Phase 5 field rename): initial run
  surfaced 8 errors in `apps/stores/tests/test_integration_service.py`
  (a generic connect/disconnect/tenant-isolation test file that reused
  "enamad" as its example provider and posted the now-retired
  `enamad_code` field) — fixed in commit `6acf8cc`; re-run in progress at
  time of writing (see Section 9 for how to confirm final status).

### Gate C (cross-app regression)
`apps.billing` + `apps.dashboard` + `apps.portal` + `apps.orders` run
together: **2315 tests, 2309 passed, 6 failures, 1 skipped** — the same 6
pre-existing `test_checkout_views.py` failures as Section 8, confirmed by
identical failure count between this combined run and the standalone
`apps.orders` run. No failure in this combined run touches
subscriptions/billing/Zibal/eNamad code.

### Gate D (broad/full project)
Not completed within this session — the full project suite (all apps,
likely 6000+ tests given the per-app counts above) was not run end-to-end
due to the ~15–45 minute wall-clock cost of each large suite already
observed. **Exactly what was run is listed above; "all tests passed" is
not claimed.** A follow-up session should run the complete suite
(`python manage.py test`) as a final Gate D before considering this branch
merge-ready.

### Always-run checks
`git diff --check`: clean (no whitespace errors) at every commit.
`python manage.py check`: 0 issues, checked repeatedly through the
session, clean at the final commit.
`python manage.py makemigrations --check --dry-run`: clean at the final
commit.

## 8. Pre-existing, out-of-scope failure discovered

`apps.orders.tests.test_checkout_views.CheckoutPayTests` has 6 failing
test methods (all around the guest-checkout-with-existing-phone →
OTP-challenge flow, e.g.
`test_guest_with_existing_phone_gets_otp_challenge_without_login_or_order`,
`test_guest_otp_verify_with_wrong_code_shows_error_and_creates_no_order`).
Confirmed **pre-existing and unrelated to this branch's work**:

- `git log -3 --oneline -- apps/orders/tests/test_checkout_views.py` shows
  its last commit as `4b3c8a3` ("Phase 5 Slice 1: page-type allowlist for
  section types"), far before this session's first commit — this session
  never touched this file or the views it exercises.
- The failure reproduces identically whether the file is run alone, as
  part of the full `apps.orders` suite, or as part of the four-app
  combined Gate C run (6 failures in every case).
- The failure is in the OTP/guest-phone-verification flow, adjacent to
  the SMS/OTP territory the master prompt explicitly places out of scope
  for this branch ("another engineering stream is working concurrently on
  Phase 6/SMS... do not edit SMS code unless a strict compile/import
  dependency is unavoidable").

Per the master prompt's own instruction ("if you discover a serious
blocker in one of these [out-of-scope areas], document it and continue
everything else that is achievable"), this was documented rather than
fixed. **This is a real, pre-existing gap in the current `main` branch
that whoever owns `apps.orders`/checkout should investigate** — it is not
a regression introduced by Phases 1–5.

## 9. Known limitations / unresolved items

- **Gate D (full-project suite) was not run** — see Section 7.
- **The `apps.stores` re-run after the `6acf8cc` fix commit had not
  finished at the time this report was last saved** — re-run
  `python manage.py test apps.stores` to get the final confirmed count;
  the same file (`test_integration_service.py`) was the only source of
  failure in the prior run and has been fixed.
- **Browser QA was not performed** (Section 6).
- **Zibal API facts (Phase 3) were triangulated, not confirmed against
  the primary source** (`docs.zibal.ir` is network-blocked in this
  environment) — re-verify before enabling non-sandbox platform payments.
- **No refund automation for Zibal** (platform or merchant) — both
  honestly report `succeeded=False` and require manual/dashboard
  processing, matching the existing `ManualProvider` pattern; Zibal's v1
  IPG API has no documented automated refund endpoint in any source
  reviewed.
- **"Reopen a cancelled/expired trial"** (Phase 2) was deliberately not
  implemented — see the Phase 2 report Section 3/13 for the full
  reasoning and the safe alternative (a new subscription record).

## 10. Push status — GitHub write access blocker

**This branch's 8 commits are not yet on the remote.** Both push paths
available in this session were denied throughout:

- `git push` over HTTPS: `403 Forbidden` directly from GitHub, with no
  credential challenge ever attempted (confirmed via `GIT_CURL_VERBOSE=1`
  — the request went out with no `Authorization` header and GitHub
  rejected it outright).
- GitHub MCP `push_files`: `403 Resource not accessible by integration`
  — retried once after the initial failure, same result.

This is a write-permission gap on the session's GitHub App installation
for `manouchehr94-ux/rastisi5`, not something retrying or routing around
will fix. **An org admin needs to grant this session's GitHub App write
access to this repository** (Claude GitHub settings /
`claude.ai/admin-settings/claude-in-slack`, or by re-authorizing repo
access for this session/environment) before any of this work reaches the
remote branch. Everything is committed locally and ready to push
immediately once access is granted.

## 11. Definition of Done — status against Section 16

| Item | Status |
|---|---|
| Editable platform trial default | ✅ already existed; precedence documented |
| New trials use effective configured policy | ✅ documented precedence (PlanVersion.trial_days at provisioning time) |
| Existing trial dates not rewritten by default changes | ✅ (falls out of the design; verified) |
| Extend/set/end a specific Store trial | ✅ all three implemented this session |
| Manual changes audited | ✅ SubscriptionEvent + audit log, reason mandatory |
| Multiple plans, immutable versions | ✅ already existed |
| Extensible entitlements/limits | ✅ already existed |
| Merchant inspect/renew/upgrade/downgrade | ✅ already existed |
| Expiration does not delete data | ✅ verified by test |
| Platform Zibal configurable, encrypted, request+verify+idempotent | ✅ this session |
| Merchant Zibal per-Store, isolated, tenant-bound | ✅ already existed; isolation now proven by test |
| eNamad technical meta (platform + merchant) | ✅ already existed, verified |
| eNamad safe parser, no raw injection | ✅ already existed + extended to badge |
| eNamad correct-domain-only rendering | ✅ verified + extended |
| eNamad final badge lifecycle | ✅ this session |
| No identity leakage platform↔Store | ✅ verified by test |
| Migrations clean | ✅ |
| Checks clean | ✅ |
| Targeted tests green | ✅ |
| Related app suites green | ✅ except one documented pre-existing, out-of-scope failure |
| Broad regression green "to the practical maximum" | ⚠️ Gate C green (minus the documented pre-existing failure); Gate D not run |
| Reports written | ✅ all 6 |
| No secrets committed | ✅ (verified — no `.env`/credential files staged) |
| No server/deployment changes | ✅ |
| No SMS redesign | ✅ (SMS code untouched) |
| Branch pushed | ❌ **blocked — see Section 10** |
| No PR created | ✅ (none created, per instructions) |

This branch is **not** being represented as "production ready" — real
Zibal credentials, real eNamad values, DNS/TLS, and Phase 6 SMS remain
separate, unstarted gates, and the push blocker means none of this work
is visible on the remote yet.
