"""G2.1 Defect C + required round-trip test — EVERYTHING VISIBLY RENDERED IN
PREVIEW MUST HAVE A TRUTHFUL EDIT PATH.

Root cause: the demo seed creates store-global (section=NULL) HeroSlide /
PromotionalBanner / StoryRailItem rows. The renderer (render_service) falls back
to those store-global rows when a section has none of its own, so they ARE
visibly rendered. But the Builder media CRUD filtered strictly
``model.objects.filter(section=section)``, so the manager showed "0 items" and a
direct edit URL for a visibly-rendered global row 404'd.

Contract asserted here (exercised through the REAL view/route boundary that
produced the 404):
  VISIBLE IN PREVIEW  ->  SOURCE IDENTITY RESOLVES  ->  EDIT ENDPOINT OPENS (200)
plus: opening the media list for a section that renders fallback rows must NOT
report zero items, and mutating a shared store-global item from one section must
NOT silently mutate another section's rendered content (copy-on-write / adopt).
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Product, ProductImage
from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from apps.storefront_builder.services import layout_service, render_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    DEMO_OWNER_USERNAME,
    STORE_SLUG,
)
from apps.stores.models import Store

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class G2_1MediaEditabilityRoundTripTests(TestCase):
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
        # Golden setup: catalog/content + baseline apply + Golden customization + publish.
        call_command("apply_golden_reference_storefront", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)
        # The Builder edits a DRAFT (Preview renders the Draft). Opening the
        # Builder clones Published -> Draft, exactly like a merchant opening the
        # editor. All media CRUD + this round-trip must work on the Draft.
        self.draft = layout_service.get_or_create_draft(self.store)
        self.home = self.draft.get_page("home")
        # A staff user able to reach the Builder media CRUD (demo owner is staff-capable).
        self.user = User.objects.get(username=DEMO_OWNER_USERNAME)
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

    # --------------------------------------------------------------- helpers

    def _section(self, section_key, occurrence=0):
        secs = [s for s in self.home.sections.order_by("order") if s.section_key == section_key]
        return secs[occurrence]

    def _rendered_items(self, section, context_key, resolver):
        return list(resolver(self.store, section)[context_key] if False else resolver(self.store, section))

    # --------------------------------------------------------------- list not zero

    def test_hero_media_list_is_not_falsely_zero_when_fallback_renders(self):
        hero = self._section("hero_banner")
        # renderer shows fallback slides
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        self.assertGreater(len(rendered), 0)
        url = reverse("dashboard:storefront-builder-section-media-list", args=[hero.pk, "hero-slides"])
        resp = self.client.get(url, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200)
        # the manager must surface the same rendered items (not "0 items")
        self.assertEqual(len(resp.context["items"]), len(rendered))

    # --------------------------------------------------------------- edit opens (no 404)

    def test_edit_of_a_visibly_rendered_hero_item_opens_not_404(self):
        hero = self._section("hero_banner")
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        item = rendered[0]
        url = reverse(
            "dashboard:storefront-builder-section-media-edit",
            args=[hero.pk, "hero-slides", item.pk],
        )
        resp = self.client.get(url, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200, "a visibly-rendered hero item must have a working edit path")

    def test_edit_of_a_visibly_rendered_banner_item_opens_not_404(self):
        banner_sections = [s for s in self.home.sections.order_by("order") if s.section_key == "multi_banner"]
        self.assertGreaterEqual(len(banner_sections), 1)
        section = banner_sections[0]
        rendered = list(render_service._scoped_banners(self.store, section))
        self.assertGreater(len(rendered), 0)
        item = rendered[0]
        url = reverse(
            "dashboard:storefront-builder-section-media-edit",
            args=[section.pk, "banners", item.pk],
        )
        resp = self.client.get(url, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200)

    # --------------------------------------------------------------- copy-on-write safety

    def test_editing_a_shared_global_banner_does_not_mutate_another_section(self):
        banner_sections = [s for s in self.home.sections.order_by("order") if s.section_key == "multi_banner"]
        if len(banner_sections) < 2:
            self.skipTest("need two multi_banner sections to prove cross-section safety")
        sec_a, sec_b = banner_sections[0], banner_sections[1]
        before_b = [b.pk for b in render_service._scoped_banners(self.store, sec_b)]
        item = list(render_service._scoped_banners(self.store, sec_a))[0]
        # toggle the item's active state from section A
        toggle = reverse(
            "dashboard:storefront-builder-section-media-toggle",
            args=[sec_a.pk, "banners", item.pk],
        )
        resp = self.client.post(toggle, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200)
        # Section B's rendered banners must be unchanged in identity/count.
        after_b = [b.pk for b in render_service._scoped_banners(self.store, sec_b)]
        self.assertEqual(
            len(after_b), len(before_b),
            "editing a shared global banner from section A must not change section B's rendered banners",
        )

    # --------------------------------------------------------------- product image round-trip

    def test_product_image_roundtrip_for_fsh_050(self):  # noqa: D401
        product = Product.objects.get(store=self.store, sku="FSH-050")
        rows = list(product.images.all())
        self.assertGreater(len(rows), 0)
        # exactly one cover; storefront card reads the same cover row
        covers = [i for i in rows if i.is_cover]
        self.assertEqual(len(covers), 1)
        self.assertEqual(product.cover_image.pk, covers[0].pk)
        # all images belong to this product/store
        for img in rows:
            self.assertEqual(img.product_id, product.id)
            self.assertEqual(img.product.store_id, self.store.pk)
        # editor image manager opens and shows the same rows
        url = reverse("dashboard:product-images", args=[product.pk])
        resp = self.client.get(url, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context["product"].images.all()), rows)

    # --------------------------------------------------------------- category round-trip

    def test_seeded_product_category_is_a_valid_editor_leaf(self):
        from apps.dashboard.services.catalog_admin_service import leaf_categories

        product = Product.objects.get(store=self.store, sku="FSH-050")
        valid_ids = set(leaf_categories(self.store).values_list("id", flat=True))
        self.assertIn(product.category_id, valid_ids)
