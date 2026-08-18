from django.conf import settings


def turnstile(request):
    """Expose only the public Turnstile sitekey to templates."""
    return {
        "turnstile_enabled": bool(getattr(settings, "TURNSTILE_ENABLED", False)),
        "turnstile_site_key": str(getattr(settings, "TURNSTILE_SITE_KEY", "") or ""),
    }
