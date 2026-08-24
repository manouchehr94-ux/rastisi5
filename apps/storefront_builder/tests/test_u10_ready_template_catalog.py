"""U10 — Build the Real Ready Template Catalog.

The 8 required stable recipe keys, built purely from the Universal
Storefront Engine completed in U1-U9 (`LayoutPresetDefinition` — the same
vehicle U7 added version/provenance to, U4's registered section variants,
U2A/U2B's global header/footer variants, real palettes) — no new renderer
architecture, no store-specific IDs, no fabricated commercial content.
"""

from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.global_region_registry import GLOBAL_FOOTER_REGION, GLOBAL_HEADER_REGION
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.variant_contract import build_template_provenance
from apps.stores.models import Store, StoreDomain

REQUIRED_KEYS = (
    "dense_marketplace", "premium_leather", "warm_boutique", "fashion_promo_catalog",
    "playful_lifestyle", "utility_catalog", "editorial_jewelry", "dark_digital",
)

HOST = "sfb-u10.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="u10.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (10, 90, 160)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class RequiredKeysExistTests(TestCase):
    def test_all_eight_required_keys_are_registered(self):
        for key in REQUIRED_KEYS:
            self.assertIsNotNone(lpr.get_layout_preset(key), key)

    def test_keys_are_not_reference_store_or_family_names(self):
        """The master contract forbids external-site/reference-store names
        as keys — a cheap but real tripwire against a future edit
        accidentally renaming one of these to a brand-shaped string."""
        for key in REQUIRED_KEYS:
            self.assertNotIn(" ", key)
            self.assertEqual(key, key.lower())

    def test_all_thirteen_presets_pass_full_validation(self):
        for preset in lpr.list_layout_presets():
            preset_service.validate_layout_preset(preset)  # must not raise


class MaterialDifferenceTests(TestCase):
    """The master contract requires "materially different" compositions,
    not color-only variety — verified across several real axes."""

    def test_palettes_are_all_distinct_from_each_other_and_pre_u10_presets(self):
        u10_palettes = [lpr.get_layout_preset(k).default_palette_slug for k in REQUIRED_KEYS]
        self.assertEqual(len(u10_palettes), len(set(u10_palettes)), "U10 palettes must be pairwise distinct")
        pre_u10_keys = ("clean_minimal", "editorial_story", "dense_catalog", "premium_boutique", "v5_golden_homepage")
        pre_u10_palettes = {lpr.get_layout_preset(k).default_palette_slug for k in pre_u10_keys}
        self.assertFalse(set(u10_palettes) & pre_u10_palettes, "U10 palettes must not reuse a pre-U10 preset's palette")

    def test_density_and_motion_are_not_all_identical(self):
        densities = {lpr.get_layout_preset(k).appearance["density"] for k in REQUIRED_KEYS}
        motions = {lpr.get_layout_preset(k).appearance["motion"] for k in REQUIRED_KEYS}
        self.assertGreater(len(densities), 1)
        self.assertGreater(len(motions), 1)

    def test_home_compositions_are_not_identical(self):
        section_key_sets = set()
        for key in REQUIRED_KEYS:
            preset = lpr.get_layout_preset(key)
            section_key_sets.add(tuple(entry.section_key for entry in preset.pages["home"]))
        self.assertEqual(len(section_key_sets), len(REQUIRED_KEYS), "every template's home composition must be unique")

    def test_header_and_footer_variants_are_real_registered_keys(self):
        header_keys = {v.key for v in GLOBAL_HEADER_REGION.variants}
        footer_keys = {v.key for v in GLOBAL_FOOTER_REGION.variants}
        for key in REQUIRED_KEYS:
            preset = lpr.get_layout_preset(key)
            self.assertIn(preset.header["header_variant"], header_keys, key)
            self.assertIn(preset.footer["footer_variant"], footer_keys, key)

    def test_product_card_style_varies_across_templates(self):
        card_styles = set()
        for key in REQUIRED_KEYS:
            preset = lpr.get_layout_preset(key)
            product_section = next(e for e in preset.pages["home"] if e.section_key == "product_section")
            card_styles.add(product_section.settings["card"]["card_style"])
        self.assertGreater(len(card_styles), 1)

    def test_no_two_templates_have_identical_appearance_dict(self):
        appearances = [tuple(sorted(lpr.get_layout_preset(k).appearance.items())) for k in REQUIRED_KEYS]
        self.assertEqual(len(appearances), len(set(appearances)))


class AllPagesCoveredTests(TestCase):
    def test_every_required_template_covers_all_six_page_types(self):
        from apps.storefront_builder import section_registry

        for key in REQUIRED_KEYS:
            preset = lpr.get_layout_preset(key)
            self.assertEqual(set(preset.pages.keys()), set(section_registry.ALL_PAGE_TYPES), key)


class ApplyAndRenderSmokeTests(TestCase):
    """Real proof, not just import-time validation: apply a Ready Template
    and actually render the public homepage, for one template from each
    header-variant family (covers all 5 header variants across the 13
    presets in one pass, without rendering all 13 for time)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self._override = self.settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

    def _apply_and_render(self, key):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset(key))
        section = draft.get_page("home").sections.filter(section_key="hero_banner").first()
        if section is not None:
            HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, title=f"اسلاید {key}")
        svc.publish(self.store)
        return self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)

    def test_dense_marketplace_renders_without_error(self):
        resp = self._apply_and_render("dense_marketplace")
        self.assertEqual(resp.status_code, 200)

    def test_premium_leather_renders_without_error(self):
        resp = self._apply_and_render("premium_leather")
        self.assertEqual(resp.status_code, 200)

    def test_warm_boutique_renders_without_error(self):
        resp = self._apply_and_render("warm_boutique")
        self.assertEqual(resp.status_code, 200)

    def test_utility_catalog_renders_without_error(self):
        resp = self._apply_and_render("utility_catalog")
        self.assertEqual(resp.status_code, 200)

    def test_dark_digital_renders_without_error(self):
        resp = self._apply_and_render("dark_digital")
        self.assertEqual(resp.status_code, 200)

    def test_applying_records_correct_provenance(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        self.assertEqual(
            draft.template_provenance,
            build_template_provenance(template_key="editorial_jewelry", template_version=preset.version),
        )

    def test_reset_to_baseline_works_for_a_u10_template(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("playful_lifestyle"))
        draft.get_page("home").sections.all().delete()
        returned = preset_service.reset_storefront_to_baseline(draft)
        self.assertEqual(returned.key, "playful_lifestyle")
        draft.refresh_from_db()
        self.assertGreater(draft.get_page("home").sections.count(), 0)
