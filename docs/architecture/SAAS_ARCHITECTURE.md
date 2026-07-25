# SaaS Foundation Architecture

Status: Foundation stage. PR 2 (`Store`/`StoreDomain`/`StoreMembership`) has
merged. PR 3 (Store resolution infrastructure, §6 below) is implemented on
branch `claude/store-resolution-infra` and open as a pull request — not yet
merged into the canonical base branch as of this writing. See
`SAAS_MIGRATION_PLAN.md` for the full staged sequence and current status of
each PR.

## 1. Platform vs. Store

The application is not the store. The application is the platform runtime that
hosts one or more Stores. `Store` (`apps.stores.Store`) is the authoritative
tenant and data-ownership boundary for all merchant commerce data.

```text
Commerce SaaS Platform
├── Store: Akhlaghi
├── Future Store B
├── Future Store C
│
├── Merchant Administration
│   └── Store-scoped operational management (per-Store dashboard, catalog, orders)
│
└── Platform Operations
    └── Platform lifecycle and infrastructure management (provisioning,
        billing, cross-Store observability, support tooling)
```

Every future commerce record must be either:

1. platform-global by explicit, documented design (e.g. a shared payment
   provider catalog, platform-level configuration); or
2. owned directly (a foreign key to `Store`) or indirectly (a foreign key to
   something that is itself Store-owned) by exactly one `Store`.

No record may be ambiguously scoped. If ownership is unclear for an existing
model, that is treated as an open risk to resolve in the PR that migrates that
model, not something to paper over with a global default.

## 2. Store as Tenant Boundary

`Store` is a new, independent domain entity. It is **not** `Vendor`. `Vendor`
today is a single-store, multi-seller construct (`apps.catalog.Vendor`) used
inside product/order ownership; it does not represent a tenant and its final
domain meaning (marketplace seller vs. supplier vs. something else) is
deferred to a dedicated catalog-domain review. See
`SAAS_DOMAIN_DECISIONS.md` for the explicit decision record.

`Store` provides:

* a stable, non-guessable public identifier (`public_id`, UUID) for external
  references (APIs, billing, support tooling) that must not leak sequential
  database IDs;
* a platform-global unique `slug` for human-readable identification and
  future path-based routing;
* one explicit lifecycle `status` (`provisioning`, `active`, `suspended`,
  `closed`) — see `SAAS_DOMAIN_DECISIONS.md` for why this replaces ambiguous
  boolean flags.

`Store` intentionally has no owner FK, no billing/subscription/theme/payment
fields, and no domain fields. Those are separate concerns (see below).

## 3. Merchant Administration vs. Platform Operations

Two distinct authorization/operational contexts exist conceptually, though
only the data model for the first is created in this stage:

* **Merchant Administration** — actions scoped to a single Store, performed
  by users who hold a `StoreMembership` in that Store (owner, administrator,
  catalog manager, order manager, content editor, analyst). Merchant
  Administration must never implicitly reach across Stores.
* **Platform Operations** — actions that operate on the platform itself
  (provisioning Stores, suspending a Store, billing, infrastructure). This is
  a Django-admin/operator concern in the current stage. Platform operators do
  not automatically receive unrestricted merchant-data access — that
  boundary is a documented decision (`SAAS_DOMAIN_DECISIONS.md`), not yet
  code-enforced beyond normal Django-admin `is_staff` gating.

Neither authorization enforcement nor dashboard scoping is implemented in
this PR (out of scope — see `SAAS_MIGRATION_PLAN.md`).

## 4. Store Ownership: Direct and Indirect

* **Direct ownership**: a model has a `ForeignKey(Store)`.
* **Indirect ownership**: a model is owned by something that is itself
  Store-owned (e.g. a future `OrderItem` owned via `Order.store`).

Every model that is added or migrated in later PRs must be classified as one
or the other, or explicitly declared platform-global with a written
rationale. "No FK, no rationale" is not an acceptable end state for a
commerce record.

## 5. Shared PostgreSQL Tenancy

The chosen tenancy strategy is a **shared database** with explicit ownership,
not schema-per-tenant or database-per-tenant, and not a third-party
multi-tenancy framework (see `SAAS_DOMAIN_DECISIONS.md` for the full
rejection list and rationale). This keeps operational complexity low for a
platform with a small number of Stores in its early life, while remaining
compatible with PostgreSQL Row-Level Security (RLS) as a future
defense-in-depth layer — RLS is explicitly not implemented in this stage.

Isolation is layered:

1. **Service-layer authority** — Store-scoped services are the authoritative
   place that resolves "which Store" for every read/write. Views and
   templates must not independently decide Store scope once later PRs
   introduce Store-scoped models.
2. **Model validation** — `clean()`/constraint-level checks as defense in
   depth against a service-layer bug, not the primary mechanism.
