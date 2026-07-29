from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import IndustryTemplate, IndustryTemplateCategory, StoreIndustryInstallation
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "isv-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class IndustrySettingsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.template = IndustryTemplate.objects.create(
            slug="isv-clothing", name="پوشاک", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(
            industry_template=self.template, code="clothing", name="پوشاک",
        )
        self.staff = User.objects.create_user(username="09121188001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121188001", password="pass12345")


class IndustrySettingsPageTests(IndustrySettingsTestCase):
    def test_renders_available_templates(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پوشاک")

    def test_inactive_template_not_listed(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertContains(response, "در حال حاضر الگوی صنفی")

    def test_only_latest_version_shown(self):
        IndustryTemplate.objects.create(
            slug="isv-clothing", name="پوشاک نسخه‌ی دو", version=2,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertContains(response, "پوشاک نسخه‌ی دو")
        # only the newer version's card is rendered — one install button for this slug, not two
        self.assertContains(response, "نصب این الگو", count=1)


class IndustryInstallViewTests(IndustrySettingsTestCase):
    def test_install_creates_categories(self):
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_second_install_shows_error_not_crash(self):
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_installed_state_shown_after_install(self):
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertContains(response, "نصب شده است")

    def test_other_store_unaffected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="isv-other", status=Store.Status.ACTIVE)
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=other_store).exists())


class IndustrySettingsPermissionTests(IndustrySettingsTestCase):
    def test_catalog_manager_cannot_install(self):
        user = User.objects.create_user(username="09121188002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_install(self):
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/login/", response.url)
