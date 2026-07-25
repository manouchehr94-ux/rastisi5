from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain, StoreDomainMutationError


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
            verification_token="pending-token",
        )
        domain.full_clean()
        domain.save()
        self.assertIsNotNone(domain.pk)

    def test_non_verified_status_must_not_retain_verified_at(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.FAILED,
            verified_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_non_verified_status_must_not_retain_verified_at_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_a,
                    hostname="shop.example.com",
                    verification_status=StoreDomain.VerificationStatus.FAILED,
                    verified_at=timezone.now(),
                )

    def test_verified_status_requires_verified_at_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_a,
                    hostname="shop.example.com",
                    verification_status=StoreDomain.VerificationStatus.VERIFIED,
                )

    def test_pending_status_requires_verification_requested_at(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_token="pending-token",
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_pending_status_requires_verification_requested_at_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_a,
                    hostname="shop.example.com",
                    verification_status=StoreDomain.VerificationStatus.PENDING,
                    verification_token="pending-token",
                )

    def test_pending_status_requires_non_empty_verification_token(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_pending_status_requires_non_empty_verification_token_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(
                    store=self.store_a,
                    hostname="shop.example.com",
                    verification_status=StoreDomain.VerificationStatus.PENDING,
                    verification_requested_at=timezone.now(),
                )

    def test_pending_status_with_token_and_requested_at_is_valid(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
            verification_token="pending-token",
        )
        domain.full_clean()
        domain.save()
        self.assertIsNotNone(domain.pk)

    def test_unverified_status_with_no_lifecycle_fields_is_valid(self):
        domain = StoreDomain(store=self.store_a, hostname="shop.example.com")
        domain.full_clean()
        domain.save()
        self.assertIsNotNone(domain.pk)

    def test_failed_status_with_no_verified_at_is_valid(self):
        domain = StoreDomain(
            store=self.store_a,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.FAILED,
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


class StoreDomainMutationProtectionTests(TestCase):
    """Adversarial coverage for the bulk/queryset write paths that bypass
    ``Model.save()``/``Model.clean()`` entirely: ``QuerySet.update()`` and
    ``QuerySet.bulk_create()``. Without ``StoreDomainQuerySet``, both could
    silently persist a raw, un-normalized, or differently-cased hostname.
    """

    def setUp(self):
        self.store_a = Store.objects.create(name="Store A", slug="store-a")
        self.store_b = Store.objects.create(name="Store B", slug="store-b")

    def test_queryset_update_of_hostname_is_rejected(self):
        domain = StoreDomain.objects.create(
            store=self.store_a, hostname="shop.example.com"
        )
        with self.assertRaises(StoreDomainMutationError):
            StoreDomain.objects.filter(pk=domain.pk).update(
                hostname="HTTPS://Sneaky.Example.COM"
            )
        domain.refresh_from_db()
        self.assertEqual(domain.hostname, "shop.example.com")

    def test_queryset_update_of_hostname_cannot_bypass_via_differently_cased_value(self):
        domain = StoreDomain.objects.create(
            store=self.store_a, hostname="shop.example.com"
        )
        with self.assertRaises(StoreDomainMutationError):
            StoreDomain.objects.filter(pk=domain.pk).update(hostname="SHOP.EXAMPLE.COM")
        domain.refresh_from_db()
        self.assertEqual(domain.hostname, "shop.example.com")

    def test_queryset_update_of_other_fields_still_works(self):
        domain = StoreDomain.objects.create(
            store=self.store_a, hostname="shop.example.com"
        )
        StoreDomain.objects.filter(pk=domain.pk).update(is_primary=True)
        domain.refresh_from_db()
        self.assertTrue(domain.is_primary)

    def test_bulk_create_normalizes_hostname_before_insertion(self):
        StoreDomain.objects.bulk_create(
            [StoreDomain(store=self.store_a, hostname=" Shop.Example.COM. ")]
        )
        domain = StoreDomain.objects.get(store=self.store_a)
        self.assertEqual(domain.hostname, "shop.example.com")

    def test_bulk_create_rejects_malformed_hostname(self):
        with self.assertRaises(ValidationError):
            StoreDomain.objects.bulk_create(
                [StoreDomain(store=self.store_a, hostname="https://shop.example.com")]
            )
        self.assertFalse(StoreDomain.objects.filter(store=self.store_a).exists())

    def test_bulk_create_rejects_incoherent_verification_lifecycle(self):
        with self.assertRaises(ValidationError):
            StoreDomain.objects.bulk_create(
                [
                    StoreDomain(
                        store=self.store_a,
                        hostname="shop.example.com",
                        verification_status=StoreDomain.VerificationStatus.VERIFIED,
                    )
                ]
            )
        self.assertFalse(StoreDomain.objects.filter(store=self.store_a).exists())

    def test_bulk_create_cannot_be_used_to_bypass_case_based_deduplication(self):
        StoreDomain.objects.create(store=self.store_a, hostname="shop.example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.bulk_create(
                    [StoreDomain(store=self.store_b, hostname="SHOP.EXAMPLE.COM")]
                )

    def test_bulk_create_normalizes_every_instance_in_a_multi_object_batch(self):
        StoreDomain.objects.bulk_create(
            [
                StoreDomain(store=self.store_a, hostname="One.Example.com"),
                StoreDomain(store=self.store_b, hostname="Two.Example.com."),
            ]
        )
        self.assertEqual(
            StoreDomain.objects.get(store=self.store_a).hostname, "one.example.com"
        )
        self.assertEqual(
            StoreDomain.objects.get(store=self.store_b).hostname, "two.example.com"
        )
