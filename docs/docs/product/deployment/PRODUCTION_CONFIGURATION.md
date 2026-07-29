# Production Configuration Foundation

**Status:** Foundation only. This document covers making `shop_core.settings`
safely configurable for a real deployment — it does **not** mean the
platform is launch-ready. Real payment processing (Zibal), Enamad
readiness, the merchant/dashboard Store-boundary hardening, checkout
idempotency, and the actual server/hosting setup are separate, later pieces
of work. See `docs/00_PROJECT_MASTER_REFERENCE.md` for the full launch
picture and what remains.

This is written provider-neutral: no specific host (VPS vs. managed
platform) has been chosen yet. Adjust the process-manager/reverse-proxy
specifics to whatever you end up using.

## 1. Required environment variables

All variables are read by `shop_core/settings.py` via the helpers in
`shop_core/env_config.py`. None are required to run the app locally or to
run the test suite — every one has a default that reproduces the prior
hardcoded development behavior. See `.env.example` for the full annotated
list with placeholder values. Summary:

| Variable | Required in production? | Default (dev) | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | dev-only literal key | Rejected if left as the dev key when `DJANGO_DEBUG=False` |
| `DJANGO_DEBUG` | Yes (`False`) | `True` | |
| `DJANGO_ALLOWED_HOSTS` | Yes | `[]` | Comma-separated, no wildcards |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes, once behind a real domain | `[]` | Comma-separated, full origin (`https://host`) |
| `DJANGO_SECURE_SSL_REDIRECT` | Recommended once HTTPS works | `False` | |
| `DJANGO_SESSION_COOKIE_SECURE` | Recommended once HTTPS works | `False` | |
| `DJANGO_CSRF_COOKIE_SECURE` | Recommended once HTTPS works | `False` | |
| `DJANGO_SECURE_HSTS_SECONDS` | Staged — see §7 | `0` | |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | Staged | `False` | |
| `DJANGO_SECURE_HSTS_PRELOAD` | Staged, last | `False` | |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | Only behind a proxy that strips it | unset | See §6 warning |
| `DATABASE_URL` | Recommended (PostgreSQL) | unset (SQLite) | `postgres://user:pass@host:port/dbname` |
| `DJANGO_STATIC_ROOT` | Recommended | `<repo>/staticfiles` | |
| `DJANGO_MEDIA_ROOT` | Recommended | `<repo>/media` | Must be persistent + backed up |
| `DJANGO_LOG_LEVEL` | Optional | `INFO` | One of DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `RASTISI_ADMIN_DOMAIN_SUFFIX` | Recommended once real merchant admin subdomains are live | `rastisi.ir` | Suffix appended to `Store.admin_subdomain` to form the merchant admin host — see ADR-16 in `SAAS_DOMAIN_DECISIONS.md` |

Malformed values (an unparseable boolean, integer, or an invalid
`DATABASE_URL`) raise `ImproperlyConfigured` immediately at process startup
rather than falling back silently — you will see this as a crash on
`manage.py check`/`migrate`/`runserver`/gunicorn boot, with a clear message.

## 2. PostgreSQL preparation

1. Provision a PostgreSQL database and a role with a real password.
2. Install the driver: `psycopg[binary]` is already listed in
   `requirements.txt` (only actually needed once `DATABASE_URL` is set).
3. Set `DATABASE_URL=postgres://<user>:<password>@<host>:<port>/<dbname>`.
4. Run migrations against it (see §3) — this repository's migration history
   is engine-agnostic; no SQLite-specific operations are used.

This PR does not migrate your existing local SQLite data to PostgreSQL, and
does not rewrite migration history. A fresh PostgreSQL database is expected
to run every existing migration from scratch.

## 3. Migration command

```
python manage.py migrate
```

Run this on every deploy after pulling new code, before restarting the
application process.

## 4. Static files

```
python manage.py collectstatic --noinput
```

Serve the resulting `DJANGO_STATIC_ROOT` directory via your reverse proxy
(or a CDN in front of it) — Django itself does not serve static files when
`DEBUG=False`.

## 5. Persistent media

