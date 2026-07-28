from django.http import Http404, HttpResponseRedirect
from django.templatetags.static import static

from .models import ShopSettings


def favicon_view(request):
    """Redirect /favicon.ico to configured or default favicon."""
    shop = ShopSettings.load(store=getattr(request, "store", None))
    if shop.favicon:
        return HttpResponseRedirect(shop.favicon.url)
    return HttpResponseRedirect(static("favicon.ico"))


def admin_panel_compat_redirect(request, rest=""):
    """Temporary backward-compatible redirect: ``/admin-panel/...`` → ``/admin-portal/...``.

    ``/admin-portal/`` is the canonical Merchant Admin Portal route as of
    Phase 1B (see ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-16).
    ``/admin-panel/`` was the original path; rather than break every
    existing bookmark/link/integration outright, it 302-redirects here
    (never 301 — this is a deliberately temporary compatibility shim, not a
    permanent canonical alias, so it must stay easy to remove later without
    browsers having cached a permanent redirect) to the equivalent
    ``/admin-portal/`` path, preserving both the sub-path and query string.

    Phase 1C: obeys the exact same admin-host restriction as the canonical
    route itself (``apps.dashboard.decorators.staff_required``/``admin_host_required``)
    — a request on a disallowed host (a Store's public storefront domain,
    an unknown subdomain, ...) gets 404 directly here instead of being
    redirected to a canonical-route URL that would only 404 one hop later.
    That extra hop would also needlessly confirm to an attacker that
    *something* is mounted at ``/admin-portal/`` on this host.
    """
    from apps.stores.resolution import resolve_store_for_admin_request

    if resolve_store_for_admin_request(request) is None:
        raise Http404

    target = f"/admin-portal/{rest}"
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        target = f"{target}?{query_string}"
    return HttpResponseRedirect(target)
