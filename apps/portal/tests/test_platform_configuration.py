from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration
from apps.portal.services.platform_config_service import (
    PlatformConfigurationError,
    get_platform_configuration,
    update_platform_configuration,
)

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


class PlatformConfigurationSingletonTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_creates_the_singleton_row_with_defaults(self):
        config = get_platform_configuration()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.default_trial_days, 30)
        self.assertEqual(config.deletion_retention_days, 365)

    def test_forcing_a_second_insert_is_rejected_by_the_pk_1_singleton_guard(self):
        from django.db import IntegrityError, transaction

        get_platform_configuration()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformConfiguration.objects.create(default_trial_days=45)
        self.assertEqual(PlatformConfiguration.objects.count(), 1)

    def test_updating_the_existing_row_via_the_loader_works_normally(self):
        config = get_platform_configuration()
        config.default_trial_days = 45
        config.save()
        self.assertEqual(PlatformConfiguration.objects.count(), 1)
        self.assertEqual(PlatformConfiguration.objects.get().default_trial_days, 45)

    def test_step_up_actions_default_populated_on_save(self):
        config = get_platform_configuration()
        self.assertIn("store_delete", config.step_up_actions)
        self.assertTrue(config.step_up_actions["store_delete"])


class UpdatePlatformConfigurationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.superuser = User.objects.create_user(
            username="pfadmin@example.com", email="pfadmin@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )

    def test_update_changes_value_and_invalidates_cache(self):
        get_platform_configuration()  # warm cache
        update_platform_configuration(actor=self.superuser, default_trial_days=14)
        config = get_platform_configuration()
        self.assertEqual(config.default_trial_days, 14)

    def test_update_records_audit_event(self):
        update_platform_configuration(actor=self.superuser, default_trial_days=14)
        self.assertTrue(
            PlatformAuditLogEntry.objects.filter(
                action_code="platform_configuration.updated", actor=self.superuser,
            ).exists()
        )

    def test_retention_days_out_of_range_is_rejected(self):
        with self.assertRaises(PlatformConfigurationError):
            update_platform_configuration(actor=self.superuser, deletion_retention_days=30)
        with self.assertRaises(PlatformConfigurationError):
            update_platform_configuration(actor=self.superuser, deletion_retention_days=400)

    def test_unknown_step_up_action_key_is_rejected(self):
        with self.assertRaises(PlatformConfigurationError):
            update_platform_configuration(
                actor=self.superuser, step_up_actions={"totally_made_up_action": True},
            )


    def test_invalid_enamad_meta_is_rejected_by_service(self):
        with self.assertRaises(PlatformConfigurationError):
            update_platform_configuration(
                actor=self.superuser,
                enamad_verification_meta_tag='<meta http-equiv="refresh" content="0">',
            )


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformConfigurationViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.superuser = User.objects.create_user(
            username="pfadmin2@example.com", email="pfadmin2@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary = User.objects.create_user(
            username="ordinaryowner@example.com", email="ordinaryowner@example.com",
            password="a-very-strong-pass-1",
        )

    def test_ordinary_owner_cannot_reach_configuration_page(self):
        self.client.force_login(self.ordinary)
        response = self.client.get("/configuration/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_view_and_update_configuration(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/configuration/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/configuration/",
            {
                "default_trial_days": 21, "deletion_retention_days": 200,
                "primary_brand_color": "#123456", "secondary_brand_color": "#654321",
                "temporary_logo_text": "R", "support_contact_phone": "", "support_contact_email": "",
                "default_payment_provider": "manual",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        config = get_platform_configuration()
        self.assertEqual(config.default_trial_days, 21)
        self.assertEqual(config.deletion_retention_days, 200)

    def test_superuser_can_save_safe_enamad_verification_meta(self):
        self.client.force_login(self.superuser)
        meta = '<meta name="enamad-verification" content="platform-token-456">'
        response = self.client.post(
            "/configuration/",
            {
                "default_trial_days": 30,
                "deletion_retention_days": 365,
                "primary_brand_color": "#10a37a",
                "secondary_brand_color": "#e0a72e",
                "temporary_logo_text": "راستیسی",
                "support_contact_phone": "",
                "support_contact_email": "",
                "default_payment_provider": "manual",
                "enamad_verification_meta_tag": meta,
                "new_store_registration_enabled": "on",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        config = get_platform_configuration()
        self.assertEqual(config.enamad_verification_meta_tag, meta)

    def test_platform_configuration_rejects_unsafe_enamad_html(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/configuration/",
            {
                "default_trial_days": 30,
                "deletion_retention_days": 365,
                "primary_brand_color": "#10a37a",
                "secondary_brand_color": "#e0a72e",
                "temporary_logo_text": "راستیسی",
                "support_contact_phone": "",
                "support_contact_email": "",
                "default_payment_provider": "manual",
                "enamad_verification_meta_tag": '<script>alert(1)</script>',
                "new_store_registration_enabled": "on",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فقط یک تگ meta ساده")
        self.assertEqual(get_platform_configuration().enamad_verification_meta_tag, "")

    def test_superuser_can_configure_the_central_sms_gateway(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/sms/settings/",
            {
                "sms_backend": "melipayamak", "sms_sender_number": "10001",
                "sms_melipayamak_username": "platform-user", "sms_melipayamak_password": "platform-pass",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        config = get_platform_configuration()
        self.assertEqual(config.sms_backend, "melipayamak")
        self.assertEqual(config.sms_sender_number, "10001")
        self.assertEqual(config.get_sms_credentials()["melipayamak_username"], "platform-user")
        self.assertEqual(config.get_sms_credentials()["melipayamak_password"], "platform-pass")

    def test_sms_credentials_are_encrypted_at_rest(self):
        self.client.force_login(self.superuser)
        self.client.post(
            "/sms/settings/",
            {
                "sms_backend": "kavenegar", "sms_sender_number": "10001",
                "sms_kavenegar_api_key": "super-secret-key",
            },
            HTTP_HOST=_HOST,
        )
        config = PlatformConfiguration.objects.get(pk=1)
        self.assertNotIn("super-secret-key", config.encrypted_sms_credentials)

    def test_blank_sms_secret_does_not_clear_existing_value(self):
        self.client.force_login(self.superuser)
        common_fields = {"sms_backend": "kavenegar", "sms_sender_number": "10001"}
        self.client.post("/sms/settings/", {**common_fields, "sms_kavenegar_api_key": "original-key"}, HTTP_HOST=_HOST)
        self.client.post("/sms/settings/", {**common_fields, "sms_kavenegar_api_key": ""}, HTTP_HOST=_HOST)
        config = get_platform_configuration()
        self.assertEqual(config.get_sms_credentials()["kavenegar_api_key"], "original-key")

    def test_sms_secret_is_never_echoed_back_into_the_form(self):
        self.client.force_login(self.superuser)
        common_fields = {"sms_backend": "kavenegar", "sms_sender_number": "10001"}
        self.client.post("/sms/settings/", {**common_fields, "sms_kavenegar_api_key": "super-secret-key"}, HTTP_HOST=_HOST)
        response = self.client.get("/sms/settings/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "super-secret-key")

    _BASE_CONFIG_FIELDS = {
        "default_trial_days": 30,
        "deletion_retention_days": 365,
        "primary_brand_color": "#10a37a",
        "secondary_brand_color": "#e0a72e",
        "temporary_logo_text": "راستیسی",
        "support_contact_phone": "",
        "support_contact_email": "",
        "default_payment_provider": "manual",
        "new_store_registration_enabled": "on",
    }

    def test_superuser_can_save_platform_enamad_badge_identifiers(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/configuration/",
            {**self._BASE_CONFIG_FIELDS, "enamad_id": "998877", "enamad_auth_code": "platformAuthCode123",
             "enamad_badge_enabled": "on"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        config = get_platform_configuration()
        self.assertEqual(config.enamad_id, "998877")
        self.assertEqual(config.enamad_auth_code, "platformAuthCode123")
        self.assertTrue(config.enamad_badge_enabled)

    def test_partial_badge_identifiers_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/configuration/",
            {**self._BASE_CONFIG_FIELDS, "enamad_id": "998877", "enamad_auth_code": ""},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        config = get_platform_configuration()
        self.assertEqual(config.enamad_id, "")

    def test_badge_and_verification_meta_saved_independently(self):
        self.client.force_login(self.superuser)
        self.client.post(
            "/configuration/",
            {**self._BASE_CONFIG_FIELDS, "enamad_id": "998877", "enamad_auth_code": "platformAuthCode123"},
            HTTP_HOST=_HOST,
        )
        config = get_platform_configuration()
        self.assertEqual(config.enamad_id, "998877")
        self.assertEqual(config.enamad_verification_meta_tag, "")
