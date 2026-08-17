from pathlib import Path

from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class Phase273DomIntegrityTests(StorefrontBuilderViewsTestCase):
    def test_wishlist_oob_counters_are_post_response_only(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "customers"
            / "templates"
            / "customers"
            / "partials"
            / "wishlist_button.html"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('{% if request.method == "POST" %}', source)
        self.assertIn(
            '{% include "cart/partials/header_counts_oob.html" %}',
            source,
        )

    def test_cart_body_oob_counters_are_post_response_only(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "cart"
            / "templates"
            / "cart"
            / "partials"
            / "cart_sections_body.html"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('{% if request.method == "POST" %}', source)
        self.assertIn(
            '{% include "cart/partials/header_counts_oob.html" %}',
            source,
        )

    def test_embedded_preview_marks_zero_height_sections_as_builder_only_empty_boxes(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-preview"),
            {"page": "home"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "function markEmptyBuilderSections()")
        self.assertContains(response, "if (!inParentFrame || !container) return;")
        self.assertContains(response, "section.getBoundingClientRect().height < 1")
        self.assertContains(response, "sfb-rsec-builder-empty")

    def test_empty_placeholder_css_is_generic(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn(".rsec.sfb-rsec-builder-empty", source)
        self.assertIn("content: attr(data-section-label)", source)
        for forbidden in (
            "quick_links.sfb-rsec-builder-empty",
            "rich_text.sfb-rsec-builder-empty",
            "product_video.sfb-rsec-builder-empty",
            "cart_summary.sfb-rsec-builder-empty",
        ):
            self.assertNotIn(forbidden, source)
