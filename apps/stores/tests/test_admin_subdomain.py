"""Tests for ``Store.admin_subdomain`` and
``apps.stores.resolution.resolve_store_for_admin_host`` (Phase 1B).

Covers: auto-derivation for callers that don't set it explicitly, explicit
normalization/validation (case, invalid characters, reserved words),
uniqueness, independence from the public ``StoreDomain``, and host
resolution.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain
from apps.stores.resolution import resolve_store_for_admin_host


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class AdminSubdomainAutoDerivationTests(TestCase):
    def test_akhlaghi_seed_row_has_matching_admin_subdomain(self):
        """Backfilled by migration 0004 for the pre-existing seed row."""
        self.assertEqual(_akhlaghi().admin_subdomain, "akhlaghi")

    def test_ascii_slug_is_used_as_default(self):
        store = Store.objects.create(name="Digilool", slug="digilool")
        self.assertEqual(store.admin_subdomain, "digilool")

    def test_non_ascii_slug_falls_back_to_public_id_based_value(self):
        store = Store.objects.create(name="اخلاقی دو", slug="اخلاقی-دو")
        self.assertTrue(store.admin_subdomain.startswith("store-"))
        self.assertEqual(len(store.admin_subdomain), len("store-") + 12)

    def test_reserved_slug_falls_back_to_public_id_based_value(self):
        store = Store.objects.create(name="Admin Store", slug="admin")
        self.assertNotEqual(store.admin_subdomain, "admin")
        self.assertTrue(store.admin_subdomain.startswith("store-"))

    def test_explicit_value_is_normalized_not_overwritten(self):
        store = Store.objects.create(name="Explicit", slug="explicit-store", admin_subdomain="ExplicitSub")
        self.assertEqual(store.admin_subdomain, "explicitsub")


class AdminSubdomainValidationTests(TestCase):
    def test_uniqueness_enforced_at_validation_layer(self):
        Store.objects.create(name="A", slug="dupe-a", admin_subdomain="dupesub")
        with self.assertRaises(ValidationError):
            duplicate = Store(name="B", slug="dupe-b", admin_subdomain="dupesub")
            duplicate.full_clean()

    def test_uniqueness_enforced_at_database_layer(self):
        from django.db import IntegrityError, transaction

        Store.objects.create(name="A2", slug="dupe-a2", admin_subdomain="dupesub2")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Store.objects.create(name="B2", slug="dupe-b2", admin_subdomain="dupesub2")

    def test_invalid_characters_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("bad_sub!domain")

    def test_leading_or_trailing_hyphen_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("-badsub")
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("badsub-")

    def test_reserved_word_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("www")
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("admin")
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("chatchat")
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("platformadmins")

    def test_case_is_normalized(self):
        self.assertEqual(normalize_admin_subdomain("DigiLool"), "digilool")

    def test_empty_value_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("")
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("   ")

    def test_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_admin_subdomain("a" * 64)


class AdminSubdomainIndependentOfPublicDomainTests(TestCase):
    """Changing/losing a Store's public StoreDomain must never affect its
    admin_subdomain."""

    def test_admin_subdomain_survives_public_domain_change(self):
        store = Store.objects.create(name="Digilool", slug="digilool-indep")
        original_admin_subdomain = store.admin_subdomain

        from django.utils import timezone

        StoreDomain.objects.create(
            store=store, hostname="digilool.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        store.refresh_from_db()
        self.assertEqual(store.admin_subdomain, original_admin_subdomain)

        # Public domain changes entirely (merchant moves to a new TLD) —
        # admin_subdomain must be untouched.
        StoreDomain.objects.filter(store=store).delete()
        StoreDomain.objects.create(
            store=store, hostname="digilool.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        store.refresh_from_db()
        self.assertEqual(store.admin_subdomain, original_admin_subdomain)


@override_settings(RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class ResolveStoreForAdminHostTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Digilool", slug="digilool-rsah", admin_subdomain="digilool-rsah",
            status=Store.Status.ACTIVE,
        )

    def test_matching_admin_host_resolves_store(self):
        resolved = resolve_store_for_admin_host("digilool-rsah.rastisi.ir")
        self.assertEqual(resolved, self.store)

    def test_matching_admin_host_with_port_resolves_store(self):
        resolved = resolve_store_for_admin_host("digilool-rsah.rastisi.ir:8443")
        self.assertEqual(resolved, self.store)

    def test_case_insensitive(self):
        resolved = resolve_store_for_admin_host("Digilool-RSAH.RASTISI.IR")
        self.assertEqual(resolved, self.store)

    def test_unknown_subdomain_returns_none(self):
        self.assertIsNone(resolve_store_for_admin_host("nonexistent.rastisi.ir"))

    def test_non_admin_suffix_host_returns_none(self):
        """A Store's own public storefront domain must not resolve here —
        this is the whole point of keeping the two resolution paths separate."""
        self.assertIsNone(resolve_store_for_admin_host("digilool.ir"))

    def test_bare_suffix_with_no_label_returns_none(self):
        self.assertIsNone(resolve_store_for_admin_host("rastisi.ir"))

    def test_extra_label_before_subdomain_returns_none(self):
        self.assertIsNone(resolve_store_for_admin_host("extra.digilool-rsah.rastisi.ir"))

    def test_inactive_store_returns_none(self):
        Store.objects.filter(pk=self.store.pk).update(status=Store.Status.SUSPENDED)
        self.assertIsNone(resolve_store_for_admin_host("digilool-rsah.rastisi.ir"))

    def test_custom_suffix_setting_respected(self):
        with override_settings(RASTISI_ADMIN_DOMAIN_SUFFIX="example-platform.test"):
            self.assertIsNone(resolve_store_for_admin_host("digilool-rsah.rastisi.ir"))
