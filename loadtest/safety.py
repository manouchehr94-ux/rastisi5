"""Hard target-host safety guard for the Phase 3 Locust suite.

Pure Python, zero third-party/Django dependency — this module must be
importable (and its checks runnable) even in an environment that has
neither ``locust`` nor ``django`` installed, so it can be unit-tested in
isolation and so nothing about how it decides "is this host safe to hit"
depends on anything else in this repository being configured correctly.

Design, in order of precedence:

1. **Hard block** — a fixed, non-overridable list of production-domain
   suffixes (today: ``rastisi.ir``). Any hostname that IS one of these, or
   is any subdomain of one of these (``www.rastisi.ir``,
   ``platformadmins.rastisi.ir``, ``some-store.rastisi.ir``, ...), is
   refused unconditionally. This check runs first and nothing else in this
   module — including the operator's own allowlist — can override it.
2. **Default-deny** — every other host is refused UNLESS it appears in an
   explicit, operator-supplied allowlist (``LOADTEST_ALLOWED_HOSTS``, or
   any other allowlist an entry point chooses to pass in). An empty/unset
   allowlist means nothing is allowed, on purpose: this suite must never
   silently default to a runnable target.

Real merchant custom domains (``somemerchant.example``) are, by
definition, not enumerable in advance — this module cannot maintain a
blocklist of every domain a RastiSi merchant might configure. They are
guarded against exactly by (2): they would only ever be hit if an operator
explicitly, deliberately added one to the allowlist, which is a
misuse of this tool, not a gap this module can close by itself. See
``loadtest/README.md`` for the operator-facing warning about this.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Non-overridable. Any hostname equal to, or a subdomain of, one of these
# is refused regardless of any allowlist configuration.
HARD_BLOCKED_SUFFIXES: tuple[str, ...] = ("rastisi.ir",)

# Substrings whose presence in an allowed hostname is a mild positive
# signal that it's a deliberately-named test/staging host, not a real
# merchant domain accidentally pasted into the allowlist. Advisory only —
# see warn_if_suspicious_allowed_host(). Never used to allow or deny.
_LOOKS_LIKE_TEST_HOST_MARKERS = ("localhost", "loadtest", "staging", "load-test", "test")


class UnsafeLoadTestTargetError(Exception):
    """The configured target host failed the safety guard. Never caught and
    silently ignored by any entry point in this package — this must always
    abort the run."""


def extract_hostname(target: str) -> str:
    """Best-effort extraction of a bare, lowercased, no-port hostname from
    ``target``, which may be a full URL (``https://host:443/path``), a
    bare ``host:port``, or a bare hostname. Returns ``""`` if nothing
    hostname-shaped can be found — callers must treat that as "not
    allowed", never as "no restriction"."""
    if not target:
        return ""
    candidate = target.strip()
    if "//" not in candidate:
        # urlsplit only parses a netloc when a scheme separator is
        # present; without it, "host:port/path" is misparsed as a path.
        candidate = f"//{candidate}"
    hostname = urlsplit(candidate).hostname
    return (hostname or "").strip().lower().rstrip(".")


def _hostname_is_or_subdomain_of(hostname: str, suffix: str) -> bool:
    suffix = suffix.strip().lower().rstrip(".")
    return hostname == suffix or hostname.endswith("." + suffix)


def is_hard_blocked(hostname: str) -> bool:
    """True if ``hostname`` (already-extracted, e.g. via extract_hostname)
    is the real RastiSi production domain or any subdomain of it."""
    if not hostname:
        return False
    return any(_hostname_is_or_subdomain_of(hostname, suffix) for suffix in HARD_BLOCKED_SUFFIXES)


def parse_allowed_hosts(raw: str | None) -> frozenset[str]:
    """Parses a comma-separated allowlist string (e.g. from the
    ``LOADTEST_ALLOWED_HOSTS`` environment variable) into a normalized
    frozenset. Entries that are themselves hard-blocked are silently
    dropped here — belt-and-suspenders, since is_host_allowed() below
    already checks is_hard_blocked() first regardless, but a caller that
    only inspects the parsed allowlist (e.g. to print it) should never see
    a blocked entry presented as "allowed"."""
    if not raw:
        return frozenset()
    hosts = {extract_hostname(item) or item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()}
    return frozenset(h for h in hosts if h and not is_hard_blocked(h))


def is_host_allowed(target: str, allowed_hosts: frozenset[str]) -> bool:
    """The single source of truth for "may this suite send requests to
    `target`". Hard-block always wins; otherwise `target`'s hostname must
    exactly match, or be a subdomain of, an entry in `allowed_hosts` —
    an empty `allowed_hosts` allows nothing."""
    hostname = extract_hostname(target)
    if not hostname:
        return False
    if is_hard_blocked(hostname):
        return False
    if not allowed_hosts:
        return False
    return any(hostname == allowed or _hostname_is_or_subdomain_of(hostname, allowed) for allowed in allowed_hosts)


def assert_host_allowed(target: str, allowed_hosts: frozenset[str]) -> None:
    """Raises UnsafeLoadTestTargetError with an explanatory message if
    `target` does not pass is_host_allowed(). Call this once, as early as
    possible, on every Locust process (master, worker, and standalone) —
    see locustfile.py's `init` event listener."""
    hostname = extract_hostname(target)
    if not hostname:
        raise UnsafeLoadTestTargetError(
            f"Refusing to run: could not determine a hostname from target {target!r}. "
            "Pass a real --host, e.g. https://loadtest.example.internal."
        )
    if is_hard_blocked(hostname):
        raise UnsafeLoadTestTargetError(
            f"Refusing to run: {hostname!r} is the real RastiSi production domain (or a "
            "subdomain of it). This suite must never target rastisi.ir or any "
            "*.rastisi.ir host, under any configuration. This check cannot be "
            "overridden by LOADTEST_ALLOWED_HOSTS or any other setting."
        )
    if not allowed_hosts:
        raise UnsafeLoadTestTargetError(
            "Refusing to run: no LOADTEST_ALLOWED_HOSTS configured (default-deny — "
            "this suite never has an implicit default target). Set "
            "LOADTEST_ALLOWED_HOSTS to a comma-separated list of your staging "
            "host(s) that includes the hostname you passed via --host."
        )
    if not is_host_allowed(target, allowed_hosts):
        raise UnsafeLoadTestTargetError(
            f"Refusing to run: {hostname!r} is not in LOADTEST_ALLOWED_HOSTS "
            f"({sorted(allowed_hosts)!r}). Add it explicitly if this is really a "
            "non-production staging host you intend to load-test."
        )


def warn_if_suspicious_allowed_host(hostname: str) -> str | None:
    """Advisory-only heuristic: returns a warning string if `hostname`
    doesn't contain any of the common test/staging naming markers, since
    that's a mild signal an operator may have pasted in a real merchant's
    custom domain by mistake. Returns None if the host looks fine, or
    contains a marker. Never used to allow/deny — see module docstring for
    why real merchant domains cannot be blocked structurally."""
    if any(marker in hostname for marker in _LOOKS_LIKE_TEST_HOST_MARKERS):
        return None
    return (
        f"WARNING: allowed host {hostname!r} doesn't look like an obvious "
        "test/staging hostname (no 'test'/'staging'/'loadtest'/'localhost' "
        "marker in it). Double-check this is not a real merchant's custom "
        "domain before proceeding."
    )
