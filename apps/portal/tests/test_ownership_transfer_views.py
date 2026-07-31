"""Section 15 — the owner-facing ownership transfer views: initiate
(step-up gated like purchase/handle-claim/domain-activate/deletion) and
the PUBLIC target-side accept flow, which is OTP-gated with the target's
OWN phone, not the initiator's session."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerProfile
from apps.stores.models import Store, StoreMembership, StoreOwnershipTransfer

User = get_user_model()
_HOST = "rastisi.localhost"


def _fixed_code(code):
    import apps.portal.services.owner_otp_service as svc

    original = svc._generate_code
    svc._generate_code = lambda: code
    return original


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnershipTransferViewsTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه انتقال ویو", slug="transfer-view-store", admin_subdomain="transfer-view-store",
            status=Store.Status.ACTIVE,
        )
        self.owner = User.objects.create_user(username="09121330011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121330011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        self.code = "667788"
        self._original_generate_code = _fixed_code(self.code)
        self.addCleanup(self._restore)

    def _restore(self):
        import apps.portal.services.owner_otp_service as svc
        svc._generate_code = self._original_generate_code

    def _url(self):
        return f"/app/stores/{self.store.public_id}/transfer/"


class InitiateTransferViewTests(OwnershipTransferViewsTestCase):
    def test_post_is_gated_behind_step_up_by_default(self):
        response = self.client.post(self._url(), {"target_phone": "09121330099"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/transfer/step-up/")
        self.assertFalse(StoreOwnershipTransfer.objects.filter(store=self.store).exists())

    def test_correct_step_up_code_creates_pending_transfer(self):
        self.client.post(self._url(), {"target_phone": "09121330099"}, HTTP_HOST=_HOST)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/transfer/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url())
        transfer = StoreOwnershipTransfer.objects.get(store=self.store)
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.PENDING)
        self.assertEqual(transfer.target_phone, "09121330099")

    def test_other_owner_cannot_initiate_for_someone_elses_store(self):
        other = User.objects.create_user(username="09121330022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)


class CancelTransferViewTests(OwnershipTransferViewsTestCase):
    def _create_pending(self):
        self.client.post(self._url(), {"target_phone": "09121330099"}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/transfer/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )

    def test_cancel_does_not_require_step_up(self):
        self._create_pending()
        response = self.client.post(f"/app/stores/{self.store.public_id}/transfer/cancel/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url())
        transfer = StoreOwnershipTransfer.objects.get(store=self.store)
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.CANCELLED)


class AcceptTransferViewTests(OwnershipTransferViewsTestCase):
    def _create_pending(self, target_phone="09121330099"):
        self.client.post(self._url(), {"target_phone": target_phone}, HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/transfer/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        return StoreOwnershipTransfer.objects.get(store=self.store)

    def test_unknown_token_404s(self):
        response = self.client.get("/transfer/accept/not-a-real-token/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_get_renders_accept_page(self):
        transfer = self._create_pending()
        response = self.client.get(f"/transfer/accept/{transfer.token}/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.store.name)

    def test_full_accept_flow_transfers_ownership_and_logs_in_the_new_owner(self):
        transfer = self._create_pending()
        target_code = "112233"
        import apps.portal.services.owner_otp_service as svc
        svc._generate_code = lambda: target_code

        # New client — the target is a different person/browser.
        target_client = self.client_class()
        target_client.post(
            f"/transfer/accept/{transfer.token}/", {"action": "request_code"}, HTTP_HOST=_HOST,
        )
        response = target_client.post(
            f"/transfer/accept/{transfer.token}/", {"action": "verify_code", "code": target_code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", target_client.session)

        new_owner = User.objects.get(username="09121330099")
        self.assertEqual(int(target_client.session["_auth_user_id"]), new_owner.pk)

        membership = StoreMembership.objects.get(store=self.store, user=new_owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.owner_membership = StoreMembership.objects.get(store=self.store, user=self.owner)
        self.assertEqual(self.owner_membership.role, StoreMembership.Role.ADMINISTRATOR)

    def test_wrong_code_does_not_transfer(self):
        transfer = self._create_pending()
        target_client = self.client_class()
        target_client.post(f"/transfer/accept/{transfer.token}/", {"action": "request_code"}, HTTP_HOST=_HOST)
        target_client.post(
            f"/transfer/accept/{transfer.token}/", {"action": "verify_code", "code": "000000"}, HTTP_HOST=_HOST,
        )
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.PENDING)
        self.assertFalse(User.objects.filter(username="09121330099").exists())