`DJANGO_MEDIA_ROOT` must point at storage that survives deploys/restarts
and is included in your backup routine (see §10) — product images, uploaded
logos, and homepage/footer media all live there. This PR keeps media on
local disk (per the existing architecture); it does not add cloud object
storage. If your hosting provider's disk is ephemeral (e.g. some
container/PaaS platforms), you must mount persistent storage there before
launch — that is a hosting decision, not something this codebase enforces.

## 6. HTTPS / reverse-proxy assumptions

This application expects to sit either directly on the public internet with
its own TLS termination, or behind a reverse proxy that terminates TLS and
forwards plain HTTP internally. If you use the latter:

- Only set `DJANGO_SECURE_PROXY_SSL_HEADER` if your proxy is configured to
  **strip any client-supplied copy of that header** before setting its own
  — otherwise a client can forge the header and make Django believe an
  insecure request was secure. This setting is unset by default and must be
  deliberately opted into.
- `Store` resolution (`apps/stores/resolution.py`) uses Django's own
  `request.get_host()`, gated by `DJANGO_ALLOWED_HOSTS` — make sure your
  proxy passes through the real client-facing `Host` header unchanged.

## 7. Secure cookies and staged HSTS rollout

Do not enable `DJANGO_SECURE_SSL_REDIRECT` / `*_COOKIE_SECURE` / HSTS until
you've confirmed HTTPS actually works for every hostname in
`DJANGO_ALLOWED_HOSTS`. Suggested rollout:

1. Launch with HTTPS available but `DJANGO_SECURE_SSL_REDIRECT=False` and
   HSTS at `0`; confirm the site loads correctly over both `http://` and
   `https://`.
2. Set `DJANGO_SECURE_SSL_REDIRECT=True`, `DJANGO_SESSION_COOKIE_SECURE=True`,
   `DJANGO_CSRF_COOKIE_SECURE=True`. Confirm login/checkout still work.
3. Set `DJANGO_SECURE_HSTS_SECONDS=3600` (1 hour) for a day or two; watch for
   problems.
4. Raise to `86400` (1 day), then eventually `31536000` (1 year).
5. Only set `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True` /
   `DJANGO_SECURE_HSTS_PRELOAD=True` once you are certain every subdomain
   you control also serves HTTPS correctly — these are effectively
   irreversible from the browser's perspective for the HSTS duration.

## 8. Health verification

After deploying, verify at minimum:

```
python manage.py check --deploy
```

Review every warning it prints — some may be intentionally deferred (e.g.
until a real domain/reverse-proxy is chosen); document which ones and why
rather than silencing them. Then confirm the application actually serves a
real page over the real domain/HTTPS before considering the deploy healthy.

## 9. Backup requirement

Before going live, you need a documented, **tested** restore procedure for:

- the PostgreSQL database (e.g. `pg_dump`/`pg_restore` on a schedule);
- the `DJANGO_MEDIA_ROOT` directory (product images, uploaded content).

This PR does not implement or automate backups — that is deployment/hosting
work tracked separately (see `docs/00_PROJECT_MASTER_REFERENCE.md`). Do not
consider the platform launch-ready until a restore has actually been
exercised once against a throwaway copy, not merely scheduled.

## 10. Rollback preparation

Before a launch deploy, confirm you can:

- redeploy the previous known-good commit/build;
- reverse the most recent migration if it is safely reversible (check each
  migration's `reverse` behavior — several in this project intentionally
  only clear FK references rather than delete merchant data, precisely so
  rollback is safe);
- restore the database from the backup in §9 if a rollback requires it.

## 11. Commands to run before launch

```
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py migrate
python manage.py provision_default_warehouses
python manage.py verify_inventory_consistency --strict
python manage.py collectstatic --noinput
python manage.py test
```

All of the above should be clean (no drift, no unexpected `check --deploy`
warnings left unexplained, full test suite green) before pointing a real
domain at the deployment.

## What this PR does **not** do

- No real payment gateway (Zibal) — the checkout payment step is still
  simulated.
- No Order/dashboard Store-boundary hardening (a known, separate gap — see
  the launch audit).
- No checkout idempotency / inventory-locking fixes.
- No Enamad support.
- No hosting-provider selection or actual server provisioning.
- No secrets, merchant credentials, or real business information are
  included anywhere in this repository.
