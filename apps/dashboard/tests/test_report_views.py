from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ReportViewsTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121191001", password="pass12345", is_staff=True)
        self.client.login(username="09121191001", password="pass12345")


class ReportListViewTests(ReportViewsTestCase):
    def test_renders_default_range(self):
        response = self.client.get(reverse("dashboard:report-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گزارش‌های حرفه‌ای")
        self.assertContains(response, "<svg")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:report-list"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_range_query_param_selects_range(self):
        response = self.client.get(reverse("dashboard:report-list"), {"range": "7"})
        self.assertContains(response, "۷ روز اخیر")


class ReportBodyPartialTests(ReportViewsTestCase):
    def test_returns_partial_for_range(self):
        response = self.client.get(reverse("dashboard:report-body"), {"range": "90"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")

    def test_invalid_range_falls_back(self):
        response = self.client.get(reverse("dashboard:report-body"), {"range": "nonsense"})
        self.assertEqual(response.status_code, 200)
