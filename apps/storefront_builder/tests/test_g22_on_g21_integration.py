"""G2.2-on-G2.1 integration proof.

This suite is the mandatory integration verification requested when G2.2
(Preview media render consistency) was transplanted onto the durable Golden
checkpoint ``golden/g2-1-editing-readiness`` (which contains G1 + G2 + G2.1).

It proves the ACTUAL reported bug path end-to-end on top of a real Published
**Golden** layout, and — critically — proves that G2.1's editing-readiness
contract still holds after the G2.2 change:

    VISIBLE IN PREVIEW  ->  SOURCE IDENTITY RESOLVES  ->  EDIT ENDPOINT OPENS (200)

Everything runs through the REAL production routes/services (Golden apply
command, real Published->Draft clone, real preview route, real Builder media
edit route). Nothing is mocked.
"""

import shutil
import tempfile
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.services import layout_service, render_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _img(name="g22g21.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (20, 40, 60)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class G22OnGoldenG21IntegrationTests(TestCase):
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
        # Real Golden setup: catalog/content + baseline apply + Golden
        # customization + publish (G1 + G2 + G2.1 all exercised).
        call_command("apply_golden_reference_storefront", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)
        # Opening the Builder clones Published -> Draft, exactly like a merchant
        # opening the editor. The Preview renders this Draft.
        self.draft = layout_service.get_or_create_draft(self.store)
        self.home = self.draft.get_page("home")
        self.user = User.objects.create_user(
            username="g22g21_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.user)
        self.host = f"{self.store.admin_subdomain}.rastisi.localhost"

    def _hero_section(self):
        for s in self.home.sections.order_by("order"):
            if s.section_key == "hero_banner":
                return s
        self.fail("Golden home page has no hero_banner section")

    def _preview_html(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, "Golden Builder Preview must render 200")
        return resp.content.decode("utf-8")

    # --------------------------------------------------------------- G2.2 bug path on Golden

    def test_golden_asset_backed_hero_renders_in_preview_and_stays_editable(self):
        """The full reported path on a real Published Golden layout:
        Published Golden -> Draft clone -> asset-backed HeroSlide with empty
        legacy desktop_image -> real Preview route -> HTTP 200 + MediaAsset
        URL rendered; AND the G2.1 editability chain still holds for that
        exact placement (visible -> identity -> edit endpoint 200)."""
        hero = self._hero_section()
        # Take a hero slide that the renderer actually shows in Preview.
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        self.assertGreater(len(rendered), 0, "Golden hero must render at least one slide")
        slide = rendered[0]

        # Convert this rendered placement to be MediaAsset-backed with an EMPTY
        # legacy desktop_image — the exact post-clone state that crashed.
        asset = MediaAsset.objects.create(store=self.store, image=_img("golden-hero.png"))
        # Ensure it is section-scoped to the Draft hero section (so it is a
        # real Draft placement, editable + rendered).
        slide.section = hero
        slide.desktop_asset = asset
        slide.desktop_image = ""
        slide.save()
        slide.refresh_from_db()
        self.assertEqual(slide.desktop_asset_id, asset.pk)
        self.assertFalse(bool(slide.desktop_image))

        # G2.2: Preview renders 200 and uses the MediaAsset URL (no ValueError).
        html = self._preview_html()
        self.assertIn(asset.image.url, html)
        self.assertNotIn("has no file associated with it", html)

        # G2.1 chain preserved: VISIBLE -> SOURCE IDENTITY -> EDIT ENDPOINT 200.
        still_rendered = [s.pk for s in render_service._scoped_hero_slides(self.store, hero)]
        self.assertIn(slide.pk, still_rendered, "asset-backed slide must remain visible in Preview")
        edit_url = reverse(
            "dashboard:storefront-builder-section-media-edit",
            args=[hero.pk, "hero-slides", slide.pk],
        )
        resp = self.client.get(edit_url, HTTP_HOST=self.host)
        self.assertEqual(
            resp.status_code, 200,
            "a visibly-rendered asset-backed hero must still have a working edit path after G2.2",
        )

    def test_golden_hero_media_list_still_lists_asset_backed_placement(self):
        """G2.1 media manager must still surface the asset-backed placement
        (not falsely report zero) after G2.2."""
        hero = self._hero_section()
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        slide = rendered[0]
        asset = MediaAsset.objects.create(store=self.store, image=_img("golden-hero-list.png"))
        slide.section = hero
        slide.desktop_asset = asset
        slide.desktop_image = ""
        slide.save()

        list_url = reverse(
            "dashboard:storefront-builder-section-media-list", args=[hero.pk, "hero-slides"],
        )
        resp = self.client.get(list_url, HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        listed_pks = [i.pk for i in resp.context["items"]]
        self.assertIn(slide.pk, listed_pks)

    def test_golden_preview_renders_200_unmodified(self):
        """Sanity: the untouched Golden Draft Preview renders 200 (G1/G2/G2.1
        composition intact under the G2.2 templates)."""
        html = self._preview_html()
        self.assertNotIn("has no file associated with it", html)
        self.assertNotIn('src=""', html)
