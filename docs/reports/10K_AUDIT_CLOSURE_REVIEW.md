# 10K Audit Closure Review

**Reviewed HEAD:** `a8d4f54fdf8f877db7fc1ccbe03ef1f7f02b3ac1` (branch `audit/security-performance-10k-readiness`)
**Scope:** Evidence-based closure pass only — verifies the five pre-launch remediations landed correctly, audits one newly-discovered N+1 without fixing it, and reclassifies every remaining Phase-2-deferred/operational/infrastructure item against current source. No new broad audit was performed; no application code, migrations, settings, or dependencies were changed in this pass.

---

## FINAL_AUDIT_CLOSURE_STATUS

**READY_TO_CLOSE_WITH_OPERATIONAL_PREREQUISITES**

Every confirmed code-level correctness defect (CB-1, the coupon race) is remediated and evidenced under real PostgreSQL row-locking. The private-storage migration-stability gap raised by operator review is corrected and evidenced with a genuine fresh-process test. The Phase-2 product-detail prefetch gap is remediated and evidenced. No new `OPEN_CODE_BLOCKER` was found. What remains open is: day-one operational scheduling (cron/systemd for existing management commands), the Phase-1C security operator-configuration steps (trusted client-IP mode and shared Redis-backed rate-limit counters — both code-ready today, and the Redis item already relevant to the *current* production topology, not merely a future one, since production already runs 2 Gunicorn sync workers), and infrastructure provisioning tied to genuinely future scale milestones (object storage, ahead of a second app-server instance) — plus one newly-confirmed, narrowly-scoped, non-blocking N+1 (Section 9) that is a legitimate future performance item, not a launch blocker.

---

## 1. STARTUP_GATE_STATUS

- Fetched `origin` for `audit/security-performance-10k-readiness` and `main`.
- `origin/audit/security-performance-10k-readiness` = `a8d4f54fdf8f877db7fc1ccbe03ef1f7f02b3ac1` — **MATCH**.
- `origin/main` = `dc71a8135949caa60f20e53da195feb332966bd2` — **MATCH**.
- Local review branch `claude/rastisi-10k-closure-review` created fresh, non-destructively, directly from the canonical audit HEAD (no reset/rebase/rewrite).
- Working tree: clean at gate entry, and clean again after this review (no code changes made).
- Confirmed the five remediation commits present at HEAD (`1d4a748`, `02e2350`, `4409918`, `099fe4a`, `a8d4f54`) are byte-identical in tree content to the locally-authored patch series from the prior remediation session (`git diff <prior-local-head> <canonical-HEAD> --stat` produced no output).

---

## 2. CLOSED_REMEDIATIONS

### A. Coupon concurrency race (CB-1) — CLOSED / REMEDIATED

Direct source verification (`apps/orders/services/order_service.py`): `_lock_coupon()` re-fetches the `Coupon` row with `select_for_update()` **before** `cart_totals()`/`coupon_is_applicable()` runs, and the lock is held through the final `used_count` increment at the end of the same `@transaction.atomic` function — closing the exact TOCTOU window CB-1 described. Behavior preserved: unlimited coupons (`usage_limit=None`), expiration, `min_order`, store scoping (`coupon.store_id != store.pk` raise, checked before any lock work), and the pre-existing silent "not applicable → no discount, no increment" behavior.

Evidence at this HEAD:
- `apps/orders/tests/test_order_service.py::CouponConcurrencySafetyTests` — single redemption, exhausted-coupon rejection, unlimited-coupon repeated use, store isolation, same-code-different-store independence, rollback-does-not-consume-usage. **6/6 pass.**
- `CouponRedemptionRaceConditionTests::test_concurrent_redemptions_never_exceed_usage_limit` — `TransactionTestCase`, 8 real threads racing a coupon with `usage_limit=3`, each thread independently re-reading the coupon unlocked (mirroring `checkout_service.get_applied_coupon`) before calling `create_order_from_cart`. **Re-ran against real PostgreSQL 16 in this session: PASS** — `used_count` never exceeded 3, and `used_count == sum(orders that got the discount)`. Auto-skips correctly on SQLite with an explicit reason (file-level locking cannot prove row-level semantics).
- Rollback: `test_rollback_after_coupon_lock_does_not_consume_usage` forces a `ValueError` after `create_order_from_cart` completes inside an outer `transaction.atomic()`, then asserts `used_count == 0` and that the coupon is still fully usable afterward — confirms rollback genuinely reverts the increment, not merely that it "looks" reverted.

