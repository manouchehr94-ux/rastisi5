# SaaS Domain Decisions

ADR-style decision record for the SaaS foundation stage. Each decision lists
Context, Decision, Alternatives, Consequences, and Deferred Questions.

---

## ADR-1: Store Is a New Entity, Separate From Vendor

**Context.** The repository has an existing `apps.catalog.Vendor` model
(`name`, `slug`, `owner` FK to `User`, `logo`, `description`, `is_active`),
docstring "فروشنده / فروشگاه — پایه‌ی چند فروشنده‌ای (Multi-Vendor Ready)". It
is referenced by `Product.vendor` and `Order.vendor`. A prior assessment
proposed renaming or reinterpreting `Vendor` as the SaaS tenant.

**Decision.** `Store` is created as an independent new entity in a new
`apps.stores` app. `Vendor` is not renamed, repointed, or reinterpreted in
this PR. `Vendor` remains exactly as it is today.

**Alternatives considered.**
* Rename `Vendor` → `Store`. Rejected: `Vendor` is already a live FK target
  for `Product` and `Order` with existing data and tests; conflating "the
  SaaS tenant" with "a multi-vendor marketplace seller" would force a
  premature, irreversible decision about whether a Store's internal sellers
  (if the platform ever supports multi-vendor marketplaces per Store) are the
  same concept as the tenant itself. They are not obviously the same thing.
* Add a `Store` FK directly to `Vendor` now. Rejected: this PR's scope is
  explicitly limited to the new `apps.stores` app; no existing model gets a
  new FK in this PR (see Out-of-Scope in `SAAS_MIGRATION_PLAN.md`).

