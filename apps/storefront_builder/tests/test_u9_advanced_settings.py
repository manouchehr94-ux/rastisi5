"""U9 — Advanced Storefront Settings.

Audit findings:

- The central motion architecture (`MOTION_CHOICES`, `data-sfb-motion`/
  `data-motion` attributes, section-level `motion.style` already wired
  through `responsive_section_wrapper.html`, and a global
  `@media (prefers-reduced-motion: reduce)` override in
  `apps/core/static/css/base.css`) **already existed, fully wired** —
  confirmed by reading the actual CSS and wrapper template, not assumed
  from the phase name. Nothing to build there.
- Real gap found: U4 registered two new section component variants
  (`hero_banner`'s `hero_style`, `collection_tiles`'s `tile_style`) but
  never exposed a merchant-facing control for either — the settings form
  (`partials/section_settings_form.html`) had no `<select>` for them, and
  even if it had, the POST handler (`storefront_section_settings`) builds
  an explicit per-type field allowlist that didn't include either key, so
  a submitted value would have been silently dropped. This is exactly
  U9's "section component variant swap" requirement — closed here.
- `image_text`'s existing `image_position` control and `category_grid`/
  `brand_carousel`'s `display_mode` controls were already present and
  working — confirmed unaffected.
- `header_variant`/`footer_variant` ("global component variant swap")
  were already fully wired (`header_editor.html`/`footer_editor.html`) —
  confirmed, not rebuilt.
"""

from django.urls import reverse

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.tests.test_views import StorefrontBuilderViewsTestCase


class HeroStyleFormControlTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_settings_form_shows_hero_style_control_for_hero_banner(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertContains(resp, 'name="hero_style"')
        self.assertContains(resp, "متن و تصویر جدا")

    def test_settings_form_hides_hero_style_control_for_image_slider(self):
        """image_slider shares the same form block but has no registered
        variants — the control must not appear there."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="image_slider", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertNotContains(resp, 'name="hero_style"')

    def test_posting_split_actually_persists(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"hero_style": "split"},
        )
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["hero_style"], "split")

    def test_omitting_the_field_defaults_to_overlay(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {})
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["hero_style"], "overlay")

    def test_form_reflects_currently_saved_split_selection(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0, settings={"hero_style": "split"},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertContains(resp, '<option value="split" selected>')


class TileStyleFormControlTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_settings_form_shows_tile_style_control(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="collection_tiles", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertContains(resp, 'name="tile_style"')

    def test_posting_carousel_actually_persists(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="collection_tiles", order=0)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"tile_style": "carousel"},
        )
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["tile_style"], "carousel")

    def test_omitting_the_field_defaults_to_grid(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="collection_tiles", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {})
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["tile_style"], "grid")


class MotionArchitectureAlreadyWiredTests(StorefrontBuilderViewsTestCase):
    """Tripwire confirming the audit finding — motion is already centrally
    wired — stays true; not a new feature, a regression guard."""

    def test_reduced_motion_override_present_in_base_css(self):
        import pathlib

        css_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "core" / "static" / "css" / "base.css"
        )
        content = css_path.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", content)
