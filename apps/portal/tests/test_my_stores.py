from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services import owner_auth_service
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class MyStoresTests(TestCase):
    def setUp(self):
        self.owner = owner_auth_service.register_owner(
            full_name="Store Owner", email="owner@example.com", password="a-very-strong-pass-1",
        )
        self.other_owner = owner_auth_service.register_owner(
            full_name="Other Owner", email="other@example.com", password="a-very-strong-pass-1",
        )

    def test_app_home_requires_login(self):
        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_app_home_shows_empty_state_with_no_stores(self):
        self.client.force_login(self.owner)
        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هنوز هیچ فروشگاهی نساخته‌اید")

    def test_app_home_lists_only_own_active_memberships(self):
        mine = Store.objects.create(
            name="Mine", slug="mine-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        StoreMembership.objects.create(
            store=mine, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        theirs = Store.objects.create(
            name="Theirs", slug="theirs-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        StoreMembership.objects.create(
            store=theirs, user=self.other_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

        self.client.force_login(self.owner)
        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")

    def test_app_home_excludes_revoked_memberships(self):
        store = Store.objects.create(
            name="Revoked", slug="revoked-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        StoreMembership.objects.create(
            store=store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.REVOKED,
            accepted_at=timezone.now(), revoked_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "Revoked")
