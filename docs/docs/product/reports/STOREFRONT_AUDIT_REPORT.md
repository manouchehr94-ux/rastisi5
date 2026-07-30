# Storefront Audit Report — Checkpoint 6

**Scope.** This audit maps the *actual* customer-facing storefront as it exists
in the codebase at the start of Checkpoint 6 (after Checkpoint 5B), by reading
the real routing, views, templates, static assets, and tests — not the
documentation. It classifies every major page/journey and names the concrete
work Checkpoint 6 performs.

**Headline finding.** The storefront is **substantially complete and
functional**, not a placeholder: a token-based RTL design system
(`core/static/css/tokens.css` + `base.css` + `layout.css`), a full public shell
(announcement bar, header with search/cart/wishlist/account, category dropdown,
merchant-configurable nav menus, footer), a data-driven homepage, a product
list with search + filters + sort + pagination (HTMX partial swaps), a product
detail page with a gallery, variant groups, reviews and related products, a
cart, a multi-step checkout with shipping/coupon/OTP/gateway, and a customer
account with profile, addresses, orders, and wishlist. Store branding is driven
by per-store CSS variables; templates avoid Store-specific hardcoding.

The **genuine gaps** Checkpoint 6 closes are concentrated in: SEO
(sitemap/robots/structured data/canonical were entirely absent), a root `403`
page, an explicit restricted/inactive-store customer state, and additional
adversarial security + tenant-isolation tests plus the required QA/inventory
docs.

---

## Classification legend

- **Complete** — implemented, wired, tenant-safe, and covered by tests.
- **Functional** — works end to end but has visual/UX polish or test gaps.
- **Partial** — core exists; notable sub-features missing.
- **Placeholder** — markup exists but not wired to real behavior.
- **Missing** — no implementation.

---

## Audit table

| Page / journey | URL name | Backend | Template | Navigation | Mobile | RTL | A11y | SEO | Status | Checkpoint-6 work |
|---|---|---|---|---|---|---|---|---|---|---|
| Store homepage | `catalog:home` | done | `catalog/home.html` | linked | yes | yes | ok | title only | Functional | Add canonical + Organization JSON-LD |
| Category listing | `catalog:product-list?category=` | done (query-param) | `product_list.html` | header dropdown | yes | yes | ok | none | Functional | Canonical; documented as filter-based (ADR-83) |
| Subcategory listing | `catalog:product-list?category=` | done (parent+child) | `product_list.html` | header dropdown | yes | yes | ok | none | Functional | Same as above |
| Product listing | `catalog:product-list` | done | `product_list.html` + partials | linked | yes | yes | ok | none | Complete | Canonical + noindex on filtered params |
| Search | `catalog:product-list?q=` | done (name/brand/category `icontains`) | reuses list | header form | yes | yes | ok | none | Functional | Persian normalization documented (ADR-90); empty state present |
| Filters | `catalog:product-list?...` | done (category/brand/price/discount) | list sidebar | in-page | yes | yes | ok | n/a | Functional | Mobile drawer present; querystring preserved |
| Sorting | `?sort=` | done (5 options) | list | in-page | yes | yes | ok | n/a | Complete | — |
| Product detail | `catalog:product-detail` | done | `product_detail.html` | breadcrumb + links | yes | yes | ok | title | Functional | Product + Breadcrumb JSON-LD, canonical, OG |
| Variant selection | product detail | done (attribute/value groups) | detail template | in-page | yes | yes | partial | n/a | Functional | Server-side add-to-cart validation tests (ADR-85) |
| Variant images | gallery | done (product images) | gallery | yes | yes | yes | alt text | n/a | Functional | Fallback behavior documented (ADR-86) |
| Stock display | product detail / cart | done (sellable stock) | templates | n/a | yes | yes | ok | n/a | Functional | Revalidated at cart/checkout by existing services |
| Cart | `cart:detail` | done (add/update/remove) | `cart_detail.html` | header icon | yes | yes | ok | noindex-worthy | Functional | Add `noindex` |
| Checkout | `orders:checkout-step1` + steps | done (shipping/coupon/OTP/gateway) | `checkout_step1.html` | CTA | yes | yes | ok | noindex-worthy | Functional | Idempotency exists (checkout_token); add `noindex` |
| Shipping selection | `orders:checkout-set-shipping` | done | checkout body | in-page | yes | yes | ok | n/a | Complete | — |
| Tax display | checkout totals | done (tax service) | checkout body | n/a | yes | yes | ok | n/a | Complete | — |
| Coupon | `orders:checkout-coupon-apply` | done | checkout body | in-page | yes | yes | ok | n/a | Complete | — |
| Payment return | `orders:payment-callback` | done (server-verified) | `payment_result.html` | redirect | yes | yes | ok | noindex | Complete | Browser return not trusted (existing) |
| Customer login | `customers:login` / OTP | done | `auth_forms.html` | header modal | yes | yes | ok | noindex-worthy | Functional | Generic errors; `noindex` |
| Customer registration | `customers:signup` | done | `auth_forms.html` | header modal | yes | yes | ok | n/a | Functional | — |
| Password reset | `customers:otp-reset` | done (OTP) | otp body | modal | yes | yes | ok | n/a | Functional | — |
| Customer dashboard | `customers:account` | done | `account.html` | header | yes | yes | ok | noindex-worthy | Functional | `noindex` |
| Addresses | `customers:address-*` | done (add/delete/default) | `account_addresses.html` | account | yes | yes | ok | n/a | Functional | — |
| Order history | `customers:account` | done | account partials | account | yes | yes | ok | n/a | Functional | Own-orders-only (verified) |
| Order detail | `customers:account-order-detail` | done | `order_detail.html` | account | yes | yes | ok | n/a | Functional | Ownership enforced; no internal fields exposed |
| Return status | order detail | done (existing Return domain) | order detail | account | yes | yes | ok | n/a | Functional | Customer-visible status only |
| Refund status | order detail | done (existing Refund domain) | order detail | account | yes | yes | ok | n/a | Functional | Customer-visible status only |
| Static/policy pages | `content:page-detail` | done (CMS) | `page_detail.html` | footer | yes | yes | ok | title | Functional | Published-only; canonical |
| Contact page | via CMS page | done | page | footer | yes | yes | ok | n/a | Functional | — |
| 404 | handler | done | `404.html` | n/a | yes | yes | ok | n/a | Complete | — |
| 403 | handler | **none at root** | — | n/a | n/a | n/a | n/a | n/a | **Missing** | Add `403.html` |
| 500 | handler | done | `500.html` | n/a | yes | yes | ok | n/a | Complete | — |
| Restricted/inactive store | middleware 404 | resolves to 404 | — | n/a | n/a | n/a | n/a | n/a | Partial | Inactive/suspended stores 404 by design (ADR-83) |
| Sitemap | — | **none** | — | n/a | n/a | n/a | n/a | **Missing** | Add `django.contrib.sitemaps` |
| robots.txt | — | **none** | — | n/a | n/a | n/a | n/a | **Missing** | Add robots view |
| Structured data | — | **none** | — | n/a | n/a | n/a | n/a | **Missing** | Product/Breadcrumb/Organization JSON-LD |

