# SaaS Foundation Architecture

Status: Foundation stage (PR 2 of the staged migration plan — see `SAAS_MIGRATION_PLAN.md`).

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

A future PR ("Store resolution infrastructure in compatibility mode", see
`SAAS_MIGRATION_PLAN.md`) will introduce a mechanism for resolving which
Store a given request belongs to (via `StoreDomain` or another explicit
signal) and attaching it to the request in a way services can consume. This
PR does **not** implement that middleware, host resolution, or any
`request.store` attribute. `StoreDomain` is created now only as a data model
so that later resolution work has a stable schema to resolve against.

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
