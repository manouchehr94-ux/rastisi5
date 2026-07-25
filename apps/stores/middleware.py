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

from .resolution import resolve_store_for_request


class StoreResolutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = resolve_store_for_request(request)
        return self.get_response(request)
