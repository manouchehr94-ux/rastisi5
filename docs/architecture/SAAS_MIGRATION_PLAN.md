# SaaS Migration Plan

This is a staged PR sequence. Each PR must land, be reviewed, and be verified
green before the next begins. No PR in this list implements more than its
own stated scope.

```text
PR 1  — Documentation and baseline locks                         [this PR, combined with PR 2]
PR 2  — Store, StoreDomain and StoreMembership foundation         [this PR]
PR 3  — Store resolution infrastructure in compatibility mode
PR 4  — Core settings and footer settings ownership
PR 5  — Catalog ownership and constraints
PR 6  — Cart and coupon ownership
PR 7  — Order, shipping and payment-domain separation
PR 8  — Content, navigation, homepage, blog and media ownership
PR 9  — SMS and integration configuration ownership
PR 10 — Customer identity and Store customer profile
PR 11 — Merchant dashboard authorization and role enforcement
PR 12 — Non-null enforcement and legacy-path removal
PR 13 — PostgreSQL production migration and operational hardening
PR 14 — Full adversarial isolation suite
```

Note on ordering: this repository had no separate "PR 1" work item pending
(no uncommitted assessment artifacts, no drifted migrations at baseline), so
PR 1's documentation scope and PR 2's model scope are delivered together as
one PR, as instructed by the governing task program. Later PR numbers are
unchanged.

## Cross-cutting distinctions used throughout this plan

* **Schema migration** — adding a nullable `store` FK (and any new tables)
  via `makemigrations`. Reversible, non-destructive, safe to deploy without
  application changes.
* **Data migration** — backfilling the new FK for existing rows (e.g.
  assigning all current rows to the Akhlaghi Store). Must be idempotent and
  auditable (row counts before/after).
* **Compatibility period** — a window where both the legacy unscoped
  behavior and the new Store-scoped field coexist; application code has not
  yet been converted to require the new field.
- **Query conversion** — updating views/services/templates/context
  processors to filter by the resolved Store instead of operating globally.
- **Non-null enforcement** — once all rows are backfilled and all code
  paths converted, altering the FK to `null=False` in its own migration.
- **Rollback strategy** — every schema/data migration in this plan must have
  a tested reverse path, or (for `RunPython` data migrations) an explicit,
  documented statement that reversal is a no-op and why that is safe.
- **Verification gates** — `python manage.py check`, `makemigrations
  --check --dry-run`, full test suite, and (starting when real data exists)
  row-count and referential-integrity spot checks, must pass before a PR in
  this sequence is considered mergeable.

## PR 2 — Store, StoreDomain and StoreMembership foundation (this PR)

Scope: new `apps/stores` app only. `Store`, `StoreDomain`,
`StoreMembership` models, their constraints, hostname normalization,
admin registrations, migrations (schema + the Akhlaghi data migration),
and tests. No existing app is modified. See the PR's own report for exact
file list.

## PR 3 — Store Resolution Infrastructure in Compatibility Mode [done]

Status note: merged into the canonical base branch.

Scope, and *only* scope: `apps.stores.resolution` resolves "which Store
does this request belong to" from `StoreDomain.hostname` (authoritative
path) with a narrow, explicitly isolated, fail-closed compatibility
fallback for a fixed local-development host allowlist while Akhlaghi is
the platform's sole Store. `StoreResolutionMiddleware` attaches the result
to `request.store` once per request, positioned before
`SessionMiddleware`/`AuthenticationMiddleware` in `MIDDLEWARE`. No `Store`
FK was added to any existing model; no existing view, template, or
business query changed. See `SAAS_ARCHITECTURE.md` §6 and
`SAAS_DOMAIN_DECISIONS.md` ADR-11 for the full design. Verification gates
(all green): full existing suite, plus new resolver/middleware tests
including adversarial cross-Store and caller-controlled-input isolation
tests.

## PR 4 — Tenant-scope existing core settings, without splitting them [this PR]

Status note: implemented on branch `claude/store-scope-core-settings` and
open as a pull request against the branch PR 3 merged into — not yet merged
into the canonical base branch as of this writing. "This PR" here means
exactly that, not "already merged." Update this to "[done]" only once the
PR opening this section has actually merged.

