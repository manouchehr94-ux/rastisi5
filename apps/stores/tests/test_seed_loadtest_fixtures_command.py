"""Django tests for ``seed_loadtest_fixtures`` — the deterministic,
disposable multi-tenant fixture seeder the Phase 3 Locust suite depends
on. See loadtest/README.md for how these fixtures are used."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


class SeedLoadtestFixturesCommandTests(TestCase):
    def _run(self, *args, **kwargs):
        call_command("seed_loadtest_fixtures", *args, stdout=StringIO(), **kwargs)

    def test_creates_requested_number_of_stores(self):
        self._run("--stores", "3", "--products-per-store", "5")
        self.assertEqual(Store.objects.filter(slug__startswith="loadtest-").count(), 3)

    def test_every_store_has_the_fixed_product_slug_locustfile_depends_on(self):
        """loadtest/locustfile.py hardcodes 'loadtest-product-1' — this is
        the contract between the seeder and the Locust tasks."""
        self._run("--stores", "2", "--products-per-store", "5")
        for store in Store.objects.filter(slug__startswith="loadtest-"):
            self.assertTrue(Product.objects.filter(store=store, slug="loadtest-product-1").exists())

    def test_creates_verified_platform_subdomain_for_each_store(self):
        self._run("--stores", "1", "--products-per-store", "1")
        store = Store.objects.get(slug="loadtest-1")
        domain = StoreDomain.objects.get(store=store)
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.PLATFORM_SUBDOMAIN)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertTrue(domain.is_primary)

    def test_provisions_shop_settings_so_product_detail_does_not_500(self):
        """Regression coverage for a real bug this suite's own smoke test
        caught: product_detail() -> is_gift_wrap_available() ->
        ShopSettings.load() raises ShopSettingsNotProvisionedError unless
        ShopSettings.provision_for(store) has been called."""
        self._run("--stores", "1", "--products-per-store", "1")
        store = Store.objects.get(slug="loadtest-1")
        self.assertTrue(ShopSettings.objects.filter(store=store).exists())

    def test_shared_admin_user_has_owner_membership_in_every_store(self):
        self._run("--stores", "3", "--products-per-store", "1")
        admin = User.objects.get(username="09120000001")
        for store in Store.objects.filter(slug__startswith="loadtest-"):
            membership = StoreMembership.objects.get(store=store, user=admin)
            self.assertEqual(membership.role, StoreMembership.Role.OWNER)
            self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_admin_password_is_settable_and_actually_usable_for_login(self):
        self._run("--stores", "1", "--products-per-store", "1", "--admin-password", "MyCustomPass!1")
        admin = User.objects.get(username="09120000001")
        self.assertTrue(admin.check_password("MyCustomPass!1"))

    def test_idempotent_rerun_does_not_duplicate_products_or_stores(self):
        self._run("--stores", "2", "--products-per-store", "10")
        self._run("--stores", "2", "--products-per-store", "10")
        self.assertEqual(Store.objects.filter(slug__startswith="loadtest-").count(), 2)
        self.assertEqual(Product.objects.filter(store__slug="loadtest-1").count(), 10)

    def test_categories_and_vendor_created_per_store(self):
        self._run("--stores", "1", "--products-per-store", "1")
        store = Store.objects.get(slug="loadtest-1")
        self.assertTrue(Vendor.objects.filter(store=store).exists())
        self.assertEqual(Category.objects.filter(store=store).count(), 3)

    def test_rejects_zero_or_negative_counts(self):
        with self.assertRaises(CommandError):
            self._run("--stores", "0")
        with self.assertRaises(CommandError):
            self._run("--products-per-store", "0")

    @override_settings(DEBUG=False, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir", RASTISI_CANONICAL_DOMAIN_SUFFIX="rastisi.ir")
    def test_refuses_to_run_when_indistinguishable_from_production(self):
        with self.assertRaises(CommandError):
            self._run("--stores", "1", "--products-per-store", "1")
        self.assertFalse(Store.objects.filter(slug__startswith="loadtest-").exists())

    @override_settings(DEBUG=False, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir", RASTISI_CANONICAL_DOMAIN_SUFFIX="rastisi.ir")
    def test_confirm_flag_overrides_the_production_lookalike_guard(self):
        self._run("--stores", "1", "--products-per-store", "1", "--confirm-not-production")
        self.assertTrue(Store.objects.filter(slug="loadtest-1").exists())

    def test_staging_domain_suffix_never_triggers_the_guard(self):
        """The default test/dev domain suffix (rastisi.localhost, or any
        non-rastisi.ir staging suffix) must never require the confirm
        flag — the guard is specifically about the *real* production
        domain, not DEBUG=False on its own."""
        with override_settings(DEBUG=False, RASTISI_ADMIN_DOMAIN_SUFFIX="loadtest-staging.example"):
            self._run("--stores", "1", "--products-per-store", "1")
        self.assertTrue(Store.objects.filter(slug="loadtest-1").exists())
