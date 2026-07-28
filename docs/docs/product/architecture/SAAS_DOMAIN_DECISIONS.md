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
