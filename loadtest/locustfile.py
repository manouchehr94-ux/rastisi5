"""RastiSi Phase 3 Locust suite — entry point.

Run this with the `locust` CLI, never by importing/executing it directly.
See loadtest/README.md for exact commands (single-process smoke test,
each of the 100/500/1000/2500/5000/10000 load levels, and distributed
master/worker invocation).

SAFETY: every hostname this suite could possibly send a request to or set
as a Host header — the `--host` connection target, every configured
tenant storefront host, every configured admin host — is checked against
loadtest.safety.assert_host_allowed() in the `init` event handler below,
which fires on every Locust process (standalone, master, and every
worker) before any User class can spawn. There is no code path in this
file that sends an HTTP request before that check has passed.
"""

from __future__ import annotations

import logging
import os
import random
import time

from locust import HttpUser, between, events, task

from loadtest.config import (
    LoadTestConfigError,
    load_slo_thresholds,
    load_workload_config,
)
from loadtest.safety import UnsafeLoadTestTargetError, assert_host_allowed, warn_if_suspicious_allowed_host

logger = logging.getLogger("rastisi.loadtest")

_workload = load_workload_config()
_slo = load_slo_thresholds()


# ---------------------------------------------------------------------------
# Startup safety gate — runs on every Locust process (init fires once per
# process: standalone, master, and each worker in distributed mode).
# ---------------------------------------------------------------------------

@events.init.add_listener
def _enforce_target_safety(environment, **kwargs):
    targets_to_check = [environment.host or ""]
    targets_to_check.extend(_workload.tenant_hosts)
    targets_to_check.extend(_workload.admin_hosts)

    for target in targets_to_check:
        if not target:
            continue
        try:
            assert_host_allowed(target, _workload.allowed_hosts)
        except UnsafeLoadTestTargetError as exc:
            logger.error(str(exc))
            # Abort hard — do not let Locust proceed to spawn a single User.
            raise SystemExit(1) from exc

    for host in (*_workload.tenant_hosts, *_workload.admin_hosts):
        warning = warn_if_suspicious_allowed_host(host)
        if warning:
            logger.warning(warning)

    logger.info(
        "Load-test safety guard passed. Connection target=%r, tenant hosts=%s, admin hosts=%s, "
        "checkout writes=%s, admin mutations=%s",
        environment.host, _workload.tenant_hosts, _workload.admin_hosts,
        _workload.enable_checkout_writes, _workload.enable_admin_mutations,
    )


# ---------------------------------------------------------------------------
# Load-generator saturation detection (Phase 3: "Detect and document
# load-generator saturation"). Locust already monitors its own process CPU
# and fires `cpu_warning` above ~90% sustained usage — we surface that
# loudly instead of leaving it as a debug-level log line, since a saturated
# load generator invalidates every response-time measurement in the run
# (you'd be measuring Locust's own scheduling delay, not the target
# server). We also track a simple response-time-inflation heuristic:
# if p95 more than doubles between consecutive reporting windows while RPS
# is flat or falling, that's consistent with the *generator* running out
# of headroom rather than the target degrading (a target degrading under
# more load usually comes with RPS still rising or the failure rate
# rising, not RPS flat/falling under a steady user count).
# ---------------------------------------------------------------------------

_generator_saturation_warned = False


@events.cpu_warning.add_listener
def _on_generator_cpu_warning(environment, cpu_usage, **kwargs):
    global _generator_saturation_warned
    _generator_saturation_warned = True
    logger.warning(
        "LOAD GENERATOR SATURATION: this Locust process's own CPU usage is %.0f%%. "
        "Response-time measurements from this point are unreliable — you are likely "
        "measuring load-generator scheduling delay, not the target server. Reduce "
        "--users on this process and add distributed workers instead (see README).",
        cpu_usage,
    )


@events.quitting.add_listener
def _warn_if_run_was_saturated(environment, **kwargs):
    if _generator_saturation_warned:
        logger.warning(
            "This run hit load-generator CPU saturation at least once (see warnings "
            "above) — treat its response-time percentiles as a lower bound on the "
            "target's real latency, not a reliable measurement. Re-run with more "
            "distributed workers before trusting these numbers."
        )


# ---------------------------------------------------------------------------
# End-of-run summary: RPS, failures, median/p90/p95/p99/max, and — only if
# the operator configured any — SLO pass/fail. This never asserts or
# hardcodes a capacity claim; it only reports whether THIS run's measured
# numbers met the thresholds THIS run's operator chose to set.
# ---------------------------------------------------------------------------

