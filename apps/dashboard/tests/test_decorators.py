from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class StaffRequiredDecoratorTests(TestCase):
    def test_anonymous_user_is_redirected_home(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_anonymous_user_sees_login_prompt_message(self):
        response = self.client.get(reverse("dashboard:dashboard"), follow=True)
        messages = list(response.context["messages"])
        self.assertTrue(any("وارد حساب کاربری" in str(m) for m in messages))

    def test_authenticated_non_staff_is_redirected_home(self):
        user = User.objects.create_user(username="09121119900", password="pass12345", is_staff=False)
        self.client.login(username="09121119900", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_authenticated_non_staff_sees_access_denied_message(self):
        user = User.objects.create_user(username="09121119901", password="pass12345", is_staff=False)
        self.client.login(username="09121119901", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), follow=True)
        messages = list(response.context["messages"])
        self.assertTrue(any("دسترسی ندارید" in str(m) for m in messages))

    def test_staff_user_can_access(self):
        user = User.objects.create_user(username="09121119902", password="pass12345", is_staff=True)
        self.client.login(username="09121119902", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 200)
