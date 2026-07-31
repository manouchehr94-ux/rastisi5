"""Section 8/9 — the portal-facing subscription purchase flow: plan list →
checkout → dev/test provider fake bank page → return. Exercised through the
real HTTP client (not the service layer directly) so the urlconf/reverse
wiring between apps.portal and apps.subscriptions is actually verified."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, PlatformInvoice, StoreSubscription
from apps.subscriptions.services import subscription_service

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class BillingViewsTestCase(TestCase):
    """Section 10's step-up OTP is exercised on its own in
    test_step_up_billing.py; these tests are about checkout/dev-provider
    mechanics, so step-up is explicitly turned off here to isolate that.

    PlatformConfiguration is cached (300s) independently of the DB — a
    view read *after* the setUp update but *before* this test's transaction
    rolls back would otherwise leave a stale cached copy that outlives the
    rollback and leaks into whichever test runs next in this process, so
    the cache is force-cleared on teardown too, not just before the update.
    """

    def setUp(self):
        self.addCleanup(cache.clear)
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(
            name="فروشگاه صورتحساب", slug="billing-view-store", admin_subdomain="billing-view-store",
        )
        self.owner = User.objects.create_user(username="09121230011", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.plan = Plan.objects.create(code="pro-view", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        self.client.force_login(self.owner)

    def _checkout(self):
        return self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )


class BillingPlansViewTests(BillingViewsTestCase):
    def test_lists_published_paid_plan(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pro")

    def test_hides_draft_versions(self):
        PlanVersion.objects.create(
            plan=self.plan, version_number=2, status=PlanVersion.Status.DRAFT, display_price=1,
        )
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        versions = response.context["plan_versions"]
        self.assertEqual([v.pk for v in versions], [self.version.pk])

    def test_hides_free_plans(self):
        free_plan = Plan.objects.create(code="trial-view", name="Trial", is_publicly_selectable=True)
        PlanVersion.objects.create(
            plan=free_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0,
        )
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        versions = response.context["plan_versions"]
        self.assertNotIn(free_plan.code, [v.plan.code for v in versions])

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_other_owner_cannot_see_someone_elses_billing_page(self):
        other = User.objects.create_user(username="09121230022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)


class BillingCheckoutViewTests(BillingViewsTestCase):
    def test_creates_invoice_and_redirects_to_dev_provider(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/dev-provider/", response["Location"])
        self.assertEqual(PlatformInvoice.objects.filter(store=self.store).count(), 1)

    def test_get_is_not_allowed(self):
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 405)

    def test_draft_version_cannot_be_checked_out(self):
        draft = PlanVersion.objects.create(plan=self.plan, version_number=2, status=PlanVersion.Status.DRAFT)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{draft.pk}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)


class BillingDevProviderViewTests(BillingViewsTestCase):
    def _attempt_public_id(self):
        response = self._checkout()
        return response["Location"].rstrip("/").rsplit("/", 1)[-1]

    def test_get_renders_fake_bank_page(self):
        public_id = self._attempt_public_id()
        response = self.client.get(f"/billing/dev-provider/{public_id}/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درگاهِ آزمایشی")

    def test_non_member_gets_404(self):
        public_id = self._attempt_public_id()
        stranger = User.objects.create_user(username="09121230033", password="a-very-strong-pass-1")
        self.client.force_login(stranger)
        response = self.client.get(f"/billing/dev-provider/{public_id}/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_pay_action_activates_subscription_and_redirects_to_return(self):
        public_id = self._attempt_public_id()
        response = self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "pay"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/invoices/", response["Location"])

        sub = StoreSubscription.objects.get(store=self.store, is_current=True)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(sub.plan_version_id, self.version.pk)

    def test_fail_action_never_activates_and_invoice_stays_pending(self):
        public_id = self._attempt_public_id()
        self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "fail"}, HTTP_HOST=_HOST)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())
        invoice = PlatformInvoice.objects.get(store=self.store)
        self.assertEqual(invoice.status, PlatformInvoice.Status.PENDING)

    def test_revisiting_a_finalized_attempt_redirects_straight_to_return(self):
        public_id = self._attempt_public_id()
        self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "pay"}, HTTP_HOST=_HOST)
        response = self.client.get(f"/billing/dev-provider/{public_id}/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/invoices/", response["Location"])

    def test_full_purchase_flow_from_a_trialing_subscription(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.owner)
        subscription_service.start_trial(sub, actor=self.owner)

        public_id = self._attempt_public_id()
        self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "pay"}, HTTP_HOST=_HOST)

        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)


class BillingReturnViewTests(BillingViewsTestCase):
    def test_shows_paid_state(self):
        response = self._checkout()
        public_id = response["Location"].rstrip("/").rsplit("/", 1)[-1]
        self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "pay"}, HTTP_HOST=_HOST)

        invoice = PlatformInvoice.objects.get(store=self.store)
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/invoices/{invoice.public_id}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "با موفقیت")

    def test_other_owners_invoice_is_not_reachable(self):
        response = self._checkout()
        public_id = response["Location"].rstrip("/").rsplit("/", 1)[-1]
        self.client.post(f"/billing/dev-provider/{public_id}/", {"action": "pay"}, HTTP_HOST=_HOST)
        invoice = PlatformInvoice.objects.get(store=self.store)

        other_store = Store.objects.create(name="فروشگاه دیگر", slug="billing-other-store", admin_subdomain="billing-other-store")
        other_owner = User.objects.create_user(username="09121230044", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=other_store, user=other_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(other_owner)
        response = self.client.get(
            f"/app/stores/{other_store.public_id}/billing/invoices/{invoice.public_id}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)
