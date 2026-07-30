"""Checkpoint 5A commit 8 (ADR-63): platform Django Admin for the subscription
runtime models is superuser-only and enforces immutability server-side —
SubscriptionEvent/UsageRecord can never be changed, and nothing here can be
added/deleted from the admin (subscriptions move only through the state
machine, counters only through usage_service)."""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.subscriptions.admin import (
    StoreSubscriptionAdmin,
    SubscriptionEventAdmin,
    UsageRecordAdmin,
)
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent, UsageRecord

User = get_user_model()


class SubscriptionAdminPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin8-super", email="s@example.com", password="p",
        )
        cls.staff = User.objects.create_user(
            username="admin8-staff", password="p", is_staff=True, is_superuser=False,
        )

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.sub_admin = StoreSubscriptionAdmin(StoreSubscription, self.site)
        self.event_admin = SubscriptionEventAdmin(SubscriptionEvent, self.site)
        self.usage_admin = UsageRecordAdmin(UsageRecord, self.site)

    def _req(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_non_superuser_has_no_module_access(self):
        request = self._req(self.staff)
        for admin in (self.sub_admin, self.event_admin, self.usage_admin):
            self.assertFalse(admin.has_module_permission(request))
            self.assertFalse(admin.has_view_permission(request))

    def test_superuser_may_view(self):
        request = self._req(self.superuser)
        for admin in (self.sub_admin, self.event_admin, self.usage_admin):
            self.assertTrue(admin.has_module_permission(request))
            self.assertTrue(admin.has_view_permission(request))

    def test_nothing_can_be_added_or_deleted(self):
        request = self._req(self.superuser)
        for admin in (self.sub_admin, self.event_admin, self.usage_admin):
            self.assertFalse(admin.has_add_permission(request))
            self.assertFalse(admin.has_delete_permission(request))

    def test_event_and_usage_are_not_changeable(self):
        request = self._req(self.superuser)
        # Immutable history + system-maintained counters: no change, even for superuser.
        self.assertFalse(self.event_admin.has_change_permission(request))
        self.assertFalse(self.usage_admin.has_change_permission(request))

    def test_subscription_fields_are_all_readonly(self):
        request = self._req(self.superuser)
        readonly = self.sub_admin.get_readonly_fields(request)
        # Status must be readonly so it can only move through the state machine.
        self.assertIn("status", readonly)
        self.assertIn("is_current", readonly)
