"""Adversarial tests for StoreMembership-based dashboard authorization.

Before this PR, ``apps.dashboard.decorators.staff_required`` granted access
to *any* Store's ``/admin-portal/`` to any ``is_staff=True`` account, because
nothing checked *which* Store the user actually belonged to (see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §10.2/§11.1 — recorded
as the highest-priority tenant-authorization gap). These tests use two real
Stores, each with its own verified ``StoreDomain`` and distinct Host header,
mirroring the established pattern in
``apps.dashboard.tests.test_catalog_store_isolation``.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

HOST_A = "memauth-a.example.com"
HOST_B = "memauth-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


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
        self.store_b = Store.objects.create(name="Store B", slug="memauth-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

    def test_membership_in_store_a_denied_at_store_b_host(self):
        """is_staff=True + active membership in Store A must NOT unlock
        Store B's dashboard — this is the exact gap this PR closes."""
        user = User.objects.create_user(username="memauth-a-only", password="pass12345", is_staff=True)
        _membership(self.store_a, user)
        self.client.login(username="memauth-a-only", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_B)
        self.assertRedirects(response, reverse("catalog:home"))

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
        self.assertRedirects(response, reverse("catalog:home"))

    def test_invited_membership_denied(self):
        user = User.objects.create_user(username="memauth-invited", password="pass12345", is_staff=True)
        _membership(self.store_a, user, status=StoreMembership.MembershipStatus.INVITED)
        self.client.login(username="memauth-invited", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"))

    def test_revoked_membership_denied(self):
        user = User.objects.create_user(username="memauth-revoked", password="pass12345", is_staff=True)
        _membership(self.store_a, user, status=StoreMembership.MembershipStatus.REVOKED)
        self.client.login(username="memauth-revoked", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"))

    def test_membership_without_is_staff_still_denied(self):
        """Membership alone must not bypass the existing is_staff bar —
        this PR adds a requirement, it does not remove the old one."""
        user = User.objects.create_user(username="memauth-nostaff", password="pass12345", is_staff=False)
        _membership(self.store_a, user)
        self.client.login(username="memauth-nostaff", password="pass12345")

        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertRedirects(response, reverse("catalog:home"))

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
        self.assertRedirects(response, reverse("catalog:home"))
