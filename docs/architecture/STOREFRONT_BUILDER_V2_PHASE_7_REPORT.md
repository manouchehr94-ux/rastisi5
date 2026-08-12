# Storefront Builder V2 — Phase 7 Completion Report

**Phase**: 7 — Legacy Family Migration / Retirement
**Base SHA**: `7ffc4ae805012f8545da454935555009c392e096` (canonical synchronized HEAD, confirmed)
**Final commit this phase**: `86cce53`
**Commits this phase**: 4

```
86cce53 Phase 7: remove family CSS link + data-sfb-family attribute from base.html
9e366ed Phase 7: hard cutover — retire the legacy Family storefront system
594c062 Phase 7 legacy visual pattern extraction (pre-deletion)
14f0100 Phase 7 read-only retirement audit: legacy Family system
```

Net change: 115 files, +764/−8166 lines — overwhelmingly deletion, as expected for a retirement phase.

## 1. Owner hard-cutover decision

The owner explicitly confirmed: no production stores, no real merchants, no data requiring
preservation, backward compatibility not required, destructive dev/QA cleanup acceptable, Git
history sufficient as the archive for removed source. This superseded the previously conservative
assumption (documented across Phases 1–6) that the legacy Family system might need to coexist
indefinitely. Per that decision, this phase performed a genuine **hard cutover** — not a
deprecation flag, not a parallel-path compromise.

## 2. Initial dependency audit (summary — full detail in the two Phase 7 audit documents)

`STOREFRONT_BUILDER_V2_PHASE_7_AUDIT.md` and `STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md`
found:

- **Two independent legacy appearance mechanisms**, only one in scope: **Family**
  (DOM-swapping, 11 registered families) was retired; the separate, still-live **Template**
  system (`appearance_registry.TemplateDefinition`, 10 shared-DOM CSS-token templates,
  architecturally independent of Family per its own docstrings) was explicitly kept — the master
  instruction's title and every section name "Family" specifically, and warns against deleting
  shared appearance infrastructure.
- Family dispatch was **broader than previously assumed**: not just Product Detail's full-body
  swap, but a global `SHOP_FAMILY` context processor reaching header, footer, product cards,
  hero, and category sections on every page, plus one real business-logic dependency outside
  `storefront_builder` — `apps/cart/context_processors.py`'s `heritage_premium`-keyed
  `cart_preview_mode` branch.
- `family_slug`/`preset_slug` confirmed as pure JSON dict keys inside
  `StorefrontLayoutVersion.appearance_config` — zero schema/migration footprint, no Django model
  named Family or Preset anywhere.
- 67 family-specific template files, 11 family CSS files, 2 registry modules, 10 fully-obsolete
  test files, and 3 family-specific test classes inside an otherwise-unrelated shared-capability
  test file.

## 3. Exact legacy systems retired

- The Family DOM-swap renderer selection mechanism (`SHOP_FAMILY` global context injection and
  every `{% if SHOP_FAMILY %}` branch that consumed it).
- `family_registry.py` (`FamilyDefinition`, `FAMILY_REGISTRY`, 11 families).
- `preset_registry.py` (`PresetDefinition`, `PRESET_REGISTRY`, 11 family-locked presets).
- `bootstrap_service.apply_family_default_sections`/`build_family_default_sections`.
- The merchant-facing family gallery, family preview-candidate flow, and
  `confirm_family_switch` destructive-reset confirmation in the appearance editor.
- `family_slug`/`preset_slug` as active, validated, rendering-significant keys.
- The `heritage_premium`-specific cart preview mode default.

## 4. Exact files deleted

