"""G2.3 — Builder/Public content & section-appearance consistency.

Three verified manual-QA defects on the G2.2 stack (base 0276a5d):

  A. Brand section layout breaks after a real Brand-name edit.
  B. Brand + Featured Collections visible/editable in Builder but ABSENT from
     the public storefront after Publish.
  C. The "Section Background" (نوع پس‌زمینه) control is a no-op.

Every test drives REAL production routes/services (Golden apply command, the
real section-settings mutation route, the real Publish service, the real
public storefront GET). Tests prove render/persist semantics, not merely that
JSON contains a key.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, MerchantCollection
from apps.catalog.services.brand_service import update_brand
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder import section_registry
from apps.storefront_builder.services import layout_service, render_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store, StoreMembership

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class _GoldenBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mr = tempfile.mkdtemp()
        cls._ov = override_settings(MEDIA_ROOT=cls._mr)
        cls._ov.enable()

    @classmethod
    def tearDownClass(cls):
        cls._ov.disable()
        shutil.rmtree(cls._mr, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        call_command("apply_golden_reference_storefront", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)
        self.user = User.objects.create_user(username="g23owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.host = f"{self.store.admin_subdomain}.rastisi.localhost"
        self.client = Client(HTTP_HOST=self.host)
        self.client.force_login(self.user)

    # -- helpers ---------------------------------------------------------

    def _draft_home(self):
        draft = layout_service.get_or_create_draft(self.store)
        return draft, draft.get_page("home")

    def _section(self, page, key):
        return page.sections.filter(section_key=key).first()

    def _settings_url(self, section):
        return reverse("dashboard:storefront-builder-section-settings", args=[section.pk])

    def _public_home_html(self):
        resp = self.client.get("/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")

    def _preview_home_html(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")


# =====================================================================
# DEFECT A — Brand section layout after a real Brand-name edit
# =====================================================================
class DefectABrandLayoutAfterEditTests(_GoldenBase):
    def _brand_item_html(self, home):
        """Render the brand section through the REAL production render
        pipeline (build_page_render_items -> responsive_section_wrapper),
        returning the section's rendered HTML."""
        items = render_service.build_page_render_items(home, self.store)
        item = next(i for i in items if i["section"].section_key == "brand_carousel")
        return item, render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True, "is_builder_preview": True},
        )

    def test_brand_edit_preserves_layout_class_contract(self):
        """A real Brand-name edit must NOT change the brand section's layout
        contract: the container class stays the same (carousel -> brand-carousel),
        the brand count is unchanged, and no brand is dropped."""
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        self.assertIsNotNone(brand_sec)

        before_item, before_html = self._brand_item_html(home)
        before_count = len(before_item["context"]["brands"])
        before_mode = before_item["context"]["brand_carousel_settings"]["display_mode"]
        self.assertGreater(before_count, 0)

        # Real content edit of a brand name.
        b = Brand.objects.filter(store=self.store, is_active=True).first()
        update_brand(b, name="برند ویرایش‌شده جدید")

        after_item, after_html = self._brand_item_html(home)
        self.assertEqual(len(after_item["context"]["brands"]), before_count, "brand count changed after a name edit")
        self.assertEqual(after_item["context"]["brand_carousel_settings"]["display_mode"], before_mode, "display_mode drifted after a name edit")

        # carousel display_mode must yield the horizontal-row container class.
        if before_mode == "carousel":
            self.assertIn("brand-carousel", after_html, "carousel brand section lost its .brand-carousel layout container")
        self.assertIn("برند ویرایش‌شده جدید", after_html)

    def test_brand_carousel_has_inline_horizontal_layout_fallback(self):
        """Defect A hardening: the carousel brand layout must not depend
        *solely* on the external home.css `.brand-carousel{display:flex}`
        rule (whose non-application in a reloaded Builder Preview iframe is
        the observed 'cards collapse into a narrow vertical column'). The
        grid branch already ships an inline `grid-template-columns` fallback;
        the carousel branch must ship an equivalent inline `display:flex`
        fallback so a horizontal row survives even if the stylesheet is
        momentarily unavailable."""
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        # Force carousel mode explicitly (the Golden default).
        brand_sec.settings = {**(brand_sec.settings or {}), "display_mode": "carousel"}
        brand_sec.save(update_fields=["settings"])
        item, _html = self._brand_item_html(home)
        section_html = render_to_string(
            "storefront_builder/sections/brand_carousel.html", item["context"],
        )
        # The carousel container must carry an inline flex fallback.
        self.assertIn("brand-carousel", section_html)
        self.assertIn("display:flex", section_html,
                      "carousel brand container has no inline horizontal-layout fallback (Defect A)")


# =====================================================================
# DEFECT B — Brand + Featured Collections round-trip Preview->Publish->Public
# =====================================================================
class DefectBBrandRoundTripTests(_GoldenBase):
    def test_brand_section_survives_publish_into_public(self):
        _, home = self._draft_home()
        brand_sec = self._section(home, "brand_carousel")
        self.assertIsNotNone(brand_sec, "Golden draft must have a brand_carousel section")

        # Preview shows the brand section content.
        preview = self._preview_home_html()
        self.assertIn('data-section-key="brand_carousel"', preview)

        # Edit a brand, then Publish through the real service.
        b = Brand.objects.filter(store=self.store, is_active=True).first()
        update_brand(b, name="برند منتشر")
        layout_service.publish(self.store)

        # Public must still render the brand section + the edited brand.
        public = self._public_home_html()
        self.assertIn("brand-carousel", public, "brand section absent from public after publish")
        self.assertIn("برند منتشر", public, "edited brand content absent from public after publish")


