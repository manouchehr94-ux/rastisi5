# RastiSi Phase 3 Locust Load-Test Suite — Operator Runbook

**Status: not executed in Claude Code Web.** This suite was built and
smoke-tested in this sandbox only against a throwaway local SQLite-backed
Django dev server (`127.0.0.1`, a handful of users, a few seconds) purely
to prove the tool itself works end to end — safety guard, multi-tenant
Host-header routing, all three workload classes, CSRF handling, and the
RPS/percentile summary report. **No real capacity test was run.** Claude
Code Web has no path to a real staging deployment and must never attempt
one — see "Never target production" below. Real load testing at any of the
required levels (100 through 10,000 users) is an **operator action**, run
from your own machine or a dedicated load-generator host, using the exact
commands in this document.

## 0. Never target production — read this first

This suite has a hard, non-overridable safety guard
(`loadtest/safety.py`) that refuses to send a single request if:

- the connection target (`--host`), or
- any configured `LOADTEST_TENANT_HOSTS` entry, or
- any configured `LOADTEST_ADMIN_HOSTS` entry

is `rastisi.ir` or any subdomain of it (`www.rastisi.ir`,
`platformadmins.rastisi.ir`, any real merchant's `*.rastisi.ir` handle,
...). This check cannot be disabled by any environment variable or flag.

Beyond that hard block, the suite is **default-deny**: nothing runs unless
you explicitly set `LOADTEST_ALLOWED_HOSTS` to the exact staging
hostname(s) you intend to hit. An empty/unset allowlist means the suite
refuses to run at all, on purpose.

