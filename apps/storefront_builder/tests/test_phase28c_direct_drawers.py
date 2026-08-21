from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class Phase28CDirectDrawerTests(StorefrontBuilderViewsTestCase):
    """Compatibility tests updated for the approved V3 shell.

    Phase 2.8C introduced stable overlay drawers. V3 deliberately replaces that
    desktop presentation with persistent side panes, without changing the
    server-backed Inspector/Library behavior.
    """

    def test_library_and_inspector_are_persistent_and_independently_collapsible(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("sfb-v3-sidebar-right", html)
        self.assertIn("sfb-v3-inspector", html)
        self.assertIn("sidebarCollapsed", html)
        self.assertIn("inspectorCollapsed", html)
        self.assertIn("syncPreviewViewport()", html)
        self.assertNotIn("sfb-desktop-drawer-backdrop", html)

    def test_right_panel_has_add_layers_style_and_pages_tabs(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        for tab in ("'add'", "'layers'", "'style'", "'pages'"):
            self.assertIn(f"sidebarTab = {tab}", html)
        for label in ("افزودن", "ساختار", "استایل", "صفحات"):
            self.assertIn(label, html)

    def test_opening_cell_library_reveals_persistent_add_panel(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("openCellLibrary(cellId, containerId", html)
        self.assertIn("this.sidebarTab = 'add'", html)
        self.assertIn("this.sidebarCollapsed = false", html)


class Phase28CDirectDrawerStaticTests(SimpleTestCase):
    def test_v3_desktop_shell_has_no_offscreen_drawer_translation(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        start = css.index("Storefront Builder V3 — Free Layout visual contract")
        phase = css[start:]
        self.assertIn("grid-template-columns: 280px minmax(0, 1fr) 320px", phase)
        self.assertNotIn("translateX(104%)", phase)
        self.assertNotIn("translateX(-104%)", phase)
        self.assertNotIn("sfb-overlay-drawer-open", phase)
