"""URLconf for Rastisi's own platform-level host (marketing site + owner
portal) — see ``apps.portal.middleware.PlatformHostRoutingMiddleware`` and
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-97. Only
ever active on a Host listed in ``settings.RASTISI_PLATFORM_HOSTS``;
every other Host keeps using ``shop_core.urls`` (ROOT_URLCONF) untouched.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.portal.views import not_found as handler404  # noqa: F401 — Django urlconf convention

urlpatterns = [
    path("", include("apps.portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