---

## Routing and tenant safety (existing)

`apps.stores.resolution` resolves a Store from the request Host, fail-closed:
a `StoreDomain` only resolves when its Store `status == ACTIVE` **and** the
domain `verification_status == VERIFIED`. Inactive/provisioning/suspended/closed
stores, unverified domains, and unknown hosts do not resolve — the storefront
middleware yields a 404 rather than leaking another Store's content. The
merchant admin host (`admin_subdomain`) and Django admin host are resolved by
separate functions and are isolated from the storefront. A development
compatibility fallback exists (single-store "akhlaghi") and is documented.
Checkpoint 6 adds adversarial tenant-routing tests and documents this policy as
ADR-83; it does not change the resolution contract.

## Pricing & stock (existing)

Prices are server-owned (`Product.price`/`final_price`, variant deltas);
templates never trust a browser-supplied price, and add-to-cart / checkout
resolve price from the Product/Variant server-side. Stock uses the existing
inventory services as the source of truth and is revalidated at cart and
checkout. Checkpoint 6 adds explicit adversarial tests (forged price/variant/
cross-store) rather than changing these services.

## What Checkpoint 6 deliberately does NOT do

Per the checkpoint brief, it does not rebuild subscription billing, plans,
entitlements, usage limits, import/export, inventory, shipping, tax, refund,
return, CRM, or merchant-admin architecture. It does not add a drag-and-drop
page builder, an external search engine, or a heavyweight frontend framework —
the repo's existing HTMX + Alpine + token-CSS conventions are preserved.

## Scope note (honesty)

The storefront was already mature, so Checkpoint 6 is a **completion and
hardening** pass, not a from-scratch build. This report, the screen inventory,
and the manual QA checklist are the canonical coverage maps; the code changes
in this checkpoint focus on the genuine gaps above (SEO, 403/restricted states,
adversarial tests) while documenting the already-working journeys.
