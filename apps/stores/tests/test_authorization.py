"""Unit tests for ``apps.stores.authorization``.

Covers the role/permission registry and the membership-lookup helpers in
isolation, independent of HTTP/dashboard wiring (see
``apps.dashboard.tests.test_membership_authorization`` and
``apps.dashboard.tests.test_permission_enforcement`` for the end-to-end
HTTP-level tests through ``staff_required``/``permission_required``).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.authorization import (
    ATTRIBUTE_MANAGE,
    CATEGORY_MANAGE,
    CONTENT_MANAGE,
    CUSTOMER_EDIT,
    CUSTOMER_VIEW,
    DASHBOARD_VIEW,
    DISCOUNT_MANAGE,
    DOMAIN_MANAGE,
    INVENTORY_MANAGE,
    ORDER_STATUS_CHANGE,
    ORDER_VIEW,
    PAYMENT_SETTINGS_MANAGE,
    PRODUCT_CREATE,
    PRODUCT_DELETE,
    PRODUCT_EDIT,
    PRODUCT_VIEW,
    REPORTS_VIEW,
    SETTINGS_MANAGE,
    SMS_SETTINGS_MANAGE,
    STAFF_MANAGE,
    SUBSCRIPTION_MANAGE,
    VARIANT_MANAGE,
    ALL_PERMISSIONS,
    get_active_membership,
    user_can_access_dashboard,
    user_has_permission,
)
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _membership(store, user, role, status=StoreMembership.MembershipStatus.ACTIVE, **extra):
    kwargs = {"store": store, "user": user, "role": role, "status": status}
    if status == StoreMembership.MembershipStatus.ACTIVE:
        kwargs["accepted_at"] = extra.get("accepted_at", timezone.now())
    if status == StoreMembership.MembershipStatus.REVOKED:
        kwargs["revoked_at"] = extra.get("revoked_at", timezone.now())
    return StoreMembership.objects.create(**kwargs)


class GetActiveMembershipTests(TestCase):
    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="auth-store-b", status=Store.Status.ACTIVE)
        self.user = User.objects.create_user(username="auth-user", password="pass12345")

    def test_none_store_returns_none(self):
        self.assertIsNone(get_active_membership(self.user, None))

    def test_none_user_returns_none(self):
        self.assertIsNone(get_active_membership(None, self.store_a))

    def test_unauthenticated_user_returns_none(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(get_active_membership(AnonymousUser(), self.store_a))

    def test_no_membership_row_returns_none(self):
        self.assertIsNone(get_active_membership(self.user, self.store_a))

    def test_active_membership_in_other_store_not_returned(self):
        _membership(self.store_b, self.user, StoreMembership.Role.OWNER)
        self.assertIsNone(get_active_membership(self.user, self.store_a))

    def test_active_membership_returned(self):
        membership = _membership(self.store_a, self.user, StoreMembership.Role.OWNER)
        self.assertEqual(get_active_membership(self.user, self.store_a), membership)

    def test_invited_membership_not_returned(self):
        _membership(
            self.store_a, self.user, StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.INVITED,
        )
        self.assertIsNone(get_active_membership(self.user, self.store_a))

    def test_revoked_membership_not_returned(self):
        _membership(
            self.store_a, self.user, StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.REVOKED,
        )
        self.assertIsNone(get_active_membership(self.user, self.store_a))


class UserCanAccessDashboardTests(TestCase):
    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="auth-store-b2", status=Store.Status.ACTIVE)
        self.user = User.objects.create_user(username="auth-user2", password="pass12345", is_staff=True)

    def test_is_staff_alone_does_not_grant_access(self):
        self.assertFalse(user_can_access_dashboard(self.user, self.store_a))

    def test_any_active_role_grants_baseline_access(self):
        _membership(self.store_a, self.user, StoreMembership.Role.ANALYST)
        self.assertTrue(user_can_access_dashboard(self.user, self.store_a))

    def test_membership_in_store_a_does_not_grant_store_b(self):
        _membership(self.store_a, self.user, StoreMembership.Role.OWNER)
        self.assertFalse(user_can_access_dashboard(self.user, self.store_b))


class OwnerPermissionTests(TestCase):
    """Owner must retain complete Store access — every permission key."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="owner1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.OWNER)

    def test_owner_has_every_permission(self):
        for permission in ALL_PERMISSIONS:
            self.assertTrue(
                user_has_permission(self.user, self.store, permission),
                msg=f"Owner should have {permission}",
            )


