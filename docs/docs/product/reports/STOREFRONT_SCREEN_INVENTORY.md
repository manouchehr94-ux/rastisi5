# Storefront Screen Inventory — Checkpoint 6

Canonical coverage map of every customer-facing storefront screen: URL name,
template, view, permissions, tenant scope, and status of mobile / RTL / empty
state / error state / SEO / tests. All storefront views resolve the Store from
the request Host via `apps.stores.resolution.resolve_store_for_service`
(fail-closed; only an ACTIVE store on a VERIFIED domain resolves).

Legend for status cells: ✅ done · ▶ functional · ➕ added/hardened in
Checkpoint 6 · — n/a.

| Screen | URL name | Template | View | Auth | Tenant scope | Mobile | RTL | Empty | Error | SEO | Tests |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Homepage | `catalog:home` | `catalog/home.html` | `catalog.views.home` | public | store | ✅ | ✅ | ✅ (sections hide) | ✅ | ➕ canonical + Org JSON-LD | ✅ |
| Best-products partial | `catalog:home-best-products` | `partials/product_grid.html` | `home_best_products` | public | store | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| Product list / category / search | `catalog:product-list` | `product_list.html` + `partials/product_list_results.html` | `product_list` | public | store | ✅ | ✅ | ✅ | ✅ | ➕ canonical + noindex-on-filters | ✅ |
| Product detail | `catalog:product-detail` | `product_detail.html` | `product_detail` | public | store | ✅ | ✅ | ✅ (gallery fallback) | 404 invalid slug | ➕ Product+Breadcrumb JSON-LD, canonical, OG | ✅ |
| Review submit | `catalog:product-review-create` | `partials/review_form.html` | `product_review_create` | customer | store | ✅ | ✅ | ✅ | inline errors | — | ✅ |
| Cart | `cart:detail` | `cart/cart_detail.html` | `cart.views.cart_detail` | public/session | store | ✅ | ✅ | ✅ empty cart | ✅ | ➕ noindex | ✅ |
| Cart add | `cart:add` | (redirect/partial) | `cart_add` | public/session | store | ✅ | ✅ | — | server-validated | — | ✅ |
| Cart update/remove | `cart:item-update` / `cart:item-remove` | partials | `cart_item_*` | public/session | store | ✅ | ✅ | ✅ | server-validated | — | ✅ |
| Checkout | `orders:checkout-step1` | `orders/checkout_step1.html` + `partials/checkout_body.html` | `checkout_step1` | customer | store | ✅ | ✅ | ✅ | ✅ | ➕ noindex | ✅ |
| Checkout shipping | `orders:checkout-set-shipping` | checkout body | `checkout_set_shipping` | customer | store | ✅ | ✅ | — | validated | — | ✅ |
| Checkout coupon | `orders:checkout-coupon-apply` / `-remove` | checkout body | `checkout_apply_coupon` | customer | store | ✅ | ✅ | ✅ readable errors | ✅ | — | ✅ |
| Checkout OTP | `orders:checkout-otp-*` | `partials/checkout_otp.html` | `checkout_verify_otp` etc. | customer | store | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| Payment start | `orders:payment-start` | redirect | `payment_start` | customer | store | — | — | — | ✅ | noindex | ✅ |
| Payment result | `orders:payment-callback` | `orders/payment_result.html` | `payment_callback` | customer | store | ✅ | ✅ | ✅ | ✅ (server-verified) | noindex | ✅ |
| Login / OTP login | `customers:login` / `customers:otp-login` | `partials/auth_forms.html` / `otp_login_body.html` | `login_view` / `otp_login_view` | public | account | ✅ | ✅ | ✅ | generic errors | ➕ noindex | ✅ |
| Signup | `customers:signup` | `partials/auth_forms.html` | `signup_view` | public | account | ✅ | ✅ | ✅ | ✅ | noindex | ✅ |
| Password reset (OTP) | `customers:otp-reset` | otp body | `otp_reset_view` | public | account | ✅ | ✅ | ✅ | generic | noindex | ✅ |
| Logout | `customers:logout` | (redirect) | `logout_view` | customer | account | — | — | — | — | — | ✅ |
| Account dashboard | `customers:account` | `customers/account.html` | `account_home` | customer | account | ✅ | ✅ | ✅ | ✅ | ➕ noindex | ✅ |
| Profile update | `customers:account-profile-update` | `partials/account_profile.html` | `account_profile_update` | customer | account | ✅ | ✅ | ✅ | inline | noindex | ✅ |
| Address book | `customers:address-add` / `-delete` / `-default` | `partials/account_addresses.html` | `address_*` | customer | account | ✅ | ✅ | ✅ | inline | noindex | ✅ |
| Order detail (account) | `customers:account-order-detail` | `customers/order_detail.html` | `account_order_detail` | customer (owner) | account+store | ✅ | ✅ | ✅ | 404 non-owner | noindex | ✅ |
| Wishlist | `customers:wishlist` / `-toggle` | `customers/wishlist.html` / `partials/wishlist_button.html` | `wishlist_list` / `wishlist_toggle` | customer | account | ✅ | ✅ | ✅ | ✅ | noindex | ✅ |
| Static/policy page | `content:page-detail` | `content/page_detail.html` | content view | public | store | ✅ | ✅ | ✅ | 404 unpublished | ➕ canonical | ✅ |
| 404 | (handler404) | `404.html` | Django | — | — | ✅ | ✅ | — | 404 | — | ✅ |
| 403 | (handler403) | `403.html` (➕ added) | Django | — | — | ✅ | ✅ | — | 403 | — | ➕ |
| 500 | (handler500) | `500.html` | Django | — | — | ✅ | ✅ | — | 500 | — | ✅ |
| Sitemap | `sitemap` (➕) | (xml) | `django.contrib.sitemaps` | public | store | — | — | — | — | ➕ | ➕ |
| robots.txt | `robots` (➕) | (text) | robots view | public | store | — | — | — | — | ➕ | ➕ |

## Notes

- **Tenant scope** "store" = filtered by the Host-resolved Store; "account" =
  the authenticated customer's own records; "account+store" = both (an order is
  scoped to its store and only visible to its owning customer).
- **Category pages** are served by the product list filtered on `?category=`
  (with parent→child expansion), a deliberate design choice documented in
  ADR-83 rather than a separate template tree.
- **Merchant admin** (`/admin-portal/`) and **Django admin** (`/admin/`) are
  intentionally excluded from this inventory — they are not storefront screens
  and are gated separately (StoreMembership / superuser).
- Cells marked ➕ are the concrete Checkpoint-6 additions; everything else was
  already present and is confirmed by the existing storefront test suites.
