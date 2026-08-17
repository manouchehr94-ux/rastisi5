from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services import provisioning_service
from apps.stores.models import Store, StoreDomain
from apps.stores.services.domain_namespace_service import (
    DomainNamespaceCollisionError,
    assert_admin_subdomain_namespace_available,
    assert_public_handle_namespace_available,
    platform_owned_hosts_for_label,
)

User = get_user_model()


@override_settings(
    RASTISI_CANONICAL_DOMAIN_SUFFIX="rastisi.ir",
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.localhost",
)
class DomainNamespaceWriteGuardTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.create(
            name="Store A", slug="namespace-store-a",
            admin_subdomain="blue", status=Store.Status.ACTIVE,
        )
        self.store_b = Store.objects.create(
            name="Store B", slug="namespace-store-b",
            admin_subdomain="green", status=Store.Status.ACTIVE,
        )

    def _platform_domain(self, store, hostname):
        return StoreDomain.objects.create(
            store=store,
            hostname=hostname,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    def test_owned_hosts_include_canonical_and_runtime_suffixes(self):
        self.assertEqual(
            platform_owned_hosts_for_label("Blue"),
            frozenset({"blue.rastisi.ir", "blue.rastisi.localhost"}),
        )

    def test_public_handle_rejects_another_stores_admin_subdomain(self):
        with self.assertRaises(DomainNamespaceCollisionError):
            assert_public_handle_namespace_available(
                store=self.store_b, label="blue",
            )

    def test_public_handle_allows_same_stores_admin_label(self):
        assert_public_handle_namespace_available(
            store=self.store_a, label="blue",
        )

    def test_admin_subdomain_rejects_another_stores_canonical_public_handle(self):
        self._platform_domain(self.store_a, "purple.rastisi.ir")
        with self.assertRaises(DomainNamespaceCollisionError):
            assert_admin_subdomain_namespace_available(
                store=self.store_b, label="purple",
            )

    def test_admin_subdomain_rejects_another_stores_local_runtime_handle(self):
        self._platform_domain(self.store_a, "orange.rastisi.localhost")
        with self.assertRaises(DomainNamespaceCollisionError):
            assert_admin_subdomain_namespace_available(
                store=self.store_b, label="orange",
            )

    def test_admin_subdomain_allows_same_store_public_label(self):
        self._platform_domain(self.store_a, "blue.rastisi.ir")
        assert_admin_subdomain_namespace_available(
            store=self.store_a, label="blue",
        )


class ProvisioningNamespaceIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="namespace-provision-owner",
            password="a-very-strong-pass-1",
        )

    @patch(
        "apps.portal.services.provisioning_service."
        "assert_admin_subdomain_namespace_available"
    )
    def test_collision_rolls_back_partial_provisioned_store(self, namespace_guard):
        namespace_guard.side_effect = DomainNamespaceCollisionError(
            "namespace collision"
        )
        before = Store.objects.count()

        with self.assertRaises(provisioning_service.ProvisioningError):
            provisioning_service.provision_trial_store(
                owner=self.owner, name="Rollback Namespace Store",
            )

        self.assertEqual(Store.objects.count(), before)
