"""Django Admin (``/admin/``) is restricted to active superusers only.

ADR-8 records unscoped Django-Admin access to Store-owned commerce data as a
known, deferred security boundary — not an accepted tenant-safe model. Since
``apps.dashboard``'s ``staff_required`` decorator and Django's own
``AdminSite`` both historically gated on the identical ``is_staff`` flag,
any merchant given dashboard access could also reach ``/admin/`` and see or
mutate every Store's catalog data with no isolation. ``apps.stores.admin_permissions``
closes this by restricting ``has_permission`` to active superusers, without
touching the merchant dashboard's own ``is_staff`` contract.

These tests use two real Stores (each with its own verified ``StoreDomain``,
matching the same real-Host convention already used by
``apps.catalog.tests.test_store_isolation`` /
``apps.dashboard.tests.test_catalog_store_isolation``) with distinct Product
rows, and assert that a non-superuser staff account (the kind used to grant
dashboard access) cannot reach either Store's data through Django Admin,
while the merchant dashboard remains reachable for that same account, and a
real superuser's Django Admin access is unaffected.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

HOST_A = "admgate-a.example.com"
HOST_B = "admgate-b.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class AdminSuperuserGateFixture(TestCase):
    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="admin-gate-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-admgate-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-admgate-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a,
            name="Product A", slug="product-admgate-a", sku="SKU-ADMGATE-A", price=Decimal("100000"),
        )

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-admgate-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-admgate-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b,
            name="Product B", slug="product-admgate-b", sku="SKU-ADMGATE-B", price=Decimal("200000"),
        )

        self.staff = User.objects.create_user(
            username="dashboard-only-staff", password="pass12345", is_staff=True, is_superuser=False,
        )
        self.superuser = User.objects.create_superuser(
            username="platform-superuser", email="super@example.com", password="pass12345",
        )
        StoreMembership.objects.create(
            store=self.store_a, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        StoreMembership.objects.create(
            store=self.store_a, user=self.superuser, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )


class NonSuperuserStaffDeniedAdminTests(AdminSuperuserGateFixture):
    """A dashboard staff account (is_staff=True, is_superuser=False) must be
    fully denied Django Admin, for both Stores' data, while retaining
    dashboard access."""

    def setUp(self):
        super().setUp()
        self.client.login(username="dashboard-only-staff", password="pass12345")

    def test_dashboard_still_accessible(self):
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)

    def test_admin_index_denied(self):
        response = self.client.get(reverse("admin:index"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_admin_login_page_does_not_grant_index_access(self):
        response = self.client.get(reverse("admin:login"), HTTP_HOST=HOST_A)
        # Django's own admin login view redirects an already-permitted user
        # straight to the index; a denied user must not be redirected there.
        self.assertNotEqual(response.status_code, 302)

    def test_product_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_product_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_product_a_change_page_denied(self):
        response = self.client.get(
            reverse("admin:catalog_product_change", args=[self.product_a.pk]), HTTP_HOST=HOST_A
        )
        self.assertNotEqual(response.status_code, 200)

    def test_product_b_change_page_denied(self):
        response = self.client.get(
            reverse("admin:catalog_product_change", args=[self.product_b.pk]), HTTP_HOST=HOST_A
        )
        self.assertNotEqual(response.status_code, 200)

    def test_category_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_category_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_brand_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_brand_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_vendor_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_vendor_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_productimage_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_productimage_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_specification_changelist_denied(self):
        response = self.client.get(reverse("admin:catalog_specification_changelist"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)

    def test_direct_post_cannot_mutate_product_a(self):
        original_name = self.product_a.name
        response = self.client.post(
            reverse("admin:catalog_product_change", args=[self.product_a.pk]),
            {"name": "Hijacked via admin POST", "sku": self.product_a.sku, "price": "1"},
            HTTP_HOST=HOST_A,
        )
        self.assertNotEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.name, original_name)

    def test_direct_post_cannot_delete_product_b(self):
        response = self.client.post(
            reverse("admin:catalog_product_delete", args=[self.product_b.pk]), {"post": "yes"}, HTTP_HOST=HOST_A,
        )
        self.assertTrue(Product.objects.filter(pk=self.product_b.pk).exists())
        self.assertNotEqual(response.status_code, 200)

    def test_no_database_changes_from_denied_access_attempts(self):
        before_product_count = Product.objects.count()
        before_category_count = Category.objects.count()
        self.client.get(reverse("admin:catalog_product_changelist"), HTTP_HOST=HOST_A)
        self.client.post(
            reverse("admin:catalog_product_delete", args=[self.product_a.pk]), {"post": "yes"}, HTTP_HOST=HOST_A,
        )
        self.assertEqual(Product.objects.count(), before_product_count)
        self.assertEqual(Category.objects.count(), before_category_count)


class SuperuserRetainsAdminAccessTests(AdminSuperuserGateFixture):
    def setUp(self):
        super().setUp()
        self.client.login(username="platform-superuser", password="pass12345")

    def test_admin_index_accessible(self):
        response = self.client.get(reverse("admin:index"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)

    def test_product_changelist_accessible(self):
        response = self.client.get(reverse("admin:catalog_product_changelist"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product A")
        self.assertContains(response, "Product B")

    def test_product_change_page_accessible(self):
        response = self.client.get(
            reverse("admin:catalog_product_change", args=[self.product_a.pk]), HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)

    def test_dashboard_also_still_accessible(self):
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)


class AnonymousAndInactiveAdminAccessTests(AdminSuperuserGateFixture):
    def test_anonymous_admin_index_redirects_to_login(self):
        response = self.client.get(reverse("admin:index"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_inactive_superuser_flagged_user_still_denied(self):
        """Manually setting is_superuser/is_staff on an inactive account must
        not grant admin access — is_active is part of the invariant (Django's
        own auth backend already refuses to attach an inactive user to
        request.user at all, so this also proves that path stays closed)."""
        inactive_super = User.objects.create_user(
            username="inactive-super", password="pass12345", is_staff=True, is_superuser=True, is_active=False,
        )
        self.client.force_login(inactive_super)
        response = self.client.get(reverse("admin:index"), HTTP_HOST=HOST_A)
        self.assertNotEqual(response.status_code, 200)
