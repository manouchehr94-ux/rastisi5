from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase28CanvasFirstUXTemplateTests(StorefrontBuilderViewsTestCase):
    def test_editor_exposes_canvas_first_controls_and_drawer_state(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        for marker in (
            "sfb-canvas-drawer-actions",
            "sfb-library-toggle",
            "sfb-layout-shortcut",
            "sfb-inspector-toggle",
            "sfb-desktop-drawer-backdrop",
            "libraryDrawerOpen",
            "inspectorDrawerOpen",
            "toggleLibraryDrawer()",
            "openInspectorDrawer()",
            "openSelectedContainerSettings()",
        ):
            self.assertContains(response, marker)

    def test_layout_shortcut_opens_real_container_settings(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn("selectedContainerId", html)
        self.assertIn("openSelectedContainerSettings()", html)
        self.assertIn("containerSettingsUrlTemplate", html)
        self.assertIn("selectContainer(containerId", html)
        self.assertNotIn("openSelectedLayout()", html)

    def test_existing_mobile_navigation_is_preserved(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "sfb-mobile-builder-nav")
        self.assertContains(response, "setMobilePanel('library')")
        self.assertContains(response, "setMobilePanel('canvas')")
        self.assertContains(response, "setMobilePanel('inspector')")

    def test_layout_explanation_is_merchant_facing_and_separate_from_content(self):
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        page = draft.get_page(StorefrontPage.PageType.HOME)
        page.containers.all().delete()
        section = page.sections.order_by("order", "id").first()
        if section is None:
            section = StorefrontSection.objects.create(
                page=page,
                section_key="rich_text",
                order=0,
                settings={"body_html": "<p>layout</p>"},
            )
        from apps.storefront_builder.services import container_service
        container = container_service.create_empty_container(page, "single")
        container_service.place_section(container.cells.get(), section)

        response = self.client.get(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "ابتدا شکل خانه‌ها را انتخاب کن")
        self.assertContains(response, "خانه‌های جدید را خالی می‌سازد")
        self.assertContains(response, "نصف + نصف")
        self.assertContains(response, "چهار ستون")
        self.assertContains(response, "خانه‌ها زیر هم قرار بگیرند")
        self.assertNotContains(response, "گرید ۱۲ ستونه")
    def test_desktop_panels_are_overlay_drawers_and_canvas_is_wider(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        self.assertIn("Phase 2.8C — Direct stable Canvas drawers", css)
        self.assertIn("@media (min-width: 861px)", css)
        self.assertIn(".sfb-overlay-drawer.sfb-overlay-drawer-open", css)
        self.assertIn(".sfb-overlay-drawer-library", css)
        self.assertIn(".sfb-overlay-drawer-inspector", css)
        self.assertIn("max-width: 1500px", css)
        self.assertIn("position: absolute", css)
        self.assertIn("transform: none !important", css)
