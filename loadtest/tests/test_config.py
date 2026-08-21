"""Unit tests for loadtest.config — load levels, SLO thresholds, and
workload toggles. Plain unittest, no Django/locust dependency."""

import unittest

from loadtest.config import (
    LOAD_LEVELS,
    LoadTestConfigError,
    load_slo_thresholds,
    load_workload_config,
    resolve_load_level,
)


class LoadLevelsTests(unittest.TestCase):
    def test_all_six_required_levels_present(self):
        self.assertEqual(set(LOAD_LEVELS), {"100", "500", "1000", "2500", "5000", "10000"})

    def test_users_match_level_name(self):
        for name, level in LOAD_LEVELS.items():
            self.assertEqual(level.users, int(name))

    def test_levels_are_monotonically_increasing(self):
        ordered = [LOAD_LEVELS[n] for n in ("100", "500", "1000", "2500", "5000", "10000")]
        users = [lvl.users for lvl in ordered]
        self.assertEqual(users, sorted(users))
        self.assertEqual(len(set(users)), len(users))

    def test_suggested_workers_non_decreasing_with_scale(self):
        ordered = [LOAD_LEVELS[n].suggested_workers for n in ("100", "500", "1000", "2500", "5000", "10000")]
        self.assertEqual(ordered, sorted(ordered))

    def test_resolve_valid_level(self):
        self.assertIs(resolve_load_level("1000"), LOAD_LEVELS["1000"])

    def test_resolve_unknown_level_raises(self):
        with self.assertRaises(LoadTestConfigError):
            resolve_load_level("12345")


class SloThresholdsTests(unittest.TestCase):
    def test_unset_by_default(self):
        thresholds = load_slo_thresholds(environ={})
        self.assertFalse(thresholds.configured)
        self.assertIsNone(thresholds.p95_ms)
        self.assertIsNone(thresholds.p99_ms)
        self.assertIsNone(thresholds.max_failure_rate_pct)

    def test_partial_configuration_is_configured(self):
        thresholds = load_slo_thresholds(environ={"LOADTEST_SLO_P95_MS": "800"})
        self.assertTrue(thresholds.configured)
        self.assertEqual(thresholds.p95_ms, 800.0)
        self.assertIsNone(thresholds.p99_ms)

    def test_all_three_configured(self):
        thresholds = load_slo_thresholds(environ={
            "LOADTEST_SLO_P95_MS": "800",
            "LOADTEST_SLO_P99_MS": "1500",
            "LOADTEST_SLO_MAX_FAILURE_RATE_PCT": "1.0",
        })
        self.assertEqual((thresholds.p95_ms, thresholds.p99_ms, thresholds.max_failure_rate_pct), (800.0, 1500.0, 1.0))

    def test_malformed_value_raises(self):
        with self.assertRaises(LoadTestConfigError):
            load_slo_thresholds(environ={"LOADTEST_SLO_P95_MS": "not-a-number"})

    def test_never_hardcodes_a_default_threshold(self):
        """Phase 3 requirement: SLOs are configurable, never a baked-in
        business claim — the default must be None across the board, not
        some plausible-looking number."""
        thresholds = load_slo_thresholds(environ={})
        self.assertEqual((thresholds.p95_ms, thresholds.p99_ms, thresholds.max_failure_rate_pct), (None, None, None))


class WorkloadConfigTests(unittest.TestCase):
    def test_checkout_writes_default_off(self):
        config = load_workload_config(environ={})
        self.assertFalse(config.enable_checkout_writes)

    def test_admin_mutations_default_off(self):
        config = load_workload_config(environ={})
        self.assertFalse(config.enable_admin_mutations)

    def test_checkout_writes_explicit_opt_in(self):
        config = load_workload_config(environ={"LOADTEST_ENABLE_CHECKOUT_WRITES": "true"})
        self.assertTrue(config.enable_checkout_writes)

    def test_admin_mutations_explicit_opt_in(self):
        config = load_workload_config(environ={"LOADTEST_ENABLE_ADMIN_MUTATIONS": "true"})
        self.assertTrue(config.enable_admin_mutations)

    def test_tenant_hosts_parsed_as_tuple(self):
        config = load_workload_config(environ={"LOADTEST_TENANT_HOSTS": "a.example.com, b.example.com"})
        self.assertEqual(config.tenant_hosts, ("a.example.com", "b.example.com"))

    def test_tenant_hosts_empty_by_default(self):
        config = load_workload_config(environ={})
        self.assertEqual(config.tenant_hosts, ())

    def test_allowed_hosts_wired_through_safety_parser(self):
        config = load_workload_config(environ={"LOADTEST_ALLOWED_HOSTS": "rastisi.ir,loadtest.example.internal"})
        # rastisi.ir must be dropped even here (parse_allowed_hosts already
        # covers this in test_safety.py; this proves the wiring, not the
        # logic itself, to catch a future accidental bypass of the shared
        # parser).
        self.assertEqual(config.allowed_hosts, frozenset({"loadtest.example.internal"}))

    def test_default_think_time_is_nonzero_realistic_range(self):
        """Phase 3 requirement: realistic think time, not near-zero
        request hammering."""
        config = load_workload_config(environ={})
        self.assertGreater(config.think_time_min_seconds, 0)
        self.assertGreaterEqual(config.think_time_max_seconds, config.think_time_min_seconds)

    def test_invalid_think_time_range_raises(self):
        with self.assertRaises(LoadTestConfigError):
            load_workload_config(environ={
                "LOADTEST_THINK_TIME_MIN_SECONDS": "10",
                "LOADTEST_THINK_TIME_MAX_SECONDS": "2",
            })

    def test_negative_think_time_raises(self):
        with self.assertRaises(LoadTestConfigError):
            load_workload_config(environ={"LOADTEST_THINK_TIME_MIN_SECONDS": "-1"})


if __name__ == "__main__":
    unittest.main()
