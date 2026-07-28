"""Adversarial tests for StoreMembership-based dashboard authorization.

Before Phase 1B, ``apps.dashboard.decorators.staff_required`` granted access
to *any* Store's ``/admin-panel/`` to any ``is_staff=True`` account, because
nothing checked *which* Store the user actually belonged to (see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §10.2/§11.1 — recorded
as the highest-priority tenant-authorization gap).

Phase 1C additionally requires every admin request to resolve through a
Store's real ``admin_subdomain`` host (or the approved local-dev/test
allowlist) — see ``apps.stores.resolution.resolve_store_for_admin_request``.
These tests therefore use two real Stores identified purely by their
``admin_subdomain`` hosts (``<subdomain>.rastisi.ir``), not a public
``StoreDomain`` — this file is about *membership* authorization, not host
enforcement (see ``test_admin_host_enforcement.py`` for that).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST_A = "memauth-a.rastisi.ir"
HOST_B = "memauth-b.rastisi.ir"


def _membership(store, user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE):
    kwargs = {"store": store, "user": user, "role": role, "status": status}
    if status == StoreMembership.MembershipStatus.ACTIVE:
        kwargs["accepted_at"] = timezone.now()
    if status == StoreMembership.MembershipStatus.REVOKED:
        kwargs["revoked_at"] = timezone.now()
    return StoreMembership.objects.create(**kwargs)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class MembershipAuthorizationTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_a.admin_subdomain = "memauth-a"
        self.store_a.save(update_fields=["admin_subdomain"])
        self.store_b = Store.objects.create(
            name="Store B", slug="memauth-store-b", status=Store.Status.ACTIVE, admin_subdomain="memauth-b",
        )
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

    def test_membership_in_store_a_denied_at_store_b_host(self):
        """is_staff=True + active membership in Store A must NOT unlock
        Store B's dashboard — this is the exact gap Phase 1B closed."""
        user = User.objects.create_user(username="memauth-a-only", password="pass12345", is_staff=True)
        _membership(self.store_a, user)
        self.client.login(username="memauth-a-only", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_B)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_membership_in_store_a_allowed_at_store_a_host(self):
        user = User.objects.create_user(username="memauth-a-ok", password="pass12345", is_staff=True)
        _membership(self.store_a, user)
        self.client.login(username="memauth-a-ok", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)

    def test_is_staff_without_any_membership_denied(self):
        user = User.objects.create_user(username="memauth-nomember", password="pass12345", is_staff=True)
        self.client.login(username="memauth-nomember", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_invited_membership_denied(self):
        user = User.objects.create_user(username="memauth-invited", password="pass12345", is_staff=True)
        _membership(self.store_a, user, status=StoreMembership.MembershipStatus.INVITED)
        self.client.login(username="memauth-invited", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_revoked_membership_denied(self):
        user = User.objects.create_user(username="memauth-revoked", password="pass12345", is_staff=True)
        _membership(self.store_a, user, status=StoreMembership.MembershipStatus.REVOKED)
        self.client.login(username="memauth-revoked", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_membership_without_is_staff_still_denied(self):
        """Membership alone must not bypass the existing is_staff bar —
        this only adds a requirement, it never removes the old one."""
        user = User.objects.create_user(username="memauth-nostaff", password="pass12345", is_staff=False)
        _membership(self.store_a, user)
        self.client.login(username="memauth-nostaff", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_member_of_both_stores_can_access_both(self):
        user = User.objects.create_user(username="memauth-both", password="pass12345", is_staff=True)
        _membership(self.store_a, user)
        _membership(self.store_b, user)
        self.client.login(username="memauth-both", password="pass12345")

        response_a = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        response_b = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_B)
        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)

    def test_superuser_without_membership_still_denied_dashboard(self):
        """Platform Superuser is a separate concern (``/admin/``, gated by
        ``apps.stores.admin_permissions``) — it must not implicitly unlock
        a Store's merchant dashboard too."""
        superuser = User.objects.create_superuser(
            username="memauth-super", email="memauth-super@example.com", password="pass12345",
        )
        self.client.login(username="memauth-super", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)
