"""Section 12 — custom domain DNS verification. A domain is NEVER marked
verified by anything other than a real (here, mocked) DNS TXT lookup; a
failed/absent lookup always leaves it retryable, never silently verified."""

from datetime import timedelta
from unittest.mock import patch

import dns.resolver
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.domain_verification_service import (
    DomainVerificationError,
    activate_custom_domain,
    begin_dns_verification,
    check_dns_routing,
    check_dns_verification,
    check_ssl_connection,
    custom_domain_connection_instructions,
    custom_domain_is_ready_for_activation,
    refresh_custom_domain_readiness,
    request_custom_domain,
    verification_record_name,
)
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()


class _FakeTXTRecord:
    def __init__(self, *chunks):
        self.strings = [chunk.encode() for chunk in chunks]


def _resolve_target():
    return "apps.stores.services.domain_verification_service.dns.resolver.resolve"


class DomainVerificationTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه دامنه", slug="domain-verify-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="domain-verify-store",
        )
        self.trial_domain = StoreDomain.objects.create(
            store=self.store, hostname=f"{self.store.platform_code}.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.actor = User.objects.create_user(username="09121280011", password="a-very-strong-pass-1")


class RequestCustomDomainTests(DomainVerificationTestCase):
    def test_creates_unverified_custom_domain(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.CUSTOM_DOMAIN)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.UNVERIFIED)
        self.assertFalse(domain.is_primary)

    def test_rejects_hostname_already_registered_elsewhere(self):
        request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        other_store = Store.objects.create(
            name="فروشگاه دیگر دامنه", slug="domain-verify-other", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="domain-verify-other",
        )
        with self.assertRaises(DomainVerificationError):
            request_custom_domain(store=other_store, hostname="shop.example.com", actor=self.actor)

    def test_rejects_a_rastisi_subdomain_as_a_custom_domain(self):
        with self.assertRaises(DomainVerificationError):
            request_custom_domain(store=self.store, hostname="somelabel.rastisi.ir", actor=self.actor)


class BeginDnsVerificationTests(DomainVerificationTestCase):
    def test_sets_pending_with_a_token(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        domain = begin_dns_verification(domain=domain, actor=self.actor)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.PENDING)
        self.assertTrue(domain.verification_token)
        self.assertIsNotNone(domain.verification_requested_at)

    def test_rejects_a_non_custom_domain(self):
        with self.assertRaises(DomainVerificationError):
            begin_dns_verification(domain=self.trial_domain, actor=self.actor)

    def test_rejects_an_already_verified_domain(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
        domain.verified_at = self.trial_domain.created_at
        domain.save()
        with self.assertRaises(DomainVerificationError):
            begin_dns_verification(domain=domain, actor=self.actor)


class CheckDnsVerificationTests(DomainVerificationTestCase):
    def _pending_domain(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        return begin_dns_verification(domain=domain, actor=self.actor)

    def test_requires_a_pending_challenge(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        with self.assertRaises(DomainVerificationError):
            check_dns_verification(domain=domain, actor=self.actor)

    def test_matching_txt_record_verifies(self):
        domain = self._pending_domain()
        expected_name = verification_record_name(domain.hostname)
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            result = check_dns_verification(domain=domain, actor=self.actor)
        mock_resolve.assert_called_once()
        self.assertEqual(mock_resolve.call_args[0][0], expected_name)
        self.assertTrue(result)
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertIsNotNone(domain.verified_at)

    def test_txt_record_split_across_multiple_strings_is_reassembled(self):
        domain = self._pending_domain()
        token = domain.verification_token
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={token[:10]}", token[10:])]
            result = check_dns_verification(domain=domain, actor=self.actor)
        self.assertTrue(result)

    def test_wrong_token_value_does_not_verify(self):
        domain = self._pending_domain()
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord("rastisi-verify=wrong-token")]
            result = check_dns_verification(domain=domain, actor=self.actor)
        self.assertFalse(result)
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.PENDING)

    def test_dns_lookup_failure_never_verifies(self):
        domain = self._pending_domain()
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NXDOMAIN()
            result = check_dns_verification(domain=domain, actor=self.actor)
        self.assertFalse(result)
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.PENDING)
        self.assertIsNone(domain.verified_at)

    def test_no_txt_records_at_all_never_verifies(self):
        domain = self._pending_domain()
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = []
            result = check_dns_verification(domain=domain, actor=self.actor)
        self.assertFalse(result)


