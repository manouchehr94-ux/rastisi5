from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services.handoff_service import build_admin_return_token, decode_admin_return_token
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
_PORTAL_HOST = "rastisi.localhost"


def _make_store(admin_subdomain="centrallogin"):
    return Store.objects.create(
        name="Central Login Store", slug=f"central-login-{admin_subdomain}", status=Store.Status.ACTIVE,
        platform_code=generate_unique_platform_code(), admin_subdomain=admin_subdomain,
    )


def _make_member(store, email="member@example.com"):
    user = User.objects.create_user(username=email, email=email, password="a-very-strong-pass-1", is_staff=True)
    StoreMembership.objects.create(
        store=store, user=user, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )
    return user


class AdminReturnTokenTests(TestCase):
    def test_round_trips(self):
        token = build_admin_return_token(admin_subdomain="somestore", destination_path="/admin-portal/orders/")
        decoded = decode_admin_return_token(token)
        self.assertEqual(decoded, ("somestore", "/admin-portal/orders/"))

    def test_tampered_token_is_rejected(self):
        token = build_admin_return_token(admin_subdomain="somestore", destination_path="/admin-portal/")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        self.assertIsNone(decode_admin_return_token(tampered))

    def test_destination_outside_admin_portal_is_rejected(self):
        # Defense in depth: even a validly-signed token pointing somewhere
        # other than /admin-portal/ is refused by the decoder itself.
        from django.core import signing

        signer = signing.TimestampSigner(salt="portal.admin_return_token")
        forged = signer.sign_object({"admin_subdomain": "somestore", "destination_path": "/evil/"})
        self.assertIsNone(decode_admin_return_token(forged))

    def test_garbage_token_is_rejected(self):
        self.assertIsNone(decode_admin_return_token("not-a-real-token"))


@override_settings(
    ALLOWED_HOSTS=[_PORTAL_HOST, "centrallogin.rastisi.ir", "testserver"],
    RASTISI_PLATFORM_PRIMARY_HOST=_PORTAL_HOST,
)
class UnauthenticatedAdminRequestRedirectsCentrallyTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit/step-up counters are cache-backed, not DB-backed — not reset by transaction rollback
        self.store = _make_store()

    def test_unauthenticated_dashboard_request_redirects_to_central_login(self):
        response = self.client.get("/admin-portal/", HTTP_HOST="centrallogin.rastisi.ir")
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertIn(_PORTAL_HOST, location)
        self.assertIn("/login/", location)
        self.assertIn("admin_return=", location)

    def test_redirect_never_points_at_the_old_local_admin_login_page(self):
        response = self.client.get("/admin-portal/", HTTP_HOST="centrallogin.rastisi.ir")
        self.assertNotIn("centrallogin.rastisi.ir/admin-portal/login", response["Location"])


@override_settings(
    ALLOWED_HOSTS=[_PORTAL_HOST, "centrallogin.rastisi.ir", "testserver"],
    RASTISI_PLATFORM_PRIMARY_HOST=_PORTAL_HOST,
)
class FullCentralLoginHandoffFlowTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit/step-up counters are cache-backed, not DB-backed — not reset by transaction rollback
        self.store = _make_store()
        self.member = _make_member(self.store)

    def _fixed_code(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "444555"
        self.addCleanup(setattr, svc, "_generate_code", original)
        return "444555"

    def test_full_flow_lands_back_on_the_original_admin_destination(self):
        # 1) Unauthenticated request to a real admin_subdomain page.
        first = self.client.get("/admin-portal/products/", HTTP_HOST="centrallogin.rastisi.ir")
        self.assertEqual(first.status_code, 302)
        central_login_url = first["Location"]

        # 2) Follow it to the central login page and request an OTP,
        # preserving admin_return through the form.
        query = central_login_url.split("?", 1)[1]
        code = self._fixed_code()
        self.client.post(f"/login/?{query}", {"phone": "09121234590"}, HTTP_HOST=_PORTAL_HOST)

        # register this phone to the SAME member account so it has an
        # active membership at the target store.
        from apps.portal.models import OwnerProfile

        OwnerProfile.objects.create(user=self.member, phone="09121234590")

        response = self.client.post("/verify/", {"phone": "09121234590", "code": code}, HTTP_HOST=_PORTAL_HOST)
        self.assertEqual(response.status_code, 302)
        handoff_url = response["Location"]
        self.assertIn("centrallogin.rastisi.ir", handoff_url)
        self.assertIn("/admin-portal/handoff/", handoff_url)

        # 3) Follow the handoff on a fresh client (no portal cookies).
        admin_client = self.client_class()
        path = "/" + handoff_url.split("://", 1)[1].split("/", 1)[1]
        final = admin_client.get(path, HTTP_HOST="centrallogin.rastisi.ir")
        self.assertEqual(final.status_code, 302)
        self.assertEqual(final["Location"], "/admin-portal/products/")
        self.assertIn("_auth_user_id", admin_client.session)

    def test_login_without_membership_at_target_store_shows_error_not_leak(self):
        code = self._fixed_code()
        token = build_admin_return_token(admin_subdomain="centrallogin", destination_path="/admin-portal/")
        self.client.post(f"/login/?admin_return={token}", {"phone": "09121234591"}, HTTP_HOST=_PORTAL_HOST)
        response = self.client.post(
            "/verify/", {"phone": "09121234591", "code": code}, HTTP_HOST=_PORTAL_HOST, follow=True,
        )
        # A brand-new, unrelated phone: no membership at "centrallogin" —
        # must never be silently handed off there. Ends up on the normal
        # onboarding/My-Stores path for their own new account instead.
        self.assertNotIn("centrallogin.rastisi.ir", response.redirect_chain[-1][0] if response.redirect_chain else "")