**Real merchant custom domains** (a merchant's own `mystoreexample.com`)
cannot be blocked by a fixed list — they're unknowable in advance. The
only protection is you: never add a real merchant's live domain to
`LOADTEST_ALLOWED_HOSTS`/`LOADTEST_TENANT_HOSTS`. Use a dedicated staging
environment with its own non-production hostnames. `loadtest.safety`
prints an advisory (non-blocking) warning if an allowed host doesn't
contain an obvious test/staging marker (`test`, `staging`, `loadtest`,
`localhost`) — take that warning seriously.

Proof this works (from this session's smoke test):

```
$ locust -f loadtest/locustfile.py --host=https://rastisi.ir --headless -u 1 -r 1 --run-time 2s
[...] ERROR/rastisi.loadtest: Refusing to run: 'rastisi.ir' is the real
RastiSi production domain (or a subdomain of it). [...]
$ echo $?
1
```

## 1. Install

```
python3 -m venv .venv-loadtest
.venv-loadtest/bin/pip install -r loadtest/requirements.txt
```

Locust is deliberately not in the main `requirements.txt` — it's a
tooling dependency for whoever runs this suite, not a Django app runtime
dependency.

## 2. Seed deterministic staging fixtures

Run this against your **staging** Django database (never production):

```
python manage.py seed_loadtest_fixtures --stores 5 --products-per-store 100
```

This creates `N` disposable stores (`loadtest-1` .. `loadtest-N`), each
with categories, products (always including a fixed
`loadtest-product-1` slug the Locust tasks depend on), a verified
storefront/admin host, provisioned `ShopSettings`, and ONE shared admin
user (`09120000001`, password `LoadTest!Pass123` by default — override
with `--admin-password`) with OWNER membership in every seeded store.
Idempotent — safe to re-run.

The command prints ready-to-export environment variables at the end:

```
LOADTEST_TENANT_HOSTS=loadtest-1.rastisi.localhost,loadtest-2.rastisi.localhost,...
LOADTEST_ADMIN_HOSTS=loadtest-1.rastisi.localhost,loadtest-2.rastisi.localhost,...
LOADTEST_ADMIN_USERNAME=09120000001
LOADTEST_ADMIN_PASSWORD=LoadTest!Pass123
```

Adjust the hostnames' suffix to match your actual staging domain
configuration (`RASTISI_ADMIN_DOMAIN_SUFFIX`) if it isn't
`rastisi.localhost`.

**Production-lookalike guard**: if your staging environment's domain
configuration is byte-for-byte identical to real production
(`RASTISI_ADMIN_DOMAIN_SUFFIX=rastisi.ir` and `DJANGO_DEBUG=False`), this
command refuses to run unless you also pass `--confirm-not-production`
— on the theory that a config that looks exactly like production deserves
one extra explicit confirmation before this command creates fake data and
a known-password staff account in it.

## 3. Required environment variables

| Variable | Required | Purpose |
|---|---|---|
| `LOADTEST_ALLOWED_HOSTS` | **yes** | Comma-separated safety allowlist — must include `--host` and every tenant/admin host below. |
| `LOADTEST_TENANT_HOSTS` | yes, for storefront/shopper workloads | Comma-separated `Host:` header values simulating different merchant storefronts (multi-tenant spread). |
| `LOADTEST_ADMIN_HOSTS` | yes, for the merchant-admin workload | Comma-separated `Host:` header values for merchant-admin login. |
| `LOADTEST_ADMIN_USERNAME` / `LOADTEST_ADMIN_PASSWORD` | yes, for the merchant-admin workload | From step 2's seed output. |
| `LOADTEST_ENABLE_CHECKOUT_WRITES` | no (default `false`) | Opt-in: exercise cart-add write traffic beyond read-only browsing. |
| `LOADTEST_ENABLE_ADMIN_MUTATIONS` | no (default `false`) | Opt-in extension point for admin write/bulk-action traffic (see locustfile.py's placeholder task). |
| `LOADTEST_THINK_TIME_MIN_SECONDS` / `_MAX_SECONDS` | no (default `2` / `8`) | Per-task pause range — this is what makes "10,000 users" mean 10,000 *paced* virtual humans, not a request burst. |
| `LOADTEST_SLO_P95_MS` / `LOADTEST_SLO_P99_MS` / `LOADTEST_SLO_MAX_FAILURE_RATE_PCT` | no (unset by default) | If set, the end-of-run summary reports PASS/FAIL against *your* chosen numbers. Never hardcoded. |

## 4. Smoke test (always do this first, at low concurrency)

```
export LOADTEST_ALLOWED_HOSTS="your-staging-host.example"
export LOADTEST_TENANT_HOSTS="loadtest-1.your-staging-host.example"
export LOADTEST_ADMIN_HOSTS="loadtest-1.your-staging-host.example"
export LOADTEST_ADMIN_USERNAME="09120000001"
export LOADTEST_ADMIN_PASSWORD="LoadTest!Pass123"

locust -f loadtest/locustfile.py --host=https://your-staging-host.example \
    --headless -u 10 -r 5 --run-time 30s --csv=results/smoke --html=results/smoke.html
```

Confirm: zero "Refusing to run" errors, a nonzero request count, and the
`===== RastiSi Phase 3 load-test summary =====` block at the end showing
RPS/median/p90/p95/p99/max. Only proceed to real load levels once this is
clean.

## 5. Load levels

Named presets live in `loadtest/config.py` (`LOAD_LEVELS`) — `users` is
**virtual users**, not a request rate; each one paces itself with the
think-time range above.

| Level | Users | Spawn rate | Suggested distributed workers |
|---|---|---|---|
| 100 | 100 | 5/s | 1 (standalone is fine) |
| 500 | 500 | 10/s | 1 |
| 1,000 | 1,000 | 20/s | 2 |
| 2,500 | 2,500 | 25/s | 4 |
| 5,000 | 5,000 | 30/s | 8 |
| 10,000 | 10,000 | 40/s | 16 |

Single-process command (100/500, and 1,000 if your load-generator
machine has healthy CPU headroom — watch for the CPU-saturation warning,
§7):

```
locust -f loadtest/locustfile.py --host=https://your-staging-host.example \
    --headless -u 500 -r 10 --run-time 10m \
    --csv=results/500users --html=results/500users.html
```

Repeat with `-u`/`-r` set from the table above for each level you need.

## 6. Distributed workers (required for 2,500+ — see table above)

A single Locust process is CPU-bound; beyond roughly 1,000-2,500
concurrent users (depends entirely on your load-generator's hardware —
see the CPU-saturation warning in §7) one process can no longer generate
load fast enough to be a trustworthy measurement. Locust's own
distributed mode fixes this — run one master and several worker
processes (can be on the same machine for lower levels, must be on
separate machines for 5,000-10,000):

```
# Master (no --headless flags needed here beyond the run config; the master
# coordinates, workers do the actual HTTP calls):
locust -f loadtest/locustfile.py --host=https://your-staging-host.example \
    --master --headless -u 10000 -r 40 --run-time 15m \
    --csv=results/10k --html=results/10k.html

# On each worker (run this on N separate processes/machines — the safety
# guard's `init` event fires on every worker too, so each one independently
# refuses an unsafe target):
locust -f loadtest/locustfile.py --worker --master-host=<master-ip>
```

All the `LOADTEST_*` environment variables must be exported on **every**
worker process, not just the master — each worker independently
evaluates the safety guard and the workload config.

## 7. Detecting load-generator saturation

This is a real failure mode: if the machine *running* Locust runs out of
CPU, the response times you measure reflect Locust's own scheduling
delay, not your target server's real latency — the numbers become
meaningless without telling you so.

This suite surfaces it two ways:

1. Locust's built-in per-process CPU monitor (`events.cpu_warning`) is
   wired to a loud `WARNING`-level log line the moment the load-generator
   process itself crosses ~90% CPU, and a final reminder at
   shutdown if that happened at any point during the run.
2. Watch RPS alongside failure rate as you scale `-u` up: if RPS
   plateaus or drops while failures climb and CPU warnings are firing,
   that's the generator, not necessarily the target. Rule out generator
   saturation (reduce `-u` on this process, add more distributed workers)
   before concluding the *target* has a capacity problem.

## 8. Collecting results

Always pass `--csv=<prefix>` and `--html=<prefix>.html` (as in the
examples above) — Locust writes `<prefix>_stats.csv` (RPS, failures,
avg/min/max, and every standard percentile including p50/p90/p95/p99 per
endpoint and aggregated) and a browsable HTML report. The suite's own
`test_stop` listener additionally prints a compact summary (RPS,
failures, median/p90/p95/p99/max, generator-saturation flag, and — if
`LOADTEST_SLO_*` was set — a PASS/FAIL line) directly to the console/log,
so you don't have to open the CSV just to see the headline numbers.

## 9. Write workloads are opt-in

- `ShoppingCustomerUser`'s cart-add traffic runs by default (it's a
  read-mostly browse-then-add-one-item flow); the actual checkout
  submission (address/payment form POST) is **not wired up** by default
  — see the comment in `checkout_write_flow()` in `locustfile.py`. Wiring
  it up requires per-store checkout fixtures (a shipping method, a
  payment gateway, a valid address) beyond what `seed_loadtest_fixtures`
  creates by default, and should go through `PAYMENTS_SIMULATION_ENABLED`
  on the target staging environment, never a real gateway.
- `LOADTEST_ENABLE_ADMIN_MUTATIONS=true` enables the placeholder admin
  write task — it is a documented extension point (see
  `admin_mutation_placeholder()`), not a stub that fires a real mutation
  out of the box, since which mutation is realistic depends on your
  specific staging store's fixture data.

## 10. Known limitation from this session's local validation

Smoke-testing this suite locally in this sandbox (Django dev server +
SQLite) surfaced `sqlite3.OperationalError: database is locked` on a
fraction of concurrent `POST /cart/add/...` requests. This is SQLite's
own single-writer limitation, not a RastiSi application bug — production
runs PostgreSQL, which handles concurrent writes via row-level MVCC
locking, not a single file lock. **Any real load test must run against a
PostgreSQL-backed staging environment**, matching production's database
engine, or write-heavy results will be artificially worse than reality
(and, at high concurrency, SQLite will simply fail requests that
PostgreSQL would serve correctly).

## 11. What this suite does NOT claim

Per the Phase 3 charter: running this suite, at any level up to and
including 10,000 users, does **not** by itself establish that RastiSi
"supports 10,000 users." It measures what actually happened during one
run against one staging environment at one point in time. Capacity
conclusions belong to a later phase that correlates these results with
target-server-side metrics (CPU, DB connections, error logs) — not to
this tool's console output alone.
