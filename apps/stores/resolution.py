"""Authoritative request-time Store resolution.

This module is the ONLY place in the codebase that decides "which Store
does this HTTP request belong to." No view, context processor, dashboard
service, or future business-logic code should independently guess a Store
from a hostname, a caller-supplied ID, the authenticated user, a Vendor, a
Product, a Cart, or a session value. See
``docs/architecture/SAAS_ARCHITECTURE.md`` ("Request Store Context") for
the policy this module implements, and
``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` for why tenant resolution,
authentication, authorization, and data filtering are kept as separate
concerns.

Resolution source of truth: ``StoreDomain.hostname`` — verified domains of
an active Store only (``domain_is_eligible_for_routing``). A narrow,
explicitly isolated, temporary compatibility fallback additionally allows a
fixed allowlist of local-development hosts to resolve to the Akhlaghi Store,
but only while the database contains exactly one, active, "akhlaghi" Store
(``resolve_compatibility_store``). The fallback fails closed the moment a
second Store exists — it is not a permanent behavior.
"""

from django.conf import settings as django_settings
from django.core.exceptions import DisallowedHost, ImproperlyConfigured, ValidationError

from .hostnames import normalize_hostname
from .models import Store, StoreDomain

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StoreResolutionError(Exception):
    """Base class for all Store-resolution failures.

    Never surface ``str(exc)`` from one of these directly in an HTTP
    response — these messages exist for logs and tests, not public callers
    (see module docstring: resolution must not leak tenant-existence
    details). ``resolve_store_for_request`` never raises these; it converts
    every one of them into ``None``.
    """


class InvalidHostnameError(StoreResolutionError):
    """The supplied host is not a syntactically valid, resolvable hostname."""


class UnknownStoreDomainError(StoreResolutionError):
    """The hostname is syntactically valid, but no ``StoreDomain`` row matches it."""


class IneligibleStoreDomainError(StoreResolutionError):
    """A ``StoreDomain`` matches, but it — or its Store — is not eligible for
    request routing right now. See ``domain_is_eligible_for_routing``."""


class CompatibilityFallbackUnavailableError(StoreResolutionError):
    """The host is an approved development host, but the narrow conditions
    required for the temporary Akhlaghi compatibility fallback are not met
    (more than one Store exists, the sole Store isn't Akhlaghi, or it isn't
    active)."""


class StoreNotResolvedError(StoreResolutionError):
    """Raised by ``require_resolved_store`` when a caller needs a Store that
    was never resolved for this request."""


# ---------------------------------------------------------------------------
# Routing eligibility policy
# ---------------------------------------------------------------------------


def domain_is_eligible_for_routing(domain: StoreDomain) -> bool:
    """The exact, minimal routing-eligibility policy for this PR.

    A ``StoreDomain`` may route a request only when BOTH:

    * its Store's ``status`` is ``ACTIVE`` — not provisioning, suspended, or closed;
    * its own ``verification_status`` is ``VERIFIED`` — not unverified, pending, or failed.

    Anything else fails closed. An unverified, pending, or failed domain,
    or a domain whose Store is not active, must never resolve — even if the
    hostname otherwise matches a real, existing row.
    """
    return (
        domain.store.status == Store.Status.ACTIVE
        and domain.verification_status == StoreDomain.VerificationStatus.VERIFIED
    )


# ---------------------------------------------------------------------------
# Hostname helpers
# ---------------------------------------------------------------------------


def _strip_port(host: str) -> str:
    """Remove a trailing ``:port`` from an HTTP host value, safely.

    Bracketed IPv6 literals (e.g. ``[::1]:8000``) are handled explicitly so
    the brackets are never mistaken for part of the hostname or the port.
    """
    host = (host or "").strip()
    if not host:
        return host
    if host.startswith("["):
        closing = host.find("]")
        return host[: closing + 1] if closing != -1 else host
    if host.count(":") == 1:
        base, _, _port = host.rpartition(":")
        return base
    return host


# ---------------------------------------------------------------------------
# Development/compatibility fallback — deliberately isolated from the
# authoritative StoreDomain lookup path below.
# ---------------------------------------------------------------------------

#: Hosts that may ever attempt the temporary Akhlaghi compatibility
#: fallback. These are not, and must never become, real StoreDomain rows —
#: that is precisely why this list is checked BEFORE, and instead of, the
#: authoritative StoreDomain lookup. Overridable via the
#: ``STORES_DEVELOPMENT_HOST_ALLOWLIST`` Django setting (tests use this).
DEFAULT_DEVELOPMENT_HOST_ALLOWLIST = frozenset({
    "localhost",
    "127.0.0.1",
    "[::1]",
    "testserver",  # Django test client's default HTTP Host
})

#: Duplicates apps/stores/migrations/0002_create_akhlaghi_store.py's seed
#: slug value intentionally. Runtime code must never import a migration
#: module, so this is a small, deliberate, documented duplication rather
#: than a shared import.
AKHLAGHI_SLUG = "akhlaghi"


