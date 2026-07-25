from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.resolution import (
    AKHLAGHI_SLUG,
    CompatibilityFallbackUnavailableError,
    IneligibleStoreDomainError,
    InvalidHostnameError,
    StoreNotResolvedError,
    UnknownStoreDomainError,
    _strip_port,
    domain_is_eligible_for_routing,
    require_resolved_store,
    resolve_store_for_hostname,
    resolve_store_for_hostname_or_none,
    resolve_store_for_request,
)


class StripPortTests(SimpleTestCase):
    def test_removes_port_from_plain_host(self):
        self.assertEqual(_strip_port("shop.example.com:8080"), "shop.example.com")

    def test_no_port_is_unchanged(self):
        self.assertEqual(_strip_port("shop.example.com"), "shop.example.com")

    def test_bracketed_ipv6_with_port(self):
        self.assertEqual(_strip_port("[::1]:8000"), "[::1]")

    def test_bracketed_ipv6_without_port(self):
        self.assertEqual(_strip_port("[::1]"), "[::1]")

    def test_empty_string(self):
        self.assertEqual(_strip_port(""), "")

    def test_none_input(self):
        self.assertEqual(_strip_port(None), "")


def _make_verified_domain(store, hostname, is_primary=True):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=is_primary,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


class ResolveStoreForHostnameNormalizationTests(TestCase):
    """Normalization + lookup: resolve_store_for_hostname must reach the
    same StoreDomain row for every equivalent representation of one host."""

    def setUp(self):
        self.store = Store.objects.create(
            name="Shop", slug="shop-a", status=Store.Status.ACTIVE
        )
        self.domain = _make_verified_domain(self.store, "shop.example.com")

    def test_uppercase_hostname_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("SHOP.EXAMPLE.COM").pk, self.store.pk
        )

    def test_trailing_dot_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com.").pk, self.store.pk
        )

    def test_hostname_with_port_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com:8080").pk, self.store.pk
        )

    def test_mixed_case_whitespace_and_port_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname(" Shop.Example.COM:443 ").pk, self.store.pk
        )

    def test_idna_unicode_input_resolves_the_punycode_domain(self):
        store = Store.objects.create(name="IDN Store", slug="idn-store", status=Store.Status.ACTIVE)
        _make_verified_domain(store, "xn--mgbh0fb.example")
        self.assertEqual(resolve_store_for_hostname("مثال.example").pk, store.pk)

    def test_malformed_url_like_input_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("https://shop.example.com/path")

    def test_input_with_query_string_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("shop.example.com?x=1")

    def test_input_with_credentials_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("user:pass@shop.example.com")

    def test_malformed_label_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("-bad.example.com")

    def test_empty_host_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("")


