"""Section 15 — ownership transfer: two-party (initiator + target, each
their own OTP-gated confirmation), pending/expiring, fully audited. This
module tests the service layer; accept_transfer assumes the caller already
verified the target's OTP (that verification itself is tested at the view
layer in test_ownership_transfer_views.py)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreMembership, StoreOwnershipTransfer
from apps.stores.services.ownership_transfer_service import (
    OwnershipTransferError,
    accept_transfer,
    cancel_transfer,
    get_pending_transfer_by_token,
    initiate_transfer,
)
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()


class OwnershipTransferTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه انتقال", slug="transfer-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="transfer-store",
        )
        self.owner = User.objects.create_user(username="09121320011", password="a-very-strong-pass-1")
        self.owner_membership = StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )


class InitiateTransferTests(OwnershipTransferTestCase):
    def test_creates_a_pending_transfer(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.PENDING)
        self.assertEqual(transfer.target_phone, "09121320099")
        self.assertTrue(transfer.token)

    def test_non_owner_cannot_initiate(self):
        staff = User.objects.create_user(username="09121320022", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=self.store, user=staff, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        with self.assertRaises(OwnershipTransferError):
            initiate_transfer(store=self.store, initiated_by=staff, target_phone="09121320099")

    def test_cannot_have_two_pending_transfers(self):
        initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        with self.assertRaises(OwnershipTransferError):
            initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320088")

    def test_records_audit_event(self):
        initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="store.ownership_transfer_initiated").exists()
        )


class AcceptTransferTests(OwnershipTransferTestCase):
    def test_accept_makes_target_the_new_owner(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        _updated, new_owner = accept_transfer(transfer=transfer)

        self.assertEqual(new_owner.username, "09121320099")
        membership = StoreMembership.objects.get(store=self.store, user=new_owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_accept_demotes_previous_owner_to_administrator(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, StoreMembership.Role.ADMINISTRATOR)

    def test_only_one_active_owner_after_transfer(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        owners = StoreMembership.objects.filter(
            store=self.store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        self.assertEqual(owners.count(), 1)

    def test_marks_transfer_completed(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        updated, _new_owner = accept_transfer(transfer=transfer)
        self.assertEqual(updated.status, StoreOwnershipTransfer.Status.COMPLETED)
        self.assertIsNotNone(updated.completed_at)

    def test_expired_transfer_cannot_be_accepted(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        transfer.expires_at = timezone.now() - timezone.timedelta(days=1)
        transfer.save(update_fields=["expires_at"])
        with self.assertRaises(OwnershipTransferError):
            accept_transfer(transfer=transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.EXPIRED)

    def test_already_completed_transfer_cannot_be_accepted_again(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        with self.assertRaises(OwnershipTransferError):
            accept_transfer(transfer=transfer)

    def test_target_who_already_has_a_membership_is_just_promoted(self):
        existing_target = User.objects.create_user(username="09121320099", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=self.store, user=existing_target, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)

        membership = StoreMembership.objects.get(store=self.store, user=existing_target)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(StoreMembership.objects.filter(store=self.store, user=existing_target).count(), 1)

    def test_records_audit_event(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="store.ownership_transfer_completed").exists()
        )


class CancelTransferTests(OwnershipTransferTestCase):
    def test_cancel_marks_cancelled(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        cancel_transfer(transfer=transfer, actor=self.owner)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.CANCELLED)

    def test_cancelled_transfer_allows_a_new_one(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        cancel_transfer(transfer=transfer, actor=self.owner)
        new_transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320088")
        self.assertEqual(new_transfer.status, StoreOwnershipTransfer.Status.PENDING)

    def test_cannot_cancel_a_completed_transfer(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        with self.assertRaises(OwnershipTransferError):
            cancel_transfer(transfer=transfer, actor=self.owner)


class GetPendingTransferByTokenTests(OwnershipTransferTestCase):
    def test_finds_a_pending_transfer(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        found = get_pending_transfer_by_token(transfer.token)
        self.assertEqual(found.pk, transfer.pk)

    def test_returns_none_for_a_completed_transfer(self):
        transfer = initiate_transfer(store=self.store, initiated_by=self.owner, target_phone="09121320099")
        accept_transfer(transfer=transfer)
        self.assertIsNone(get_pending_transfer_by_token(transfer.token))

    def test_returns_none_for_garbage_token(self):
        self.assertIsNone(get_pending_transfer_by_token("not-a-real-token"))
