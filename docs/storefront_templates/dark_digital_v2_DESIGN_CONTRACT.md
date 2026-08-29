# dark_digital v2 — Luxury Mobile Commerce Design Contract

## Intent
Premium dark commerce experience derived from RastiSi's own approved concept: graphite/black surfaces, warm gold emphasis, search-led discovery, image-driven merchandising, and a persistent mobile bottom-navigation system.

## Universal-engine rules
- No `template_key` renderer branch.
- No Store/Product/Category IDs.
- Merchant-owned HeroSlide/category/product data only.
- `theme-black-gold` supplies color semantics; structural variants remain reusable.
- Mobile navigation is a registered global region and defaults to `hidden` for existing stores.
- Cart badge is live data only on the public storefront; Builder Preview must not leak a viewer cart.
- Desktop does not render visible bottom navigation.
- Mobile fixed navigation reserves safe-area/content space.

## v2 composition
1. `hero_banner` / `luxury_showcase`
2. `category_grid` / `luxury_shortcuts`
3. `product_section` newest / `luxury_dark`
4. `trust_features`
5. `product_section` best_sellers / `luxury_dark`

## Global shell
- palette: `theme-black-gold`
- header: `luxury_search`
- footer: `dark_tech`
- mobile nav: `luxury_floating_cart`

## Acceptance
Desktop and mobile must stay tenant-safe, overflow-free, readable, and visually distinct. Mobile navigation must link to real home/listing/cart/account routes and provide a real search form.
