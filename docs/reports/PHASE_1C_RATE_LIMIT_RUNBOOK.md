# Phase 1C Production Runbook — Trusted Client IP + Shared Rate-Limit Backend

**Status: NOT EXECUTED.** This is a precise, step-by-step procedure prepared
for a later, separate, deliberate production change. Phase 1C itself makes
no production infrastructure changes — it only makes the application code
*ready* for this runbook to be carried out under operator control.

## 0. Scope and exclusions

This runbook touches **only**:

- the RastiSi Gunicorn/Django deployment (`rastisi.service`, socket
  `/run/rastisi/gunicorn.sock`, env file `/etc/rastisi.env`);
- a new, dedicated Redis instance for RastiSi rate-limit counters;
- the RastiSi Nginx vhosts (central host + wildcard merchant hosts) already
  proxying to that Gunicorn socket.

This runbook **must not** touch, and no step below references:

- `rasti.service`
- `/root/service_app`
- RastiChat / `chatchat.rastisi.ir`
- any Nginx site other than the RastiSi central host and wildcard merchant
  hosts already listed in the verified production evidence

If any step below would require touching one of the excluded items, stop
and re-scope — it does not belong in this runbook.

## 1. Install and use Redis

```
sudo apt-get update
sudo apt-get install redis-server
```

Confirm the installed version supports the features this runbook relies on
(`SETNX`/`INCR` atomicity and per-key TTL — both present in every Redis
version this application would reasonably encounter; no exotic feature is
required).

Do **not** point RastiSi at a Redis instance shared with any other
application (including RastiChat) — provision this instance, or at minimum
a dedicated logical DB index on a shared instance (`redis://127.0.0.1:6379/<N>`
with `<N>` not used by anything else), exclusively for RastiSi rate-limit
counters. The application already assumes it owns the keyspace under the
`ratelimit:` prefix; do not add a second consumer of the same
instance/DB without re-auditing key-namespace collisions first.

## 2. Bind Redis only to localhost or a Unix socket

RastiSi's own Gunicorn already listens only on a Unix socket
(`/run/rastisi/gunicorn.sock`), never a TCP port directly reachable from the
internet. Redis must follow the same principle — it is a trusted-network,
same-host dependency, never internet-exposed:

In `/etc/redis/redis.conf`:

```
bind 127.0.0.1 -::1
port 6379
# or, for a Unix socket instead of TCP:
# unixsocket /run/redis/redis-rastisi.sock
# unixsocketperm 770
```

If using TCP on localhost, also set a password (`requirepass`) even though
it never leaves the host — defense in depth against any other local process
or misconfigured container network path:

```
requirepass <a-real-generated-secret>
```

Confirm after restart (§5) that Redis is **not** listening on any
non-loopback interface:

```
sudo ss -tlnp | grep redis
# expected: 127.0.0.1:6379 (and/or [::1]:6379) only — no 0.0.0.0/public IP
```

## 3. Persistence decision

