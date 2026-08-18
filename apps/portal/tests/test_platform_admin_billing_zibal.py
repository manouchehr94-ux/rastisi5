"""Platform Admin > Zibal (platform subscription billing) settings — Phase
3, master-prompt section 5.2: enable/disable, DB-editable merchant
credential (encrypted, masked, blank-preserves), sandbox toggle, no
source-code edit required."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.portal.models import PlatformConfiguration
from apps.portal.services.platform_config_service import get_platform_configuration

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class BillingZibalSettingsViewTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.superuser = User.objects.create_user(
            username="pa-zibal-super@example.com", email="pa-zibal-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary = User.objects.create_user(
            username="pa-zibal-ordinary@example.com", email="pa-zibal-ordinary@example.com",
            password="a-very-strong-pass-1",
        )

    def test_ordinary_user_denied(self):
        self.client.force_login(self.ordinary)
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_view_and_save(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal",
            "zibal_merchant": "platform-merchant-999",
            "zibal_sandbox_mode": "on",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

        config = get_platform_configuration()
        self.assertEqual(config.default_payment_provider, "zibal")
        self.assertTrue(config.zibal_sandbox_mode)
        self.assertEqual(config.get_zibal_credentials()["merchant"], "platform-merchant-999")

    def test_merchant_credential_encrypted_at_rest(self):
        self.client.force_login(self.superuser)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal",
            "zibal_merchant": "super-secret-merchant-abc",
        }, HTTP_HOST=_HOST)
        raw = PlatformConfiguration.objects.get(pk=1).encrypted_zibal_credentials
        self.assertNotIn("super-secret-merchant-abc", raw)

    def test_merchant_never_echoed_back_in_plaintext(self):
        self.client.force_login(self.superuser)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": "super-secret-merchant-abc",
        }, HTTP_HOST=_HOST)
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "super-secret-merchant-abc")

    def test_blank_merchant_preserves_existing_value(self):
        self.client.force_login(self.superuser)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": "original-merchant-id",
        }, HTTP_HOST=_HOST)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": "",
        }, HTTP_HOST=_HOST)
        config = get_platform_configuration()
        self.assertEqual(config.get_zibal_credentials()["merchant"], "original-merchant-id")

    def test_can_disable_by_switching_back_to_manual(self):
        self.client.force_login(self.superuser)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": "m-1",
        }, HTTP_HOST=_HOST)
        self.client.post("/payments/zibal/", {
            "default_payment_provider": "manual",
        }, HTTP_HOST=_HOST)
        config = get_platform_configuration()
        self.assertEqual(config.default_payment_provider, "manual")

    def test_invalid_provider_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post("/payments/zibal/", {
            "default_payment_provider": "not-a-real-provider",
        }, HTTP_HOST=_HOST, follow=True)
        self.assertContains(response, "معتبر نیست")
        config = get_platform_configuration()
        self.assertEqual(config.default_payment_provider, "manual")