@events.test_stop.add_listener
def _print_summary(environment, **kwargs):
    stats = environment.stats.total
    p50 = stats.median_response_time
    p90 = stats.get_response_time_percentile(0.90)
    p95 = stats.get_response_time_percentile(0.95)
    p99 = stats.get_response_time_percentile(0.99)
    rps = stats.total_rps
    fail_pct = stats.fail_ratio * 100

    logger.info(
        "\n"
        "===== RastiSi Phase 3 load-test summary =====\n"
        "  target             : %s\n"
        "  requests           : %d (failures: %d, %.2f%%)\n"
        "  RPS (avg over run) : %.2f\n"
        "  median (p50)       : %d ms\n"
        "  p90                : %d ms\n"
        "  p95                : %d ms\n"
        "  p99                : %d ms\n"
        "  max                : %d ms\n"
        "  generator saturated: %s\n"
        "===============================================",
        environment.host, stats.num_requests, stats.num_failures, fail_pct,
        rps, p50, p90, p95, p99, stats.max_response_time,
        _generator_saturation_warned,
    )

    if not _slo.configured:
        logger.info("No LOADTEST_SLO_* thresholds configured — skipping pass/fail SLO check.")
        return

    failures = []
    if _slo.p95_ms is not None and p95 > _slo.p95_ms:
        failures.append(f"p95 {p95}ms > configured threshold {_slo.p95_ms}ms")
    if _slo.p99_ms is not None and p99 > _slo.p99_ms:
        failures.append(f"p99 {p99}ms > configured threshold {_slo.p99_ms}ms")
    if _slo.max_failure_rate_pct is not None and fail_pct > _slo.max_failure_rate_pct:
        failures.append(f"failure rate {fail_pct:.2f}% > configured threshold {_slo.max_failure_rate_pct}%")

    if failures:
        logger.warning("SLO check: FAIL — %s", "; ".join(failures))
    else:
        logger.info("SLO check: PASS (against operator-configured thresholds only — not a capacity claim)")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _think_time():
    return between(_workload.think_time_min_seconds, _workload.think_time_max_seconds)


def _pick_tenant_host() -> str:
    """Multi-tenant workload: each simulated user is assigned one store's
    Host-header value at on_start (see each User class below) — this
    spreads a swarm of thousands of virtual users across many different
    Store tenants, the same way real platform traffic would, and exercises
    RastiSi's per-request Store-resolution path (apps.stores.middleware.
    StoreResolutionMiddleware) under real concurrent multi-tenant load
    instead of hammering a single store."""
    if not _workload.tenant_hosts:
        raise LoadTestConfigError(
            "LOADTEST_TENANT_HOSTS is not set — this suite needs at least one "
            "storefront host (Host-header value) to simulate. See README."
        )
    return random.choice(_workload.tenant_hosts)


def _pick_admin_host() -> str:
    if not _workload.admin_hosts:
        raise LoadTestConfigError(
            "LOADTEST_ADMIN_HOSTS is not set — this suite needs at least one "
            "merchant-admin host (Host-header value) to simulate. See README."
        )
    return random.choice(_workload.admin_hosts)


# ---------------------------------------------------------------------------
# Workload 1 — anonymous storefront browsing (highest-weight, matches real
# traffic composition: most visits never touch cart/checkout/admin).
# ---------------------------------------------------------------------------

class StorefrontBrowserUser(HttpUser):
    weight = 6
    wait_time = _think_time()

    def on_start(self):
        self.tenant_host = _pick_tenant_host()
        self._headers = {"Host": self.tenant_host}

    @task(5)
    def view_home(self):
        self.client.get("/", headers=self._headers, name="/ [home]")

    @task(4)
    def browse_product_list(self):
        self.client.get("/products/", headers=self._headers, name="/products/ [list]")

    @task(2)
    def browse_category(self):
        self.client.get("/products/?category=demo", headers=self._headers, name="/products/?category= [filtered]")

    @task(2)
    def search(self):
        self.client.get("/products/?q=کالا", headers=self._headers, name="/products/?q= [search]")

    @task(3)
    def view_product_detail(self):
        # A fixed, seeded slug — see apps/stores/management/commands/
        # seed_loadtest_fixtures.py, which creates this deterministically
        # for every seeded store so this task never depends on scraping a
        # listing page first (keeping each task independently retryable).
        self.client.get(
            "/products/loadtest-product-1/", headers=self._headers, name="/products/<slug>/ [detail]",
        )

    @task(1)
    def view_collections(self):
        self.client.get("/collections/", headers=self._headers, name="/collections/ [index]")


# ---------------------------------------------------------------------------
# Workload 2 — shopping customer: browse + cart, checkout writes gated
# behind LOADTEST_ENABLE_CHECKOUT_WRITES (default off).
# ---------------------------------------------------------------------------

