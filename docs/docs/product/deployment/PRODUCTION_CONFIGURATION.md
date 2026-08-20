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
| `DJANGO_PRIVATE_MEDIA_ROOT` | Recommended | `<repo>/private_media` | Export/import files — never web-served directly; see §5a |
| `DJANGO_LOG_LEVEL` | Optional | `INFO` | One of DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `RASTISI_ADMIN_DOMAIN_SUFFIX` | Recommended once real merchant admin subdomains are live | `rastisi.ir` | Suffix appended to `Store.admin_subdomain` to form the merchant admin host — see ADR-16 in `SAAS_DOMAIN_DECISIONS.md` |
| `RASTISI_DEFAULT_PLAN_CODE` | Optional (checkpoint 5A) | *(empty)* | `Plan.code` new stores are auto-subscribed to; empty = no auto-assignment (fail-open entitlements). Existing stores are unaffected — see §5a and ADR-65/72 |
| `RASTISI_DEFAULT_PLAN_START_TRIAL` | Optional (checkpoint 5A) | `true` | Whether a new store's default subscription starts in a trial (if the plan version defines `trial_days`) or goes straight to active |
| `RASTISI_BILLING_PROVIDER` | Optional (checkpoint 5B) | `manual` | Active SaaS payment provider. `manual` is an honest test/manual provider — wire a real gateway behind the same interface (ADR-75) |
| `RASTISI_BILLING_WEBHOOK_SECRET` | Required once a provider sends webhooks | *(empty)* | Secret used to verify webhook signatures (ADR-76). Never stored in the DB or code |
| `RASTISI_BILLING_MAX_WEBHOOK_BYTES` | Optional | `65536` | Max webhook body accepted before a 413 |
| `RASTISI_BILLING_WEBHOOK_TOLERANCE_SECONDS` | Optional | `300` | Signature timestamp tolerance |
| `RASTISI_BILLING_RENEWAL_LEAD_DAYS` | Optional | `3` | Days before period end that renewal invoices are generated (ADR-78) |
| `RASTISI_BILLING_DUNNING_SCHEDULE` | Optional | `0,3,7,14` | Days-after-due dunning retry schedule (ADR-79) |
| `RASTISI_BILLING_TAX_RATE` | Optional | `0` | Flat SaaS-billing tax rate; `0` = off. Not a legal VAT guarantee (ADR-82) |
| `RASTISI_TRUST_PROXY_CLIENT_IP` | Only behind a proxy that overwrites `X-Real-IP` for every request | `False` | See §6a — never enable without confirming the proxy config |
| `RASTISI_RATE_LIMIT_CACHE_URL` | Recommended once running more than one worker process | unset (process-local LocMemCache) | `redis://host:port/db` or `rediss://...`; see §6a |

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

### 3a. Industry Template catalog sync

`IndustryTemplate` rows (the merchant-onboarding "choose your industry"
catalog — categories, attributes, recommended options) are living,
version-controlled platform *content*
(`apps.catalog.industry_templates.registry`), not a one-time historical
fact — they are deliberately **not** created by a schema migration. A
migration is a frozen snapshot of a point in schema history; baking today's
registry into one would mean a fresh database, migrated years from now,
runs *today's* seed logic against whatever `IndustryTemplate`-family schema
existed back at that migration — silently breaking fresh installs the
moment a later migration changes one of those model fields.

Run this immediately after `migrate`, on every deploy:

```
python manage.py seed_industry_templates
python manage.py validate_industry_templates
```

Both are idempotent (`update_or_create` on stable natural keys) and safe to
run on every deploy, including ones that change nothing — re-running
`seed_industry_templates` creates no duplicate `IndustryTemplate`/category/
attribute rows. `validate_industry_templates` is read-only by default and
exits non-zero (failing the deploy, if your pipeline checks exit codes) the
moment any template fails validation — never skip or silence this step to
get a deploy through; fix the registry entry instead.

Skipping this step is exactly the production bug this section exists to
prevent: a fresh database that never runs `seed_industry_templates` silently
ends up with zero Industry Templates, and onboarding's industry-selection
step falls back to its (otherwise correct) empty state for every merchant.

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

## 5a. Private storage for export/import files, and its cleanup schedule

`DJANGO_PRIVATE_MEDIA_ROOT` must also point at persistent storage,
separate from `DJANGO_MEDIA_ROOT` — it holds generated Product/Variant/
Inventory/Customer/Order CSV exports (`ExportJob.file`), some of which
contain Customer PII or Order financial detail. Unlike `DJANGO_MEDIA_ROOT`,
nothing under this directory is ever served by a public URL — see ADR-52 in
`SAAS_DOMAIN_DECISIONS.md`; the only read path is the authenticated,
Store-scoped `dashboard:export-download` view.

