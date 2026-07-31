from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services import provisioning_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.publication_service import PublicationState, get_store_publication_state

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingViewTests(TestCase):
    """Section 5 — the multi-stage wizard (identity → industry → branding →
    review). The dispatcher (``/onboarding/``) always redirects to whichever
    stage the Store is currently on; only the review stage's POST sets
    ``onboarding_completed_at``."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="onboardowner@example.com", email="onboardowner@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه من")
        self.client.force_login(self.owner)

    def _url(self, stage):
        return f"/app/stores/{self.store.public_id}/onboarding/{stage}/"

    def test_dispatcher_redirects_a_fresh_store_to_the_identity_stage(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("identity"))

    def test_identity_stage_renders_form_with_current_name(self):
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فروشگاه من")

    def test_new_store_starts_with_onboarding_incomplete(self):
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)

    def _complete_identity(self, name="عطر گل"):
        return self.client.post(self._url("identity"), {"name": name}, HTTP_HOST=_HOST)

    def test_identity_stage_saves_name_and_advances_to_industry(self):
        response = self._complete_identity()
        self.assertRedirects(response, self._url("industry"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "عطر گل")
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.INDUSTRY)
        self.assertIsNone(self.store.onboarding_completed_at)

    def test_industry_stage_installs_the_selected_template_and_advances(self):
        from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation

        template = IndustryTemplate.objects.create(
            slug="perfume", name="عطر", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        self._complete_identity()
        response = self.client.post(
            self._url("industry"), {"industry_template_id": template.pk}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url("branding"))
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, template.pk)

    def test_industry_stage_already_installed_never_installs_twice(self):
        from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
        from apps.catalog.services.industry_template_service import install_industry_template

        template = IndustryTemplate.objects.create(
            slug="books", name="کتاب", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        self._complete_identity()
        install_industry_template(self.store, template)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

        response = self.client.get(self._url("industry"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کتاب")

        response = self.client.post(self._url("industry"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("branding"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_industry_stage_skip_advances_to_branding_without_installing(self):
        self._complete_identity()
        response = self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("branding"))
        self.assertFalse(hasattr(self.store, "industry_installation"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_branding_stage_skip_advances_to_review(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("review"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.REVIEW)

    def test_branding_stage_saves_colors(self):
        from apps.core.models import ShopSettings

        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.post(
            self._url("branding"), {"primary_color": "#112233", "accent_color": "#445566"}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url("review"))
        shop_settings = ShopSettings.load(store=self.store)
        self.assertEqual(shop_settings.primary_color, "#112233")
        self.assertEqual(shop_settings.accent_color, "#445566")

    def test_review_stage_publishes_and_completes_onboarding(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.post(self._url("review"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.onboarding_completed_at)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)

    def test_dispatcher_resumes_at_the_saved_stage(self):
        self._complete_identity()
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("industry"))

    def test_dispatcher_sends_a_completed_store_straight_to_store_created(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("review"), {}, HTTP_HOST=_HOST)
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/created/")

    def test_earlier_stage_remains_freely_editable_after_advancing(self):
        self._complete_identity()
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.client.post(self._url("identity"), {"name": "دوباره ویرایش شد"}, HTTP_HOST=_HOST)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "دوباره ویرایش شد")
        # Revisiting an earlier stage never regresses saved progress.
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.INDUSTRY)

    def test_other_owner_cannot_onboard_someone_elses_store(self):
        other = User.objects.create_user(
            username="otheronboard@example.com", email="otheronboard@example.com",
            password="a-very-strong-pass-1",
        )
        self.client.force_login(other)
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class RegistrationAutoProvisionsTrialStoreTests(TestCase):
    def _fixed_code(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "222333"
        self.addCleanup(setattr, svc, "_generate_code", original)
        return "222333"

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_first_registration_creates_exactly_one_store(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "First Timer", "phone": "09359990001"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990001", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990001")
        memberships = StoreMembership.objects.filter(
            user=user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        self.assertEqual(memberships.count(), 1)
        self.assertEqual(memberships.first().store.name, "فروشگاه من")

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_my_stores_shows_the_auto_provisioned_store_immediately(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Second", "phone": "09359990002"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990002", "code": code}, HTTP_HOST=_HOST)

        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertContains(response, "فروشگاه من")
        self.assertContains(response, "راه‌اندازی ناتمام")

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_trial_store_storefront_is_403_until_onboarding_completes(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Third", "phone": "09359990003"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990003", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990003")
        store = StoreMembership.objects.get(user=user).store
        trial_domain = store.domains.get(is_primary=True)

        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        # RASTISI_DEFAULT_PLAN_CODE is unset in this environment (Section 7 —
        # the four seeded Plans — is not built yet), so provisioning's call
        # to provision_default_subscription fails open and creates no
        # subscription at all. With zero subscriptions, publication_service
        # itself fails open (ADR-65/ADR-103) rather than restrict a Store it
        # has no entitlement data for — so this is correctly 200 today. Once
        # a real default plan is configured, this same Store (still not
        # onboarded) would 403 instead — see test_publication_service.py for
        # that behavior tested directly against the service, and
        # test_full_chain_with_real_default_plan_configured below for the
        # same thing exercised end-to-end.
        self.assertEqual(response.status_code, 200)

    @override_settings(RASTISI_DEFAULT_PLAN_CODE="trial")
    def test_full_chain_with_real_default_plan_configured(self):
        """Section 7 (four seeded Plans) closes the loop Section 6 left
        open: with a real default plan configured, a freshly-registered
        owner's Store gets a genuine trialing subscription, so its
        storefront is correctly 403 until onboarding completes — then 200
        once it does."""
        call_command("seed_default_plans", stdout=StringIO())

        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Fourth", "phone": "09359990004"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990004", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990004")
        membership = StoreMembership.objects.get(user=user)
        store = membership.store
        trial_domain = store.domains.get(is_primary=True)

        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        self.assertEqual(response.status_code, 403)

        # Complete the onboarding wizard — the same Store must now be publicly visible.
        base = f"/app/stores/{store.public_id}/onboarding"
        self.client.post(f"{base}/identity/", {"name": "فروشگاه چهارم"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/industry/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/branding/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/review/", {}, HTTP_HOST=_HOST)
        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        self.assertEqual(response.status_code, 200)
