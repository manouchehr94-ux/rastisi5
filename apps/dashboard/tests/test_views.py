from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class DashboardViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121121001", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121001", password="pass12345")

    def test_dashboard_renders_with_active_nav(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "داشبورد")
        self.assertContains(response, 'data-page="dashboard"')
        self.assertContains(response, "روند فروش")

    def test_dashboard_shows_all_nine_sidebar_sections(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        for label in [
            "داشبورد", "کالاها", "گروه‌بندی کالاها", "سفارشات", "فاکتورها",
            "مشتری‌ها", "پرداخت‌ها", "گزارش‌های حرفه‌ای", "تنظیمات",
        ]:
            self.assertContains(response, label)

    def test_dashboard_shows_store_status(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "فعال")
        self.assertContains(response, 'data-store-status="active"')


class SalesChartPartialViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121121002", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121002", password="pass12345")

    def test_week_range_returns_svg(self):
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "week"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")

    def test_invalid_range_falls_back_without_error(self):
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "nonsense"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")

    def test_anonymous_cannot_fetch_chart(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "week"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)