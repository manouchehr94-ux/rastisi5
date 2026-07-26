"""Environment-variable parsing and production-safety validation for ``shop_core.settings``.

These are plain functions with no side effects and no dependency on Django's
settings machinery — kept separate from ``settings.py`` specifically so they
can be unit-tested directly with arbitrary input dictionaries. ``settings.py``
is imported exactly once per process (by Django's own startup), so its
module-level code cannot be re-exercised with different environment variables
inside the same test run; the parsing/validation logic below can be, because
each function accepts an explicit ``environ`` mapping instead of always
reading the real ``os.environ``.
"""

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

# The literal key Django's ``startproject`` generated for this repository.
# Kept as the *only* allowed fallback, and only while DEBUG=True — production
# must never run with this (or any other hardcoded) key.
DEV_INSECURE_SECRET_KEY = "django-insecure-an#yw@3zj9_hmh3^9t&(4+eu^a8mwtbii9b68yus3q=xnu%f%i"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_SUPPORTED_DATABASE_URL_SCHEMES = {"postgres", "postgresql"}

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _environ(environ):
    return os.environ if environ is None else environ


def env_str(name, default="", *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None:
        return default
    return raw.strip()


def env_bool(name, default, *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f"Environment variable {name}={raw!r} is not a valid boolean "
        "(use one of: true/false, 1/0, yes/no, on/off)."
    )


def env_int(name, default, *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {name}={raw!r} is not a valid integer."
        ) from exc


def env_list(name, default=(), *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_secret_key(debug, *, environ=None):
    """Return the SECRET_KEY to use, enforcing production safety.

    Raises ``ImproperlyConfigured`` when ``debug`` is False and no real
    secret key is configured, or the configured value is the known
    development-only key.
    """
    secret_key = env_str("DJANGO_SECRET_KEY", "", environ=environ)
    if not secret_key:
        if debug:
            return DEV_INSECURE_SECRET_KEY
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when DJANGO_DEBUG=False. Generate one with "
            '`python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` '
            "and set it as an environment variable — never commit it."
        )
    if not debug and secret_key == DEV_INSECURE_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is set to the known development-only insecure key. "
            "Set a real, unique secret key before running with DJANGO_DEBUG=False."
        )
    return secret_key


def resolve_allowed_hosts(debug, *, environ=None):
    hosts = env_list("DJANGO_ALLOWED_HOSTS", default=(), environ=environ)
    if not debug and not hosts:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be set (comma-separated hostnames) when DJANGO_DEBUG=False."
        )
    return hosts


def resolve_secure_proxy_ssl_header(*, environ=None):
    """Return a ``SECURE_PROXY_SSL_HEADER`` tuple, or ``None`` if unconfigured.

    Only takes effect when explicitly set to a specific header/value pair —
    this must never be enabled unless the reverse proxy strips/overwrites the
    header for all client traffic, since Django trusts it unconditionally
    once configured.
    """
    raw = env_str("DJANGO_SECURE_PROXY_SSL_HEADER", "", environ=environ)
    if not raw:
        return None
    header_name, sep, header_value = raw.partition(":")
    header_name = header_name.strip()
    header_value = header_value.strip()
    if not sep or not header_name or not header_value:
        raise ImproperlyConfigured(
            "DJANGO_SECURE_PROXY_SSL_HEADER must be 'Header-Name:expected-value', "
            "e.g. 'X-Forwarded-Proto:https' — only set this if your reverse proxy "
            "strips/overwrites this header for all client traffic."
        )
    return (f"HTTP_{header_name.upper().replace('-', '_')}", header_value)


def build_database_config(base_dir, *, environ=None):
    """Build the ``DATABASES["default"]`` dict.

    Falls back to a local SQLite file under ``base_dir`` when ``DATABASE_URL``
    is unset (the local development/test default, unchanged from before this
    module existed). When ``DATABASE_URL`` is set, it must be a valid
    ``postgres://`` URL with a host and a database name — anything else
    raises ``ImproperlyConfigured`` rather than silently falling back to
    SQLite in what was meant to be a production deployment.
    """
    database_url = env_str("DATABASE_URL", "", environ=environ)
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(base_dir / "db.sqlite3"),
        }
    parsed = urlparse(database_url)
    if parsed.scheme not in _SUPPORTED_DATABASE_URL_SCHEMES:
        raise ImproperlyConfigured(
            f"DATABASE_URL scheme {parsed.scheme!r} is not supported; use postgres:// or postgresql://."
        )
    database_name = parsed.path.lstrip("/")
    if not parsed.hostname or not database_name:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a host and a database name, e.g. "
            "postgres://user:password@host:5432/dbname."
        )
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname,
        "PORT": str(parsed.port) if parsed.port else "",
    }


def resolve_log_level(*, environ=None):
    level = env_str("DJANGO_LOG_LEVEL", "INFO", environ=environ).upper()
    if level not in _VALID_LOG_LEVELS:
        raise ImproperlyConfigured(
            f"DJANGO_LOG_LEVEL={level!r} is invalid; use one of {sorted(_VALID_LOG_LEVELS)}."
        )
    return level
