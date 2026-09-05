"""G2.1 (hardened) — the Golden Demo owner is provisioned ONLY via the explicit
``--owner-username`` contract, and the seed NEVER creates a credentialed owner
or mutates an existing user's authentication credentials.

Safe model:
  - ``seed_ready_template_fashion_demo`` WITHOUT ``--owner-username`` creates NO
    owner (no deterministic demo user, no hardcoded password).
  - WITH ``--owner-username <existing user>``: that user is resolved and given
    ONLY the OWNER StoreMembership for rasti-mode-demo; the seed does not change
    the user's password / email / phone / active state.
  - Central email+password login (an EXISTING, unchanged contract) works for a
    user the operator created explicitly with a real password/email + OwnerProfile.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings

from apps.portal.models import OwnerProfile
from apps.portal.services import owner_auth_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store, StoreMembership

User = get_user_model()

# A test-only owner the OPERATOR creates explicitly (never committed to source
# as a product default). Central login resolves an email identifier against
# User.email, so an email + usable password is sufficient.
TEST_OWNER_USERNAME = "local_demo_owner"
TEST_OWNER_EMAIL = "local-demo-owner@example.test"
TEST_OWNER_PASSWORD = "s3cure-Test-Pass!42"
TEST_OWNER_PHONE = "09121230099"


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

    def _make_explicit_owner(self):
        user = User.objects.create_user(
            username=TEST_OWNER_USERNAME, email=TEST_OWNER_EMAIL, password=TEST_OWNER_PASSWORD
        )
        OwnerProfile.objects.create(user=user, full_name="مالکِ محلی", phone=TEST_OWNER_PHONE)
        return user

    # --------------------------------------------------- explicit owner contract

    def test_explicit_owner_username_creates_owner_active_membership(self):
        owner = self._make_explicit_owner()
        self._seed("--owner-username", TEST_OWNER_USERNAME)
        membership = StoreMembership.objects.get(store=self._store(), user=owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_central_email_password_login_works_for_the_explicit_owner(self):
        self._make_explicit_owner()
        self._seed("--owner-username", TEST_OWNER_USERNAME)
        request = RequestFactory().post("/login/password/")
        user = owner_auth_service.authenticate_owner_by_identifier(
            request, identifier=TEST_OWNER_EMAIL, password=TEST_OWNER_PASSWORD
        )
        self.assertIsNotNone(user)
        self.assertEqual(user.username, TEST_OWNER_USERNAME)

    def test_seed_does_not_mutate_the_owners_credentials(self):
        owner = self._make_explicit_owner()
        password_hash_before = owner.password
        email_before = owner.email
        profile_phone_before = OwnerProfile.objects.get(user=owner).phone
        active_before = owner.is_active

        self._seed("--owner-username", TEST_OWNER_USERNAME)

        owner.refresh_from_db()
        self.assertEqual(owner.password, password_hash_before, "seed must not change the password")
        self.assertEqual(owner.email, email_before, "seed must not change the email")
        self.assertEqual(owner.is_active, active_before, "seed must not change active state")
        self.assertEqual(
            OwnerProfile.objects.get(user=owner).phone, profile_phone_before,
            "seed must not change the OwnerProfile phone",
        )
        # login still works with the ORIGINAL password (proves it is unchanged).
        self.assertTrue(owner.check_password(TEST_OWNER_PASSWORD))

    def test_explicit_owner_membership_is_visible_for_handoff(self):
        owner = self._make_explicit_owner()
        self._seed("--owner-username", TEST_OWNER_USERNAME)
        memberships = StoreMembership.objects.filter(
            user=owner, status=StoreMembership.MembershipStatus.ACTIVE
        ).select_related("store")
        self.assertTrue(memberships.filter(store=self._store(), role=StoreMembership.Role.OWNER).exists())

    def test_unknown_owner_username_raises_command_error(self):
        with self.assertRaises(CommandError):
            self._seed("--owner-username", "__no_such_user__")

    def test_explicit_owner_seed_is_idempotent_for_membership(self):
        self._make_explicit_owner()
        self._seed("--owner-username", TEST_OWNER_USERNAME)
        self._seed("--owner-username", TEST_OWNER_USERNAME)
        self.assertEqual(
            StoreMembership.objects.filter(store=self._store(), role=StoreMembership.Role.OWNER).count(), 1
        )

    # --------------------------------------------------- no auto-owner regression

    def test_seed_without_owner_username_creates_no_owner(self):
        self._seed()  # no --owner-username
        store = self._store()
        # No OWNER membership exists for the demo store.
        self.assertFalse(
            StoreMembership.objects.filter(store=store, role=StoreMembership.Role.OWNER).exists()
        )
        # The old deterministic demo user is NOT created.
        self.assertFalse(User.objects.filter(username="rasti_demo_admin").exists())
        self.assertFalse(User.objects.filter(email="rasti-demo-admin@local.test").exists())

    def test_no_hardcoded_demo_password_constant_is_exported(self):
        import apps.stores.management.commands.seed_ready_template_fashion_demo as seed_mod

        for name in ("DEMO_OWNER_PASSWORD", "DEMO_OWNER_USERNAME", "DEMO_OWNER_EMAIL", "DEMO_OWNER_PHONE"):
            self.assertFalse(
                hasattr(seed_mod, name),
                f"the seed module must not export {name} (no hardcoded demo owner/password)",
            )