class AdministratorPermissionTests(TestCase):
    """Administrator: everything operational, but not ownership-tier actions."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="administrator1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.ADMINISTRATOR)

    def test_allowed_operational_actions(self):
        for permission in (
            PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
            CATEGORY_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE,
            ORDER_VIEW, ORDER_STATUS_CHANGE, CUSTOMER_VIEW,
            REPORTS_VIEW, SETTINGS_MANAGE, PAYMENT_SETTINGS_MANAGE,
            SMS_SETTINGS_MANAGE, CONTENT_MANAGE,
        ):
            self.assertTrue(user_has_permission(self.user, self.store, permission))

    def test_forbidden_ownership_tier_actions(self):
        for permission in (STAFF_MANAGE, DOMAIN_MANAGE, SUBSCRIPTION_MANAGE):
            self.assertFalse(user_has_permission(self.user, self.store, permission))


class CatalogManagerPermissionTests(TestCase):
    """Product Manager (``Role.CATALOG_MANAGER``): catalog-only."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="catalogmgr1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.CATALOG_MANAGER)

    def test_allowed_catalog_actions(self):
        for permission in (
            PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
            CATEGORY_MANAGE, ATTRIBUTE_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE,
            REPORTS_VIEW, DASHBOARD_VIEW,
        ):
            self.assertTrue(user_has_permission(self.user, self.store, permission))

    def test_forbidden_non_catalog_actions(self):
        for permission in (
            ORDER_STATUS_CHANGE, CUSTOMER_EDIT, SETTINGS_MANAGE,
            STAFF_MANAGE, CONTENT_MANAGE,
        ):
            self.assertFalse(user_has_permission(self.user, self.store, permission))


class OrderManagerPermissionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="ordermgr1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.ORDER_MANAGER)

    def test_allowed_order_and_customer_actions(self):
        for permission in (ORDER_VIEW, ORDER_STATUS_CHANGE, CUSTOMER_VIEW, CUSTOMER_EDIT, REPORTS_VIEW):
            self.assertTrue(user_has_permission(self.user, self.store, permission))

    def test_forbidden_catalog_and_settings_actions(self):
        for permission in (PRODUCT_EDIT, PRODUCT_DELETE, SETTINGS_MANAGE, CONTENT_MANAGE, STAFF_MANAGE):
            self.assertFalse(user_has_permission(self.user, self.store, permission))


class ContentEditorPermissionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="contentmgr1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.CONTENT_EDITOR)

    def test_allowed_content_actions(self):
        self.assertTrue(user_has_permission(self.user, self.store, CONTENT_MANAGE))

    def test_forbidden_non_content_actions(self):
        for permission in (ORDER_VIEW, PRODUCT_EDIT, SETTINGS_MANAGE, DISCOUNT_MANAGE):
            self.assertFalse(user_has_permission(self.user, self.store, permission))


class AnalystPermissionTests(TestCase):
    """Analyst / Read-Only: view-only across product/order/customer/reports,
    never a mutation permission."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="analyst1", password="pass12345")
        _membership(self.store, self.user, StoreMembership.Role.ANALYST)

    def test_allowed_read_only_actions(self):
        for permission in (DASHBOARD_VIEW, REPORTS_VIEW, PRODUCT_VIEW, ORDER_VIEW, CUSTOMER_VIEW):
            self.assertTrue(user_has_permission(self.user, self.store, permission))

    def test_forbidden_mutation_actions(self):
        for permission in (
            PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE, CATEGORY_MANAGE,
            ORDER_STATUS_CHANGE, CUSTOMER_EDIT, SETTINGS_MANAGE,
            CONTENT_MANAGE, STAFF_MANAGE,
        ):
            self.assertFalse(user_has_permission(self.user, self.store, permission))


class NoMembershipPermissionTests(TestCase):
    def test_no_membership_has_no_permission_at_all(self):
        store = _akhlaghi()
        user = User.objects.create_user(username="nobody1", password="pass12345")
        for permission in ALL_PERMISSIONS:
            self.assertFalse(user_has_permission(user, store, permission))
