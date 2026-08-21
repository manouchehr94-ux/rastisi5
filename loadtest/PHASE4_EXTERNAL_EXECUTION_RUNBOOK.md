# RastiSi Phase 4 — Staging Capacity Benchmark: External Execution Runbook

**Status of this document: PREPARED_FOR_EXTERNAL_EXECUTION.** No capacity
benchmark was run to produce this runbook. It was authored by inspecting the
Phase 3 harness (`loadtest/`) and the application's own environment-driven
configuration (`shop_core/env_config.py`, `shop_core/settings.py`,
`apps/stores/management/commands/seed_loadtest_fixtures.py`) as of audit HEAD
`4521b82fdd455b168c19bae50e4ce4f6afe28c56`. Every command below is exact and
copy-pasteable for whoever runs this on real infrastructure — it is not a
generic Locust tutorial.

## 0. Why this session did not run a real benchmark

The Claude Code Web container this Phase 4 session runs in was checked
against the "valid Phase 4 capacity environment" bar from the audit charter
and fails it structurally, not for lack of trying:

| Requirement | This container |
|---|---|
| Isolated from production | Yes |
| No production data | Yes |
| PostgreSQL, not SQLite | `psql` binary present, cluster installed but **stopped**; would need to be started fresh with no data |
| Django behind Gunicorn | Gunicorn **not installed** |
| Phase 3 deterministic fixtures | Available (`seed_loadtest_fixtures`), never run here |
| Safe test-only hostnames | Configurable, not yet configured |
| Host safety guard fully enabled | Confirmed working — see §TOOL_VALIDATION_ONLY below |
| Real external side effects prevented | Configurable via `PAYMENTS_SIMULATION_ENABLED`, SMS backend, etc. |
| Monitoring visibility to correlate load with behavior | Limited — single container, no separate app/DB hosts to attribute bottlenecks to |
| **A second machine to run the load generator on** | **Does not exist** — this is one 4 vCPU / 15 GiB RAM container |

The last row is disqualifying on its own: `loadtest/README.md` (Phase 3's own
runbook, §7) documents that a load generator sharing a machine with its
target invalidates capacity results once concurrency rises, because CPU
contention between Locust and the Django process being measured makes
response-time numbers reflect generator scheduling delay, not real server
latency. This container cannot provision a second host. It is also ephemeral
— reclaimed at the end of this session — so even a same-box measurement
would not persist as a reusable staging environment for Phase 5 to build on.

Per the audit charter: no capacity numbers were fabricated, extrapolated, or
inferred from local smoke tests to fill this gap. Two tiny checks were run
to confirm the harness itself still works in a fresh session; both are
labeled `TOOL_VALIDATION_ONLY` and must never be read as capacity evidence.

### TOOL_VALIDATION_ONLY

1. `python -m unittest discover -s loadtest/tests` — all 54 tests in
   `loadtest/tests/test_safety.py` and `loadtest/tests/test_config.py` pass
   in this fresh checkout (safety-guard and config-parsing logic only; no
   network I/O).
2. `locust -f loadtest/locustfile.py --host=https://rastisi.ir --headless -u 1 -r 1 --run-time 2s`
   — reproduced the Phase 3 proof that the hard guard still refuses the real
   production domain (`UnsafeLoadTestTargetError`, zero requests sent), and a
   parallel run against an explicitly-allowlisted non-resolving test hostname
   (`loadtest.invalid.local`) proceeded past the guard with 0 requests (no
   server was listening) — confirming the guard is a targeted block, not a
   blanket one. Neither run touched a real host or produced a request/latency
   measurement of any kind.

## 1. Provisioning an isolated staging host

Use a disposable VM or container, **never** the production VPS. Minimum
spec to be meaningfully comparable to production: match production's real
vCPU/RAM/disk where known; if unknown, record actual staging specs honestly
in the topology table (§below) rather than guessing production's.

