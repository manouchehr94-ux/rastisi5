from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class PrototypeV2Phase26EmbeddedNavigationGuardTests(StorefrontBuilderViewsTestCase):
    def test_preview_installs_capture_phase_navigation_guard(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "function blockEmbeddedNavigation(evt)")
        self.assertContains(response, "document.addEventListener('click', blockEmbeddedNavigation, true)")
        self.assertContains(response, "document.addEventListener('auxclick', blockEmbeddedNavigation, true)")

    def test_embedded_navigation_guard_blocks_links_and_forms_only_in_parent_frame(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertContains(response, "if (!inParentFrame) return;")
        self.assertContains(response, "target.closest('a[href], [role=\"link\"]')")
        self.assertContains(response, "evt.preventDefault();")
        self.assertContains(response, "evt.stopPropagation();")
        self.assertContains(response, "document.addEventListener('submit', function (evt)")

    def test_clicking_embedded_section_link_still_selects_its_section(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertContains(response, "navigationTarget.closest('[data-section-id]')")
        self.assertContains(response, "if (section) selectSectionElement(section);")
