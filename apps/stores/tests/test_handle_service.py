"""Section 11 — permanent Store handle claim: one-time, race-safe (DB
uniqueness), only after a paid+active subscription, and the trial hostname
is retired (never redirected, never deleted, never reassigned)."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.handle_service import (
    HandleError,
    claim_platform_handle,
    has_claimed_handle,
    rename_platform_handle_as_superuser,
)
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service

User = get_user_model()


class HandleServiceTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه نام دائمی", slug="handle-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="handle-store",
        )
        self.trial_domain = StoreDomain.objects.create(
            store=self.store, hostname=f"{self.store.platform_code}.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.actor = User.objects.create_user(username="09121260011", password="a-very-strong-pass-1")

    def _make_paid_active_subscription(self):
        plan = Plan.objects.create(code=f"pro-handle-{self.store.pk}", name="Pro")
        version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        sub = subscription_service.create_subscription(self.store, version, actor=self.actor)
        subscription_service.activate_subscription(sub, actor=self.actor)
        return sub


class ClaimPlatformHandleTests(HandleServiceTestCase):
    def test_rejects_without_a_paid_active_subscription(self):
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="digilool", actor=self.actor)

    def test_rejects_for_a_still_trialing_subscription(self):
        plan = Plan.objects.create(code="trial-only-handle", name="Trial")
        version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED, trial_days=14,
        )
        sub = subscription_service.create_subscription(self.store, version, actor=self.actor)
        subscription_service.start_trial(sub, actor=self.actor)
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="digilool", actor=self.actor)

    def test_successful_claim_creates_verified_primary_platform_subdomain(self):
        self._make_paid_active_subscription()
        domain = claim_platform_handle(store=self.store, label="Digilool", actor=self.actor)

        self.assertEqual(domain.hostname, "digilool.rastisi.ir")
        self.assertTrue(domain.is_primary)
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.PLATFORM_SUBDOMAIN)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertIsNotNone(domain.verified_at)
        self.assertTrue(has_claimed_handle(self.store))

    def test_sends_a_security_notification(self):
        from apps.notifications.models import NotificationOutbox

        self._make_paid_active_subscription()
        claim_platform_handle(store=self.store, label="digilool", actor=self.actor)
        self.assertTrue(NotificationOutbox.objects.filter(recipient_user=self.actor, is_security=True).exists())

    def test_successful_claim_retires_the_old_trial_hostname_without_deleting_it(self):
        self._make_paid_active_subscription()
        claim_platform_handle(store=self.store, label="digilool", actor=self.actor)

        self.trial_domain.refresh_from_db()
        self.assertFalse(self.trial_domain.is_primary)
        self.assertIsNotNone(self.trial_domain.retired_at)
        self.assertTrue(StoreDomain.objects.filter(pk=self.trial_domain.pk).exists())

    def test_cannot_claim_twice(self):
        self._make_paid_active_subscription()
        claim_platform_handle(store=self.store, label="digilool", actor=self.actor)
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="anothername", actor=self.actor)

    def test_reserved_word_is_rejected(self):
        self._make_paid_active_subscription()
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="admin", actor=self.actor)

    def test_already_taken_label_is_rejected_not_silently_reassigned(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="handle-other-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="handle-other-store",
        )
        StoreDomain.objects.create(
            store=other_store, hostname="digilool.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self._make_paid_active_subscription()
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="digilool", actor=self.actor)
        # Nothing about this Store changed — the whole attempt rolled back.
        self.trial_domain.refresh_from_db()
        self.assertTrue(self.trial_domain.is_primary)
        self.assertIsNone(self.trial_domain.retired_at)

    def test_failed_claim_never_leaves_the_store_without_a_primary_domain(self):
        other_store = Store.objects.create(
            name="فروشگاه سوم", slug="handle-third-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="handle-third-store",
        )
        StoreDomain.objects.create(
            store=other_store, hostname="takenlabel.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self._make_paid_active_subscription()
        with self.assertRaises(HandleError):
            claim_platform_handle(store=self.store, label="takenlabel", actor=self.actor)
        self.assertTrue(StoreDomain.objects.filter(store=self.store, is_primary=True).exists())


class RenamePlatformHandleAsSuperuserTests(HandleServiceTestCase):
    def _claimed_store(self):
        self._make_paid_active_subscription()
        claim_platform_handle(store=self.store, label="oldname", actor=self.actor)
        return self.store

    def test_requires_a_reason(self):
        store = self._claimed_store()
        with self.assertRaises(HandleError):
            rename_platform_handle_as_superuser(store=store, new_label="newname", actor=self.actor, reason="")

    def test_requires_an_existing_claimed_handle(self):
        with self.assertRaises(HandleError):
            rename_platform_handle_as_superuser(
                store=self.store, new_label="newname", actor=self.actor, reason="merchant request",
            )

    def test_successful_rename_retires_old_and_creates_new(self):
        store = self._claimed_store()
        old_hostname = "oldname.rastisi.ir"
        new_domain = rename_platform_handle_as_superuser(
            store=store, new_label="newname", actor=self.actor, reason="brand change requested by owner",
        )
        self.assertEqual(new_domain.hostname, "newname.rastisi.ir")
        self.assertTrue(new_domain.is_primary)

        old = StoreDomain.objects.get(hostname=old_hostname)
        self.assertFalse(old.is_primary)
        self.assertIsNotNone(old.retired_at)

    def test_rename_is_not_restricted_to_once(self):
        store = self._claimed_store()
        rename_platform_handle_as_superuser(store=store, new_label="second", actor=self.actor, reason="r1")
        third = rename_platform_handle_as_superuser(store=store, new_label="third", actor=self.actor, reason="r2")
        self.assertEqual(third.hostname, "third.rastisi.ir")