class EligibilityTests(TestCase):
    """A StoreDomain must resolve only when both the domain is VERIFIED and
    its Store is ACTIVE — every other combination fails closed."""

    def setUp(self):
        self.store = Store.objects.create(
            name="Shop", slug="shop-a", status=Store.Status.ACTIVE
        )

    def test_verified_domain_and_active_store_resolves(self):
        _make_verified_domain(self.store, "shop.example.com")
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com").pk, self.store.pk
        )

    def test_domain_is_eligible_for_routing_true_case(self):
        domain = _make_verified_domain(self.store, "shop.example.com")
        self.assertTrue(domain_is_eligible_for_routing(domain))

    def test_unverified_domain_does_not_resolve(self):
        StoreDomain.objects.create(store=self.store, hostname="shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_pending_domain_does_not_resolve(self):
        StoreDomain.objects.create(
            store=self.store,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
            verification_token="pending-token",
        )
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_failed_domain_does_not_resolve(self):
        StoreDomain.objects.create(
            store=self.store,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.FAILED,
        )
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_suspended_store_does_not_resolve(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_closed_store_does_not_resolve(self):
        self.store.status = Store.Status.CLOSED
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_provisioning_store_does_not_resolve(self):
        self.store.status = Store.Status.PROVISIONING
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_unknown_hostname_raises_unknown_not_ineligible(self):
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("totally-unregistered-host.example")


class CompatibilityModeTests(TestCase):
    """The temporary, narrow Akhlaghi compatibility fallback.

    The Akhlaghi Store already exists in every test's starting database
    state — it is created by the ``stores.0002_create_akhlaghi_store`` data
    migration when the test database itself is built (verified: it is not
    created fresh per test). These tests use that existing row via
    ``_akhlaghi()`` rather than creating a second, colliding one.
    """

    def _akhlaghi(self, status=Store.Status.ACTIVE):
        store = Store.objects.get(slug=AKHLAGHI_SLUG)
        if store.status != status:
            store.status = status
            store.save(update_fields=["status"])
        return store

    def test_localhost_resolves_to_akhlaghi_when_sole_active_store(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("localhost").pk, akhlaghi.pk)

    def test_127_0_0_1_resolves_under_the_same_condition(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("127.0.0.1").pk, akhlaghi.pk)

    def test_bracketed_ipv6_localhost_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("[::1]").pk, akhlaghi.pk)

    def test_django_test_host_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("testserver").pk, akhlaghi.pk)

    def test_localhost_with_port_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("localhost:8000").pk, akhlaghi.pk)

    def test_arbitrary_unknown_public_hostname_does_not_fallback(self):
        self._akhlaghi()
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("some-random-public-host.example")

    def test_fallback_refused_when_a_second_store_exists(self):
        self._akhlaghi()
        Store.objects.create(name="Second", slug="second-store", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")
        self.assertIsNone(resolve_store_for_hostname_or_none("localhost"))

    def test_fallback_refused_if_sole_store_is_not_akhlaghi(self):
        Store.objects.filter(slug=AKHLAGHI_SLUG).delete()
        Store.objects.create(name="Not Akhlaghi", slug="not-akhlaghi", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_if_akhlaghi_is_not_active(self):
        self._akhlaghi(status=Store.Status.SUSPENDED)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_when_no_store_exists_at_all(self):
        Store.objects.all().delete()
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    @override_settings(STORES_DEVELOPMENT_HOST_ALLOWLIST={"custom-dev-host"})
    def test_development_allowlist_is_overridable_via_setting(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(
            resolve_store_for_hostname("custom-dev-host").pk, akhlaghi.pk
        )
        # And the default list is no longer active once overridden: "localhost"
        # has no dot, so once it isn't treated as a dev-compat host it fails
        # hostname *syntax* validation outright (never reaches the StoreDomain
        # lookup at all) — proving it was only ever resolvable via the
        # explicitly isolated compatibility path, never as a "real" hostname.
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("localhost")


class ResolveStoreForHostnameOrNoneTests(TestCase):
    def test_returns_none_instead_of_raising(self):
        self.assertIsNone(resolve_store_for_hostname_or_none("https://bad"))
        self.assertIsNone(resolve_store_for_hostname_or_none("unknown-host.example"))


class RequireResolvedStoreTests(SimpleTestCase):
    class _FakeRequest:
        def __init__(self, store=None):
            if store is not None:
                self.store = store

    def test_raises_when_store_attribute_absent(self):
        with self.assertRaises(StoreNotResolvedError):
            require_resolved_store(self._FakeRequest())

    def test_raises_when_store_is_none(self):
        with self.assertRaises(StoreNotResolvedError):
            require_resolved_store(self._FakeRequest(store=None))

    def test_returns_store_when_resolved(self):
        sentinel = object()
        self.assertIs(require_resolved_store(self._FakeRequest(store=sentinel)), sentinel)


@override_settings(ALLOWED_HOSTS=["a.example.com", "b.example.com"])
class IsolationAdversarialTests(TestCase):
    """Store A's hostname must never resolve Store B, and nothing but the
    Host header may influence resolution.

    ALLOWED_HOSTS is overridden for this class because ``resolve_store_for_request``
    goes through ``request.get_host()``, which is Django's own Host-header
    validation — with the project's default ``ALLOWED_HOSTS = []`` and
    ``DEBUG = True``, only localhost/127.0.0.1/[::1] pass that check, so
    arbitrary test hostnames must be explicitly allowed here.
    """

    def setUp(self):
        self.store_a = Store.objects.create(name="Store A", slug="store-a", status=Store.Status.ACTIVE)
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        self.domain_a = _make_verified_domain(self.store_a, "a.example.com")
        self.domain_b = _make_verified_domain(self.store_b, "b.example.com")

    def test_store_a_hostname_never_resolves_store_b(self):
        resolved = resolve_store_for_hostname("a.example.com")
        self.assertEqual(resolved.pk, self.store_a.pk)
        self.assertNotEqual(resolved.pk, self.store_b.pk)

    def test_store_b_hostname_never_resolves_store_a(self):
        resolved = resolve_store_for_hostname("b.example.com")
        self.assertEqual(resolved.pk, self.store_b.pk)
        self.assertNotEqual(resolved.pk, self.store_a.pk)

    def test_duplicate_hostname_across_stores_is_impossible(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(store=self.store_b, hostname="a.example.com")

    def test_request_headers_other_than_host_do_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(
            "/", HTTP_HOST="a.example.com", HTTP_X_FORWARDED_FOR="b.example.com",
            HTTP_X_STORE_ID=str(self.store_b.pk),
        )
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_query_parameters_do_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/?store={self.store_b.pk}", HTTP_HOST="a.example.com")
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_url_path_does_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/stores/{self.store_b.slug}/", HTTP_HOST="a.example.com")
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_session_values_do_not_affect_resolution(self):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="a.example.com")
        request.session = SessionStore()
        request.session["store_id"] = self.store_b.pk
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)


@override_settings(ALLOWED_HOSTS=["a.example.com", "unknown-public-host.example"])
class QueryCountTests(TestCase):
    """Empirically pins the query counts reported for this PR: one bounded
    query for a matched domain, one bounded query for the compatibility
    fallback, one query for an unknown host, and zero queries for an
    invalid host (which fails before any database access)."""

    def setUp(self):
        self.store = Store.objects.create(name="Store A", slug="store-a", status=Store.Status.ACTIVE)
        _make_verified_domain(self.store, "a.example.com")

    def test_matched_verified_domain_is_one_query(self):
        with self.assertNumQueries(1):
            resolve_store_for_hostname("a.example.com")

    def test_development_fallback_is_one_query(self):
        # Isolate to the sole-Store condition the fallback requires — undo
        # setUp's extra Store so only the seeded Akhlaghi Store remains.
        self.store.delete()
        with self.assertNumQueries(1):
            resolve_store_for_hostname("localhost")

    def test_unknown_public_host_is_one_query(self):
        with self.assertNumQueries(1):
            resolve_store_for_hostname_or_none("unknown-public-host.example")

    def test_invalid_hostname_is_zero_queries(self):
        with self.assertNumQueries(0):
            resolve_store_for_hostname_or_none("https://bad/path")