class DefectBFeaturedCollectionsRoundTripTests(_GoldenBase):
    def test_collection_tiles_survive_publish_into_public(self):
        _, home = self._draft_home()
        col_sec = self._section(home, "collection_tiles")
        self.assertIsNotNone(col_sec, "Golden draft must have a collection_tiles section")

        preview = self._preview_home_html()
        self.assertIn('data-section-key="collection_tiles"', preview)

        # Edit a collection name, then publish.
        c = MerchantCollection.objects.filter(store=self.store, is_active=True).first()
        self.assertIsNotNone(c)
        c.name = "کالکشن منتشر"
        c.save(update_fields=["name"])
        layout_service.publish(self.store)

        public = self._public_home_html()
        self.assertIn("کالکشن منتشر", public, "featured collection absent from public after publish")


# =====================================================================
# DEFECT C — Section Background control end-to-end
# =====================================================================
class DefectCSectionBackgroundTests(_GoldenBase):
    def _bg_section(self, home):
        # category_grid is background-aware and has a settings form.
        return self._section(home, "category_grid")

    def _post_settings(self, section, extra):
        base = {
            "title": (section.settings or {}).get("title", ""),
            "display_mode": (section.settings or {}).get("display_mode", "fashion_tiles"),
            "item_limit": (section.settings or {}).get("item_limit", 12),
            "motion_style": "none",
        }
        base.update(extra)
        return self.client.post(self._settings_url(section), base, HTTP_HOST=self.host)

    # 1. MUTATION / PERSISTENCE ----------------------------------------
    def test_palette_mode_persists_when_only_mode_selected(self):
        """A merchant selecting a palette background whose companion field is
        left at its natural default MUST persist as palette — not silently
        downgrade to theme (the observed 'nothing changes')."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        # The exact minimal payload a merchant produces by only changing the
        # background type to 'palette' (companion palette-role field left
        # unset / not touched).
        self._post_settings(sec, {"background_mode": "palette"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "palette",
                         "palette selection silently downgraded to theme (Defect C)")

    def test_custom_color_mode_persists_when_only_mode_selected(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "color",
                         "custom-color selection silently downgraded to theme (Defect C)")

    # 2. PREVIEW RENDER ------------------------------------------------
    def test_palette_background_changes_preview_render(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-2"})
        preview = self._preview_home_html()
        self.assertIn('data-bg-mode="palette"', preview)
        self.assertIn('data-palette-role="tone-2"', preview)

    def test_color_mode_without_color_paints_no_background(self):
        """G2.3 review follow-up: selecting 'custom color' but never picking a
        colour must keep the mode (no silent theme downgrade) yet paint NO
        background — never a surprise hardcoded red. The wrapper only emits an
        inline background-color when a real colour is set."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("mode"), "color")
        self.assertEqual((sec.settings or {}).get("background", {}).get("color"), "")
        preview = self._preview_home_html()
        # No accidental red / no inline background-color painted for this section.
        self.assertNotIn("#F53247", preview)

    def test_palette_pattern_without_role_persists_with_default_role(self):
        """The empty-companion defaulting must apply to BOTH palette modes."""
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {
            "background_mode": "palette_pattern",
            "background_pattern_slug": "commerce-doodle",
        })
        sec.refresh_from_db()
        bg = (sec.settings or {}).get("background", {})
        self.assertEqual(bg.get("mode"), "palette_pattern")
        self.assertEqual(bg.get("palette_role"), "tone-1")

    # 4. CUSTOM COLOR INDEPENDENCE -------------------------------------
    def test_custom_color_renders_independent_hex(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "color", "background_color": "#123456"})
        sec.refresh_from_db()
        self.assertEqual((sec.settings or {}).get("background", {}).get("color"), "#123456")
        preview = self._preview_home_html()
        self.assertIn("#123456", preview)

    # 5. PUBLISH / PUBLIC ----------------------------------------------
    def test_background_survives_publish_into_public(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-3"})
        layout_service.publish(self.store)
        public = self._public_home_html()
        self.assertIn('data-bg-mode="palette"', public)
        self.assertIn('data-palette-role="tone-3"', public)

    # 6. INVALID INPUT --------------------------------------------------
    def test_invalid_palette_role_does_not_persist_bogus(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-99"})
        sec.refresh_from_db()
        bg = (sec.settings or {}).get("background", {})
        # Bogus role must never be stored; must not raise; safe fallback.
        self.assertNotEqual(bg.get("palette_role"), "tone-99")

    def test_malformed_color_rejected_safely(self):
        _, home = self._draft_home()
        sec = self._bg_section(home)
        before = (sec.settings or {}).get("background", {})
        resp = self._post_settings(sec, {"background_mode": "color", "background_color": "not-a-color"})
        sec.refresh_from_db()
        after = (sec.settings or {}).get("background", {})
        # Must not store a malformed color.
        self.assertNotEqual(after.get("color"), "not-a-color")

    # 7. TENANT ISOLATION ----------------------------------------------
    def test_background_change_is_store_scoped(self):
        # Store A change must not touch Store B's sections.
        other = Store.objects.create(
            name="فروشگاه دیگر", slug="g23-other-store", admin_subdomain="g23-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other)
        other_home = other_draft.get_page("home")
        other_sec = other_home.sections.filter(section_key="category_grid").first()
        other_before = (other_sec.settings or {}).get("background") if other_sec else None

        _, home = self._draft_home()
        sec = self._bg_section(home)
        self._post_settings(sec, {"background_mode": "palette", "background_palette_role": "tone-1"})

        if other_sec:
            other_sec.refresh_from_db()
            self.assertEqual((other_sec.settings or {}).get("background"), other_before,
                             "changing store A background mutated store B")