**Consequences.** Two parallel concepts exist for a period: `Vendor` (legacy,
unscoped) and `Store` (new, tenant boundary). This is intentional and
temporary. A later, dedicated catalog-domain PR must decide Vendor's final
meaning (e.g. "Vendor becomes a Store-scoped marketplace seller" or "Vendor
is deprecated in favor of Store" or "Vendor and Store coexist for
multi-vendor Stores") before catalog ownership is migrated (PR 5).

**Deferred questions.** What does "Vendor" mean once a Store can itself host
multiple internal sellers? Is single-seller-per-Store the only supported
model for the first SaaS version? These are explicitly out of scope here.

**Resolution (PR 5 — Catalog Tenant Boundary Assessment and Hardening).**
`Vendor` becomes a Store-owned Aggregate Root: a direct, non-nullable
`store` FK, with `slug` uniqueness re-derived as Store-scoped
(`UniqueConstraint(fields=["store", "slug"])` instead of platform-global
`unique=True`). This settles the "final meaning" question deferred above as
narrowly as the evidence supports: `Vendor` is not itself a tenant, and
multi-vendor-within-a-Store (a Store hosting more than one internal seller)
remains a distinct, unbuilt future feature — today's dashboard has no UI to
create a second `Vendor` for a Store at all (only `seed_shop` or Django
admin can). What this resolves is narrower and more urgent: every `Vendor`
row must belong to exactly one Store, so that Store A can never see,
reassign, or collide slugs with Store B's Vendor. Full multi-vendor-per-
Store product ownership semantics remain deferred, unchanged from this
ADR's original scope.

---

## ADR-2: Store Ownership Uses StoreMembership, Not a Store.owner Field

**Context.** A tenant needs an authoritative notion of "who owns this
Store." Two competing designs are possible: a direct `Store.owner` FK, or an
owner represented as a role within a membership table.

**Decision.** Store ownership is represented exclusively through an active
`StoreMembership` row with `role=owner`. No `Store.owner` field is added.

**Alternatives considered.**
* `Store.owner` FK to `User`, in addition to `StoreMembership`. Rejected:
  this creates two sources of truth that can silently disagree (owner FK
  says user A, membership table says user B is the active Owner). Every
  future authorization check would need to reconcile both, which is
  itself a class of bug.
* `Store.owner` FK only, no `StoreMembership` in this stage. Rejected: a
  Store must support multiple members with different roles from the start
  (StoreMembership is explicitly foundation-stage per the task program),
  and ownership transfer/co-ownership cannot be modeled by a single FK
  without a subsequent migration anyway.

**Consequences.** "Who owns Store X" is always answered by querying
`StoreMembership.objects.filter(store=X, role=OWNER, status=ACTIVE)`. This
query is expected to return at most one row (enforced by a partial unique
constraint, see ADR-3), but the enforcement mechanism is the constraint, not
a denormalized field.

Because ownership lives exclusively in `StoreMembership`, deleting a `User`
must not be allowed to silently delete their membership rows — that could
delete a Store's only active Owner membership as a side effect of an
unrelated user-deletion action, orphaning the Store. `StoreMembership.user`
therefore uses `on_delete=PROTECT`, not `CASCADE`: deleting a User who still
holds any membership raises `ProtectedError` rather than deleting the
membership row. `StoreMembership.store` still uses `CASCADE` — a membership
has no meaning without its Store, so deleting the Store deleting its
memberships is correct. `StoreMembership.invited_by` remains `SET_NULL`,
since losing a record of *who sent an invitation* is not a safety concern.
Formal user-account deletion for a user who holds memberships requires a
future, explicit membership-revocation/ownership-transfer service to run
first; this PR does not implement that service.

---

## ADR-3: Store Has One Explicit Status Field

**Context.** The prior assessment suggested boolean flags such as
`is_active` / `is_suspended`, which can independently be set to
contradictory combinations (e.g. both true).

**Decision.** `Store.status` is a single `TextChoices` field:
`provisioning`, `active`, `suspended`, `closed`.

**Alternatives considered.** Multiple booleans — rejected for the reason
above. A richer state machine with billing/deletion sub-states — rejected as
premature; this PR does not implement billing or deletion lifecycle.

**Consequences.** Any future state transition (e.g. suspend, reactivate,
close) is a single-field update with a well-defined value set, and is a
natural place to hang a future service-layer transition function. No
transition logic or validation of legal transitions is implemented yet.

**Deferred questions.** Legal transition rules (e.g. can a `closed` Store
return to `active`?) and billing-driven transitions are deferred to the
billing/lifecycle work, not this foundation PR.

---

## ADR-4: StoreDomain Stores Normalized Hostnames, With One Primary per Store

**Context.** Custom domains are a standard SaaS requirement, and hostname
input is an XSS/SSRF/host-header-confusion-adjacent surface if accepted
loosely (schemes, paths, credentials, ports embedded in a "hostname" field).

**Decision.** `StoreDomain.hostname` stores only a normalized hostname
(lowercased, trimmed, trailing dot removed, validated as a syntactically
valid hostname). Scheme, path, query, fragment, credentials, and port are
rejected at write time by the model's `clean()`/normalization path, not only
by a form. This guarantee covers `instance.save()`, `full_clean()`, and
`StoreDomain.objects.bulk_create()` (which normalizes and validates each
instance before insertion, since `bulk_create()` never calls `save()`).
`StoreDomain.objects.filter(...).update(hostname=...)` is the one write path
that cannot be normalized this way — a raw SQL `UPDATE` runs no Python code —
so it is rejected outright with `StoreDomainMutationError` rather than being
allowed to persist an un-normalized value. Hostname is platform-globally
unique. At most one `is_primary=True` `StoreDomain` per Store is enforced by
a partial (conditional) database `UniqueConstraint`.

**Alternatives considered.** Storing a full URL and parsing it downstream
wherever needed — rejected: this multiplies the number of places that must
agree on what counts as "the same domain," which is exactly the kind of
duplicate-source-of-truth problem this program is meant to avoid.
Form-level-only validation — rejected: bypassable via the admin, shell, data
migrations, or a future API, so it is not authoritative. Relying on
`Model.save()`/`clean()` alone — rejected once identified that
`QuerySet.update()` and `QuerySet.bulk_create()` bypass both entirely; a
dedicated `StoreDomainQuerySet` closes that gap for `bulk_create()` and
blocks the un-normalizable `update(hostname=...)` path outright.

**Consequences.** Internationalized (IDN) domains are accepted only as their
ASCII-compatible (Punycode/IDNA) form; normalization decodes/encodes
consistently so visually-identical Unicode variants cannot collide with or
bypass uniqueness. This is a normalization decision, not a full IDNA
homograph-attack mitigation (e.g. this PR does not attempt to block
confusable-Unicode-lookalike domains beyond IDNA syntax rules) — flagged as
a deferred question below.

**Deferred questions.** IDNA homograph/lookalike mitigation beyond syntactic
IDNA validation. DNS/HTTP verification networking (deferred to a later PR by
explicit program instruction).

---

## ADR-5: Domain Verification Is a Small Lifecycle, Not a Boolean

**Context.** "Is this domain verified" needs more than a boolean once a
verification flow (token issuance, retry, expiry) exists.

**Decision.** `StoreDomain` carries `verification_status`
(`unverified`/`pending`/`verified`/`failed`), a `verification_token`,
`verification_requested_at`, and `verified_at`. No DNS/HTTP verification
networking is implemented; only the model foundation. Coherence between
these four fields is enforced twice, deliberately: as database
`CheckConstraint`s (authoritative — hold even against direct SQL or a bug in
application code) and mirrored in `clean()` (defense in depth, for a
friendlier `ValidationError` before the database is even touched). The
enforced rules are exactly:

* `verified` requires `verified_at` to be set.
* Any non-`verified` status must **not** retain `verified_at` (so a domain
  that later moves from `verified` to `failed` must have `verified_at`
  cleared by the caller, not left stale).
* `pending` requires `verification_requested_at` to be set.
* `pending` requires a non-empty `verification_token`.
* The existing uniqueness rule for non-empty `verification_token` values is
  unchanged.

**Consequences.** A later PR can implement the actual verification checker
against this schema without another migration to add lifecycle fields. The
rules above are intentionally the minimum needed for internal coherence of
the four fields — they are not a claim that the verification *process*
(retry limits, token expiry, re-verification after a hostname change) is
fully modeled; that is still future work for the verification-checker PR.

---

## ADR-6: Customer Identity — Deferred, Direction Recorded Only

**Context.** `apps.customers.Customer` today is a 1:1 extension of
`django.contrib.auth.User` with no Store scoping. Deciding its final shape
touches authentication, privacy, and cross-Store data-sharing questions that
are out of scope for this PR.

**Decision.** No changes to `Customer` in this PR. The recorded future
direction is:

```text
Global authentication identity (the Django User / login credential)
+
Store-specific commerce customer profile (order history, addresses,
wishlist, VIP status, spend totals — all Store-scoped)
```

i.e. a person can log in once (global identity) but has a distinct
commerce profile — and distinct privacy boundary — per Store they have
shopped at. This mirrors the Store/StoreMembership split already adopted for
staff-side identity.

**Alternatives considered.** Fully global Customer (one profile shared
across all Stores) — rejected as a final design because it would leak
one Store's purchase history/VIP status/spend into another Store's view of
the same person, which is a cross-tenant data leak by definition. Fully
duplicated User-per-Store — rejected as unnecessarily duplicating
authentication identity and complicating login.

**Deferred questions.** Exact mechanism for "same login, N Store profiles";
whether `OtpCode` is platform-global (plausible, since it verifies a phone
number, not a Store relationship) or needs a Store dimension for
rate-limiting/audit purposes — not decided here. `OtpCode` is explicitly
**not** declared platform-global by this document; that determination is
deferred to the customer-identity PR (PR 10).

---

## ADR-7: Payment Provider and Store Payment Configuration Are Separate Concepts

**Context.** `apps.orders.PaymentGateway` today mixes what looks like a
provider definition (`name`, `slug`, `icon`, `fee_percent`) with what will
need to become per-Store enablement/credentials once Stores have their own
payment configuration. Adding a `Store` FK directly to `PaymentGateway`
would conflate "this payment method exists on the platform" with "this
Store has enabled and configured it."

**Decision.** No change to `PaymentGateway` in this PR. The recorded future
direction is three separate concepts:

```text
PaymentProvider              — platform-global integration definition
StorePaymentConfiguration    — Store-specific credentials and enablement
PaymentTransaction           — order/payment attempt and result
```

**Alternatives considered.** Add `Store` FK to the existing
`PaymentGateway` — rejected: `PaymentGateway` must first be audited to
determine which of its current fields are really provider-level (global)
versus configuration-level (per-Store), which this PR does not do.

**Deferred questions.** The `PaymentGateway` audit itself; how
`fee_percent` splits between platform-level default and Store-level
override, if at all.

---

## ADR-8: Platform Operators Do Not Automatically Get Unrestricted Merchant-Data Access

**Context.** Django's `is_staff`/`is_superuser` flags currently grant full
admin access to all data through the Django admin, with no Store-scoping
concept.

**Decision.** Being a platform operator (however that role is eventually
modeled) must not be conflated with "can read/write any Store's commerce
data unrestricted." Any future platform-operator tooling that needs
cross-Store visibility must be an explicit, audited capability, not an
incidental side effect of Django-admin `is_staff`.

**Consequences.** This PR does not implement any enforcement of this
decision (no authorization code changes at all). It is recorded so that
later PRs (dashboard authorization, PR 11) are not designed against an
assumption that staff access already implies "trusted with all merchant
data."

**Deferred questions.** Concrete mechanism (separate permission model,
audit-logged elevated access, etc.) — not decided here.

**Addendum (PR 5 — Catalog Tenant Boundary Assessment and Hardening).**
This ADR's "not implemented, not to be assumed safe" framing was
subsequently misquoted in `SAAS_MIGRATION_PLAN.md` as an "already-accepted"
scope — it was not; the text above has always meant the opposite. Once PR 5
gave `Product`/`Category`/`Brand`/`Vendor` a real, non-nullable `store` FK,
the gap this ADR describes stopped being latent (there was only ever one
Store's catalog data to leak before) and became a live cross-Store exposure
the moment any second Store's dashboard staff existed, since
`apps.dashboard`'s `is_staff`-gated authorization and Django's own
`AdminSite` shared the identical flag. PR 5 closes the immediate exposure,
without resolving this ADR's deferred questions: Django Admin is now
restricted to active superusers only (`apps.stores.admin_permissions`).
Platform-operator tooling still has no Store-scoped, audited,
narrower-than-superuser capability — that remains exactly as open as this
ADR originally left it, and is still PR 11's job.

---

## ADR-9: Merchant Sales Funds Flow Directly to Merchant-Owned Payment Accounts

**Context.** A marketplace-style platform could route customer payments
through a platform-owned account before disbursing to merchants
(platform-as-merchant-of-record), or let each Store's payment configuration
point directly at that Store's own payment-provider account.

**Decision.** For the first SaaS version, the recorded direction is that
funds flow directly to merchant-owned payment accounts (the platform is not
a merchant-of-record / money-transmitter in v1). This has no code impact in
this PR; it constrains the design of `StorePaymentConfiguration` and
`PaymentTransaction` in the future payment-domain PR (PR 7).

**Alternatives considered.** Platform-as-merchant-of-record with internal
ledgering/payouts — rejected for v1 due to the additional regulatory and
reconciliation complexity, revisit once the platform has multiple Stores and
a real payments requirement.

**Deferred questions.** Whether/when a payout/ledger model becomes
necessary as the platform grows.

---

## ADR-10: Store Configuration Is Modeled as Direct Domain Models, Not a Generic StoreConfiguration Table

**Context.** `apps.core.ShopSettings` today bundles four unrelated
concerns in one singleton row: store identity/contact, tax/shipping
defaults, SMS provider credentials, and branding/theme tokens. A dedicated
Store Configuration Architecture Assessment evaluated five alternatives
(one god model; a generic `StoreConfiguration` aggregate table plus
domain-specific one-to-ones; `Store` as aggregate root with direct
domain-specific models and no umbrella table; JSON documents; a relational
+ namespaced-JSON hybrid) against this repository's actual field inventory
— not generic SaaS theory.

**Decision.** `Store` is the aggregate root. No generic `StoreConfiguration`
database table is introduced. Configuration domains are modeled as direct,
independently-owned models attached straight to `Store` (mirroring how
`FooterSettings`, `SocialLink`, and `Menu` already exist as separate
top-level models today, not sub-documents of one settings blob). Domain
models are introduced incrementally, driven by fields that actually exist
in the codebase — not speculatively for every domain named in the platform
roadmap (SEO, notifications, checkout rules, order numbering, invoicing,
and email do not have a single field in this codebase today, so no models
are created for them yet). Current `ShopSettings` is **not split** in the
resolution-infrastructure PR that introduced this ADR; a future PR will
tenant-scope it as-is (add a `store` FK, no field reorganization), with any
eventual split treated as its own, separately-reviewed decision.

**Alternatives considered.** See the full assessment for the five-way
comparison; in short: one god model was rejected as reproducing the exact
problem this ADR exists to prevent; a generic `StoreConfiguration`
aggregate table was rejected because it would add a table with no real
column content of its own, existing only to be pointed at; JSON-only was
rejected because this codebase's existing settings fields all have strict,
already-relied-upon per-field validation (hex colors, decimal ranges,
choices) that JSON would weaken.

**Consequences.** Splitting `ShopSettings` (identity/commerce-defaults vs.
branding/theme vs. SMS credentials) is deferred to a dedicated future PR,
sequenced after the tenant-scoping-without-split PR described in
`SAAS_MIGRATION_PLAN.md`. The merchant-facing admin UI's existing five
sections (general, finance, delivery-payment, sms, appearance) remain the
UX contract regardless of how many models eventually back them — database
table boundaries must never dictate a fragmented admin experience. The
tenant-scoping-without-split PR referenced above is PR 4
(`SAAS_MIGRATION_PLAN.md`); see ADR-12 for the specific ownership shape it
gave `ShopSettings`/`FooterSettings`/`FooterTrustBadge`/`FooterPaymentLogo`.

**Deferred questions.** Exact field boundary between "identity" and
"commerce-defaults" if/when `ShopSettings` is split; timing of the SMS
credential extraction (a real, already-identified plaintext-handling issue
independent of tenancy); whether feature flags/experimental configuration
ever gets a minimal JSON column on `Store` itself, once such fields
actually exist.

---

## ADR-11: Store Resolution Is Hostname-Authoritative, With a Fail-Closed Compatibility Fallback

**Context.** Every future Store-scoped model, view, and service needs a
single, trustworthy answer to "which Store is this request for?" before
any of them can be built safely. `StoreDomain` existed as a data model
since the foundation PR but nothing consumed it.

**Decision.** `apps.stores.resolution` is the sole authoritative resolver:
it maps `request.get_host()` → normalized hostname (via the existing
`normalize_hostname`) → `StoreDomain.hostname` lookup → the associated
`Store`, gated by a routing-eligibility policy (Store `ACTIVE` and domain
`VERIFIED` — see `SAAS_ARCHITECTURE.md` §6.2). `StoreResolutionMiddleware`
runs this once per request and attaches the result to `request.store`
(`Store` or `None`), positioned before `SessionMiddleware` and
`AuthenticationMiddleware` in `MIDDLEWARE` so tenant resolution is
structurally independent of session/auth state, not just independent by
convention. A narrow, explicitly isolated, temporary compatibility fallback
lets a fixed development-host allowlist resolve to the Akhlaghi Store, but
only while exactly one, active, `"akhlaghi"`-slugged Store exists — it
fails closed the instant a second Store is created, rather than falling
back to "the first Store" or any other heuristic.

**Alternatives considered.** Deriving Store from the authenticated user's
`StoreMembership` — rejected for storefront resolution: a storefront
visitor is usually unauthenticated, and even when authenticated, "which
Store am I browsing" must not depend on "which Store(s) am I staff of" —
those are different questions (tenant resolution vs. authorization, see
`SAAS_ARCHITECTURE.md` §6.4). Accepting a caller-supplied Store ID (query
param, header, session key) — rejected outright as trivially spoofable;
verified directly by adversarial tests
(`apps.stores.tests.test_resolution.IsolationAdversarialTests`). A single
`Store.objects.first()`-style fallback — rejected; this is precisely the
class of singleton assumption flagged as unsafe in the prior Tenant
Ownership assessment, and the narrow, multi-condition compatibility check
in this ADR exists specifically to avoid it.

**Consequences.** No existing view, template, or business query was
changed — `request.store` is set on every request but consumed nowhere
yet. A Django system check for "middleware omitted" or "unsafe
compatibility configuration in production" was considered and explicitly
declined for this PR: no such setting (e.g. a "strict tenant mode" flag)
exists yet to check against, and the compatibility fallback's own
multi-condition gate already fails closed structurally, so no additional
check could add a reliable, non-noisy signal beyond what the fallback's own
logic already guarantees.

**Deferred questions.** When request-time resolution becomes a *hard*
requirement for a given model (i.e., when its own PR removes any
compatibility fallback) is decided per-model, not by this ADR. Whether a
future "strict tenant mode" setting is introduced, and a matching system
check with it, is left open.

---

## ADR-12: `ShopSettings`/`FooterSettings` Are One-Row-Per-Store; Trust Badges and Payment Logos Own Their Store Directly

**Context.** ADR-10 decided `ShopSettings` and `FooterSettings` would
eventually be tenant-scoped without a field split. PR 4
(`SAAS_MIGRATION_PLAN.md`) is the PR that actually does this, and had to
answer two concrete questions ADR-10 left open: (1) what field/constraint
shape enforces "one row per Store" instead of "one row for the whole
platform," and (2) whether `FooterTrustBadge`/`FooterPaymentLogo` should
gain their own `store` FK or be reached only through `FooterSettings`.

**Decision.** `ShopSettings.store` and `FooterSettings.store` are each a
`OneToOneField("stores.Store")` — the database itself enforces at most one
row per Store, not just applic­ation-level convention. `FooterTrustBadge`
and `FooterPaymentLogo` each get a plain, non-unique
`ForeignKey("stores.Store")` directly, independent of `FooterSettings`:
inspection of every call site showed both are queried and managed
independently today (their own dashboard list/create/edit/delete/toggle
views, filtered directly by `store`, never joined through
`FooterSettings`) — inferring their ownership from the fact that the
storefront renders them inside the same footer region as `FooterSettings`
would have been ownership-by-visual-adjacency, not ownership-by-actual-use.
Retrieval for both settings models follows one shared contract:
`load(store=...)` (explicit, authoritative, raises a dedicated
`*NotProvisionedError` rather than ever returning another Store's row or
auto-creating one) and `load()` (temporary compatibility mode, delegating
to PR 3's `resolve_compatibility_store()` fail-closed check). Provisioning
a new Store's rows is a separate, explicit, idempotent `provision_for(store)`
classmethod — never a signal, never invoked implicitly on read.

**Alternatives considered.** A shared, unique `store` FK plus
`FooterTrustBadge`/`FooterPaymentLogo` reached only via
`FooterSettings.trust_badges`/`payment_logos` reverse relations — rejected
because it does not match how these models are actually used in this
codebase today and would require a speculative redesign of their own
dashboard views as part of a PR whose stated scope is tenant-scoping, not
redesigning. Enforcing "one row per Store" purely at the application layer
(`unique=True` alone, or a service-layer check) instead of a
`OneToOneField` — rejected: a plain unique constraint plus a bug in the
service layer could still create a second row per Store, whereas
`OneToOneField`'s own DB-level unique index makes that a hard constraint
violation, not a bug waiting to happen. Auto-provisioning a Store's
settings via `get_or_create()` inside `load()` itself — rejected outright
per this PR's own governing instructions: that would permanently hide a
genuinely missing provisioning step behind a silent read-time side effect,
the same failure mode the removed platform-wide `get_or_create(pk=1)`
singleton exhibited, just re-scoped per-Store instead of fixed.

**Consequences.** The previous `save()` override that forced `pk=1` on
every `ShopSettings`/`FooterSettings` instance is removed entirely from
both models — a Store's settings row can have any primary key, and no code
anywhere may assume otherwise. `resolve_compatibility_store()` was promoted
from a resolver-module-private helper (`_resolve_compatibility_store`) to
a public function specifically so this compatibility contract has exactly
one implementation, shared by hostname resolution (PR 3) and settings
retrieval (PR 4) — not two independently-maintained copies of the same
fail-closed rule that could quietly drift apart. `SocialLink`, `Menu`,
`ContentPage`, `HeroSlide`, and `PromotionalBanner` were deliberately left
un-scoped in this PR; that remains PR 8's job.

**Deferred questions.** Whether `FooterTrustBadge`/`FooterPaymentLogo`
should ever gain a display-order uniqueness constraint per Store (today,
duplicate `display_order` values within a Store are allowed and broken
only by `id` as a tiebreaker) is left open — no requirement for it exists
today. Whether provisioning should ever be triggered automatically as part
of a future "create Store" service/admin action (rather than an explicit,
separate call) is left to whichever PR introduces that service.

---

## ADR-13: Tenant-Sensitive Services Take an Explicit Store Argument, Resolved Once at the Boundary

**Context.** ADR-12's fail-closed compatibility check (§ ADR-12) meant
`apps.cart.services.pricing` and `apps.sms.services.sms_service` — which
still called `ShopSettings.load()` with no Store — would break the moment
a second, real `Store` existed, even for that Store's own valid request.
Neither `Cart`, `Order`, `Customer`, nor `SmsTemplate`/`SmsLog` carry a
`store` FK yet (that is PR 6/7/9/10's job), so these services had no
model-level way to derive "which Store" on their own.

**Decision.** Every tenant-sensitive service function that reads
`ShopSettings` takes a required, keyword-only `store` argument — no
default, so a caller cannot silently omit it and fall into compatibility
mode by accident. A new shared helper,
`apps.stores.resolution.resolve_store_for_service(request)`, resolves the
authoritative Store exactly once, at the HTTP boundary (a view, or a
service function that already receives `request`): `request.store` if
already resolved, otherwise the same `resolve_compatibility_store()`
fail-closed check used everywhere else. The resolved, concrete `Store`
object is then threaded down explicitly as a plain function argument
through every deeper call (`cart_totals` → `_free_shipping_threshold`/
`_tax_percent`; `create_order_from_cart`/`change_order_status`/
`simulate_payment` → `send_event_sms` → `get_backend`) — none of those
deeper functions ever call `resolve_store_for_service` or
`resolve_compatibility_store` themselves, and none accept a caller-supplied
Store ID from request data (POST body, query parameter) as authoritative.

**Alternatives considered.** Giving `cart_totals`/`send_event_sms` an
optional `store=None` that falls back to compatibility mode internally —
rejected: that would re-introduce exactly the "quietly using Akhlaghi" risk
ADR-12 exists to close off, just moved one layer deeper, and would make an
explicit `store=None` call indistinguishable from "caller forgot to
resolve one." Adding a `store` FK to `Cart`/`Order` now, ahead of PR 6/7,
to give these services a model-level Store — rejected as unnecessary and
out of scope: every call site already has an authoritative Store available
from the triggering request, so no schema change was needed to make these
services Store-explicit. Passing `request` itself into every deep service
function instead of a resolved `Store` — rejected for the leaf functions
(`cart_totals`, `send_event_sms`, etc.): they are pure business-logic
functions with no reason to depend on Django's request object, and passing
the already-resolved `Store` keeps them independently testable without a
request/response cycle.

**Consequences.** `apps.dashboard.views._resolve_dashboard_store`
(introduced in PR 4) now delegates to `resolve_store_for_service` instead
of duplicating the same "request.store, else compatibility check" logic. A
handful of service functions without prior `request` access
(`create_order_from_cart`, `change_order_status`, `simulate_payment`,
`otp_service.request_otp`, `auth_service.signup`/`create_account_for_guest`)
gained a `store` parameter; their callers across `apps.orders`,
`apps.customers`, `apps.sms`, and `apps.dashboard` were all updated
accordingly — none of those apps' models changed. `apps.core.management.commands.seed_shop`
(no request context) resolves Akhlaghi explicitly by slug rather than via
the request-shaped compatibility check, since it only ever seeds Akhlaghi
demo data.

**Deferred questions.** Whether `resolve_store_for_service` should move out
of `apps.stores.resolution` (a module whose docstring frames it around
"request-time" resolution, even though this function and
`resolve_compatibility_store` are not themselves request-specific) into a
more neutrally-named module is left open — a naming/layering question, not
a functional one, and not worth a file move bundled into this PR.

---

## ADR-14: `Order` Gets a Direct `store` FK (Redundant Store-Owned Child), Not Just `vendor.store`

**Context.** PR#20/ADR-13 deliberately gave `Cart`/`Order` no `store` FK,
since every call site already had an authoritative `Store` available from
the triggering request and `Order.vendor` (itself Store-scoped since PR#21)
made the ownership derivable. PR23 found this indirection was a real,
exploited gap in practice: `apps.dashboard.services.orders_admin_service`/
`customers_admin_service` queried `Order.objects`/`Transaction.objects`
completely unscoped by Store — the exact bug class ADR-13 and PR#21 already
fixed once for catalog, recurring here because there was no `Order.store`
column to filter on directly, only a join through `vendor__store` that
every call site would have had to remember to add correctly, forever.

**Decision.** `Order.store` is now a direct, required
(`on_delete=PROTECT`) foreign key to `Store` — the same "Redundant
Store-owned Child" category as `apps.catalog.ProductVariant.store` (see
`00_PROJECT_MASTER_REFERENCE.md` §8's four-category ownership model): the
authoritative source is still `Order.vendor.store`, but a direct column
exists because per-Store filtering/reporting on `Order` is a proven,
constant need (every dashboard order/invoice/payment/customer query), not
a hypothetical one. `on_delete=PROTECT` — not `CASCADE` like catalog's
Store-owned content — because an `Order` is an immutable financial/
historical record; deleting a `Store` must never silently delete its order
history. The invariant `order.store_id == order.vendor.store_id` is
enforced at two layers: `apps.orders.services.order_service.create_order_from_cart`
(the sole Production write path for `Order` creation) raises `ValueError`
on mismatch before ever touching the database, and `Order.clean()` is a
second, model-level defensive check mirroring `apps.catalog.models.Product.clean()`'s
already-established pattern. A database-level `CheckConstraint` was
considered and rejected — Django's `CheckConstraint` cannot compare two
different tables' columns, and neither SQLite nor the project's intended
production database (PostgreSQL) supports a cross-table CHECK constraint
either, so no implementation would actually provide DB-level enforcement
here; claiming one exists would be a false statement about the schema.

**Migration.** Staged exactly like catalog's original backfill
(`0006`→`0007`→`0008`): `0003_store_scope_orders_schema` (nullable FK +
new `idempotency_key`/`OrderItem.sku`/`OrderItem.variant_label` fields +
`PaymentGateway`/`ShippingMethod.store`, also nullable, plus their new
per-Store slug-uniqueness constraints) → `0004_backfill_orders_store`
(data migration) → `0005_store_scope_orders_enforce_not_null` (NOT NULL).
Unlike catalog's original backfill, `Order.store` did **not** need an
Akhlaghi-guess fallback: every existing `Order` already had a required,
non-null `vendor`, and every `Vendor` already had a required, non-null
`store` (enforced since catalog's own `0008`) — so the backfill derives
`Order.store` deterministically from `Order.vendor.store` for every row,
never guessing or falling back to Akhlaghi. `PaymentGateway`/
`ShippingMethod` had no prior Store relationship at all (the same
situation catalog's `Vendor`/`Category`/`Brand` were originally in), so
their backfill does use the Akhlaghi-exact-slug-or-fail pattern, identical
in shape to `apps/catalog/migrations/0007_backfill_catalog_store.py`.

**Alternatives considered.** Leaving `Order` without a direct `store` field
and instead auditing every dashboard query to join through `vendor__store`
correctly — rejected: this is exactly the "remember to do it everywhere,
forever" pattern that already failed once (the gap this ADR fixes). Giving
`Transaction` its own direct `store` FK too — rejected as unnecessary
duplication: `Transaction.order` is a required FK, and `Order.store` is
now itself required and authoritative, so `Transaction`'s Store is already
unambiguously reachable via `transaction.order.store`; dashboard payment
queries filter via `order__store=store` rather than a redundant column.

**Consequences.** `apps.dashboard.services.orders_admin_service`,
`customers_admin_service`, and `settings_admin_service` all now require an
explicit `store` keyword argument, resolved once per request via
`apps.dashboard.views._resolve_dashboard_store` (already the established
pattern), and every dashboard order/invoice/payment/customer/gateway/
shipping list, detail, and mutation endpoint is Store-scoped — a Store A
user requesting a Store B `Order`/`Transaction`/gateway/shipping-method by
ID or code now gets the repository's standard safe denial (404), not the
object. `Customer` deliberately still has no `store` field (see ADR-6,
still deferred) — `customers_admin_service.annotated_customers` instead
scopes by the existing `orders__store` relationship, so a customer is only
visible in a given Store's dashboard if they have at least one `Order`
there, and their `order_count`/`paid_total` aggregates are computed with
that same Store filter, never a global total.

---

## ADR-15: Checkout Idempotency — a Server-Held Token on `Cart`, Not a Client-Echoed Field or a Random-Code `.exists()` Check

**Context.** The pre-PR23 order-code generator
(`f"{ORDER_CODE_PREFIX}-{random.randint(10000, 99999)}"`, checked via a
plain, non-locked `Order.objects.filter(code=code).exists()`) was never a
real idempotency mechanism — it only avoided colliding on the *code*
string; nothing prevented two Orders being created from one legitimate
checkout submission (double-click, browser retry, network retry). A real
mechanism was needed that: requires no client cooperation (nothing a
compromised or buggy client could omit, forge, or replay across a
different Cart/Store); works identically on SQLite (tests) and PostgreSQL
(production) without relying on Redis or a process-local lock (both
explicitly out of scope for this PR); and closes the concurrent-race
window, not just the easy sequential-retry case.

**Decision.** `Cart` gained a `checkout_token` field
(`secrets.token_urlsafe(32)`, generated server-side, once, lazily, the
first time `apps.orders.services.checkout_service.get_or_create_checkout_token`
is called for that Cart — never read from or influenced by client input).
Because every checkout attempt for the same guest session or logged-in
Customer resolves the *same* `Cart` row (the existing, unchanged
`apps.cart.services.cart_service.get_cart` lookup), a double-click or
retry naturally reads back the identical token with zero new state to
manage and nothing for a client to submit or tamper with. `Order` gained a
matching `idempotency_key` (blank-by-default, uniqueness enforced only
when set — the same `condition=~Q(field="")` partial-uniqueness pattern
already used for `ProductVariant.sku`, so the many existing tests/services
that create Orders without a token are entirely unaffected).
`apps.orders.services.checkout_service.finalize_order` checks for an
existing `Order` with that token *before* checking whether the Cart is
empty (a same-Cart replay after a first, already-successful submission
would otherwise see an emptied cart and wrongly report "cart is empty"
instead of returning the original Order). `apps.orders.services.order_service.create_order_from_cart`
itself repeats that check, then — for the genuine concurrent-race window,
where two requests both pass that check before either commits — wraps
only the `Order.objects.create(...)` call in a nested `transaction.atomic()`
savepoint and catches `IntegrityError`: the losing request's savepoint
rolls back (not the whole transaction), and it re-queries and returns the
winning request's `Order` instead of raising, creating a duplicate, or
double-decrementing stock (the item/stock loop never runs for the losing
attempt, since the `Order.objects.create()` call happens first and fails
before it).

**Alternatives considered.** A hidden form field echoed back by the
client — rejected: requires template changes, and trusts a client-supplied
value's *presence* even if not its content, for no benefit over reading
the value straight off the server-held `Cart` row the request already
resolves. A dedicated `CheckoutAttempt` model — rejected as unnecessary
duplication: `Cart.checkout_token` + `Order.idempotency_key` already give
a complete request → in-flight-attempt → completed-Order chain without a
third table. A process-local lock (e.g. a `threading.Lock` keyed by
Cart ID) — rejected per this PR's explicit scope: it wouldn't work across
multiple application processes/workers in real production deployment, and
the database-level unique-constraint approach above is strictly stronger
(works correctly regardless of process/worker topology) at no extra cost.

**Consequences.** A "true" concurrent-race test cannot be exercised
deterministically against SQLite (its whole-database write lock
effectively serializes concurrent writers rather than reproducing
PostgreSQL's row-level contention) — `apps/orders/tests/test_checkout_correctness.py::CheckoutIdempotencyServiceTests.test_concurrent_race_simulated_via_preexisting_conflicting_order`
instead deterministically pre-creates the "winning" Order with the same
key and asserts the losing call's `IntegrityError`-catch-and-refetch path
behaves correctly — this exercises the exact code path a real race would
hit, without depending on real thread/process timing. Verifying the
mechanism's behavior under genuine PostgreSQL row-level lock contention is
listed as a pre-launch verification item, not something SQLite testing can
substitute for (see `00_PROJECT_MASTER_REFERENCE.md`'s SQLite-vs-PostgreSQL
concurrency-limitation note).

---

## ADR-16: Merchant Admin Portal Domain and Routing — `Store.admin_subdomain` Is a Platform-Assigned Field, Independent of `StoreDomain`; `/admin-portal/` Is the Canonical Route

**Context.** The originating Phase 1B request specifies a target
architecture where a merchant's public storefront
(`https://<public-domain>`) and merchant admin portal
(`https://<admin-subdomain>.rastisi.ir/admin-portal/`) are independent:
changing or losing the public domain must never affect the stable admin
host. Before this PR, the codebase had no concept of an admin subdomain at
all — Host-based Store resolution only ever produced a Store from a
verified `StoreDomain` row (a merchant-supplied, DNS/HTTP-verified public
domain) or the narrow single-Store development fallback. Nothing
distinguished "this Host is this Store's public storefront" from "this
Host is this Store's admin portal" — the same resolved Store served both
purposes through one mechanism. The dashboard itself was also still
mounted at `/admin-panel/`, not the target `/admin-portal/` path.

**Decision.**

1. `Store` gains a new `admin_subdomain` field: a single DNS label
   (`CharField`, `max_length=63`, globally unique, ASCII-only, normalized
   lowercase, validated against a reserved-word list), independent of
   `StoreDomain` — it lives directly on `Store`, not as a `StoreDomain`
   row, precisely because it is platform-assigned and never subject to the
   merchant DNS/HTTP verification lifecycle `StoreDomain` implements.
   `Store.save()` auto-derives a value from `slug` (or, if `slug` isn't a
   valid ASCII DNS label — `Store.slug` allows Unicode — from `public_id`)
   when a caller doesn't supply one explicitly, so every existing
   `Store.objects.create(name=..., slug=...)` call site across the
   codebase and test suite keeps working unmodified; a real
   merchant-onboarding flow can always set an explicit, chosen value later.
   `apps.stores.resolution.resolve_store_for_admin_host(raw_host)` resolves
   a Store from a Host of the exact shape
   `f"{admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"`
   (`RASTISI_ADMIN_DOMAIN_SUFFIX` defaults to `"rastisi.ir"`, environment-overridable).
2. `/admin-portal/` becomes the canonical Merchant Admin Portal URL prefix
   (`shop_core/urls.py`); the previous `/admin-panel/` prefix is kept alive
   only as a 302 (not 301 — deliberately not permanent/cacheable)
   backward-compatible redirect to the equivalent `/admin-portal/` path via
   `apps.core.views.admin_panel_compat_redirect`, preserving both sub-path
   and query string. `admin-portal` (alongside the pre-existing
   `admin-panel`) is added to `apps.content.models.RESERVED_SLUGS` so a
   merchant-authored `ContentPage` can never claim either path.

**What this PR deliberately does NOT do.** `resolve_store_for_admin_host`
is new, tested, standalone infrastructure — like
`StoreResolutionMiddleware`'s own `request.store` before it, it is not yet
*consumed* by `apps.dashboard.decorators.staff_required` to enforce "this
request must have arrived via the admin subdomain, not a public storefront
domain." Wiring that enforcement in is the one remaining piece of "public
storefront domains must not expose the merchant admin portal" from the
Phase 1B request. It was deliberately deferred rather than rushed, because
doing it safely requires first migrating every existing multi-Store
dashboard test's Host fixtures (currently generic hosts like
`dash-a.example.com`, chosen before this ADR existed) to real
admin-subdomain-shaped hosts, and deciding how the existing
single-Store `testserver`/`localhost` development compatibility fallback
(`apps.stores.resolution.resolve_compatibility_store`) should interact with
admin-host enforcement — both are separate, sizeable pieces of follow-up
work of their own, tracked in the Phase 1B report's Known Limitations
rather than done under time pressure in the same pass as the schema and
routing changes.

**Alternatives considered.** Deriving the admin host directly from
`Store.slug` with no separate field — rejected: `slug` is
`allow_unicode=True` (Persian slugs are an explicit product requirement),
so it cannot always serve as a DNS label without a second, independent,
ASCII-only field. Making `/admin-panel/` a permanent (301) alias instead of
a temporary compatibility redirect — rejected: a 301 gets cached by
browsers/proxies indefinitely, which would make the old prefix effectively
permanent infrastructure instead of the removable shim it's meant to be.

**Consequences.** Every `reverse("dashboard:...")` call across the
entire codebase and test suite kept working unchanged through the route
rename, since the URL prefix is defined in exactly one place
(`shop_core/urls.py`'s `include("apps.dashboard.urls")`); only the
hardcoded literal path strings (a handful of test assertions and the
login-redirect logic in `apps.dashboard.decorators`/`apps.dashboard.views.admin_login`)
needed updating. The admin-subdomain-only enforcement gap above means that,
as of this PR, a Store's dashboard is still reachable through any Host that
resolves to it via `apps.stores.resolution.resolve_store_for_service`
(including a verified public `StoreDomain`) — `StoreMembership`
authorization (ADR-13's Phase 1/1A work) still fully prevents cross-Store
data access regardless of which Host was used to get there; what remains
open is only "should this Host be allowed to serve the admin portal for
*any* Store at all," not tenant isolation itself.

## ADR-17: Admin-Subdomain Enforcement Closes the ADR-16 Gap via `resolve_store_for_admin_request`, Not by Changing `resolve_store_for_admin_host`

**Context.** ADR-16 shipped `Store.admin_subdomain` and
`resolve_store_for_admin_host(raw_host)` as new, tested, standalone
infrastructure but explicitly did not wire it into
`apps.dashboard.decorators.staff_required`, leaving the dashboard reachable
through any Host that resolved to a Store at all — including a merchant's
public `StoreDomain`. Phase 1C's mandate was to close that gap first,
before any further Product Management work, without breaking the existing
single-Store `testserver`/`localhost` developer-compatibility fallback that
`resolve_compatibility_store()` provides for local development and the bulk
of the test suite.

**Decision.** A new function,
`apps.stores.resolution.resolve_store_for_admin_request(request)`, is the
single call site `staff_required`/`admin_host_required` use. It tries
`resolve_store_for_admin_host(request.get_host())` first; only if that
returns `None` *and* the Host is one of the recognized development hosts
(`testserver`, `localhost`, etc.) does it fall through to
`resolve_store_for_request(request)` (the general public-domain-or-compat
resolver). Any other unresolved Host is a hard `Http404` — never a redirect,
never a fallback guess. `resolve_store_for_admin_host` itself is
unchanged from ADR-16; the new function composes it with the existing
development allowlist rather than teaching the admin-only resolver about
development hosts directly, keeping "what counts as an admin host in
production" and "what the dev/test convenience fallback allows" as two
separately reasoned concerns.

**Consequences.** A request to the dashboard over a Host that is a
verified public `StoreDomain` (but not that Store's `admin_subdomain`) now
404s instead of rendering the dashboard — verified by
`apps/stores/tests/test_admin_host_enforcement.py`. Six existing
multi-Store dashboard test files that previously used arbitrary
`*.example.com`-shaped Hosts (`test_membership_authorization.py`,
`test_catalog_store_isolation.py`, `test_order_store_isolation.py`,
`test_gateway_shipping_store_isolation.py`, `test_admin_superuser_gate.py`,
`test_footer_config.py`) were migrated to set a real `admin_subdomain` and
request against a `*.rastisi.ir`-shaped Host, since a Host that resolves to
*no* Store's admin subdomain now correctly 404s rather than serving the
dashboard by accident. A related, previously-latent production bug was
found and fixed in the same pass: `apps.core.context_processors.shop_settings`,
`apps.catalog.context_processors.nav_categories`, and
`apps.content.context_processors.footer_settings` all called into
`ShopSettings.load()`/`FooterSettings.load()`/`resolve_store_for_service()`
unconditionally, which raised an unhandled `StoreResolutionError` — and
therefore a 500, not a 404 — whenever Django's own 404 handler tried to
render a page for an unresolvable Host with two or more Stores in the
database. All three now catch `StoreResolutionError` (and the relevant
not-provisioned error) and return an empty context, so an unresolvable Host
reliably 404s end-to-end instead of 500ing on whichever template happens to
render first.

**Alternatives considered.** Teaching `resolve_store_for_admin_host` itself
to accept development hosts — rejected: it would blur "the shape of a real
admin host" with "what a developer's machine is allowed to pretend," and
every non-admin caller of `resolve_store_for_admin_host` (there are none
today, but the function is public API) would inherit the dev-only
behavior. Redirecting an unresolvable admin Host to `catalog:home` instead
of 404ing — rejected: it would need to resolve *some* Store to build that
redirect, which is exactly the ambiguity a fail-closed design must refuse
to guess at; a wrong-membership Host still redirects to `catalog:home`
(the user has a Store to go back to), but an unresolvable Host has none.

## ADR-18: Variant-Specific Product Images Are `ProductImage.variant` (Nullable FK, `SET_NULL`), Not a Separate Model

**Context.** Phase 1C's Product Management scope required merchants to be
able to associate specific gallery images with a specific `ProductVariant`
(e.g., a red T-shirt's photos distinct from the blue one's), while the
existing `ProductImage` gallery (product-level, ordered, one designated
cover) had no notion of variants at all. The prototype under review shows
per-variant image swapping on the storefront product page.

**Decision.** `ProductImage` gains one new field: `variant = ForeignKey
("ProductVariant", null=True, blank=True, on_delete=SET_NULL,
related_name="images")`. A blank `variant` means "general product image,
shown regardless of selected variant" (the existing, pre-Phase-1C
behavior); a set `variant` means "specific to this variant only."
`ProductImage.clean()` rejects a `variant` that does not belong to
`self.product` — the same defense-in-depth pattern `Product.clean()`
already uses for `brand`/`category`/`vendor`. `ProductVariant.display_image`
is a new convenience property: the variant's own first image if one
exists, otherwise the product's `cover_image` — so every code path that
wants "the one image to show for this variant" (the dashboard variant
table, and any future storefront variant-switcher) has a single fallback
rule to depend on, rather than re-implementing the "does this variant have
its own image?" check at every call site. No new upload path exists for
variant images: merchants upload into the same product-level gallery as
before and then assign an existing image to a variant via a
`<select>` per image (`dashboard:product-image-variant`), rather than a
separate per-variant upload form — reusing the existing validated/resized
upload pipeline (`apps.catalog.services.product_image_service`) instead of
duplicating it.

**Consequences.** Deleting a `ProductVariant` never deletes its images —
`SET_NULL` demotes them back to general product images automatically at
the database level, with no application code needed to "rescue" them; this
was a deliberate choice over `CASCADE`, since a merchant deleting one color
variant should not silently lose photography that may still be reusable.
Because `related_name="images"` is added to `ProductVariant` (mirroring
`Product.images`), `variant.images.all()` and `product.images.all()`
coexist without collision — a `ProductImage` always belongs to exactly one
`Product` (unchanged) and *optionally* to one of that same `Product`'s
`ProductVariant`s.

**What this PR deliberately does NOT do.** The storefront product-detail
page does not yet swap displayed images when a shopper selects a variant —
this phase only builds the admin-side association (upload → assign →
persist, all tenant/product-isolated and tested) and the data model
(`display_image`) a storefront feature would consume. Wiring
`display_image` into the actual storefront variant-selector UI is
out of scope for Phase 1C and is recorded as a remaining gap in the Phase
1C report.

**Alternatives considered.** A separate `VariantImage` model (own table,
own upload form) — rejected: it would duplicate the entire validated
upload/resize/thumbnail pipeline in `product_image_service.py` for no
behavioral gain, since "an image that may or may not belong to a variant"
is exactly what a nullable FK expresses. Storing multiple images per
variant via a many-to-many instead of each `ProductImage` pointing at one
variant — rejected: the prototype and the existing product gallery both
model "one image, one owner, explicit order/cover flag"; a M2M would need
its own through-model to carry per-pair ordering, which is exactly the
`ProductImage.order`/`is_cover` shape already in place, just duplicated.

---

## ADR-19: Descriptive Attributes and Variant-Generating Options Are Separate Models That Optionally Share One `Attribute` Definition

**Context.** Phase 1D requires two behaviorally distinct concepts the prompt
itself insists must not be merged: a *descriptive attribute* ("Material:
Cotton") that describes a product but never creates a purchasable row, and
a *variant-generating option* ("Color: Green/Blue/Yellow") whose values are
combined into `ProductVariant` rows. The existing codebase already has one
single-axis, ad-hoc variant mechanism (`ProductVariant.attribute`/`.value`,
free-text CharFields, no shared definition, no descriptive-attribute
concept at all) — extending it in place to also mean "the reusable
Store-wide catalog of attribute definitions" would conflate a per-product
label with a Store-owned, reusable schema.

**Decision.** A new Store-owned `Attribute` model is the single reusable
definition: name, code, data type, display type, unit, and boolean flags
including `is_variant_axis` (whether this attribute is *eligible* to
generate variants — eligibility, not a commitment; a Store can define
"Material" once and use it descriptively on some products while never
using it as a variant axis, and use "Color" both descriptively on
non-variable products and as a variant axis on others). Two separate
product-scoped models consume it for the two distinct behaviors:
`ProductAttributeValue` (a Product's descriptive assignment: one row per
product+attribute for scalar types, multiple rows for multi-select) and
`ProductOption` (a Product's variant-generating axis — `position`-ordered,
own `ProductOptionValue` children). Both `ProductAttributeValue.attribute`
and `ProductOption.attribute` are optional FKs to the same `Attribute`
row — a merchant *may* pick "Color" from the shared definition, or a
`ProductOption` may be created with only a free-text `label` and no linked
`Attribute` at all (matching the prototype's own "custom variant attribute"
flow, where a merchant types an arbitrary axis name with no schema
behind it).

**Consequences.** The existing single-axis `ProductVariant.attribute`/
`.value` fields are *not* removed or migrated — see ADR-20's "Consequences"
for why they are repurposed as generated display fields rather than
identity. A Store's `Attribute` catalog and a specific Product's
`ProductOption` axes can diverge in the ordinary case (most attributes are
descriptive-only, never linked to any `ProductOption`), which is the
correct shape: not every attribute is a variant axis, and the eligibility
flag exists precisely so the admin UI can filter "attributes worth
offering as a variant axis" without a second registry.

**Alternatives considered.** One unified `Attribute`-with-variant-behavior
model, distinguishing descriptive vs. variant-generating only by whether
any `ProductOption` row references it — rejected: it would make "is this
attribute currently a variant axis" a derived, per-product fact instead of
a Store-level eligibility declaration, so the admin attribute-list page
could never show "eligible for variants" as a stable column without an
expensive per-row subquery, and a merchant could not mark an attribute
variant-*ineligible* (e.g. "Warranty" should never be offered as an axis)
without it being enforced anywhere. Two entirely disconnected schemas (no
shared `Attribute` at all, `ProductOption.label` and
`ProductAttributeValue`'s type both free-text per product) — rejected: it
would mean re-typing "Color" with a fresh, unrelated spelling on every
product, with no Store-wide filterable/searchable/comparable attribute
catalog at all, which the prompt's Attribute Definitions section (§7)
explicitly requires.

## ADR-20: Stable Variant Combination Identity Is a `VariantOptionValue` Through-Table Plus a Derived `combination_key`, Not the Legacy `attribute`/`value` Strings

**Context.** `ProductVariant.attribute`/`.value` (pre-existing) are
free-text `CharField`s with a `normalized_attribute`/`normalized_value`
uniqueness constraint — adequate for one axis, but the prompt explicitly
forbids using a display string as multi-axis identity ("Green / M" must
not be the source of truth), since renaming a value or reordering axes
must never be mistaken for a new combination.

**Decision.** A new `VariantOptionValue` model is the real, normalized
per-axis relation: one row per `(ProductVariant, ProductOption,
ProductOptionValue)`, so a three-axis variant has exactly three rows, each
pointing at an immutable `ProductOptionValue` primary key — renaming a
value's label or an option's label changes no `VariantOptionValue` row at
all. `UniqueConstraint(variant, option)` guarantees a variant has at most
one value per axis; `UniqueConstraint(variant, option_value)` is a second,
redundant safety net. Because comparing sets of FK rows on every
generation/reconciliation pass is not cheap and cannot be expressed as a
single database uniqueness constraint, `ProductVariant` also gets a
derived `combination_key`: a deterministic string built by the generation
service from the *sorted* `ProductOptionValue` primary keys of a
combination (e.g. `"14-27-31"` — sorted so that submission order of
`Color=Green, Size=M` vs. `Size=M, Color=Green` produce the identical
key). `UniqueConstraint(product, combination_key, condition=~Q
(combination_key=""))` (the same `~Q(field="")`-guarded-blank pattern
`ProductVariant.sku`'s own uniqueness constraint already uses) then gives
duplicate-combination prevention a real database constraint, not just
service-layer diligence. `combination_key` is written *only* by the
generation service, alongside the `VariantOptionValue` rows it is derived
from — it is never a directly user-editable field.

**Consequences.** Legacy single-axis variants (created via the
pre-existing `bulk_create_variants`/`create_variant` service, unchanged by
this phase) simply never get a `combination_key` — it stays `""`, exempt
from the new constraint, and the new generation/reconciliation engine
explicitly excludes `combination_key=""` rows from its own bookkeeping
(`ProductVariant.objects.exclude(combination_key="")`), so a Product using
the legacy mechanism is completely invisible to — and completely
unaffected by — the new engine. `ProductVariant.attribute`/`.value`
survive as generated *display* fields for multi-axis variants too
(populated by joining each axis's/value's label, e.g. `attribute="رنگ /
سایز"`, `value="سبز / M"`) purely so every existing template, the order
snapshot fields, and `__str__` keep working unmodified — but they carry no
identity weight for multi-axis variants; only `combination_key` and the
`VariantOptionValue` rows do. A Product cannot mix the legacy single-axis
flow and the new `ProductOption` flow at the same time — `add_product_
option` refuses to create the first axis while any `combination_key=""`
variant still exists on that Product, so a merchant must first clear
legacy variants before opting into multi-axis (or vice versa is simply
never necessary, since generation never touches legacy rows). This is a
deliberate simplification recorded here, not a silent gap: mixed-mode
products (some variants legacy, some multi-axis, on the same Product) are
out of scope.

**Alternatives considered.** Hashing the combination with a cryptographic
hash (e.g. SHA-1 of sorted IDs) instead of a plain sorted join — rejected:
a plain sorted join of small integer IDs is already short, human-
debuggable in the Django admin/shell, and collision-free by construction
(distinct ID sets always sort to distinct strings), so a hash would only
add opacity with no benefit. Relying on `VariantOptionValue` rows alone
(a `GROUP BY`/`HAVING` query comparing per-variant ID sets) instead of a
denormalized `combination_key` column — rejected: the reconciliation
service runs a "does this desired combination already exist" lookup once
per combination on every `generate_variants()` call (up to the
performance test's 125 combinations), and a single indexed string-equality
lookup is a straightforward, obviously-correct way to keep that lookup a
single query instead of N relational comparisons.

## ADR-21: Variant Reconciliation Never Hard-Deletes — Obsolete Combinations Are Marked, Never Removed, and Axis Removal Requires an Explicit Regeneration Pass

**Context.** Changing a Product's options after variants already exist —
adding a value, removing a value, removing an entire axis, renaming,
reordering — can each change which combinations *should* exist, while
existing `ProductVariant` rows may already carry real SKUs, prices,
inventory, images, and (via `OrderItem`) irreversible historical sales
records. The prompt is explicit that guessing which data to keep, or
silently merging/deleting, is unacceptable.

**Decision.** `generate_variants(product)` is the only place combinations
are ever created or retired, and it follows one rule for every scenario:
compare the *desired* set of combinations (the Cartesian product of
currently-active axes × currently-active values) against the *existing*
set (`ProductVariant` rows with a non-blank `combination_key` on this
Product); a combination present in both is preserved byte-for-byte (same
primary key, SKU, price, `compare_at_price`, `cost`, stock, images,
`created_at` — nothing about the row is touched beyond, if needed,
clearing an `is_obsolete` flag); a combination only in *desired* gets a
newly created `ProductVariant`; a combination only in *existing* is marked
`is_obsolete=True` and `is_active=False` — **never deleted**. `is_obsolete`
is a distinct field from the pre-existing `is_active` specifically so the
admin UI can tell "a merchant turned this off" apart from "this
combination no longer matches the Product's current options" — the latter
is reported back to the merchant as an explicit, named list
(`GenerationResult.obsoleted`) after every regeneration, not silently
absorbed. Removing an axis is not a separate code path: a merchant
deactivates a `ProductOption` (`is_active=False`) — which by itself changes
nothing — and then must explicitly re-run `generate_variants()`, which
naturally treats every combination that included that axis's values as no
longer desired and marks them obsolete, following the exact same rule as
removing one value. This is the prompt's own suggested safe policy ("block
destructive axis removal until the merchant confirms... document a
deterministic policy") implemented as "nothing destructive happens until
an explicit regeneration action, and that action's only behavior is mark-
obsolete, never delete."

**Consequences.** Renaming a `ProductOptionValue.label` or a
`ProductOption.label` touches no `combination_key` (ADR-20) and is
therefore invisible to reconciliation — the desired/existing comparison
is keyed on primary keys, not labels, so a rename can never look like "this
combination no longer exists, create a new one." Reordering `ProductOption
.position` changes which order `generate_variants()` iterates axes in
(affecting new variants' generated `attribute`/`value` display strings and
every variant's recomputed `display_order` — see ADR-20's Alternatives),
but never changes any `combination_key`, since the key is built from
*sorted* value IDs, independent of axis order. An obsoleted variant that
was the Product's `is_default` variant is never left dangling: `generate_
variants()` always ends by calling the same default-selection routine
`add_product_image`'s cover-image "steal the flag" pattern uses — if no
active, non-obsolete variant currently holds `is_default=True`, the first
one (by the freshly recomputed `display_order`) is promoted automatically,
so a Product with any active variant always has exactly one default,
enforced by `UniqueConstraint(product, condition=Q(is_default=True))` at
the database layer too. Because obsolete variants are never deleted,
`OrderItem.variant` (a `PROTECT`/`SET_NULL` FK depending on the pre-
existing order-history design — unchanged by this phase) is never left
pointing at a vanished row, and a merchant who removed a value by mistake
can simply re-add it: the next `generate_variants()` run finds the old
`ProductOptionValue`/combination still exists (values are soft-deactivated,
not hard-deleted either — see §8/§14) and clears `is_obsolete` on the
original row instead of creating a duplicate.

**Alternatives considered.** Hard-deleting obsolete variants with no order
history — rejected: even a variant with zero orders may still hold a
merchant-uploaded image or a manually-set price the merchant would
reasonably expect to survive a value being removed and re-added a minute
later; "no orders reference it yet" is not the same guarantee as "this
data is safe to discard," and the mark-obsolete rule needs no special case
for that distinction, which is itself a simplicity win. Automatically
merging an axis-removal's collapsed combinations (e.g. "Color+Size"
becoming "Color only" summing the removed Sizes' stock into the surviving
Color row) — rejected: the prompt explicitly prohibits silently merging
inventory, SKU, pricing, or media, and no business rule for *which* of N
now-redundant rows' SKU/price/image should "win" can be inferred safely
without asking the merchant, which this phase's UI does not yet build (see
Known Limitations in the Phase 1D report) — today, axis removal always
produces obsoleted rows the merchant must manually review, never an
automatic merge.

---

## ADR-22: Industry Templates Are Platform-Owned and Read-Only; Installation Deep-Copies Into Store-Owned Records, Never Links to the Shared Template

**Context.** Phase 1E needs a library of reusable per-industry catalog
structures (categories, attributes, values, category→attribute mappings,
recommended variant options) that a merchant can install into their Store
to avoid designing a catalog from scratch. The obvious risk: if a Store's
catalog structure is represented as *live references* into shared
`IndustryTemplate` rows, any future edit to the template (fixing a typo,
adding a value) could silently ripple into every Store that installed it,
and a Store's own customization (renaming a category, disabling an
optional attribute) would either be impossible to express or would corrupt
the shared template for every other Store.

**Decision.** `IndustryTemplate` and its children
(`TemplateCategory`, `TemplateAttribute`, `TemplateAttributeValue`,
`TemplateCategoryAttributeMapping`, `TemplateRecommendedOption`) are
platform-owned, have no `store` FK anywhere in the chain, and are never
writable through any Store-scoped/`StoreMembership`-gated code path — only
Django admin (superuser) or a management command touches them (§26).
`apps.catalog.services.industry_template_service.install_industry_template
(store, industry_template)` performs a **deep copy**: it creates genuinely
new, Store-owned `Category`, `Attribute`, `AttributeValue`,
`CategoryAttributeSchema`, and `CategoryRecommendedOption` rows, one for
one, from the template's data. After installation, a Store's catalog rows
have **no live FK back to the template rows that produced them** for
day-to-day operation — the only connection is a nullable, purely
informational traceability FK (`Category.source_template_category`,
`Attribute.source_template_attribute`, both `SET_NULL` on template
deletion) plus one `StoreIndustryInstallation` row recording which
template (and which version) a Store installed and when. Editing a
`Category`, `Attribute`, or `CategoryAttributeSchema` row after
installation is *ordinary Store-owned catalog editing* — the exact same
code path (`attribute_service`, the Category views) a merchant who never
installed any template uses. There is no special "templated" mode a
Category can be in.

**Consequences.** A future edit to a platform `IndustryTemplate` can never
affect an already-installed Store, by construction — there is no
mechanism by which it could, since nothing in a Store's catalog holds a
live reference to template data at query time. This also means Phase 1E
does not need to build any "protect template-derived fields from merchant
edits" enforcement: a merchant can rename, reorder, archive, or add to
their installed categories/attributes exactly as freely as anything they
built by hand, because after installation there is no meaningful
distinction left to protect. The cost of this choice is real duplication:
ten Stores installing the same "Clothing" template each get their own
full copy of every category/attribute/value row — accepted deliberately,
since SQLite/Postgres row counts at this scale are not a concern, and the
alternative (shared/linked records with an override layer) is
categorically more complex to build correctly and query efficiently.
`install_industry_template` also **reuses** an existing Store `Attribute`
by `code` instead of creating a duplicate if one already exists with a
matching code (`get_or_create`) — this is the one place a merchant's
*pre-existing* catalog data intentionally interacts with installation, and
it only ever reuses, never overwrites, an existing row's other fields.

**Alternatives considered.** Live FK from Store `Category` to
`TemplateCategory` with a per-Store override table layered on top —
rejected: correctly resolving "effective" values through an override layer
at every read (product form load, category list, schema resolution) adds
real query complexity for a benefit (saving template-update propagation)
this phase's own §23 (versioning) explicitly says must *not* happen
automatically anyway — the override layer would exist only to prevent a
behavior the product spec says should never occur, making it pure
unrewarded complexity. A "linked copy with detach-on-edit" hybrid
(reference the template until the merchant's first edit, then fork) —
rejected as needless statefulness: every code path that touches a
Category/Attribute would need to first check "is this still linked or has
it forked," for a benefit no requirement asks for.

## ADR-23: Category Attribute Schema Resolution — Direct Mappings Always Win Over Inherited Ones; Inheritance Is Opt-Out Per Mapping, Not Per Category

**Context.** Phase 1E's Category hierarchy (pre-existing, two levels:
parent/child `Category` rows) needs Attribute schema *inheritance* — an
Attribute assigned to "Clothing" should apply to "Clothing → T-Shirts" —
while guaranteeing the Product form is handed one normalized list with no
duplicate Attribute entries when the same Attribute is reachable through
more than one path (assigned directly on the child *and* inherited from
the parent).

**Decision.** Each `CategoryAttributeSchema` row (the mapping of one
`Attribute` onto one `Category`) carries its own
`is_inherited_by_children` boolean (default `True`) — inheritance is a
property of the *mapping*, not a category-wide switch, so a merchant can
mark one specific Attribute assignment as "just for this category, don't
propagate to children" without affecting any other mapping on the same
category. `apps.catalog.services.category_schema_service.resolve_category_schema
(category)` walks from `category` up through every ancestor
(`category.parent`, `category.parent.parent`, …), collecting: (a) *every*
`CategoryAttributeSchema` row directly on `category` itself, regardless of
that row's own `is_inherited_by_children` value (a category always uses
its own direct mappings — that flag only ever governs propagation
*downward* to children, never affects the category the row lives on), and
(b) for each ancestor, only the ancestor's rows where
`is_inherited_by_children=True`. When the same `Attribute` appears from
more than one source (e.g. a direct mapping on the child *and* an
inherited one from the parent), **the most specific mapping wins** — the
child's own direct row (if any) is used verbatim (its `group`/`order`/
`is_required`/help text/etc.), and the ancestor's row for that same
Attribute is discarded entirely rather than merged field-by-field. Direct
mappings are looked up first (closest ancestor — the category itself —
wins over anything further up), so a two-level-removed grandparent's
mapping loses to a parent's mapping for the same Attribute, which in turn
loses to the category's own.

**Consequences.** The Product form, `build_product_specification`, and
publish validation all consume the single list `resolve_category_schema`
returns and never need to reason about inheritance themselves — each
`ResolvedSchemaEntry` in that list already carries a resolved
`is_required`/`group`/`display_order`/etc. and a `source_category`
(which category in the chain the winning mapping actually came from) plus
an `is_inherited` boolean, purely for UI display ("این ویژگی از «پوشاک»
به ارث رسیده" badges) — never for re-deriving behavior. A merchant who
wants a child category to *not* show a parent's optional Attribute cannot
do so by editing the child (there is no child-side "hide this inherited
Attribute" row in this phase) — only by editing the parent mapping's
`is_inherited_by_children` flag directly (which affects *all* of that
parent's children uniformly). This is a deliberate, named scope
reduction — a proper per-child "hide this one inherited Attribute"
override is listed as a remaining gap in the Phase 1E report rather than
built now, since it would require a third kind of record (a child-level
suppression row) whose interaction with future re-installation/versioning
was not resolvable within this phase's time.

**Alternatives considered.** Category-wide `inherits_from_parent` boolean
(all-or-nothing per category) — rejected: too coarse for the concrete
prompt example (a Store wants "Country of Manufacture" inherited
everywhere but "Season" only on seasonal subcategories), which needs
per-mapping control. Field-by-field merge of parent and child mappings for
the same Attribute (e.g. take the child's `group` but the parent's
`is_required`) — rejected: unpredictable and hard to explain to a
merchant ("why is this field required here but its help text is from
somewhere else?"); "closest mapping wins outright" is a rule a UI badge
can state in one sentence.

## ADR-24: Product Attribute Values Are Never Deleted on Category Change — They Become Invisible (Not in the New Schema) Until an Explicit Cleanup Action Is Taken

**Context.** Changing a Product's Category changes which
`CategoryAttributeSchema` entries apply to it. A `ProductAttributeValue`
row that was valid under the old Category (e.g. "Sleeve Type: Long" on a
T-Shirt) may not correspond to any Attribute in the new Category's schema
(e.g. after moving the Product to "Shoes"). The prompt is explicit:
existing data must never be silently deleted, and any destructive cleanup
needs an explicit merchant confirmation.

**Decision.** No new field or flag is added to `ProductAttributeValue`
for this. Changing `Product.category` is an ordinary field update — it
does not trigger any automatic deletion, migration, or mutation of
existing `ProductAttributeValue` rows at all. Instead,
`apps.catalog.services.category_schema_service.orphaned_product_attribute_values
(product)` computes, on demand (at product-edit-page render time and
before publish), the set of a Product's existing `ProductAttributeValue`
rows whose `attribute` is *not* present in `resolve_category_schema
(product.category)`'s current result — these are "orphaned," not
deleted, not hidden from the database, simply no longer part of what the
current Category's schema asks for. `build_product_specification`
(§ "Product Specifications") only ever renders schema-membership-filtered
values, so an orphaned value never appears in specification output or the
active product-edit form automatically — but it still physically exists
and is trivially recoverable (e.g. switching the Category back). Deleting
an orphaned value is only ever a distinct, explicit action
(`cleanup_orphaned_attribute_values(product)`) the product-edit UI offers
behind its own confirmation, never something a Category-change save does
by itself.

**Consequences.** A Category change is always non-destructive and instant
— there is no "are you sure, this might delete data" interstitial on the
save action itself, because the save action provably cannot delete
anything. The product-edit page, after a Category change, shows a
distinct "این مقادیر دیگر با دسته‌بندی فعلی مطابقت ندارند" (these values
no longer match the current category) panel listing exactly the orphaned
values with a manual "پاک‌سازی" (cleanup) button — the warning the prompt
requires exists at the point of *consequence* (viewing the product after
the change) rather than *action* (the change itself), which is simpler to
reason about and impossible to accidentally skip past (unlike a
confirm-dialog a merchant might reflexively click through). Publish
validation (§ "Draft and Publish Validation") only checks *required*
attributes of the *current* schema — an orphaned value from the old
Category, being outside the current schema entirely, is never counted
toward or against publish-readiness either way.

**Alternatives considered.** A `ProductAttributeValue.is_orphaned` boolean
flag, set automatically on Category change — rejected: it would need to be
kept in sync any time *either* the Product's Category *or* the Category's
own schema changes (e.g. a merchant removes an Attribute mapping from a
Category entirely, orphaning it for every Product in that Category at
once) — computing it on demand from the current schema is simpler,
always-correct by construction, and never goes stale. Hard-blocking a
Category change until the merchant manually resolves every orphaned value
first — rejected: the prompt explicitly asks that old values be
*preservable*, not that a Category change be blocked by pre-existing data,
and forcing resolution up front would make Category changes needlessly
disruptive for what is very often a harmless, later-cleaned-up situation.

## ADR-25: Industry Template Versions Are Immutable Snapshots; Existing Installations Never Auto-Update, and No Update-Application UI Ships This Phase

**Context.** Industry templates will need to evolve over time (a new
recommended Attribute, a corrected category name) without ever silently
mutating a Store's already-installed, possibly-customized catalog — the
prompt's §23 explicitly forbids automatic overwrites of merchant changes.

**Decision.** `IndustryTemplate.version` is a plain `PositiveIntegerField`,
and `(slug, version)` is unique — a "new version" of an industry is
authored as an **entirely new `IndustryTemplate` row** (new PK, new full
tree of `TemplateCategory`/`TemplateAttribute`/etc.), never an in-place
edit of an existing template's children. This makes every
`IndustryTemplate` row, once created, an immutable historical snapshot by
construction — there is no code path in this phase that mutates a
`TemplateCategory`/`TemplateAttribute`/etc. row after creation (the seed
management command, per ADR-below-on-idempotency, only ever creates
missing rows, never edits existing ones — see the Phase 1E report §5).
`StoreIndustryInstallation.installed_version` records exactly which
version a Store installed. A Store may only ever install **one**
`IndustryTemplate`, period, for its entire lifetime — see the Phase 1E
report's Industry Change Policy: `install_industry_template` rejects any
call once a `StoreIndustryInstallation` row already exists for that Store
(enforced by service-level check plus a `UniqueConstraint(fields=["store"])`
as a database-level backstop), regardless of whether the new call targets
the same industry, a newer version of it, or an entirely different
industry. This is deliberately the strictest of the prompt's own
explicitly-acceptable §22 options ("Block change after installation"),
chosen because it requires no new merge/reconciliation logic at all — the
one thing every other listed option (additional-template-without-deleting,
required-migration-workflow, empty-catalog-required) would need.

**Consequences.** "Existing Stores keep their copied records; new Stores
receive the latest template" (the prompt's own preferred default in §23)
holds trivially: a new `IndustryTemplate` version is simply a new row that
future installations pick, and no existing `StoreIndustryInstallation` or
the Store-owned rows it produced are ever touched by that new row's
existence. No "review available updates and apply them selectively" UI is
built this phase — the data model (`installed_version` vs. the current
max version for that `slug` being queryable) supports building one later
without a schema change, and this gap is named explicitly in the Phase 1E
report rather than left ambiguous. A Store that installs the wrong
industry, or whose business changes industries entirely, has no supported
in-product path to switch in this phase — a platform operator would need
to intervene directly (e.g. via Django admin) — a real, named limitation,
not an oversight.

**Alternatives considered.** Mutable templates with a `version` field that
increments in place on edit — rejected: it reintroduces exactly the
"does an edit affect already-installed Stores" ambiguity ADR-22 exists to
foreclose; an editor could all too easily "fix a typo" on a live template
row believing it only affects future installs, when in a mutable-row
design the meaning of "already installed" vs. "the template" is not
statically distinguishable without extremely careful, easy-to-get-wrong
discipline. Allowing a Store to install additional templates alongside its
first (union of multiple industries' structures) — rejected for this
phase specifically because merging two industries' category trees and
attribute schemas without collision (two industries both wanting a
"Color" attribute with different `data_type`s, for instance) is a real
design problem the prompt itself does not resolve, and the single-
installation-only policy sidesteps it entirely without losing any
capability a Store lacks another way (a merchant can always build
additional categories/attributes by hand after installing their one
template — nothing is blocked, only *automatic* multi-industry merging
is).

---

## ADR-26: Industry Template Quality Is a Structured, Reusable Validation Service — Not a Vanity Score

**Context.** Phase 1F must scale the Industry Template catalog from 10 to
30 (and eventually further), which makes it realistic that a future
template author writes something structurally broken (a dangling parent
reference, a required Attribute with no obtainable choice Values) or
merely shallow (a Category with no Attribute mappings at all). The prompt
explicitly warns against "a fake quality score" that could make severe
errors invisible behind a high aggregate number.

**Decision.** `apps.catalog.services.template_validation_service.validate_industry_template(template)`
returns a structured `TemplateValidationResult` dataclass: a list of
typed `ValidationIssue` entries (`code`, `severity` — `error`/`warning`/
`info`, `message`, `model_type`, `identifier`, `remediation`), a
`metrics` dict (category/attribute/value/mapping/recommendation counts),
and a derived `readiness` recommendation. **Any `error`-severity issue
unconditionally blocks `production_ready`**, regardless of how many other
dimensions pass — there is no numeric score that can average away a
structural defect. A secondary, explicitly-documented `quality_score`
(0–100, weighted: structure 25 / attribute completeness 20 / schema
quality 20 / variant recommendations 15 / merchant usefulness 10 /
installability 10 — see `QUALITY_SCORE_WEIGHTS` in the service module) is
computed *only* from `warning`/`info`-level findings once zero errors are
present, and is advisory metadata, never a gate — a template with 0
errors and a low score is still eligible for `production_ready` review
if a platform operator explicitly promotes it; the score is a triage aid
for operators comparing templates, not an automated pass/fail threshold
on its own.

**Consequences.** The same service function is called identically by the
`validate_industry_templates` management command, the Django admin
action, the seed command (to set initial `readiness`), and every test —
one source of truth for "what makes a template good," matching the
prompt's explicit requirement that validation logic must not live inside
a view or command. Adding a new quality rule means adding one function to
`_STRUCTURAL_CHECKS`/`_CONTENT_CHECKS` in the service module and it is
immediately live everywhere.

**Alternatives considered.** A single opaque 0–100 score as the only
output — rejected outright per the prompt's explicit prohibition and
because it cannot express "which specific thing is wrong," which is what
a template author actually needs to fix it. Silent logging-only
validation with no persisted/queryable result — rejected because
platform operators need to inspect *why* a template is not
`production_ready` without re-running validation by hand each time (see
ADR context in §11 of the Phase 1F report for the persistence policy).

## ADR-27: Template Versioning Stays on `IndustryTemplate.(slug, version)` — No Separate Version-Family Model

**Context.** Phase 1F requires representing "Industry family identity,
multiple versions, one version installed in a Store, a newer version
available, comparison between versions" — the prompt suggests a
`IndustryTemplate` → `IndustryTemplateVersion` split as one *possible*
shape, but explicitly permits keeping the existing architecture if it
"already supports this safely."

**Decision.** Phase 1E's `IndustryTemplate` model, with `slug` as the
family identity and `version` as a per-family incrementing integer
(`UniqueConstraint(slug, version)`), already satisfies every requirement
above without a new model: the "family" is simply
`IndustryTemplate.objects.filter(slug=slug)`, "current recommended
version for new installs" is computed on demand (not stored) as
`IndustryTemplate.objects.filter(slug=slug, readiness=PRODUCTION_READY).order_by("-version").first()`
(`latest_production_version(slug)` in `template_validation_service`), and
"a newer version is available for an installed Store" is
`installation.industry_template.version < latest_production_version(installation.industry_template.slug).version`.
No new model was introduced; `IndustryTemplate` gains two new fields
instead: `readiness` (the lifecycle state — §ADR-26/28) and
`content_fingerprint` (a cached, deterministic content hash — see below).

**Consequences.** Zero migration risk to the 10 existing Phase 1E
templates or their installations beyond two new nullable/defaulted
columns — no data restructuring, no re-keying of any child row's FK.
"Current recommended version" being *computed*, not stored, means there
is no mutable-flag invariant to maintain (no risk of two rows both
claiming `is_recommended=True` for one family) — a `production_ready`
template simply is or is not the highest-versioned one in its family
that has reached that state, evaluated fresh on every read. A template's
`content_fingerprint` (`apps.catalog.services.template_validation_service.compute_template_fingerprint`)
is a SHA-256 over a canonical JSON structure built entirely from stable
identifiers (`slug`/`code`/labels/ordering/flags) — explicitly excluding
every database primary key, `created_at`, and `updated_at` — so two
`IndustryTemplate` rows seeded with byte-identical content always fingerprint
identically regardless of DB insert order, and re-running the seed
command against unchanged data never appears to "drift." The fingerprint
is computed once (at validation time, cached on the `IndustryTemplate`
row) rather than on every read, since template child rows are immutable
after creation (ADR-25) — there is no code path that could make a cached
fingerprint stale without also creating a *new* `IndustryTemplate` row
(which computes its own fresh fingerprint).

**Alternatives considered.** A dedicated `IndustryTemplateVersion` model
wrapping a stable `IndustryTemplate` family row — rejected for this phase
as the disruptive redesign the prompt explicitly permits avoiding: it
would require re-pointing every one of `IndustryTemplateCategory`/
`IndustryTemplateAttribute`/etc.'s `industry_template` FK, plus a backfill
migration, for a capability (family-vs-version distinction) the existing
`(slug, version)` compound key already provides without it. If a future
phase needs first-class "family" metadata that varies independently of
any specific version (e.g., a family-level icon that should not require
a new version row to change), that would be the concrete trigger to
revisit this decision — not before.

## ADR-28: Store Customization Detection Compares Live Fields Against the Immutable Source Template — No Snapshot Table

**Context.** The safe-update workflow (ADR-29) must never silently
overwrite a value a merchant deliberately changed after installing a
template. Detecting "has this Store-owned record been customized"
normally requires either an explicit dirty flag maintained on every write
path, or a stored snapshot of the record's state at install time to diff
against.

**Decision.** Because `IndustryTemplate*` rows are immutable once created
(ADR-25/27), the *source template row itself* already **is** the
install-time snapshot — there is no need to copy it a second time into a
separate snapshot table. `apps.catalog.services.template_customization_service`
detects customization by directly comparing each Store-owned record's
current field values against its `source_template_*` FK target's current
field values: `is_category_customized(category)` compares `name`/`icon`/
parent-identity against `category.source_template_category`;
`is_attribute_customized(attribute)` compares `label`/`data_type`/
`display_type`/`unit`/`is_variant_axis` against
`attribute.source_template_attribute`; `is_schema_entry_customized(entry)`
compares `group`/`is_required`/the three override flags/`help_text`/
`placeholder` against `entry.source_template_mapping`. A record with no
`source_template_*` FK (merchant-created from scratch, or installed
before Phase 1F added a given traceability FK) is always treated as
customized/merchant-owned — never eligible for silent update overwrite,
the conservative default the prompt requires. `AttributeValue` gained a
new `source_template_value` FK (mirroring `Category`/`Attribute`'s
existing pattern) specifically so *value-level* customization (a
merchant renaming or deleting a template-provided choice value) is
detectable the same way; Phase 1E installations predate this FK and are
`NULL` on it, so their existing `AttributeValue` rows are conservatively
treated as customized by the same "no source FK means owned" rule above.

**Consequences.** No new snapshot storage, no risk of a snapshot silently
drifting out of sync with what was "actually installed," and detection
logic automatically improves for future installations as more
`source_template_*` FKs are added, with old installations safely
defaulting to "assume customized" rather than "assume safe to overwrite."
The cost: a customization check requires a live read of the source
template row (cheap — `IndustryTemplate*` rows are small, and the update
planning service prefetches them in bulk, not per-record).

**Alternatives considered.** A dirty-bit (`is_customized` boolean) set by
every mutating service call that touches an installed record — rejected:
it requires disciplined maintenance across every future write path
touching `Category`/`Attribute`/`CategoryAttributeSchema` (including
Django admin edits, which bypass service functions entirely), and a
missed call silently mis-flags a customized record as pristine — exactly
the "silently overwrite merchant customization" failure the prompt
prohibits. A full point-in-time snapshot copy at install time — rejected
as redundant, since the immutable source template already serves that
role at zero extra storage cost.

## ADR-29: Template Updates Default to Additive-Only Auto-Apply; Everything Else Requires Explicit Merchant Review, Nothing Is Ever Auto-Applied Destructively

**Context.** The prompt's §19 draws a three-way line: changes safe to
apply automatically, changes requiring merchant review, and changes that
must never be applied automatically. Phase 1F must implement a real,
transactional update-application path that respects this line without
degenerating into "sync everything" (which would silently clobber
customization) or "do nothing" (which would make the whole feature a
placeholder).

**Decision.** `apps.catalog.services.template_update_service.plan_template_update(installation, target_template)`
classifies every diff entry from `compare_template_versions` (ADR-27's
comparison service) into exactly one bucket:

* **`safe_additive`** — a new template Category/Attribute/Value/mapping/
  recommendation with no Store-owned counterpart yet. These are
  auto-selected by default in the plan and applied by
  `apply_template_update` **only if the merchant does not deselect them**
  — the merchant still confirms the batch, but no individual review is
  required per item, matching the prompt's "Add a new optional Attribute"
  example category exactly.
* **`review_required`** — a changed field on an *existing, uncustomized*
  Store-owned record (matched via `source_template_*`) — e.g. the
  template's newer version renamed a Category the Store never touched.
  These are listed but **not pre-selected**; the merchant must explicitly
  check each one.
* **`blocked`** — anything touching a Store-owned record this phase's
  `template_customization_service` (ADR-28) determines is customized, or
  any requested change this phase does not support applying at all
  (label conflicts with an existing unrelated Attribute of a different
  `data_type`, for instance). Blocked entries are never selectable and
  are always shown with a reason string.

`apply_template_update` **only ever applies `safe_additive` entries in
this phase** — `review_required` entries can be selected in the plan UI
for future extension, but the Phase 1F implementation of the apply
service raises `TemplateUpdateError` if a caller attempts to select one,
rather than silently downgrading it to "creates" behavior or silently
ignoring the selection. This is a deliberate, named scope line (see the
Phase 1F report's Known Limitations): the additive path is the one the
prompt's own worked example (§19 "Automatically safe") fully specifies
end-to-end; applying a *review-required* rename/retype safely (which
existing Product data might depend on) is a strictly harder problem
(e.g., changing an Attribute's `data_type` after Products already hold
typed `ProductAttributeValue` rows against it) that deserves its own
dedicated design pass rather than a rushed implementation inside this
phase.

**Consequences.** A merchant can safely accept "add everything new" in
one confirmed action with zero risk of losing customization (verified by
dedicated tests asserting a customized Category's `name` is byte-identical
before and after an update that adds new sibling Categories). Every
application is wrapped in one `@transaction.atomic` block, keyed by an
idempotency key (`f"{installation.pk}:{target_template.pk}"` plus a
per-call selection hash) recorded on the new `StoreTemplateUpdate` history
row *before* any Store-owned row is touched, so a duplicate/retried
request against an already-`completed` update of the same
(installation, target_template) pair is rejected outright rather than
double-applying. `installation.installed_version` is updated to the
target template's version only on a fully successful apply.

**Alternatives considered.** Applying `review_required` changes too, gated
only by a merchant checkbox per item — rejected for this phase because
several of those change types (data-type change, required-Category
removal) have no safe, generally-correct "apply" implementation yet
without also deciding what happens to existing `Product`/
`ProductAttributeValue` rows that depend on the old shape; shipping a
checkbox that silently does the wrong thing on `apply` would be worse
than not offering the option. A full three-way merge/diff resolution UI
(à la source control) — rejected as disproportionate scope for this
phase; the additive-first slice already delivers the update workflow's
primary value (new template content becomes available without
re-installation) safely.

---

## ADR-30: Staff Management Grants Immediate Active Access; Token-Based Invitation Acceptance Is Out of Scope

**Context.** `StoreMembership` (ADR-2/ADR-4) has carried `invited_at`/
`accepted_at`/`revoked_at` and an `INVITED` status since Phase 1B, but its
own docstring explicitly deferred "invitation delivery, tokenized
acceptance, owner transfer, ... and dashboard integration" to a later PR.
No route, view, or template referencing membership management existed
anywhere in `apps.dashboard` before this phase — `STAFF_MANAGE` was a
permission key with no feature behind it. The Admin Panel Completion
Program requires this gap closed with real persistence, real permission
enforcement, and real tests — not a mock or a placeholder screen.

**Decision.** `apps.stores.services.membership_service.add_staff_member`
creates (or reactivates) a `StoreMembership` row with
`status=ACTIVE` and `accepted_at=now()` **immediately**, with no
intervening `INVITED` state the target user must separately accept. The
`Owner` (the only role granted `STAFF_MANAGE`, since it is in
`_OWNER_ONLY`) is adding a specific person they already know — an
employee — not sending cold outreach to a stranger who must opt in. A
`User` row is created (with an unusable password) if the phone number has
no existing account, and `is_staff=True` is set so the account can pass
`staff_required`'s Django-level staff gate the next time that person logs
in (via the existing OTP/password flow in `apps.customers.services.auth_service`
— unchanged by this phase).

This sidesteps a real chicken-and-egg problem: `staff_required` denies
access to *every* admin-portal route, including a hypothetical "accept your
invitation" page, to anyone without an already-`ACTIVE` membership in that
exact Store. A safe, reachable, tokenized acceptance flow (e.g., a signed
link mailed/texted to the invitee, verified without requiring a prior
session) is a legitimate, separate feature — it needs its own delivery
channel decision (SMS vs. email), token model, and expiry policy — and is
documented as a limitation in the Admin Panel Completion Report rather than
built as a rushed, half-covered addition here.

The `INVITED` status and its fields remain fully supported by the model and
`membership_service` (`list_memberships` still sorts and displays `INVITED`
rows distinctly, `revoke_membership`/`reactivate_membership` operate on
them too) for any row created by a future acceptance-flow feature or
directly via Django admin — this phase does not remove or weaken that
state, it simply never creates one itself.

**Consequences.** A merchant can add a working team member in one step
with no delivery-channel dependency (no SMS/email plumbing needed for the
core feature to be real and usable today). The tradeoff is explicit and
documented: there is currently no "pending invite the recipient must
approve" moment — whoever holds the phone number gains access as soon as
the Owner submits the form, so Owners must only enter numbers they intend
to grant access to right away.

**Alternatives considered.** Building a full tokenized email/SMS
acceptance flow in this same phase — rejected as disproportionate scope
that would also require solving the reachability problem above (a new,
unauthenticated-but-token-gated route class that does not yet exist
anywhere in `apps.dashboard`) and a new SMS event/template plus its own
test surface, none of which the rest of this phase's checkpoints depend on.
Making `is_staff` alone sufficient (dropping the `StoreMembership` check)
— rejected outright: this is exactly the tenant-isolation vulnerability
`apps.stores.authorization`'s own module docstring was written to close.

---

## ADR-31: Inventory Is a Ledger (`StockMovement`), Not a Bare Counter — and Order-Level Stock Mutation Targets the Correct Field

**Context.** Before this phase, `Product.stock`/`ProductVariant.stock` were
plain `PositiveIntegerField` counters mutated directly (via `F()` updates)
with no audit trail, and auditing revealed two real correctness bugs in
`apps.orders.services.order_service`:

1. `create_order_from_cart` decremented `Product.stock` **unconditionally**
   for every order line, even when the line was for a specific
   `ProductVariant`. For a variable product, `ProductVariant.stock` (the
   Phase 1D variant engine's own counter) was never touched by checkout —
   only the parent `Product.stock` was, regardless of which variant was
   actually ordered. `_lock_and_revalidate_items` had the matching bug on
   the validation side: it checked `item.quantity > product.stock`, so an
   order for a variant with `stock=0` could still pass validation as long
   as the *parent* `Product.stock` happened to be positive.
2. `change_order_status` had no restock path at all — canceling a
   `PENDING`/`PROCESSING`/`SHIPPED` order permanently "lost" the stock that
   was decremented when the order was placed; it was never returned.

Both bugs are silent under the platform's own test suite prior to this
phase because every existing checkout test used simple (non-variant)
products, so `product.stock` was always the correct target by coincidence,
and no test asserted post-cancellation stock levels.

**Decision.** `apps.catalog.models.StockMovement` is the single, append-only
ledger every stock mutation must pass through — enforced by convention (no
code outside `apps.catalog.services.inventory_service` performs a raw `F()`
stock update) rather than by a database trigger, matching this codebase's
existing pattern of enforcing invariants in one service layer
(`template_update_service`, `membership_service`) rather than in triggers.
Each row records `store`, `product`, `variant` (nullable — null means the
movement targets the product's own counter, not a specific variant's),
`reason` (`order_placed` / `order_canceled` / `manual_adjustment`), signed
`delta`, and `stock_before`/`stock_after` — enough to reconstruct the exact
state of any counter at any point in time without recomputing it from
scratch.

`apps.catalog.services.inventory_service.decrement_stock_for_order_item`
is now the only place `create_order_from_cart` decrements stock: it targets
`variant.stock` when the order line has a variant, `product.stock`
otherwise — fixing bug (1) at its root, not by adding a special case.
`_lock_and_revalidate_items`'s pre-checkout stock check was fixed the same
way (`available_stock = variant.stock if variant is not None else
product.stock`). `restock_order` is called from `change_order_status`
whenever an order transitions to `CANCELED`, reversing every
`ORDER_PLACED` movement for that order's items — fixing bug (2). Because
`CANCELED` is one of `order_service.FINAL_STATUSES` with no outgoing
transitions (ADR predates this document but is enforced by
`ALLOWED_TRANSITIONS`), `restock_order` runs at most once per order.

**Consequences.** Every unit of stock ever decremented by a real order is
now provably returned on cancellation, and a merchant (or platform
operator, via the read-only `StockMovementAdmin`) can answer "why does this
product show 7 in stock" by reading the ledger instead of trusting an
opaque counter. The dashboard's new Inventory Ledger page
(`apps.dashboard.views.inventory_list`) surfaces this history directly to
the merchant, filterable by product/SKU and reason. `adjust_stock_manually`
is provided for a future manual-recount UI but is not wired to a dashboard
view in this phase — this phase's scope was the order-lifecycle
correctness fix and its supporting audit trail, not a full manual
stock-adjustment workflow (documented as a limitation in the Admin Panel
Completion Report).

**Alternatives considered.** Fixing only the `Product.stock`-vs-
`ProductVariant.stock` targeting bug without introducing a ledger —
rejected because the prompt's own explicit prohibition ("do not mutate
inventory without a ledger") and the restock-on-cancel bug are the same
class of problem (stock mutated with no auditable trail of *why*); fixing
one without the other would leave the other bug in place and undiscovered
by tests. A database trigger-based ledger (writing `StockMovement` rows
automatically on any `UPDATE` to `stock`) — rejected as inconsistent with
every other invariant in this codebase, all of which are enforced in
Python service layers precisely so the reasoning is visible in one place
and covered by ordinary Django tests, not hidden in database-specific
trigger SQL that would also have to be reproduced for SQLite (tests) and
PostgreSQL (production) separately.

---

## ADR-32: Coupon Is Store-Owned — Code Uniqueness Is Per-Store, Not Global

**Context.** The Admin Panel Completion Report (checkpoint 1) named
`Coupon` having no `store` FK at all as a real, live cross-tenant leak:
`Coupon.code` was globally unique, and both `checkout_service.apply_coupon`
and `get_applied_coupon` looked up `Coupon.objects.filter(code=code)` with
no Store filter whatsoever. In practice this meant any Store's checkout
could apply any other Store's coupon code, and two Stores could never both
use a common, obvious code like `WELCOME10` — the second one to try would
simply fail with "code already exists," attributed to a stranger's Store.

**Decision.** `Coupon` gets a required `store` FK (`on_delete=CASCADE`,
matching every other Store-owned aggregate in this codebase) and the
uniqueness constraint moves from a bare `unique=True` on `code` to
`UniqueConstraint(fields=["store", "code"])`. The migration follows the
same three-step safe pattern already established for `Product`/`Category`/
`Vendor` Store-scoping (`apps/catalog/migrations/0006-0008`): (1) add the
FK nullable and drop the old global-unique constraint, (2) backfill every
pre-existing `Coupon` row to the Akhlaghi Store (the platform's only
pre-existing Store, the sole deterministic choice — mirrors
`apps/catalog/migrations/0007_backfill_catalog_store.py`'s own reasoning),
(3) enforce `NOT NULL` and add the per-Store unique constraint. Every
lookup site (`checkout_service.apply_coupon`, `get_applied_coupon`,
`order_service.create_order_from_cart`'s new defensive check,
`membership`-style dashboard views) now filters or validates by `store`
explicitly — checkout resolves the Store once at the HTTP boundary
(`resolve_store_for_service`) and passes it down, matching this codebase's
standing rule that deeper service functions never re-derive a Store
themselves.

**Consequences.** Two Stores can now both run a `WELCOME10` campaign
independently; a coupon code leaking into another Store's checkout is now
structurally impossible (enforced by the query filter, verified by
`CouponTenantIsolationTests` in `apps/orders/tests/test_checkout_service.py`
using two Stores with the *same* code string). A previously undiscovered
class of bug (checking `product.stock` regardless of variant is the direct
analogue in ADR-31) is closed the same way: fix the query, not just the
symptom.

**Alternatives considered.** Scoping only at the checkout-lookup layer
(add a `store` filter to the two call sites) without touching the model —
rejected because the underlying data model would still allow a genuine
data-integrity violation (two Stores literally unable to pick the same
code) and would leave the Django Admin / any future direct-model access
path unscoped. Making `Coupon` a subclass of a generic "Promotion" model
with Product/Category scope fields — out of scope for this checkpoint;
this codebase's `Coupon` has never had per-product/per-category scoping
fields at all (verified by reading the full model before this change), so
introducing them now would be new functionality, not a tenant-isolation
fix — tracked as a follow-up in the Admin Panel Completion Report, not
invented here.

---

## ADR-33: Refund Financial Integrity — Amounts Computed From the Immutable Order Snapshot; Only `MANUAL` Execution Is Real

**Context.** Checkpoint 2 requires refund planning and execution that
cannot over-refund, double-refund, or refund against the wrong Store/
currency — and this platform has no payment gateway integration capable of
actually pushing money back to a customer (`PaymentGatewayConfig`/
`PaymentAttempt` model the *forward* payment flow only). Silently
pretending a `GATEWAY` refund succeeded would be dishonest and would
corrupt the ledger with a claim this codebase cannot back up.

**Decision.** `apps.orders.services.refund_service` computes every amount
from `Order.grand_total`/`shipping_cost` and `OrderItem.unit_price` — the
snapshot already frozen at checkout time (`create_order_from_cart`) —
never from `Product.price`, which can change after the order was placed.
`refundable_amount(order)` = `paid_amount(order)` (the full `grand_total`
if `payment_status` is `PAID`/`REFUNDED`, else zero — this codebase does
not model partial payment at the Order level) minus the sum of every
non-final-failed/cancelled `Refund`'s amount already committed against
this order. `plan_order_refund` is a pure, side-effect-free computation
(no DB writes) used both by the dashboard form (to show the merchant the
real maximum before they submit) and by `execute_order_refund` itself (so
the two can never disagree). `execute_order_refund` re-validates
everything server-side from POST data containing only *quantities* and a
*shipping toggle* — never a client-supplied amount — before creating the
`Refund`/`RefundItem` rows inside one atomic transaction.

Only `refund_method=Refund.Method.MANUAL` is actually executable:
`execute_order_refund` immediately marks it `SUCCEEDED` with
`completed_at=now()`, which is an honest statement ("the merchant just
told this system they paid the customer back outside of it"), never a
claim that this platform moved money. Requesting
`refund_method=Refund.Method.GATEWAY` raises `RefundError` immediately,
with a message that says why, surfaced directly in the dashboard UI —
per this checkpoint's own explicit instruction not to claim money was
transferred when it wasn't. `record_refund_result` exists as the future
integration point for a real gateway webhook, and refuses to modify a
`Refund` that has already reached one of `FINAL_STATUSES` (`SUCCEEDED`/
`FAILED`/`CANCELLED`) — a completed refund's amount is a historical fact,
correctable only by a new `Refund` row, never an edit.

**Consequences.** Over-refund, duplicate-refund (via `idempotency_key`,
mirroring `Order.idempotency_key`'s own pattern), cross-Store refund, and
refunding a quantity beyond what was purchased (accounting for *all*
already-refunded quantity across every non-cancelled refund on that line,
not just the most recent one) are all provably impossible — verified by
adversarial tests in `test_refund_service.py`. The dashboard refund form
never has an amount input field at all; it only collects quantities and a
shipping toggle, so there is nothing for a manipulated request to lie
about.

**Alternatives considered.** Modeling a fake "gateway success" for
`GATEWAY` refunds so the UI always looks fully automated — rejected
outright as dishonest and explicitly prohibited by this checkpoint's own
instructions. Tracking partial payment at the `Order` level to make
`paid_amount` more granular — out of scope; this codebase's `Order` has
always treated payment as binary (`PaymentStatus.PENDING`/`PAID`/`FAILED`/
`REFUNDED`), and changing that is a separate, larger payment-domain
decision this checkpoint does not make.

---

## ADR-34: Return Requests Get Their Own Explicit State Machine, Separate From `Order.status`

**Context.** `Order.status` (ADR predates this document; enforced by
`order_service.ALLOWED_TRANSITIONS`) is fulfillment-focused — pending
through delivered/canceled — and has no room for "a customer wants to send
part of this delivered order back." Overloading it with return-related
values would conflict with `FINAL_STATUSES` semantics (a `DELIVERED` order
is done, but a return against it is only just starting) and would make
`ALLOWED_TRANSITIONS` express two unrelated concerns in one field.

**Decision.** `ReturnRequest` is a separate model with its own
`Status` (`requested → under_review → approved/rejected → in_transit →
received → inspected → completed/cancelled`) and its own
`ALLOWED_TRANSITIONS`/`FINAL_STATUSES` pair, built with exactly the same
shape as `order_service`'s (a dict of legal next-states, a frozenset of
terminal ones) — a deliberate architectural echo, not a coincidence, so
anyone who already understands the Order state machine immediately
recognizes this one. Every transition goes through
`apps.orders.services.return_service`, never a raw `.status = X; .save()`
in a view: `review_return_request`, `approve_return_request` (validates
per-item approved quantity never exceeds requested), `reject_return_request`
(requires a reason), `mark_return_received`, `inspect_return_items`
(records condition/restockability/resolution per item), and
`complete_return` (triggers inventory restock and, where the merchant's
per-item resolution was "refund," an actual `Refund` via
`refund_service.execute_order_refund`). A `ReturnRequest.order` can have
*multiple* `ReturnRequest`s over its lifetime (a customer might return two
different items on two different days) — quantity reservation is tracked
per-`OrderItem` across all non-rejected/non-cancelled returns
(`_reserved_return_quantity`), not per-Order, so this is provably safe
against double-counting.

**Consequences.** `Order.status` needed no changes at all — it remains
purely about fulfillment, exactly as before. A return can be created,
approved, rejected, received, inspected, and completed with a fully
auditable trail (`approved_at`/`received_at`/`completed_at`/`rejected_at`
timestamps plus an `AuditLogEntry` at every transition) independent of
whatever the Order's own fulfillment status is.

**Alternatives considered.** Adding `partially_returned`/`returned` values
directly to `Order.Status` — rejected because a `DELIVERED` order (a
`FINAL_STATUSES` member with no outgoing transition in
`order_service.ALLOWED_TRANSITIONS`) would need to somehow also become
`returned` without violating that finality, which would require weakening
an existing, tested invariant just to shoehorn an unrelated concern into
the same field. See ADR-35 for the matching decision on financial state.

---

## ADR-35: Order Financial/Return State Is Tracked in Dedicated Fields and Related Rows, Not Folded Into `Order.status`

**Context.** Checkpoint 2 explicitly asks whether an Order should be able
to become `partially_refunded`/`refunded`/`partially_returned`/`returned`,
or whether that state should live separately from the existing
fulfillment-focused status. This is the direct financial-state
counterpart to ADR-34's fulfillment/return-workflow split.

**Decision.** Financial and return state stay **out of** `Order.status`
entirely. `Order.payment_status` gains its natural final value
(`REFUNDED`) exactly once already-supported by the model — no new status
values were added anywhere on `Order` itself. The complete financial
picture is always *derived*, on demand, from real rows: `paid_amount`,
`refunded_total`, `refundable_amount` (all in `refund_service`, ADR-33)
compute directly from `Order.grand_total` plus the live set of
non-cancelled `Refund` rows; return state is the live set of
`ReturnRequest` rows linked to the order (`order.return_requests`). The
dashboard's Order Financial Summary (`_order_detail_context`) simply
surfaces these computed values and the related querysets — there is no
stored, cacheable "is this order returned" boolean anywhere that could
drift out of sync with the underlying `Refund`/`ReturnRequest` rows.

**Consequences.** There is exactly one source of truth for "how much of
this order has been refunded" (the `Refund` rows themselves), so it can
never disagree with itself. Adding a future reporting need (e.g., "list
all partially-refunded orders") is a query over `Refund`, not a migration
to add and backfill a new `Order` field. The tradeoff is that "is this
order returned" is a computed property, not an indexed column — acceptable
at this codebase's scale (matching the same tradeoff already accepted for
`refundable_amount` itself).

**Alternatives considered.** Adding `financial_status`/`return_status`
fields directly to `Order` — rejected for the same reason ADR-34 rejected
folding return workflow into `Order.status`: it would require keeping a
denormalized field in sync with the real `Refund`/`ReturnRequest` rows on
every write path, a second source of truth that can drift, for a
computation that is already cheap and correct today.

---

## ADR-36: Audit Log Is Store-Scoped, Redacts Known-Sensitive Keys at Write Time, and Deliberately Omits IP/User-Agent

**Context.** Checkpoint 2 requires a reusable audit trail for sensitive
merchant-admin actions (staff changes, inventory adjustments, order
cancellation, refund/return lifecycle, coupon changes) with explicit
before/after summaries, while never storing passwords, gateway secrets,
card data, or auth tokens — and the request notes IP/User-Agent logging
is conditional on "existing privacy policy" support.

**Decision.** `apps.core.models.AuditLogEntry` is a new, Store-scoped,
append-only model (no `updated_at` at all — a correction is a new row,
never an edit of history) with `store`, `actor` (nullable — some events
are system-initiated), `action_code`, a loose `object_type`/`object_id`
(plain strings, not Django `ContentType`, so this model never needs to
import or depend on whichever app owns the object it's describing —
important since it is written from `apps.stores`, `apps.catalog`, and
`apps.orders` services alike), `object_label`, `before_summary`/
`after_summary` (JSON-serialized, redacted), `metadata` (`JSONField`,
redacted), `request_id` (for idempotent-on-retry writes), and `result`.
The single write path, `apps.core.services.audit_service.record_audit_event`,
redacts any key matching a hardcoded forbidden-key list (`password`,
`token`, `secret`, `api_key`, `card_number`, `cvv`, and their common
variants) inside `metadata`/`before`/`after` **before** the row is ever
written — a defense-in-depth measure, not a substitute for callers simply
not passing secrets in the first place. Passing a `request_id` makes the
call idempotent: a retried operation with the same id returns the
already-existing entry instead of writing a duplicate.

`ip_address`/`user_agent` fields were **deliberately not added**. This
codebase has never adopted a privacy policy governing retention of end-user
network metadata (verified by inspecting `apps.customers`, `apps.orders`,
and every existing model for any precedent — there is none), so adding
IP/User-Agent collection now, with no policy decision behind it, would be
unpoliced personal-data collection introduced as a side effect of an
unrelated feature. The checkpoint's own instruction ("only if existing
privacy policy supports it") is read literally: no policy exists, so
nothing is collected.

The Merchant Admin Audit Log UI (`apps.dashboard.views.audit_log_list`)
is gated by the new `AUDIT_LOG_VIEW` permission, granted to `Owner`,
`Administrator` (via `ALL_PERMISSIONS - _OWNER_ONLY`), and `Analyst`
(read-only reporting, per this checkpoint's own suggested role policy) —
`Catalog Manager`/`Order Manager`/`Content Editor` do not get it, matching
the centralized `apps.stores.authorization` registry every other
permission in this codebase goes through.

**Consequences.** Every sensitive action integrated this checkpoint
(staff add/role-change/revoke/reactivate/ownership-transfer, manual
inventory adjustment, order cancellation, refund completion, every return
transition, coupon create/update/toggle/archive) now produces a
searchable, Store-scoped, tamper-evident trail with no secret material at
rest. Redaction is unit-tested directly (`test_audit_service.py`) rather
than trusted to caller discipline alone.

**Alternatives considered.** Using Django's built-in `ContentType`/
`GenericForeignKey` for `object_type`/`object_id` — rejected as
unnecessary coupling; this log is deliberately a write-mostly, read-by-
humans record, not a queryable-by-relation index, so a plain string pair
is simpler and avoids a hard dependency from `apps.core` back onto every
app it audits. Logging IP/User-Agent "since it might be useful later" —
rejected per the reasoning above; it is easier to add a field later behind
an actual privacy-policy decision than to have collected it without one
from day one.

---

## ADR-37: `Warehouse` Provisioning Is an Explicit, Idempotent Service Call — Never a Django Signal

**Context.** Every Store needs exactly one default `Warehouse` to exist
before any inventory/order operation can attribute stock to a location.
This is the same shape of problem `ShopSettings.provision_for`/
`FooterSettings.provision_for` already solved for their respective
Store-scoped singletons, both predating this checkpoint.

**Decision.** `provision_default_warehouse(store)` follows that exact,
established precedent: an explicit, idempotent, plain Python function —
called from the data migration (`0018_provision_default_warehouses`, for
Stores that existed before this checkpoint), from the
`provision_default_warehouses` management command (for ops/future Stores),
and available for any future Store-creation code path to call directly —
never a `post_save` signal on `Store`. This codebase has no signal-based
provisioning anywhere (verified across `apps.stores`, `apps.core`,
`apps.content` before adding this), so introducing one exception here
for warehouses would be a new, inconsistent pattern for the one place
that happens to need it most recently.

**Consequences.** Warehouse provisioning is easy to reason about, easy to
call from a script or a one-off shell, and impossible to trigger
accidentally as an invisible side effect of an unrelated `Store.save()`.
The cost — matching the cost already accepted for `ShopSettings`/
`FooterSettings` — is that any *new* Store-creation code path that
forgets to call `provision_default_warehouse` will simply not have a
warehouse until something calls it; `provision_default_warehouses` (the
management command) exists as an idempotent, safe-to-rerun backstop for
exactly that scenario.

**Alternatives considered.** A `post_save` signal on `Store` — rejected
solely for consistency with the two directly analogous precedents this
codebase already chose not to signal-provision; introducing signals for
warehouses alone would make this the only Store-scoped singleton
provisioned differently from the other two, for no functional benefit.

---

## ADR-38: `Product`/`ProductVariant.stock` Remains the Single Authoritative Sellable-Stock Field; `WarehouseInventory` Is a Synced Per-Warehouse Breakdown, Not a New Source of Truth

**Context.** Checkpoint 3 asks for a Warehouse/stock-location domain with
per-warehouse balances. The "obvious" design flips authority: delete the
aggregate `stock` field and make `WarehouseInventory` (summed across a
product's warehouses) the only truth. That is the textbook multi-warehouse
model — but this codebase has ~2,400 existing passing tests that create
`Product`/`ProductVariant` rows and assert directly against `.stock`
before, during, and after checkout, returns, and refunds (`decrement_stock_for_order_item`,
`restock_order`, `restock_return_item`, `restock_refund_item`,
`adjust_stock_manually` — all of `apps.catalog.services.inventory_service`
predate this checkpoint and are exercised by that entire existing suite).

**Decision.** `Product.stock`/`ProductVariant.stock` **stay** the single
authoritative field for "how much of this can currently be sold" — exactly
as before this checkpoint. `Warehouse` and `WarehouseInventory` are new,
additive models: every warehouse-aware balance changes (`_sync_warehouse_balance`
in `inventory_service`) alongside the aggregate field, in the same
transaction, whenever `decrement_stock_for_order_item`/`restock_order`/
`restock_return_item`/`restock_refund_item`/`adjust_stock_manually` runs —
so `WarehouseInventory.on_hand` summed across a product's warehouses is
kept equal to `Product.stock`/`ProductVariant.stock` by construction, not
by a periodic reconciliation job. `verify_inventory_consistency
--strict` (a new, read-only management command) exists specifically to
catch drift if that invariant is ever violated by a future bug, but it is
a safety net, not the mechanism that keeps the two in sync.

A direct consequence of this decision: every order-driven inventory-service
call that touches `_sync_warehouse_balance` — `decrement_stock_for_order_item`
(checkout), `restock_order` (cancellation), `restock_return_item`,
`restock_refund_item`, and `adjust_stock_manually` — always resolves and
credits/debits the Store's *default* warehouse, unconditionally, via
`_resolve_default_warehouse`. None of them ask "which warehouse actually
fulfilled this order" because nothing in this codebase's `Order`/`OrderItem`
model records that yet — fulfillment-warehouse selection is out of scope
for this checkpoint. This is a deliberate, narrow policy for return/refund
restocking specifically: a returned or refunded item always goes back into
the Store's default warehouse's balance, regardless of which (if any)
non-default warehouse a merchant may have manually shipped it from via a
`WarehouseTransfer`. The only way stock moves into or out of a *non*-default
warehouse's balance is an explicit `WarehouseTransfer` (ADR-40) — order
fulfillment itself is single-warehouse-implicit today.

**Consequences.** Every existing test that asserts against `Product.stock`/
`ProductVariant.stock` continues to pass unmodified — this checkpoint adds
a parallel, synced breakdown rather than migrating the meaning of an
already-load-bearing field. The cost is that `WarehouseInventory` is
"derived-but-stored" rather than the single source of truth a textbook
warehouse model would prefer — a store that somehow bypassed
`inventory_service` and wrote to `Product.stock` directly would silently
desync the two (mitigated by `verify_inventory_consistency` and by the
fact that nothing in this codebase, before or after this checkpoint,
writes to `.stock` outside that service module).

**Alternatives considered.** Making `WarehouseInventory` the sole
authority and deriving `Product.stock` as a computed property — rejected:
it would require rewriting every existing inventory-service function and
every one of the ~2,400 tests that construct a `Product`/`ProductVariant`
with a `stock=` kwarg and assert against it after a save, for a benefit
(single source of truth) this codebase does not yet need at its current
scale — no multi-warehouse store exists yet, `provision_default_warehouse`
provisions exactly one warehouse per Store today. Revisiting this decision
is explicitly a candidate for a *future* checkpoint once a store actually
operates multiple warehouses with independent, warehouse-specific sellable
quantities (e.g. "in stock at warehouse A, sold out at warehouse B").

---

## ADR-39: Inventory Reservation Reduces "Available" (Computed), Not "On-Hand" (Stored) — and Is Created and Consumed Synchronously Within `create_order_from_cart`'s Own Transaction, Never Held Open Across Requests

**Context.** Checkpoint 3 asks for atomic inventory reservation with
idempotent retries, reservation release, and reservation expiration —
language that, in most e-commerce systems, implies a reservation created
at "add to cart" or "begin checkout" time and held open across a
multi-step, multi-request checkout flow (address entry, payment redirect,
gateway callback) until the order is confirmed or the reservation expires.
This codebase's existing checkout (`checkout_service.finalize_order` →
`order_service.create_order_from_cart`), predating this checkpoint, is a
single synchronous call: lock rows, validate, create the `Order` and all
`OrderItem`s, decrement stock, done — all inside one `transaction.atomic()`
block, already covered by a large existing test suite
(`test_checkout_correctness.py`, `test_checkout_integrity.py`,
`test_checkout_service.py`, `test_checkout_views.py`) that asserts on this
exact synchronous behavior, including its idempotency-key retry handling.

**Decision.** `InventoryReservation` is a real, first-class model with its
own lifecycle (`ACTIVE`/`CONSUMED`/`RELEASED`/`EXPIRED`/`CANCELLED`), and
`reserve_inventory` only ever reduces *available* quantity — computed as
`on_hand − sum(active reservations)` — never `on_hand` itself. But the
checkpoint's own synchronous, single-request checkout flow is preserved
unchanged: `create_order_from_cart`'s per-item loop calls
`reserve_inventory` and then, in the same atomic transaction, immediately
`consume_inventory_reservation` (which is what actually decrements
`on_hand`/`Product.stock`/`ProductVariant.stock` via the existing
`decrement_stock_for_order_item`, writing the usual `StockMovement`).
Reservation idempotency keys are derived per-cart-item
(`f"{idempotency_key}:{item.pk}"`) from the existing
`Order.idempotency_key`, so a retried checkout submission (already
tested — see `test_checkout_integrity.py`) hits the reservation's own
idempotency short-circuit and returns the already-created reservation
instead of double-reserving or double-consuming.

The `ttl_minutes`/`expires_at`/`expire_inventory_reservations` machinery
this ADR describes is real and independently tested
(`test_reservation_service.py`), and is available today for any future
caller that *does* want a reservation held open across requests (e.g. a
future "hold my cart for 20 minutes" feature, or a future asynchronous/
redirect-based payment gateway flow) — `reserve_inventory` defaults to a
20-minute TTL when called without `ttl_minutes=None`, and
`create_order_from_cart` is the one caller that explicitly opts out of
that default (`ttl_minutes=None`) because it consumes the reservation
before the transaction that created it ever commits.

**Consequences.** Existing checkout behavior — timing, error messages,
idempotency-retry semantics, the entire existing checkout test suite — is
unchanged byte-for-byte; reservation is an internal accounting step
inserted transparently into an already-correct flow, not a rewrite of
that flow's request/response shape. The cost is that this checkpoint does
not deliver a "hold stock while the customer is on the payment gateway's
site" feature — today's payment flow does not have a redirect-and-return
window that would need one (verified against `apps.orders.services.checkout_service`
and the `PaymentGateway`/payment views: gateway selection happens before
`create_order_from_cart`, not after). If a future gateway integration
adds a genuine redirect-based flow, the reservation service already has
the primitives (`ttl_minutes`, `expire_inventory_reservations`) that flow
would need — no new model would be required, only a new caller.

**Alternatives considered.** Reserving at "add to cart" time and holding
the reservation open until checkout completes or the cart is abandoned —
rejected for this checkpoint as a materially larger, riskier change (every
cart mutation would need to reserve/release, `CartItem` quantity edits
would need to adjust reservations, and abandoned-cart expiry would need
to run continuously in production) than what today's actual synchronous
checkout flow requires; the model and service already support this mode
for a future, explicitly-scoped follow-up.

---

## ADR-40: Warehouse Transfers Move Only the Per-Warehouse Breakdown; the Aggregate `Product`/`ProductVariant.stock` Is Untouched by an Internal Transfer

**Context.** `WarehouseTransfer` moves quantity from a source to a
destination warehouse of the same Store through an explicit state machine
(`DRAFT → REQUESTED → IN_TRANSIT → RECEIVED`, with `CANCELLED` reachable
from any non-final state). Every other `StockMovement` reason
(`ORDER_PLACED`, `RETURN_RESTOCK`, `MANUAL_ADJUSTMENT`, etc.) records
`stock_before`/`stock_after` against the aggregate `Product`/`ProductVariant.stock`,
because those events actually change how much of the product is
sellable in total.

**Decision.** A transfer between two warehouses of the *same* Store never
changes how much is sellable in total — it only changes *where* it
physically sits — so `ship_transfer`/`receive_transfer`/a cancelled
in-transit transfer's compensating restock touch only `WarehouseInventory.on_hand`
for the two warehouses involved; `Product.stock`/`ProductVariant.stock`
(ADR-38's single authoritative field) is never written by
`apps.catalog.services.transfer_service`. Consequently, the
`WAREHOUSE_TRANSFER_OUT`/`WAREHOUSE_TRANSFER_IN` `StockMovement` rows this
service writes record `stock_before`/`stock_after` against the *warehouse's*
`on_hand`, not the product aggregate — a deliberate, documented exception
to every other `StockMovement` reason's convention, made explicit in
`transfer_service`'s module docstring so a future reader does not assume
it is a bug. `ship_transfer`/`receive_transfer` are only reachable from
one specific prior status each (`REQUESTED`→ship, `IN_TRANSIT`→receive),
so a retried request after a successful transition is rejected by the
state machine itself rather than re-applying the balance change — the
same idempotent-on-retry shape as this checkpoint's reservation-consume
path (ADR-39).

**Consequences.** `test_transfer_service.py`'s
`test_full_happy_path_moves_balance` asserts the aggregate `Product.stock`
is unchanged across a complete ship→receive cycle, which is the concrete,
tested expression of this decision. Cancelling an `IN_TRANSIT` transfer
restores the shipped quantity to the source warehouse's balance (since it
never reached the destination) — also with no effect on the aggregate.

**Alternatives considered.** Treating a transfer as a restock-then-decrement
pair against the aggregate field (mirroring `RETURN_RESTOCK`) — rejected
because it would imply the total sellable quantity of a product
transiently drops while a transfer is `IN_TRANSIT`, which is not true: the
stock still belongs to the Store and is not sellable-elsewhere-in-the-
meantime in any way this codebase's single-Store-front checkout models —
only its warehouse location is provisionally ambiguous.

---

## Summary Table

| Decision | Status |
|---|---|
| Store is separate from Vendor | Decided |
| Vendor final meaning | Deferred to catalog-domain PR |
| Store ownership via StoreMembership only | Decided |
| Store has one explicit status field | Decided |
| StoreDomain stores normalized hostnames | Decided |
| At most one primary domain per Store | Decided (DB-enforced) |
| Customer direction: global identity + Store profile | Recorded, not implemented |
| PaymentProvider vs StorePaymentConfiguration split | Recorded, not implemented |
| Platform operators ≠ unrestricted merchant-data access | Recorded, not enforced |
| Merchant funds flow directly to merchant accounts (v1) | Recorded |
| Store is aggregate root; no generic StoreConfiguration table | Decided |
| Store resolution is hostname-authoritative, fail-closed compatibility fallback | Decided, implemented |
| ShopSettings/FooterSettings: OneToOneField per Store; trust badges/payment logos: direct Store FK | Decided, implemented |
| Tenant-sensitive services resolve Store once at the boundary, never re-derive it deeper | Decided, implemented |
| `Order` gets a direct `store` FK (redundant, PROTECT) alongside `vendor` | Decided, implemented |
| Checkout idempotency via server-held `Cart.checkout_token` + `Order.idempotency_key` | Decided, implemented |
| `Store.admin_subdomain` is a platform-assigned field, independent of `StoreDomain` | Decided, implemented |
| `/admin-portal/` is the canonical Merchant Admin Portal route; `/admin-panel/` is a temporary 302 redirect | Decided, implemented |
| Admin-subdomain-only enforcement (block public storefront domains from serving the admin portal) | Decided, implemented |
| Variant-specific product images via `ProductImage.variant` (nullable FK, `SET_NULL`) | Decided, implemented |
| Descriptive `Attribute` and variant-generating `ProductOption` are separate models sharing one optional `Attribute` definition | Decided, implemented |
| Variant combination identity is `VariantOptionValue` + derived `combination_key`, not display strings | Decided, implemented |
| Variant reconciliation never hard-deletes; obsolete combinations are marked, axis removal requires explicit regeneration | Decided, implemented |
| Industry templates are platform-owned/read-only; installation deep-copies into Store-owned records, no live template FK | Decided, implemented |
| Category Attribute schema inheritance: direct mapping always wins, opt-out is per-mapping not per-category | Decided, implemented |
| Category change never deletes `ProductAttributeValue`; orphaned values are computed on demand, cleanup is explicit | Decided, implemented |
| Industry template versions are immutable snapshots; a Store may install at most one template, ever (no auto-update) | Decided, implemented |
| Industry template quality is a structured, reusable validation service, not a vanity score | Decided, implemented |
| Template versioning stays on `IndustryTemplate.(slug, version)`; no separate version-family model | Decided, implemented |
| Store customization detection compares live fields against the immutable source template; no snapshot table | Decided, implemented |
| Template updates: additive changes auto-apply by default, everything else requires explicit review or is blocked | Decided, implemented |
| Staff management grants immediate ACTIVE access on add; token-based invitation acceptance is out of scope | Decided, implemented |
| Inventory is an append-only `StockMovement` ledger; order stock mutation targets variant stock when a variant is ordered, and cancellation restocks | Decided, implemented |
| Coupon is Store-owned; code uniqueness is per-Store, not global | Decided, implemented |
| Refund amounts computed from immutable Order snapshot; only manual refund execution is real, gateway execution honestly rejected | Decided, implemented |
| Return requests get their own explicit state machine, separate from Order.status | Decided, implemented |
| Order financial/return state is derived from Refund/ReturnRequest rows, never folded into Order.status | Decided, implemented |
| Audit log is Store-scoped, redacts secrets at write time, deliberately omits IP/User-Agent (no privacy policy backs it) | Decided, implemented |
| Warehouse provisioning is an explicit, idempotent service call, never a Django signal | Decided, implemented |
| `Product`/`ProductVariant.stock` remains the sole authoritative sellable-stock field; `WarehouseInventory` is a synced per-warehouse breakdown | Decided, implemented |
| Inventory reservation reduces computed "available", never stored `on_hand`; reserved and consumed synchronously within order creation, not held across requests | Decided, implemented |
| Warehouse transfers move only the per-warehouse breakdown; the aggregate `Product`/`ProductVariant.stock` is untouched by an internal transfer | Decided, implemented |
