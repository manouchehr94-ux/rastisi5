"""Tests for the Phase-2 manual trial controls (extend/set-end/end-now) on
apps.subscriptions.services.subscription_service — Platform Admin per-Store
trial overrides. Covers: service-layer enforcement (trialing-only, reason
required), audit/event trail with before/after end times, idempotency, and
that ending a trial never deletes Store data (grace/expired, not deletion)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import subscription_service as svc

User = get_user_model()


class ManualTrialControlsTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه تریال", slug="trial-store", admin_subdomain="trial-store")
        self.plan = Plan.objects.create(code="pro-trial", name="Pro")
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            trial_days=14, grace_period_days=7,
        )
        self.no_grace_version = PlanVersion.objects.create(
            plan=self.plan, version_number=2, status=PlanVersion.Status.PUBLISHED,
            trial_days=14, grace_period_days=0,
        )
        self.actor = User.objects.create_user(username="trial-admin", password="p", is_staff=True, is_superuser=True)

    def _trialing_sub(self, version=None):
        sub = svc.create_subscription(self.store, version or self.version, actor=self.actor)
        return svc.start_trial(sub, actor=self.actor)


class ExtendTrialTests(ManualTrialControlsTestCase):
    def test_extends_from_current_end(self):
        sub = self._trialing_sub()
        before = sub.trial_end_at
        sub = svc.extend_trial(sub, days=5, actor=self.actor, reason="درخواستِ مشتری")
        self.assertEqual(sub.trial_end_at, before + timezone.timedelta(days=5))
        event = sub.events.get(event_type=SubscriptionEvent.EventType.TRIAL_EXTENDED)
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.reason, "درخواستِ مشتری")
        self.assertEqual(event.metadata["days_added"], 5)
        self.assertIn("previous_trial_end_at", event.metadata)
        self.assertIn("new_trial_end_at", event.metadata)

    def test_requires_reason(self):
        sub = self._trialing_sub()
        with self.assertRaises(svc.SubscriptionError):
            svc.extend_trial(sub, days=5, actor=self.actor, reason="   ")

    def test_requires_positive_days(self):
        sub = self._trialing_sub()
        with self.assertRaises(svc.SubscriptionError):
            svc.extend_trial(sub, days=0, actor=self.actor, reason="x")
        with self.assertRaises(svc.SubscriptionError):
            svc.extend_trial(sub, days=-3, actor=self.actor, reason="x")

    def test_rejected_when_not_trialing(self):
        sub = svc.create_subscription(self.store, self.version, actor=self.actor)
        sub = svc.activate_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.extend_trial(sub, days=5, actor=self.actor, reason="x")

    def test_idempotency_key_prevents_double_extension(self):
        sub = self._trialing_sub()
        svc.extend_trial(sub, days=5, actor=self.actor, reason="x", idempotency_key="ext-1")
        sub.refresh_from_db()
        after_first = sub.trial_end_at
        svc.extend_trial(sub, days=5, actor=self.actor, reason="x", idempotency_key="ext-1")
        sub.refresh_from_db()
        self.assertEqual(sub.trial_end_at, after_first)
        self.assertEqual(sub.events.filter(event_type=SubscriptionEvent.EventType.TRIAL_EXTENDED).count(), 1)


class SetTrialEndTests(ManualTrialControlsTestCase):
    def test_sets_exact_end(self):
        sub = self._trialing_sub()
        target = timezone.now() + timezone.timedelta(days=40)
        sub = svc.set_trial_end(sub, end_at=target, actor=self.actor, reason="توافقِ ویژه")
        self.assertEqual(sub.trial_end_at, target)
        event = sub.events.get(event_type=SubscriptionEvent.EventType.TRIAL_END_SET)
        self.assertEqual(event.reason, "توافقِ ویژه")

    def test_rejects_naive_datetime(self):
        import datetime

        sub = self._trialing_sub()
        with self.assertRaises(svc.SubscriptionError):
            svc.set_trial_end(sub, end_at=datetime.datetime.now(), actor=self.actor, reason="x")

    def test_requires_reason(self):
        sub = self._trialing_sub()
        with self.assertRaises(svc.SubscriptionError):
            svc.set_trial_end(sub, end_at=timezone.now(), actor=self.actor, reason="")

    def test_rejected_when_not_trialing(self):
        sub = svc.create_subscription(self.store, self.version, actor=self.actor)
        sub = svc.activate_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.set_trial_end(sub, end_at=timezone.now(), actor=self.actor, reason="x")


class EndTrialNowTests(ManualTrialControlsTestCase):
    def test_ends_into_grace_period_when_plan_has_grace_days(self):
        sub = self._trialing_sub(self.version)
        sub = svc.end_trial_now(sub, actor=self.actor, reason="پایانِ زودهنگام")
        self.assertEqual(sub.status, StoreSubscription.Status.GRACE_PERIOD)
        self.assertIsNotNone(sub.grace_period_end)
        event = sub.events.get(event_type=SubscriptionEvent.EventType.TRIAL_ENDED_MANUALLY)
        self.assertEqual(event.reason, "پایانِ زودهنگام")
        self.assertEqual(event.to_status, StoreSubscription.Status.GRACE_PERIOD)

    def test_ends_directly_expired_when_plan_has_no_grace(self):
        sub = self._trialing_sub(self.no_grace_version)
        sub = svc.end_trial_now(sub, actor=self.actor, reason="پایانِ زودهنگام")
        self.assertEqual(sub.status, StoreSubscription.Status.EXPIRED)
        self.assertIsNotNone(sub.expired_at)

    def test_requires_reason(self):
        sub = self._trialing_sub()
        with self.assertRaises(svc.SubscriptionError):
            svc.end_trial_now(sub, actor=self.actor, reason="")

    def test_does_not_delete_store_or_owner_access(self):
        """Ending a trial must never delete Store data — the Store row and
        its subscription history must survive intact."""
        sub = self._trialing_sub()
        svc.end_trial_now(sub, actor=self.actor, reason="پایانِ زودهنگام")
        self.store.refresh_from_db()
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())
        self.assertTrue(StoreSubscription.objects.filter(pk=sub.pk).exists())

    def test_rejected_when_not_trialing(self):
        sub = svc.create_subscription(self.store, self.version, actor=self.actor)
        sub = svc.activate_subscription(sub, actor=self.actor)
        with self.assertRaises(svc.IllegalTransitionError):
            svc.end_trial_now(sub, actor=self.actor, reason="x")
