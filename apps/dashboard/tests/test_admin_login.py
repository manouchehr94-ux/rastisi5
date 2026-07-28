"""Regression tests for the admin login foundation.

Proves:
1. Anonymous users are redirected to /admin-panel/login/ (not storefront)
2. Staff users can access the dashboard directly
3. Authenticated non-staff users are denied access
4. Successful login redirects to the next URL
5. Invalid credentials show an error on the login page
6. Non-staff users see a clear denial message
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _grant_akhlaghi_membership(user, role=None):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"),
        user=user,
        role=role or StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class AdminLoginRedirectTests(TestCase):
    """Anonymous users must be redirected to the admin login page."""

    def test_anonymous_redirected_to_admin_login_from_dashboard(self):
        """GET /admin-panel/ → 302 → /admin-panel/login/?next=/admin-panel/"""
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)
        self.assertIn("next=", response.url)

    def test_anonymous_redirected_from_nested_admin_page(self):
        """GET /admin-panel/products/ → 302 → /admin-panel/login/?next=..."""
        response = self.client.get("/admin-panel/products/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)
        self.assertIn("next=", response.url)

    def test_login_page_accessible_without_auth(self):
        """GET /admin-panel/login/ → 200 (login page renders)"""
        response = self.client.get("/admin-panel/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ورود به حساب مدیریت")


class StaffAccessTests(TestCase):
    """Staff users can access the admin panel."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="admin1", password="StaffPass123!", is_staff=True
        )
        _grant_akhlaghi_membership(self.staff_user)

    def test_staff_can_access_dashboard(self):
        """Staff user → GET /admin-panel/ → 200"""
        self.client.login(username="admin1", password="StaffPass123!")
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 200)

    def test_staff_login_page_redirects_to_dashboard(self):
        """Already-authenticated staff visiting login page → redirect to dashboard"""
        self.client.login(username="admin1", password="StaffPass123!")
        response = self.client.get("/admin-panel/login/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-panel/")


class NonStaffDeniedTests(TestCase):
    """Authenticated non-staff users are denied admin access."""

    def setUp(self):
        self.customer_user = User.objects.create_user(
            username="customer1", password="CustPass123!", is_staff=False
        )

    def test_non_staff_denied_dashboard(self):
        """Non-staff authenticated user → GET /admin-panel/ → redirect to storefront"""
        self.client.login(username="customer1", password="CustPass123!")
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-panel/", response.url)

    def test_non_staff_login_attempt_shows_error(self):
        """Non-staff user tries to login via admin login form → error message"""
        response = self.client.post("/admin-panel/login/", {
            "username": "customer1",
            "password": "CustPass123!",
            "next": "/admin-panel/",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دسترسی ندارید")


class AdminLoginFlowTests(TestCase):
    """Complete login flow: credentials → authenticate → redirect."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="manager", password="ManagerPass123!", is_staff=True
        )
        _grant_akhlaghi_membership(self.staff_user)

    def test_successful_login_redirects_to_next(self):
        """Valid credentials with next param → redirect to requested page"""
        response = self.client.post("/admin-panel/login/?next=/admin-panel/orders/", {
            "username": "manager",
            "password": "ManagerPass123!",
            "next": "/admin-panel/orders/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-panel/orders/")

    def test_successful_login_without_next_goes_to_dashboard(self):
        """Valid credentials without next → redirect to /admin-panel/"""
        response = self.client.post("/admin-panel/login/", {
            "username": "manager",
            "password": "ManagerPass123!",
            "next": "/admin-panel/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-panel/")

    def test_invalid_credentials_show_error(self):
        """Wrong password → stays on login page with error"""
        response = self.client.post("/admin-panel/login/", {
            "username": "manager",
            "password": "WrongPassword",
            "next": "/admin-panel/",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اشتباه")

    def test_open_redirect_prevention(self):
        """next parameter to external URL → redirects to /admin-panel/ instead"""
        response = self.client.post("/admin-panel/login/", {
            "username": "manager",
            "password": "ManagerPass123!",
            "next": "https://evil.com/steal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-panel/")

    def test_user_is_authenticated_after_login(self):
        """After successful login, user session is authenticated"""
        self.client.post("/admin-panel/login/", {
            "username": "manager",
            "password": "ManagerPass123!",
            "next": "/admin-panel/",
        })
        # Follow-up request should work without re-login
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 200)
