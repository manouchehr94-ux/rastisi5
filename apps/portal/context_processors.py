from django.conf import settings


def turnstile(request):
    """Expose only the public Turnstile sitekey to templates."""
    return {
        "turnstile_enabled": bool(getattr(settings, "TURNSTILE_ENABLED", False)),
        "turnstile_site_key": str(getattr(settings, "TURNSTILE_SITE_KEY", "") or ""),
    }


def platform_enamad_verification(request):
    """Expose a validated eNamad meta only on the platform marketing homepage."""
    if getattr(request, "path", "") != "/":
        return {}

    try:
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    except Exception:
        return {}

    platform_hosts = {
        str(value).lower().rstrip(".")
        for value in getattr(settings, "RASTISI_PLATFORM_HOSTS", ())
    }
    if host not in platform_hosts:
        return {}

    from apps.portal.services.platform_config_service import (
        get_platform_configuration,
    )
    from apps.stores.services.enamad_verification_service import (
        EnamadVerificationMetaError,
        parse_enamad_verification_meta_tag,
    )

    raw = get_platform_configuration().enamad_verification_meta_tag
    try:
        meta = parse_enamad_verification_meta_tag(raw)
    except EnamadVerificationMetaError:
        return {}
    if meta is None:
        return {}

    return {
        "PLATFORM_ENAMAD_VERIFICATION_META_NAME": meta.name,
        "PLATFORM_ENAMAD_VERIFICATION_META_CONTENT": meta.content,
    }
