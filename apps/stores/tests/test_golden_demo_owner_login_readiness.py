"""G2.1 Defect A — the Golden Demo store must be login-ready by default.

The demo seed previously created NO owner user/membership unless an operator
passed ``--owner-username <existing user>``. So after ``apply_golden_reference_storefront``
(which runs the seed WITHOUT that flag) there was no way to log into the central
portal as the demo owner and hand off to the store's admin-portal.

These tests assert the seed now provisions a deterministic, central-login-ready
demo owner:
  - a User with the demo email and a usable password,
  - an OwnerProfile (so both email- and phone-identifier central login resolve),
  - an OWNER + ACTIVE StoreMembership for rasti-mode-demo,
  - central owner authentication by email+password succeeds and resolves to that user,
  - the user's ACTIVE OWNER membership is visible for the /app/ handoff flow.

Central-auth CONTRACT is NOT changed — we only make the demo DATA satisfy it
(``authenticate_owner_by_identifier``: email path uses ``User.email``).
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings

from apps.portal.models import OwnerProfile
from apps.portal.services import owner_auth_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    DEMO_OWNER_EMAIL,
    DEMO_OWNER_PASSWORD,
    DEMO_OWNER_USERNAME,
    STORE_SLUG,
)
from apps.stores.models import Store, StoreMembership

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GoldenDemoOwnerLoginReadinessTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def _seed(self, *extra):
        call_command("seed_ready_template_fashion_demo", *extra, stdout=StringIO())

    def _store(self):
        return Store.objects.get(slug=STORE_SLUG)

    def test_seed_creates_the_demo_owner_user_with_email_and_usable_password(self):
        self._seed()
        user = User.objects.get(username=DEMO_OWNER_USERNAME)
        self.assertEqual(user.email, DEMO_OWNER_EMAIL)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(DEMO_OWNER_PASSWORD))
        self.assertTrue(OwnerProfile.objects.filter(user=user).exists())

    def test_seed_creates_owner_active_membership_for_the_demo_store(self):
        self._seed()
        user = User.objects.get(username=DEMO_OWNER_USERNAME)
        membership = StoreMembership.objects.get(store=self._store(), user=user)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_central_email_password_login_succeeds_and_resolves_the_demo_owner(self):
        self._seed()
        request = RequestFactory().post("/login/password/")
        user = owner_auth_service.authenticate_owner_by_identifier(
            request, identifier=DEMO_OWNER_EMAIL, password=DEMO_OWNER_PASSWORD
        )
        self.assertIsNotNone(user)
        self.assertEqual(user.username, DEMO_OWNER_USERNAME)

    def test_demo_owners_active_owner_membership_is_visible_for_handoff(self):
        # Mirrors the /app/ (app_home) + enter-admin membership query.
        self._seed()
        user = User.objects.get(username=DEMO_OWNER_USERNAME)
        memberships = StoreMembership.objects.filter(
            user=user, status=StoreMembership.MembershipStatus.ACTIVE
        ).select_related("store")
        self.assertTrue(memberships.filter(store=self._store(), role=StoreMembership.Role.OWNER).exists())

    def test_seed_is_idempotent_for_the_demo_owner(self):
        self._seed()
        self._seed()
        self.assertEqual(User.objects.filter(username=DEMO_OWNER_USERNAME).count(), 1)
        self.assertEqual(
            StoreMembership.objects.filter(store=self._store(), role=StoreMembership.Role.OWNER).count(), 1
        )

    def test_explicit_owner_username_still_overrides_the_default_demo_owner(self):
        existing = User.objects.create_user(username="explicit_owner", email="explicit@local.test", password="x")
        self._seed("--owner-username", "explicit_owner")
        membership = StoreMembership.objects.get(store=self._store(), user=existing)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