3. **Database constraints** — `UniqueConstraint`s and, where representable,
   `CheckConstraint`s enforce invariants the database can actually express
   (e.g. one primary domain per Store). Plain `ForeignKey` existence is not,
   by itself, tenant-integrity enforcement — a FK only proves a related row
   exists, not that it belongs to the same Store as its parent.
4. **Adversarial tests** — every future Store-scoped feature must ship with
   tests that attempt cross-tenant access and assert it is rejected.
5. **Future RLS** — a defense-in-depth layer to be added once the
   application-level model above is proven, not a substitute for it.

## 6. Request Store Context

Implemented (PR — "Store Resolution Infrastructure in Compatibility Mode").

### 6.1 Resolution flow

`apps.stores.resolution` is the single authoritative module that decides
"which Store does this request belong to." `StoreResolutionMiddleware`
(`apps.stores.middleware`) runs this resolution once per request and
attaches the result to `request.store` (a `Store` instance, or `None`).

The resolution source of truth is **the HTTP `Host` header, resolved
through `StoreDomain`** — nothing else. Concretely, for a given
`request.get_host()` value:

1. the port is stripped safely (including bracketed IPv6 literals);
2. if the resulting host is on the (small, centralized, overridable)
   development-host allowlist, the request goes through the compatibility
   fallback (§6.3) instead of the authoritative path below;
3. otherwise, the host is normalized via the existing authoritative
   `apps.stores.hostnames.normalize_hostname`;
4. the normalized hostname is looked up against `StoreDomain.hostname`
   (globally unique, so this lookup can never be ambiguous);
5. a match resolves only if it passes the **routing eligibility policy**
   (§6.2); anything else — no match, or a match that fails eligibility —
   resolves to `None` for callers that want a non-raising result, or a
   specific, distinguishable exception for callers (tests, future services)
   that need to know why.

Hostname is the authoritative **storefront** tenant source: a caller can
never supply a Store ID, and resolution never consults the authenticated
user, session state, `Vendor`, `Product`, `Cart`, `StoreMembership`, or any
other business data. See §6.4 for why that separation matters.

### 6.2 Routing eligibility policy

A `StoreDomain` may route a request only when **both**:

* its Store's `status` is `ACTIVE` (not `provisioning`, `suspended`, or `closed`);
* its own `verification_status` is `VERIFIED` (not `unverified`, `pending`, or `failed`).

This is deliberately conservative: an unverified, pending, or failed domain,
or a domain whose Store is not active, never resolves — even though the
hostname row genuinely exists. This is the same "fail closed rather than
guess" posture the compatibility fallback also follows (§6.3).

### 6.3 Temporary Akhlaghi / local-development compatibility mode

