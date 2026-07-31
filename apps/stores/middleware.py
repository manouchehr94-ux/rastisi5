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
"""

from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect

from .resolution import resolve_store_domain_for_request_or_none, resolve_store_for_request


class StoreResolutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = resolve_store_for_request(request)
        return self.get_response(request)


#: HTTP methods for which a 301 (not 308) is used on a retired-hostname
#: redirect. GET/HEAD are always safe to permanently redirect; every other
#: method uses 308 so the method and body are preserved rather than silently
#: downgraded to GET by some clients (ADR-96).
_SAFE_METHODS_FOR_301 = frozenset({"GET", "HEAD"})


class HostnameRedirectMiddleware:
    """Permanently redirects a Store's retired hostname to its current
    primary domain (ADR-96).

    Runs after ``StoreResolutionMiddleware``. Looks up the matched
    ``StoreDomain`` for the request's Host a second time (cheap, single
    indexed lookup) only to read ``is_redirect`` — ``request.store`` itself
    is untouched, so every existing view keeps working exactly as before on
    every hostname that isn't a redirect alias (the overwhelming majority).
    A redirect alias with no eligible primary domain on its Store (should
    never happen given ``uniq_primary_domain_per_store`` plus the subdomain-
    claim service always setting a new primary before aliasing the old one,
    but defensively) falls through to the normal view instead of redirecting
    to nothing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        domain = resolve_store_domain_for_request_or_none(request)
        if domain is not None and domain.is_redirect:
            primary = domain.store.domains.filter(is_primary=True).first()
            if primary is not None:
                target = f"{request.scheme}://{primary.hostname}{request.get_full_path()}"
                redirect_cls = (
                    HttpResponsePermanentRedirect
                    if request.method in _SAFE_METHODS_FOR_301
                    else _PermanentRedirectPreservingMethod
                )
                return redirect_cls(target)
        return self.get_response(request)


class _PermanentRedirectPreservingMethod(HttpResponseRedirect):
    """A 308 Permanent Redirect — like ``HttpResponsePermanentRedirect``
    (301) but preserves the original HTTP method/body on the client, unlike
    301 which some clients silently downgrade to GET."""

    status_code = 308
