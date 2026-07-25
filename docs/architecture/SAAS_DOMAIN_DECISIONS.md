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
by a form. Hostname is platform-globally unique. At most one
`is_primary=True` `StoreDomain` per Store is enforced by a partial
(conditional) database `UniqueConstraint`.

**Alternatives considered.** Storing a full URL and parsing it downstream
wherever needed — rejected: this multiplies the number of places that must
agree on what counts as "the same domain," which is exactly the kind of
duplicate-source-of-truth problem this program is meant to avoid.
Form-level-only validation — rejected: bypassable via the admin, shell, data
migrations, or a future API, so it is not authoritative.

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
networking is implemented; only the model foundation.

**Consequences.** A later PR can implement the actual verification checker
against this schema without another migration to add lifecycle fields.

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