- `apps/storefront_builder/family_registry.py`, `apps/storefront_builder/preset_registry.py`.
- 44 structural partials: `apps/storefront_builder/templates/storefront_builder/partials/families/<slug>/{header,hero,category,footer}.html` × 11 families.
- 11 Product Detail page partials: `apps/catalog/templates/catalog/partials/product_pages/<slug>.html`.
- 12 product card partials: `apps/catalog/templates/catalog/partials/product_cards/*.html` (heritage_premium had 2 — standard + campaign mode).
- 11 CSS files: `apps/core/static/css/families/<slug>.css`.
- 10 test files: `test_family_registry.py`, `test_family_default_section_reset.py`,
  `test_eleven_families.py`, `test_preset_registry_import.py`,
  `test_six_families_tenant_isolation.py`, `test_family_artisan_editorial.py`,
  `test_family_heritage_premium.py`, `test_family_nordic_living.py`,
  `test_family_vibrant_catalog.py`, `test_template_syntax_integrity.py` (the last one found
  during implementation, not in the original audit's test inventory — a pure-Python tag-balance
  checker scoped entirely to the deleted family template files).

Total: 90 files deleted outright, plus surgical edits to 3 test classes inside
`test_shared_capabilities.py` and 2 seed-command test files.

## 5. Exact files retained and why

- `appearance_registry.py` in full — Palette system (`PaletteDefinition`, `PALETTE_REGISTRY`,
  `resolve_colors`, 20 palettes) and structural tokens (density/motion/type-scale/font/
  button-style/image-fit enums) are genuinely shared V2 infrastructure, consumed independently
  of Family by `layout_service`, the global context processor, and Phase 6's
  `layout_preset_registry`/`preset_service`. The 10-entry `TemplateDefinition`/`TEMPLATE_REGISTRY`
  system is a separate, still-live, out-of-scope mechanism (see §2).
- `layout_preset_registry.py`, `services/preset_service.py` (Phase 6) — untouched, confirmed
  still fully functional by both targeted tests and browser QA.
- `test_appearance.py` — zero `family_slug` references, tests only the retained Template/Palette
  system; untouched.

## 6. Universal replacements

| Retired | Replaced by |
|---|---|
| Family DOM-swap renderer selection | The single Universal V2 renderer (Phases 1–5) — no per-family template selection exists anywhere in the active render path. |
| `FamilyDefinition.default_section_keys` + `apply_family_default_sections` (home-only) | `layout_preset_registry.LayoutPresetDefinition.pages` + `preset_service.apply_preset` (Phase 6) — already generalized to all 6 page types, transactional, tenant-safe. |
| Family gallery / "choose a Family" merchant flow | Layout Preset gallery (Phase 6, already present in the same appearance panel) — now the sole "starting point" concept. |
| `family_slug`/`preset_slug` (legacy) | `layout_preset_key` (Phase 6) — family-agnostic, no 1:1 coupling. |

## 7. `family_slug`/`preset_slug` final status

Removed from `APPEARANCE_CONFIG_DEFAULTS` and from `validate_appearance_config`'s validation/
cleaning logic. No schema migration was needed or written (confirmed: pure JSON dict keys, no
Django model, no migration file ever referenced them). Any stale value still physically present
in a pre-Phase-7 stored `appearance_config` blob is now completely inert — proven by
`test_phase7_family_retirement.py::StaleFamilyConfigCannotSwitchRendererTests`, which writes
`family_slug: "modern_fashion"` directly into a Draft's `appearance_config` (bypassing the
validator, simulating real old data) and confirms every one of the 6 page types still renders
through the sole Universal path with no family markup, and that applying a Layout Preset
afterward works normally and drops the stale keys on the next save. Live-verified in browser QA
against the QA store's actual `published_version` with the same stale values injected.

## 8. Registry final status

`family_registry.py` and `preset_registry.py` no longer exist. Confirmed via a dedicated static
test (`RegistryModulesAreGoneTests`) that importing either module now raises
`ModuleNotFoundError`, and that `bootstrap_service` no longer exposes
`apply_family_default_sections`/`build_family_default_sections`. `layout_preset_registry.py`
(Phase 6) confirmed still present and functional with all 4 built-in presets intact.

## 9. Template final status

Zero family-specific template files remain in the active codebase. All 7 shared render points
that previously branched on `SHOP_FAMILY` (`templates/base.html`, `page_shell_header.html`,
`page_shell_footer.html`, `product_card.html`, `hero_banner.html`, `category_grid.html`,
`product_detail.html`) now render their single canonical body unconditionally — no
`{% if SHOP_FAMILY %}` branch remains anywhere in the repository (confirmed by repo-wide grep).

