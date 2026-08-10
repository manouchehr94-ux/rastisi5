# Six New Families Implementation Plan

## Starting State
- Branch: `claude/family-visual-fidelity-fix`
- Starting HEAD: `c4e55bb33195c5bceed53ee517c36e845e1daeea`

## Architecture Findings

The existing 5-family system uses:
- `apps/storefront_builder/family_registry.py` — FamilyDefinition dataclass registry
- `apps/storefront_builder/preset_registry.py` — PresetDefinition per family
- `apps/storefront_builder/section_registry.py` — 23 section types
- Per-family templates in `apps/storefront_builder/templates/storefront_builder/partials/families/{slug}/`
- Per-family CSS in `apps/core/static/css/families/{slug}.css`
- Per-family product cards in `apps/catalog/templates/catalog/partials/product_cards/`
- Per-family product pages in `apps/catalog/templates/catalog/partials/product_pages/`
- Shared render pipeline: `render_service.build_render_items(version, store)`
- Shared context processors for design tokens
- `base.html` with `data-sfb-family` attribute for CSS scoping

## Files to Change/Create

### Registry (Python)
- `apps/storefront_builder/family_registry.py` — Add 6 FamilyDefinition entries
- `apps/storefront_builder/preset_registry.py` — Add 6 PresetDefinition entries

### Templates (per family × 4 structural + 1 card + 1 PDP = ~36 new files)
- `apps/storefront_builder/templates/storefront_builder/partials/families/{slug}/header.html`
- `apps/storefront_builder/templates/storefront_builder/partials/families/{slug}/hero.html`
- `apps/storefront_builder/templates/storefront_builder/partials/families/{slug}/category.html`
- `apps/storefront_builder/templates/storefront_builder/partials/families/{slug}/footer.html`
- `apps/catalog/templates/catalog/partials/product_cards/{card_variant}.html`
- `apps/catalog/templates/catalog/partials/product_pages/{slug}.html`

### CSS (6 new files)
- `apps/core/static/css/families/{slug}.css`

### Tests
- `apps/storefront_builder/tests/test_eleven_families.py`

## Migration Requirement
No migration required. Family registration is pure Python (registry dictionaries).
All new families use existing section types from SECTION_REGISTRY.
No new database columns, tables, or constraints are needed.

## Batch Order
1. Registry entries (family_registry + preset_registry)
2. Templates batch 1: atlas_catalog, ava_fashion
3. Templates batch 2: toranj_gifting, sarv_stock
4. Templates batch 3: sepidar_handmade, zarrin_jewelry
5. CSS for all 6 families
6. Tests
7. Visual QA screenshots
8. Implementation report

## Data-Binding Strategy
All templates use the same shared context variables already provided by the render pipeline:
- `hero_slides`, `banners`, `nav_categories`, `products`, `top_level_categories`
- `SHOP_NAME`, `SHOP_LOGO`, `SHOP_TAGLINE`, etc.
- `header_config`, `footer_config`
- Product data from `product` context variable on PDP

## Renderer Strategy
Each family uses the existing `{% include %}` dispatch via `FamilyDefinition.header_variant` etc.
The shared `page_shell_header.html` / `page_shell_footer.html` already conditionally includes
family-specific partials based on the active `SHOP_FAMILY` object.

## Test Strategy
- Registry count = 11
- All 11 family slugs resolvable
- All 11 presets resolvable
- Default section keys valid for all 11 families
- Template files exist for all 11 families

## Visual QA Strategy
Screenshots via agent-browser at required viewports (if browser available).