### B. Private/media storage architecture — CLOSED / REMEDIATED (code); provisioning remains infrastructure, correctly deferred

Direct source verification (`apps/core/storage.py`): `private_storage` is now a `_PrivateStorageProxy(LazyObject)` whose `deconstruct()` returns a **fixed** tuple (`("apps.core.storage.PrivateFileSystemStorage", [], {})`, matching `core/migrations/0014_private_storage_deconstructible.py` verbatim) regardless of what `_setup()` actually resolves via `storages["private"]` — while every real I/O call (`save`/`open`/`exists`/`delete`/`path`/`url`) proxies through `LazyObject.__getattr__` to whatever backend is genuinely configured. This mirrors Django's own `default_storage`/`DefaultStorage(LazyObject)` pattern precisely.

This closes the specific gap the operator's review raised: under the **prior** implementation (`private_storage = storages["private"]`, a raw resolved instance), a fresh-process check proved that swapping `STORAGES["private"]["BACKEND"]` to an alternate backend caused `ExportJob.file`'s deconstructed storage kwarg to become the *alternate* backend's own representation — and, concretely, when the alternate backend was not itself deconstructible, produced `AttributeError: 'NoPathStorage' object has no attribute 'deconstruct'` (reproduced directly in this codebase during the correction pass). The corrected proxy design makes this impossible by construction: the deconstructed representation never depends on which backend is actually wired up.

Evidence at this HEAD (`apps/core/tests/test_storage.py`, **6/6 pass**):
- `test_private_storage_is_the_stable_deconstructible_proxy` — deconstruct() is the frozen tuple.
- `test_private_storage_proxies_real_operations_to_the_resolved_backend` — real save/exists/open round-trip through the proxy.
- `test_storages_setting_resolves_a_path_less_backend_for_the_private_alias` — `STORAGES["private"]` swap resolves a fake, `.path`-less backend; full save/open/exists/delete cycle works without `.path`.
- `test_fresh_process_migration_state_is_stable_across_backends` — spawns two **genuinely separate Python processes** (not `override_settings` after model import), one with the normal filesystem backend and one with an alternate path-less backend installed *before* `django.setup()` ever runs. Both processes' `ExportJob.file`/`ImportJob.source_file`/`ImportJob.error_report_file` deconstruct to the identical frozen tuple, and each process independently confirms it actually resolved a *different* concrete backend class at runtime (sanity check against a false-positive).
- `test_fresh_process_makemigrations_check_reports_no_drift_under_alternate_backend` — runs the real `manage.py makemigrations --check --dry-run` management command inside a fresh process with the alternate backend wired in before `django.setup()`. Exit code 0 (no drift) — the strongest available evidence, since it exercises Django's actual autodetector rather than a hand-rolled comparison.
- `test_fresh_process_real_fieldfile_io_through_pathless_backend` — the real model-bound `FieldFile` (not `storages["private"]` called directly) round-trips save/open/exists/delete through the alternate path-less backend, and accessing `.path` raises `NotImplementedError` exactly as it would against a real non-filesystem backend.

`makemigrations --check --dry-run` on the current, real (filesystem) configuration: **"No changes detected."**

