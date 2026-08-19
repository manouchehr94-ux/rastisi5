import unittest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from urllib.parse import urlsplit

from apps.portal.models import AdminHandoffTicket
from apps.portal.services import handoff_service
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
_PORTAL_HOST = "rastisi.localhost"


def _handoff_target(url):
    """Return the HTTP_HOST value and path from an absolute handoff URL."""
    parsed = urlsplit(url)
    return parsed.netloc, parsed.path


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
        user, destination, _issued_by = result
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
    _PORTAL_HOST,
    "handoffstore.rastisi.ir",
    "otherstore.rastisi.ir",
    "handoffstore.rastisi.localhost",
    "otherstore.rastisi.localhost",
    "testserver",
])
class HandoffFullFlowViewTests(TestCase):
    def setUp(self):
        self.store = _make_store()
        self.owner = _make_owner(self.store)

    def test_enter_admin_requires_login(self):
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_enter_admin_preserves_current_non_default_port(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/enter-admin/",
            HTTP_HOST=f"{_PORTAL_HOST}:8765",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(
            f"http://handoffstore.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}:8765/admin-portal/handoff/"
        ))

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
        admin_host, path = _handoff_target(handoff_url)
        follow_response = admin_client.get(path, HTTP_HOST=admin_host)
        self.assertEqual(follow_response.status_code, 302)
        self.assertEqual(follow_response["Location"], "/admin-portal/")
        self.assertIn("_auth_user_id", admin_client.session)
        self.assertEqual(int(admin_client.session["_auth_user_id"]), self.owner.pk)

    def test_next_param_carries_a_deeper_admin_destination(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/enter-admin/",
            {"next": "/admin-portal/billing/"}, HTTP_HOST=_PORTAL_HOST,
        )
        handoff_url = response["Location"]
        admin_client = self.client_class()
        admin_host, path = _handoff_target(handoff_url)
        follow_response = admin_client.get(path, HTTP_HOST=admin_host)
        self.assertEqual(follow_response["Location"], "/admin-portal/billing/")

    def test_next_param_outside_admin_portal_is_ignored(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/enter-admin/",
            {"next": "https://evil.example.com/"}, HTTP_HOST=_PORTAL_HOST,
        )
        handoff_url = response["Location"]
        admin_client = self.client_class()
        admin_host, path = _handoff_target(handoff_url)
        follow_response = admin_client.get(path, HTTP_HOST=admin_host)
        self.assertEqual(follow_response["Location"], "/admin-portal/")

    def test_handoff_link_cannot_be_reused(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        handoff_url = response["Location"]
        admin_host, path = _handoff_target(handoff_url)

        first = self.client_class().get(path, HTTP_HOST=admin_host)
        self.assertEqual(first.status_code, 302)
        second = self.client_class().get(path, HTTP_HOST=admin_host)
        self.assertEqual(second.status_code, 404)

    def test_handoff_link_rejected_on_a_different_stores_admin_host(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST)
        handoff_url = response["Location"]
        token = handoff_url.rstrip("/").rsplit("/", 1)[-1]

        wrong_admin_host = f"otherstore.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        wrong_host_response = self.client_class().get(
            f"/admin-portal/handoff/{token}/", HTTP_HOST=wrong_admin_host,
        )
        self.assertEqual(wrong_host_response.status_code, 404)


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "reproduces a PostgreSQL-only row-locking restriction that SQLite (the "
    "default local/test backend) silently ignores; run with "
    "DATABASE_URL=postgres://... python manage.py test apps.portal.tests.test_handoff "
    "to actually exercise it.",
)
class ConsumeTicketPostgresProductionParityTests(TestCase):
    """Regression test for the production HTTP 500 on cross-host admin
    handoff (Issue 4).

    Root cause: ``handoff_service.consume_ticket`` used
    ``select_for_update()`` together with
    ``select_related("issued_by_platform_admin")`` — a *nullable*
    ForeignKey, so ``select_related`` turns that join into a LEFT OUTER
    JOIN. PostgreSQL refuses ``SELECT ... FOR UPDATE`` across the nullable
    side of an outer join and raises
    ``django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to
    the nullable side of an outer join`` — an unhandled 500 for every
    single handoff attempt in production. SQLite (this test suite's
    default backend) has no such restriction, which is exactly why this
    was invisible until it hit production Postgres.

    Uses a realistic generated fallback ``admin_subdomain``
    (``store-c535b10c9246``, the same shape ``Store._fallback_admin_subdomain``
    produces from a ``public_id``) and the matching production-style host
    ``store-c535b10c9246.rastisi.ir``, exactly as seen in production.
    """

    def setUp(self):
        self.store = Store.objects.create(
            name="Handoff PG Store", slug="handoff-pg-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
            admin_subdomain="store-c535b10c9246",
        )
        self.owner = _make_owner(self.store, email="pgowner@example.com")

    def test_consume_ticket_does_not_raise_notsupportederror_on_postgres(self):
        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        # Before the fix, this raised django.db.utils.NotSupportedError on
        # PostgreSQL instead of returning a result.
        result = handoff_service.consume_ticket(ticket.token, store=self.store)
        self.assertIsNotNone(result)
        user, destination_path, issued_by_platform_admin = result
        self.assertEqual(user, self.owner)
        self.assertEqual(destination_path, "/admin-portal/")
        self.assertIsNone(issued_by_platform_admin)

    def test_full_handoff_flow_succeeds_on_realistic_generated_admin_host(self):
        admin_host = f"store-c535b10c9246.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        with override_settings(ALLOWED_HOSTS=[_PORTAL_HOST, admin_host, "testserver"]):
            self.client.force_login(self.owner)
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/enter-admin/", HTTP_HOST=_PORTAL_HOST,
            )
            self.assertEqual(response.status_code, 302)
            handoff_url = response["Location"]
            self.assertIn(admin_host, handoff_url)

            admin_client = self.client_class()
            resolved_host, path = _handoff_target(handoff_url)
            # Before the fix, this 500'd with an unhandled NotSupportedError
            # instead of redirecting.
            follow_response = admin_client.get(path, HTTP_HOST=resolved_host)
            self.assertEqual(follow_response.status_code, 302)
            self.assertEqual(follow_response["Location"], "/admin-portal/")
            self.assertIn("_auth_user_id", admin_client.session)
            self.assertEqual(int(admin_client.session["_auth_user_id"]), self.owner.pk)
