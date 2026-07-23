from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class StaffRequiredDecoratorTests(TestCase):
    def test_anonymous_user_is_redirected_to_admin_login(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_anonymous_redirect_includes_next_parameter(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertIn("next=", response.url)

    def test_authenticated_non_staff_is_redirected_home(self):
        user = User.objects.create_user(username="09121119900", password="pass12345", is_staff=False)
        self.client.login(username="09121119900", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_staff_user_can_access(self):
        user = User.objects.create_user(username="09121119902", password="pass12345", is_staff=True)
        self.client.login(username="09121119902", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 200)
