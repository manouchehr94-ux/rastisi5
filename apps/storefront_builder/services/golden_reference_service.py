"""Golden Reference Storefront (G1) — composition service.

The Golden Reference Storefront is the customized ``rasti-mode-demo`` store: a
visually complete premium multi-brand fashion/lifestyle storefront that a
prospective merchant can visit to understand what a finished RastiSi store
looks like.

Design authority:
``docs/superpowers/specs/2026-09-04-golden-reference-storefront-design.md``
Executable plan:
``docs/superpowers/plans/2026-09-04-golden-reference-storefront-g1-plan.md``

This module deliberately reuses the existing production contracts and adds no
parallel architecture:

- It builds an **in-memory** ``LayoutPresetDefinition`` derived from the
  officially registered ``fashion_promo_catalog`` Ready Template
  (``dataclasses.replace`` over the registered recipe). It keeps that recipe's
  ``key``/``version`` so ``template_provenance`` stays honest — the store is
  still built from the ``fashion_promo_catalog`` baseline. It is **never
  registered**, so the A8 catalog stays at exactly 50 templates (this is not a
  51st Ready Template).
- It customizes only what a merchant may legitimately customize through the
  store contracts: the identity **palette** (``theme-forest-cream``), the
  **global shell** variants (header/footer/mobile-nav), the typed
  ``store_appearance`` manifest to match, and the **Home composition**.
- It applies the customized recipe to the store's active Draft with the
  ordinary Draft-only ``preset_service.apply_preset`` contract and publishes
  with ``layout_service.publish``. (It deliberately does NOT use
  ``apply_preset_with_checkpoint`` — see ``apply_golden_reference_storefront``'s
  docstring for why the checkpoint path would be a no-op here.)

Re-running converges (idempotent): ``apply_preset`` fully replaces the page
composition and rewrites appearance/header/footer from the recipe every run, so
repeated runs rebuild the same published state.

Guardrails: this service only ever operates on the store handed to it (the
management command scopes that to the fixed ``rasti-mode-demo`` slug). It never
writes commerce truth (price/stock/SKU) and bakes no catalog IDs into settings
— product sections resolve their products at render time from Catalog via
``data_source``.
"""

from __future__ import annotations

import dataclasses

from apps.storefront_builder.layout_preset_registry import (
    LayoutPresetDefinition,
    PresetSectionEntry,
    get_layout_preset,
)
from apps.storefront_builder.services import layout_service, preset_service

#: The official Ready Template used as the Golden baseline (unchanged; still the
#: recorded provenance). Chosen because it is already the ``rasti-mode-demo``
#: seed's applied template and carries the widest commercial fashion vocabulary.
GOLDEN_BASELINE_TEMPLATE_KEY = "fashion_promo_catalog"

#: Identity palette (registered) — teal/green primary, charcoal contrast, gold
#: accent, warm/light neutral surfaces. No new/parallel color system.
GOLDEN_PALETTE_SLUG = "theme-forest-cream"

#: Global shell variants (all existing registered variants).
GOLDEN_HEADER_VARIANT = "marketplace_search_first"
GOLDEN_FOOTER_VARIANT = "premium_columns"
GOLDEN_BOTTOM_NAV_VARIANT = "five_item"


def _golden_store_appearance(base_manifest: dict) -> dict:
    """Return a schema-v1 store-appearance manifest matching the Golden shell.

    Only the ``header``/``footer``/``bottom_nav`` family selections diverge from
    the baseline recipe; everything else (hero/card/layout/etc.) is inherited so
    the commercial DNA of ``fashion_promo_catalog`` is preserved.
    """
    selections = dict((base_manifest or {}).get("selections", {}))
    selections["header"] = f"header.{GOLDEN_HEADER_VARIANT}.v1"
    selections["footer"] = f"footer.{GOLDEN_FOOTER_VARIANT}.v1"
    selections["bottom_nav"] = f"bottom_nav.{GOLDEN_BOTTOM_NAV_VARIANT}.v1"
    return {
        "schema_version": 1,
        "selections": selections,
        "settings": dict((base_manifest or {}).get("settings", {})),
    }


