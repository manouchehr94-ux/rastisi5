# U1A Decision — `appearance_registry.TEMPLATE_REGISTRY` vs. `layout_preset_registry`

**Phase:** U1A (Engine Metadata Contract Foundation)
**Type:** Architecture decision only — no functional registry migration, no
runtime redirection, no code deleted or deprecated in this document's scope.
**Status:** Decided. Amended once (pre-commit external review) to add
Section 3a — the merchant-facing "one Ready Template" clarification.

## 1. Question being answered

R1 (`docs/reports/...` R1 gap matrix, Section E/O/P) flagged that two
registries are both "live" in `apps/storefront_builder`:

- `appearance_registry.TEMPLATE_REGISTRY` (`TemplateDefinition`)
- `layout_preset_registry.LAYOUT_PRESET_REGISTRY` (`LayoutPresetDefinition`)

and asked, for U1A: which one should become authoritative for future
Ready Templates (U7), and which is the retirement candidate?

## 2. What re-tracing both call paths actually found

Re-reading both modules end to end (not just grepping for "is it imported")
shows they are **not two competing implementations of the same concept**.
They answer two different questions, and always have:

| | `TEMPLATE_REGISTRY` (`appearance_registry.TemplateDefinition`) | `LAYOUT_PRESET_REGISTRY` (`layout_preset_registry.LayoutPresetDefinition`) |
|---|---|---|
| Answers | "What do things look like?" | "What content appears, on which pages, in what settings?" |
| Fields | `font`, `radius`, `button_radius`, `button_style`, `density`, `motion`, `type_scale`, `content_width`, `grid_density`, `card_shadow`, `card_hover`, `hero_style`, `swatch` (`appearance_registry.py:78-111`) | `appearance` (**structural subset only, never color**), `default_palette_slug` (a *suggestion*, never a lock), `header`/`footer` overlay dicts, `pages: dict[page_type, tuple[PresetSectionEntry,...]]` (`layout_preset_registry.py:84-118`) |
| Selected via | `StorefrontLayoutVersion.appearance_config["template_slug"]`, validated on every save (`layout_service.py:345-348`) | Applied once, imperatively, via `preset_service.apply_preset(draft, preset)` — not a persistent "current preset" selection at all |
| Owns color | Yes — this is the actual palette/token owner | **Explicitly never** — the module's own docstring states the owner decision in plain terms: *"Palette همیشه Global می‌ماند"* ("Palette always stays Global") (`layout_preset_registry.py:14-17`) |
| Relationship to the retired Family system | Independent; predates and survives the Family retirement untouched | The module docstring explicitly distinguishes itself from the retired `preset_registry.py`/`family_registry.py`: *"این ماژول جایگزین/گسترشِ preset_registry.py نیست... آن سیستم یک بسته‌یِ توکن درونِ یک Family خاص است... این ماژول یک مفهومِ کاملاً جدا و مستقل از Family است"* (`layout_preset_registry.py:1-11`) |

Both are exercised in production code today: `template_slug` is validated in
`layout_service.validate_appearance_config` on every appearance save and is
covered by ~30 assertions in `tests/test_appearance.py`; `LayoutPresetDefinition`
is applied via `preset_service.apply_preset`, itself invoked from the
`storefront_apply_layout_preset` view and covered extensively in
`tests/test_preset_service.py` and `tests/test_layout_preset_registry.py`.
Neither is dormant, and — contrary to a first-pass reading of "two things
that are both live" — neither is a duplicate of the other.

## 3. Decision

**No consolidation and no retirement.** Both registries remain authoritative,
each for the layer it already owns:

- `appearance_registry.TEMPLATE_REGISTRY` remains authoritative for
  **style/token defaults** (typography, radius, density, motion, content
  width, card shadow/hover, hero shape).
- `layout_preset_registry.LAYOUT_PRESET_REGISTRY` remains authoritative for
  **content/section composition** across all six `StorefrontPage` types,
  plus header/footer extra blocks.