This platform has no background task queue (ADR-49), so expired export
files are **not** reclaimed automatically — you must schedule
`python manage.py cleanup_expired_exports` yourself (cron or a systemd
timer), e.g. daily:

```
0 3 * * * cd /path/to/app && python manage.py cleanup_expired_exports
```

Without this, expired `ExportJob` rows still stop being downloadable
(the download view checks `status`/`expires_at`), but their files remain on
disk until the command actually runs.

Similarly, `python manage.py refresh_customer_segments` (ADR-53) must be
scheduled if you want dynamic Customer Segments' *materialized* membership
to stay current for future bulk actions — the segment detail page's live
preview does not depend on this schedule (it always re-evaluates), but the
materialized `CustomerSegmentMembership` rows only update when this command
(or the per-segment "Refresh Membership" button) runs:

```
0 4 * * * cd /path/to/app && python manage.py refresh_customer_segments
```

And `python manage.py cleanup_import_files` (ADR-62) deletes the private
source and error-report files of `ImportJob`s older than a 30-day retention
window (the `ImportJob` record and its per-row results are preserved). Like
the two commands above it needs external scheduling; the files it removes
are regeneratable/re-uploadable, never the sole copy of any data:

```
0 5 * * * cd /path/to/app && python manage.py cleanup_import_files
```

### Subscription state evaluation and consistency (checkpoint 5A)

The subscription domain (plans, entitlements, usage, trials, state machine)
has two cron-scheduled commands, again because this codebase has no background
task queue (ADR-49). `python manage.py evaluate_subscription_states` applies
due time-driven transitions — trial end → grace/expired, grace end →
suspended, elapsed billing period → grace, and a scheduled cancel firing at
period end (ADR-66/67). Run it at least daily; `--dry-run` reports what would
change without applying it:

```
0 6 * * * cd /path/to/app && python manage.py evaluate_subscription_states
```

`python manage.py verify_subscription_consistency --strict` is a **read-only**
health check (≤1 current subscription per store, no terminal-but-current row,
current version published, entitlement definitions present); with `--strict`
it exits non-zero on any problem, so it fits a CI/monitoring gate. It never
writes:

```
30 6 * * * cd /path/to/app && python manage.py verify_subscription_consistency --strict
```

`python manage.py provision_legacy_subscriptions` is idempotent and only
needed as a repair/backfill — the initial legacy grandfathering runs as a data
migration (ADR-65). Existing stores always get the unlimited Legacy plan;
they are never assigned a limited plan.

**Default plan for new stores.** `RASTISI_DEFAULT_PLAN_CODE` (empty by default
= no auto-assignment) names the `Plan.code` whose latest published version a
genuinely new store is placed on via `provision_default_subscription`;
`RASTISI_DEFAULT_PLAN_START_TRIAL` (default `true`) controls whether that
subscription starts in a trial. Leaving the code empty keeps new stores on
fail-open entitlements until a plan is chosen — turning it on is an explicit
deployment decision.

### SaaS billing: providers, webhooks, renewals, and dunning (checkpoint 5B)

SaaS subscription billing (`apps.billing`) is a domain separate from merchant
storefront order payments (ADR-73). It runs the honest `manual` provider by
default — no production payment is faked. Wire a real gateway behind
`apps.billing.providers` and set `RASTISI_BILLING_PROVIDER` +
`RASTISI_BILLING_WEBHOOK_SECRET`.

The provider **webhook endpoint** is `POST /billing/webhook/<provider>/` — the
only CSRF-exempt billing route; it authenticates by signature, not session
(ADR-76). Point the provider's webhook at that URL and share the secret.

Three billing commands need external scheduling (no task queue, ADR-49):

```
0 7 * * * cd /path/to/app && python manage.py generate_subscription_renewals
30 7 * * * cd /path/to/app && python manage.py process_subscription_dunning
45 7 * * * cd /path/to/app && python manage.py verify_billing_consistency --strict
```

`generate_subscription_renewals` creates one open renewal invoice per period,
`RASTISI_BILLING_RENEWAL_LEAD_DAYS` before period end (ADR-78).
`process_subscription_dunning` walks `RASTISI_BILLING_DUNNING_SCHEDULE`
(days-after-due), moving unpaid invoices past-due → grace → suspended (ADR-79).
`verify_billing_consistency --strict` is a **read-only** health check (paid
invoice without a successful attempt, overpaid invoice, duplicate renewal,
currency mismatch, refund over the paid amount, open invoice for a terminal
subscription, and so on) that exits non-zero on any problem.

**Tax and legal note (ADR-82):** SaaS billing tax defaults to zero
(`RASTISI_BILLING_TAX_RATE`); when enabled it is a single flat platform-wide
rate, not a jurisdiction-aware VAT engine. The platform makes no automatic
legal tax-compliance guarantee.