Scope: add a `store` FK to `apps.core.ShopSettings` (`OneToOneField`) and
`apps.content.FooterSettings` (`OneToOneField`) /`FooterTrustBadge`/
`FooterPaymentLogo` (plain `ForeignKey`, direct ownership — not mediated
through `FooterSettings`, since both are independently queried/managed
today) **as they exist today — no field reorganization, no model split**
(see `SAAS_DOMAIN_DECISIONS.md` ADR-10 and ADR-12: splitting `ShopSettings`
by domain is a deliberately separate, later decision, not bundled into
tenant-scoping it). Each app's migration is staged in three steps: nullable
schema `AddField`, a `RunPython` backfill resolving Akhlaghi via
`Store.objects.get(slug="akhlaghi")` (never `.first()`, fails loudly on
zero or multiple matches), then `AlterField` to enforce non-null — done in
this PR, not deferred to PR 12, since the backfill guarantees zero unowned
rows before enforcement runs. `ShopSettings.load(store=...)`/
`FooterSettings.load(store=...)` accept an explicit Store (authoritative,
never returns another Store's row, raises a dedicated
`*NotProvisionedError` instead of auto-creating one) or fall back to the
same `resolve_compatibility_store()` fail-closed check PR 3's compatibility
mode already defines when no Store is given — never a bare
`get_or_create(pk=1)`, which is removed from both models' runtime code
entirely. A new, explicit `provision_for(store)` classmethod on each model
is the one sanctioned way to create a new Store's settings rows
(idempotent, never overwrites existing values, never invoked implicitly on
read). Query conversion for the context processors
(`apps.core.context_processors`, `apps.content.context_processors`) and the
dashboard settings/footer views to resolve via `request.store` instead of
the global singleton, including Store-scoped `get_object_or_404` lookups
for the trust-badge/payment-logo CRUD endpoints. Rollback: each schema
migration's `AlterField`/`AddField` reverses via Django's own framework
defaults; each backfill migration's reverse only clears the `store`
reference (`update(store=None)`) — never deletes a settings/badge/logo row.
Verification gates (all green): full existing suite (apps.stores,
apps.core, apps.content, apps.dashboard.tests.test_settings_views, and the
full project suite), plus new per-Store isolation tests including real
two-Host integration coverage (verified `StoreDomain` rows, real Django
test `Client` requests, no `request.store` mocking) and adversarial
dashboard write-isolation tests. A **separate, later PR** — not this one —
is where `ShopSettings` is actually split into domain-specific models
(identity/commerce-defaults, branding/theme, and extracting SMS
credentials), per ADR-10.

## PR 5 — Catalog ownership and constraints

Scope: resolve the Vendor/Store domain question from
`SAAS_DOMAIN_DECISIONS.md` ADR-1 (dedicated catalog-domain review, may be
its own preceding PR if the decision is non-trivial). Add nullable `store`
FK to `Category`, `Brand`, `Product` (and re-evaluate whether `Vendor`
itself becomes Store-scoped based on that review). Re-derive global
uniqueness constraints (`slug`, `sku`) as Store-scoped uniqueness where
appropriate — this is a behavior change requiring its own migration and
explicit sign-off, since today's `Product.slug`/`sku` and `Category.slug`/
`Brand.slug` are platform-global unique. Data migration backfills existing
rows to Akhlaghi. Query conversion for catalog views, nav context
processor, product listing/detail. Verification: existing catalog test
suite green plus new Store-scoping tests plus adversarial
cross-Store-access tests.

## PR 6 — Cart and coupon ownership

Scope: `apps.cart` models (cart, cart items, `Coupon`) gain Store scoping.
Coupon code uniqueness re-derived as Store-scoped if currently global.
Query conversion for cart views/services. Adversarial tests: a coupon code
valid in Store A must not validate against Store B's cart.

## PR 7 — Order, shipping and payment-domain separation

