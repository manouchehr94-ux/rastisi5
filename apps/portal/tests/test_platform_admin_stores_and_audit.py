"""Section 13 — Platform Admin's Store search/detail and audit-log views,
the concrete gap platform_admin_views.py's own module docstring had
flagged as not built yet ("Store search/detail")."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.portal.services.platform_config_service import record_platform_audit_event
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminStoreAndAuditTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="pa-super@example.com", email="pa-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary_owner = User.objects.create_user(
            username="pa-ordinary@example.com", email="pa-ordinary@example.com", password="a-very-strong-pass-1",
        )
        self.store = Store.objects.create(
            name="فروشگاه ادمین پلتفرم", slug="pa-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="pa-store",
        )
        StoreDomain.objects.create(
            store=self.store, hostname=f"{self.store.platform_code}.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreMembership.objects.create(
            store=self.store, user=self.ordinary_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.superuser)


class StoresListViewTests(PlatformAdminStoreAndAuditTestCase):
    def test_lists_stores(self):
        response = self.client.get("/stores/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فروشگاه ادمین پلتفرم")

    def test_search_by_slug_filters(self):
        Store.objects.create(
            name="فروشگاهِ نامرتبط", slug="unrelated-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="unrelated-store",
        )
        response = self.client.get("/stores/", {"q": "pa-store"}, HTTP_HOST=_HOST)
        self.assertContains(response, "pa-store")
        self.assertNotContains(response, "unrelated-store")

    def test_search_by_platform_code_filters(self):
        response = self.client.get("/stores/", {"q": self.store.platform_code}, HTTP_HOST=_HOST)
        self.assertContains(response, "فروشگاه ادمین پلتفرم")

    def test_non_superuser_is_redirected(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get("/stores/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)


class StoreDetailViewTests(PlatformAdminStoreAndAuditTestCase):
    def _url(self):
        return f"/stores/{self.store.public_id}/"

    def test_shows_store_domains_and_membership(self):
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{self.store.platform_code}.rastisi.ir")
        self.assertContains(response, "pa-ordinary@example.com")

    def test_shows_store_scoped_audit_entries(self):
        record_audit_event(
            store=self.store, actor=self.ordinary_owner, action_code="store.handle_claimed",
            object_type="StoreDomain", object_id=1, object_label="novin.rastisi.ir",
        )
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertContains(response, "store.handle_claimed")

    def test_unknown_store_404s(self):
        import uuid

        response = self.client.get(f"/stores/{uuid.uuid4()}/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_non_superuser_is_redirected(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)


class AuditLogViewTests(PlatformAdminStoreAndAuditTestCase):
    def test_lists_platform_audit_entries(self):
        record_platform_audit_event(actor=self.superuser, action_code="platform_configuration.updated")
        response = self.client.get("/audit-log/", HTTP_HOST=_HOST)
        self.assertContains(response, "platform_configuration.updated")

    def test_filters_by_action_code(self):
        record_platform_audit_event(actor=self.superuser, action_code="platform_configuration.updated")
        record_platform_audit_event(actor=self.superuser, action_code="something_else")
        response = self.client.get("/audit-log/", {"action_code": "something_else"}, HTTP_HOST=_HOST)
        self.assertContains(response, "something_else")
        self.assertNotContains(response, "platform_configuration.updated")

    def test_non_superuser_is_redirected(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get("/audit-log/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
