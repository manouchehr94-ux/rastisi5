# Storefront Manual QA Checklist — Checkpoint 6

Step-by-step browser scenarios for a human tester to exercise the real customer
storefront end to end. Each item lists preconditions, steps, the expected
result, a severity, and a **Status** field to fill in during a QA pass
(`PASS` / `FAIL` / `N/A` + notes).

**How to run.** Start the dev server (`python manage.py runserver`), seed a
store (see §0), and drive the browser at the store's host. Desktop first, then
repeat the mobile-flagged rows at 375px. Severities: **S1** blocker · **S2**
major · **S3** minor · **S4** cosmetic.

Legend for Status column: leave blank until run, then `PASS`/`FAIL`/`N/A`.

---

## 0. Setup & data (preconditions for everything below)

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 1 | Store owner exists | Fresh DB | Create a Store (active) + owner StoreMembership | Owner can reach `/admin-portal/` | S1 | |
| 2 | Store domain resolves | Store active, verified StoreDomain | Visit the store host | Homepage renders, not 404 | S1 | |
| 3 | Catalog seeded | Owner logged into admin | Add ≥2 categories (1 with children), ≥6 products | Products visible on storefront | S1 | |
| 4 | Multi-axis variants | A product marked variable | Add color + size variants, some out of stock | Variant selectors render on PDP | S1 | |
| 5 | Inventory set | Warehouse provisioned | Set stock on products/variants | Stock states reflect values | S2 | |
| 6 | One out-of-stock product | Product stock = 0 | View it on PDP | Shows "out of stock", not purchasable | S2 | |
| 7 | Store branding | Owner in admin | Set logo, primary color, contact, social | Storefront reflects branding | S2 | |
| 8 | Second store exists | Two active stores | Note both hosts | Used for tenant-isolation rows | S1 | |

## 1. Homepage

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 9 | Homepage loads | §0 | Open `/` | 200, hero/sections render | S1 | |
| 10 | Featured categories | Categories exist | Scroll home | Category tiles link correctly | S2 | |
| 11 | New products | Products exist | Scroll | Newest products shown, real data | S2 | |
| 12 | Discounted products | ≥1 discounted product | Scroll | Discount badges show real % | S2 | |
| 13 | Empty section hides | Remove all discounted | Reload | Discount section disappears gracefully | S3 | |
| 14 | No fake metrics | — | Inspect any counters | Counts reflect real data | S2 | |
| 15 | Homepage SEO | View source | Check `<title>`, canonical, Organization JSON-LD | Present and correct | S3 | |
| 16 | Announcement bar | Free-shipping threshold set | Load home | Bar shows configured content | S4 | |

## 2. Header, navigation, footer

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 17 | Logo → home | — | Click logo | Returns to `/` | S3 | |
| 18 | Category dropdown | Categories exist | Open dropdown | Parents + children listed, links work | S2 | |
| 19 | No dead links | — | Click each nav link | No 404s | S2 | |
| 20 | Cart indicator | Add an item | Observe header | Count increments | S2 | |
| 21 | Wishlist indicator | Toggle wishlist | Observe | Count updates | S3 | |
| 22 | Account link (guest) | Logged out | Click account | Login modal opens | S2 | |
| 23 | Account link (auth) | Logged in | Click account | Goes to account page | S2 | |
| 24 | Footer links | CMS pages published | Scroll footer | Policy/page links resolve | S2 | |
| 25 | Social links | Social configured | Click each | Open correct URLs (new tab) | S3 | |
| 26 | Mobile nav | 375px | Open burger | Menu opens, usable, closes | S2 | |

## 3. Category & subcategory

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 27 | Category page | Category with products | Open `?category=slug` | Only that category's products | S1 | |
| 28 | Subcategory | Parent+child | Open child category | Child's products; parent expands | S2 | |
| 29 | Empty category | Category with 0 products | Open it | Clear empty state, no error | S2 | |
| 30 | Hidden category excluded | is_active=False category | Try its slug | Not shown / no products | S2 | |
| 31 | Draft product excluded | Draft in category | View category | Draft not listed | S1 | |
| 32 | Product count | — | Observe listing | Count/pagination accurate | S3 | |
| 33 | Invalid category slug | — | Open `?category=nope` | No products, no crash | S3 | |