Code vs. infrastructure, explicitly separated: the **code** is now fully object-storage-ready and migration-stable under any future backend swap — verified, not asserted. **Provisioning** real shared/object storage remains a pure infrastructure decision, correctly deferred to the moment a second application-server instance is actually added (unchanged from the architecture report's own conclusion; nothing in this pass changes that timing).

### C. Product-detail variant/image prefetch — CLOSED / REMEDIATED

Direct source verification (`apps/catalog/views.py`): `build_product_detail_context()` calls `prefetch_related_objects([product], Prefetch("variants", ..., to_attr="prefetched_variants"), Prefetch("images", ..., to_attr="prefetched_images"))`, and `_variant_groups()`/`_gallery_slides()` read `product.prefetched_variants`/`product.prefetched_images` directly — not `product.variants.all().order_by(...)`/`product.images.all().order_by(...)` as before. This is the correct fix, not the naive one the audit warned against: a bare `prefetch_related("variants", "images")` would not have helped, because both helpers' `.order_by()` bypasses the default prefetch cache and would have added two *wasted* queries on top of the two still-executed re-queries (6 total instead of 4) — `Prefetch(..., to_attr=...)` is what actually avoids the re-query.

Evidence at this HEAD (`apps/catalog/tests/test_product_detail_view.py::ProductDetailVariantImagePrefetchTests`, **3/3 pass**):
- `test_prefetch_is_actually_consumed_not_a_fallback_query` — calls `_variant_groups`/`_gallery_slides` directly against a product with `prefetched_variants`/`prefetched_images` manually populated, inside `CaptureQueriesContext`, asserting **zero** queries — proves the `to_attr` result is genuinely what is read, not merely present alongside a silent fallback query.
- `test_query_count_does_not_grow_with_variant_or_image_count` — isolates the prefetch mechanism itself (not the whole page, which is polluted by the separate N+1 in Section 9 below) across 1 vs. 21 variants / 1 vs. 20 images: exactly 2 queries either way.
- `test_deterministic_ordering_preserved_after_prefetch_fix` — attribute/value ordering for variants, `order` for images, unchanged from pre-fix behavior.

All three call sites that share `build_product_detail_context` (public storefront `product_detail`, dashboard `product_preview`, storefront-builder preview) benefit uniformly, since the prefetch is applied inside the shared function itself rather than duplicated into each caller's own queryset.

---

## 3. OPEN_CODE_BLOCKERS

**None found.** No confirmed data-integrity, tenant-isolation, idempotency, or correctness defect remains open as of this HEAD.

---

## 4. PRE_LAUNCH_CODE_REMEDIATIONS

**None remaining.** CB-1 was the only item in this category; it is closed (Section 2A).

---

## 5. PRE_LAUNCH_OPERATIONAL_REQUIREMENTS

Verified directly against `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` and the actual management commands in source (`ls apps/*/management/commands/`) — no invented commands.

| Command | Exists in source | Documented | Classification |
|---|---|---|---|
| `process_notification_outbox` | yes | yes (this session's prior pass) | **PRE_LAUNCH_REQUIRED** — queued notifications never deliver without it, from the first one, any traffic level |
| `expire_inventory_reservations` | yes | yes | **PRE_LAUNCH_REQUIRED** — abandoned-cart stock never frees without it, any traffic level |
| `evaluate_subscription_states` | yes | yes | **PRE_LAUNCH_REQUIRED** (day-one correctness for trial/grace/suspend transitions, not scale-dependent) |
| `generate_subscription_renewals` / `process_subscription_dunning` | yes | yes | **PRE_LAUNCH_REQUIRED** for stores actually on paid plans |
| `cleanup_expired_exports` / `cleanup_import_files` | yes | yes | **PRE_LAUNCH_REQUIRED**-adjacent (disk hygiene for a feature already in use; not a correctness blocker but files accumulate from day one) |
| `refresh_customer_segments` | yes | yes | GROWTH_STAGE_REQUIRED (materialized segment membership only; live preview always re-evaluates) |
| `cleanup_stale_product_drafts` | yes | yes | GROWTH_STAGE_REQUIRED (UI hygiene only) |
| `verify_domain_consistency` / `verify_subscription_consistency` / `verify_billing_consistency` | yes | yes | OPTIONAL (read-only health checks, monitoring nicety) |

No business rule was found with no operational mechanism at all (e.g., no "cashback expiry" feature exists in source to check — not invented here). All commands an operator would need to schedule already exist and are already documented; **none of this requires a code change** — it requires an operator actually configuring cron/systemd, which remains explicitly out of scope for this and the prior session.

### 5a. Phase-1C security operator-configuration (corrected in this pass)

Two related Phase-1C settings — both default to safe, non-trusting/non-shared behavior and both require deliberate operator action, verified directly against `apps/core/services/rate_limit.py`, `apps/core/checks.py`, `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` §6a, and `docs/reports/PHASE_1C_RATE_LIMIT_RUNBOOK.md`:

| Item | APPLICATION CODE | CURRENT PRODUCTION OPERATOR CONFIGURATION | Classification |
|---|---|---|---|
| Trusted client IP (`RASTISI_TRUST_PROXY_CLIENT_IP`) | **CLOSED / READY** — `client_ip_or_unknown()` defaults to `False` (never reads any client-supplied header, uses validated `REMOTE_ADDR` only); when explicitly set `True` it reads only `HTTP_X_REAL_IP` (never `X-Forwarded-For`), validates it with `ipaddress.ip_address` via `_valid_single_ip()`, and falls back to `"unknown"` on anything absent/invalid. A system check (`apps.core.checks.trust_proxy_debug_check`) warns if this is enabled together with `DEBUG=True`. Verified production evidence: the Nginx config is documented as unconditionally overwriting `X-Real-IP = $remote_addr` on every proxied location, which is exactly the precondition the code requires before this flag is safe to enable. | **PENDING** — `docs/reports/PHASE_1C_RATE_LIMIT_RUNBOOK.md` itself is explicitly headed "**Status: NOT EXECUTED**"; the runbook's own step 7 requires *independently re-confirming* the Nginx `proxy_set_header X-Real-IP $remote_addr;` fact before setting `RASTISI_TRUST_PROXY_CLIENT_IP=True` in production. Not done in this or any prior session — no environment variable was set, no Nginx config was touched. | **PRE_LAUNCH_OPERATIONAL_SECURITY_REQUIREMENT** |
| Shared Redis-backed rate-limit cache (`RASTISI_RATE_LIMIT_CACHE_URL`) | **CLOSED / READY** — `build_rate_limit_cache_config()` (`shop_core/env_config.py`) already switches `CACHES["rate_limit"]` to `django.core.cache.backends.redis.RedisCache` the moment this URL is set, with a Lua-script atomic increment-with-TTL already implemented (`apps/core/services/rate_limit.py`) specifically for correctness under Redis. A system check (`rastisi.core.W001`) already warns under `DJANGO_DEBUG=False` when this is unset. | **PENDING** — unset in production today. **This is not waiting on a future second application server**: previously verified production evidence (cited in the architecture report and re-confirmed here) is that current production already runs **2 Gunicorn sync workers**, so rate-limit counters (login/OTP/signup brute-force protection) are **already split across two independent process-local counters today**, not a hypothetical future condition. This is a documented, bounded security degradation (per-identifier limits — phone/account, not just IP — still apply independently and still function correctly per-worker; it is not a security bypass), not a code defect and not grounds to reopen the audit. | **PRE_LAUNCH_OPERATIONAL_SECURITY_REQUIREMENT** |

Neither item requires (and this pass performed) any code change, Redis installation, or production configuration — both are operator actions to schedule before real merchant launch, using the already-prepared `docs/reports/PHASE_1C_RATE_LIMIT_RUNBOOK.md`.

---

## 6. SCALING_PREREQUISITES

Re-verified directly against current source; no reclassification from the architecture report was warranted for any item below. (Shared Redis for the rate-limit cache was previously listed here; it is corrected and moved to §5a above — it is a pre-launch operational security requirement given the current 2-worker production topology, not a future-scale item.)

| Item | Current state (verified) | Trigger |
|---|---|---|
| Shared/object media storage provisioning | Code confirmed migration-stable and backend-agnostic (Section 2B); **provisioning** itself untouched | BEFORE_SECOND_APP_SERVER (functional breakage otherwise — images/exports 404 depending on which instance served the write) |
| `CONN_MAX_AGE` / PgBouncer | Confirmed absent from `shop_core/settings.py` — still Django's per-request default (`0`) | BEFORE_TRAFFIC_GROWTH (once aggregate connections from instances × workers approach Postgres's `max_connections`) |
| Product composite index `(store, -created_at)` | Confirmed absent from `Product.Meta` (only `Order` has the equivalent `orders_store_created_idx`) — unchanged | BEFORE_TRAFFIC_GROWTH (low-risk, well-precedented, existing pagination already bounds customer-facing impact) |
| Tenant/domain resolution caching | Confirmed unchanged: single indexed `StoreDomain.hostname` lookup per request, no O(stores) pattern anywhere in the request path | WHEN_MEASURED_BY_BENCHMARK |
| `pg_trgm` indexing for platform-admin cross-tenant search | Confirmed unchanged: platform-admin views still the only cross-tenant `icontains` search, correctly capped (`[:8]`) elsewhere | WHEN_MEASURED_BY_BENCHMARK |
| Gunicorn worker/thread sizing | No code assumes a fixed count; genuinely operator/benchmark territory | WHEN_MEASURED_BY_BENCHMARK |

---

## 7. BENCHMARK_ONLY_ITEMS

Unchanged from the architecture report — no new evidence in this pass changes any of these, and none is answerable from source review: exact Gunicorn worker/thread counts, sustainable RPS at a given infrastructure size, database CPU/IO saturation point, whether/when a tenant-resolution cache is worth the complexity, PgBouncer transaction-pooling-mode compatibility with the `select_for_update`-heavy checkout paths, and worst-case checkout-thread occupancy under real concurrent SMS/gateway calls.

---

## 8. OPTIONAL_OPTIMIZATIONS

- Category composite index — still correctly *not* recommended (small, curated, non-monotonic ordering field; verified unchanged).
- `cleanup_stale_product_drafts` scheduling — cosmetic/UI hygiene only, no correctness impact.

---

## 9. VARIANT_SELECTOR_N_PLUS_ONE_CLASSIFICATION

**Function:** `apps/catalog/services/storefront_variant_service.py` — `build_variant_selector_context()` → `_legacy_context()` / `_multi_axis_context()` → `_variant_payload()` → `resolve_display_image()`.

**Exact query path:** for every variant in the loop, `resolve_display_image(product, variant, ...)` calls `variant.images.all()` (one query per variant, never prefetched anywhere in this module) and, when that is empty (the common case for variants without a dedicated image), falls through to `product.cover_image`, whose own implementation (`apps/catalog/models.py`) calls `self.images.all()` again — a **second** per-variant query, since `storefront_variant_service.py` has no knowledge of `build_product_detail_context`'s `product.prefetched_images` (that list is intentionally stored via `to_attr`, precisely so it would *not* populate the default `.images.all()` manager cache — a correct design choice for Section 2C's ordering requirement, but it means this separate code path gets no benefit from it).

