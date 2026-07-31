from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.subscriptions.models import Plan, PlanVersion


class SeedDefaultPlansTests(TestCase):
    def test_creates_exactly_four_plans(self):
        call_command("seed_default_plans", stdout=StringIO())
        codes = set(Plan.objects.values_list("code", flat=True))
        self.assertTrue({"trial", "basic", "professional", "enterprise"} <= codes)

    def test_each_plan_has_exactly_one_published_version(self):
        call_command("seed_default_plans", stdout=StringIO())
        for code in ("trial", "basic", "professional", "enterprise"):
            plan = Plan.objects.get(code=code)
            self.assertEqual(plan.versions.count(), 1)
            self.assertEqual(plan.versions.first().status, PlanVersion.Status.PUBLISHED)

    def test_trial_plan_trial_days_comes_from_platform_configuration(self):
        from apps.portal.services.platform_config_service import update_platform_configuration
        from django.contrib.auth import get_user_model

        superuser = get_user_model().objects.create_user(
            username="seedplan-admin@example.com", email="seedplan-admin@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        update_platform_configuration(actor=superuser, default_trial_days=45)

        call_command("seed_default_plans", stdout=StringIO())
        trial_version = Plan.objects.get(code="trial").versions.first()
        self.assertEqual(trial_version.trial_days, 45)

    def test_rerunning_is_idempotent_no_duplicate_plans_or_versions(self):
        call_command("seed_default_plans", stdout=StringIO())
        call_command("seed_default_plans", stdout=StringIO())
        self.assertEqual(Plan.objects.filter(code="trial").count(), 1)
        self.assertEqual(Plan.objects.get(code="trial").versions.count(), 1)

    def test_rerunning_never_touches_a_manually_customized_plan_version(self):
        call_command("seed_default_plans", stdout=StringIO())
        basic = Plan.objects.get(code="basic")
        version = basic.versions.first()
        original_price = version.display_price

        # Simulate manual customization elsewhere (e.g. Platform Admin) —
        # a re-run must not clobber it.
        Plan.objects.filter(pk=basic.pk).update(public_title="پایه (ویژه)")

        call_command("seed_default_plans", stdout=StringIO())
        basic.refresh_from_db()
        self.assertEqual(basic.public_title, "پایه (ویژه)")
        self.assertEqual(basic.versions.first().display_price, original_price)
        self.assertEqual(basic.versions.count(), 1)

    def test_plans_have_real_entitlements_not_empty(self):
        call_command("seed_default_plans", stdout=StringIO())
        for code in ("trial", "basic", "professional", "enterprise"):
            version = Plan.objects.get(code=code).versions.first()
            self.assertGreater(version.plan_entitlements.count(), 0)

    def test_enterprise_plan_has_unlimited_product_entitlement(self):
        from apps.subscriptions.entitlements import CATALOG_PRODUCTS

        call_command("seed_default_plans", stdout=StringIO())
        version = Plan.objects.get(code="enterprise").versions.first()
        entitlement = version.plan_entitlements.get(entitlement__key=CATALOG_PRODUCTS)
        self.assertTrue(entitlement.is_unlimited)

    def test_trial_plan_has_no_custom_domain_entitlement(self):
        call_command("seed_default_plans", stdout=StringIO())
        version = Plan.objects.get(code="trial").versions.first()
        entitlement = version.plan_entitlements.get(entitlement__key="domains.custom")
        self.assertFalse(entitlement.is_enabled)