## 4. Product listing

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 34 | List loads | Products exist | Open `/products/` | Grid of product cards | S1 | |
| 35 | Card image | Products with images | Observe cards | Primary image or fallback | S2 | |
| 36 | Card price | — | Observe | Current price, real compare-at | S2 | |
| 37 | Discount badge | Discounted product | Observe | Badge only when real | S3 | |
| 38 | Stock state on card | Out-of-stock product | Observe | Not shown as purchasable | S2 | |
| 39 | Pagination | >12 products | Go to page 2 | Correct page, filters preserved | S2 | |
| 40 | Card → PDP | — | Click a card | Opens correct product | S1 | |
| 41 | No N+1 | Dev toolbar/log | Load list | Bounded query count | S3 | |

## 5. Search

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 42 | Search by name | Known product | Search its name | Product appears | S1 | |
| 43 | Search by brand | Product with brand | Search brand | Matching products | S2 | |
| 44 | Search by category | — | Search category name | Matching products | S3 | |
| 45 | Empty query | — | Submit empty | Full list / graceful | S3 | |
| 46 | No results | — | Search gibberish | Clear empty state | S2 | |
| 47 | Persian normalization | Product with ي/ك | Search with ی/ک | Still matches | S2 | |
| 48 | Term preserved | — | Search then paginate | Term stays in URL/box | S3 | |
| 49 | No cross-tenant results | Two stores | Search on store A | Only A's products | S1 | |
| 50 | Search is noindex | View source on results | Check robots meta | `noindex` present | S3 | |

## 6. Filters & sorting

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 51 | Brand filter | Multiple brands | Pick a brand | Only that brand | S2 | |
| 52 | Price range | Varied prices | Set min/max | In-range products | S2 | |
| 53 | Discounted filter | Some discounted | Toggle it | Only discounted | S3 | |
| 54 | Combine filters | — | Category + brand + price | Correct intersection | S2 | |
| 55 | Sort newest | — | Sort newest | Order correct | S3 | |
| 56 | Sort price asc | — | Sort cheapest | Ascending price | S2 | |
| 57 | Sort price desc | — | Sort priciest | Descending price | S2 | |
| 58 | Invalid sort value | — | `?sort=xyz` | Falls back to default | S3 | |
| 59 | Filters preserved on page | — | Filter then page 2 | Filters kept | S2 | |
| 60 | Mobile filter drawer | 375px | Open filters | Drawer usable, applies | S2 | |
| 61 | Filters store-scoped | Two stores | Compare brand lists | Only own store's brands | S1 | |

## 7. Product detail

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 62 | PDP loads | Active product | Open PDP | 200, full detail | S1 | |
| 63 | Breadcrumb | Product in category | Observe | Home → category → product | S3 | |
| 64 | Gallery | Multi-image product | Click thumbs | Main image swaps | S2 | |
| 65 | Gallery fallback | No-image product | Open PDP | Placeholder, no broken img | S3 | |
| 66 | Price + compare-at | Discounted product | Observe | Both shown correctly | S2 | |
| 67 | Stock status | In/out variants | Observe | Correct state | S2 | |
| 68 | SKU shown | — | Observe | Correct SKU | S4 | |
| 69 | Description/specs | Product with specs | Scroll | Rendered | S3 | |
| 70 | Related products | Same-category siblings | Scroll | Relevant, same store | S3 | |
| 71 | Draft PDP blocked | Draft product | Open its slug | 404 | S1 | |
| 72 | PDP SEO | View source | canonical + Product JSON-LD | Present, real price/availability | S2 | |
| 73 | Cross-store PDP | Store B slug on A host | Open | 404 | S1 | |

## 8. Variant selection

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 74 | Options render | Multi-axis product | Open PDP | Color/size selectors show real combos | S1 | |
| 75 | Select updates price | Variant with price delta | Pick variant | Price updates | S2 | |
| 76 | Select updates stock | Out-of-stock variant | Pick it | Shows unavailable | S2 | |
| 77 | Select updates SKU | — | Pick variant | SKU updates | S3 | |
| 78 | Invalid combo disabled | Unavailable combo | Try it | Cannot select | S2 | |
| 79 | Add resolves variant | Valid variant | Add to cart | Correct variant in cart | S1 | |
| 80 | Inactive variant blocked | Inactive variant id (dev POST) | Attempt add | 404, not added | S1 | |
| 81 | Cross-store variant blocked | Store B variant id | Attempt add on A | 404 | S1 | |
| 82 | Forged price ignored | POST fake price | Add | Cart uses server price | S1 | |

## 9. Variant images

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 83 | Variant image shows | Variant with image | Select it | Its image displayed | S2 | |
| 84 | Fallback to product | Variant without image | Select it | Product image shown | S3 | |
| 85 | No foreign image | — | Switch variants | Never another product's image | S1 | |
| 86 | Thumbnails update | Multi-image | Switch | Thumbs reflect selection | S3 | |
| 87 | Mobile gallery | 375px | Swipe/scroll | Usable | S2 | |
| 88 | Alt text | Screen reader | Inspect images | Meaningful alt | S3 | |