```bash
# Example: a plain Ubuntu 22.04/24.04 VM from any provider, sized to your
# judgement of production capacity. Nothing RastiSi-specific here.
ssh <staging-host>
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip postgresql postgresql-contrib \
    redis-server build-essential libpq-dev
```

A **separate** host (or at minimum a separate VM on different CPU
allocation) must run the Locust load generator — see §26.

## 2. Clone the exact audit branch

```bash
git clone https://github.com/manouchehr94-ux/rastisi5.git
cd rastisi5
git fetch origin audit/security-performance-10k-readiness
git checkout audit/security-performance-10k-readiness
```

## 3. Verify HEAD

```bash
git rev-parse HEAD
# must print exactly:
# 4521b82fdd455b168c19bae50e4ce4f6afe28c56
```

If this does not match, STOP — you are not benchmarking the code this
runbook was written against.

## 4. Create an isolated Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

## 5. Install application dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` already includes `psycopg[binary]` (PostgreSQL driver).
Also install a production-like application server, which is **not** in
`requirements.txt` (deliberately — see §11):

```bash
pip install gunicorn
```

## 6. Install `loadtest/requirements.txt`

```bash
pip install -r loadtest/requirements.txt
```

This installs `locust>=2.46,<3` — kept out of the main requirements file on
purpose (tooling dependency for the operator/generator host, not a Django
runtime dependency).

## 7. Configure PostgreSQL safely

```bash
sudo -u postgres psql -c "CREATE USER rastisi_loadtest WITH PASSWORD '<generate-a-random-password>';"
sudo -u postgres psql -c "CREATE DATABASE rastisi_loadtest OWNER rastisi_loadtest;"
```

Never point `DATABASE_URL` at any production database. Never copy a
production database dump into this staging database — fixtures come from
`seed_loadtest_fixtures` only (§10).

## 8. Configure staging-only environment variables

```bash
export DJANGO_DEBUG=True
# DEBUG=True is deliberate here: it keeps PAYMENTS_SIMULATION_ENABLED
# defaulted to True (shop_core/settings.py) and avoids requiring a
# production-grade DJANGO_SECRET_KEY/DJANGO_ALLOWED_HOSTS setup that would
# make this environment config-indistinguishable from real production —
# see the seed command's own production-lookalike guard in §10.
export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
export DATABASE_URL="postgres://rastisi_loadtest:<password>@127.0.0.1:5432/rastisi_loadtest"
export RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.localhost"
# Explicitly keep real external side effects OFF:
export PAYMENTS_SIMULATION_ENABLED=True
# Confirm your SMS backend env vars (Melipayamak/Kavenegar credentials) are
# UNSET on this host — apps/sms/services/backends.py must not be able to
# reach a real provider from staging. Do not export real SMS/Zibal secrets
# here under any circumstance.
```

Add any other `DJANGO_*`-prefixed variables your deployment normally
requires (email backend, etc.) pointed at safe no-op/console backends, never
production credentials.

## 9. Apply migrations

```bash
python manage.py migrate
```

## 10. Seed deterministic load-test stores

```bash
python manage.py seed_loadtest_fixtures --stores 100 --products-per-store 100
```

This matches the audit's target multi-tenant model (100 stores). It is
idempotent — safe to re-run. It creates one shared admin user
(`09120000001` / `LoadTest!Pass123` by default) with OWNER membership in
every seeded store, and prints ready-to-export
`LOADTEST_TENANT_HOSTS`/`LOADTEST_ADMIN_HOSTS` values — capture that output,
you need it for §14-16.

Because `RASTISI_ADMIN_DOMAIN_SUFFIX=rastisi.localhost` (§8) is not
byte-for-byte identical to production's `rastisi.ir`, the command's
production-lookalike guard does not require `--confirm-not-production`
here. If your staging domain config is ever set to look identical to
production, the command will refuse until you pass that flag explicitly —
do not do so unless you have independently confirmed this is not the real
production database.

Record the exact dataset produced (row counts) per the audit's
DATASET requirements:

