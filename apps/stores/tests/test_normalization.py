from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase

from apps.stores.hostnames import build_cross_host_url, normalize_hostname


class NormalizeHostnameTests(SimpleTestCase):
    def test_lowercase_normalization(self):
        self.assertEqual(normalize_hostname("Shop.Example.COM"), "shop.example.com")

    def test_surrounding_whitespace_removed(self):
        self.assertEqual(normalize_hostname("  shop.example.com  "), "shop.example.com")

    def test_trailing_dot_removed(self):
        self.assertEqual(normalize_hostname("shop.example.com."), "shop.example.com")

    def test_combined_whitespace_case_and_trailing_dot(self):
        self.assertEqual(
            normalize_hostname(" Shop.Example.COM "), "shop.example.com"
        )

    def test_case_variants_normalize_to_the_same_value(self):
        self.assertEqual(
            normalize_hostname("SHOP.example.com"),
            normalize_hostname("shop.EXAMPLE.com"),
        )

    def test_trailing_dot_variants_normalize_to_the_same_value(self):
        self.assertEqual(
            normalize_hostname("shop.example.com"),
            normalize_hostname("shop.example.com."),
        )

    def test_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("https://shop.example.com")

    def test_scheme_http_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("http://shop.example.com")

    def test_path_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("shop.example.com/path")

    def test_query_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("shop.example.com?x=1")

    def test_fragment_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("shop.example.com#section")

    def test_port_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("shop.example.com:8000")

    def test_credentials_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("user:pass@shop.example.com")

    def test_empty_value_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("")

    def test_whitespace_only_value_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("   ")

    def test_none_value_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname(None)

    def test_malformed_label_leading_hyphen_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("-bad.example.com")

    def test_malformed_label_trailing_hyphen_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("bad-.example.com")

    def test_empty_label_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("shop..example.com")

    def test_single_label_without_dot_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_hostname("localhost")

    def test_label_exceeding_dns_limit_rejected(self):
        long_label = "a" * 64
        with self.assertRaises(ValidationError):
            normalize_hostname(f"{long_label}.example.com")

    def test_hostname_exceeding_total_length_rejected(self):
        # Build a syntactically valid but overlong hostname (> 253 chars).
        long_hostname = ".".join(["a" * 50] * 6) + ".com"
        self.assertGreater(len(long_hostname), 253)
        with self.assertRaises(ValidationError):
            normalize_hostname(long_hostname)

    def test_valid_hostname_accepted(self):
        self.assertEqual(normalize_hostname("shop.example.com"), "shop.example.com")

    def test_valid_hostname_with_subdomains_accepted(self):
        self.assertEqual(
            normalize_hostname("akhlaghi.stores.example.com"),
            "akhlaghi.stores.example.com",
        )

    def test_idna_unicode_domain_normalizes_to_ascii_compatible_form(self):
        # "مثال.example" (an Arabic-script label) must normalize to its
        # documented ASCII-compatible (Punycode) form so that it can be
        # compared/stored consistently — see hostnames.py module docstring
        # and SAAS_DOMAIN_DECISIONS.md ADR-4.
        result = normalize_hostname("مثال.example")
        self.assertTrue(result.startswith("xn--"))
        self.assertTrue(result.endswith(".example"))

    def test_idna_unicode_and_equivalent_punycode_normalize_identically(self):
        unicode_result = normalize_hostname("مثال.example")
        punycode_input = normalize_hostname("XN--MGBH0FB.example")
        self.assertEqual(unicode_result, punycode_input)

    def test_already_ascii_punycode_domain_round_trips(self):
        self.assertEqual(
            normalize_hostname("xn--mgbh0fb.example"), "xn--mgbh0fb.example"
        )


class CrossHostUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_preserves_explicit_non_default_http_port(self):
        request = self.factory.get("/", HTTP_HOST="shop.rastisi.localhost:8765")
        url = build_cross_host_url(request, hostname="rastisi.localhost", path="/login/")
        self.assertEqual(url, "http://rastisi.localhost:8765/login/")

    def test_omits_port_when_request_has_no_explicit_port(self):
        request = self.factory.get("/", HTTP_HOST="shop.rastisi.localhost")
        url = build_cross_host_url(request, hostname="rastisi.localhost", path="/app/")
        self.assertEqual(url, "http://rastisi.localhost/app/")

    def test_omits_explicit_default_https_port(self):
        request = self.factory.get("/", secure=True, HTTP_HOST="shop.rastisi.ir:443")
        url = build_cross_host_url(request, hostname="rastisi.ir", path="login/")
        self.assertEqual(url, "https://rastisi.ir/login/")
