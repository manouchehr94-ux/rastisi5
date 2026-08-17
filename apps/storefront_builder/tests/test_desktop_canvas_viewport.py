from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class PrototypeV2Phase26DesktopCanvasViewportTests(StorefrontBuilderViewsTestCase):
    def test_editor_declares_fixed_desktop_preview_viewport(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-desktop-viewport-width="1440"')
        self.assertContains(response, 'class="sfb-preview-viewport"')

    def test_editor_recalculates_scaled_viewport_on_device_and_resize(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "installPreviewViewportObserver()")
        self.assertContains(response, "syncPreviewViewport()")
        self.assertContains(response, "new ResizeObserver")
        self.assertContains(response, "availableWidth / requestedWidth")

    def test_library_drop_metrics_account_for_desktop_scale(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "rect.top * scale")
        self.assertContains(response, "rect.bottom * scale")
        self.assertContains(response, "24 / (this.device === 'desktop'")