```bash
python manage.py shell -c "
from apps.stores.models import Store
from apps.catalog.models import Product, Category
from django.contrib.auth import get_user_model
User = get_user_model()
print('stores', Store.objects.count())
print('products', Product.objects.count())
print('categories', Category.objects.count())
print('users', User.objects.count())
"
```

## 11. Start a production-like Gunicorn target

```bash
export DJANGO_SETTINGS_MODULE=shop_core.settings
gunicorn shop_core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class sync \
    --threads 1 \
    --timeout 30 \
    --keep-alive 2 \
    --access-logfile - \
    --error-logfile -
```

The worker/thread/timeout values above are Gunicorn defaults / common
starting points, chosen because Phase 2 explicitly deferred Gunicorn
worker/thread sizing to benchmark evidence (item 5, §PHASE_2_DEFERRED). **Do
not tune these before or during the baseline run** — record whatever you
start with, run the baseline, and let Phase 5 decide whether to change them.
Record the exact values used (worker count, worker class, threads, timeout,
keep-alive, bind) in the topology table — see §STAGING_TOPOLOGY.

## 12. Optionally configure staging Nginx

Only if your production topology puts Nginx in front of Gunicorn — mirror
that here for topology parity, terminating TLS or not to match production.
If you skip this, document it as a material difference from production.

```bash
sudo apt-get install -y nginx
# minimal reverse proxy to Gunicorn on :8000, e.g.:
# server { listen 80; server_name *.rastisi.localhost;
#   location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; } }
```

## 13. Configure safe staging hostnames

On the load-generator host (and anywhere else that needs to resolve these),
map the tenant/admin hostnames printed by `seed_loadtest_fixtures` (§10) to
the staging target's IP, e.g. via `/etc/hosts`:

```
<staging-target-ip>  loadtest-1.rastisi.localhost
<staging-target-ip>  loadtest-2.rastisi.localhost
... (one line per seeded store)
```

None of these may ever be `rastisi.ir` or a subdomain of it — the safety
guard hard-blocks that unconditionally regardless of `/etc/hosts` content.

## 14. Configure `LOADTEST_ALLOWED_HOSTS`

```bash
export LOADTEST_ALLOWED_HOSTS="loadtest-1.rastisi.localhost,loadtest-2.rastisi.localhost,...<all seeded hosts>...,<the --host you'll pass to locust>"
```

Must include every tenant/admin host from §10's output, plus whatever host
you pass to `locust --host=`. Default-deny: anything left out is refused.

## 15. Configure `LOADTEST_TENANT_HOSTS`

```bash
export LOADTEST_TENANT_HOSTS="loadtest-1.rastisi.localhost,loadtest-2.rastisi.localhost,...<all seeded hosts>..."
```

Copy verbatim from §10's printed output.

## 16. Configure `LOADTEST_ADMIN_HOSTS`

```bash
export LOADTEST_ADMIN_HOSTS="loadtest-1.rastisi.localhost,loadtest-2.rastisi.localhost,...<all seeded hosts>..."
export LOADTEST_ADMIN_USERNAME="09120000001"
export LOADTEST_ADMIN_PASSWORD="LoadTest!Pass123"   # or whatever --admin-password you used in §10
```

## 17. Confirm checkout/admin mutation flags are disabled

```bash
echo "LOADTEST_ENABLE_CHECKOUT_WRITES=${LOADTEST_ENABLE_CHECKOUT_WRITES:-unset (defaults false)}"
echo "LOADTEST_ENABLE_ADMIN_MUTATIONS=${LOADTEST_ENABLE_ADMIN_MUTATIONS:-unset (defaults false)}"
```

Both must be unset/false for the baseline read-heavy benchmark (§DEFAULT
WORKLOAD in the audit charter). Leave them off for every level in the
baseline table; only turn `LOADTEST_ENABLE_CHECKOUT_WRITES=true` on for a
separately labeled `WRITE_WORKLOAD` run, reported separately, never mixed
into the baseline table.

## 18. Run a safety-guard validation

