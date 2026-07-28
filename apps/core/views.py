from django.http import HttpResponseRedirect
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
    """
    target = f"/admin-portal/{rest}"
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        target = f"{target}?{query_string}"
    return HttpResponseRedirect(target)
