from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.stores.models import Store, StoreMembership
from apps.stores.services import integration_service

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class IntegrationSettingsSectionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121197001", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121197001", password="pass12345")

    def test_section_lists_all_providers(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=integrations")
        self.assertContains(response, "اینماد")
        self.assertContains(response, "ترب")
        self.assertContains(response, "گوگل آنالیتیکس")

    def test_connect_activates_integration(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]), {"enamad_code": "123456"},
        )
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        store = Store.objects.get(slug="akhlaghi")
        rows = integration_service.connections_context(store=store)
        enamad_row = next(row for row in rows if row["provider"].code == "enamad")
        self.assertTrue(enamad_row["is_connected"])

    def test_connect_with_invalid_format_shows_error(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["google_analytics"]),
            {"measurement_id": "not-valid"}, follow=True,
        )
        self.assertContains(response, "الگو")

    def test_disconnect_deactivates(self):
        store = Store.objects.get(slug="akhlaghi")
        integration_service.connect(store=store, provider_code="torob", values={"merchant_id": "m-1"}, actor=None)
        response = self.client.post(reverse("dashboard:settings-integration-disconnect", args=["torob"]))
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        rows = integration_service.connections_context(store=store)
        torob_row = next(row for row in rows if row["provider"].code == "torob")
        self.assertFalse(torob_row["is_connected"])

    def test_test_connection_shows_result(self):
        store = Store.objects.get(slug="akhlaghi")
        integration_service.connect(
            store=store, provider_code="ad_pixel", values={"pixel_id": "1234567890123456"}, actor=None,
        )
        response = self.client.post(reverse("dashboard:settings-integration-test", args=["ad_pixel"]), follow=True)
        self.assertContains(response, "پیکسلِ تبلیغاتی")

    def test_unknown_provider_404s(self):
        response = self.client.post(reverse("dashboard:settings-integration-connect", args=["not-a-provider"]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-integration-connect", args=["enamad"]))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_connecting_appears_in_the_existing_audit_log_page(self):
        """رخدادهای یکپارچه‌سازی نیازی به یک صفحه‌ی گزارشِ جداگانه ندارند —
        همان صفحه‌ی «گزارش رخدادها»ی موجود (AuditLogEntry) را بازاستفاده
        می‌کنند."""
        self.client.post(
            reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "m-999"},
        )
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertContains(response, "integration.connected")

    def test_credentials_never_appear_as_plaintext_in_encrypted_column(self):
        from apps.stores.models import StoreIntegrationConnection

        self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]), {"enamad_code": "super-unique-code-999"},
        )
        connection = StoreIntegrationConnection.objects.get(store__slug="akhlaghi", provider_code="enamad")
        self.assertNotIn("super-unique-code-999", connection.encrypted_credentials)


_HOST_B = "integration-view-store-b.rastisi.ir"


@override_settings(ALLOWED_HOSTS=[_HOST_B, "testserver"])
class IntegrationTenantIsolationViewTests(TestCase):
    """یک کارمندِ فروشگاهِ B هرگز نباید بتواند اتصالِ فروشگاهِ A را از طریقِ
    این ویوها ببیند یا تغییر دهد — هر ویو از request.store (که staff_required
    resolve می‌کند) استفاده می‌کند، نه یک شناسه‌ی خامِ ارسالی."""

    def setUp(self):
        from apps.core.models import ShopSettings

        self.store_b = Store.objects.create(
            name="Store B", slug="integration-view-store-b", status=Store.Status.ACTIVE,
            admin_subdomain="integration-view-store-b",
        )
        ShopSettings.provision_for(self.store_b)
        integration_service.connect(
            store=Store.objects.get(slug="akhlaghi"), provider_code="enamad",
            values={"enamad_code": "akhlaghi-secret"}, actor=None,
        )
        self.staff_b = User.objects.create_user(username="09121197002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_b, user=self.staff_b, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def test_store_b_staff_sees_own_disconnected_state_not_akhlaghis(self):
        self.client.login(username="09121197002", password="pass12345")
        response = self.client.get(
            reverse("dashboard:settings") + "?section=integrations", HTTP_HOST=_HOST_B,
        )
        self.assertNotContains(response, "akhlaghi-secret")
