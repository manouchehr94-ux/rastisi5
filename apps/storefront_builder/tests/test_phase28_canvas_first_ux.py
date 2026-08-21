from pathlib import Path

from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase28CanvasFirstUXTemplateTests(StorefrontBuilderViewsTestCase):
    """The older Phase 2.8 overlay-drawer contract is intentionally superseded
    by the approved V3 Free Layout prototype: both side panes are persistent on
    desktop and independently collapsible, while compact layouts keep the
    existing three-way mobile navigation.
    """

    def test_editor_exposes_v3_persistent_canvas_first_shell(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        for marker in (
            "sfb-v3-shell",
            "sfb-v3-sidebar-right",
            "sfb-v3-canvas-area",
            "sfb-v3-inspector",
            "sidebarCollapsed",
            "inspectorCollapsed",
            "sidebarTab: 'add'",
            "openSelectedContainerSettings()",
        ):
            self.assertContains(response, marker)
        self.assertNotContains(response, "sfb-desktop-drawer-backdrop")

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
        self.assertContains(response, ':aria-pressed="mobilePanel === \'canvas\'"')

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
        self.assertContains(response, 'hx-trigger="change delay:250ms"')
        self.assertContains(response, "هیچ بلاکی بی‌صدا حذف نمی‌شود")
        self.assertNotContains(response, "گرید ۱۲ ستونه")

    def test_desktop_panels_follow_v3_persistent_three_column_contract(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        start = css.index("Storefront Builder V3 — Free Layout visual contract")
        v3 = css[start:]
        self.assertIn("display: grid;", v3)
        self.assertIn("grid-template-columns: 280px minmax(0, 1fr) 320px", v3)
        self.assertIn(".sfb-v3-sidebar-right", v3)
        self.assertIn(".sfb-v3-inspector", v3)
        self.assertIn(".sfb-v3-sidebar-collapsed", v3)
        self.assertIn(".sfb-v3-inspector-collapsed", v3)
        self.assertNotIn("sfb-overlay-drawer-open", v3)

    def test_v3_layout_controls_are_visible_without_hunting_for_canvas_gear(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "افزودن چیدمان")
        self.assertContains(response, "چیدمان‌ها")
        self.assertContains(response, "sfb-v3-layout-layer-list")
        self.assertContains(response, "@click=\"selectContainer(")

    def test_v3_fullscreen_keeps_a_visible_exit_control(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "sfb-v3-exit-fullscreen")
        self.assertContains(response, "خروج از تمام‌صفحه")
        self.assertContains(response, "fullscreen = false")

    def test_v3_inspector_uses_one_three_tab_state_and_live_autosave(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = response.content.decode("utf-8")
        self.assertIn(":data-inspector-tab=\"inspectorTab\"", html)
        self.assertIn("queueInspectorAutosave", html)
        self.assertIn("autosaveInspectorForm", html)
        self.assertIn("reloadPreview()", html)

        page = layout_service.get_or_create_draft(self.store, user=self.staff).get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=page, section_key="rich_text", order=999, settings={"body_html": "<p>live</p>"}
        )
        settings = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(settings.status_code, 200)
        settings_html = settings.content.decode("utf-8")
        self.assertIn('data-sfb-autosave="true"', settings_html)
        self.assertNotIn("window.sfbInspectorTab", settings_html)