## 10. Price & stock presentation

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 89 | IRT zero-decimal | — | Any price | No decimals, Toman label | S3 | |
| 90 | Consistent format | — | Compare list vs PDP vs cart | Same formatting | S3 | |
| 91 | Low stock (if policy) | Low stock product | View | Message per policy | S4 | |
| 92 | Out of stock | Stock 0 | View + attempt add | Blocked | S2 | |
| 93 | No internal inventory leak | — | Inspect PDP | No warehouse/movement data | S1 | |
| 94 | Stock revalidated | Reduce stock mid-session | Add to cart | Revalidated at add/checkout | S2 | |

## 11. Cart

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 95 | Add item | Product | Add to cart | Appears in cart | S1 | |
| 96 | Update quantity | Item in cart | Change qty | Line total updates | S1 | |
| 97 | Remove item | Item in cart | Remove | Item gone | S1 | |
| 98 | Empty cart state | Empty cart | Open cart | Clear empty state + CTA | S2 | |
| 99 | Images/labels | Variant item | Observe | Image + variant label | S3 | |
| 100 | Subtotal | Multiple items | Observe | Correct subtotal | S1 | |
| 101 | Qty bounds | — | Set qty 0/negative | Clamped ≥1 | S2 | |
| 102 | Cart store-isolated | Two stores | Add on A, visit B | A's cart not shown on B | S1 | |
| 103 | Checkout CTA | Non-empty cart | Click checkout | Goes to checkout | S1 | |
| 104 | Mobile cart | 375px | Edit cart | Usable | S2 | |

## 12. Checkout

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 105 | Reach checkout | Cart + login | Start checkout | Step renders | S1 | |
| 106 | Address entry | — | Enter province/city/postal | Validated | S1 | |
| 107 | Shipping select | Methods configured | Pick a method | Cost reflected | S1 | |
| 108 | Tax display | Tax configured | Observe totals | Tax line shown | S2 | |
| 109 | Coupon valid | Valid coupon | Apply | Discount applied | S2 | |
| 110 | Coupon invalid | Bad code | Apply | Readable error | S2 | |
| 111 | Order review | — | Review step | Correct totals | S1 | |
| 112 | Final revalidation | Change price/stock mid-flow | Submit | Revalidated server-side | S1 | |
| 113 | Duplicate submit | — | Double-click submit | One order only | S1 | |
| 114 | Form data preserved | Trigger validation error | Observe | Valid fields kept | S2 | |
| 115 | Payment redirect | Gateway | Proceed | Redirect to payment | S1 | |
| 116 | Browser return not trusted | Manipulate return URL | Return "success" | Not marked paid without server verify | S1 | |
| 117 | Confirmation page | Complete payment (sim) | Finish | Order confirmation shown | S1 | |
| 118 | Mobile checkout | 375px | Complete flow | Buttons visible, forms fit | S2 | |

## 13. Payments

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 119 | Payment pending | Gateway pending | Return | Pending state, honest | S2 | |
| 120 | Payment failed | Fail path | Return | Failure state, retry option | S2 | |
| 121 | Payment success | Success (server-verified) | Return | Order paid | S1 | |
| 122 | No SaaS/commerce mix | — | Inspect | Store payment ≠ SaaS billing | S1 | |

## 14. Customer authentication

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 123 | Register | Guest | Sign up | Account created | S1 | |
| 124 | Login | Existing customer | Log in | Session established | S1 | |
| 125 | Logout | Logged in | Log out | Session cleared | S2 | |
| 126 | Password/OTP reset | — | Reset via OTP | Can regain access | S2 | |
| 127 | Generic auth errors | Wrong credentials | Attempt | No account enumeration | S2 | |
| 128 | Next-URL safe | `?next=//evil.com` | Login | No open redirect | S1 | |
| 129 | Customer ≠ merchant | Customer account | Try `/admin-portal/` | Blocked | S1 | |
| 130 | CSRF on forms | — | Tamper token | Rejected | S1 | |

## 15. Customer account

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 131 | Dashboard | Logged in | Open account | Renders | S2 | |
| 132 | Profile update | — | Edit profile | Saved | S2 | |
| 133 | Add address | — | Add address | Saved, listed | S2 | |
| 134 | Default address | ≥2 addresses | Set default | Marked default | S3 | |
| 135 | Delete address | — | Delete | Removed | S3 | |
| 136 | Account is noindex | View source | Check robots | `noindex` | S3 | |

