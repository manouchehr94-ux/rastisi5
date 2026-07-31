"""Section 12 — custom domain DNS verification. A domain is NEVER marked
verified by anything other than a real (here, mocked) DNS TXT lookup; a
failed/absent lookup always leaves it retryable, never silently verified."""

from unittest.mock import patch

import dns.resolver
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.domain_verification_service import (
    DomainVerificationError,
    activate_custom_domain,
    begin_dns_verification,
    check_dns_verification,
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

    def test_rejects_a_domain_belonging_to_another_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر فعال‌سازی", slug="domain-verify-activate-other", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="domain-verify-activate-other",
        )
        domain = self._verified_domain()
        with self.assertRaises(DomainVerificationError):
            activate_custom_domain(store=other_store, domain=domain, actor=self.actor)