### CSV Import — columns, modes, and safety (checkpoint 4B)

Merchants import Products, Variants, and Inventory from CSV via the
**واردات داده‌ها** (Import) admin page. Every import is a two-step flow:
upload → automatic dry-run **preview** (nothing changes) → explicit
**execute** confirmation. The three modes are always chosen explicitly:
`create_only` (reject rows matching an existing record), `update_only`
(reject rows with no match), `upsert` (update matches, create the rest).

Records are matched by **stable, Store-scoped identity**: a platform
`product_id` first, then `sku` within the Store — never by name or slug.
Brand/Category/TaxClass/Warehouse are referenced by their **Store-scoped
code** (`brand_code`, `category_code`, `tax_class_code`, `warehouse_code`),
not display name; a missing or another-Store reference is a per-row error.
Downloadable CSV templates for each type are linked from the upload page.

Limits (documented, fixed — see `apps.core.services.csv_utils`): max upload
**10 MB**, max **20,000 rows**, max field length **2,000 chars**. Files are
UTF-8 (BOM-tolerant); Persian/Arabic digits are normalized automatically.
Inventory imports can never oversell — a reduction that would drop available
stock below active reservations is refused. Import source and error-report
files live under `DJANGO_PRIVATE_MEDIA_ROOT` and are only downloadable
through the authenticated, Store-scoped admin view (never a public URL).

### Storefront SEO endpoints (checkpoint 6)

The customer storefront serves a tenant-scoped `GET /sitemap.xml` and
`GET /robots.txt` (ADR-90): both resolve the Store from the request Host, so
each store's domain gets its own sitemap listing only that store's home,
product list, active categories, and published (never draft) products, plus
published CMS pages. `robots.txt` disallows `/cart/`, `/checkout/`, `/account/`,
and the admin paths and links the same-host sitemap. Canonical URLs, Open
Graph, and JSON-LD (Product/BreadcrumbList/Organization) are emitted per page
and reflect real price/availability. No cross-store URL or draft product is ever
exposed to crawlers. Because `django.contrib.sites` is not installed, these are
request-scoped views rather than the Sites-coupled sitemap framework — no
`SITE_ID` configuration is needed. See `STOREFRONT_AUDIT_REPORT.md`,
`STOREFRONT_SCREEN_INVENTORY.md`, and `STOREFRONT_MANUAL_QA_CHECKLIST.md` for
the full storefront coverage map and manual QA scenarios.

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

## 6a. Trusted client IP and shared rate-limit backend (Phase 1C)

Two related, but independent, settings — both default to the safe
(non-trusting, non-shared) behavior, and both must be deliberately opted
into:

- `RASTISI_TRUST_PROXY_CLIENT_IP` — whether `apps.core.services.rate_limit.
  client_ip_or_unknown()` trusts the reverse proxy's `X-Real-IP` header
  instead of `REMOTE_ADDR`. Only ever set `True` when the reverse proxy is
  confirmed to unconditionally **overwrite** `X-Real-IP` for every request
  (never merge/forward a client-supplied value) — otherwise a client can
  forge the header and spoof their rate-limit identity. `X-Forwarded-For`
  is never read, even when this is enabled (see the function's docstring).
- `RASTISI_RATE_LIMIT_CACHE_URL` — a `redis://`/`rediss://` URL for the
  dedicated `rate_limit` cache alias. Unset means rate-limit counters are
  process-local (`LocMemCache`) — fine for a single worker process, but
  each additional Gunicorn/uWSGI worker then keeps its own counters, so a
  brute-force/OTP-spam limit's effective threshold multiplies by the
  worker count. `python manage.py check --deploy` warns
  (`rastisi.core.W001`) about this under `DJANGO_DEBUG=False`, without
  blocking startup.

See `docs/reports/PHASE_1C_RATE_LIMIT_RUNBOOK.md` for the step-by-step
operator procedure (Redis install/config, env vars, restart, verification,
rollback) to actually turn these on for RastiSi's real production topology
— that runbook is deliberately **not executed** by this PR; it is prepared
for a later, separate, controlled change.

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
- the `DJANGO_PRIVATE_MEDIA_ROOT` directory is deliberately **not** a backup
  candidate — every file in it today is a regeneratable CSV export (re-run
  the export from the admin panel), never the sole copy of any data. (A
  future CSV Import feature, not implemented as of this checkpoint — see
  ADR-54 — would also stage uploads here; that upload would likewise be a
  copy of data the merchant already has locally, not something this
  platform would need to be the only holder of.)

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
python manage.py seed_industry_templates
python manage.py validate_industry_templates
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
