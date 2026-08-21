"""Environment-driven configuration for the Phase 3 Locust suite — load
levels, SLO thresholds, workload toggles, and multi-tenant fixture data.

Pure Python, no Django/locust dependency, so it stays independently
unit-testable (see loadtest/tests/test_config.py) and importable from
anywhere. All parsing follows the same "explicit env var, safe default,
fail loud on a malformed value" shape as ``shop_core/env_config.py`` in
the Django app, but this module intentionally does NOT import that one —
this package must run in an environment that never has Django installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from loadtest.safety import parse_allowed_hosts


class LoadTestConfigError(Exception):
    """A load-test environment variable is set but malformed."""


def _env_str(name: str, default: str = "", *, environ=None) -> str:
    raw = (environ or os.environ).get(name)
    return default if raw is None else raw.strip()


def _env_bool(name: str, default: bool, *, environ=None) -> bool:
    raw = (environ or os.environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise LoadTestConfigError(f"{name}={raw!r} is not a valid boolean (use true/false, 1/0, yes/no, on/off).")


def _env_float_or_none(name: str, *, environ=None) -> float | None:
    raw = (environ or os.environ).get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise LoadTestConfigError(f"{name}={raw!r} is not a valid number.") from exc


def _env_int(name: str, default: int, *, environ=None) -> int:
    raw = (environ or os.environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise LoadTestConfigError(f"{name}={raw!r} is not a valid integer.") from exc


# ---------------------------------------------------------------------------
# Named load levels (§ Phase 3: "100, 500, 1,000, 2,500, 5,000, and 10,000
# users"). These are *virtual users* (concurrent simulated humans, each
# pacing itself with think time — see users/*.py wait_time), not a request
# rate. spawn_rate is deliberately gentle (ramp-up, not an instant burst) so
# the platform sees a realistic traffic ramp, not a thundering herd.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadLevel:
    name: str
    users: int
    spawn_rate: float  # users started per second during ramp-up
    suggested_workers: int  # rule-of-thumb distributed Locust workers — see README


LOAD_LEVELS: dict[str, LoadLevel] = {
    level.name: level
    for level in (
        LoadLevel("100", 100, 5, 1),
        LoadLevel("500", 500, 10, 1),
        LoadLevel("1000", 1_000, 20, 2),
        LoadLevel("2500", 2_500, 25, 4),
        LoadLevel("5000", 5_000, 30, 8),
        LoadLevel("10000", 10_000, 40, 16),
    )
}


def resolve_load_level(name: str) -> LoadLevel:
    try:
        return LOAD_LEVELS[name.strip()]
    except KeyError:
        raise LoadTestConfigError(
            f"Unknown load level {name!r}; choose one of {sorted(LOAD_LEVELS)}."
        ) from None


# ---------------------------------------------------------------------------
# SLO thresholds — configurable, unset by default. This module never
# hardcodes a "RastiSi supports N users" claim: it only compares a
# completed run's *measured* stats against whatever numbers the operator
# chose to configure, and reports pass/fail on that operator-chosen bar.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SloThresholds:
    p95_ms: float | None
    p99_ms: float | None
    max_failure_rate_pct: float | None

    @property
    def configured(self) -> bool:
        return self.p95_ms is not None or self.p99_ms is not None or self.max_failure_rate_pct is not None


def load_slo_thresholds(*, environ=None) -> SloThresholds:
    return SloThresholds(
        p95_ms=_env_float_or_none("LOADTEST_SLO_P95_MS", environ=environ),
        p99_ms=_env_float_or_none("LOADTEST_SLO_P99_MS", environ=environ),
        max_failure_rate_pct=_env_float_or_none("LOADTEST_SLO_MAX_FAILURE_RATE_PCT", environ=environ),
    )


# ---------------------------------------------------------------------------
# Workload toggles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkloadConfig:
    allowed_hosts: frozenset[str]
    enable_checkout_writes: bool
    enable_admin_mutations: bool
    tenant_hosts: tuple[str, ...]
    admin_hosts: tuple[str, ...]
    admin_username: str
    admin_password: str
    think_time_min_seconds: float
    think_time_max_seconds: float


def _env_host_tuple(name: str, *, environ=None) -> tuple[str, ...]:
    raw = _env_str(name, "", environ=environ)
    return tuple(h.strip() for h in raw.split(",") if h.strip())


def load_workload_config(*, environ=None) -> WorkloadConfig:
    think_min = _env_float_or_none("LOADTEST_THINK_TIME_MIN_SECONDS", environ=environ) or 2.0
    think_max = _env_float_or_none("LOADTEST_THINK_TIME_MAX_SECONDS", environ=environ) or 8.0
    if think_min < 0 or think_max < think_min:
        raise LoadTestConfigError(
            "LOADTEST_THINK_TIME_MIN_SECONDS/LOADTEST_THINK_TIME_MAX_SECONDS must satisfy "
            f"0 <= min <= max (got min={think_min}, max={think_max})."
        )
    return WorkloadConfig(
        allowed_hosts=parse_allowed_hosts(_env_str("LOADTEST_ALLOWED_HOSTS", environ=environ)),
        # Both write-workload toggles default OFF — Phase 3 requirement:
        # "Keep order/checkout write workloads explicitly opt-in."
        enable_checkout_writes=_env_bool("LOADTEST_ENABLE_CHECKOUT_WRITES", False, environ=environ),
        enable_admin_mutations=_env_bool("LOADTEST_ENABLE_ADMIN_MUTATIONS", False, environ=environ),
        tenant_hosts=_env_host_tuple("LOADTEST_TENANT_HOSTS", environ=environ),
        admin_hosts=_env_host_tuple("LOADTEST_ADMIN_HOSTS", environ=environ),
        admin_username=_env_str("LOADTEST_ADMIN_USERNAME", environ=environ),
        admin_password=_env_str("LOADTEST_ADMIN_PASSWORD", environ=environ),
        think_time_min_seconds=think_min,
        think_time_max_seconds=think_max,
    )
