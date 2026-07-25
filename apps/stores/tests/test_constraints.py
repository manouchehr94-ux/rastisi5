from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain


class StoreDomainConstraintTests(TestCase):
    """Database-level constraint coverage for StoreDomain.

    IntegrityError assertions are wrapped in ``transaction.atomic()`` so a
    caught database error does not leave the outer test transaction broken
    for subsequent statements in the same test.
    """

    def setUp(self):
        self.store_a = Store.objects.create(name="Store A", slug="store-a")
        self.store_b = Store.objects.create(name="Store B", slug="store-b")

    def test_duplicate_hostname_rejected_by_validation(self):
        StoreDomain.objects.create(store=self.store_a, hostname="shop.example.com")
        with self.assertRaises(ValidationError):
            dup = StoreDomain(store=self.store_b, hostname="shop.example.com")
            dup.full_clean()

    def test_duplicate_hostname_rejected_at_database_level(self):
        StoreDomain.objects.create(store=self.store_a, hostname="shop.example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_b, hostname="shop.example.com"
                )

    def test_one_primary_domain_per_store_allowed(self):
        domain = StoreDomain.objects.create(
            store=self.store_a, hostname="shop.example.com", is_primary=True
        )
        self.assertTrue(domain.is_primary)

    def test_second_primary_domain_for_same_store_rejected(self):
        StoreDomain.objects.create(
            store=self.store_a, hostname="one.example.com", is_primary=True
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_a, hostname="two.example.com", is_primary=True
                )

    def test_non_primary_domains_for_same_store_are_unlimited(self):
        StoreDomain.objects.create(store=self.store_a, hostname="one.example.com")
        StoreDomain.objects.create(store=self.store_a, hostname="two.example.com")
        self.assertEqual(StoreDomain.objects.filter(store=self.store_a).count(), 2)

    def test_primary_domains_for_different_stores_allowed(self):
        StoreDomain.objects.create(
            store=self.store_a, hostname="one.example.com", is_primary=True
        )
        StoreDomain.objects.create(
            store=self.store_b, hostname="two.example.com", is_primary=True
        )
        self.assertEqual(StoreDomain.objects.filter(is_primary=True).count(), 2)

    def test_store_may_have_no_primary_domain_during_provisioning(self):
        StoreDomain.objects.create(
            store=self.store_a, hostname="one.example.com", is_primary=False
        )
        self.assertFalse(
            StoreDomain.objects.filter(store=self.store_a, is_primary=True).exists()
        )

    def test_store_deletion_cascades_to_domains(self):
        StoreDomain.objects.create(store=self.store_a, hostname="shop.example.com")
        self.store_a.delete()
        self.assertFalse(
            StoreDomain.objects.filter(hostname="shop.example.com").exists()
        )

    def test_verified_status_requires_verified_at(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_verified_status_with_verified_at_is_valid(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        domain.full_clean()
        domain.save()
        self.assertIsNotNone(domain.pk)

    def test_pending_status_does_not_require_verified_at(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
        )
        domain.full_clean()
        domain.save()
        self.assertIsNotNone(domain.pk)

    def test_duplicate_verification_token_rejected(self):
        StoreDomain.objects.create(
            store=self.store_a,
            hostname="one.example.com",
            verification_token="shared-token",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_b,
                    hostname="two.example.com",
                    verification_token="shared-token",
                )

    def test_multiple_domains_with_empty_verification_token_are_allowed(self):
        StoreDomain.objects.create(store=self.store_a, hostname="one.example.com")
        StoreDomain.objects.create(store=self.store_b, hostname="two.example.com")
        self.assertEqual(StoreDomain.objects.count(), 2)

    def test_hostname_persisted_in_normalized_form(self):
        domain = StoreDomain.objects.create(
            store=self.store_a, hostname=" Shop.Example.COM. "
        )
        domain.refresh_from_db()
        self.assertEqual(domain.hostname, "shop.example.com")
