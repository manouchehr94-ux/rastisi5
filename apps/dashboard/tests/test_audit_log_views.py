from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"audit-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class AuditLogViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09127700001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127700001", password="pass12345")
        record_audit_event(store=self.store, actor=self.owner, action_code="staff.added", object_label="09121234567")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09127700{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class AuditLogListViewTests(AuditLogViewsTestCase):
    def test_renders_events(self):
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staff.added")

    def test_other_store_events_not_visible(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="audit-other-view", status=Store.Status.ACTIVE)
        record_audit_event(store=other_store, action_code="other.action", object_label="نباید دیده شود")
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertNotContains(response, "other.action")

    def test_analyst_can_view(self):
        self._login_as(StoreMembership.Role.ANALYST, "101")
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertEqual(response.status_code, 200)

    def test_catalog_manager_cannot_view(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "102")
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertEqual(response.status_code, 302)

    def test_search_filters(self):
        response = self.client.get(reverse("dashboard:audit-log-table"), {"q": "staff"})
        self.assertContains(response, "staff.added")
        response = self.client.get(reverse("dashboard:audit-log-table"), {"q": "no-such-thing"})
        self.assertNotContains(response, "staff.added")
