# 10K Architectural & Code Scalability Readiness Review

**Audit branch HEAD reviewed:** `9ebfd10e42342cd598b1d327d4d7864bb95f35f9`
**Scope:** Source-code and architecture review only. No load test was run in this session (Phase 4 already established no valid isolated staging environment exists — see `loadtest/PHASE4_EXTERNAL_EXECUTION_RUNBOOK.md`).

**Question answered:** *If adequate future infrastructure is provided (more app servers, sized PostgreSQL, Redis, load balancer, shared media storage), does the current RastiSi application code/architecture contain blockers that would prevent scaling to ~100 tenant stores × ~100 active users/store (~10,000 total active users)?*

This is explicitly **not** an evaluation of the current small production VPS (2 vCPU / 4GB / 2 Gunicorn workers). That machine's size reflects a pre-launch product, not the architecture's ceiling.

---

## 10K_ARCHITECTURAL_READINESS_STATUS

**READY_WITH_CODE_REMEDIATIONS**

One confirmed, narrowly-scoped code-level data-integrity bug (coupon over-redemption race) needs a small, well-understood fix. Every other dimension reviewed is either already scaling-ready or requires only infrastructure/configuration changes the code already anticipates (in several cases, with system checks and env-var switches already built for exactly this purpose).

---

## EXECUTIVE_VERDICT

Yes — if adequate future infrastructure is provided, RastiSi's current architecture is fundamentally capable of scaling toward ~10,000 active users across ~100 stores. This is a well-structured Django monolith with correct tenant isolation, properly locked and atomic concurrency-sensitive writes (cart, inventory, order creation, billing webhooks, domain verification), DB-backed (not process-local) sessions and OTP state, and several places where the team has *already* anticipated multi-instance deployment (a Redis-swappable rate-limit cache with its own system check, a composite DB index added specifically citing "10k-readiness order volume," documented cron/systemd-based scheduled tasks). One genuine, fixable code bug (coupon redemption race) and one infrastructure change that must happen at the same time as adding a second app server (shared/object media storage) are the two items that need attention — neither is architectural in the sense of requiring a rewrite. No benchmark-proven capacity number can be claimed from source review alone; that remains for a real staging load test (Phase 4/5).

---

## CODE_BLOCKERS

### CB-1: Coupon `used_count` increment is an unlocked read-modify-write — real over-redemption / lost-update race

