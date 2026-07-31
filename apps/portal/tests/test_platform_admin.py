from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminAccessTests(TestCase):
    def setUp(self):
        self.staff_superuser = User.objects.create_user(
            username="platformstaff@example.com", email="platformstaff@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary_owner = User.objects.create_user(
            username="ordinary@example.com", email="ordinary@example.com", password="a-very-strong-pass-1",
        )
        self.staff_but_not_superuser = User.objects.create_user(
            username="halfstaff@example.com", email="halfstaff@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=False,
        )

    def test_anonymous_is_redirected_to_platform_admin_login(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_ordinary_owner_cannot_reach_platform_admin(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_staff_without_superuser_cannot_reach_platform_admin(self):
        self.client.force_login(self.staff_but_not_superuser)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_staff_superuser_can_reach_platform_admin(self):
        self.client.force_login(self.staff_superuser)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

    def test_platform_admin_login_view_works_on_get(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminLoginRememberMeTests(TestCase):
    def setUp(self):
        self.staff_superuser = User.objects.create_user(
            username="rememberadmin@example.com", email="rememberadmin@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )

    def test_correct_credentials_log_in(self):
        response = self.client.post(
            "/login/", {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_remember_me_unchecked_expires_at_browser_close(self):
        self.client.post(
            "/login/", {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_checked_uses_persistent_expiry(self):
        self.client.post(
            "/login/",
            {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1", "remember_me": "on"},
            HTTP_HOST=_HOST,
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)

    def test_remember_me_checkbox_present_on_the_page(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, "مرا به خاطر بسپار")

    def test_non_superuser_staff_never_gets_logged_in_even_with_correct_password(self):
        User.objects.create_user(
            username="halfadmin2@example.com", email="halfadmin2@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=False,
        )
        response = self.client.post(
            "/login/", {"email": "halfadmin2@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