From the **load-generator** host, exported with all `LOADTEST_*` vars from
§14-17:

```bash
# Must be refused — proves the hard block is live on this host:
locust -f loadtest/locustfile.py --host=https://rastisi.ir --headless -u 1 -r 1 --run-time 2s
echo "exit code: $?"   # must be non-zero, log line must say "Refusing to run"

# Must be refused — proves default-deny when the allowlist doesn't cover it:
env -u LOADTEST_ALLOWED_HOSTS locust -f loadtest/locustfile.py \
    --host=https://loadtest-1.rastisi.localhost --headless -u 1 -r 1 --run-time 2s
echo "exit code: $?"   # must be non-zero
```

Do not proceed to §19 until both checks behave as documented.

## 19. Run a tiny staging smoke test

```bash
locust -f loadtest/locustfile.py --host=https://loadtest-1.rastisi.localhost \
    --headless -u 10 -r 5 --run-time 30s \
    --csv=results/smoke --html=results/smoke.html
```

Confirm: zero "Refusing to run" errors, nonzero request count, the
`===== RastiSi Phase 3 load-test summary =====` block prints RPS and
percentiles, and Gunicorn's access log shows real 2xx/3xx responses. Only
proceed to §20 once this is clean. This smoke test itself is
`TOOL_VALIDATION_ONLY` — its numbers are not capacity evidence (10 users, 30
seconds is not a steady-state measurement).

## 20-25. Load levels — run in this order, do not skip ahead

Do not jump directly to a higher level. If a lower level is already
catastrophically unstable (majority failures, Gunicorn workers crashing,
Postgres connection exhaustion), stop and document why higher levels were
not run rather than proceeding.

Recommended duration and spawn rate per level (spawn rates are Phase 3's own
`loadtest/config.py` `LOAD_LEVELS` values; durations below add a
stabilization window before the steady-state measurement period the audit
charter requires):

| # | Level | Users (`-u`) | Spawn rate (`-r`) | Recommended `--run-time` | Rationale |
|---|---|---|---|---|---|
| 20 | 100 | 100 | 5 | 5m | ~20s ramp-up, several minutes of steady state at low load |
| 21 | 500 | 500 | 10 | 10m | ~50s ramp-up; matches README's own 500-user example |
| 22 | 1,000 | 1,000 | 20 | 10m | ~50s ramp-up; last level safely single-process on typical hardware — watch CPU-saturation warning (§32) |
| 23 | 2,500 | 2,500 | 25 | 15m | ~100s ramp-up; distributed workers required (§26) |
| 24 | 5,000 | 5,000 | 30 | 15m | ~167s ramp-up; distributed workers required |
| 25 | 10,000 | 10,000 | 40 | 20m | ~250s ramp-up; distributed workers required, matches README's own 10k example |

Before interpreting any level's numbers, discard the ramp-up window and the
first ~1 minute after full ramp-up as stabilization; treat the remainder of
`--run-time` as the steady-state measurement period.

### §20 — 100 users

```bash
locust -f loadtest/locustfile.py --host=https://loadtest-1.rastisi.localhost \
    --headless -u 100 -r 5 --run-time 5m \
    --csv=results/100users --html=results/100users.html
```

### §21 — 500 users

```bash
locust -f loadtest/locustfile.py --host=https://loadtest-1.rastisi.localhost \
    --headless -u 500 -r 10 --run-time 10m \
    --csv=results/500users --html=results/500users.html
```

### §22 — 1,000 users

```bash
locust -f loadtest/locustfile.py --host=https://loadtest-1.rastisi.localhost \
    --headless -u 1000 -r 20 --run-time 10m \
    --csv=results/1000users --html=results/1000users.html
```

Watch the console/log for `cpu_warning` lines from Locust's own monitor — if
they fire, the generator itself may be the bottleneck; consider moving to
distributed mode (§26) even at this level.

### §23-25 — 2,500 / 5,000 / 10,000 users (distributed, see §26)

Config values per §26, `-u`/`-r` from the table above.

