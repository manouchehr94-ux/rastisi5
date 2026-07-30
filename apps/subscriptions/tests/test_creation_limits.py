"""Checkpoint 5A commit 5 (ADR-69/§16/§27/§28): creation-limit enforcement in
the SERVICE LAYERS (not just UI) for Product / Variant / Staff / Warehouse /
Segment.

Covers: limit boundary (create allowed up to the limit, blocked at it),
bulk/generation total-increment checks with atomicity (no partial creation),
staff-seat semantics (role change consumes no seat, reactivation of a revoked
seat does), updates remaining allowed at the limit, existing over-limit data
staying readable after a downgrade, and restricted-state blocking growth.
"""

from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductVariant, Vendor, Warehouse
from apps.catalog.services import variant_service, warehouse_service
from apps.stores.models import Store, StoreMembership
from apps.stores.services import membership_service
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc
from apps.subscriptions.services.enforcement import (
    FeatureNotAvailable,
    SubscriptionRestricted,
    UsageLimitExceeded,
    enforce_can_create_product,
    enforce_can_create_segment,
)


def _limited_store(slug, *, entitlement_key, limit, feature_enabled=True):
    """Create a store on a fresh published plan version that caps ``entitlement_key``
    at ``limit`` and returns it with an active subscription."""
    ent.clear_entitlement_cache()
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"plan-{slug}", name=slug)
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
    )
    definition = EntitlementDefinition.objects.get(key=entitlement_key)
    PlanEntitlement.objects.create(
        plan_version=version, entitlement=definition,
        is_enabled=feature_enabled, integer_limit=limit,
    )
    sub = svc.create_subscription(store, version)
    svc.activate_subscription(sub)
    ent.clear_entitlement_cache()
    return store, version


class WarehouseLimitTests(TestCase):
    def setUp(self):
        self.store, _ = _limited_store("wh-limit", entitlement_key=ekeys.INVENTORY_WAREHOUSES, limit=2)

    def test_create_allowed_up_to_limit(self):
        warehouse_service.create_warehouse(self.store, code="w1", name="w1")
        ent.clear_entitlement_cache()
        warehouse_service.create_warehouse(self.store, code="w2", name="w2")
        self.assertEqual(Warehouse.objects.filter(store=self.store).count(), 2)

    def test_create_blocked_at_limit(self):
        warehouse_service.create_warehouse(self.store, code="w1", name="w1")
        ent.clear_entitlement_cache()
        warehouse_service.create_warehouse(self.store, code="w2", name="w2")
        ent.clear_entitlement_cache()
        with self.assertRaises(UsageLimitExceeded):
            warehouse_service.create_warehouse(self.store, code="w3", name="w3")
        self.assertEqual(Warehouse.objects.filter(store=self.store).count(), 2)

    def test_update_allowed_at_limit(self):
        warehouse_service.create_warehouse(self.store, code="w1", name="w1")
        ent.clear_entitlement_cache()
        w2 = warehouse_service.create_warehouse(self.store, code="w2", name="w2")
        ent.clear_entitlement_cache()
        # At the limit, editing an existing warehouse must still work.
        updated = warehouse_service.update_warehouse(w2, name="w2-renamed")
        self.assertEqual(updated.name, "w2-renamed")


class StaffSeatLimitTests(TestCase):
    def setUp(self):
        self.store, _ = _limited_store("staff-limit", entitlement_key=ekeys.STAFF_MEMBERS, limit=1)
        # The store already has its owner seat consumed by the fixture? No —
        # this store was created bare, so seat usage starts at 0.

    def test_seat_blocked_at_limit(self):
        membership_service.add_staff_member(
            self.store, phone="09120000001", role=StoreMembership.Role.ADMINISTRATOR, invited_by=None,
        )
        ent.clear_entitlement_cache()
        with self.assertRaises(UsageLimitExceeded):
            membership_service.add_staff_member(
                self.store, phone="09120000002", role=StoreMembership.Role.ADMINISTRATOR, invited_by=None,
            )
        # The second (blocked) call must not have created a user or membership.
        self.assertEqual(
            StoreMembership.objects.filter(store=self.store).count(), 1,
        )

    def test_role_change_consumes_no_seat(self):
        m = membership_service.add_staff_member(
            self.store, phone="09120000001", role=StoreMembership.Role.ADMINISTRATOR, invited_by=None,
        )
        ent.clear_entitlement_cache()
        # Changing an existing member's role at the seat limit must be allowed.
        membership_service.change_role(m, new_role=StoreMembership.Role.CATALOG_MANAGER)
        m.refresh_from_db()
        self.assertEqual(m.role, StoreMembership.Role.CATALOG_MANAGER)

    def test_reactivation_of_revoked_seat_is_gated(self):
        store, _ = _limited_store("staff-limit-2", entitlement_key=ekeys.STAFF_MEMBERS, limit=1)
        m1 = membership_service.add_staff_member(
            store, phone="09120000010", role=StoreMembership.Role.ADMINISTRATOR, invited_by=None,
        )
        membership_service.revoke_membership(m1)  # frees the seat
        # Fill the single seat with a different member.
        ent.clear_entitlement_cache()
        membership_service.add_staff_member(
            store, phone="09120000011", role=StoreMembership.Role.ADMINISTRATOR, invited_by=None,
        )
        ent.clear_entitlement_cache()
        # Reactivating the revoked member would consume a second seat → blocked.
        with self.assertRaises(UsageLimitExceeded):
            membership_service.reactivate_membership(m1)


class WarehouseAndProductRestrictedStateTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="restr-store", admin_subdomain="restr-store")
        plan = Plan.objects.create(code="restr-plan", name="Restr")
        self.version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        self.sub = svc.create_subscription(self.store, self.version)
        svc.activate_subscription(self.sub)

    def test_suspended_blocks_creation_even_with_headroom(self):
        # No numeric limit on this plan, but a suspended subscription must still
        # block growth (state gate, not limit gate).
        svc.suspend_subscription(self.sub)
        ent.clear_entitlement_cache()
        with self.assertRaises(SubscriptionRestricted):
            warehouse_service.create_warehouse(self.store, code="w1", name="w1")


class VariantManualLimitTests(TestCase):
    def setUp(self):
        self.store, _ = _limited_store("var-limit", entitlement_key=ekeys.CATALOG_VARIANTS, limit=2)
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-var")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-var")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="p",
            slug="p-var", sku="SKU-VAR", price=Decimal("1"), stock=0,
        )

    def test_single_create_blocked_at_limit(self):
        variant_service.create_variant(self.product, attribute="رنگ", value="قرمز")
        ent.clear_entitlement_cache()
        variant_service.create_variant(self.product, attribute="رنگ", value="آبی")
        ent.clear_entitlement_cache()
        with self.assertRaises(UsageLimitExceeded):
            variant_service.create_variant(self.product, attribute="رنگ", value="سبز")
        self.assertEqual(ProductVariant.objects.filter(store=self.store).count(), 2)

    def test_bulk_checks_total_increment_atomically(self):
        # Limit is 2; requesting 3 new values must reject the whole batch, not
        # truncate to 2 (§28: no silent truncation).
        with self.assertRaises(UsageLimitExceeded):
            variant_service.bulk_create_variants(
                self.product, attribute="سایز", raw_values="S,M,L",
            )
        self.assertEqual(ProductVariant.objects.filter(store=self.store).count(), 0)

    def test_bulk_within_limit_succeeds(self):
        created, skipped = variant_service.bulk_create_variants(
            self.product, attribute="سایز", raw_values="S,M",
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(ProductVariant.objects.filter(store=self.store).count(), 2)


class SegmentGateTests(TestCase):
    """The segment gate combines a feature flag and a numeric limit (§29)."""

    def test_feature_disabled_blocks(self):
        store, _ = _limited_store(
            "seg-off", entitlement_key=ekeys.CUSTOMERS_SEGMENTS, limit=5, feature_enabled=False,
        )
        with self.assertRaises(FeatureNotAvailable):
            enforce_can_create_segment(store)

    def test_limit_reached_blocks(self):
        from apps.customers.models import CustomerSegment

        store, _ = _limited_store(
            "seg-lim", entitlement_key=ekeys.CUSTOMERS_SEGMENTS, limit=1,
        )
        enforce_can_create_segment(store)  # usage 0, limit 1 → ok
        CustomerSegment.objects.create(store=store, name="s1")
        ent.clear_entitlement_cache()
        with self.assertRaises(UsageLimitExceeded):
            enforce_can_create_segment(store)


class ProductLimitServiceGateTests(TestCase):
    """The product-creation gate is the same enforcement primitive the dashboard
    view calls; exercised here directly at the service boundary."""

    def setUp(self):
        self.store, _ = _limited_store("prod-limit", entitlement_key=ekeys.CATALOG_PRODUCTS, limit=1)
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-prod")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-prod")

    def _make_product(self, n):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name=f"p{n}",
            slug=f"p-prod-{n}", sku=f"SKU-PROD-{n}", price=Decimal("1"), stock=0,
        )

    def test_gate_allows_then_blocks(self):
        enforce_can_create_product(self.store)  # usage 0, limit 1 → ok
        self._make_product(1)
        ent.clear_entitlement_cache()
        with self.assertRaises(UsageLimitExceeded):
            enforce_can_create_product(self.store)  # usage 1, limit 1 → blocked

    def test_over_limit_after_downgrade_still_readable(self):
        # Simulate pre-downgrade data: 3 products under a plan that now caps at 1.
        for n in range(3):
            self._make_product(n)
        ent.clear_entitlement_cache()
        # Reading/counting the existing over-limit data must work fine.
        self.assertEqual(Product.objects.filter(store=self.store).count(), 3)
        # Only new creation is blocked.
        with self.assertRaises(UsageLimitExceeded):
            enforce_can_create_product(self.store)
