# RastiSi Golden Reference Storefront — Design Specification

**Date:** 2026-09-04
**Branch:** `golden/g1-reference-storefront`
**Base commit:** `ac2fd5dcad7b4952b02ed42995143e2cfd2504e3`
**Type:** Product/architecture design (authority). The G1 plan is the executable guide.
**Status:** Approved product/design decisions — no further brainstorming.

> **Reconstruction note.** The originally-approved Golden planning docs were lost with an
> ephemeral sandbox together with the local Phase-1 commits. This document is reconstructed
> from the locked requirements and **current repository evidence at `ac2fd5d`**. Two
> corrections versus the lost drafts are load-bearing: (1) the execution baseline is
> `ac2fd5d`, and (2) the Phase-1 "Safe Template Switching" *implementation* is **absent** at
> this baseline and is deferred — Golden G1 must not depend on APIs introduced only by that
> lost work.

---

## 1. Purpose

Turn the existing resettable QA/reference store **`rasti-mode-demo`** into the first
**visually complete Golden Reference Storefront**: a store a prospective merchant can visit
and immediately understand what a finished, premium RastiSi storefront looks like.

It is **not** a QA component gallery, a prototype, a Builder screen, a 51st Ready Template,
or a parallel demo renderer. It is a real, customized merchant storefront produced entirely
through the **existing production contracts** and rendered by the **one universal renderer**.

## 2. Locked Visual Identity

- Premium **multi-brand Fashion / Lifestyle**; editorial + commercial.
- **RTL Persian** typography (Vazirmatn), strong hierarchy.
- **Primary: teal / green.** High-contrast: **charcoal / black.** Accent: **orange / gold**, used sparingly.
- Page surfaces: **warm / light neutral.**
- Large, high-quality product/editorial imagery; restrained shadows; restrained motion;
  coherent radii; generous but not wasteful spacing.
- **Mobile is first-class**, intentionally designed — not a shrunk desktop.

## 3. Architectural Invariants (must hold; verified by tests)

- Exactly **50** official A8 Ready Templates. Golden is **not** template #51.
- **One** production renderer (`render_service`); Public and Preview share it.
- Existing **section registry**, **Store Appearance registry**, and **global region registry** only.
- Normal **Draft → Publish** lifecycle (`layout_service`).
- **Catalog** owns Product/ProductImage/Category/Brand/MerchantCollection; **Commerce** owns
  price/inventory/SKU; **Content** owns Hero/Banner/Story/Media. The Builder never writes
  commerce truth. No commerce truth is hardcoded in templates or Builder JSON.
- Tenant isolation preserved; the Golden setup touches only the fixed slug `rasti-mode-demo`.
- **Phase-1 preservation semantics are not modified by G1.** G1 must not depend on any
  Phase-1-only API. It may use the plain `preset_service.apply_preset_with_checkpoint` +
  `layout_service.publish` path that already exists at `ac2fd5d` (the same path the demo
  seed already uses).

### What must NOT be created

Second renderer; Golden-only template engine; duplicate Header/Footer system; arbitrary
template paths; arbitrary merchant HTML/CSS/JS; executable raw JSON; duplicate
product/catalog models; a one-off static Home bypassing production contracts.

## 4. Ready-Template Baseline (evidence-based ruling)

**Baseline Ready Template: `fashion_promo_catalog` (تندر).** Rationale from repository evidence:

- It is *already* the template the `rasti-mode-demo` seed applies —
  `apps/stores/tests/test_seed_ready_template_fashion_demo_command.py` asserts
  `template_provenance.template.key == "fashion_promo_catalog"`. Reusing it is the
  lowest-risk, test-backed choice.
- Its identity is commercial fashion/promo catalog and it carries the widest commercial
  section vocabulary (hero → category → product → catalog wall).

The Golden Demo intentionally **differs from its baseline** because it is a customized
merchant storefront: it enriches the Home composition, selects premium shell variants, and
selects the identity palette — all through normal merchant/store contracts. The 50-template
catalog and the `fashion_promo_catalog` recipe itself are **unchanged**.

## 5. Palette (existing registered palette — no new color system)

**`theme-forest-cream`** is selected as the demo palette because its registered tokens
already encode the locked identity exactly:

| Role | Token | Meaning |
|---|---|---|
| primary | `#2F855A` | teal / green |
| secondary | `#4D7C0F` | deep green |
| accent | `#D69E2E` | gold (restrained) |
| background / surface | `#F3F0E6` / `#FFFDF7` | warm / light neutral |
| text | `#17352B` | charcoal-green |
| header/footer bg (theme_roles) | `#17352B` / `#112A21` | charcoal contrast |
| price (theme_roles) | `#B7791F` | gold |

This is a **registered** palette selected through the merchant appearance contract, not a
parallel hardcoded color system.

## 6. Global Shell (existing registered variants)

| Region | Variant (registered key) | Why |
|---|---|---|
| Header | `marketplace_search_first` | The premium/commercial header that renders logo, prominent search, navigation, the real-category **Mega Menu** (`_shared/category_mega_menu.html`), and account/wishlist/cart shortcuts; includes mobile burger, mobile search, and mobile nav. |
| Footer | `premium_columns` | Restrained premium multi-column footer (brand, quick links, categories, contact, newsletter, social, legal, trust/payment). |
| Mega Menu | `mega_menu.none.v1` (family) + the header-embedded category mega menu | Only `mega_menu.none.v1` exists as a family; the actual mega-menu UI is the shared category panel embedded by the marketplace header. |
| Bottom Nav (mobile) | `five_item` | First-class mobile bar with search + **cart** shortcut (count badge). |

Cart access is guaranteed renderable by `validate_header_config`; `cart_action.html`
always renders the `cart_count` badge on the live storefront.

## 7. Home Composition (commercial rhythm)

Editorial impact → discovery → products → campaign → products → story → promotion →
collections → trust → newsletter/footer. Concrete section order and settings are specified
in the G1 plan (§Home Composition). Every section is an existing registered `section_key`;
no new section types are introduced for G1.

## 8. Reproducibility

Running the Golden setup repeatedly **converges** to the same intended state (idempotent),
never duplicating rows. Real content comes from existing Catalog/Content models via the
existing idempotent seed/refresh infrastructure. The Golden composition/appearance is applied
through the existing preset/publish contracts.

## 9. Scope Fence

**In scope (G1):** Global Shell + complete Home. **Out of scope:** G2 Search/Category/Listing,
G3 Product Detail, G4 Cart, G5 Responsive/a11y/visual-QA lock, and any Builder UX. No
Checkout/Account/Orders work.
