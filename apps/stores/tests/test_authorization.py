"""Unit tests for ``apps.stores.authorization``.

Covers the role/permission registry and the membership-lookup helpers in
isolation, independent of HTTP/dashboard wiring (see
``apps.dashboard.tests.test_membership_authorization`` for the end-to-end
HTTP-level adversarial tests through ``staff_required``).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.authorization import (
    CATALOG,
    CONTENT,
    MEMBERSHIP,
    ORDERS,
    REPORTS,
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


class UserHasPermissionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_owner_has_every_permission(self):
        user = User.objects.create_user(username="owner1", password="pass12345")
        _membership(self.store, user, StoreMembership.Role.OWNER)
        for permission in (CATALOG, ORDERS, CONTENT, REPORTS, MEMBERSHIP):
            self.assertTrue(user_has_permission(user, self.store, permission))

    def test_analyst_only_has_reports(self):
        user = User.objects.create_user(username="analyst1", password="pass12345")
        _membership(self.store, user, StoreMembership.Role.ANALYST)
        self.assertTrue(user_has_permission(user, self.store, REPORTS))
        self.assertFalse(user_has_permission(user, self.store, CATALOG))
        self.assertFalse(user_has_permission(user, self.store, ORDERS))
        self.assertFalse(user_has_permission(user, self.store, MEMBERSHIP))

    def test_content_editor_only_has_content(self):
        user = User.objects.create_user(username="editor1", password="pass12345")
        _membership(self.store, user, StoreMembership.Role.CONTENT_EDITOR)
        self.assertTrue(user_has_permission(user, self.store, CONTENT))
        self.assertFalse(user_has_permission(user, self.store, ORDERS))

    def test_no_membership_has_no_permission(self):
        user = User.objects.create_user(username="nobody1", password="pass12345")
        self.assertFalse(user_has_permission(user, self.store, REPORTS))
