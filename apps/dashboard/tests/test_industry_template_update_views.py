from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Attribute,
    Category,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    StoreIndustryInstallation,
    StoreTemplateUpdate,
)
from apps.catalog.services.industry_template_service import install_industry_template
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"itu-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _build_shoes_v1(slug="itu-shoes"):
    v1 = IndustryTemplate.objects.create(
        slug=slug, name="کفش", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    mens = IndustryTemplateCategory.objects.create(industry_template=v1, code="mens", name="مردانه")
    color = IndustryTemplateAttribute.objects.create(
        industry_template=v1, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="مشکی", color_hex="#111827")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=mens, template_attribute=color, group="مشخصات",
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=mens, template_attribute=color)
    return v1


def _build_shoes_v2(v1):
    v2 = IndustryTemplate.objects.create(
        slug=v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
    IndustryTemplateCategory.objects.create(industry_template=v2, code="outlet", name="ته‌مانده")
    return v2


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class IndustryTemplateViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="09122277001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09122277001", password="pass12345")


class PreviewViewTests(IndustryTemplateViewsTestCase):
    def test_renders_preview_page(self):
        template = _build_shoes_v1(slug="itu-preview")
        response = self.client.get(reverse("dashboard:settings-industry-preview", args=[template.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مردانه")
        self.assertContains(response, "رنگ")

    def test_preview_shows_installation_impact_for_this_store(self):
        template = _build_shoes_v1(slug="itu-preview-impact")
        response = self.client.get(reverse("dashboard:settings-industry-preview", args=[template.pk]))
        self.assertContains(response, "نصب این الگو")

    def test_preview_of_nonexistent_template_404s(self):
        response = self.client.get(reverse("dashboard:settings-industry-preview", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        template = _build_shoes_v1(slug="itu-preview-anon")
        self.client.logout()
        response = self.client.get(reverse("dashboard:settings-industry-preview", args=[template.pk]))
        self.assertEqual(response.status_code, 302)


class UpdatePlanViewTests(IndustryTemplateViewsTestCase):
    def test_no_installation_redirects_with_message(self):
        response = self.client.get(reverse("dashboard:settings-industry-update-plan"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_no_update_available_redirects(self):
        v1 = _build_shoes_v1(slug="itu-noupdate")
        install_industry_template(self.store, v1)
        response = self.client.get(reverse("dashboard:settings-industry-update-plan"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_shows_safe_additive_and_blocked_sections(self):
        v1 = _build_shoes_v1(slug="itu-plan")
        install_industry_template(self.store, v1)
        _build_shoes_v2(v1)
        response = self.client.get(reverse("dashboard:settings-industry-update-plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ته‌مانده")

    def test_customized_category_shown_as_blocked_not_silently_applied(self):
        v1 = _build_shoes_v1(slug="itu-plan-customized")
        install_industry_template(self.store, v1)
        category = Category.objects.get(store=self.store, name="مردانه")
        category.name = "مردانه سفارشی"
        category.save()
        v2 = IndustryTemplate.objects.create(
            slug=v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه (جدید)")
        response = self.client.get(reverse("dashboard:settings-industry-update-plan"))
        self.assertContains(response, "مسدود")
        category.refresh_from_db()
        self.assertEqual(category.name, "مردانه سفارشی")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:settings-industry-update-plan"))
        self.assertEqual(response.status_code, 302)


class UpdateApplyViewTests(IndustryTemplateViewsTestCase):
    def test_apply_creates_safe_additions(self):
        v1 = _build_shoes_v1(slug="itu-apply")
        install_industry_template(self.store, v1)
        v2 = _build_shoes_v2(v1)
        response = self.client.post(
            reverse("dashboard:settings-industry-update-apply"), {"change_id": [f"category:added:outlet"]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(store=self.store, name="ته‌مانده").exists())
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.installed_version, 2)

    def test_tampered_change_id_ignored_not_applied(self):
        v1 = _build_shoes_v1(slug="itu-tamper")
        install_industry_template(self.store, v1)
        v2 = _build_shoes_v2(v1)
        # a change_id that isn't actually in the safe_additive set must be silently dropped,
        # never trusted at face value from the client
        response = self.client.post(
            reverse("dashboard:settings-industry-update-apply"),
            {"change_id": ["category:added:outlet", "category:removed:mens", "totally:fake:id"]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(store=self.store, name="ته‌مانده").exists())
        # the still-existing "mens" category must not have been affected by the fake removal id
        self.assertTrue(Category.objects.filter(store=self.store, name="مردانه").exists())

    def test_no_installation_redirects_gracefully(self):
        response = self.client.post(reverse("dashboard:settings-industry-update-apply"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-industry-update-apply"))
        self.assertEqual(response.status_code, 302)

    def test_catalog_manager_cannot_apply_update(self):
        v1 = _build_shoes_v1(slug="itu-perm")
        install_industry_template(self.store, v1)
        _build_shoes_v2(v1)
        user = User.objects.create_user(username="09122277002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.post(reverse("dashboard:settings-industry-update-apply"))
        self.assertEqual(response.status_code, 403)


class UpdateHistoryViewTests(IndustryTemplateViewsTestCase):
    def test_empty_state_shown(self):
        response = self.client.get(reverse("dashboard:settings-industry-update-history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هنوز هیچ به‌روزرسانی‌ای انجام نشده است")

    def test_shows_completed_update(self):
        v1 = _build_shoes_v1(slug="itu-history")
        install_industry_template(self.store, v1)
        v2 = _build_shoes_v2(v1)
        self.client.post(
            reverse("dashboard:settings-industry-update-apply"), {"change_id": ["category:added:outlet"]},
        )
        response = self.client.get(reverse("dashboard:settings-industry-update-history"))
        self.assertContains(response, "تکمیل‌شده")

    def test_other_store_history_not_visible(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="itu-other-store", status=Store.Status.ACTIVE)
        v1 = _build_shoes_v1(slug="itu-other-history")
        install_industry_template(other_store, v1)
        other_installation = StoreIndustryInstallation.objects.get(store=other_store)
        v2 = _build_shoes_v2(v1)
        StoreTemplateUpdate.objects.create(
            store=other_store, installation=other_installation, from_template=v1, target_template=v2,
            status=StoreTemplateUpdate.Status.COMPLETED, idempotency_key=f"{other_installation.pk}:{v2.pk}",
        )
        response = self.client.get(reverse("dashboard:settings-industry-update-history"))
        self.assertContains(response, "هنوز هیچ به‌روزرسانی‌ای انجام نشده است")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:settings-industry-update-history"))
        self.assertEqual(response.status_code, 302)