- **Severity:** Medium (data-integrity correctness bug, not a security or tenant-isolation issue)
- **File/code path:** `apps/orders/services/order_service.py:335-337` (increment) and `apps/cart/services/pricing.py:46` (limit check); `Coupon` model at `apps/cart/models.py:68-106` (no DB-level guard)
- **Current behavior:** `create_order_from_cart` (decorated `@transaction.atomic`) does `coupon.used_count += 1; coupon.save(update_fields=["used_count"])` on a `Coupon` instance that was fetched earlier (`checkout_service.get_applied_coupon`/`apply_coupon`) with a plain, unlocked `Coupon.objects.filter(...).first()`. The earlier `usage_limit` check (`pricing.py:46`: `if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit`) reads whatever `used_count` value was fetched at that point in the request, not a value protected against concurrent modification. There is no `select_for_update()` on the coupon row, no `F("used_count") + 1` conditional update, and no DB `CHECK`/exclusion constraint enforcing `used_count <= usage_limit`.
- **Why it blocks scaling:** This is exactly the class of bug that is invisible at low traffic and real at higher concurrency. At 100 stores × 100 active users, a popular, limited-use coupon (e.g., a launch promotion capped at 50 uses) can plausibly receive multiple simultaneous checkout submissions. Two (or more) concurrent transactions can each read `used_count = 49` (below the limit of 50), each pass the check, and each independently increment — resulting in either over-redemption beyond the merchant's configured cap, or (separately) a lost update where the final stored count undercounts real usage even without exceeding the limit. This is a correctness defect that gets **strictly worse as concurrency increases**, i.e., worse exactly as the platform grows toward the target scale — not a performance question.
- **Concrete evidence:** Confirmed by direct read of `order_service.py:335-337`, `pricing.py:46`, and `apps/cart/models.py:68-106` (Coupon's `Meta.constraints` only enforces `UniqueConstraint(fields=["store","code"])`, nothing about `used_count`/`usage_limit`). No `select_for_update` call site exists anywhere in the coupon read/apply/consume path (grepped `apps/cart/services/*.py` and `apps/orders/services/order_service.py`).
- **Recommended future remediation (not applied in this audit-only session):** Lock the `Coupon` row with `select_for_update()` inside the same atomic block that both re-validates `usage_limit` and performs the increment (mirroring the exact pattern already used correctly for `Product`/`ProductVariant` stock in `_lock_and_revalidate_items`, `order_service.py:91-148`), or replace the read-modify-write with a single conditional `UPDATE ... SET used_count = used_count + 1 WHERE id = ? AND (usage_limit IS NULL OR used_count < usage_limit)` and check the affected-row count (mirroring the already-correct pattern in `apps/catalog/services/inventory_service.py:109-116`'s atomic stock decrement). Both patterns already exist elsewhere in this codebase — this is a consistency fix, not new architecture.
- **Must fix before launch? NO** — coupons are a real but narrow feature; the bug only manifests under genuine concurrent redemption of the *same* limited-use coupon, which is unlikely at pre-launch/early-traffic volumes. It should be fixed before relying on coupons as a scaled promotional mechanism, and is cheap to fix now while the codebase is small. Recommend fixing in the next normal development cycle, not as a blocking pre-launch gate.

### Note: legacy `simulate_payment` guard (not a current blocker)

`apps/orders/services/payment_service.py:71-72`'s `simulate_payment` checks `order.payment_status == PAID` without locking the `Order` row first. This function is reachable only through `apps/orders/views.py:217-235`'s `payment_callback`, which itself immediately 404s unless `settings.PAYMENTS_SIMULATION_ENABLED` is true — and that flag defaults to `False` whenever `DJANGO_DEBUG=False` (`shop_core/settings.py:89`). The **real** merchant payment-gateway path already exists and is correctly built: `apps/orders/services/gateway_payment_service.py` explicitly documents and implements `select_for_update` on `PaymentAttempt` during verification, idempotency keys, and an "already-paid order check" (lines 14-18, confirmed via direct read). This is a dead-code cleanup item for the legacy simulation path, not a production concurrency risk — **not classified as a CODE_BLOCKER**.

---

## SCALING_PREREQUISITES

| ID | Requirement | Why needed | At what growth stage | Code change required? | Infra/config only? |
|---|---|---|---|---|---|
| SP-1 | Point `RASTISI_RATE_LIMIT_CACHE_URL` at a real shared Redis instance | The `"rate_limit"` cache alias defaults to process-local `LocMemCache`; with >1 Gunicorn worker or >1 app server, each process keeps independent counters, weakening (not disabling) brute-force/OTP-spam protection to a per-process limit | As soon as more than one worker process or app-server instance serves traffic (i.e., immediately upon any horizontal scaling step) | NO — code already supports Redis via `redis://`/`rediss://` URL (`shop_core/env_config.py:171-216`), with a Lua-script atomic increment already implemented for the Redis path (`apps/core/services/rate_limit.py`) | YES — env var + provisioning Redis only |
| SP-2 | Configure shared/object media storage (network filesystem or S3-compatible `STORAGES` backend) for `MEDIA_ROOT`/`PRIVATE_MEDIA_ROOT` | Currently local `FileSystemStorage` with no `STORAGES`/`DEFAULT_FILE_STORAGE` override; every product image, export/import file goes to local disk | **Must be done at the same time as adding the 2nd app-server instance** — not deferrable like the others in this table, since running 2+ instances without this causes real functional breakage (image 404s and export-download failures depending on which instance served the request) | SMALL — Django's storage abstraction is already used throughout (no raw hardcoded file paths found in models/views/services); only the one custom `PrivateFileSystemStorage` subclass (`apps/core/storage.py:32`) needs a swapped base class for the private-media case. No model/view code needs to change. | Mostly infra + a small, contained code change (one storage subclass) |
| SP-3 | Add a shared connection pooler (PgBouncer) or tune `CONN_MAX_AGE` once multiple app-server instances exist | `CONN_MAX_AGE` is unset (defaults to Django's `0` — new connection per request); fine for one small instance, but connection count grows linearly with (instances × Gunicorn workers) as more app servers are added | When app-server instance count grows enough that aggregate Postgres connection count approaches the DB's `max_connections` | NO — pure settings/infra | YES |
| SP-4 | Add a tenant/domain-resolution cache (e.g., small-TTL Redis cache keyed by hostname) | Every request currently costs 1 (public storefront) to 3 (with `StorefrontCanonicalRedirectMiddleware`) small, correctly-indexed DB queries purely for Store resolution — correct and stateless, but adds DB round-trips proportional to total request volume | Only if/when DB query load from tenant resolution becomes a measured bottleneck | NO — additive, would not require the existing resolution logic to change, only wrap it | Requires a small code addition (cache-aside) but is not correcting a defect — pure future optimization |
| SP-5 | Ensure the deployment runs `evaluate_subscription_states`, `generate_subscription_renewals`, `process_subscription_dunning`, `cleanup_expired_exports`, `process_notification_outbox`, and related commands on a real external scheduler (cron/systemd timer) | Codebase deliberately has no background job queue (documented "ADR-49"); these management commands are the *only* mechanism that performs subscription/trial/cashback/export-cleanup/notification-delivery state transitions — there is no lazy/on-read fallback | Required from day one of any real deployment, regardless of scale — this is not scale-dependent, it is a correctness prerequisite for the features to work at all | NO | YES — pure ops/scheduler configuration |
| SP-6 | Composite/trigram indexing for platform-admin cross-tenant `icontains` search (Store/User/invoice/domain/audit-log search in `apps/portal/platform_admin_views.py`) | These platform-admin searches are intentionally cross-tenant (not store-scoped) and their working-set grows with the *sum* of all ~100 stores' data, unlike per-store merchant searches | Only relevant once total platform-wide row counts (across all stores) grow large enough for `icontains` scans to be measurably slow — internal-staff-only tool, not part of the 10k end-user traffic path | Possibly (adding a `pg_trgm` GIN index is a migration, not application logic change) | Mostly config/migration |
| SP-7 | Gunicorn worker/thread count and process-manager topology decisions | No code assumes a fixed worker count; the codebase's own production-config doc explicitly leaves this as an open operator decision | Ongoing, tune as real traffic is observed | NO | YES |

---

## BENCHMARK_ONLY_ITEMS

- **Exact Gunicorn worker/thread count** needed at various traffic levels — genuinely requires real load-test evidence (Phase 4/5), not source inspection. Nothing in the code assumes or requires a specific count.
- **Sustainable requests-per-second** at any given infrastructure size — no RPS target is assumed or should be invented per the audit brief; this is real-benchmark territory.
- **Database CPU/IO saturation point** for a given PostgreSQL instance size under the full realistic workload (checkout locking, `icontains` search, dashboard aggregates) — architecture is sound (proper indexing, atomic transactions, no full-table scans on the customer-facing hot paths found), but the exact ceiling is a benchmark question.
- **Exact benefit of adding a tenant-resolution cache (SP-4)** — the current uncached, single-indexed-lookup design is architecturally fine; whether/when it becomes worth the added complexity is a benchmark/monitoring question, not something source review can answer.
- **PgBouncer transaction-pooling compatibility** for the `select_for_update`-heavy checkout/inventory code paths — standard PostgreSQL/Django usage is normally compatible with transaction pooling for this kind of per-request, single-transaction locking, but the exact pooling mode choice and any edge-case incompatibility should be validated against real infrastructure, not assumed from source alone.
- **Worst-case checkout-thread occupancy** from synchronous SMS/Zibal-gateway calls (up to ~5s for SMS, ~30-40s worst-case for gateway timeouts) under real concurrent checkout load — every call has an explicit timeout and graceful typed-error handling (no crash), but whether this becomes a real worker-starvation bottleneck at ~10k-user scale requires load-test evidence, not speculation.

---

## HORIZONTAL_SCALING_VERDICT

**CAN_RASTISI_RUN_MULTIPLE_APP_INSTANCES? YES_WITH_PREREQUISITES**

No process-global mutable state, in-process queue, in-process lock, or process-specific session requirement was found that would break correctness across multiple Gunicorn worker processes or multiple app-server instances. Sessions are DB-backed (no `SESSION_ENGINE` override, Django's default `django.contrib.sessions.backends.db` applies). OTP codes are DB-backed (`OtpCode`, `OwnerOtpChallenge` models), not cache/memory. Cross-host admin handoff uses `django.core.signing` (stateless) plus a DB-backed `AdminHandoffTicket`. The only module-level mutable structures found (`_ADAPTER_CACHE` for payment gateway adapters, `_ENTITLEMENT_MAP_CACHE` keyed with its own freshness check, a lazy `Fernet` cipher singleton, and the already-reviewed `_raw_redis_clients`) are all safe, stateless, per-process optimization caches — losing or duplicating them across processes costs at most a redundant re-instantiation, never a correctness bug.

The prerequisites (not blockers): (1) point the rate-limit cache at shared Redis (SP-1) before relying on precise cross-worker rate limiting; (2) configure shared/object media storage (SP-2) at the moment a second app-server instance is added, since this is the one item that would cause actual functional breakage (not just degraded precision) if skipped.

---

## SESSION_SCALABILITY

Sessions use Django's default database backend (no `SESSION_ENGINE` setting present anywhere in `shop_core/settings.py`) — fully horizontally safe, no sticky sessions required. `apply_remember_me` (`apps/core/services/session_service.py`, `apps/portal/services/session_service.py`) only calls `request.session.set_expiry(...)`, pure Django session API. Multi-step register/login/OTP flows store transient state (`phone`, `purpose`, `remember_me`, `admin_return`) in `request.session[...]` — DB-backed, safe if consecutive requests hit different app instances. OTP verification (both customer/store via `apps/sms/services/otp_service.py` and platform/owner via `apps/portal/services/owner_otp_service.py`) is entirely DB-model-backed (`OtpCode`, `OwnerOtpChallenge`), never cache or in-memory. Cross-host admin handoff (`apps/portal/services/handoff_service.py`) uses a signed token (`django.core.signing`) plus a DB-backed `AdminHandoffTicket` row — no process affinity. CSRF: `CSRF_TRUSTED_ORIGINS` is env-driven and empty by default (must be populated per deployment, growing with each onboarded custom domain — pure config, not code); no `SESSION_COOKIE_DOMAIN`/`CSRF_COOKIE_DOMAIN` override exists, which is the *correct* choice for a platform mixing `*.rastisi.ir` subdomains with arbitrary merchant custom domains (host-only cookies avoid cross-tenant cookie leakage). **Classification: no CODE_BLOCKER; SCALING_PREREQUISITE for the rate-limit cache only (SP-1), which is unrelated to session correctness itself.**

---

## CACHE_AND_RATE_LIMIT_VERDICT

`CACHES["default"]` is `LocMemCache` (process-local) — used only as Django's generic cache alias; nothing found depends on it for cross-process correctness (sessions and OTP are DB-backed, not this cache). `CACHES["rate_limit"]` is a dedicated alias, independently switchable to Redis via `RASTISI_RATE_LIMIT_CACHE_URL` (`shop_core/env_config.py:171-216`), with a **Lua-script-based atomic increment-with-TTL** already implemented specifically to avoid a real TTL-loss race that plain Django `cache.add()`/`cache.incr()` would have on Redis (`apps/core/services/rate_limit.py:64-127`, extensively documented in the source). A dedicated Django system check (`apps/core/checks.py:18-63`, `rate_limit_backend_check`) **warns** (does not error/block deploys) when `DEBUG=False` and the cache is still process-local — exactly the right severity, since per-identifier rate limiting (by phone/account, not just IP) still functions correctly per-worker even without Redis; only the *global* precision is reduced.

**Is shared Redis mandatory for correctness?** No — per-identifier rate limiting still works per-process. **Mandatory only for precise, globally-shared distributed rate limiting across multiple workers/instances?** Yes, and the code already anticipates this with an env-var switch, not a rewrite. **Recommended for performance?** Rate limiting itself isn't a performance cache; recommended specifically for precision at scale. **Not currently needed?** Correct for the current single-small-VPS deployment; becomes a real SCALING_PREREQUISITE (SP-1) the moment more than one worker process or app-server instance is deployed.

**Classification: no CODE_BLOCKER. SP-1 (SCALING_PREREQUISITE).**

---

## MULTI_TENANT_SCALABILITY

`StoreResolutionMiddleware` (`apps/stores/middleware.py:41-47`) calls `resolve_store_for_request` on every request, which performs exactly one DB query (`StoreDomain.objects.select_related("store").filter(hostname=normalized).first()`, `apps/stores/resolution.py:236-238`) against a column with a `unique=True` B-tree index (`StoreDomain.hostname`, `apps/stores/models.py:409-414`) — an O(log n) exact-match lookup regardless of how many stores exist; this is fundamentally different from, and does not exhibit, the "iterate all stores" anti-pattern the audit brief warns about. `StorefrontCanonicalRedirectMiddleware` adds up to two more similarly-indexed lookups for custom-domain canonicalization. No caching layer exists for tenant resolution, and no process-local state is used — a clean, stateless, horizontally-safe design that simply pays a small, fixed number of indexed DB round-trips per request.

A separate, deliberately narrow dev-only compatibility fallback (`resolve_compatibility_store`, capped `Store.objects.all()[:2]`) only triggers for a fixed localhost/testserver allowlist and fails closed the moment a second `Store` exists in the database — not a production concern, and explicitly documented as temporary.

No hidden O(number_of_stores) work was found anywhere in a per-request storefront/customer code path. The handful of unbounded `Store.objects.all()`/`.filter(...)` iterations that do exist are confined to: a standalone, non-request-path system-check function (`apps/stores/services/domain_consistency_service.py`), a one-time legacy-data migration helper, the dev-only compatibility fallback above (capped), and platform-admin dashboard widgets that are themselves explicitly capped (`[:8]`).

**Classification: absence of tenant-resolution caching is SCALING_PREREQUISITE (SP-4) at most, verging on BENCHMARK_ONLY (whether it is ever actually needed depends on real DB load, not something source review can determine) — never CODE_BLOCKER.** The resolution design itself is correct and stateless.

---

## DATABASE_SCALABILITY

Tenant scoping is consistently enforced via a `store` foreign key on tenant-owned models (`Product`, `Order`, `Cart` items via product, `Coupon`, `Vendor`, `Category`, etc.), each carrying the implicit FK index plus, in most cases, an explicit composite unique constraint scoping business-key uniqueness to the store (`uniq_product_slug_per_store`, `uniq_product_sku_per_store`, `uniq_coupon_code_per_store`, and others). `Customer` is a deliberate exception: it has **no** `store` FK by design (documented in-code as an intentional ADR-50 decision — a global platform identity, analogous to a single sign-on account usable across stores), with per-store data instead living on `CustomerProfile`, correctly constrained by `UniqueConstraint(fields=["store","customer"])`. This is a legitimate architecture choice, not an oversight or a scaling defect, though it is worth the owner being aware it exists.

`Order` already carries an explicit composite index — `models.Index(fields=["store","-created_at"], name="orders_store_created_idx")` — added in a prior Phase-2 performance pass with an in-code comment explicitly citing "10k-readiness order volume" and a measured ~150x query-plan improvement at 8,000 seeded orders for one store (Index Scan vs. Seq Scan+Sort). `Product`, by contrast, has `ordering = ["-created_at"]` in its `Meta` but **no equivalent composite index** on `(store, -created_at)` — the same class of cost the Order fix addressed could reappear for merchant product-list pages as individual stores' catalogs grow, though it is mitigated today by the merchant product list already being paginated (bounding how many rows must actually be sorted/returned per page, even if the underlying sort itself isn't index-accelerated). This is the direct carryover of the Phase-2-deferred "product/category composite indexes" item (see PHASE_2_DEFERRED_ITEMS_CLASSIFICATION below).

Concurrency-sensitive writes were checked in depth and are, with the one exception noted in CB-1, correctly built:
- **Cart add/update** (`apps/cart/services/cart_service.py:63-145`): `transaction.atomic()` + `select_for_update()` on both the `Product`/`ProductVariant` and the existing `CartItem` row before computing available stock.
- **Inventory/stock decrement** (`apps/catalog/services/inventory_service.py`): atomic conditional `UPDATE ... WHERE stock__gte=quantity` pattern (`F("stock") - quantity`), correct even without explicit row locks, plus `select_for_update()` used throughout the related restock/adjustment functions.
- **Order creation/checkout** (`apps/orders/services/order_service.py:151-345`): `@transaction.atomic`, idempotency-key-protected (DB partial unique constraint `uniq_order_idempotency_key_when_set` plus an `IntegrityError`-savepoint fallback for the true concurrent-double-submit race), and `_lock_and_revalidate_items` locks `Product`/`ProductVariant` rows in **stable `pk` order** specifically to avoid deadlocks between concurrent transactions touching overlapping products — a textbook-correct pattern.
- **Payment/refund/return records**: `PaymentAttempt` and `RefundItem` also carry partial-unique idempotency-key constraints; the real gateway payment path (`gateway_payment_service.py`) documents and implements `select_for_update` during verification.
- **Platform billing webhook** (`apps/billing/services/webhook_service.py:50-95`): properly idempotent — `select_for_update()` plus a DB `UniqueConstraint(fields=["provider","external_event_id"])` and `IntegrityError` fallback that re-fetches the winning row. This is the correct template the eventual real merchant-payment webhook should also follow (it largely already does, via `gateway_payment_service.py`).
- **Domain ownership/verification** (`apps/stores/services/domain_verification_service.py`): atomic, relies on `StoreDomain.hostname`'s global uniqueness plus `select_for_update()` on the `StoreDomain` (and, for activation, the `Store`) row before mutating verification/`is_primary` state.
- **Coupon usage** (CB-1 above): the one confirmed gap — unlocked read-modify-write, a genuine data-integrity race under concurrent redemption of the same limited-use coupon.

No global serialization point (a single row/table that all requests across all stores must contend for) was found. Each lock scope observed is correctly narrowed to the specific store's own rows.

**Classification: SCALING_PREREQUISITE overall (Product/Category composite index, per PHASE_2_DEFERRED below), plus one CODE_BLOCKER (CB-1).** The data model itself — tenant scoping, constraint design, transaction boundaries — is architecturally sound for 100-store/10k-user growth.

---

## DB_CONNECTION_SCALABILITY

`CONN_MAX_AGE` is not set anywhere in `shop_core/settings.py`, so Django's default of `0` applies (a new connection per request, closed at the end of each request) — safe and correct for a single small instance, but connection count will grow linearly with (number of app-server instances × Gunicorn workers per instance) as horizontal scaling proceeds, and PostgreSQL's `max_connections` is a hard ceiling that must be managed as instance count grows. The project uses `psycopg[binary]>=3.2` (`requirements.txt:10`), a modern driver with good pooling support. No code was found that assumes or requires persistent, long-lived connections in a way incompatible with either raising `CONN_MAX_AGE` or introducing PgBouncer later.

**Classification:**
- **Architectural:** No issue — connection lifecycle is entirely Django's standard per-request model; nothing in application code manages connections itself.
- **Deployment configuration:** `CONN_MAX_AGE` tuning and/or PgBouncer introduction (SP-3) — pure infra/config, to be addressed once app-server instance count grows enough to approach the database's connection ceiling.
- **Requires benchmark evidence:** The exact point at which connection count becomes a problem, and whether PgBouncer transaction-pooling mode interacts cleanly with the `select_for_update`-heavy checkout paths under real concurrent load, are BENCHMARK_ONLY questions.

---

## CONCURRENCY_AND_INTEGRITY

See DATABASE_SCALABILITY above for the full per-operation breakdown. Summary: cart, inventory, order creation, refunds/returns, platform billing webhooks, and domain verification are all correctly guarded with `transaction.atomic()`, `select_for_update()` (in stable `pk` order where multiple rows are locked together, avoiding deadlocks), and/or idempotency-key DB constraints with `IntegrityError` fallback handling for the genuine concurrent-race case. This is evidence-based, not an assumption from passing tests — the locking primitives themselves are present in the source and structurally correct (e.g., `_lock_and_revalidate_items` re-validates stock/status *after* acquiring the lock, not before, which is the detail that actually matters for correctness). The one confirmed gap is CB-1 (coupon `used_count`), a real, narrowly-scoped bug, not evidence of a broader pattern — every other concurrency-sensitive write path checked follows the correct pattern already established elsewhere in the same codebase.

---

## BLOCKING_IO_SCALABILITY

Every synchronous external call found in the request/response cycle has an explicit timeout and a caught, typed failure path that degrades gracefully (no unhandled crash):

| Call | Path frequency | Timeout | Failure handling |
|---|---|---|---|
| Cloudflare Turnstile verify | Rare (owner login/step-up form) | 5s (`TURNSTILE_VERIFY_TIMEOUT_SECONDS`) | Caught, returns a rejected-verification result |
| Zibal payment gateway (create/verify) | Hot — every online checkout and payment callback | `(connect=10s, read=30s)` | Caught per exception type, typed `GatewayConnectionError`/`GatewayResponseError` with user-facing messages |
| Zibal platform-billing calls | Rare (subscription payment/renewal) | Same `(10, 30)` | Same typed-error pattern |
| SMS backends (Melipayamak, Kavenegar) | Hot — customer OTP request/resend wired directly into checkout | 5s | Broad `except Exception` → `SmsSendResult(success=False)` → caught `OtpDeliveryError`, no crash |
| Notification delivery | Not in request path — only via `process_notification_outbox` management command | N/A | N/A (already an outbox pattern designed for external scheduling) |
| Product image processing (Pillow) | Hot for merchant admin uploads | N/A (CPU-bound, size-capped at 5MB) | Raises typed `ProductImageError` on bad input |
| CSV export generation | Merchant admin action, synchronous by explicit design | N/A (local DB + disk) | Exceptions caught, job marked failed |

**Classification: SCALING_PREREQUISITE for all of the above.** Nothing here is architecturally incorrect for horizontal scaling — every external dependency is timeout-bounded and fails without corrupting state or crashing the process. The real cost (a checkout request's worker thread occupied for up to several seconds during SMS/gateway calls, or the full duration of a large export) is a **capacity** question — solvable by adding more app-server workers/processes as load grows — not a **correctness** question. Whether this specific blocking pattern becomes a measurable bottleneck at ~10k-user scale is BENCHMARK_ONLY; source review cannot determine a numeric threshold. The codebase's own design (no Celery, ADR-49) is a deliberate simplicity choice that is not, by itself, wrong for this scale — synchronous calls with real timeouts and graceful degradation are a legitimate architecture for a monolith at this size, and the audit brief explicitly does not require introducing a job queue.

---

## MEDIA_STORAGE_SCALABILITY

`MEDIA_ROOT`, `STATIC_ROOT`, and `PRIVATE_MEDIA_ROOT` (`shop_core/settings.py:314-328`) are all local filesystem paths (env-overridable, but with no storage-backend abstraction configured). There is no `STORAGES` setting, no `DEFAULT_FILE_STORAGE` override, and no `django-storages`/`boto3` dependency anywhere in the repository. Every product image (`ProductImage`, `Vendor.logo`, `Brand.logo`, etc.) uses a plain Django `ImageField`/`FileField` with the implicit default storage; export/import job files (`ExportJob.file`, `ImportJob.source_file`) explicitly use a custom `PrivateFileSystemStorage(FileSystemStorage)` class (`apps/core/storage.py:32`) that is itself hardcoded to local disk.

**The scenario the audit brief poses directly:** if RastiSi runs 3+ Django application servers behind a load balancer, will a product image uploaded through server A be immediately usable from server B? **As shipped today, no** — each instance's local disk is independent, so an image written on A would 404 when a subsequent request happens to land on B, and an export file created on A would fail to download if the follow-up download request lands on B (a real, already-observed pattern in the code: export creation and export download are two separate HTTP requests, `apps/core/services/export_service.py` writes, `apps/dashboard/views.py:6168-6185` `export_download` reads — with no guarantee both hit the same instance).

**Is this a CODE_BLOCKER or a SCALING_PREREQUISITE?** SCALING_PREREQUISITE — but the single highest-priority one identified in this review, and explained carefully as the audit brief requests:

- It is **not** a CODE_BLOCKER in the architectural sense, because the application code never bypasses Django's storage abstraction: every file write/read goes through `FileField.save()`/`.open()` or the equivalent `Storage` API, not a raw hardcoded path manipulation. Swapping the storage backend (to a shared network mount, or to an S3-compatible object store via `STORAGES`) requires **zero changes** to `Product`, `Vendor`, `Brand`, or any other model — Django resolves the active storage backend at the field level automatically. The only code touch needed is swapping `PrivateFileSystemStorage`'s base class for the one custom private-storage class — a small, contained, well-precedented change (directly analogous to how `RASTISI_RATE_LIMIT_CACHE_URL` already swaps the rate-limit cache backend via configuration, with no call-site changes required elsewhere).
- It **is**, however, functionally load-bearing in a way the other SCALING_PREREQUISITEs in this report are not: Redis-for-rate-limiting only *degrades precision* if skipped; running a second app-server instance *without* addressing media storage will cause **outright functional breakage** (broken images, failed downloads) for real users, not just a performance or precision loss. This is why it is called out separately here rather than bundled into the general infrastructure-prerequisites list: it must be resolved **at the same time as**, not sometime after, the step of adding a second app-server instance.

---

## SEARCH_SCALABILITY

All major merchant-facing search endpoints checked (`apps/catalog/views.py` storefront product search, `apps/dashboard/services/catalog_admin_service.py` merchant product search, `apps/dashboard/services/orders_admin_service.py` merchant order search, `apps/dashboard/services/customers_admin_service.py` merchant customer search) apply the store-scoping filter (`store=store` or, for the global-identity `Customer` model, `orders__store=store`) in the **same** queryset chain as the `icontains`/`Q(...)` search predicate — tenant isolation under search is correctly enforced, not an afterthought. `.distinct()` is applied only where a reverse-FK join can genuinely fan out results (the customer search, joining through `orders__store`), and is deliberately omitted elsewhere with an in-code comment explaining why it isn't needed — evidence of care, not oversight.

`icontains` (`LIKE '%...%'`) inherently cannot use a plain B-tree index for a leading wildcard; this is a known, standard PostgreSQL limitation, not a RastiSi-specific defect. At the row counts implied by ~100 users per store, per-store product/order/customer tables remain small enough that this pattern performs acceptably without further indexing; a `pg_trgm` GIN index would be the standard, well-understood future improvement if a specific store's catalog grows very large. The one place this genuinely differs is the platform-admin cross-tenant search (`apps/portal/platform_admin_views.py`) — by design not store-scoped, since platform staff need to search across all ~100 stores at once — whose row counts grow with the **sum** of all tenants' data rather than one store's own volume; this is the more plausible future search bottleneck, and it is internal-staff tooling, not part of the 10k end-user request path.

**Classification: no CODE_BLOCKER found in any search path.** SCALING_PREREQUISITE/BENCHMARK_ONLY for eventual `pg_trgm` indexing, most relevant to the platform-admin cross-tenant searches, not the per-store merchant/customer-facing ones.

---

## BUILDER_SCALABILITY

Storefront builder page/section configuration is stored relationally, not as one large unbounded JSON document: `StorefrontContainer.settings` and `StorefrontCell.settings` (JSONFields) hold small, bounded per-container/per-cell configuration, while actual section content lives in individual `StorefrontSection` rows referenced by FK — so payload size grows with the number of small, discrete JSON dicts, not as one ever-expanding blob. Layout publishing is an atomic DB pointer-swap (no local disk writes found anywhere in `apps/storefront_builder/services/*.py`). The edit-history/"autosave" mechanism (`StorefrontEditHistoryEntry`) is explicitly bounded to a fixed maximum entries per draft (`_MAX_HISTORY_ENTRIES = 30`) and stored in the database, not in memory or on local disk. No process-local caching of builder state was found anywhere in the builder's services — concurrent editing across requests landing on different app-server instances is safe because every operation resolves its state from the database, scoped by `store`, on each request. Preview/storefront rendering uses `select_related`/`prefetch_related` consistently at every relevant call site checked, avoiding an obvious N+1 pattern for the container/cell/section/product-listing traversal.

**Classification: no CODE_BLOCKER found.** 100 stores actively editing/configuring their sites concurrently does not, on this evidence, create an architectural blocker — each store's builder state is independently scoped and DB-resolved. The exact per-request rendering cost under heavy concurrent load (many merchants previewing simultaneously) is BENCHMARK_ONLY.

---

## FILESYSTEM_STATE_REVIEW

The only persistent filesystem dependency requiring multi-server correctness is the media/static storage question already covered in detail under MEDIA_STORAGE_SCALABILITY (SP-2) — no other local-filesystem-as-application-state pattern was found. Production correctly requires PostgreSQL (via `DATABASE_URL`; SQLite is only ever the local-dev/test default, and `build_database_config` raises `ImproperlyConfigured` for anything other than a valid `postgres://`/`postgresql://` URL when configured) — there is no SQLite-in-production assumption anywhere. No temp-file-as-durable-state pattern, and no local-log-file-as-application-state pattern, was found; logging is console-only (`LOGGING` config in `shop_core/settings.py`), appropriate for capture by a process manager/container runtime rather than being read back as application state.

**Classification: SCALING_PREREQUISITE (SP-2), already covered above — no additional filesystem-state findings.**

---

## SCHEDULED_TASK_REVIEW

Every periodic/expiry concern (subscription trial→grace→suspend→cancel transitions, subscription renewal invoice generation, dunning retries, cashback/coupon expiry if applicable, export-job cleanup, notification-outbox delivery, domain/SSL consistency checks) is implemented as a standalone Django management command, and each command's own docstring explicitly states the codebase has no background job queue (citing "ADR-49") and that it must be invoked periodically by an **external** scheduler (cron/systemd timer) — this is a documented, deliberate architecture decision, not an oversight. No "lazy expiry check on read" anti-pattern was found (no inline `if subscription.trial_end_at < now(): expire()` inside a view or model property) — state transitions rely entirely on the relevant command having actually run, meaning the scheduler's existence and correct configuration is a genuine functional prerequisite, not merely a performance one. The `Subscription` model carries an index (`idx_subscription_status_trial` on `(status, trial_end_at)`) explicitly sized for the scheduled-sweep query pattern, not a per-request lookup — further evidence this is intentional, not accidental.

**Classification: SCALING_PREREQUISITE.** This must be configured (an external cron/systemd timer running each command) from day one of any real deployment, regardless of user-count scale — it is a correctness prerequisite for these features to function at all, not something that only matters at 10k users. It does not, however, interact badly with horizontal app-server scaling: these are standalone `manage.py` invocations, not HTTP-triggered, so running multiple app-server replicas has no bearing on them (though the scheduler itself should run on exactly one host/cron entry, to avoid duplicate concurrent runs of the same command — a standard ops consideration, not a code change).

---

## FAILURE_DOMAIN_REVIEW

**Infrastructure-related single points of failure** (expected, not code defects, and not to be treated as findings requiring remediation):
- One PostgreSQL instance — standard; redundancy (replication, backups) is an infra decision outside this review's scope.
- One Redis instance, once introduced for rate-limiting (SP-1) — same category.
- The current single application server — the entire premise of this review is that more instances will be added; the code has been shown to support this.
- One external SMS provider per configured backend, one external payment-gateway provider (Zibal) — standard third-party dependency risk, not an architectural defect; the code already has typed error handling and timeouts around both.

**Application-architecture-related considerations** (already covered in detail above, not repeated as new findings here): the media-storage single-point-of-failure-in-practice (SP-2, until shared/object storage is configured), and the rate-limit cache's per-process fallback (SP-1, until Redis is configured).

No additional application-level single point of failure was identified beyond what is already covered in the sections above.

---

## PHASE_2_DEFERRED_ITEMS_CLASSIFICATION

| Item | Classification | Notes |
|---|---|---|
| Tenant/domain resolution caching | SCALING_PREREQUISITE (SP-4), verging on BENCHMARK_ONLY | Current design is a single indexed lookup per request (up to 3 with canonical-redirect middleware) — correct and stateless. Whether caching is ever actually worth adding depends on real DB load, not determinable from source. |
| Product-detail variants/images prefetch | Already addressed in a prior Phase-2 commit (confirmed via git history — `0d309ef "perf: eliminate storefront product-detail and homepage duplicate queries"`); not re-flagged here as outstanding. |
| `CONN_MAX_AGE` | SCALING_PREREQUISITE (SP-3) | Pure Django setting; relevant once app-server instance count grows enough to threaten Postgres's connection ceiling. No code depends on the current per-request-new-connection behavior in a way that would block raising it. |
| Product/category composite indexes | SCALING_PREREQUISITE | `Order` already received its composite `(store, -created_at)` index in Phase 2 (explicitly citing 10k-readiness in its own commit message and migration comment). `Product` has not received the equivalent index yet, despite also using `ordering = ["-created_at"]` — the same class of "sort every row before returning the first page" cost the Order fix addressed could reappear for merchant product lists as individual stores' catalogs grow, though existing pagination bounds how much of that cost reaches the response. A straightforward, low-risk migration, not requiring new architecture — same fix pattern already proven for Order. |
| Gunicorn worker/thread sizing | BENCHMARK_ONLY | The codebase's own production-configuration documentation explicitly and correctly leaves this to real operator/benchmark judgment; no code assumes a specific count. |

---

## MINIMUM_FUTURE_SCALE_ARCHITECTURE

```
                          Load Balancer
                                |
                -----------------------------------
                |               |                 |
            Django A        Django B          Django C
           (Gunicorn)       (Gunicorn)        (Gunicorn)
                \               |                 /
                 \              |                /
                        PostgreSQL (sized appropriately)
                                |
                              Redis
                     (rate-limit cache; SP-1)
                                |
                  Shared / Object Media Storage
                  (product images, export/import
                   files; SP-2 — REQUIRED at this
                   point, not optional)
```

- **REQUIRED:** Load balancer (to route across multiple Django instances); PostgreSQL sized for the target scale; shared/object media storage (SP-2) — required the moment a second Django instance exists, not merely "nice to have."
- **OPTIONAL (precision, not correctness):** Redis for the rate-limit cache (SP-1) — the platform functions and remains secure without it (per-process rate limiting still applies), but global precision requires it once multiple workers/instances exist.
- **LATER_OPTIMIZATION:** A tenant-resolution cache (SP-4); PgBouncer/connection pooling (SP-3) — relevant only once connection counts or DB round-trip volume are shown by real monitoring to warrant it; `pg_trgm` indexing for platform-admin cross-tenant search (SP-6); Product/Category composite indexes (already a known, low-risk, well-precedented addition, not urgent).

No message queue, no Kubernetes, no microservice split, no read replica, no CDN, and no search engine (Elasticsearch/OpenSearch) is indicated as necessary by any evidence found in this review. This remains, correctly, a well-structured Django monolith — the audit brief's own framing ("a well-structured Django monolith can be horizontally scaled... do not treat 'monolith' as a scalability defect") is borne out by what was actually found in the source.

---

## PRE_LAUNCH_MUST_FIX

None of the findings in this review are classified as required before launch. CB-1 (coupon race) is real but narrow in scope and low-probability at pre-launch/early-traffic volumes; it should be fixed in the ordinary course of development, not treated as a launch gate.

---

## CAN_WAIT_UNTIL_TRACTION

- CB-1 — coupon `used_count` locking fix (cheap to do now, but not urgent; genuinely only matters under real concurrent redemption of the same limited-use coupon).
- SP-1 — Redis for the rate-limit cache (needed once more than one worker process/app-server instance is actually deployed — not needed for a single current small VPS).
- SP-3 — `CONN_MAX_AGE`/PgBouncer (needed only as instance count grows enough to threaten connection limits).
- SP-4 — tenant-resolution caching (optional future optimization; current design is already correct and cheap per-request).
- SP-6 — `pg_trgm` indexing for platform-admin cross-tenant search (internal tooling, not end-user-facing).
- Product/Category composite index (Phase-2-deferred) — low-risk, well-precedented, but not urgent given existing pagination already bounds the customer-facing impact.

---

## REQUIRES_REAL_BENCHMARK_LATER

- Exact Gunicorn worker/thread counts and process topology at various real traffic levels.
- Sustainable requests-per-second at any specific infrastructure size (no number should be invented; this audit deliberately does not propose one).
- Database CPU/IO saturation point for a specific PostgreSQL instance size under the full realistic workload.
- Whether/when a tenant-resolution cache (SP-4) is actually worth adding.
- PgBouncer transaction-pooling mode compatibility with the `select_for_update`-heavy checkout/inventory code paths under real concurrent load.
- Worst-case checkout-thread occupancy from synchronous SMS/Zibal-gateway calls under real concurrent load, and whether it becomes a measurable bottleneck at ~10k-user scale.

---

## Final Matrix

| Area | Current State | Code Blocker? | Scaling Prerequisite? | Benchmark Needed? | Priority |
|---|---|---|---|---|---|
| Horizontal app instances | Stateless middleware/views; DB-backed sessions/OTP; only safe module-level caches found | No | No | No | — |
| Sessions & auth | DB-backed sessions, signed-token + DB-backed admin handoff | No | No | No | — |
| Rate-limit cache | Redis-ready via env var, LocMem fallback with system-check warning | No | Yes (SP-1) | No | Medium |
| Tenant/domain resolution | Single indexed lookup/request, no caching, no O(stores) work | No | Yes (SP-4), low priority | Whether-needed is benchmark-only | Low |
| Database model/constraints | Correct tenant scoping, idempotency keys, locking on cart/inventory/order/billing/domain paths | Yes — CB-1 coupon race only | Yes — Product/Category index (Phase-2-deferred) | No | Medium (CB-1), Low (index) |
| DB connections | Per-request connections, no PgBouncer yet | No | Yes (SP-3) | Connection-ceiling threshold is benchmark-only | Low until instance count grows |
| Blocking I/O (SMS/payment/Turnstile) | Timeout-bounded, typed graceful failure everywhere | No | Capacity is a config/scale question | Yes — worst-case thread occupancy under load | Low-Medium |
| Media/static storage | Local `FileSystemStorage`, no S3/shared backend configured | No (abstraction is swappable) | Yes (SP-2) — highest priority, required at 2nd instance | No | High |
| Search (`icontains`) | Store-scoped correctly everywhere checked; platform-admin search is cross-tenant | No | Yes (SP-6), low priority, staff-only tooling | Eventual `pg_trgm` benefit is benchmark-only | Low |
| Pagination | Paginator used broadly (dashboard + platform admin); two intentional 100-row hard caps | No | No | No | — |
| Storefront builder | DB-relational, atomic publish, bounded edit history, prefetch-optimized rendering | No | No | Per-request render cost under heavy concurrent editing | Low |
| Filesystem/ephemeral state | No local-disk-as-state pattern beyond media storage | No | Covered by SP-2 | No | — |
| Scheduled tasks | Cron/systemd-based by design (ADR-49); no lazy-expiry anti-pattern | No | Yes — must be configured from day one (correctness, not scale) | No | Medium (day-one correctness) |
| Failure domains | Standard infra SPOFs (one DB, one Redis-once-added, one app server today) | No | Covered above | No | — |

---

## FINAL_ANSWER_TO_OWNER

- Yes: if adequate future infrastructure is added, the current RastiSi code and architecture are fundamentally capable of scaling toward ~100 stores × ~100 active users (~10,000 total) — this is not benchmark-proven capacity, but no architectural blocker to reaching it was found.
- One real, narrowly-scoped code bug exists: a coupon-redemption counter can be over-redeemed or undercounted under concurrent checkout of the same limited-use coupon — a small, well-understood fix (the exact locking pattern already used correctly elsewhere in this codebase for stock/inventory), not urgent for launch.
- Sessions, OTP verification, and cross-host admin handoff are all database-backed (not tied to any single server process) — multiple application server instances behind a load balancer will work correctly for these today.
- Cart, inventory, order creation, refund/return, and platform-billing-webhook writes are already correctly protected with atomic transactions, row-level locking (in deadlock-safe stable order), and idempotency-key constraints — this is genuinely well-built for concurrent, multi-instance operation.
- Tenant/domain resolution on every request is a single, correctly-indexed database lookup with no per-store iteration anywhere — it will not get slower in proportion to the number of stores on the platform.
- The rate-limiting security cache is already built to switch to shared Redis via one environment variable, with its own automatic warning if that switch hasn't been made yet in a production-like configuration — this is a configuration step, not a code change.
- The one item that must be addressed at the same time as adding a second application server (not later) is media/file storage: uploaded product images and generated export files currently live on local disk, and a second server would not see files a request happened to land on a different server for. The code already goes through Django's swappable storage layer, so this is a small, well-contained change plus provisioning shared/object storage — not a rewrite.
- Scheduled background work (subscription/trial expiry, renewal invoices, export cleanup, notification delivery) intentionally depends on an external cron/systemd scheduler rather than a job queue — this must be configured correctly from day one regardless of user count; it is a day-one operational requirement, not a 10k-scale concern specifically.
- No message queue, container orchestration platform, microservice split, database read replica, CDN, or dedicated search engine is indicated as necessary by anything found in the source — the current well-structured Django monolith is an appropriate architecture for this target scale, not something that itself needs to change.
- Real sustainable capacity (requests per second, exact server sizing, worker counts) cannot be claimed from this source-code review — that remains a question for a genuine, isolated staging load test once suitable infrastructure exists (the Phase 3/4 Locust harness and runbook are already prepared for exactly this).

---

**STOP.** This is an audit-only review. No application code was modified, no migrations were created, no production configuration was changed, and no remediation was performed in this session. Awaiting explicit operator review before any remediation phase begins.
