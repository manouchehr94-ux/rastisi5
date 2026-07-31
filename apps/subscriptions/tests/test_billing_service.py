"""Section 8/9 — platform billing (PlatformInvoice/PlatformPaymentAttempt)
and the dev/test payment provider. Confirms: an invoice's amount is an
immutable snapshot; a failed/replayed payment attempt never activates a
subscription; a successful attempt is the ONLY path that activates one."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import (
    Plan,
    PlanVersion,
    PlatformInvoice,
    PlatformPaymentAttempt,
    StoreSubscription,
)
from apps.subscriptions.services import billing_service, subscription_service
from apps.subscriptions.services.payment_providers import PaymentProviderError, get_payment_provider

User = get_user_model()


class BillingTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه بیلینگ", slug="billing-store", admin_subdomain="billing-store")
        self.plan = Plan.objects.create(code="pro-billing", name="Pro")
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        self.free_version = PlanVersion.objects.create(
            plan=self.plan, version_number=2, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0,
        )
        self.other_plan = Plan.objects.create(code="enterprise-billing", name="Enterprise")
        self.other_version = PlanVersion.objects.create(
            plan=self.other_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=4_990_000,
        )
        self.actor = User.objects.create_user(username="09121110099", password="a-very-strong-pass-1")


class CreateInvoiceTests(BillingTestCase):
    def test_new_subscription_reason_when_store_has_no_subscription(self):
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        self.assertEqual(invoice.reason, PlatformInvoice.Reason.NEW_SUBSCRIPTION)
        self.assertEqual(invoice.amount, 490_000)
        self.assertEqual(invoice.status, PlatformInvoice.Status.PENDING)

    def test_renewal_reason_for_the_same_plan_already_subscribed(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.actor)
        subscription_service.activate_subscription(sub, actor=self.actor)
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        self.assertEqual(invoice.reason, PlatformInvoice.Reason.RENEWAL)

    def test_upgrade_reason_for_a_different_plan(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.actor)
        subscription_service.activate_subscription(sub, actor=self.actor)
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.other_version, actor=self.actor)
        self.assertEqual(invoice.reason, PlatformInvoice.Reason.UPGRADE)

    def test_draft_plan_version_is_rejected(self):
        draft = PlanVersion.objects.create(plan=self.plan, version_number=3, status=PlanVersion.Status.DRAFT)
        with self.assertRaises(billing_service.BillingError):
            billing_service.create_invoice(store=self.store, plan_version=draft, actor=self.actor)

    def test_free_no_interval_plan_is_rejected(self):
        with self.assertRaises(billing_service.BillingError):
            billing_service.create_invoice(store=self.store, plan_version=self.free_version, actor=self.actor)

    def test_amount_is_a_snapshot_immune_to_later_price_changes(self):
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        self.version.display_price = 999_999
        self.version.save(update_fields=["display_price"])
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount, 490_000)


class StartPaymentAttemptTests(BillingTestCase):
    def test_returns_dev_provider_redirect_url(self):
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        attempt, url = billing_service.start_payment_attempt(invoice=invoice, provider_code="dev")
        self.assertEqual(attempt.status, PlatformPaymentAttempt.Status.PENDING)
        self.assertIn(attempt.public_id, url)

    def test_unknown_provider_code_is_rejected(self):
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        with self.assertRaises(billing_service.BillingError):
            billing_service.start_payment_attempt(invoice=invoice, provider_code="totally-fake")

    def test_already_paid_invoice_cannot_start_a_new_attempt(self):
        invoice = billing_service.create_invoice(store=self.store, plan_version=self.version, actor=self.actor)
        attempt, _ = billing_service.start_payment_attempt(invoice=invoice, provider_code="dev")
        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        with self.assertRaises(billing_service.BillingError):
            billing_service.start_payment_attempt(invoice=invoice, provider_code="dev")


class ConfirmPaymentAttemptTests(BillingTestCase):
    def _invoice_and_attempt(self, plan_version=None):
        invoice = billing_service.create_invoice(
            store=self.store, plan_version=plan_version or self.version, actor=self.actor,
        )
        attempt, _ = billing_service.start_payment_attempt(invoice=invoice, provider_code="dev")
        return invoice, attempt

    def test_success_with_no_existing_subscription_creates_and_activates_one(self):
        invoice, attempt = self._invoice_and_attempt()
        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, PlatformInvoice.Status.PAID)
        self.assertIsNotNone(invoice.paid_at)

        sub = StoreSubscription.objects.get(store=self.store, is_current=True)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(sub.plan_version_id, self.version.pk)
        self.assertIsNotNone(sub.current_period_end)
        attempt.refresh_from_db()
        self.assertEqual(sub.external_reference, attempt.public_id)

    def test_success_from_trialing_activates_the_paid_period(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.actor)
        subscription_service.start_trial(sub, actor=self.actor)
        invoice, attempt = self._invoice_and_attempt()

        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)

    def test_success_renewal_of_an_active_subscription_extends_the_period(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.actor)
        subscription_service.activate_subscription(sub, actor=self.actor)
        first_period_end = sub.current_period_end
        invoice, attempt = self._invoice_and_attempt()

        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertGreater(sub.current_period_end, first_period_end or timezone.now())

    def test_success_upgrade_changes_plan_and_activates(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.actor)
        subscription_service.activate_subscription(sub, actor=self.actor)
        invoice, attempt = self._invoice_and_attempt(plan_version=self.other_version)

        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        sub.refresh_from_db()
        self.assertEqual(sub.plan_version_id, self.other_version.pk)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)

    def test_failure_never_activates_anything_and_invoice_stays_pending(self):
        invoice, attempt = self._invoice_and_attempt()
        billing_service.confirm_payment_attempt(attempt=attempt, success=False, actor=self.actor)

        attempt.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(attempt.status, PlatformPaymentAttempt.Status.FAILED)
        self.assertEqual(invoice.status, PlatformInvoice.Status.PENDING)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())

    def test_replaying_a_successful_attempt_is_a_no_op(self):
        invoice, attempt = self._invoice_and_attempt()
        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        sub = StoreSubscription.objects.get(store=self.store, is_current=True)
        period_end_after_first = sub.current_period_end

        # Replay/tamper: calling confirm again — even flipping success to
        # False — must not undo the already-recorded success.
        billing_service.confirm_payment_attempt(attempt=attempt, success=False, actor=self.actor)
        attempt.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(attempt.status, PlatformPaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(sub.current_period_end, period_end_after_first)

    def test_replaying_a_failed_attempt_stays_failed(self):
        invoice, attempt = self._invoice_and_attempt()
        billing_service.confirm_payment_attempt(attempt=attempt, success=False, actor=self.actor)
        billing_service.confirm_payment_attempt(attempt=attempt, success=True, actor=self.actor)
        attempt.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(attempt.status, PlatformPaymentAttempt.Status.FAILED)
        self.assertEqual(invoice.status, PlatformInvoice.Status.PENDING)


class PaymentProviderRegistryTests(TestCase):
    def test_dev_provider_is_registered(self):
        provider = get_payment_provider("dev")
        self.assertEqual(provider.code, "dev")

    def test_unknown_provider_raises(self):
        with self.assertRaises(PaymentProviderError):
            get_payment_provider("nonexistent")
