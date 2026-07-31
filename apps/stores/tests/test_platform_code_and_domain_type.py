from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.platform_code_service import generate_unique_platform_code


def _make_store(**kwargs):
    kwargs.setdefault("name", "Test Store")
    kwargs.setdefault("slug", f"test-store-{Store.objects.count()}")
    kwargs.setdefault("status", Store.Status.ACTIVE)
    kwargs.setdefault("platform_code", generate_unique_platform_code())
    return Store.objects.create(**kwargs)


class PlatformCodeGenerationTests(TestCase):
    def test_generated_code_matches_alphabet_and_length(self):
        code = generate_unique_platform_code()
        self.assertEqual(len(code), 9)
        self.assertTrue(set(code) <= set("abcdefghjkmnpqrstuvwxyz23456789"))
        self.assertFalse(set(code) & set("0o1li"))

    def test_two_generated_codes_are_different(self):
        first = generate_unique_platform_code()
        store = _make_store(slug="pc-store-1", platform_code=first)
        second = generate_unique_platform_code()
        self.assertNotEqual(first, second)
        self.assertTrue(Store.objects.filter(pk=store.pk).exists())

    def test_platform_code_must_be_unique_at_db_level(self):
        code = generate_unique_platform_code()
        _make_store(slug="pc-store-a", platform_code=code)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _make_store(slug="pc-store-b", platform_code=code)


class StoreDomainTypeAndRedirectTests(TestCase):
    def setUp(self):
        self.store = _make_store(slug="dt-store")

    def test_default_domain_type_is_custom_domain(self):
        domain = StoreDomain.objects.create(store=self.store, hostname="example.com")
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.CUSTOM_DOMAIN)
        self.assertFalse(domain.is_redirect)

    def test_generated_trial_domain_type_can_be_set(self):
        domain = StoreDomain.objects.create(
            store=self.store,
            hostname=f"{self.store.platform_code}.rastisi.ir",
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
            is_primary=True,
        )
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.GENERATED_TRIAL)

    def test_redirect_domain_cannot_also_be_primary_via_clean(self):
        domain = StoreDomain(
            store=self.store, hostname="old.example.com", is_primary=True, is_redirect=True,
        )
        with self.assertRaises(ValidationError):
            domain.clean()

    def test_redirect_domain_cannot_also_be_primary_at_db_level(self):
        # Bypasses save()/clean() entirely via a raw update() (not blocked
        # the way StoreDomainQuerySet.update() blocks "hostname") to prove
        # the DB CheckConstraint itself — not just the Python-level guard —
        # rejects this state.
        domain = StoreDomain.objects.create(
            store=self.store, hostname="old2.example.com", is_primary=False, is_redirect=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.filter(pk=domain.pk).update(is_primary=True)

    def test_non_primary_redirect_domain_is_allowed(self):
        primary = StoreDomain.objects.create(
            store=self.store, hostname="new.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        alias = StoreDomain.objects.create(
            store=self.store, hostname="old.example.com", is_primary=False, is_redirect=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.assertTrue(alias.is_redirect)
        self.assertFalse(alias.is_primary)
        self.assertTrue(primary.is_primary)
