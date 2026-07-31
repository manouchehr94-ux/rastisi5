from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import AdminHandoffTicket
from apps.portal.services import handoff_service
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
_PORTAL_HOST = "rastisi.localhost"


def _make_store(admin_subdomain="handoffstore"):
    return Store.objects.create(
        name="Handoff Store", slug=f"handoff-store-{admin_subdomain}", status=Store.Status.ACTIVE,
        platform_code=generate_unique_platform_code(), admin_subdomain=admin_subdomain,
    )


def _make_owner(store, email="owner@example.com"):
    user = User.objects.create_user(username=email, email=email, password="a-very-strong-pass-1", is_staff=True)
    StoreMembership.objects.create(
        store=store, user=user, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )
    return user


class IssueTicketTests(TestCase):
    def setUp(self):
        self.store = _make_store()
        self.owner = _make_owner(self.store)

    def test_issues_ticket_for_active_member(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        self.assertEqual(ticket.store, self.store)
        self.assertEqual(ticket.user, self.owner)
        self.assertTrue(ticket.is_usable)

    def test_refuses_ticket_for_non_member(self):
        outsider = User.objects.create_user(
            username="outsider@example.com", email="outsider@example.com", password="a-very-strong-pass-1",
        )
        with self.assertRaises(handoff_service.HandoffError):
            handoff_service.issue_ticket(user=outsider, store=self.store)


class ConsumeTicketTests(TestCase):
    def setUp(self):
        self.store = _make_store()
        self.owner = _make_owner(self.store)
        self.other_store = _make_store(admin_subdomain="otherstore")

    def test_consume_returns_user_and_destination_once(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        result = handoff_service.consume_ticket(ticket.token, store=self.store)
        self.assertIsNotNone(result)
        user, destination = result
        self.assertEqual(user, self.owner)
        self.assertEqual(destination, "/admin-portal/")

    def test_consume_twice_fails_the_second_time(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        handoff_service.consume_ticket(ticket.token, store=self.store)
        second = handoff_service.consume_ticket(ticket.token, store=self.store)
        self.assertIsNone(second)

    def test_consume_for_wrong_store_fails(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        result = handoff_service.consume_ticket(ticket.token, store=self.other_store)
        self.assertIsNone(result)
        # the ticket must remain usable against its real store afterward
        self.assertIsNotNone(handoff_service.consume_ticket(ticket.token, store=self.store))

    def test_consume_expired_ticket_fails(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        ticket.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        ticket.save(update_fields=["expires_at"])
        result = handoff_service.consume_ticket(ticket.token, store=self.store)
        self.assertIsNone(result)

    def test_bogus_token_fails(self):
        self.assertIsNone(handoff_service.consume_ticket("not-a-real-token", store=self.store))


@override_settings(ALLOWED_HOSTS=[
    _PORTAL_HOST, "handoffstore.rastisi.ir", "otherstore.rastisi.ir", "testserver",
])
class HandoffFullFlowViewTests(TestCase):
    def setUp(self):
        self.store = _make_store()
        self.owner = _make_owner(self.store)

    def test_enter_admin_requires_login(self):
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_enter_admin_get_is_not_allowed(self):
        self.client.force_login(self.owner)
        response = self.client.get(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 405)

    def test_enter_admin_for_foreign_store_404s(self):
        outsider = User.objects.create_user(
            username="outsider2@example.com", email="outsider2@example.com", password="a-very-strong-pass-1",
        )
        self.client.force_login(outsider)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 404)

    def test_full_handoff_logs_owner_into_admin_host(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 302)
        handoff_url = response["Location"]
        self.assertIn(f"handoffstore.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}", handoff_url)

        # Follow the handoff link with a FRESH client (no portal session/cookies
        # carried over) — this is the entire point of the handoff mechanism.
        admin_client = self.client_class()
        admin_host = handoff_url.split("://", 1)[1].split("/", 1)[0]
        path = "/" + handoff_url.split("://", 1)[1].split("/", 1)[1]
        follow_response = admin_client.get(path, HTTP_HOST=admin_host)
        self.assertEqual(follow_response.status_code, 302)
        self.assertEqual(follow_response["Location"], "/admin-portal/")
        self.assertIn("_auth_user_id", admin_client.session)
        self.assertEqual(int(admin_client.session["_auth_user_id"]), self.owner.pk)

    def test_handoff_link_cannot_be_reused(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        handoff_url = response["Location"]
        admin_host = handoff_url.split("://", 1)[1].split("/", 1)[0]
        path = "/" + handoff_url.split("://", 1)[1].split("/", 1)[1]

        first = self.client_class().get(path, HTTP_HOST=admin_host)
        self.assertEqual(first.status_code, 302)
        second = self.client_class().get(path, HTTP_HOST=admin_host)
        self.assertEqual(second.status_code, 404)

    def test_handoff_link_rejected_on_a_different_stores_admin_host(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        handoff_url = response["Location"]
        token = handoff_url.rstrip("/").rsplit("/", 1)[-1]

        wrong_host_response = self.client_class().get(
            f"/admin-portal/handoff/{token}/", HTTP_HOST="otherstore.rastisi.ir",
        )
        self.assertEqual(wrong_host_response.status_code, 404)
