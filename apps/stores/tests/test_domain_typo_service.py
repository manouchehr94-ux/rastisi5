from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.domain_typo_service import (
    suggest_domain_typo,
    suggest_similar_existing_domain,
    suggest_tld_correction,
)


def _verified_custom_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


class SuggestSimilarExistingDomainTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Shop", slug="typo-shop", status=Store.Status.ACTIVE)

    def test_no_existing_domains_returns_none(self):
        self.assertIsNone(suggest_similar_existing_domain(store=self.store, hostname="digigol.ir"))

    def test_close_typo_of_existing_domain_is_suggested(self):
        _verified_custom_domain(self.store, "digigol.ir")
        suggestion = suggest_similar_existing_domain(store=self.store, hostname="digigole.ir")
        self.assertEqual(suggestion, "digigol.ir")

    def test_exact_match_is_excluded_not_suggested_against_itself(self):
        _verified_custom_domain(self.store, "digigol.ir")
        self.assertIsNone(suggest_similar_existing_domain(store=self.store, hostname="digigol.ir"))

    def test_unrelated_domain_is_not_suggested(self):
        _verified_custom_domain(self.store, "digigol.ir")
        self.assertIsNone(suggest_similar_existing_domain(store=self.store, hostname="completely-different-brand.com"))

    def test_never_suggests_another_stores_domain(self):
        other_store = Store.objects.create(name="Other", slug="typo-other", status=Store.Status.ACTIVE)
        _verified_custom_domain(other_store, "digigol.ir")
        self.assertIsNone(suggest_similar_existing_domain(store=self.store, hostname="digigole.ir"))


class SuggestTldCorrectionTests(TestCase):
    def test_common_typo_of_com_is_corrected(self):
        self.assertEqual(suggest_tld_correction("shop.cm"), "shop.com")

    def test_common_typo_of_ir_is_corrected(self):
        self.assertEqual(suggest_tld_correction("shop.ri"), "shop.ir")

    def test_valid_common_tld_returns_none(self):
        self.assertIsNone(suggest_tld_correction("shop.ir"))
        self.assertIsNone(suggest_tld_correction("shop.com"))
        self.assertIsNone(suggest_tld_correction("shop.co.ir"))

    def test_no_dot_returns_none(self):
        self.assertIsNone(suggest_tld_correction("nodothere"))

    def test_wildly_different_tld_is_not_forced_into_a_suggestion(self):
        self.assertIsNone(suggest_tld_correction("shop.xyzxyzxyz"))


class SuggestDomainTypoTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Shop", slug="typo-combined", status=Store.Status.ACTIVE)

    def test_prefers_existing_domain_match_over_tld_correction(self):
        _verified_custom_domain(self.store, "digigol.ir")
        suggestion = suggest_domain_typo(store=self.store, hostname="digigole.ir")
        self.assertEqual(suggestion, "digigol.ir")

    def test_falls_back_to_tld_correction(self):
        suggestion = suggest_domain_typo(store=self.store, hostname="myshop.cm")
        self.assertEqual(suggestion, "myshop.com")

    def test_no_suggestion_for_a_clean_new_domain(self):
        self.assertIsNone(suggest_domain_typo(store=self.store, hostname="brand-new-shop.ir"))

    def test_never_mutates_the_input(self):
        original = "digigole.ir"
        _verified_custom_domain(self.store, "digigol.ir")
        suggest_domain_typo(store=self.store, hostname=original)
        self.assertEqual(original, "digigole.ir")