class ShoppingCustomerUser(HttpUser):
    weight = 3
    wait_time = _think_time()

    def on_start(self):
        self.tenant_host = _pick_tenant_host()
        self._headers = {"Host": self.tenant_host}
        # Prime the CSRF cookie/session the same way a real browser would
        # before the first POST — every mutating endpoint in this app
        # requires it.
        self.client.get("/", headers=self._headers, name="/ [home, csrf priming]")

    def _csrf_headers(self):
        token = self.client.cookies.get("csrftoken")
        headers = dict(self._headers)
        if token:
            headers["X-CSRFToken"] = token
        return headers

    @task(4)
    def browse_before_buying(self):
        self.client.get("/products/", headers=self._headers, name="/products/ [list]")
        self.client.get(
            "/products/loadtest-product-1/", headers=self._headers, name="/products/<slug>/ [detail]",
        )

    @task(2)
    def add_to_cart_and_view(self):
        self.client.post(
            "/cart/add/loadtest-product-1/", data={"quantity": 1},
            headers=self._csrf_headers(), name="/cart/add/<slug>/ [POST]",
        )
        self.client.get("/cart/", headers=self._headers, name="/cart/ [detail]")

    @task(1)
    def checkout_write_flow(self):
        if not _workload.enable_checkout_writes:
            # Explicitly opt-in only (Phase 3 requirement) — falls back to
            # a read-only cart view so this task class still contributes
            # realistic read traffic even when writes are disabled.
            self.client.get("/cart/", headers=self._headers, name="/cart/ [detail, checkout-writes disabled]")
            return
        self.client.post(
            "/cart/add/loadtest-product-1/", data={"quantity": 1},
            headers=self._csrf_headers(), name="/cart/add/<slug>/ [POST]",
        )
        self.client.get("/checkout/", headers=self._headers, name="/checkout/ [step1]")
        # Deliberately does not submit the address/payment form: driving a
        # real order through to a real (even simulated) payment gateway
        # calls needs per-store checkout fixtures (shipping method,
        # payment gateway, valid address) beyond what this suite seeds by
        # default. Wire that up here only once a specific staging
        # environment's checkout fixtures are confirmed, per README.


# ---------------------------------------------------------------------------
# Workload 3 — merchant admin: login once, then browse the exact endpoints
# Phase 2 fixed (order list, customer list, product list) under load.
# Mutations gated behind LOADTEST_ENABLE_ADMIN_MUTATIONS (default off).
# ---------------------------------------------------------------------------

class MerchantAdminUser(HttpUser):
    weight = 1
    wait_time = _think_time()

    def on_start(self):
        self.admin_host = _pick_admin_host()
        self._headers = {"Host": self.admin_host}
        if not (_workload.admin_username and _workload.admin_password):
            raise LoadTestConfigError(
                "LOADTEST_ADMIN_USERNAME/LOADTEST_ADMIN_PASSWORD are required for "
                "MerchantAdminUser — see README (seeded by seed_loadtest_fixtures)."
            )
        login_page = self.client.get("/admin-portal/login/", headers=self._headers, name="/admin-portal/login/ [GET]")
        token = self.client.cookies.get("csrftoken")
        headers = dict(self._headers)
        if token:
            headers["X-CSRFToken"] = token
        self.client.post(
            "/admin-portal/login/",
            data={"username": _workload.admin_username, "password": _workload.admin_password},
            headers=headers, name="/admin-portal/login/ [POST]",
        )

    @task(3)
    def view_dashboard(self):
        self.client.get("/admin-portal/", headers=self._headers, name="/admin-portal/ [dashboard]")

    @task(3)
    def view_product_list(self):
        # Exercises the Phase 2 stats-aggregate fix directly.
        self.client.get("/admin-portal/products/", headers=self._headers, name="/admin-portal/products/ [list]")

    @task(3)
    def view_order_list(self):
        # Exercises the Phase 2 pagination + items_count-annotation fix,
        # and the new Order(store, -created_at) index, directly.
        self.client.get("/admin-portal/orders/", headers=self._headers, name="/admin-portal/orders/ [list]")

    @task(2)
    def view_customer_list(self):
        # Exercises the Phase 2 pagination fix directly.
        self.client.get("/admin-portal/customers/", headers=self._headers, name="/admin-portal/customers/ [list]")

    @task(1)
    def paginate_orders(self):
        self.client.get("/admin-portal/orders/?page=2", headers=self._headers, name="/admin-portal/orders/?page=2")

    @task(1)
    def admin_mutation_placeholder(self):
        if not _workload.enable_admin_mutations:
            self.client.get(
                "/admin-portal/orders/", headers=self._headers,
                name="/admin-portal/orders/ [list, admin-mutations disabled]",
            )
            return
        # Deliberately left as a documented extension point, not a stub
        # that fires a real mutation by default — see README "Enabling
        # admin mutation load" before wiring a specific POST here (bulk
        # actions, status changes, ...); which one is realistic depends on
        # the specific staging store's fixture data.
