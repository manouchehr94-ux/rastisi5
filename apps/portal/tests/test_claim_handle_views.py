"""Section 11 — the owner-facing permanent handle claim view, gated behind
step-up OTP (Section 10) just like subscription purchase, using a distinct
action key ("permanent_handle_claim") so verifying one sensitive action
never unlocks a different one for the same Store."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerProfile
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service

User = get_user_model()
_HOST = "rastisi.localhost"


def _fixed_code(code="556677"):
    import apps.portal.services.owner_otp_service as svc

    original = svc._generate_code
    svc._generate_code = lambda: code
    return original


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ClaimHandleViewTests(TestCase):
    def setUp(self):
        # OTP rate-limit counters are cache-backed, not DB-backed — they
        # survive this test's transaction rollback and can otherwise leak
        # into whichever test happens to run next and also requests OTPs.
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه ویو نام دائمی", slug="claim-view-store", admin_subdomain="claim-view-store",
        )
        self.owner = User.objects.create_user(username="09121270011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121270011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        self.code = "556677"
        self.original_generate_code = _fixed_code(self.code)
        self.addCleanup(self._restore_generate_code)

    def _restore_generate_code(self):
        import apps.portal.services.owner_otp_service as svc

        svc._generate_code = self.original_generate_code

    def _activate_paid_subscription(self):
        plan = Plan.objects.create(code=f"pro-claimview-{self.store.pk}", name="Pro")
        version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        sub = subscription_service.create_subscription(self.store, version, actor=self.owner)
        subscription_service.activate_subscription(sub, actor=self.owner)

    def _url(self):
        return f"/app/stores/{self.store.public_id}/handle/"

    def test_without_a_paid_subscription_shows_the_blocked_state(self):
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_claim"])

    def test_with_a_paid_subscription_the_form_is_available(self):
        self._activate_paid_subscription()
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertTrue(response.context["can_claim"])

    def test_post_without_paid_subscription_does_not_claim(self):
        response = self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StoreDomain.objects.filter(store=self.store, domain_type="platform_subdomain").exists())

    def test_post_is_gated_behind_step_up_by_default(self):
        self._activate_paid_subscription()
        response = self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/handle/step-up/")
        self.assertFalse(StoreDomain.objects.filter(store=self.store, domain_type="platform_subdomain").exists())

    def test_correct_step_up_code_completes_the_claim(self):
        self._activate_paid_subscription()
        self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/handle/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url())
        domain = StoreDomain.objects.get(store=self.store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN)
        self.assertEqual(domain.hostname, "novin.rastisi.ir")
        self.assertTrue(domain.is_primary)

    def test_wrong_step_up_code_does_not_claim(self):
        self._activate_paid_subscription()
        self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/handle/step-up/", {"code": "000000"}, HTTP_HOST=_HOST,
        )
        self.assertFalse(StoreDomain.objects.filter(store=self.store, domain_type="platform_subdomain").exists())

    def test_already_claimed_store_shows_the_claimed_hostname(self):
        self._activate_paid_subscription()
        self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/handle/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertTrue(response.context["already_claimed"])
        self.assertContains(response, "novin.rastisi.ir")

    def test_billing_step_up_verification_does_not_unlock_handle_claim(self):
        """Different action keys must not share verified state, even for
        the exact same (owner, Store) — only the (action, target) pair
        that was actually verified counts."""
        self._activate_paid_subscription()
        session = self.client.session
        session["portal_step_up_verified"] = {
            f"subscription_purchase_confirm:{self.store.public_id}": {
                "expires_at": timezone.now().timestamp() + 900,
            },
        }
        session.save()

        response = self.client.post(self._url(), {"label": "novin"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/handle/step-up/")

    def test_other_owner_cannot_claim_someone_elses_store(self):
        other = User.objects.create_user(username="09121270022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)
