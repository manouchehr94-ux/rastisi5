"""Section 14 — the owner-facing deletion request flow: typed confirmation
+ step-up OTP (gated exactly like purchase/handle-claim/domain-activate),
plus a no-step-up-needed cancellation."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerProfile
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StoreDeletionViewsTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه حذف ویو", slug="deletion-view-store", admin_subdomain="deletion-view-store",
            status=Store.Status.ACTIVE,
        )
        self.owner = User.objects.create_user(username="09121310011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121310011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        self.code = "445566"
        import apps.portal.services.owner_otp_service as svc
        self._original_generate_code = svc._generate_code
        svc._generate_code = lambda: self.code
        self.addCleanup(self._restore)

    def _restore(self):
        import apps.portal.services.owner_otp_service as svc
        svc._generate_code = self._original_generate_code

    def _url(self):
        return f"/app/stores/{self.store.public_id}/delete/"


class RequestDeletionViewTests(StoreDeletionViewsTestCase):
    def test_get_renders_form(self):
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.store.slug)

    def test_post_is_gated_behind_step_up_by_default(self):
        response = self.client.post(
            self._url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/delete/step-up/")
        self.store.refresh_from_db()
        self.assertIsNone(self.store.deletion_requested_at)

    def test_correct_step_up_code_requests_deletion(self):
        self.client.post(self._url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/delete/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url())
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.deletion_requested_at)
        self.assertEqual(self.store.status, Store.Status.CLOSED)

    def test_wrong_typed_confirmation_never_deletes_even_after_correct_otp(self):
        self.client.post(self._url(), {"typed_confirmation": "totally-wrong"}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/delete/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.store.refresh_from_db()
        self.assertIsNone(self.store.deletion_requested_at)
        self.assertEqual(self.store.status, Store.Status.ACTIVE)

    def test_other_owner_cannot_request_deletion_of_someone_elses_store(self):
        other = User.objects.create_user(username="09121310022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)


class CancelDeletionViewTests(StoreDeletionViewsTestCase):
    def _request_deletion(self):
        self.client.post(self._url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/delete/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )

    def test_cancel_does_not_require_step_up(self):
        self._request_deletion()
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/delete/cancel/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url())
        self.store.refresh_from_db()
        self.assertIsNone(self.store.deletion_requested_at)
        self.assertEqual(self.store.status, Store.Status.ACTIVE)

    def test_cancel_without_a_pending_request_shows_an_error(self):
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/delete/cancel/", HTTP_HOST=_HOST, follow=True,
        )
        self.assertContains(response, "وجود ندارد")
