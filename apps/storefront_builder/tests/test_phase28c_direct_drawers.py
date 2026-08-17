from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class Phase28CDirectDrawerTests(StorefrontBuilderViewsTestCase):
    def test_library_and_inspector_have_direct_open_state(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("sfb-overlay-drawer-library", html)
        self.assertIn("sfb-overlay-drawer-inspector", html)
        self.assertIn("'sfb-overlay-drawer-open': !isCompactLayout() && libraryDrawerOpen", html)
        self.assertIn("'sfb-overlay-drawer-open': !isCompactLayout() && inspectorDrawerOpen", html)

    def test_parent_open_state_is_retained_as_compatibility_fallback(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("'sfb-library-open': libraryDrawerOpen", html)
        self.assertIn("'sfb-inspector-open': inspectorDrawerOpen", html)

    def test_opening_library_resets_panel_scroll(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("const panel = this.$root.querySelector('.sfb-library-panel')", html)
        self.assertIn("panel.scrollTop = 0", html)


class Phase28CDirectDrawerStaticTests(SimpleTestCase):
    def test_phase28c_has_no_offscreen_drawer_translation(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        start = css.index("Phase 2.8C — Direct stable Canvas drawers")
        phase = css[start:]
        self.assertIn("transform: none !important", phase)
        self.assertNotIn("translateX(104%)", phase)
        self.assertNotIn("translateX(-104%)", phase)
        self.assertIn("background: transparent", phase)
        self.assertIn(".sfb-overlay-drawer.sfb-overlay-drawer-open", phase)
