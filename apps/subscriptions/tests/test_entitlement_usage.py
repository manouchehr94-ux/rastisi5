"""Tests for the Checkpoint 5A entitlement + usage services (ADR-64/68/69):
boolean/limit/unlimited resolution, no-subscription fail-open, access-state
policy, live count metrics, period counters, and the usage-limit gate."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor, Warehouse
from apps.stores.models import Store
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
    StoreSubscription,
    UsageRecord,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc
from apps.subscriptions.services import usage_service as usage
from apps.subscriptions.services.entitlement_service import (
    FeatureNotAvailable,
    SubscriptionRestricted,
    UsageLimitExceeded,
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class EntitlementResolutionTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="ent-store", admin_subdomain="ent-store")
        self.plan = Plan.objects.create(code="starter", name="Starter")
        self.version = PlanVersion.objects.create(plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        self.products_def = EntitlementDefinition.objects.get(key="catalog.products")
        self.import_def = EntitlementDefinition.objects.get(key="catalog.import")
        PlanEntitlement.objects.create(plan_version=self.version, entitlement=self.products_def, integer_limit=100)
        PlanEntitlement.objects.create(plan_version=self.version, entitlement=self.import_def, is_enabled=False)
        svc.create_subscription(self.store, self.version)
        sub = ent.get_current_subscription(self.store)
        svc.activate_subscription(sub)

    def test_boolean_disabled(self):
        self.assertFalse(ent.has_entitlement(self.store, "catalog.import"))
        with self.assertRaises(FeatureNotAvailable):
            ent.check_entitlement(self.store, "catalog.import")

    def test_integer_limit_resolved(self):
        self.assertEqual(ent.get_entitlement_limit(self.store, "catalog.products"), 100)

    def test_disabled_feature_limit_is_zero(self):
        self.assertEqual(ent.get_entitlement_limit(self.store, "catalog.import"), 0)

    def test_undefined_key_fails_open(self):
        # A key not present on the plan version → unlimited (fail-open).
        self.assertIsNone(ent.get_entitlement_limit(self.store, "inventory.warehouses"))
        self.assertTrue(ent.has_entitlement(self.store, "inventory.warehouses"))


class UnlimitedTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = _akhlaghi()  # legacy subscription from migration → all unlimited

    def test_legacy_products_unlimited(self):
        self.assertIsNone(ent.get_entitlement_limit(self.store, "catalog.products"))

    def test_legacy_import_enabled(self):
        self.assertTrue(ent.has_entitlement(self.store, "catalog.import"))


class NoSubscriptionTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="nosub-store", admin_subdomain="nosub-store")

    def test_fail_open_when_no_subscription(self):
        self.assertTrue(ent.has_entitlement(self.store, "catalog.import"))
        self.assertIsNone(ent.get_entitlement_limit(self.store, "catalog.products"))

    def test_access_state_none(self):
        state = ent.get_subscription_access_state(self.store)
        self.assertEqual(state.state, ent.AccessState.NONE)
        self.assertTrue(state.allows_growth)


class AccessStateTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="access-store", admin_subdomain="access-store")
        self.plan = Plan.objects.create(code="pro", name="Pro")
        self.version = PlanVersion.objects.create(plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        self.sub = svc.create_subscription(self.store, self.version)
        self.sub = svc.activate_subscription(self.sub)

    def test_active_full(self):
        state = ent.get_subscription_access_state(self.store)
        self.assertEqual(state.state, ent.AccessState.FULL)
        self.assertTrue(state.allows_growth)

    def test_suspended_restricted_blocks_growth(self):
        svc.suspend_subscription(self.sub)
        ent.clear_entitlement_cache()
        state = ent.get_subscription_access_state(self.store)
        self.assertEqual(state.state, ent.AccessState.RESTRICTED)
        self.assertFalse(state.allows_growth)
        with self.assertRaises(SubscriptionRestricted):
            ent.require_growth_allowed(self.store)

    def test_expired_blocks_growth(self):
        svc.expire_subscription(self.sub)
        state = ent.get_subscription_access_state(self.store)
        self.assertEqual(state.state, ent.AccessState.EXPIRED)
        self.assertFalse(state.allows_growth)


class CountUsageTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="usage-store", admin_subdomain="usage-store")
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-usage")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-usage")

    def test_product_count_live(self):
        self.assertEqual(usage.get_count_usage(self.store, "catalog.products"), 0)
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="p",
            slug="p-usage", sku="SKU-U1", price=Decimal("1"), stock=0,
        )
        self.assertEqual(usage.get_count_usage(self.store, "catalog.products"), 1)

    def test_warehouse_count_active_only(self):
        Warehouse.objects.create(store=self.store, name="w1", code="w1-usage", is_active=True)
        Warehouse.objects.create(store=self.store, name="w2", code="w2-usage", is_active=False)
        self.assertEqual(usage.get_count_usage(self.store, "inventory.warehouses"), 1)


class PeriodUsageTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="ف", slug="period-store", admin_subdomain="period-store")

    def test_consume_and_read(self):
        usage.consume_period_usage(self.store, "catalog.import_rows_monthly", 50)
        self.assertEqual(usage.get_period_usage(self.store, "catalog.import_rows_monthly"), 50)
        usage.consume_period_usage(self.store, "catalog.import_rows_monthly", 30)
        self.assertEqual(usage.get_period_usage(self.store, "catalog.import_rows_monthly"), 80)

    def test_negative_rejected(self):
        with self.assertRaises(usage.UsageError):
            usage.consume_period_usage(self.store, "catalog.import_rows_monthly", -1)

    def test_period_isolation(self):
        now = timezone.now()
        last_month = (now.replace(day=1) - timezone.timedelta(days=1))
        usage.consume_period_usage(self.store, "catalog.exports_monthly", 5, now=last_month)
        # Current period must be independent of last month's counter.
        self.assertEqual(usage.get_period_usage(self.store, "catalog.exports_monthly", now=now), 0)


class UsageLimitGateTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="gate-store", admin_subdomain="gate-store")
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-gate")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-gate")
        self.plan = Plan.objects.create(code="s", name="S")
        self.version = PlanVersion.objects.create(plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        pdef = EntitlementDefinition.objects.get(key="catalog.products")
        PlanEntitlement.objects.create(plan_version=self.version, entitlement=pdef, integer_limit=2)
        sub = svc.create_subscription(self.store, self.version)
        svc.activate_subscription(sub)

    def _make_product(self, n):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name=f"p{n}",
            slug=f"p-gate-{n}", sku=f"SKU-GATE-{n}", price=Decimal("1"), stock=0,
        )

    def test_allowed_below_limit(self):
        self._make_product(1)  # usage 1, limit 2
        ent.clear_entitlement_cache()
        usage.check_usage_limit(self.store, "catalog.products")  # 1+1=2 <= 2 → ok

    def test_blocked_at_limit(self):
        self._make_product(1)
        self._make_product(2)  # usage 2, limit 2
        with self.assertRaises(UsageLimitExceeded):
            usage.check_usage_limit(self.store, "catalog.products")  # 2+1=3 > 2

    def test_over_limit_from_downgrade_still_readable(self):
        # 3 products but limit 2 (as if downgraded) — reading/counting works,
        # only new creation is blocked.
        for n in range(3):
            self._make_product(n)
        self.assertEqual(usage.get_count_usage(self.store, "catalog.products"), 3)
        with self.assertRaises(UsageLimitExceeded):
            usage.check_usage_limit(self.store, "catalog.products")