## 16. Orders, returns, refunds

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 137 | Order history | Placed orders | Open list | Own orders only | S1 | |
| 138 | Order detail | — | Open an order | Items, totals, snapshots | S1 | |
| 139 | Foreign order blocked | Another customer's code | Guess it | 404/denied | S1 | |
| 140 | No internal fields | — | Inspect detail | No staff/fraud/gateway/audit data | S1 | |
| 141 | Return eligibility | Eligible order | View | Return option per policy | S2 | |
| 142 | Submit return | Eligible items | Request return | Recorded, status shown | S2 | |
| 143 | Return quantity bound | — | Over-request | Rejected | S2 | |
| 144 | Refund visibility | Refund issued | View | Status + amount shown | S2 | |
| 145 | Cannot self-mark received/paid | — | Attempt | Not allowed | S1 | |

## 17. Static/policy pages

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 146 | Published page | Published CMS page | Open it | Renders | S2 | |
| 147 | Unpublished blocked | Draft page | Open slug | 404 | S2 | |
| 148 | Footer nav | Pages in footer | Click | Resolve | S3 | |

## 18. Errors & empty states

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 149 | 404 page | — | Open bad URL | Branded 404 | S2 | |
| 150 | 403 page | Trigger permission denied | — | Branded 403, noindex | S2 | |
| 151 | 500 page | Force error (dev) | — | Branded 500, no traceback in prod | S1 | |
| 152 | Inactive store | Suspended store host | Visit | Clean 404, not 500 | S1 | |
| 153 | No sensitive detail | Any error | Inspect | No internal exception text | S1 | |

## 19. RTL & Persian

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 154 | Direction | — | Any page | `dir=rtl`, correct alignment | S2 | |
| 155 | Numbers | — | Prices/counts | Persian digits where intended | S3 | |
| 156 | Phone/email/SKU | Forms/PDP | Observe | LTR fields render correctly | S3 | |
| 157 | Breadcrumbs RTL | — | PDP | Correct order/separators | S3 | |
| 158 | Modals/dropdowns RTL | — | Open them | Aligned correctly | S3 | |
| 159 | Consistent terminology | — | Across pages | Persian labels consistent | S4 | |

## 20. Mobile responsive (repeat key flows at 320/375/768)

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 160 | No horizontal overflow | 320px | Scroll pages | No sideways scroll | S2 | |
| 161 | Tap targets | 375px | Tap buttons | Usable size | S3 | |
| 162 | Gallery mobile | 375px | PDP gallery | Usable | S2 | |
| 163 | Variant selectors mobile | 375px | Select | Usable | S2 | |
| 164 | Checkout buttons visible | 375px | Checkout | CTA visible | S1 | |
| 165 | Tables → cards/scroll | 375px | Order detail | No clipped tables | S3 | |

## 21. Accessibility

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 166 | Headings | — | Inspect | Semantic h1/h2 order | S3 | |
| 167 | Labels | Forms | Inspect | Inputs labelled | S2 | |
| 168 | Keyboard nav | — | Tab through | Focusable, visible focus | S2 | |
| 169 | Variant selector a11y | PDP | Keyboard select | Operable | S2 | |
| 170 | Quantity controls a11y | Cart | Keyboard | Operable | S3 | |
| 171 | Error association | Form error | Inspect | Error tied to field | S3 | |
| 172 | Contrast | Brand colors | Inspect | Readable contrast | S3 | |

## 22. Tenant isolation & security (adversarial)

| # | Scenario | Preconditions | Steps | Expected | Sev | Status |
|---|---|---|---|---|---|---|
| 173 | Cross-store product id | Two stores | Store B product on A | 404 | S1 | |
| 174 | Cross-store category | — | B category slug on A | No leak | S1 | |
| 175 | Cross-store cart | — | Add on A, check B | Isolated | S1 | |
| 176 | Foreign order | — | Access other's order | Denied | S1 | |
| 177 | Forged shipping/tax | — | Tamper POST | Server recomputes | S1 | |
| 178 | Host-header abuse | — | Spoof Host | ALLOWED_HOSTS blocks | S1 | |
| 179 | Sitemap tenant scope | Two stores | Compare sitemaps | Only own URLs/host | S1 | |
| 180 | Path traversal in media | — | `../` in media path | Blocked | S1 | |

---

## Sign-off

- **Tester:** ______________  **Date:** __________  **Build/commit:** __________
- Summarize S1/S2 failures here before sign-off. Checkpoint 6 is not "done" for
  a store until all S1 rows PASS and the end-to-end journey (home → category/
  search → product → variant → cart → checkout → payment → confirmation →
  account → order history) is completed in a real browser.
