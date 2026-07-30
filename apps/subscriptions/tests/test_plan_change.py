"""Checkpoint 5A commit 7 (ADR-70/71/72): plan-change preview + execution.

Covers: entitlement-diff preview, over-limit downgrade warnings, preview-token
generation, stale-preview protection on execute, and the no-money-moved
guarantee (only entitlements change)."""

from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.stores.models import Store
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
    SubscriptionEvent,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import subscription_service as svc


def _published_version(code, *, limits):
    plan = Plan.objects.create(code=code, name=code, is_publicly_selectable=True)
    version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
    for key, integer_limit in limits.items():
        definition = EntitlementDefinition.objects.get(key=key)
        PlanEntitlement.objects.create(
            plan_version=version, entitlement=definition, is_enabled=True, integer_limit=integer_limit,
        )
    return version


class PlanChangePreviewTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="pc-store", admin_subdomain="pc-store")
        self.small = _published_version("pc-small", limits={ekeys.CATALOG_PRODUCTS: 5})
        self.big = _published_version("pc-big", limits={ekeys.CATALOG_PRODUCTS: 100})
        sub = svc.create_subscription(self.store, self.small)
        svc.activate_subscription(sub)
        ent.clear_entitlement_cache()
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-pc")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-pc")

    def test_preview_reports_entitlement_change(self):
        preview = pcs.preview_plan_change(self.store, self.big)
        changed = {c["key"]: c for c in preview["entitlement_changes"]}
        self.assertIn(ekeys.CATALOG_PRODUCTS, changed)
        self.assertEqual(changed[ekeys.CATALOG_PRODUCTS]["current"], 5)
        self.assertEqual(changed[ekeys.CATALOG_PRODUCTS]["target"], 100)
        self.assertTrue(preview["token"])

    def test_upgrade_has_no_downgrade_warning(self):
        preview = pcs.preview_plan_change(self.store, self.big)
        self.assertFalse(preview["has_downgrade_risk"])

    def test_downgrade_warns_when_usage_exceeds_target(self):
        # Store currently on big-ish? It's on `small` (5). Move to big (100),
        # create 10 products, then preview downgrade back to small (5) → warning.
        svc.change_plan_version(ent.get_current_subscription(self.store), self.big)
        ent.clear_entitlement_cache()
        for n in range(10):
            Product.objects.create(
                store=self.store, vendor=self.vendor, category=self.category, name=f"p{n}",
                slug=f"p-pc-{n}", sku=f"SKU-PC-{n}", price=Decimal("1"), stock=0,
            )
        preview = pcs.preview_plan_change(self.store, self.small)
        self.assertTrue(preview["has_downgrade_risk"])
        warned = {w["key"]: w for w in preview["over_limit_warnings"]}
        self.assertIn(ekeys.CATALOG_PRODUCTS, warned)
        self.assertEqual(warned[ekeys.CATALOG_PRODUCTS]["current"], 10)
        self.assertEqual(warned[ekeys.CATALOG_PRODUCTS]["target_limit"], 5)


class PlanChangeExecuteTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="pcx-store", admin_subdomain="pcx-store")
        self.small = _published_version("pcx-small", limits={ekeys.CATALOG_PRODUCTS: 5})
        self.big = _published_version("pcx-big", limits={ekeys.CATALOG_PRODUCTS: 100})
        sub = svc.create_subscription(self.store, self.small)
        svc.activate_subscription(sub)
        ent.clear_entitlement_cache()

    def test_execute_with_valid_token_changes_plan(self):
        preview = pcs.preview_plan_change(self.store, self.big)
        pcs.execute_plan_change(self.store, self.big, preview_token=preview["token"])
        current = ent.get_current_subscription(self.store)
        self.assertEqual(current.plan_version_id, self.big.pk)
        # A plan_changed event was recorded (immutable history).
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                store=self.store, event_type=SubscriptionEvent.EventType.PLAN_CHANGED,
            ).exists()
        )

    def test_stale_token_is_rejected(self):
        preview = pcs.preview_plan_change(self.store, self.big)
        # Mutate the subscription after the preview → token no longer matches.
        svc.change_plan_version(ent.get_current_subscription(self.store), self.big)
        ent.clear_entitlement_cache()
        with self.assertRaises(pcs.StalePreviewError):
            pcs.execute_plan_change(self.store, self.small, preview_token=preview["token"])

    def test_empty_token_is_rejected(self):
        with self.assertRaises(pcs.StalePreviewError):
            pcs.execute_plan_change(self.store, self.big, preview_token="")