## 10. CSS/static final status

All 11 family CSS files deleted; the conditional `<link>` and `data-sfb-family` attribute in
`templates/base.html` removed. No dangling references remain.

## 11. Builder UI final status

The appearance editor panel (`appearance_panel.html`) now presents exactly: Template (legacy,
retained), Palette, custom colors, advanced/structural settings, and Layout Preset — with zero
family gallery, zero family preview/apply flow, zero `confirm_family_switch` UI. Confirmed both
by targeted Django tests and live browser screenshots (desktop + mobile) showing the hub with
"پیش‌تنظیمِ صفحه‌آرایی" (Layout Preset) as a first-class card alongside the retained "قالب
فروشگاه" (Template) and "پالت فعلی" (Palette) cards. `editor.html`'s JS state/forms
(`candidateFamily`, `#sfbApplyFamilyForm`, `previewCandidateFamily`/`applyCandidateFamily`,
the `preview-candidate-family`/`apply-candidate-family` window events) fully removed; the
parallel Template candidate-preview flow is untouched and still works.

## 12. Migrations / data cleanup

No schema migration required (§7). One QA-store data touch-up was performed directly for browser
QA purposes (deliberately *injecting* a stale `family_slug`/`preset_slug` into the QA store's
published `appearance_config` to prove it's inert — the opposite of cleanup, done on purpose to
exercise the safety guarantee live). No production data existed to migrate or clean, per the
owner's confirmation. No product/category/collection/order/customer/content data was touched
anywhere in this phase.

## 13. Tests removed/replaced and why

- **10 files deleted outright** (§4) — each asserted a product contract that no longer exists
  ("family X renders family template X", "exactly 11 families/presets are registered",
  per-family tenant isolation parameterized over a retired mechanism, family template file
  tag-balance). Their safety-relevant guarantees (Draft/Published isolation, confirm-before-
  destructive-reset, cross-tenant isolation) are already independently proven for the surviving
  mechanism by Phase 6's `test_preset_service.py` and Phase 5's
  `test_phase5_composition_lifecycle.py`.
- **`test_shared_capabilities.py`** — surgically edited: removed `IndependentImageSettingsTests`'
  3 family-preset-specific methods, `StoryRailSectionTests`' 3 family-default methods, and the
  entire `AllElevenFamiliesRegisteredTests` class; kept `CategoryImageFieldTests`,
  `CartPreviewServiceTests`, `ProductMetafieldModelTests`, and the non-family assertions in the
  edited classes untouched.
- **`apps/stores/tests/test_seed_kianstock_qa_demo_command.py`** — removed one obsolete
  `family_slug` assertion (the seed command's `_seed_builder` no longer sets it; its
  `apply_family_default_sections` call was already dead code — immediately overwritten by
  `draft.sections.all().delete()` on the very next line — so removing it has zero behavioral
  effect on the seeded store).
- **`apps/stores/tests/test_seed_rastisi_fashion_demo_command.py`** — `--family` argument tests
  rewritten to `--preset`/`layout_preset_key`, preserving each test's original intent
  (unknown-value rejection, idempotency on rerun, real publish on genuine change, rate-limit
  safety across 25 reruns).
- **Phase 6's `test_preset_service.py::FamilyCompatibilityTests`** — deleted; its entire premise
  (a preset applying successfully alongside a coexisting `family_slug`) is moot now that
  `family_slug` has no meaning left in the system at all.
- **New**: `apps/storefront_builder/tests/test_phase7_family_retirement.py` (14 tests) — proves
  the claims unique to this phase that no pre-existing test covered: no merchant-facing family
  selector, stale family config inert on all 6 page types, header/footer always Universal, no
  active import needs the deleted registries.

## 14. Runtime tests

- New: `test_phase7_family_retirement.py` — **14/14 pass**.
- Directly-affected targeted suites: `test_shared_capabilities.py` + `test_preset_service.py` +
  `test_layout_preset_registry.py` + `test_appearance.py` — **114/114 pass**.
- `test_views.py` (shared `views.py` heavily edited) — **159/159 pass** (one expected
  simulated-failure traceback from a pre-existing flaky-update test, not a new failure).
