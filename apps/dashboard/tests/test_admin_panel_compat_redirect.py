"""Tests for the ``/admin-panel/`` → ``/admin-portal/`` backward-compatible
redirect (Phase 1B route rename, ADR-16)."""

from django.test import TestCase


class AdminPanelCompatRedirectTests(TestCase):
    def test_bare_prefix_redirects_to_admin_portal(self):
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/")

    def test_sub_path_redirects_preserving_path(self):
        response = self.client.get("/admin-panel/products/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/products/")

    def test_query_string_is_preserved(self):
        response = self.client.get("/admin-panel/settings/?section=finance")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/settings/?section=finance")

    def test_redirect_is_not_permanent(self):
        """302, not 301 — this is a temporary shim, not a permanent alias."""
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 302)

    def test_login_sub_path_redirects(self):
        response = self.client.get("/admin-panel/login/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/login/")

    def test_admin_portal_itself_is_served_directly_not_via_compat_redirect(self):
        """An anonymous request to the canonical route is redirected to the
        login page by staff_required — not bounced back through the
        /admin-panel/ compat redirect (which would be a self-referential
        loop back to /admin-portal/)."""
        response = self.client.get("/admin-portal/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/login/", response.url)
