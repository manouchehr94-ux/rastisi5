from django.http import HttpResponseRedirect
from django.templatetags.static import static

from .models import ShopSettings


def favicon_view(request):
    """Redirect /favicon.ico to configured or default favicon."""
    shop = ShopSettings.load()
    if shop.favicon:
        return HttpResponseRedirect(shop.favicon.url)
    return HttpResponseRedirect(static("favicon.ico"))
