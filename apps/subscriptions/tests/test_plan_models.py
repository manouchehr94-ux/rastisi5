"""Tests for the Checkpoint 5A Plan/PlanVersion/Entitlement foundation:
model constraints, published-version immutability, entitlement value-type
validation, and unlimited representation."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.subscriptions.entitlements import sync_entitlement_definitions
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
)
from apps.subscriptions.services import plan_service


class PlanModelTests(TestCase):
    def test_plan_code_globally_unique(self):
        Plan.objects.create(code="starter", name="Starter")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plan.objects.create(code="starter", name="Duplicate")

    def test_plan_version_number_unique_per_plan(self):
        plan = Plan.objects.create(code="pro", name="Pro")
        PlanVersion.objects.create(plan=plan, version_number=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlanVersion.objects.create(plan=plan, version_number=1)

    def test_same_version_number_allowed_across_plans(self):
        p1 = Plan.objects.create(code="a", name="A")
        p2 = Plan.objects.create(code="b", name="B")
        PlanVersion.objects.create(plan=p1, version_number=1)
        PlanVersion.objects.create(plan=p2, version_number=1)  # must not raise


class EntitlementValueTypeTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(code="c", name="C")
        self.version = PlanVersion.objects.create(plan=self.plan, version_number=1)
        self.bool_def = EntitlementDefinition.objects.create(
            key="catalog.import", name="Import", entitlement_type=EntitlementDefinition.EntitlementType.BOOLEAN,
        )
        self.int_def = EntitlementDefinition.objects.create(
            key="catalog.products", name="Products", entitlement_type=EntitlementDefinition.EntitlementType.INTEGER_LIMIT,
        )

    def test_integer_limit_requires_value_or_unlimited(self):
        ent = PlanEntitlement(plan_version=self.version, entitlement=self.int_def, is_enabled=True)
        with self.assertRaises(ValidationError):
            ent.full_clean()

    def test_integer_limit_with_value_valid(self):
        ent = PlanEntitlement(plan_version=self.version, entitlement=self.int_def, integer_limit=100)
        ent.full_clean()  # must not raise

    def test_unlimited_integer_limit_valid(self):
        ent = PlanEntitlement(plan_version=self.version, entitlement=self.int_def, is_unlimited=True)
        ent.full_clean()
        self.assertIsNone(ent.resolved_limit())

    def test_resolved_limit_returns_value_when_bounded(self):
        ent = PlanEntitlement(plan_version=self.version, entitlement=self.int_def, integer_limit=50)
        self.assertEqual(ent.resolved_limit(), 50)

    def test_unlimited_on_boolean_rejected(self):
        ent = PlanEntitlement(plan_version=self.version, entitlement=self.bool_def, is_unlimited=True)
        with self.assertRaises(ValidationError):
            ent.full_clean()

    def test_negative_integer_limit_rejected_by_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlanEntitlement.objects.create(
                    plan_version=self.version, entitlement=self.int_def, integer_limit=-1,
                )

    def test_duplicate_entitlement_per_version_rejected(self):
        PlanEntitlement.objects.create(plan_version=self.version, entitlement=self.int_def, integer_limit=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlanEntitlement.objects.create(plan_version=self.version, entitlement=self.int_def, integer_limit=2)


class PlanServiceTests(TestCase):
    def setUp(self):
        sync_entitlement_definitions()
        self.plan = Plan.objects.create(code="business", name="Business")

    def test_create_and_publish_version(self):
        version = plan_service.create_plan_version(self.plan)
        self.assertEqual(version.version_number, 1)
        self.assertEqual(version.status, PlanVersion.Status.DRAFT)
        published = plan_service.publish_plan_version(version)
        self.assertEqual(published.status, PlanVersion.Status.PUBLISHED)
        self.assertIsNotNone(published.published_at)

    def test_publish_is_idempotent(self):
        version = plan_service.create_plan_version(self.plan)
        plan_service.publish_plan_version(version)
        again = plan_service.publish_plan_version(version)  # must not raise
        self.assertEqual(again.status, PlanVersion.Status.PUBLISHED)

    def test_cannot_edit_entitlement_on_published_version(self):
        version = plan_service.create_plan_version(self.plan)
        plan_service.set_plan_entitlement(version, "catalog.products", integer_limit=100)
        plan_service.publish_plan_version(version)
        with self.assertRaises(plan_service.PlanServiceError):
            plan_service.set_plan_entitlement(version, "catalog.products", integer_limit=200)

    def test_retire_only_published(self):
        version = plan_service.create_plan_version(self.plan)
        with self.assertRaises(plan_service.PlanServiceError):
            plan_service.retire_plan_version(version)
        plan_service.publish_plan_version(version)
        retired = plan_service.retire_plan_version(version)
        self.assertEqual(retired.status, PlanVersion.Status.RETIRED)

    def test_auto_increments_version_number(self):
        v1 = plan_service.create_plan_version(self.plan)
        v2 = plan_service.create_plan_version(self.plan)
        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v2.version_number, 2)

    def test_set_entitlement_validates_value_type(self):
        version = plan_service.create_plan_version(self.plan)
        # catalog.import is boolean; giving it is_unlimited must fail validation.
        with self.assertRaises(ValidationError):
            plan_service.set_plan_entitlement(version, "catalog.import", is_unlimited=True)


class SyncEntitlementDefinitionsTests(TestCase):
    def test_sync_is_idempotent(self):
        sync_entitlement_definitions()
        first = EntitlementDefinition.objects.count()
        sync_entitlement_definitions()
        self.assertEqual(EntitlementDefinition.objects.count(), first)
        self.assertTrue(EntitlementDefinition.objects.filter(key="catalog.products").exists())