**Measured query-count evidence** (isolated call to `build_variant_selector_context(product)`, product with no dedicated variant images so both fallback queries fire):
- 3 variants → 12 total queries.
- 20 variants → 46 total queries.
- Marginal cost: ~2 queries per additional variant, confirmed linear, not O(1).

**Affected paths:** `build_variant_selector_context` is called from `build_product_detail_context`, which is shared by **all three** consumers — the public storefront `product_detail` view (the single highest-traffic storefront page), the dashboard merchant preview, and the storefront-builder preview. This is not a narrow admin-only path.

**Is the same image data already available via the new prefetch?** Partially. `product.prefetched_images` (Section 2C) already holds the product's own images in memory, but (a) it is stored under a custom `to_attr`, not the default manager cache `resolve_display_image`/`cover_image` consult, and (b) `variant.images` is a *different* relation (per-variant, not per-product) that has never been prefetched anywhere in either code path — so even a same-cache-slot fix would only address the `product.cover_image` half of the duplication, not `variant.images.all()`.

**Is a fix small/local or invasive?** Small and local in blast radius (confined to `storefront_variant_service.py` and its two call sites), but not a one-line change: it would need its own `Prefetch(..., to_attr=...)` restructuring for `variant.images` (per variant) analogous to Section 2C's fix, plus either a `getattr`-guarded fallback in `Product.cover_image` (a shared model property used well beyond this one path — product list cards, dashboards, etc.) or a parallel to_attr-based lookup local to this module. Comparable in size and risk to Section 2C's fix, not a rewrite — but it touches a shared helper (`resolve_display_image`, explicitly documented as the single source of truth also used by the dashboard's variant-configuration table) and so needs the same care Section 2C required for its three call sites.

**Classification: SCALING_PREREQUISITE, low-to-medium priority, trigger BEFORE_TRAFFIC_GROWTH.** This is a genuine, confirmed, linearly-growing N+1 — not invented or inflated — but it is purely a query-count/performance concern (no incorrect data, no tenant-isolation impact, no idempotency risk), and at realistic per-product variant counts (typically single digits to low tens) the absolute query volume added per page view (roughly 2×variant-count) remains bounded and non-catastrophic pre-launch. It is the same category the architecture report already used for the pre-fix state of Section 2C itself before that item was remediated — not urgent enough to block launch, but a legitimate, well-scoped item for the next performance pass once real traffic or a larger average variant count makes it measurable. **Not fixed in this session, per instruction.**

---

## 10. DATABASE_SCALE_SANITY

Re-confirmed directly against current source (no reclassification from the architecture report):

- **Tenant scoping**: `store` FK present and enforced on all tenant-owned models checked (`Product`, `Order`, `Coupon`, `Category`, `Vendor`, etc.); `Customer`'s intentional global-identity exception (ADR-50) unchanged and correctly documented, not a scoping gap.
- **Global scans / O(number_of_stores) request paths**: none found in any customer-facing or merchant-facing request path. The handful of unbounded `Store.objects.all()`/`.filter(...)` iterations found (re-grepped this session) are confined to standalone management commands (`provision_default_warehouses`, `verify_inventory_consistency`, `seed_default_shipping_methods`, `generate_subscription_renewals`, `process_subscription_dunning`, `cleanup_import_files`, `refresh_customer_segments`, `cleanup_expired_exports`'s `.iterator(chunk_size=100)`, `legacy_service.py`'s `.iterator(chunk_size=200)`), a dev-only compatibility fallback capped at `[:2]`, and platform-admin dashboard widgets explicitly capped at `[:8]` — unchanged from the architecture report.
- **Unbounded customer/order/product lists**: pagination confirmed still applied broadly in dashboard and platform-admin views; no new unbounded list found.
- **Dangerous cascade patterns**: not newly evaluated beyond what the architecture report already covered; no evidence of a new cascade issue surfaced during this session's direct source reading of `apps/core/models.py`, `apps/catalog/models.py`, `apps/orders/models.py`.
- **Hot counters**: `Coupon.used_count` (the one confirmed race, CB-1) is now closed. `Product.views_count` re-verified this session — uses the atomic conditional `Product.objects.filter(pk=product.pk).update(views_count=F("views_count") + 1)` (a real DB-level atomic increment, not a Python read-modify-write) — correctly race-free. No other unlocked hot-counter increment pattern was found in this pass.
- **Missing tenant scope**: none found beyond the already-documented `Customer` exception.

**Answer: structurally sound with known prerequisites** (the same verdict the architecture report already reached) — for the specific scenarios named (1,000 stores, ~200 products/store, 600k+ images, millions of orders over time), no structural redesign is indicated by source evidence; the known prerequisites are exactly the SCALING_PREREQUISITEs already listed in Section 6, none of which require a data-model change. This is not a benchmark-proven capacity claim.

---

## 11. SECURITY_CLOSURE_STATUS

No code in this session's remediation or this closure pass touched authentication, rate limiting, OTP, redirect handling, domain verification, or webhook processing — so this section reports direct-evidence re-confirmation, not a new audit.

| Item | Status | Evidence |
|---|---|---|
| Admin/customer login, signup rate limiting | CODE FIXED, unchanged | `enforce_rate_limit` wired in `apps/sms/services/otp_service.py`, `apps/customers/views.py`, `apps/content/views.py`, `apps/dashboard/views.py`, `apps/portal/views.py`, `apps/portal/platform_admin_views.py`, `apps/portal/services/owner_otp_service.py` — confirmed present via direct grep this session |
| OTP enumeration | CODE FIXED, unchanged | DB-backed `OtpCode`/`OwnerOtpChallenge`, not process-local; unaffected by this session |
| Open redirect | CODE FIXED, unchanged | `apps/portal/views.py::_is_safe_next()` guard confirmed present, applied to the `next` param before any redirect |
| SSRF-adjacent domain verification | CODE FIXED, unchanged | `apps/stores/services/domain_verification_service.py` real DNS TXT/CNAME lookups via `dnspython`, no fetch-and-follow of user-supplied URLs |
| Webhook tolerance/idempotency | CODE FIXED, unchanged | `apps/billing/services/webhook_service.py` `select_for_update()` + `UniqueConstraint(provider, external_event_id)` confirmed present |
| Django/cryptography dependency floors | CODE FIXED, current | `requirements.txt`: `Django>=5.2.17,<6`, `cryptography>=50.0,<51` — both current major/patch lines as of this review; installed and verified at `Django 5.2.17` in this session's environment |
| Trusted client IP handling | **CODE FIXED / READY**; **OPERATOR CONFIGURATION PENDING before real merchant launch** (corrected in this pass — see §5a) | `client_ip_or_unknown()` defaults non-trusting, validates `HTTP_X_REAL_IP` with `ipaddress` when explicitly enabled, never trusts `X-Forwarded-For`; production Nginx is documented to overwrite `X-Real-IP` unconditionally, but `RASTISI_TRUST_PROXY_CLIENT_IP=True` has not actually been set (`PHASE_1C_RATE_LIMIT_RUNBOOK.md` status: NOT EXECUTED) |
| Shared rate-limit backend readiness | **CODE FIXED / READY**; **OPERATOR CONFIGURATION PENDING before real merchant launch** — and already relevant *today*, not only at future scale (see §5a) | `RASTISI_RATE_LIMIT_CACHE_URL` unset in this environment; code-side Redis switch and Lua-script atomic increment confirmed intact; current production's 2 Gunicorn sync workers already keep separate rate-limit counters as a result |

No previously-identified security issue was found reopened or regressed by this session's changes (none of the five remediation commits touch any file in `apps/portal`, `apps/sms`, `apps/customers/views.py`, `apps/stores/services/domain_verification_service.py`, or `apps/billing/services/webhook_service.py`).

---

## 12. SECTION 8 — FINAL BLOCKER SWEEP

Focused re-scan, evidence-based only (not a new broad audit):

- **Data-integrity races**: CB-1 closed (Section 2A); no other unlocked hot-counter or read-modify-write race found (Section 10).
- **Payment/idempotency regressions**: none — `gateway_payment_service.py`'s `select_for_update`/idempotency-key pattern and the billing webhook's idempotency (Section 11) untouched by this session.
- **Tenant isolation regressions**: none — the coupon fix explicitly re-validates `coupon.store_id != store.pk` before any lock work (unchanged from before); the storage fix and prefetch fix touch no tenant-scoping code at all.
- **Filesystem coupling**: closed for the one remaining item (Section 2B); no other hardcoded local-path dependency found in this pass beyond what the architecture report's exhaustive A–L verification already covered.
- **Process-local correctness state**: none introduced — `_PrivateStorageProxy` is a per-process singleton cache of a *reference*, not correctness-bearing state (losing/duplicating it across processes costs at most a redundant re-resolution, exactly like Django's own `default_storage`).
- **Unsafe background-task assumptions**: none — no background task queue exists (ADR-49, unchanged); this session added no new scheduled-task code.
- **High-impact unbounded queries**: the one new confirmed item is Section 9 (variant-selector N+1) — classified, not a blocker.
- **Accidental new migration drift**: `makemigrations --check --dry-run` on this HEAD reports "No changes detected"; the fresh-process test additionally proves this holds even under a hypothetical future backend swap (Section 2B).
- **Unresolved audit TODOs**: none found referencing this audit specifically in the remediated files (`grep -rn "TODO" apps/orders/services/order_service.py apps/core/storage.py apps/catalog/views.py` — no hits tied to CB-1, the storage proxy, or the prefetch fix).

---

## 13. TESTS_RUN

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `apps.orders.tests.test_order_service` (coupon concurrency + full order-service suite)
- `apps.core.tests.test_storage` (private-storage migration stability + fresh-process tests)
- `apps.catalog.tests.test_product_detail_view` (prefetch regression coverage)
- `apps.orders.tests.test_catalog_store_boundary` (tenant isolation, cross-store rejection)
- `apps.orders.tests.test_order_service.CouponRedemptionRaceConditionTests` against real PostgreSQL 16 (throwaway local database)
- A throwaway (not committed) query-count probe against `build_variant_selector_context` to obtain Section 9's evidence, removed after use — confirmed `git status` clean afterward

Not re-run: the full 5968-test suite. Per the operator's instruction, this was not required given no code changed in this pass, and the following prior-session evidence is cited (all against tree-identical content, confirmed via empty `git diff` against the canonical HEAD):
- 70 targeted local tests PASS, 1 expected SQLite concurrency skip.
- 4385 broad local regression tests PASS, 5 skipped.
- Full local suite: 5968 PASS, 8 skipped.
- Real PostgreSQL coupon concurrency validation: PASS.

## 14. TEST_RESULTS

All tests run in this session: **PASS**. `manage.py check`: clean. `makemigrations --check --dry-run`: "No changes detected." Targeted suites: 76/76 pass (1 expected SQLite skip) plus 6/6 storage tests plus the PostgreSQL concurrency test — all green. No failures, no errors, no unexpected skips.

## 15. FILES_CHANGED

None (review-only pass, as instructed). This document is the only addition.

## 16. COMMITS_CREATED

One documentation-only commit adding this file: `docs(audit): add 10K audit closure review`.

## 17. GIT_FINAL_STATE

Branch `claude/rastisi-10k-closure-review`, created from and currently one commit ahead of canonical `a8d4f54fdf8f877db7fc1ccbe03ef1f7f02b3ac1`. Working tree clean after the documentation commit. No merge into `main`, no PR, no push attempted (push was already established as blocked by an environment/permissions gap in the prior session; not retried here since this is a review-only pass and the operator has not asked for delivery of this branch).

---

## FINAL_OPERATOR_RECOMMENDATION

**A. Can the audit branch now be considered technically complete?** Yes, for code. All confirmed code-level blockers and pre-launch code remediations identified across this audit's lifecycle are closed and evidenced, including under real PostgreSQL concurrency and a genuine fresh-process migration-stability test. The one newly-discovered item (variant-selector N+1, Section 9) is a legitimate future performance item, not a completeness gap — the audit's own standard throughout has been to not block closure on non-urgent, non-correctness performance opportunities, and this item meets that same bar.

**B. Is it safe to begin controlled merge planning into main?** Yes, from a code-correctness standpoint — nothing found in this pass should block planning a merge. The two things worth sequencing deliberately, not as blockers but as plan inputs: (1) confirm main's own history hasn't diverged further since `dc71a813` in a way that creates conflicts (a routine merge-planning step, not a code-quality question); (2) this branch's push to origin has been blocked by an environment permission gap in prior sessions — resolving that (or applying the already-exported patch series) is a prerequisite to any merge mechanics, independent of code readiness.

**C. What must still be done before real merchant launch?** Purely operational, not code — two categories, both already fully code-ready:

  (A) Required scheduled management commands (Section 5): `process_notification_outbox`, `expire_inventory_reservations`, `evaluate_subscription_states`, and the billing renewal/dunning pair if paid plans are live, via real cron/systemd.

  (B) Phase-1C security operator configuration (§5a): (i) enable trusted `X-Real-IP` mode (`RASTISI_TRUST_PROXY_CLIENT_IP=True`) after independently re-confirming the already-documented Nginx `proxy_set_header X-Real-IP $remote_addr;` topology, per the runbook's own step 7; (ii) provision and point `RASTISI_RATE_LIMIT_CACHE_URL` at a shared Redis instance so brute-force/OTP-spam rate limiting is precise across worker processes — this is not a future-scale nicety, since current production already runs 2 Gunicorn sync workers and is therefore already running with split, per-process counters today.

**D. What can safely wait until traffic/benchmark evidence exists?** Everything in Sections 6–8 *except* the Phase-1C items moved to §5a: object-storage provisioning (tied to the *second* app-server instance, not to launch itself), `CONN_MAX_AGE`/PgBouncer, the `Product` composite index, tenant-resolution caching, `pg_trgm` indexing, Gunicorn sizing, and the Section 9 variant-selector N+1 — all correctly deferred, none blocking a pre-market launch with the current single small production instance. Shared Redis and trusted-IP configuration are **not** in this deferred set (see C above).

---

**STOP.** This is a closure review only. No remediation performed, no merge, no deployment, no benchmark execution, no infrastructure change. Awaiting operator review.