Scope: `Order`, `ShippingMethod` gain Store scoping. This PR also executes
the `PaymentProvider` / `StorePaymentConfiguration` / `PaymentTransaction`
split recorded in ADR-7/ADR-9 — the `PaymentGateway` audit happens at the
start of this PR, before any schema change, to decide which existing fields
map to which new model. This is the highest-risk PR in the sequence because
it touches financial data; row-count and financial-total checks
(sum of order totals before/after backfill) are mandatory gates, not
optional.

## PR 8 — Content, navigation, homepage, blog and media ownership

Scope: `apps.content` (pages, navigation menus, homepage sections) and
`apps.blog` gain Store scoping. Media path/storage isolation principle
(from `SAAS_ARCHITECTURE.md` §7) is implemented here for content/blog
media specifically — not a platform-wide media migration.

## PR 9 — SMS and integration configuration ownership

Scope: `apps.sms` (`SmsTemplate`, `SmsLog`) gain Store scoping, with the
`OtpCode` question from ADR-6 resolved explicitly (platform-global vs.
Store-dimensioned) before schema changes. Plaintext SMS credentials
(`ShopSettings.melipayamak_username/password`, moved to
`StorePaymentConfiguration`-equivalent for SMS in PR 4/9) are flagged for
the encryption-at-rest work — selecting and installing an encryption
library requires its own ADR and is not bundled into this PR.

## PR 10 — Customer identity and Store customer profile

Scope: executes ADR-6. Splits `Customer` into a global authentication
identity concern and a Store-scoped commerce profile
(`Address`, `Wishlist`, order history, VIP/spend). This is a
user-data-shape change and needs its own explicit data-migration and
rollback design, plus privacy review (a Store must not see another Store's
view of the same underlying person).

## PR 11 — Merchant dashboard authorization and role enforcement

Scope: `apps.dashboard` is converted to enforce `StoreMembership`
role-based access (the roles already exist as of PR 2; this PR is where they
start being checked). Platform-operator vs. merchant-admin boundary from
ADR-8 becomes enforced code, not just a documented intention.

## PR 12 — Non-null enforcement and legacy-path removal

Scope: once every model that should be Store-scoped has been backfilled and
every code path converted (PRs 4–11 complete), flip the nullable `store`
FKs to `null=False` and remove any compatibility fallbacks introduced in
PR 3. This is the PR where "Store scoping is fully mandatory" becomes true.

## PR 13 — PostgreSQL production migration and operational hardening

Scope: move the production database from SQLite to PostgreSQL. This is
**not** a `dumpdata`/`loaddata` one-liner. Required steps:

1. Source backup (full SQLite file snapshot, timestamped, stored outside
   the deploy path).
2. Controlled export (`dumpdata` per app, not a single global dump, to keep
   failure blast radius small and allow partial re-import).
3. Data normalization pass (SQLite is more permissive about type coercion
   than PostgreSQL — e.g. empty-string vs. NULL handling, datetime
   timezone-awareness — must be checked field by field for models touched
   in PRs 4–12).
4. Import ordering that respects FK dependency order (platform-global
   tables, then `Store`, then Store-owned tables in dependency order).
5. Sequence reset (`sqlsequencereset` per app) after import, since
   `loaddata` preserves explicit PKs but does not advance PostgreSQL
   sequences.
6. Row-count checks: per-table row count in source vs. destination must
   match exactly.
7. Financial-total checks: sum of order totals, payments, and refunds in
   source vs. destination must match to the last unit — not a spot check.
8. Media verification: every `ImageField`/`FileField` referenced by an
   imported row must resolve to an existing file in the migrated media
   storage.
9. Smoke tests: authenticated login, one full order flow, one dashboard
   session, against the PostgreSQL-backed instance before cutover.
10. Rollback snapshot: the SQLite source file and export dumps are retained,
    untouched, until the PostgreSQL instance has run in production for an
    agreed bake-in period.

## PR 14 — Full adversarial isolation suite

Scope: a dedicated cross-cutting test suite that, for every Store-scoped
model introduced in PRs 4–12, asserts that a user authenticated to Store A
cannot read, write, list, or otherwise reach Store B's data through any
view, service, or admin path. This is where PostgreSQL RLS is evaluated as
an additional defense-in-depth layer (still not required to be implemented
here — evaluation, not implementation, unless the review at that time
decides otherwise).
