from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.catalog.models import IndustryTemplate

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


def _make_template(**kwargs):
    defaults = {
        "slug": "pa-test-industry", "name": "صنفِ آزمایشیِ ادمین", "icon": "🧪",
        "sector": IndustryTemplate.Sector.RETAIL, "version": 1, "is_active": True,
        "readiness": IndustryTemplate.Readiness.PRODUCTION_READY,
    }
    defaults.update(kwargs)
    return IndustryTemplate.objects.create(**defaults)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminIndustriesListTests(TestCase):
    """بخشِ ۱۴ (پنل مالکِ پلتفرم — مدیریتِ صنف) + بخشِ ۱۷ (تست‌های پلتفرم ادمین)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="pastaff@example.com", email="pastaff@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.staff)
        self.retail_template = _make_template(
            slug="pa-retail", name="صنفِ خرده‌فروشیِ آزمایشی", sector=IndustryTemplate.Sector.RETAIL,
        )
        self.services_template = _make_template(
            slug="pa-services", name="صنفِ خدماتیِ آزمایشی", sector=IndustryTemplate.Sector.SERVICES,
        )
        self.inactive_template = _make_template(
            slug="pa-inactive", name="صنفِ غیرفعالِ آزمایشی", is_active=False,
            readiness=IndustryTemplate.Readiness.DEPRECATED,
        )

    def test_list_shows_all_by_default(self):
        response = self.client.get("/industries/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "صنفِ خرده‌فروشیِ آزمایشی")
        self.assertContains(response, "صنفِ خدماتیِ آزمایشی")
        self.assertContains(response, "صنفِ غیرفعالِ آزمایشی")

    def test_search_filters_by_name(self):
        response = self.client.get("/industries/", {"q": "خرده‌فروشی"}, HTTP_HOST=_HOST)
        self.assertContains(response, "صنفِ خرده‌فروشیِ آزمایشی")
        self.assertNotContains(response, "صنفِ خدماتیِ آزمایشی")

    def test_sector_filter(self):
        response = self.client.get("/industries/", {"sector": "services"}, HTTP_HOST=_HOST)
        self.assertContains(response, "صنفِ خدماتیِ آزمایشی")
        self.assertNotContains(response, "صنفِ خرده‌فروشیِ آزمایشی")

    def test_active_filter(self):
        response = self.client.get("/industries/", {"active": "inactive"}, HTTP_HOST=_HOST)
        self.assertContains(response, "صنفِ غیرفعالِ آزمایشی")
        self.assertNotContains(response, "صنفِ خرده‌فروشیِ آزمایشی")

    def test_readiness_filter(self):
        response = self.client.get("/industries/", {"readiness": "deprecated"}, HTTP_HOST=_HOST)
        self.assertContains(response, "صنفِ غیرفعالِ آزمایشی")
        self.assertNotContains(response, "صنفِ خرده‌فروشیِ آزمایشی")

    def test_counts_annotated(self):
        response = self.client.get("/industries/", HTTP_HOST=_HOST)
        template_in_ctx = next(t for t in response.context["templates"] if t.pk == self.retail_template.pk)
        self.assertEqual(template_in_ctx.category_count, 0)
        self.assertEqual(template_in_ctx.installation_count, 0)

    def test_ordinary_user_denied(self):
        self.client.logout()
        owner = User.objects.create_user(
            username="notstaff@example.com", email="notstaff@example.com", password="a-very-strong-pass-1",
        )
        self.client.force_login(owner)
        response = self.client.get("/industries/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminIndustryDetailActionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="padetail@example.com", email="padetail@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.staff)
        self.template = _make_template(slug="pa-detail-toggle")

    def test_toggle_active_flips_state(self):
        self.assertTrue(self.template.is_active)
        response = self.client.post(
            f"/industries/{self.template.pk}/", {"action": "toggle_active"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.template.refresh_from_db()
        self.assertFalse(self.template.is_active)

    def test_validate_action_runs_validation(self):
        response = self.client.post(
            f"/industries/{self.template.pk}/", {"action": "validate"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.template.refresh_from_db()
        self.assertTrue(self.template.content_fingerprint)
