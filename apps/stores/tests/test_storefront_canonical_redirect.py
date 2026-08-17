from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.stores.middleware import StorefrontCanonicalRedirectMiddleware
from apps.stores.models import Store, StoreDomain


def _verified_domain(store, hostname, *, domain_type, is_primary):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        domain_type=domain_type,
        is_primary=is_primary,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(
    ALLOWED_HOSTS=["digilool.rastisi.ir", "digilool.ir", "testserver"],
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class StorefrontCanonicalRedirectMiddlewareUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.store = Store.objects.create(
            name="دیجی‌لول", slug="digilool-canonical",
            admin_subdomain="digilool", status=Store.Status.ACTIVE,
        )
        self.handle = _verified_domain(
            self.store, "digilool.rastisi.ir",
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=False,
        )
        self.custom = _verified_domain(
            self.store, "digilool.ir",
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            is_primary=True,
        )

    def _run(self, path="/", host="digilool.rastisi.ir"):
        seen = {"called": False}
        def get_response(_request):
            seen["called"] = True
            return HttpResponse("downstream")
        request = self.factory.get(path, HTTP_HOST=host)
        request.store = self.store
        response = StorefrontCanonicalRedirectMiddleware(get_response)(request)
        return response, seen["called"]

    def test_public_root_redirects_permanently_to_custom_domain(self):
        response, called = self._run("/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://digilool.ir/")
        self.assertFalse(called)

    def test_path_and_query_string_are_preserved(self):
        response, _ = self._run("/product/42/?color=blue&page=2")
        self.assertEqual(
            response["Location"],
            "https://digilool.ir/product/42/?color=blue&page=2",
        )

    def test_admin_portal_stays_on_rastisi_host(self):
        response, called = self._run("/admin-portal/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(called)

    def test_admin_portal_without_trailing_slash_stays_on_rastisi_host(self):
        response, called = self._run("/admin-portal")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(called)

    def test_admin_assets_stay_on_rastisi_host(self):
        for path in ("/static/css/base.css", "/media/example.jpg"):
            with self.subTest(path=path):
                response, called = self._run(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(called)

    def test_custom_domain_request_does_not_redirect(self):
        response, called = self._run("/", host="digilool.ir")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(called)

    def test_no_primary_custom_domain_means_no_redirect(self):
        self.custom.is_primary = False
        self.custom.save(update_fields=["is_primary", "updated_at"])
        response, called = self._run("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(called)

    def test_retired_platform_handle_does_not_redirect(self):
        self.handle.retired_at = timezone.now()
        self.handle.save(update_fields=["retired_at", "updated_at"])
        response, called = self._run("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(called)


@override_settings(
    ALLOWED_HOSTS=["digilool.rastisi.ir", "digilool.ir", "testserver"],
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class StorefrontCanonicalRedirectEndToEndTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="دیجی‌لول E2E", slug="digilool-canonical-e2e",
            admin_subdomain="digilool", status=Store.Status.ACTIVE,
        )
        _verified_domain(
            self.store, "digilool.rastisi.ir",
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=False,
        )
        _verified_domain(
            self.store, "digilool.ir",
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            is_primary=True,
        )

    def test_full_stack_public_request_is_301_before_storefront_view(self):
        response = Client().get(
            "/some-public-path/?x=1",
            HTTP_HOST="digilool.rastisi.ir",
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://digilool.ir/some-public-path/?x=1",
        )
