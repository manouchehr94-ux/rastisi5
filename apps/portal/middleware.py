"""Routes Rastisi's own platform-level hosts to a dedicated URLconf (ADR-97).

Additive only: a Host that isn't in ``settings.RASTISI_PLATFORM_HOSTS`` or
``settings.RASTISI_PLATFORM_ADMIN_HOSTS`` leaves ``request.urlconf`` unset,
so Django falls back to ``ROOT_URLCONF`` (the existing per-Store catalog/
dashboard routes) exactly as before this middleware existed. Never touches
``request.store`` or makes any authorization decision — this is routing
only, same spirit as ``apps.stores.middleware.StoreResolutionMiddleware``.
"""

from django.conf import settings
from django.core.exceptions import DisallowedHost

from apps.stores.resolution import strip_port


class PlatformHostRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            host = strip_port(request.get_host()).lower()
        except DisallowedHost:
            host = ""

        if host in settings.RASTISI_PLATFORM_ADMIN_HOSTS:
            request.urlconf = "shop_core.urls_platform_admin"
        elif host in settings.RASTISI_PLATFORM_HOSTS:
            request.urlconf = "shop_core.urls_platform"

        return self.get_response(request)
