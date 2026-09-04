"""Tests for the Golden Reference Storefront G1 setup command
(``apply_golden_reference_storefront``).

The Golden Reference Storefront is the customized ``rasti-mode-demo`` store —
a visually complete premium multi-brand fashion/lifestyle storefront produced
entirely through existing production contracts (the demo seed for the real
catalog/content, then the ``fashion_promo_catalog`` Ready Template baseline
customized via the normal preset/appearance/publish services).

Contracts asserted here (see
``docs/superpowers/plans/2026-09-04-golden-reference-storefront-g1-plan.md``):

- The command runs the idempotent demo seed, then applies + publishes the
  Golden composition. A published V2 layout exists afterward (so the public
  route uses the universal shell, not the legacy fallback).
- Provenance stays honest: the applied baseline is still
  ``fashion_promo_catalog`` — the Golden customization is NOT a 51st Ready
  Template and never mutates the A8 registry.
- The Golden shell selections are applied: header ``marketplace_search_first``,
  footer ``premium_columns``, mobile bottom nav ``five_item``, palette
  ``theme-forest-cream``.
- The Home composition is the approved 13-section commercial rhythm.
- Re-running converges (idempotent): no duplicate stores/products, exactly one
  published layout, identical section order.
- Tenant isolation: only ``rasti-mode-demo`` is ever touched.

MEDIA_ROOT is overridden so uploaded media never lands under the real
project ``media/``.
"""

import shutil
import tempfile
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Product
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import layout_service
from apps.stores.models import Store

STORE_SLUG = "rasti-mode-demo"
OTHER_REAL_SLUG = "rastisi-fashion-test"

GOLDEN_HOME_SECTIONS = [
    "announcement_bar",
    "hero_banner",
    "category_grid",
    "multi_banner",
    "product_section",   # newest
    "brand_carousel",
    "multi_banner",
    "product_section",   # best sellers
    "story_rail",
    "product_section",   # discounted / special offer
    "collection_tiles",
    "trust_features",
    "newsletter",
]


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApplyGoldenReferenceStorefrontCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def _run(self, *extra_args):
        call_command("apply_golden_reference_storefront", *extra_args, stdout=StringIO())

    def _store(self) -> Store:
        return Store.objects.get(slug=STORE_SLUG)

    # ------------------------------------------------------------------ Publish

    def test_provisions_a_published_universal_layout(self):
        self._run()
        layout = layout_service.get_or_create_layout(self._store())
        self.assertIsNotNone(layout.published_version_id)

    def test_provenance_is_still_the_fashion_promo_catalog_baseline(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        self.assertEqual(
            published.template_provenance.get("template", {}).get("key"),
            "fashion_promo_catalog",
        )

    # ------------------------------------------------------------------ Shell

    def test_golden_shell_variants_are_applied(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        header = published.effective_header_config()
        footer = published.effective_footer_config()
        appearance = published.effective_appearance_config()
        self.assertEqual(header.get("header_variant"), "marketplace_search_first")
        self.assertEqual(footer.get("footer_variant"), "premium_columns")
        self.assertEqual(footer.get("mobile_nav_variant"), "five_item")
        self.assertEqual(appearance.get("palette_slug"), "theme-forest-cream")

    def test_cart_shortcut_remains_enabled_in_header(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        self.assertTrue(published.effective_header_config().get("show_cart", True))

    # ------------------------------------------------------------------ Home

    def test_home_composition_matches_the_golden_commercial_rhythm(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            GOLDEN_HOME_SECTIONS,
        )

    def test_three_product_sections_use_distinct_data_sources(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        product_sections = [
            s for s in home.sections.order_by("order") if s.section_key == "product_section"
        ]
        sources = [s.settings.get("data_source") for s in product_sections]
        self.assertEqual(sources, ["newest", "best_sellers", "discounted"])

    def test_no_catalog_ids_are_hardcoded_into_product_section_settings(self):
        """Product data must resolve at render time from Catalog via
        ``data_source`` — never by baking product IDs into Builder JSON."""
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        for section in home.sections.filter(section_key="product_section"):
            self.assertEqual(section.settings.get("product_ids", []), [])

    # ------------------------------------------------------------------ Idempotence

    def test_second_run_converges_without_duplicates(self):
        self._run()
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store).count(), 50)
        layout = layout_service.get_or_create_layout(store)
        self.assertIsNotNone(layout.published_version_id)
        home = layout.published_version.home_page()
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            GOLDEN_HOME_SECTIONS,
        )

    # ------------------------------------------------------------------ Invariants

    def test_a8_ready_template_registry_is_unchanged(self):
        before = {p.key for p in lpr.list_ready_templates()}
        self._run()
        after = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(before, after)
        self.assertEqual(len(after), 50)

    def test_never_touches_another_store(self):
        other = Store.objects.create(
            name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE
        )
        self._run()
        other.refresh_from_db()
        self.assertEqual(other.name, "فروشگاه لباس تستی راستی سی")
        from apps.storefront_builder.models import StorefrontLayout

        self.assertFalse(StorefrontLayout.objects.filter(store=other).exists())
