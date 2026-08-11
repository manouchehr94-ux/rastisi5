"""Checkpoint 5A commit 7: Merchant Admin subscription/usage/plans/preview/
history views, permission gating (SUBSCRIPTION_VIEW / SUBSCRIPTION_CHANGE /
USAGE_VIEW), and that plan selection is restricted to publicly-selectable
published versions (a merchant cannot POST an arbitrary version id)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.stores.authorization import (
    ROLE_PERMISSIONS,
    SUBSCRIPTION_CHANGE,
    SUBSCRIPTION_VIEW,
    USAGE_VIEW,
)
from apps.stores.models import Store, StoreMembership
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs

User = get_user_model()

HOST = f"sub-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


class RolePermissionMappingTests(TestCase):
    def test_owner_can_change_but_administrator_cannot(self):
        self.assertIn(SUBSCRIPTION_CHANGE, ROLE_PERMISSIONS[StoreMembership.Role.OWNER])
        self.assertNotIn(SUBSCRIPTION_CHANGE, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])

    def test_administrator_can_view_subscription_and_usage(self):
        self.assertIn(SUBSCRIPTION_VIEW, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])
        self.assertIn(USAGE_VIEW, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])

    def test_content_editor_sees_none_of_the_three(self):
        perms = ROLE_PERMISSIONS[StoreMembership.Role.CONTENT_EDITOR]
        self.assertNotIn(SUBSCRIPTION_VIEW, perms)
        self.assertNotIn(SUBSCRIPTION_CHANGE, perms)
        self.assertNotIn(USAGE_VIEW, perms)

    def test_analyst_sees_usage_only(self):
        perms = ROLE_PERMISSIONS[StoreMembership.Role.ANALYST]
        self.assertIn(USAGE_VIEW, perms)
        self.assertNotIn(SUBSCRIPTION_CHANGE, perms)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SubscriptionViewTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")  # legacy sub → unlimited
        self.store.admin_subdomain = "sub-test"
        self.store.save(update_fields=["admin_subdomain"])

        # A publicly-selectable plan the merchant may switch to.
        self.target_plan = Plan.objects.create(code="growth-sv", name="Growth", is_publicly_selectable=True)
        self.target_version = PlanVersion.objects.create(
            plan=self.target_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        PlanEntitlement.objects.create(
            plan_version=self.target_version,
            entitlement=EntitlementDefinition.objects.get(key=ekeys.CATALOG_PRODUCTS),
            is_enabled=True, integer_limit=50,
        )

        self.owner = self._member("sv-owner", StoreMembership.Role.OWNER)
        self.client.login(username="sv-owner", password="pass12345")

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        return user

    def _login(self, username, role):
        self._member(username, role)
        self.client.logout()
        self.client.login(username=username, password="pass12345")

    def test_owner_can_view_overview(self):
        resp = self.client.get(reverse("dashboard:subscription-overview"))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_view_usage(self):
        resp = self.client.get(reverse("dashboard:usage-overview"))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_view_plans_and_history(self):
        self.assertEqual(self.client.get(reverse("dashboard:subscription-plans")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:subscription-history")).status_code, 200)

    def test_content_editor_forbidden_from_overview(self):
        self._login("sv-editor", StoreMembership.Role.CONTENT_EDITOR)
        resp = self.client.get(reverse("dashboard:subscription-overview"))
        self.assertEqual(resp.status_code, 403)

    def test_administrator_can_view_but_not_change(self):
        self._login("sv-admin", StoreMembership.Role.ADMINISTRATOR)
        self.assertEqual(self.client.get(reverse("dashboard:subscription-overview")).status_code, 200)
        # Plans page requires SUBSCRIPTION_CHANGE → forbidden for administrator.
        self.assertEqual(self.client.get(reverse("dashboard:subscription-plans")).status_code, 403)

    def test_preview_then_execute_changes_plan(self):
        preview_resp = self.client.post(
            reverse("dashboard:subscription-plan-preview"),
            {"version_id": self.target_version.pk},
        )
        self.assertEqual(preview_resp.status_code, 200)
        # Extract the token the preview embedded (from the service, deterministically).
        preview = pcs.preview_plan_change(self.store, self.target_version)
        exec_resp = self.client.post(
            reverse("dashboard:subscription-plan-execute"),
            {"version_id": self.target_version.pk, "preview_token": preview["token"]},
        )
        self.assertRedirects(exec_resp, reverse("dashboard:subscription-overview"))
        ent.clear_entitlement_cache()
        current = ent.get_current_subscription(self.store)
        self.assertEqual(current.plan_version_id, self.target_version.pk)

    def test_execute_rejects_non_selectable_version(self):
        hidden_plan = Plan.objects.create(code="hidden-sv", name="Hidden", is_publicly_selectable=False)
        hidden_version = PlanVersion.objects.create(
            plan=hidden_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        resp = self.client.post(
            reverse("dashboard:subscription-plan-execute"),
            {"version_id": hidden_version.pk, "preview_token": "whatever"},
        )
        self.assertEqual(resp.status_code, 404)
