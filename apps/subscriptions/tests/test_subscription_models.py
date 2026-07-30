"""Tests for Checkpoint 5A commit 2: StoreSubscription/SubscriptionEvent/
UsageRecord model constraints and the idempotent legacy provisioning."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
    StoreSubscription,
    SubscriptionEvent,
    UsageRecord,
)
from apps.subscriptions.services.legacy_service import LEGACY_PLAN_CODE, provision_legacy


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _run_legacy(now=None):
    return provision_legacy(
        Plan=Plan, PlanVersion=PlanVersion, EntitlementDefinition=EntitlementDefinition,
        PlanEntitlement=PlanEntitlement, StoreSubscription=StoreSubscription, Store=Store,
        now=now or timezone.now(),
    )


class SubscriptionConstraintTests(TestCase):
    def setUp(self):
        # A fresh store — the 0003 migration already gave the akhlaghi store a
        # current legacy subscription, which would otherwise collide with the
        # current-subscription uniqueness these tests deliberately exercise.
        self.store = Store.objects.create(
            name="فروشگاه قید", slug="constraint-store", admin_subdomain="constraint-store",
        )
        self.plan = Plan.objects.create(code="p", name="P")
        self.version = PlanVersion.objects.create(plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED)

    def test_one_current_subscription_per_store(self):
        StoreSubscription.objects.create(store=self.store, plan_version=self.version, is_current=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreSubscription.objects.create(store=self.store, plan_version=self.version, is_current=True)

    def test_terminal_subscription_does_not_block_new_current(self):
        StoreSubscription.objects.create(
            store=self.store, plan_version=self.version, status=StoreSubscription.Status.EXPIRED, is_current=False,
        )
        # A new current subscription must be allowed alongside the historical one.
        StoreSubscription.objects.create(store=self.store, plan_version=self.version, is_current=True)
        self.assertEqual(StoreSubscription.objects.filter(store=self.store).count(), 2)

    def test_usage_record_unique_per_store_metric_period(self):
        start = timezone.now()
        UsageRecord.objects.create(
            store=self.store, metric_key="catalog.import_rows_monthly",
            period_start=start, period_end=start + timezone.timedelta(days=30),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UsageRecord.objects.create(
                    store=self.store, metric_key="catalog.import_rows_monthly",
                    period_start=start, period_end=start + timezone.timedelta(days=30),
                )

    def test_subscription_event_idempotency_unique(self):
        sub = StoreSubscription.objects.create(store=self.store, plan_version=self.version, is_current=True)
        SubscriptionEvent.objects.create(
            subscription=sub, store=self.store, event_type=SubscriptionEvent.EventType.ACTIVATED,
            idempotency_key="k1",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SubscriptionEvent.objects.create(
                    subscription=sub, store=self.store, event_type=SubscriptionEvent.EventType.ACTIVATED,
                    idempotency_key="k1",
                )

    def test_empty_idempotency_key_not_unique(self):
        sub = StoreSubscription.objects.create(store=self.store, plan_version=self.version, is_current=True)
        SubscriptionEvent.objects.create(subscription=sub, store=self.store, event_type="created", idempotency_key="")
        SubscriptionEvent.objects.create(subscription=sub, store=self.store, event_type="created", idempotency_key="")
        self.assertEqual(SubscriptionEvent.objects.filter(subscription=sub).count(), 2)


class LegacyProvisioningTests(TestCase):
    def test_migration_already_provisioned_existing_store(self):
        # The 0003 data migration runs during test DB setup, so the akhlaghi
        # store must already have a current legacy subscription.
        store = _akhlaghi()
        sub = StoreSubscription.objects.get(store=store, is_current=True)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(sub.plan_version.plan.code, LEGACY_PLAN_CODE)
        self.assertEqual(sub.source, StoreSubscription.Source.LEGACY)

    def test_legacy_plan_is_hidden(self):
        plan = Plan.objects.get(code=LEGACY_PLAN_CODE)
        self.assertFalse(plan.is_publicly_selectable)

    def test_legacy_version_grants_unlimited_limits(self):
        version = PlanVersion.objects.get(plan__code=LEGACY_PLAN_CODE, version_number=1)
        self.assertEqual(version.status, PlanVersion.Status.PUBLISHED)
        products = version.plan_entitlements.get(entitlement__key="catalog.products")
        self.assertTrue(products.is_unlimited)
        self.assertIsNone(products.resolved_limit())
        import_ent = version.plan_entitlements.get(entitlement__key="catalog.import")
        self.assertTrue(import_ent.is_enabled)

    def test_provisioning_is_idempotent(self):
        before_subs = StoreSubscription.objects.count()
        before_plans = Plan.objects.filter(code=LEGACY_PLAN_CODE).count()
        _run_legacy()
        self.assertEqual(StoreSubscription.objects.count(), before_subs)
        self.assertEqual(Plan.objects.filter(code=LEGACY_PLAN_CODE).count(), before_plans)

    def test_new_store_gets_legacy_subscription_on_provision(self):
        new_store = Store.objects.create(name="فروشگاه تازه", slug="legacy-new-store", admin_subdomain="legacy-new")
        self.assertFalse(StoreSubscription.objects.filter(store=new_store).exists())
        counts = _run_legacy()
        self.assertGreaterEqual(counts["subscriptions"], 1)
        self.assertTrue(StoreSubscription.objects.filter(store=new_store, is_current=True, status="active").exists())

    def test_existing_capabilities_preserved(self):
        # Every entitlement definition must be present and enabled on the
        # legacy version — no existing capability silently dropped.
        version = PlanVersion.objects.get(plan__code=LEGACY_PLAN_CODE, version_number=1)
        from apps.subscriptions.entitlements import ENTITLEMENT_DEFINITIONS
        for key, _n, _t, _d in ENTITLEMENT_DEFINITIONS:
            ent = version.plan_entitlements.filter(entitlement__key=key).first()
            self.assertIsNotNone(ent, f"missing legacy entitlement {key}")
            self.assertTrue(ent.is_enabled, f"legacy entitlement {key} not enabled")