Akhlaghi must keep working locally before it has a real, verified
`StoreDomain`. A narrow, explicitly isolated fallback allows a fixed
allowlist of development hosts (`localhost`, `127.0.0.1`, `[::1]`,
`testserver` — Django's own test-client host) to resolve to the Akhlaghi
Store, but **only** when all of the following hold at resolution time:

* the (port-stripped) host is an **exact** match to an entry in the
  development-host allowlist — checked first, and *instead of* the
  authoritative `StoreDomain` lookup, not after it fails. A real, verified
  `StoreDomain` row happening to exist for one of these exact strings
  (e.g. `"127.0.0.1"`, which is unusually a syntactically valid hostname)
  would never be consulted — the compatibility path always wins for an
  exact allowlist match, and the authoritative lookup is never attempted
  for it. No legitimate merchant would ever use a loopback address as a
  real custom domain, so this is an accepted, tested quirk of the
  isolation design, not a tenant-isolation risk;
* the match is exact, never a substring or suffix — `localhost.example.com`
  and `127.0.0.1.example.com` are *not* development hosts and go through
  the authoritative path like any other hostname (adversarially tested);
* exactly one `Store` exists in the entire database, **regardless of that
  Store's own status** — a second Store that is merely provisioning,
  suspended, or closed still disables the fallback, exactly like an active
  one (adversarially tested per status);
* that sole Store's slug is `"akhlaghi"`;
* that sole Store is `ACTIVE`.

**This is temporary and fails closed, not a permanent behavior.** The
instant a second `Store` is created anywhere on the platform, the fallback
stops resolving anything — it does not fall back to "the first Store" or
any other heuristic; it raises internally and callers see `None`. This
property is directly tested (`apps.stores.tests.test_resolution.
CompatibilityModeTests`) and must not be weakened by any later change.

**Allowlist configuration safety.** `STORES_DEVELOPMENT_HOST_ALLOWLIST`
must be a list/tuple/set of hostnames. A bare string is rejected with
`django.core.exceptions.ImproperlyConfigured` rather than silently accepted
— Python iterates a string character-by-character, so a naive
`STORES_DEVELOPMENT_HOST_ALLOWLIST = "prod.example.com"` would otherwise
silently decompose into single-character "hosts" that can never match a
real Host header, quietly disabling the allowlist instead of doing what
was obviously intended. Misconfiguration fails loudly (every request
raises) rather than failing silently.

### 6.4 Separation from authentication and authorization

Tenant resolution, authentication, authorization, and data filtering are
four separate concerns, and this PR implements **only the first**:

* **Tenant resolution** (this middleware) — which Store is this request for?
* **Authentication** (`AuthenticationMiddleware`) — who is the user?
* **Authorization** (not implemented anywhere yet) — what may they do in
  this Store?
* **Data filtering** (not implemented anywhere yet) — which rows may this
  operation read or mutate?

`StoreResolutionMiddleware` never reads `request.user`, never touches the
session, never consults `StoreMembership`, and never makes an authorization
decision or redirects — it only ever sets `request.store`. Nothing in the
codebase consumes `request.store` yet; it is infrastructure for future PRs.

### 6.5 Middleware ordering

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.stores.middleware.StoreResolutionMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

`StoreResolutionMiddleware` runs immediately after `SecurityMiddleware`
(Django's own host/security processing) and, critically, **before**
`SessionMiddleware` and `AuthenticationMiddleware`. This is deliberate: it
structurally guarantees Store resolution cannot depend on session or
authentication state, since neither has run yet when this middleware
executes — the ordering itself enforces the §6.4 separation, rather than
relying on code review to keep it that way.

### 6.6 Reverse-proxy trust boundary (operational precondition, not code in this PR)

Resolution trusts `request.get_host()` completely — Django's own Host-header
parsing and `ALLOWED_HOSTS` validation. That trust model has one sharp edge
that is not, and cannot be, fixed by application code alone: Django's
`USE_X_FORWARDED_HOST` setting. Verified in this repository's
`shop_core/settings.py`: it is **not set**, so Django's default (`False`)
applies, and `get_host()` uses only the actual `Host` header — an
`X-Forwarded-Host` header is inert (directly demonstrated by
`apps.stores.tests.test_resolution.ForwardedHostTests.
test_x_forwarded_host_is_ignored_by_default`).

If this platform is ever deployed behind a reverse proxy and
`USE_X_FORWARDED_HOST = True` is set to make `get_host()` see the proxy's
original-request hostname, `get_host()` switches to preferring
`X-Forwarded-Host` over `Host`
(`test_x_forwarded_host_is_honored_once_explicitly_enabled` demonstrates
this with Django's own machinery, unmodified by this PR). **This is only
safe if the proxy is trusted to set or strip that header on every request
it forwards** — otherwise any client that can reach the application
directly (or send an arbitrary `X-Forwarded-Host` through a
misconfigured/permissive proxy) can influence Store resolution as
completely as if `ALLOWED_HOSTS` didn't exist. This is a deployment/proxy
configuration responsibility, not something `apps.stores.resolution` can
verify at runtime — do not enable `USE_X_FORWARDED_HOST` without first
confirming the fronting proxy strips client-supplied `X-Forwarded-Host`
headers.

`SECURE_PROXY_SSL_HEADER` is unrelated to this concern — it affects only
`request.is_secure()`/scheme detection, not `get_host()` or Store
resolution, and is also unset in this repository today.

### 6.7 Explicit non-goals of this PR

* No `Store` foreign key was added to any existing commerce/content model.
* `ShopSettings`/`FooterSettings` were not split or tenant-scoped.
* No caching was introduced — resolution is a bounded query every time
  (see the PR's own report for exact query counts).
* No DNS/HTTP domain-verification networking.
* No dashboard authorization changes, and `StoreMembership` is not consulted.
* No second real Store was provisioned, and no production domain was
  invented for Akhlaghi.

## 7. Media, Cache, Session and Background-Job Isolation Principles

These are documented now as forward-looking principles; none are implemented
in this PR:

* **Media**: future Store-owned media (product images, logos, etc.) must be
  stored under a path or storage backend that is unambiguously attributable
  to a Store, so that a misconfigured storage backend cannot serve one
  Store's media as another's.
* **Cache**: any cache key that stores or serves Store-scoped data must
  include the Store identifier in the key. Global cache keys (e.g. the
  current singleton `ShopSettings.load()` cache-like `get_or_create(pk=1)`
  pattern) must not be reused unscoped once `ShopSettings` becomes
  Store-owned.
* **Sessions**: user sessions may span multiple Store memberships (a user
  can belong to several Stores); session data must not assume a single
  implicit Store for a user.
* **Background jobs**: none exist in the current codebase. Any future
  background job that touches Store-owned data must carry an explicit Store
  identifier as a job argument — never inferred from ambient/global state.

## 8. What This PR Does Not Change

This PR adds a new, self-contained `apps/stores` app. It does not add a
`Store` foreign key to any existing model, does not change any existing
migration, view, template, service, or middleware behavior, and does not
change `INSTALLED_APPS` request/response behavior. The application behaves
exactly as it did before this PR. See `SAAS_MIGRATION_PLAN.md` for the
staged sequence that will change this incrementally.