def _golden_home_composition() -> tuple[PresetSectionEntry, ...]:
    """The approved 12-section Home in commercial rhythm.

    Editorial impact -> discovery -> products(new) -> campaign -> brand ->
    promo -> products(best) -> story -> promotion -> collections -> trust ->
    newsletter. Every ``section_key`` is an existing registered section. Only
    neutral, enum-driven settings are provided; no Store IDs, prices, SKUs, or
    inventory are ever written here.
    """
    # Note on the announcement: it is rendered by the global header itself
    # (``header_config.announcement_enabled`` -> the header partial includes
    # ``_shared/announcement_bar.html``). Adding a separate ``announcement_bar``
    # *section* here would render the strip twice (a real defect observed in
    # visual QA), so the announcement lives only in the shell — not the page
    # composition.
    return (
        # 1) Editorial hero (store/section HeroSlides render at runtime)
        PresetSectionEntry("hero_banner", {"hero_style": "overlay"}),
        # 2) Quick categories (discovery)
        PresetSectionEntry(
            "category_grid",
            {"display_mode": "circular", "item_limit": 8, "title": "دسته‌بندی‌ها"},
        ),
        # 3) Featured campaign / editorial promotion
        PresetSectionEntry("multi_banner"),
        # 4) New arrivals
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "newest",
                "display_mode": "carousel",
                "title": "جدیدترین‌ها",
                "item_limit": 8,
            },
        ),
        # 5) Brand strip
        PresetSectionEntry(
            "brand_carousel",
            {"display_mode": "carousel", "title": "برندها"},
        ),
        # 6) Promo banners
        PresetSectionEntry("multi_banner"),
        # 7) Most popular / most viewed (uses views_count, a production-written
        #    metric — see ruling in the G1 plan; avoids fabricating Order/
        #    payment/shipping infrastructure just to populate a Home section).
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "most_viewed",
                "display_mode": "grid",
                "title": "محبوب‌ترین‌ها",
                "item_limit": 8,
            },
        ),
        # 8) Story / editorial rail
        PresetSectionEntry("story_rail"),
        # 9) Special offer / promotion
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "discounted",
                "display_mode": "campaign_band",
                "title": "پیشنهاد ویژه",
                "item_limit": 8,
            },
        ),
        # 10) Curated collections
        PresetSectionEntry(
            "collection_tiles",
            {"tile_style": "grid", "title": "کالکشن‌های منتخب"},
        ),
        # 11) Trust / service features
        PresetSectionEntry("trust_features"),
        # 12) Newsletter
        PresetSectionEntry(
            "newsletter",
            {
                "title": "عضویت در خبرنامه",
                "subtitle": "از جدیدترین محصولات و پیشنهادهای ویژه باخبر شوید",
                "button_label": "عضویت",
            },
        ),
    )


def build_golden_preset() -> LayoutPresetDefinition:
    """Build the in-memory Golden ``LayoutPresetDefinition``.

    Derived from the registered ``fashion_promo_catalog`` recipe via
    ``dataclasses.replace`` — same ``key``/``version`` (honest provenance),
    customized palette/shell/manifest/Home composition. Never registered.
    """
    base = get_layout_preset(GOLDEN_BASELINE_TEMPLATE_KEY)
    if base is None:  # pragma: no cover - defensive; the baseline is always registered
        raise LookupError(
            f"Golden baseline Ready Template «{GOLDEN_BASELINE_TEMPLATE_KEY}» is not registered."
        )

    header = dict(base.header or {})
    header.update(
        {
            "header_variant": GOLDEN_HEADER_VARIANT,
            "sticky": True,
            "announcement_enabled": True,
            "show_search": True,
            "show_account": True,
            "show_wishlist": True,
            "show_cart": True,
        }
    )

    footer = dict(base.footer or {})
    footer.update(
        {
            "footer_variant": GOLDEN_FOOTER_VARIANT,
            "mobile_nav_variant": GOLDEN_BOTTOM_NAV_VARIANT,
        }
    )

    pages = dict(base.pages)
    pages["home"] = _golden_home_composition()

    return dataclasses.replace(
        base,
        default_palette_slug=GOLDEN_PALETTE_SLUG,
        store_appearance=_golden_store_appearance(base.store_appearance),
        header=header,
        footer=footer,
        pages=pages,
    )


def ensure_golden_view_signals(store) -> int:
    """Give the demo store's products deterministic ``views_count`` so a
    ``most_viewed`` presentation (and general realism) has data.

    ``views_count`` is a display/analytics metric that IS genuinely written in
    production (``apps.catalog.views.product_detail`` on every view), so seeding
    it for a demo store is legitimate content, not commerce truth. The value is
    derived purely from each product's stable PK, so within a store it is
    reproducible and idempotent — repeated runs recompute the same value and
    never accumulate. (Absolute values differ after a ``--reset`` that rebuilds
    the store with fresh PKs; only the within-store ranking matters for the
    "most viewed" section.) Returns rows rewritten.
    """
    from apps.catalog.models import Product

    updated = 0
    for product in Product.objects.filter(store=store).order_by("pk"):
        views = 120 + (product.pk * 53) % 3400
        if product.views_count != views:
            product.views_count = views
            product.save(update_fields=["views_count", "updated_at"])
            updated += 1
    return updated


def apply_golden_reference_storefront(store, *, user=None):
    """Apply + publish the Golden composition onto ``store``.

    Applies the in-memory Golden recipe to the store's active Draft via the
    ordinary Draft-only contract (``preset_service.apply_preset`` on
    ``layout_service.get_or_create_draft``), then ``layout_service.publish``.

    Why ``apply_preset`` and not ``apply_preset_with_checkpoint`` here: the
    Golden recipe deliberately keeps the baseline's ``key``/``version`` (so
    ``template_provenance`` honestly records ``fashion_promo_catalog``). The
    checkpoint entry point treats a same-``(key, version)`` recipe whose
    recorded baseline snapshot still matches the draft as a no-op (a
    history-cleanliness optimization) — which would skip the Golden
    customization entirely because the demo seed just applied that same
    baseline key. The Golden setup is not a merchant "switch template" action
    (it needs no undo checkpoint against merchant-authored content on the
    resettable QA store); it is a deterministic composition apply, so the
    plain Draft-only ``apply_preset`` is the correct, idempotent contract.

    Idempotent: ``apply_preset`` fully replaces the page composition and rewrites
    appearance/header/footer from the recipe every run, so repeated runs
    converge to the same published state.

    Returns the published :class:`StorefrontLayoutVersion`.
    """
    ensure_golden_view_signals(store)
    preset = build_golden_preset()
    draft = layout_service.get_or_create_draft(store, user=user)
    preset_service.apply_preset(draft, preset)
    return layout_service.publish(store, user=user)