A future U7 "Ready Template" recipe is the **pairing** of one
`LayoutPresetDefinition` with a suggested `TemplateDefinition` — a
combination of the two existing registries, not a replacement of either.
This is already loosely true today: `LayoutPresetDefinition.default_palette_slug`
is exactly this kind of suggestion at the color layer; a parallel
"suggested `template_slug`" field on `LayoutPresetDefinition` would be the
natural, additive way to complete the pairing in a later phase — **not
proposed or implemented here**, since it would be a functional registry
change and is explicitly out of U1A's scope.

This decision **corrects** the framing in the R1 report's Section E/O/P,
which characterized the pair as "two coexisting mechanisms needing
consolidation." That framing was accurate at the surface level (both are
live) but did not distinguish that they operate at different layers by
original design, not by accident. U1A's mandate ("trace both live call
paths once more... produce a concise architecture decision") exists
precisely to catch this kind of correction before wasted consolidation work
is scheduled into U7 — so it is reported here rather than carried forward
silently.

## 3a. Correction (U1A pre-commit review) — the merchant must never see two "Templates"

External review of this decision correctly flagged a gap: Section 3 above
settles the *internal* question (neither registry is a duplicate of the
other, both stay), but says nothing about what a merchant is allowed to
perceive. That needs to be stated explicitly, now, so U7 doesn't
accidentally expose two separate "choose a Template" surfaces just because
two separate Python registries happen to exist underneath.

**Explicit rule for U7 and beyond:** `TEMPLATE_REGISTRY` and
`LAYOUT_PRESET_REGISTRY` may remain two internal implementation registries
— that internal split is correct and is not being undone — but the
merchant-facing product must never expose them as two independent
"Templates" to choose between. U7 must introduce a single **Ready Template**
recipe/wrapper concept that *composes* the relevant internal ingredients
behind one merchant-facing choice. Conceptually (not a storage schema, and
not decided here):

```
ReadyTemplate
  - composition preset            (→ LayoutPresetDefinition today)
  - appearance/token preset       (→ TemplateDefinition today)
  - component variant selections  (→ SectionDefinition.variants, U1A)
  - global-region variant selections   (header/footer — not yet a variant
                                         axis; see R1 gap matrix Section F)
  - template/version provenance   (→ variant_contract.build_template_provenance
                                     shape, U1A — not yet written anywhere)
```

**What is and is not decided by this correction:**

- Decided: the merchant-facing unit of choice in U7 is one `ReadyTemplate`,
  not "pick a layout preset, then separately pick a template/palette."
- Not decided: `ReadyTemplate`'s exact storage shape, whether it is a new
  registry, a wrapper function, a paired-key convention, or something else
  — that is explicitly a U7 architecture decision, out of scope here.
- Not implemented: no `ReadyTemplate` code, registry, model, or field exists
  after this correction. This section is documentation/architecture
  clarification only, per the explicit boundary of this correction pass.

## 4. Compatibility obligations (for any future phase touching either registry)

- Every `StorefrontLayoutVersion.appearance_config["template_slug"]` value
  currently stored must keep resolving through `appearance_registry.get_template`
  exactly as it does today; `layout_service.validate_appearance_config`
  (`layout_service.py:345-348`) is the single enforcement point and must not
  be bypassed by any future Ready Template feature.
- `LayoutPresetDefinition.default_palette_slug` must keep behaving as a
  non-clobbering suggestion (`preset_service.py:206-210`: only applied "اگر
  مرچنت هنوز هیچ Paletteای انتخاب نکرده") — a future paired
  "suggested `template_slug`" field, if added, must follow the identical
  non-clobbering rule, not silently override a merchant's chosen template.
- `LayoutPresetDefinition.appearance`'s structural-only subset (never color)
  must stay disjoint from what `TemplateDefinition` owns, to avoid the two
  registries drifting into overlapping responsibility for the same field.

## 5. What this decision does NOT do

- Does not add a `template_slug` (or equivalent) field to `LayoutPresetDefinition`.
- Does not change `layout_service.py`, `appearance_registry.py`, or
  `layout_preset_registry.py` behavior in any way.
- Does not migrate, rename, or deprecate any stored `template_slug` or
  `layout_preset_key` value.
- Does not block any future phase from building the "recipe = preset +
  template pairing" concept — it only records that both registries should
  be the two ingredients of that pairing, not consolidated into one.
