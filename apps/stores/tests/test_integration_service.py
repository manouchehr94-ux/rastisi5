from django.test import TestCase

from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreIntegrationConnection
from apps.stores.services import integration_service


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ConnectTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_credentials_activate_the_connection(self):
        connection = integration_service.connect(
            store=self.store, provider_code="enamad", values={"enamad_code": "123456"}, actor=None,
        )
        self.assertTrue(connection.is_active)
        self.assertIsNotNone(connection.connected_at)

    def test_credentials_are_stored_encrypted_not_plaintext(self):
        connection = integration_service.connect(
            store=self.store, provider_code="enamad", values={"enamad_code": "123456"}, actor=None,
        )
        self.assertNotIn("123456", connection.encrypted_credentials)

    def test_stored_credentials_round_trip(self):
        connection = integration_service.connect(
            store=self.store, provider_code="google_analytics", values={"measurement_id": "G-ABC1234DEF"}, actor=None,
        )
        self.assertEqual(connection.get_credentials()["measurement_id"], "G-ABC1234DEF")

    def test_invalid_format_is_rejected(self):
        with self.assertRaises(integration_service.IntegrationError):
            integration_service.connect(
                store=self.store, provider_code="google_analytics", values={"measurement_id": "not-valid"}, actor=None,
            )

    def test_empty_required_field_is_rejected(self):
        with self.assertRaises(integration_service.IntegrationError):
            integration_service.connect(store=self.store, provider_code="enamad", values={}, actor=None)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(integration_service.UnknownProviderError):
            integration_service.connect(
                store=self.store, provider_code="not-a-real-provider", values={}, actor=None,
            )

    def test_records_an_audit_event(self):
        integration_service.connect(
            store=self.store, provider_code="torob", values={"merchant_id": "m-123"}, actor=None,
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="integration.connected").exists()
        )

    def test_reconnecting_records_credentials_updated_not_connected_again(self):
        integration_service.connect(
            store=self.store, provider_code="torob", values={"merchant_id": "m-123"}, actor=None,
        )
        integration_service.connect(
            store=self.store, provider_code="torob", values={"merchant_id": "m-456"}, actor=None,
        )
        self.assertEqual(
            AuditLogEntry.objects.filter(store=self.store, action_code="integration.connected").count(), 1,
        )
        self.assertEqual(
            AuditLogEntry.objects.filter(store=self.store, action_code="integration.credentials_updated").count(), 1,
        )


class DisconnectTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        integration_service.connect(
            store=self.store, provider_code="enamad", values={"enamad_code": "123456"}, actor=None,
        )

    def test_disconnect_deactivates(self):
        connection = integration_service.disconnect(store=self.store, provider_code="enamad", actor=None)
        self.assertFalse(connection.is_active)

    def test_disconnect_keeps_credentials_for_reconnect(self):
        integration_service.disconnect(store=self.store, provider_code="enamad", actor=None)
        connection = StoreIntegrationConnection.objects.get(store=self.store, provider_code="enamad")
        self.assertEqual(connection.get_credentials()["enamad_code"], "123456")

    def test_records_an_audit_event(self):
        integration_service.disconnect(store=self.store, provider_code="enamad", actor=None)
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="integration.disconnected").exists()
        )


class TestConnectionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_stored_credentials_report_success(self):
        integration_service.connect(
            store=self.store, provider_code="google_tag_manager", values={"container_id": "GTM-ABC1234"}, actor=None,
        )
        connection = integration_service.test_connection(store=self.store, provider_code="google_tag_manager", actor=None)
        self.assertEqual(connection.last_test_result, "success")
        self.assertIsNotNone(connection.last_tested_at)

    def test_missing_credentials_report_failure(self):
        connection = integration_service.test_connection(store=self.store, provider_code="google_tag_manager", actor=None)
        self.assertEqual(connection.last_test_result, "failed")

    def test_records_an_audit_event_with_result_metadata(self):
        integration_service.connect(
            store=self.store, provider_code="ad_pixel", values={"pixel_id": "1234567890123456"}, actor=None,
        )
        integration_service.test_connection(store=self.store, provider_code="ad_pixel", actor=None)
        entry = AuditLogEntry.objects.get(store=self.store, action_code="integration.tested")
        self.assertIn("success", entry.metadata.get("result", "") if entry.metadata else "")


class ConnectionsContextTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_lists_every_registered_provider_even_if_not_connected(self):
        rows = integration_service.connections_context(store=self.store)
        codes = {row["provider"].code for row in rows}
        self.assertIn("enamad", codes)
        self.assertIn("torob", codes)
        self.assertIn("google_analytics", codes)
        self.assertIn("google_tag_manager", codes)
        self.assertIn("ad_pixel", codes)
        for row in rows:
            self.assertFalse(row["is_connected"])

    def test_connected_provider_shows_is_connected_true(self):
        integration_service.connect(
            store=self.store, provider_code="enamad", values={"enamad_code": "123456"}, actor=None,
        )
        rows = integration_service.connections_context(store=self.store)
        enamad_row = next(row for row in rows if row["provider"].code == "enamad")
        self.assertTrue(enamad_row["is_connected"])
        self.assertEqual(enamad_row["credentials"]["enamad_code"], "123456")


class TenantIsolationTests(TestCase):
    def test_store_a_connection_never_visible_to_store_b(self):
        store_a = _akhlaghi()
        store_b = Store.objects.create(name="Store B", slug="integration-store-b", status=Store.Status.ACTIVE)
        integration_service.connect(
            store=store_a, provider_code="enamad", values={"enamad_code": "a-secret-code"}, actor=None,
        )

        rows_b = integration_service.connections_context(store=store_b)
        enamad_row_b = next(row for row in rows_b if row["provider"].code == "enamad")
        self.assertFalse(enamad_row_b["is_connected"])
        self.assertEqual(enamad_row_b["credentials"], {})

    def test_disconnecting_store_b_never_affects_store_a(self):
        store_a = _akhlaghi()
        store_b = Store.objects.create(name="Store B", slug="integration-store-b2", status=Store.Status.ACTIVE)
        integration_service.connect(
            store=store_a, provider_code="enamad", values={"enamad_code": "a-code"}, actor=None,
        )
        integration_service.disconnect(store=store_b, provider_code="enamad", actor=None)

        connection_a = StoreIntegrationConnection.objects.get(store=store_a, provider_code="enamad")
        self.assertTrue(connection_a.is_active)
