"""Platform Admin per-Store trial controls (Phase 2, master-prompt section
4.2): extend, set exact end, end now. These views must route through the
subscription_service state machine (not mutate StoreSubscription rows
directly) and be restricted to platform staff."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import subscription_service as svc

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class TrialControlsViewTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="pa-trial-super@example.com", email="pa-trial-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary_owner = User.objects.create_user(
            username="pa-trial-ordinary@example.com", email="pa-trial-ordinary@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = Store.objects.create(
            name="فروشگاه کنترلِ تریال", slug="trial-ctrl-store", admin_subdomain="trial-ctrl-store",
        )
        self.plan = Plan.objects.create(code="trial-ctrl-plan", name="Trial Ctrl")
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            trial_days=14, grace_period_days=7,
        )
        sub = svc.create_subscription(self.store, self.version, actor=self.superuser)
        self.subscription = svc.start_trial(sub, actor=self.superuser)
        self.client.force_login(self.superuser)

    _PATHS = {
        "store-extend-trial": "extend-trial",
        "store-set-trial-end": "set-trial-end",
        "store-end-trial-now": "end-trial-now",
    }

    def _url(self, name):
        return f"/stores/{self.store.public_id}/{self._PATHS[name]}/"


class ExtendTrialViewTests(TrialControlsViewTestCase):
    def test_extends_and_records_reason(self):
        before = self.subscription.trial_end_at
        response = self.client.post(
            self._url("store-extend-trial"), {"days": "5", "reason": "چانه‌زنیِ فروش"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.trial_end_at, before + timezone.timedelta(days=5))
        event = self.subscription.events.get(event_type=SubscriptionEvent.EventType.TRIAL_EXTENDED)
        self.assertEqual(event.reason, "چانه‌زنیِ فروش")
        self.assertEqual(event.actor, self.superuser)

    def test_non_superuser_denied(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.post(self._url("store-extend-trial"), {"days": "5"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_invalid_days_rejected(self):
        before = self.subscription.trial_end_at
        response = self.client.post(self._url("store-extend-trial"), {"days": "-1"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.trial_end_at, before)


class SetTrialEndViewTests(TrialControlsViewTestCase):
    def test_sets_exact_end(self):
        response = self.client.post(
            self._url("store-set-trial-end"),
            {"trial_end_at": "2027-01-15T10:00", "reason": "توافقِ ویژه با مشتری"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.trial_end_at.year, 2027)
        self.assertEqual(self.subscription.trial_end_at.month, 1)
        event = self.subscription.events.get(event_type=SubscriptionEvent.EventType.TRIAL_END_SET)
        self.assertEqual(event.reason, "توافقِ ویژه با مشتری")

    def test_missing_reason_rejected_by_service(self):
        response = self.client.post(
            self._url("store-set-trial-end"), {"trial_end_at": "2027-01-15T10:00"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            self.subscription.events.filter(event_type=SubscriptionEvent.EventType.TRIAL_END_SET).exists()
        )

    def test_invalid_date_format_rejected(self):
        response = self.client.post(
            self._url("store-set-trial-end"), {"trial_end_at": "not-a-date", "reason": "x"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            self.subscription.events.filter(event_type=SubscriptionEvent.EventType.TRIAL_END_SET).exists()
        )


class EndTrialNowViewTests(TrialControlsViewTestCase):
    def test_ends_trial_into_grace_period(self):
        response = self.client.post(
            self._url("store-end-trial-now"), {"reason": "درخواستِ داخلی برایِ QA"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.GRACE_PERIOD)
        # Store data must survive — ending a trial never deletes anything.
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())

    def test_missing_reason_rejected(self):
        response = self.client.post(self._url("store-end-trial-now"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.TRIALING)

    def test_non_superuser_denied(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.post(self._url("store-end-trial-now"), {"reason": "x"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.TRIALING)