def _development_host_allowlist():
    configured = getattr(
        django_settings, "STORES_DEVELOPMENT_HOST_ALLOWLIST", DEFAULT_DEVELOPMENT_HOST_ALLOWLIST
    )
    # A bare string is iterable character-by-character in Python. Silently
    # accepting one here would decompose e.g. "prod.example.com" into
    # single-character "hosts" that can never match a real Host header —
    # not a security hole by itself (no real request ever has a one-
    # character Host), but a silent misconfiguration that quietly disables
    # the allowlist instead of doing what whoever set it obviously intended.
    # Fail loudly instead: a bare string is always a configuration mistake.
    if isinstance(configured, str):
        raise ImproperlyConfigured(
            "STORES_DEVELOPMENT_HOST_ALLOWLIST must be a list/tuple/set of "
            "hostnames, not a bare string (a string would be iterated "
            "character-by-character)."
        )
    return frozenset(h.lower() for h in configured)


def _is_development_host(stripped_host: str) -> bool:
    return stripped_host.lower() in _development_host_allowlist()


def resolve_compatibility_store() -> Store:
    """The narrow, temporary single-Store compatibility fallback.

    Returns the Akhlaghi Store only when ALL of the following hold:

    * exactly one Store exists in the entire database;
    * that Store's slug is ``"akhlaghi"``;
    * that Store's status is ``ACTIVE``.

    Raises ``CompatibilityFallbackUnavailableError`` otherwise. In
    particular, the moment a second Store is created anywhere on the
    platform, this fails closed instead of guessing — it never falls back
    to "the first Store" or any other heuristic. This exists only to let
    Akhlaghi keep working locally before a real, verified ``StoreDomain``
    is provisioned for it; it is not a permanent behavior and must not be
    relied upon once a real domain exists.

    Public (not host-specific) on purpose: this same "is there exactly one
    active Akhlaghi Store" check is also the compatibility rule for
    Store-scoped settings retrieval (``apps.core.models.ShopSettings.load()``,
    ``apps.content.models.FooterSettings.load()``) when no explicit Store is
    given — reusing it here keeps there being exactly one fail-closed check,
    not two independently-maintained copies of the same safety rule.
    """
    stores = list(Store.objects.all()[:2])
    if len(stores) != 1:
        raise CompatibilityFallbackUnavailableError(
            "compatibility fallback requires exactly one Store to exist"
        )
    store = stores[0]
    if store.slug != AKHLAGHI_SLUG:
        raise CompatibilityFallbackUnavailableError("the sole Store is not Akhlaghi")
    if store.status != Store.Status.ACTIVE:
        raise CompatibilityFallbackUnavailableError("the Akhlaghi Store is not active")
    return store


# ---------------------------------------------------------------------------
# Public resolution interface
# ---------------------------------------------------------------------------


def resolve_store_for_hostname(raw_host: str) -> Store:
    """Resolve a Store from a raw HTTP host value (may include a port).

    Raises one of the ``StoreResolutionError`` subclasses above on any
    failure, so callers (typically tests) can distinguish *why* resolution
    failed. Use ``resolve_store_for_hostname_or_none`` when only a
    yes/no-with-fallback-to-None result is needed.
    """
    stripped = _strip_port(raw_host)

    if _is_development_host(stripped):
        return resolve_compatibility_store()

    try:
        normalized = normalize_hostname(stripped)
    except ValidationError as exc:
        raise InvalidHostnameError(str(exc)) from exc

    domain = (
        StoreDomain.objects.select_related("store").filter(hostname=normalized).first()
    )
    if domain is None:
        raise UnknownStoreDomainError(f"no StoreDomain matches {normalized!r}")

    if not domain_is_eligible_for_routing(domain):
        raise IneligibleStoreDomainError(
            f"StoreDomain {normalized!r} is not eligible for routing"
        )

    return domain.store


def resolve_store_for_hostname_or_none(raw_host: str):
    """Same as ``resolve_store_for_hostname``, but returns ``None`` instead
    of raising on any ``StoreResolutionError``."""
    try:
        return resolve_store_for_hostname(raw_host)
    except StoreResolutionError:
        return None


def resolve_store_for_request(request):
    """Resolve a Store for an in-flight ``HttpRequest``. Never raises.

    Uses ``request.get_host()`` — Django's own Host-header parsing and
    ``ALLOWED_HOSTS`` validation — as the sole source of the hostname.
    Never a caller-supplied Store ID, a query parameter, a header other
    than ``Host``, the URL path, a session value, or an authenticated
    membership. Returns ``None`` for any failure, including an
    already-disallowed Host header: this function must never raise, since
    it is what the middleware calls directly on every request.
    """
    try:
        raw_host = request.get_host()
    except DisallowedHost:
        return None
    return resolve_store_for_hostname_or_none(raw_host)


def require_resolved_store(request) -> Store:
    """For future Store-aware service code: return ``request.store``, or raise.

    Nothing in this PR consumes this helper — no business logic depends on
    Store resolution yet. It is provided now as the single, documented way
    later code should assert "this operation requires an already-resolved
    Store," instead of each future caller re-deriving or re-guessing one
    independently.
    """
    store = getattr(request, "store", None)
    if store is None:
        raise StoreNotResolvedError("no Store was resolved for this request")
    return store
