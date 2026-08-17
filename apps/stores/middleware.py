"""Request-time Store resolution middleware.

Attaches ``request.store`` (a ``Store`` instance or ``None``) to every
request, using ``apps.stores.resolution.resolve_store_for_request`` as the
sole resolution mechanism. See
``docs/architecture/SAAS_ARCHITECTURE.md`` ("Request Store Context") for
the full policy. This middleware deliberately does NOT:

* redirect, render a response, or make any authorization decision;
* raise — resolution failure always means ``request.store = None``;
* touch ``request.user``, sessions, or ``StoreMembership`` — nothing here
  depends on authentication, which is precisely why this middleware runs
  before ``AuthenticationMiddleware`` in ``shop_core.settings.MIDDLEWARE``;
* query ``ShopSettings`` or any commerce model.

Tenant resolution (this middleware), authentication, authorization, and
data filtering are deliberately kept as separate concerns; this middleware
implements only the first, and nothing downstream currently consumes
``request.store`` — it is infrastructure for future PRs.

A retired hostname (e.g. a generated trial hostname superseded by a paid
permanent handle, ADR-101) needs no special middleware of its own: it is
simply not routing-eligible (``domain_is_eligible_for_routing`` excludes
any ``StoreDomain`` with ``retired_at`` set), so it falls through the exact
same fail-closed path as an unverified/unknown host — a clean 404 via
``resolve_store_for_storefront``, never a redirect. An earlier version of
this module had a dedicated ``HostnameRedirectMiddleware`` that redirected
retired hostnames forever; that behavior was a product-decision mistake
(see ADR-96, superseded by ADR-101) and has been removed, not merely
disabled.
"""

from django.core.exceptions import DisallowedHost, ValidationError
from django.http import HttpResponsePermanentRedirect

from .hostnames import normalize_hostname
from .models import StoreDomain
from .resolution import resolve_store_for_request, strip_port


class StoreResolutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = resolve_store_for_request(request)
        return self.get_response(request)


_ADMIN_PORTAL_PREFIX = "/admin-portal"
_LOCAL_ASSET_PREFIXES = ("/static/", "/media/")


def _is_merchant_admin_or_local_asset_path(path: str) -> bool:
    if path == _ADMIN_PORTAL_PREFIX or path.startswith(f"{_ADMIN_PORTAL_PREFIX}/"):
        return True
    return path.startswith(_LOCAL_ASSET_PREFIXES)


class StorefrontCanonicalRedirectMiddleware:
    """Redirect permanent Rastisi public handle to the active custom domain.

    Tenant resolution remains separate. This middleware only canonicalizes
    public requests from a live PLATFORM_SUBDOMAIN when the same Store has a
    VERIFIED PRIMARY CUSTOM_DOMAIN. Merchant admin and local asset paths stay
    on the Rastisi host.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        store = getattr(request, "store", None)
        if store is None or _is_merchant_admin_or_local_asset_path(request.path_info):
            return self.get_response(request)

        try:
            hostname = normalize_hostname(strip_port(request.get_host()))
        except (DisallowedHost, ValidationError):
            return self.get_response(request)

        incoming_platform_domain = StoreDomain.objects.filter(
            store=store,
            hostname=hostname,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            retired_at__isnull=True,
        ).only("id").first()
        if incoming_platform_domain is None:
            return self.get_response(request)

        canonical_custom_domain = StoreDomain.objects.filter(
            store=store,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            retired_at__isnull=True,
        ).only("hostname").first()
        if canonical_custom_domain is None:
            return self.get_response(request)

        target = f"https://{canonical_custom_domain.hostname}{request.get_full_path()}"
        return HttpResponsePermanentRedirect(target)
