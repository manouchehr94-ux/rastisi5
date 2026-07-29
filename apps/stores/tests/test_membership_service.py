from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreMembership
from apps.stores.services.membership_service import (
    MembershipError,
    active_owner_count,
    add_staff_member,
    change_role,
    list_memberships,
    reactivate_membership,
    revoke_membership,
    transfer_ownership,
)

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class MembershipServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.owner_user = User.objects.create_user(username="09121190001", password="pass12345", is_staff=True)
        self.owner_membership = StoreMembership.objects.create(
            store=self.store, user=self.owner_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )


class AddStaffMemberTests(MembershipServiceTestCase):
    def test_creates_new_user_and_active_membership(self):
        membership = add_staff_member(
            self.store, phone="09121190002", role=StoreMembership.Role.CATALOG_MANAGER,
            invited_by=self.owner_user,
        )
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertEqual(membership.role, StoreMembership.Role.CATALOG_MANAGER)
        self.assertIsNotNone(membership.accepted_at)
        user = User.objects.get(username="09121190002")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.has_usable_password())

    def test_reuses_existing_user_account(self):
        existing_user = User.objects.create_user(username="09121190003", password="realpass")
        membership = add_staff_member(
            self.store, phone="09121190003", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user,
        )
        self.assertEqual(membership.user_id, existing_user.pk)
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.is_staff)
        self.assertTrue(existing_user.has_usable_password())

    def test_duplicate_active_membership_rejected(self):
        add_staff_member(self.store, phone="09121190004", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        with self.assertRaises(MembershipError):
            add_staff_member(self.store, phone="09121190004", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)

    def test_reinvite_after_revoke_reactivates_same_row_not_new_row(self):
        membership = add_staff_member(self.store, phone="09121190005", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        revoke_membership(membership)
        reactivated = add_staff_member(
            self.store, phone="09121190005", role=StoreMembership.Role.ORDER_MANAGER, invited_by=self.owner_user,
        )
        self.assertEqual(reactivated.pk, membership.pk)
        self.assertEqual(reactivated.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertEqual(reactivated.role, StoreMembership.Role.ORDER_MANAGER)
        self.assertEqual(
            StoreMembership.objects.filter(store=self.store, user__username="09121190005").count(), 1,
        )

    def test_invalid_phone_rejected(self):
        with self.assertRaises(MembershipError):
            add_staff_member(self.store, phone="12345", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)

    def test_cannot_assign_owner_role_via_add(self):
        with self.assertRaises(MembershipError):
            add_staff_member(self.store, phone="09121190006", role=StoreMembership.Role.OWNER, invited_by=self.owner_user)

    def test_membership_scoped_to_store_another_store_unaffected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ms-other", status=Store.Status.ACTIVE)
        add_staff_member(self.store, phone="09121190007", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        self.assertEqual(StoreMembership.objects.filter(store=other_store).count(), 0)


class ChangeRoleTests(MembershipServiceTestCase):
    def test_changes_role(self):
        membership = add_staff_member(self.store, phone="09121190010", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        change_role(membership, new_role=StoreMembership.Role.CATALOG_MANAGER)
        membership.refresh_from_db()
        self.assertEqual(membership.role, StoreMembership.Role.CATALOG_MANAGER)

    def test_cannot_change_owner_role(self):
        with self.assertRaises(MembershipError):
            change_role(self.owner_membership, new_role=StoreMembership.Role.ANALYST)

    def test_cannot_promote_to_owner(self):
        membership = add_staff_member(self.store, phone="09121190011", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        with self.assertRaises(MembershipError):
            change_role(membership, new_role=StoreMembership.Role.OWNER)


class RevokeMembershipTests(MembershipServiceTestCase):
    def test_revokes_active_membership(self):
        membership = add_staff_member(self.store, phone="09121190020", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        revoke_membership(membership)
        membership.refresh_from_db()
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.REVOKED)
        self.assertIsNotNone(membership.revoked_at)

    def test_cannot_revoke_owner(self):
        with self.assertRaises(MembershipError):
            revoke_membership(self.owner_membership)
        self.assertEqual(active_owner_count(self.store), 1)

    def test_cannot_revoke_twice(self):
        membership = add_staff_member(self.store, phone="09121190021", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        revoke_membership(membership)
        with self.assertRaises(MembershipError):
            revoke_membership(membership)


class ReactivateMembershipTests(MembershipServiceTestCase):
    def test_reactivates_revoked_membership(self):
        membership = add_staff_member(self.store, phone="09121190030", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        revoke_membership(membership)
        reactivate_membership(membership)
        membership.refresh_from_db()
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertIsNone(membership.revoked_at)

    def test_cannot_reactivate_already_active(self):
        membership = add_staff_member(self.store, phone="09121190031", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        with self.assertRaises(MembershipError):
            reactivate_membership(membership)


class TransferOwnershipTests(MembershipServiceTestCase):
    def test_transfers_ownership(self):
        new_owner = add_staff_member(self.store, phone="09121190040", role=StoreMembership.Role.ADMINISTRATOR, invited_by=self.owner_user)
        transfer_ownership(self.store, current_owner=self.owner_membership, new_owner=new_owner)
        self.owner_membership.refresh_from_db()
        new_owner.refresh_from_db()
        self.assertEqual(self.owner_membership.role, StoreMembership.Role.ADMINISTRATOR)
        self.assertEqual(new_owner.role, StoreMembership.Role.OWNER)
        self.assertEqual(active_owner_count(self.store), 1)

    def test_cannot_transfer_to_inactive_membership(self):
        new_owner = add_staff_member(self.store, phone="09121190041", role=StoreMembership.Role.ADMINISTRATOR, invited_by=self.owner_user)
        revoke_membership(new_owner)
        with self.assertRaises(MembershipError):
            transfer_ownership(self.store, current_owner=self.owner_membership, new_owner=new_owner)

    def test_cannot_transfer_membership_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ms-other-transfer", status=Store.Status.ACTIVE)
        other_owner_user = User.objects.create_user(username="09121190050", password="pass12345", is_staff=True)
        other_owner = StoreMembership.objects.create(
            store=other_store, user=other_owner_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        with self.assertRaises(MembershipError):
            transfer_ownership(self.store, current_owner=self.owner_membership, new_owner=other_owner)


class ListMembershipsTests(MembershipServiceTestCase):
    def test_active_first_then_invited_then_revoked(self):
        revoked = add_staff_member(self.store, phone="09121190060", role=StoreMembership.Role.ANALYST, invited_by=self.owner_user)
        revoke_membership(revoked)
        invited = StoreMembership.objects.create(
            store=self.store, user=User.objects.create_user(username="09121190061", is_staff=True),
            role=StoreMembership.Role.ANALYST, status=StoreMembership.MembershipStatus.INVITED,
        )
        memberships = list_memberships(self.store)
        statuses = [m.status for m in memberships]
        self.assertEqual(
            statuses.index(StoreMembership.MembershipStatus.ACTIVE) < statuses.index(StoreMembership.MembershipStatus.INVITED),
            True,
        )
        self.assertEqual(
            statuses.index(StoreMembership.MembershipStatus.INVITED) < statuses.index(StoreMembership.MembershipStatus.REVOKED),
            True,
        )

    def test_only_this_store_memberships_returned(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ms-other-list", status=Store.Status.ACTIVE)
        other_user = User.objects.create_user(username="09121190070", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=other_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        memberships = list_memberships(self.store)
        self.assertTrue(all(m.store_id == self.store.id for m in memberships))
