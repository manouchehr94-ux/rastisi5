"""Unit tests for loadtest.safety — the hard target-host guard.

Plain unittest, zero Django/locust dependency (matches safety.py itself),
runnable via `python -m unittest loadtest.tests.test_safety` standalone,
or via `python manage.py test loadtest.tests` for consistency with the
rest of this repository's test conventions (Django's test runner
discovers any importable test*.py under the project root, not only
files inside INSTALLED_APPS).
"""

import unittest

from loadtest.safety import (
    UnsafeLoadTestTargetError,
    assert_host_allowed,
    extract_hostname,
    is_hard_blocked,
    is_host_allowed,
    parse_allowed_hosts,
    warn_if_suspicious_allowed_host,
)


class ExtractHostnameTests(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(extract_hostname("https://loadtest.example.internal:8443/path"), "loadtest.example.internal")

    def test_bare_host_port(self):
        self.assertEqual(extract_hostname("127.0.0.1:8000"), "127.0.0.1")

    def test_bare_hostname(self):
        self.assertEqual(extract_hostname("rastisi.ir"), "rastisi.ir")

    def test_uppercase_normalized(self):
        self.assertEqual(extract_hostname("HTTPS://Rastisi.IR"), "rastisi.ir")

    def test_trailing_dot_stripped(self):
        self.assertEqual(extract_hostname("rastisi.ir."), "rastisi.ir")

    def test_empty_input(self):
        self.assertEqual(extract_hostname(""), "")
        self.assertEqual(extract_hostname(None), "")


class HardBlockTests(unittest.TestCase):
    def test_exact_production_domain_blocked(self):
        self.assertTrue(is_hard_blocked("rastisi.ir"))

    def test_www_subdomain_blocked(self):
        self.assertTrue(is_hard_blocked("www.rastisi.ir"))

    def test_platform_admin_subdomain_blocked(self):
        self.assertTrue(is_hard_blocked("platformadmins.rastisi.ir"))

    def test_arbitrary_merchant_subdomain_blocked(self):
        self.assertTrue(is_hard_blocked("some-real-merchant.rastisi.ir"))

    def test_deeply_nested_subdomain_blocked(self):
        self.assertTrue(is_hard_blocked("a.b.c.rastisi.ir"))

    def test_lookalike_domain_not_blocked(self):
        """rastisi.ir as a *substring* of a totally different domain must
        NOT be treated as the production domain — only an exact match or
        genuine subdomain relationship counts."""
        self.assertFalse(is_hard_blocked("rastisi.ir.evil.com"))
        self.assertFalse(is_hard_blocked("notrastisi.ir"))
        self.assertFalse(is_hard_blocked("rastisi.irrelevant.com"))

    def test_unrelated_domain_not_blocked(self):
        self.assertFalse(is_hard_blocked("loadtest.example.internal"))

    def test_empty_hostname_not_blocked_but_also_not_allowed_elsewhere(self):
        # is_hard_blocked("") is False by contract, but callers must never
        # treat that as "safe" — extract_hostname("") already guards this
        # at the assert_host_allowed level (see AssertHostAllowedTests).
        self.assertFalse(is_hard_blocked(""))


class ParseAllowedHostsTests(unittest.TestCase):
    def test_empty_or_none_returns_empty(self):
        self.assertEqual(parse_allowed_hosts(""), frozenset())
        self.assertEqual(parse_allowed_hosts(None), frozenset())

    def test_comma_separated_parsed_and_normalized(self):
        result = parse_allowed_hosts("Loadtest.Example.Internal, 127.0.0.1 ,staging.example.com")
        self.assertEqual(result, frozenset({"loadtest.example.internal", "127.0.0.1", "staging.example.com"}))

    def test_blank_entries_dropped(self):
        self.assertEqual(parse_allowed_hosts("a.example.com,,b.example.com,"), frozenset({"a.example.com", "b.example.com"}))

    def test_production_domain_silently_dropped_even_if_operator_lists_it(self):
        """Defense in depth: even if an operator mistakenly puts rastisi.ir
        in LOADTEST_ALLOWED_HOSTS, it never appears in the parsed set."""
        result = parse_allowed_hosts("rastisi.ir,loadtest.example.internal,evil.rastisi.ir")
        self.assertEqual(result, frozenset({"loadtest.example.internal"}))


class IsHostAllowedTests(unittest.TestCase):
    def test_exact_match_allowed(self):
        self.assertTrue(is_host_allowed("https://loadtest.example.internal/", frozenset({"loadtest.example.internal"})))

    def test_subdomain_of_allowed_entry_allowed(self):
        self.assertTrue(is_host_allowed("https://store1.loadtest.example.internal/", frozenset({"loadtest.example.internal"})))

    def test_unrelated_host_not_in_allowlist_denied(self):
        self.assertFalse(is_host_allowed("https://other.example.com/", frozenset({"loadtest.example.internal"})))

    def test_empty_allowlist_denies_everything(self):
        self.assertFalse(is_host_allowed("https://loadtest.example.internal/", frozenset()))

    def test_production_domain_denied_even_with_matching_allowlist_entry(self):
        """The hard block always wins — even a (hypothetically corrupted)
        allowed_hosts set containing rastisi.ir must still deny it. This
        exercises is_host_allowed() directly with a deliberately unsafe
        frozenset that parse_allowed_hosts() itself would never produce,
        to prove the hard-block check is not solely relied upon at the
        parsing layer."""
        unsafe_allowlist = frozenset({"rastisi.ir"})
        self.assertFalse(is_host_allowed("https://rastisi.ir/", unsafe_allowlist))

    def test_subdomain_of_production_domain_denied_even_with_matching_allowlist(self):
        unsafe_allowlist = frozenset({"rastisi.ir"})
        self.assertFalse(is_host_allowed("https://evil.rastisi.ir/", unsafe_allowlist))


class AssertHostAllowedTests(unittest.TestCase):
    def test_raises_for_production_domain(self):
        with self.assertRaises(UnsafeLoadTestTargetError):
            assert_host_allowed("https://rastisi.ir/", frozenset({"rastisi.ir"}))

    def test_raises_for_production_subdomain(self):
        with self.assertRaises(UnsafeLoadTestTargetError):
            assert_host_allowed("https://checkout.rastisi.ir/", frozenset())

    def test_raises_when_allowlist_empty(self):
        with self.assertRaises(UnsafeLoadTestTargetError):
            assert_host_allowed("https://loadtest.example.internal/", frozenset())

    def test_raises_when_host_not_in_nonempty_allowlist(self):
        with self.assertRaises(UnsafeLoadTestTargetError):
            assert_host_allowed("https://not-listed.example.com/", frozenset({"loadtest.example.internal"}))

    def test_raises_when_target_has_no_extractable_hostname(self):
        with self.assertRaises(UnsafeLoadTestTargetError):
            assert_host_allowed("", frozenset({"loadtest.example.internal"}))

    def test_passes_silently_for_allowed_host(self):
        assert_host_allowed("https://loadtest.example.internal/", frozenset({"loadtest.example.internal"}))  # no raise

    def test_error_message_mentions_hostname_and_reason(self):
        try:
            assert_host_allowed("https://rastisi.ir/", frozenset())
        except UnsafeLoadTestTargetError as exc:
            self.assertIn("rastisi.ir", str(exc))
            self.assertIn("production", str(exc).lower())
        else:
            self.fail("expected UnsafeLoadTestTargetError")


class WarnIfSuspiciousAllowedHostTests(unittest.TestCase):
    def test_no_warning_for_obvious_test_host(self):
        self.assertIsNone(warn_if_suspicious_allowed_host("loadtest.example.internal"))
        self.assertIsNone(warn_if_suspicious_allowed_host("staging.example.com"))
        self.assertIsNone(warn_if_suspicious_allowed_host("store1.rastisi.localhost"))

    def test_warning_for_host_with_no_test_marker(self):
        warning = warn_if_suspicious_allowed_host("mystoreexample.com")
        self.assertIsNotNone(warning)
        self.assertIn("mystoreexample.com", warning)


if __name__ == "__main__":
    unittest.main()