Rate-limit counters are short-lived (window durations of 5–10 minutes in
this codebase's current call sites) and disposable — losing them on a
Redis restart only means rate-limit windows reset early, not a security
hole (the account/identifier-scoped layer, not the IP layer, is the real
brute-force defense; see `apps.core.services.rate_limit`'s docstrings).

**Decision: disable RDB snapshotting and AOF for this Redis instance.**
There is no data here worth persisting across a restart, and disabling both
avoids unnecessary disk I/O and fork-based snapshot pauses on a small VPS:

```
save ""
appendonly no
```

If this Redis instance is ever repurposed to hold anything other than
rate-limit counters, revisit this decision — it is only correct because
every key in this instance is disposable.

## 4. Memory limit / eviction policy

Every key this application writes carries an explicit TTL
(`window_seconds`, currently 300–600s depending on the call site — see
`apps.core.services.rate_limit.enforce_rate_limit`'s callers). Memory usage
is bounded by (distinct IPs/identifiers seen per window) × (small per-key
overhead), which is small for RastiSi's current traffic — no evidence
exists yet to size a specific number beyond a conservative, cheap default:

```
maxmemory 64mb
maxmemory-policy volatile-ttl
```

`volatile-ttl` (evict the key closest to expiring first, among keys that
have a TTL) is correct here specifically because every key this application
writes has a TTL — there are no persistent keys in this instance that could
be evicted unexpectedly. Revisit the `maxmemory` figure only with real
`INFO memory` observations after running in production for a while; do not
guess a larger number without that evidence.

## 5. Service health check

Add a simple systemd dependency/check, without altering any other service:

```
sudo systemctl enable redis-server
sudo systemctl status redis-server
redis-cli ping   # expected: PONG
# if a password was set:
redis-cli -a '<the-secret>' ping
```

Confirm the socket/port matches whatever `RASTISI_RATE_LIMIT_CACHE_URL`
will point at (§6).

## 6. Environment variables added to `/etc/rastisi.env`

Add (do not remove or reorder existing lines):

```
RASTISI_RATE_LIMIT_CACHE_URL=redis://127.0.0.1:6379/1
```

(Adjust host/port/DB index/password to match §1–§2's actual
configuration. Use `rediss://` instead of `redis://` only if TLS was
configured, which is not expected for a localhost-only instance.)

## 7. Proxy trust environment setting

Add, only after independently re-confirming the exact fact already verified
by the operator — that `/etc/nginx/proxy_params` sets
`proxy_set_header X-Real-IP $remote_addr;` on **every** location block that
proxies to `rastisi/gunicorn.sock`, for both the central host and every
wildcard merchant host:

```
RASTISI_TRUST_PROXY_CLIENT_IP=True
```

Do **not** set this before that re-confirmation — see
`apps.core.checks.trust_proxy_debug_check` and the extensive commentary in
`apps.core.services.rate_limit.client_ip_or_unknown` for why trusting a
proxy that does not unconditionally overwrite this header lets a client
spoof their own rate-limit identity.

## 8. Django check

Before restarting the service, run from the deployment directory with the
new `/etc/rastisi.env` sourced into the environment:

```
python manage.py check --deploy
```

Expected change from before this runbook: `rastisi.core.W001` (process-local
rate-limit cache under `DEBUG=False`) must no longer appear — see §9's
before/after table. Any other pre-existing warnings (HSTS staging, etc.)
are unrelated to this runbook and are handled by their own rollout (see
`docs/deployment/PRODUCTION_CONFIGURATION.md` §7).

## 9. Focused tests

Run, from the deployment checkout (or a staging checkout with the same
`/etc/rastisi.env`), before restarting the live service:

```
python manage.py test apps.core.tests.test_rate_limit apps.core.tests.test_checks
python manage.py test shop_core.tests.test_env_config shop_core.tests.test_production_settings
python manage.py test apps.customers.tests.test_auth_views apps.customers.tests.test_auth_service
python manage.py test apps.dashboard.tests.test_admin_login
python manage.py test apps.portal.tests.test_owner_otp apps.portal.tests.test_owner_auth apps.portal.tests.test_central_admin_login
python manage.py test apps.sms.tests.test_otp_service
```

These do not require the real Redis instance (they run under the
LocMemCache test fallback) — they confirm the *code* is correct before the
runbook changes the *environment*. After the environment change (§6–§7)
and before restarting, manually exercise one real request against staging
that would call `client_ip_or_unknown()` (e.g. a login attempt) and confirm
via logs/`redis-cli monitor` that a `ratelimit:` key actually appears in
Redis with the request's real client IP as part of the key — do not trust
`check --deploy` alone.

### `check --deploy` before / after

| Check | Before this runbook (current production: no Redis, `RASTISI_RATE_LIMIT_CACHE_URL` unset) | After this runbook (Redis configured, `RASTISI_RATE_LIMIT_CACHE_URL` set) |
|---|---|---|
| `rastisi.core.W001` | **Present** (Warning — rate-limit cache is process-local under `DEBUG=False`) | Absent |
| `rastisi.core.W002` | Absent (only fires when `DEBUG=True`) | Absent (only fires when `DEBUG=True`) |
| Exit code | `0` (Warning never blocks) | `0` |

## 10. Restart `rastisi.service` ONLY

```
sudo systemctl restart rastisi.service
```

Do not restart, reload, or otherwise touch `rasti.service`, anything under
`/root/service_app`, or any RastiChat process as part of this step — they
are unrelated to this change (see §0).

## 11. Post-restart verification

1. `sudo systemctl status rastisi.service` — active, no crash loop.
2. `curl --unix-socket /run/rastisi/gunicorn.sock http://localhost/` (or
   equivalent through Nginx on a real hostname) — a normal 200/redirect,
   not a 500.
3. `python manage.py check --deploy` again (via the same env) — confirm
   `rastisi.core.W001` is now absent and no new warning appeared.
4. Trigger one real rate-limited action (e.g. a deliberate wrong-password
   login attempt) from a real client and confirm in `redis-cli` that a
   `ratelimit:customer_login:<ip>` (or the relevant action name) key exists
   with a sane TTL (`TTL <key>` — should be ≤ that action's configured
   `window_seconds` and > 0).
5. Watch `journalctl -u rastisi.service -f` for a few minutes under real
   traffic for any unexpected cache-connection errors.

## 12. Rollback

Both changes in this runbook are env-var-only and independently reversible
without a code deploy:

1. Remove (or comment out) `RASTISI_RATE_LIMIT_CACHE_URL` from
   `/etc/rastisi.env` to fall back to the process-local LocMemCache — the
   application does not fail closed if Redis becomes unreachable, it was
   never made to depend on Redis being present at import time (§6's setting
   only takes effect if actually set); however, if Redis *has* been set and
   later becomes unreachable while still configured, cache operations will
   raise on that alias — remove the env var and restart rather than leaving
   the app pointed at a dead Redis.
2. Remove (or set to `False`) `RASTISI_TRUST_PROXY_CLIENT_IP` to
   immediately stop trusting `X-Real-IP` and fall back to `REMOTE_ADDR`.
3. `sudo systemctl restart rastisi.service` (only).
4. Optionally `sudo systemctl stop redis-server` if fully backing out —
   not required for the application to keep working, since removing
   `RASTISI_RATE_LIMIT_CACHE_URL` (step 1) already stops it from being used.

No database migration, no data backfill, and no schema change is involved
in this runbook in either direction.