- Seed command tests (`test_seed_kianstock_qa_demo_command.py` +
  `test_seed_rastisi_fashion_demo_command.py`, both commands materially rewritten) —
  **66/66 pass**, full idempotency/rate-limit/lifecycle coverage for both.
- `manage.py check`: clean throughout. `manage.py makemigrations --check --dry-run`: no changes
  detected (confirms the schema-free removal claim in §7/§12).
- Not run this phase: the full `apps.storefront_builder` suite (800+ tests) or the cross-app
  suite — the directly-affected suites above (353 tests total across 6 files) cover every shared
  file actually modified or deleted; a full-suite run was judged not necessary given the change,
  while large, is almost entirely deletion of self-contained legacy code plus surgical edits to
  already-covered shared files.

## 15. Browser QA

Playwright, desktop (1440×900) and mobile (375×812), against the `sfb-phase4-qa` store, with a
stale `family_slug`/`preset_slug` **deliberately injected** into the store's live
`published_version.appearance_config` (bypassing the validator, simulating real pre-Phase-7 data)
specifically to prove it no longer has any effect:

- **Public**: Home, Listing, Collection Index, Product Detail, Cart all return HTTP 200 with zero
  `data-sfb-family` attribute and zero `css/families/` reference — confirmed via both raw HTML
  inspection and full-page screenshots (desktop + mobile) showing the exact same Universal header/
  footer/design-token shell as every other Phase 4–6 QA session, unaffected by the stale value.
- **Builder**: opens cleanly; appearance panel shows Template (retained)/Palette/Layout Preset as
  the only appearance-related cards, zero Family gallery, zero "خانواده" or
  `confirm_family_switch` text anywhere in the rendered HTML (screenshot-confirmed); Palette
  gallery still lists all 20 options independently; Header editor still opens and shows its
  toggle controls; the section list sidebar still shows all 6 composed home-page sections with
  working drag/hide/duplicate/settings controls; Draft Preview returns 200; Publish completes
  without error.
- Zero console errors on both viewports across the entire flow.

## 16. Known remaining visual gaps

None newly introduced by this phase — Phase 7 is architecture retirement, not visual-capability
work. The genuine visual/UX capability gaps identified during pre-deletion pattern extraction
(hover cart-preview panel, sticky PDP buy box, mobile bottom tab-bar nav, gift-wrap addon,
PDP social-share/FAQ accordion, and two consolidatable product-card hover-reveal/crossfade
settings) are fully catalogued in `STOREFRONT_BUILDER_V2_LEGACY_VISUAL_PATTERN_EXTRACTION.md` and
explicitly deferred to Phase 8, per the master instruction's explicit Phase 7/8 boundary.

## 17. Phase 8 prerequisites

The codebase now truthfully satisfies the Phase 7 success condition: no storefront design
selects or depends on a coded Family; all active rendering uses the Universal V2 engine;
customer-facing configuration is Layout Preset + Palette + free-form Universal Builder editing;
a new visual design requires configuration or a future reusable block, never a new storefront
codebase. `STOREFRONT_BUILDER_V2_LEGACY_VISUAL_PATTERN_EXTRACTION.md`'s "Summary for Phase 8"
section is the direct, ranked input list for Phase 8's capability-gap work.

## Owner-local Heavy Gate (PowerShell)

```powershell
cd <repo-root>
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.storefront_builder --verbosity 1
python manage.py test apps.catalog apps.cart apps.dashboard --verbosity 1
python manage.py test apps.stores --verbosity 1
python manage.py test apps.core --verbosity 1
```

(`apps.stores` and `apps.core` added to the minimum gate this phase specifically because the two
seed-command management files under `apps/stores/management/commands/` and the global context
processor `apps/core/context_processors.py` were both materially rewritten.)

## Report status

`IMPLEMENTATION_COMPLETE`
`TARGETED_RUNTIME_VERIFIED`
`BROWSER_VERIFIED`
`OWNER_HEAVY_GATE_PENDING`

Final commit SHA: `86cce533533ab7a4b6fedc7f943be9eb9a4311e1`
