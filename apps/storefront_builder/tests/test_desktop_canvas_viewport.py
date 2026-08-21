from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class PrototypeV3ResponsiveCanvasViewportTests(StorefrontBuilderViewsTestCase):
    def test_editor_declares_prototype_desktop_tablet_and_mobile_viewports(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-desktop-viewport-width="1200"')
        self.assertContains(response, 'data-tablet-viewport-width="768"')
        self.assertContains(response, 'data-mobile-viewport-width="390"')
        self.assertContains(response, 'class="sfb-preview-viewport"')

    def test_editor_recalculates_scaled_viewport_on_device_zoom_and_resize(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(response, "installPreviewViewportObserver()")
        self.assertContains(response, "syncPreviewViewport()")
        self.assertContains(response, "new ResizeObserver")
        self.assertContains(response, "availableWidth / requestedWidth")
        self.assertContains(response, "zoom: 100")
        self.assertContains(response, "changeZoom(delta)")
        self.assertContains(response, "Math.max(60, Math.min(130, this.zoom + delta))")

    def test_library_drop_metrics_account_for_actual_preview_scale(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"))
        # Real-cell drop zones are projected from iframe coordinates into the
        # scaled parent canvas using top/left + scaled width/height.
        self.assertContains(response, "rect.top * scale")
        self.assertContains(response, "rect.width * scale")
        self.assertContains(response, "rect.height * scale")
        self.assertContains(response, "bottom: top + height")
        self.assertContains(response, "30 / Math.max(this.previewScale, 0.01)")