## 26. Distributed Locust master/workers (required for 2,500+)

One Locust process is CPU-bound; beyond roughly 1,000-2,500 users a single
process cannot generate load fast enough to be trustworthy. Use Locust's own
distributed mode. Suggested worker counts from `loadtest/config.py`'s
`LOAD_LEVELS.suggested_workers`: 2,500→4 workers, 5,000→8 workers,
10,000→16 workers. For 5,000-10,000, workers must run on separate machines
from each other and from the target, not just separate processes on one
box.

```bash
# On the master:
locust -f loadtest/locustfile.py --host=https://loadtest-1.rastisi.localhost \
    --master --headless -u 10000 -r 40 --run-time 20m \
    --csv=results/10k --html=results/10k.html

# On each worker host/process (repeat for the suggested worker count):
locust -f loadtest/locustfile.py --worker --master-host=<master-ip>
```

**All** `LOADTEST_*` environment variables (§14-17) must be exported on
**every** worker process, not just the master — each worker independently
runs the safety guard's `init` check and independently refuses an unsafe
target.

## 27. Collecting CSV and HTML result artifacts

Always pass `--csv=<prefix>` and `--html=<prefix>.html` as shown above.
Locust writes `<prefix>_stats.csv` (RPS, failures, percentiles per endpoint
and aggregated) and a browsable HTML report. Do not report numbers from
memory or from the live console — always cite the CSV/HTML files. Keep every
level's artifacts under a level-specific prefix (`results/100users*`,
`results/500users*`, ...) so they are never overwritten by the next level.

## 28. Collecting system metrics

Run alongside each load level, on **both** the target host and the
generator host separately (never conflate them):

```bash
# Target host, during the run:
vmstat 5 > results/100users_target_vmstat.log &
mpstat -P ALL 5 > results/100users_target_mpstat.log &   # apt install sysstat if missing
free -s 5 > results/100users_target_free.log &
iostat -xz 5 > results/100users_target_iostat.log &      # apt install sysstat if missing

# Generator host, during the run:
vmstat 5 > results/100users_generator_vmstat.log &
mpstat -P ALL 5 > results/100users_generator_mpstat.log &
```

Stop the background collectors (`kill %1 %2 ...` or `pkill vmstat mpstat
free iostat`) once the run finishes, before starting the next level.

## 29. Collecting Gunicorn metrics

Gunicorn has no built-in metrics endpoint. At minimum, during each run:

```bash
# Worker process count/CPU/RSS at a point in steady state:
ps -o pid,ppid,%cpu,%mem,etime,cmd -C gunicorn

# Restarts/crashes: grep Gunicorn's own error log for "Worker exiting"/
# "Worker was sent SIGKILL"/traceback lines during the run window:
grep -E "Worker (exiting|was sent|failed to boot)|Traceback" <gunicorn-error-log>
```

If Gunicorn was started with `--access-logfile -`, count 5xx responses and
timeouts directly from it:

```bash
awk '{print $9}' <gunicorn-access-log> | sort | uniq -c | sort -rn   # status code histogram
```

If none of this is available for a given run, report `N/A` in the app-server
metrics row and say why (e.g. "access log not captured for this level")
rather than inventing a number.

## 30. Collecting PostgreSQL metrics

```bash
# Active/total connections, during and immediately after a run:
psql "$DATABASE_URL" -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"
psql "$DATABASE_URL" -c "SHOW max_connections;"

# Long-running / blocked queries:
psql "$DATABASE_URL" -c "
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND now() - query_start > interval '1 second'
ORDER BY duration DESC;"

# Lock contention:
psql "$DATABASE_URL" -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

If `pg_stat_statements` is already enabled in this staging database (check
with `SELECT * FROM pg_extension WHERE extname = 'pg_stat_statements';`),
use it to identify the highest-cost statements after each run:

```bash
psql "$DATABASE_URL" -c "
SELECT query, calls, total_exec_time, mean_exec_time, rows
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;"
```

If it is not already enabled, do **not** enable it as part of this
benchmark unless doing so is trivial in your staging environment (it
usually requires a Postgres restart with `shared_preload_libraries` set) —
otherwise document it as a limitation. Never enable it on production.

## 31. Collecting Redis metrics (only if Redis is actually in the staging runtime)

The default `CACHES["default"]` backend in `shop_core/settings.py` is
`LocMemCache`, not Redis — Redis is only in play if you deliberately set
`RASTISI_RATE_LIMIT_CACHE_URL=redis://...` for the `"rate_limit"` cache
alias used by the rate-limiting middleware. If you did:

```bash
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO stats   # ops/sec, evictions, errors
```

If you did not set `RASTISI_RATE_LIMIT_CACHE_URL`, Redis is not part of the
runtime under test — report Redis metrics as "N/A — not configured for this
run" rather than omitting the row silently.

## 32. Detecting load-generator saturation

The Phase 3 suite already surfaces this: Locust's own CPU monitor logs a
`WARNING` the moment the generator process itself crosses ~90% CPU, plus a
reminder at shutdown if it happened at any point. Watch for these lines in
the Locust console/log for every level:

```bash
grep -i "cpu usage above" <locust-log>
```

Also watch RPS alongside failure rate as `-u` scales up: if RPS plateaus or
drops while failures and CPU warnings climb, treat that level as
`GENERATOR_LIMITED`, not evidence of a target-side problem, until you've
ruled out generator saturation by adding distributed workers (§26).

## 33. Stopping the benchmark safely

`Ctrl-C` the Locust master (or let `--run-time` expire naturally, which is
preferred so the CSV/HTML artifacts and the built-in summary print cleanly).
Do not `kill -9` mid-run if avoidable — it can leave partial/corrupt CSV
output.

## 34. Preserving result artifacts

```bash
mkdir -p phase4-results/$(date +%Y%m%d)
cp results/*_stats.csv results/*.html \
   results/*_target_*.log results/*_generator_*.log \
   phase4-results/$(date +%Y%m%d)/
tar czf phase4-results-$(date +%Y%m%d).tar.gz phase4-results/$(date +%Y%m%d)/
```

Keep raw CSV/HTML/log artifacts alongside the written report so every number
in the RESULT_TABLE can be traced back to a file, per the audit charter's
"use raw Locust CSV/HTML artifacts... do not report values from memory"
requirement.

## 35. Cleaning up disposable test data/infrastructure

```bash
# Tear down the staging Django app / Gunicorn / Nginx as normal for your
# provisioning method (stop services, terminate the VM/container).
sudo -u postgres psql -c "DROP DATABASE rastisi_loadtest;"
sudo -u postgres psql -c "DROP USER rastisi_loadtest;"
```

`seed_loadtest_fixtures` never touches anything outside this disposable
database, so there is nothing else to clean up. Do not reuse the staging
database for anything beyond this benchmark without re-seeding fresh
fixtures.

## Required operator confirmations before running any load level

- [ ] `git rev-parse HEAD` on the staging checkout prints exactly
      `4521b82fdd455b168c19bae50e4ce4f6afe28c56`
- [ ] `DATABASE_URL` points at the disposable staging Postgres instance
      created in §7 — not production
- [ ] `LOADTEST_ALLOWED_HOSTS`/`TENANT_HOSTS`/`ADMIN_HOSTS` contain only
      staging hostnames, none of them `rastisi.ir` or a subdomain
- [ ] §18's two safety-guard validation commands both behaved as documented
- [ ] `LOADTEST_ENABLE_CHECKOUT_WRITES` and `LOADTEST_ENABLE_ADMIN_MUTATIONS`
      are unset/false for the baseline table
- [ ] Real SMS backend credentials are not exported anywhere on the staging
      host; `PAYMENTS_SIMULATION_ENABLED=True`
- [ ] The load generator runs on a host separate from the target for every
      level at and above 1,000 users, and on physically separate machines
      for 5,000 and 10,000
