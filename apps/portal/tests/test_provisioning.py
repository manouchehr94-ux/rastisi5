from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation, Warehouse
from apps.core.models import AuditLogEntry, ShopSettings
from apps.portal.services import provisioning_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()


def _make_owner(email="owner@example.com"):
    return User.objects.create_user(username=email, email=email, password="a-very-strong-pass-1")


class ProvisionTrialStoreTests(TestCase):
    def setUp(self):
        self.owner = _make_owner()

    def test_creates_active_store_with_platform_code_and_admin_subdomain(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="Novin Shop")
        self.assertEqual(store.status, Store.Status.ACTIVE)
        self.assertEqual(len(store.platform_code), 9)
        self.assertTrue(store.admin_subdomain)

    def test_creates_active_owner_membership(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="Novin Shop")
        membership = StoreMembership.objects.get(store=store, user=self.owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertIsNotNone(membership.accepted_at)

    def test_creates_verified_primary_trial_domain_matching_platform_code(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="Novin Shop")
        domain = StoreDomain.objects.get(store=store)
        self.assertTrue(domain.is_primary)
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.GENERATED_TRIAL)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertTrue(domain.hostname.startswith(store.platform_code))

    def test_provisions_shop_settings_and_default_warehouse(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="Novin Shop")
        self.assertTrue(ShopSettings.objects.filter(store=store).exists())
        self.assertTrue(Warehouse.objects.filter(store=store, is_default=True).exists())

    def test_records_audit_event(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="Novin Shop")
        self.assertTrue(
            AuditLogEntry.objects.filter(store=store, action_code="store.trial_provisioned").exists()
        )

    def test_rejects_blank_name(self):
        with self.assertRaises(provisioning_service.ProvisioningError):
            provisioning_service.provision_trial_store(owner=self.owner, name="   ")
        self.assertFalse(Store.objects.filter(slug__startswith="store").exists())

    def test_two_stores_with_same_name_get_different_slugs(self):
        first = provisioning_service.provision_trial_store(owner=self.owner, name="Same Name")
        second_owner = _make_owner("owner2@example.com")
        second = provisioning_service.provision_trial_store(owner=second_owner, name="Same Name")
        self.assertNotEqual(first.slug, second.slug)
        self.assertNotEqual(first.platform_code, second.platform_code)

    @override_settings(RASTISI_MAX_STORES_PER_OWNER=1)
    def test_enforces_per_owner_store_cap(self):
        provisioning_service.provision_trial_store(owner=self.owner, name="First Store")
        with self.assertRaises(provisioning_service.ProvisioningError):
            provisioning_service.provision_trial_store(owner=self.owner, name="Second Store")
        self.assertEqual(
            StoreMembership.objects.filter(user=self.owner, role=StoreMembership.Role.OWNER).count(), 1,
        )

    def test_failure_midway_does_not_leave_a_partial_store(self):
        store_count_before = Store.objects.count()
        with self.assertRaises(provisioning_service.ProvisioningError):
            provisioning_service.provision_trial_store(owner=self.owner, name="")
        self.assertEqual(Store.objects.count(), store_count_before)


class ProvisionWithIndustryTemplateTests(TestCase):
    def setUp(self):
        self.owner = _make_owner()
        self.template = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )

    def test_installs_industry_template_when_provided(self):
        store = provisioning_service.provision_trial_store(
            owner=self.owner, name="Clothing Store", industry_template=self.template,
        )
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=store).exists())

    def test_no_installation_when_industry_template_omitted(self):
        store = provisioning_service.provision_trial_store(owner=self.owner, name="No Industry Store")
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=store).exists())


class LatestOfferableIndustryTemplatesTests(TestCase):
    def test_returns_only_the_latest_production_ready_version_per_slug(self):
        IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک v1", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        v2 = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک v2", version=2,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        IndustryTemplate.objects.create(
            slug="electronics", name="لوازم الکترونیک", version=1,
            readiness=IndustryTemplate.Readiness.DRAFT, is_active=True,
        )
        results = provisioning_service.latest_offerable_industry_templates()
        slugs = [t.slug for t in results]
        self.assertEqual(slugs.count("clothing"), 1)
        self.assertIn(v2, results)
        self.assertNotIn("electronics", slugs)
