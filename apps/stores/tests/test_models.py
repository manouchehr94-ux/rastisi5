import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

User = get_user_model()


class StoreModelTests(TestCase):
    def test_creation(self):
        store = Store.objects.create(name="Test Store", slug="test-store")
        self.assertIsNotNone(store.pk)

    def test_string_representation(self):
        store = Store.objects.create(name="Test Store", slug="test-store")
        self.assertEqual(str(store), "Test Store")

    def test_default_status_is_provisioning(self):
        store = Store.objects.create(name="Test Store", slug="test-store")
        self.assertEqual(store.status, Store.Status.PROVISIONING)

    def test_status_choices_are_the_four_defined_values(self):
        values = {choice for choice, _ in Store.Status.choices}
        self.assertEqual(
            values, {"provisioning", "active", "suspended", "closed"}
        )

    def test_slug_uniqueness_is_enforced(self):
        Store.objects.create(name="Test Store", slug="test-store")
        with self.assertRaises(ValidationError):
            duplicate = Store(name="Test Store Two", slug="test-store")
            duplicate.full_clean()

    def test_public_id_is_unique_and_auto_generated(self):
        a = Store.objects.create(name="Store A", slug="store-a")
        b = Store.objects.create(name="Store B", slug="store-b")
        self.assertIsInstance(a.public_id, uuid.UUID)
        self.assertNotEqual(a.public_id, b.public_id)

    def test_unicode_slug_is_supported(self):
        store = Store.objects.create(name="اخلاقی", slug="اخلاقی")
        self.assertEqual(store.slug, "اخلاقی")

    def test_store_has_no_owner_field(self):
        field_names = {f.name for f in Store._meta.get_fields()}
        self.assertNotIn("owner", field_names)


class StoreMembershipTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.create(name="Store A", slug="store-a")
        self.store_b = Store.objects.create(name="Store B", slug="store-b")
        self.user_1 = User.objects.create_user(username="user1", password="pass12345")
        self.user_2 = User.objects.create_user(username="user2", password="pass12345")

    def test_membership_creation(self):
        membership = StoreMembership.objects.create(
            store=self.store_a,
            user=self.user_1,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        self.assertIsNotNone(membership.pk)

    def test_unique_store_user_pair(self):
        from django.db import IntegrityError, transaction

        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreMembership.objects.create(
                    store=self.store_a,
                    user=self.user_1,
                    role=StoreMembership.Role.ADMINISTRATOR,
                )

    def test_same_user_may_belong_to_two_stores(self):
        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        StoreMembership.objects.create(
            store=self.store_b, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        self.assertEqual(
            StoreMembership.objects.filter(user=self.user_1).count(), 2
        )

    def test_two_different_users_may_belong_to_same_store(self):
        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        StoreMembership.objects.create(
            store=self.store_a, user=self.user_2, role=StoreMembership.Role.CATALOG_MANAGER
        )
        self.assertEqual(StoreMembership.objects.filter(store=self.store_a).count(), 2)

    def test_one_active_owner_per_store_enforced(self):
        from django.db import IntegrityError, transaction

        StoreMembership.objects.create(
            store=self.store_a,
            user=self.user_1,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreMembership.objects.create(
                    store=self.store_a,
                    user=self.user_2,
                    role=StoreMembership.Role.OWNER,
                    status=StoreMembership.MembershipStatus.ACTIVE,
                    accepted_at=timezone.now(),
                )

    def test_different_stores_may_each_have_an_owner(self):
        StoreMembership.objects.create(
            store=self.store_a,
            user=self.user_1,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        StoreMembership.objects.create(
            store=self.store_b,
            user=self.user_2,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        self.assertEqual(
            StoreMembership.objects.filter(
                role=StoreMembership.Role.OWNER,
                status=StoreMembership.MembershipStatus.ACTIVE,
            ).count(),
            2,
        )

    def test_active_membership_requires_accepted_at(self):
        membership = StoreMembership(
            store=self.store_a,
            user=self.user_1,
            role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE,
        )
        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_revoked_membership_requires_revoked_at(self):
        membership = StoreMembership(
            store=self.store_a,
            user=self.user_1,
            role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.REVOKED,
        )
        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_deleting_a_user_with_a_membership_raises_protected_error(self):
        from django.db.models import ProtectedError

        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        with self.assertRaises(ProtectedError):
            self.user_1.delete()

    def test_deleting_a_user_with_a_membership_leaves_store_intact(self):
        from django.db.models import ProtectedError

        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        with self.assertRaises(ProtectedError):
            self.user_1.delete()
        self.assertTrue(Store.objects.filter(pk=self.store_a.pk).exists())

    def test_deleting_a_user_with_a_membership_leaves_membership_intact(self):
        from django.db.models import ProtectedError

        membership = StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        with self.assertRaises(ProtectedError):
            self.user_1.delete()
        self.assertTrue(StoreMembership.objects.filter(pk=membership.pk).exists())

    def test_deleting_a_user_with_no_membership_succeeds(self):
        user = User.objects.create_user(username="lonely-user", password="pass12345")
        user.delete()
        self.assertFalse(User.objects.filter(username="lonely-user").exists())

    def test_store_deletion_cascades_memberships(self):
        StoreMembership.objects.create(
            store=self.store_a, user=self.user_1, role=StoreMembership.Role.ANALYST
        )
        self.store_a.delete()
        self.assertFalse(StoreMembership.objects.filter(user=self.user_1).exists())

    def test_no_owner_field_exists_on_store_ownership_is_via_membership_only(self):
        field_names = {f.name for f in Store._meta.get_fields()}
        self.assertNotIn("owner", field_names)
