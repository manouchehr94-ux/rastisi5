"""Tests for the Checkpoint 5A subscription state machine (ADR-66): legal
and illegal transitions, idempotency, event history, and plan change."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import (
    Plan,
    PlanVersion,
    StoreSubscription,
    SubscriptionEvent,
)
from apps.subscriptions.services import subscription_service as svc

User = get_user_model()


class StateMachineTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه حالت", slug="sm-store", admin_subdomain="sm-store")
        self.plan = Plan.objects.create(code="pro", name="Pro")
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED, trial_days=14, grace_period_days=7,
        )
        self.v2 = PlanVersion.objects.create(
            plan=self.plan, version_number=2, status=PlanVersion.Status.PUBLISHED, trial_days=14,
        )
        self.actor = User.objects.create_user(username="sm-actor", password="p", is_staff=True)

    def _sub(self):
        return svc.create_subscription(self.store, self.version, actor=self.actor)


class CreateAndTrialTests(StateMachineTestCase):
    def test_create_subscription_pending(self):
        sub = self._sub()
        self.assertEqual(sub.status, StoreSubscription.Status.PENDING)
        self.assertTrue(sub.is_current)
        self.assertTrue(sub.events.filter(event_type="created").exists())

    def test_cannot_create_second_current_subscription(self):
        self._sub()
        with self.assertRaises(svc.SubscriptionError):
            self._sub()

    def test_create_requires_published_version(self):
        draft = PlanVersion.objects.create(plan=self.plan, version_number=3, status=PlanVersion.Status.DRAFT)
        with self.assertRaises(svc.SubscriptionError):
            svc.create_subscription(self.store, draft, actor=self.actor)

    def test_start_trial_sets_dates(self):
        sub = self._sub()
        sub = svc.start_trial(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertIsNotNone(sub.trial_start_at)
        self.assertIsNotNone(sub.trial_end_at)
        self.assertTrue(sub.events.filter(event_type="trial_started").exists())


class TransitionTests(StateMachineTestCase):
    def test_full_legal_lifecycle(self):
        sub = self._sub()
        sub = svc.start_trial(sub, actor=self.actor)
        sub = svc.activate_subscription(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        sub = svc.enter_grace_period(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.GRACE_PERIOD)
        self.assertIsNotNone(sub.grace_period_end)
        sub = svc.resume_subscription(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        sub = svc.suspend_subscription(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.SUSPENDED)
        sub = svc.resume_subscription(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)

    def test_expire_makes_non_current(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.expire_subscription(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.EXPIRED)
        self.assertFalse(sub.is_current)
        self.assertIsNotNone(sub.expired_at)

    def test_cancel_immediately_terminal(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.cancel_immediately(sub, actor=self.actor, reason="merchant request")
        self.assertEqual(sub.status, StoreSubscription.Status.CANCELLED)
        self.assertFalse(sub.is_current)

    def test_cancel_at_period_end_keeps_active(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.cancel_at_period_end(sub, actor=self.actor)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertTrue(sub.cancel_at_period_end)
        self.assertTrue(sub.events.filter(event_type="cancel_scheduled").exists())


class IllegalTransitionTests(StateMachineTestCase):
    def test_expired_cannot_activate(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.expire_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.activate_subscription(sub, actor=self.actor)

    def test_cancelled_cannot_trial(self):
        sub = self._sub()
        sub = svc.cancel_immediately(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.start_trial(sub, actor=self.actor)

    def test_suspended_cannot_trial(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.suspend_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.start_trial(sub, actor=self.actor)


class IdempotencyTests(StateMachineTestCase):
    def test_repeated_activation_with_same_key_is_noop(self):
        sub = self._sub()
        svc.activate_subscription(sub, actor=self.actor, idempotency_key="act-1")
        svc.activate_subscription(sub, actor=self.actor, idempotency_key="act-1")
        self.assertEqual(sub.events.filter(event_type="activated").count(), 1)

    def test_cancel_at_period_end_idempotent(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        svc.cancel_at_period_end(sub, actor=self.actor)
        svc.cancel_at_period_end(sub, actor=self.actor)
        self.assertEqual(sub.events.filter(event_type="cancel_scheduled").count(), 1)


class PlanChangeTests(StateMachineTestCase):
    def test_change_plan_version_records_event(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        sub = svc.change_plan_version(sub, self.v2, actor=self.actor, reason="upgrade")
        self.assertEqual(sub.plan_version, self.v2)
        event = sub.events.get(event_type="plan_changed")
        self.assertEqual(event.from_plan_version, self.version)
        self.assertEqual(event.to_plan_version, self.v2)

    def test_change_to_unpublished_rejected(self):
        draft = PlanVersion.objects.create(plan=self.plan, version_number=9, status=PlanVersion.Status.DRAFT)
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.SubscriptionError):
            svc.change_plan_version(sub, draft, actor=self.actor)

    def test_change_on_terminal_rejected(self):
        sub = self._sub()
        sub = svc.cancel_immediately(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.change_plan_version(sub, self.v2, actor=self.actor)

    def test_change_plan_idempotent(self):
        sub = self._sub()
        sub = svc.activate_subscription(sub, actor=self.actor)
        svc.change_plan_version(sub, self.v2, actor=self.actor, idempotency_key="chg-1")
        svc.change_plan_version(sub, self.version, actor=self.actor, idempotency_key="chg-1")
        # Second call with same key is a no-op → still on v2.
        sub.refresh_from_db()
        self.assertEqual(sub.plan_version, self.v2)
