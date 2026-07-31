from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.platform_code_service import generate_unique_platform_code


@override_settings(ALLOWED_HOSTS=["old.example.com", "new.example.com", "testserver"])
class HostnameRedirectMiddlewareTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Redirect Co", slug="redirect-co", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        self.primary = StoreDomain.objects.create(
            store=self.store, hostname="new.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.alias = StoreDomain.objects.create(
            store=self.store, hostname="old.example.com", is_primary=False, is_redirect=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_get_on_alias_hostname_redirects_permanently_to_primary(self):
        response = self.client.get("/", HTTP_HOST="old.example.com")
        self.assertEqual(response.status_code, 301)
        self.assertIn("new.example.com", response["Location"])

    def test_redirect_preserves_path_and_query(self):
        response = self.client.get("/some/path/?x=1", HTTP_HOST="old.example.com")
        self.assertEqual(response.status_code, 301)
        self.assertIn("new.example.com/some/path/?x=1", response["Location"])

    def test_post_on_alias_hostname_uses_308_not_301(self):
        response = self.client.post("/checkout/", {}, HTTP_HOST="old.example.com")
        self.assertEqual(response.status_code, 308)

    def test_primary_hostname_is_never_redirected(self):
        response = self.client.get("/", HTTP_HOST="new.example.com")
        self.assertNotIn(response.status_code, (301, 308))

    def test_unrelated_hostname_is_unaffected(self):
        response = self.client.get("/", HTTP_HOST="testserver")
        self.assertNotIn(response.status_code, (301, 308))