class ActivateCustomDomainTests(DomainVerificationTestCase):
    def _verified_domain(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        domain = begin_dns_verification(domain=domain, actor=self.actor)
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            check_dns_verification(domain=domain, actor=self.actor)
        domain.refresh_from_db()
        domain.routing_status = StoreDomain.RoutingStatus.CONNECTED
        domain.routing_checked_at = timezone.now()
        domain.tls_status = StoreDomain.TlsStatus.READY
        domain.tls_checked_at = timezone.now()
        domain.save(update_fields=[
            "routing_status", "routing_checked_at",
            "tls_status", "tls_checked_at", "updated_at",
        ])
        domain.refresh_from_db()
        return domain

    def test_requires_verified_status(self):
        domain = request_custom_domain(store=self.store, hostname="shop.example.com", actor=self.actor)
        with self.assertRaises(DomainVerificationError):
            activate_custom_domain(store=self.store, domain=domain, actor=self.actor)

    def test_activation_retires_old_primary_and_sets_new(self):
        domain = self._verified_domain()
        activated = activate_custom_domain(store=self.store, domain=domain, actor=self.actor)
        self.assertTrue(activated.is_primary)

        self.trial_domain.refresh_from_db()
        self.assertFalse(self.trial_domain.is_primary)
        self.assertIsNotNone(self.trial_domain.retired_at)

    def test_activation_preserves_permanent_rastisi_handle_as_live_alias(self):
        self.trial_domain.is_primary = False
        self.trial_domain.retired_at = timezone.now()
        self.trial_domain.save(update_fields=["is_primary", "retired_at", "updated_at"])
        permanent = StoreDomain.objects.create(
            store=self.store,
            hostname="digilool.rastisi.ir",
            is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

        domain = self._verified_domain()
        activated = activate_custom_domain(store=self.store, domain=domain, actor=self.actor)

        self.assertTrue(activated.is_primary)
        permanent.refresh_from_db()
        self.assertFalse(permanent.is_primary)
        self.assertIsNone(permanent.retired_at)

    def test_rejects_a_domain_belonging_to_another_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر فعال‌سازی", slug="domain-verify-activate-other", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="domain-verify-activate-other",
        )
        domain = self._verified_domain()
        with self.assertRaises(DomainVerificationError):
            activate_custom_domain(store=other_store, domain=domain, actor=self.actor)


    def test_requires_connected_dns_readiness(self):
        domain = self._verified_domain()
        domain.routing_status = StoreDomain.RoutingStatus.NOT_CONNECTED
        domain.save(update_fields=["routing_status", "updated_at"])
        with self.assertRaisesRegex(DomainVerificationError, "آماده"):
            activate_custom_domain(store=self.store, domain=domain, actor=self.actor)

    def test_requires_tls_readiness(self):
        domain = self._verified_domain()
        domain.tls_status = StoreDomain.TlsStatus.NOT_READY
        domain.save(update_fields=["tls_status", "updated_at"])
        with self.assertRaisesRegex(DomainVerificationError, "آماده"):
            activate_custom_domain(store=self.store, domain=domain, actor=self.actor)

    @override_settings(RASTISI_CUSTOM_DOMAIN_READINESS_MAX_AGE_SECONDS=60)
    def test_rejects_stale_readiness(self):
        domain = self._verified_domain()
        stale = timezone.now() - timedelta(minutes=5)
        domain.routing_checked_at = stale
        domain.tls_checked_at = stale
        domain.save(update_fields=[
            "routing_checked_at", "tls_checked_at", "updated_at",
        ])
        self.assertFalse(custom_domain_is_ready_for_activation(domain))
        with self.assertRaisesRegex(DomainVerificationError, "آماده"):
            activate_custom_domain(store=self.store, domain=domain, actor=self.actor)


@override_settings(
    RASTISI_CUSTOM_DOMAIN_A_TARGETS=("203.0.113.10",),
    RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="domains.rastisi.ir",
)
class CheckDnsRoutingTests(TestCase):
    def test_connection_instructions_expose_configured_targets(self):
        result = custom_domain_connection_instructions("shop.example.com")
        self.assertTrue(result["configured"])
        self.assertEqual(result["a_targets"], ("203.0.113.10",))
        self.assertEqual(result["cname_target"], "domains.rastisi.ir")

    def test_matching_a_record_is_connected(self):
        def resolver(hostname, record_type, lifetime):
            if record_type == "A":
                return ["203.0.113.10"]
            raise dns.resolver.NoAnswer()

        with patch(_resolve_target(), side_effect=resolver):
            result = check_dns_routing("example.com")
        self.assertTrue(result.connected)

    def test_matching_cname_is_connected(self):
        class _Cname:
            target = "domains.rastisi.ir."

        def resolver(hostname, record_type, lifetime):
            if record_type == "A":
                raise dns.resolver.NoAnswer()
            if record_type == "CNAME":
                return [_Cname()]
            raise AssertionError(record_type)

        with patch(_resolve_target(), side_effect=resolver):
            result = check_dns_routing("shop.example.com")
        self.assertTrue(result.connected)
        self.assertEqual(result.observed_cname, "domains.rastisi.ir")

    def test_wrong_records_are_not_connected(self):
        def resolver(hostname, record_type, lifetime):
            if record_type == "A":
                return ["198.51.100.44"]
            raise dns.resolver.NoAnswer()

        with patch(_resolve_target(), side_effect=resolver):
            result = check_dns_routing("example.com")
        self.assertFalse(result.connected)


@override_settings(
    RASTISI_CUSTOM_DOMAIN_A_TARGETS=("203.0.113.10",),
    RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="",
)
class RefreshCustomDomainReadinessTests(DomainVerificationTestCase):
    def _verified_domain(self):
        domain = request_custom_domain(
            store=self.store, hostname="shop.example.com", actor=self.actor
        )
        domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
        domain.verified_at = timezone.now()
        domain.save(update_fields=[
            "verification_status", "verified_at", "updated_at",
        ])
        return domain

    def test_connected_dns_and_tls_are_persisted_ready(self):
        from apps.stores.services.domain_verification_service import (
            DnsRoutingCheck,
            SslConnectionCheck,
        )
        domain = self._verified_domain()
        routing = DnsRoutingCheck(
            configured=True, connected=True,
            expected_a_targets=("203.0.113.10",),
            observed_a_targets=("203.0.113.10",),
            expected_cname="", observed_cname="", error="",
        )
        tls = SslConnectionCheck(
            reachable=True, certificate_expires_at=None, error=""
        )
        with patch(
            "apps.stores.services.domain_verification_service.check_dns_routing",
            return_value=routing,
        ), patch(
            "apps.stores.services.domain_verification_service.check_ssl_connection",
            return_value=tls,
        ):
            result = refresh_custom_domain_readiness(
                domain=domain, actor=self.actor
            )
        self.assertTrue(result.ready)
        domain.refresh_from_db()
        self.assertEqual(domain.routing_status, StoreDomain.RoutingStatus.CONNECTED)
        self.assertEqual(domain.tls_status, StoreDomain.TlsStatus.READY)

    def test_disconnected_dns_skips_tls_and_persists_not_connected(self):
        from apps.stores.services.domain_verification_service import DnsRoutingCheck
        domain = self._verified_domain()
        routing = DnsRoutingCheck(
            configured=True, connected=False,
            expected_a_targets=("203.0.113.10",),
            observed_a_targets=("198.51.100.44",),
            expected_cname="", observed_cname="", error="",
        )
        with patch(
            "apps.stores.services.domain_verification_service.check_dns_routing",
            return_value=routing,
        ), patch(
            "apps.stores.services.domain_verification_service.check_ssl_connection"
        ) as tls_check:
            result = refresh_custom_domain_readiness(
                domain=domain, actor=self.actor
            )
        self.assertFalse(result.ready)
        tls_check.assert_not_called()
        domain.refresh_from_db()
        self.assertEqual(domain.routing_status, StoreDomain.RoutingStatus.NOT_CONNECTED)
        self.assertEqual(domain.tls_status, StoreDomain.TlsStatus.UNCHECKED)


class CheckSslConnectionTests(TestCase):
    """هرگز اتصالِ شبکه‌ی واقعی برقرار نمی‌کند — socket.create_connection و
    ssl.create_default_context mock می‌شوند، دقیقاً همان الگویِ mock‌کردنِ
    dns.resolver.resolve برایِ تستِ TXT."""

    def test_successful_handshake_reports_reachable_with_expiry(self):
        from unittest.mock import MagicMock

        fake_cert = {"notAfter": "Jan 1 00:00:00 2030 GMT"}
        fake_tls_sock = MagicMock()
        fake_tls_sock.__enter__.return_value.getpeercert.return_value = fake_cert
        fake_context = MagicMock()
        fake_context.wrap_socket.return_value = fake_tls_sock

        with patch("apps.stores.services.domain_verification_service.socket.create_connection") as mock_conn, \
             patch("apps.stores.services.domain_verification_service.ssl.create_default_context", return_value=fake_context):
            mock_conn.return_value.__enter__.return_value = MagicMock()
            result = check_ssl_connection("shop.example.com")

        self.assertTrue(result.reachable)
        self.assertEqual(result.certificate_expires_at.year, 2030)
        self.assertEqual(result.error, "")

    def test_connection_refused_reports_unreachable_without_raising(self):
        with patch(
            "apps.stores.services.domain_verification_service.socket.create_connection",
            side_effect=OSError("Connection refused"),
        ):
            result = check_ssl_connection("not-configured-yet.example.com")

        self.assertFalse(result.reachable)
        self.assertIsNone(result.certificate_expires_at)
        self.assertIn("refused", result.error.lower())

    def test_ssl_error_reports_unreachable_without_raising(self):
        import ssl as ssl_module

        with patch(
            "apps.stores.services.domain_verification_service.socket.create_connection",
        ) as mock_conn, patch(
            "apps.stores.services.domain_verification_service.ssl.create_default_context",
            side_effect=ssl_module.SSLError("bad certificate"),
        ):
            mock_conn.return_value.__enter__.return_value = None
            result = check_ssl_connection("bad-cert.example.com")

        self.assertFalse(result.reachable)

    def test_malformed_certificate_expiry_does_not_crash(self):
        from unittest.mock import MagicMock

        fake_cert = {"notAfter": "not-a-real-date"}
        fake_tls_sock = MagicMock()
        fake_tls_sock.__enter__.return_value.getpeercert.return_value = fake_cert
        fake_context = MagicMock()
        fake_context.wrap_socket.return_value = fake_tls_sock

        with patch("apps.stores.services.domain_verification_service.socket.create_connection") as mock_conn, \
             patch("apps.stores.services.domain_verification_service.ssl.create_default_context", return_value=fake_context):
            mock_conn.return_value.__enter__.return_value = MagicMock()
            result = check_ssl_connection("shop.example.com")

        self.assertTrue(result.reachable)
        self.assertIsNone(result.certificate_expires_at)
