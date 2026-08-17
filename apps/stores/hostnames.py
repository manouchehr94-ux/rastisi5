"""Authoritative hostname normalization for ``StoreDomain``.

This is the single reusable normalization function for Store domains. It is
called from every write path ``apps.stores.models.StoreDomain`` exposes:
``instance.save()``/``clean()`` for direct writes, and
``StoreDomainQuerySet.bulk_create()`` for bulk inserts. Plain
``QuerySet.update(hostname=...)`` cannot be normalized this way — a raw SQL
UPDATE never runs Python code — so it is rejected outright by
``StoreDomainQuerySet.update()`` with ``StoreDomainMutationError`` instead of
being allowed to silently persist a raw value. Do not duplicate this
normalization logic elsewhere; import and call this function instead.

Unicode / IDNA decision: internationalized domains are accepted, but are
always normalized to their ASCII-compatible (Punycode) form via Python's
built-in ``idna`` codec before being persisted or compared. This guarantees
that visually-identical inputs (typed in Unicode vs. already-encoded
Punycode) normalize to the exact same stored value, so uniqueness cannot be
bypassed by using a different representation of the same hostname. This is
a normalization decision only — it does not attempt to detect
Unicode-lookalike ("homograph") domains that are technically distinct
hostnames; that is a deferred question (see
``docs/architecture/SAAS_DOMAIN_DECISIONS.md``, ADR-4).
"""

import re

from django.core.exceptions import ValidationError

MAX_HOSTNAME_LENGTH = 253
MAX_LABEL_LENGTH = 63

_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_hostname(raw_value):
    """Normalize and validate a hostname, returning its canonical ASCII form.

    Raises ``django.core.exceptions.ValidationError`` for anything that is
    not a bare hostname (schemes, paths, queries, fragments, credentials,
    ports, malformed labels, empty values, or values exceeding DNS length
    limits).
    """
    if raw_value is None:
        raise ValidationError("نام میزبان الزامی است.", code="hostname_required")

    value = str(raw_value).strip()
    if not value:
        raise ValidationError("نام میزبان الزامی است.", code="hostname_required")

    if "://" in value or value.startswith("//"):
        raise ValidationError(
            "نام میزبان نباید شامل پروتکل (مثل http:// یا https://) باشد.",
            code="hostname_has_scheme",
        )
    if "@" in value:
        raise ValidationError(
            "نام میزبان نباید شامل نام کاربری/رمز عبور باشد.", code="hostname_has_credentials"
        )
    if "/" in value:
        raise ValidationError("نام میزبان نباید شامل مسیر (path) باشد.", code="hostname_has_path")
    if "?" in value:
        raise ValidationError(
            "نام میزبان نباید شامل رشته‌ی پرس‌وجو (query string) باشد.", code="hostname_has_query"
        )
    if "#" in value:
        raise ValidationError("نام میزبان نباید شامل fragment باشد.", code="hostname_has_fragment")
    if ":" in value:
        raise ValidationError("نام میزبان نباید شامل پورت باشد.", code="hostname_has_port")

    if value.endswith("."):
        value = value[:-1]
    if not value:
        raise ValidationError("نام میزبان الزامی است.", code="hostname_required")

    value = value.lower()

    try:
        ascii_value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError(
            "نام میزبان شامل نویسه‌های نامعتبر است.", code="hostname_invalid_characters"
        ) from exc

    if len(ascii_value) > MAX_HOSTNAME_LENGTH:
        raise ValidationError(
            "طول نام میزبان بیش از حد مجاز است.", code="hostname_too_long"
        )

    labels = ascii_value.split(".")
    if len(labels) < 2:
        raise ValidationError(
            "نام میزبان باید حداقل شامل یک نقطه باشد (مثل example.com).",
            code="hostname_missing_label",
        )
    for label in labels:
        if len(label) > MAX_LABEL_LENGTH or not _LABEL_RE.match(label):
            raise ValidationError(
                f"بخش «{label}» از نام میزبان معتبر نیست.", code="hostname_invalid_label"
            )

    return ascii_value


def rastisi_owned_domain_suffixes():
    """All DNS suffixes that are owned/reserved by Rastisi in this process.

    ``RASTISI_CANONICAL_DOMAIN_SUFFIX`` is the real platform identity
    (normally ``rastisi.ir``). ``RASTISI_ADMIN_DOMAIN_SUFFIX`` is the runtime
    sibling-host suffix (``rastisi.localhost`` in local development). Keeping
    both prevents DEBUG from accidentally treating a real ``*.rastisi.ir``
    hostname as a merchant custom domain.
    """
    from django.conf import settings

    values = {
        str(settings.RASTISI_CANONICAL_DOMAIN_SUFFIX).strip().lower().strip("."),
        str(settings.RASTISI_ADMIN_DOMAIN_SUFFIX).strip().lower().strip("."),
    }
    return frozenset(value for value in values if value)


def is_rastisi_owned_hostname(raw_hostname) -> bool:
    """Return True when ``raw_hostname`` is the platform domain itself or
    any subdomain below one of Rastisi's owned suffixes."""
    try:
        hostname = normalize_hostname(raw_hostname)
    except ValidationError:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in rastisi_owned_domain_suffixes()
    )


#: Subdomains that must never be assigned to a merchant Store's
#: ``admin_subdomain`` — either because the platform itself uses them
#: (``www``, ``api``, ``admin``, the panel/portal path names, ...), or
#: because they'd be confusing/spoofable (``mail``, ``support``, ...).
#: Mirrors the same intent as ``apps.content.models.RESERVED_SLUGS``, kept
#: as a separate list since these two namespaces (URL path slugs vs. DNS
#: subdomain labels) are independent.
def build_cross_host_url(request, *, hostname: str, path: str) -> str:
    """Build an absolute URL on a sibling host while preserving an explicit
    non-default port from the current request.

    This is primarily for local development, where the owner portal and
    merchant-admin hosts are different ``*.localhost`` names served by the
    same Django ``runserver`` port (for example ``:8000``). Production
    requests with no explicit port, or an explicit default 80/443 port,
    stay clean and do not gain a port suffix.
    """
    from urllib.parse import urlsplit

    parsed = urlsplit(f"//{request.get_host()}")
    port = parsed.port
    default_port = 443 if request.is_secure() else 80

    authority = hostname
    if port is not None and port != default_port:
        authority = f"{hostname}:{port}"

    if not path.startswith("/"):
        path = f"/{path}"

    return f"{request.scheme}://{authority}{path}"


RESERVED_ADMIN_SUBDOMAINS = frozenset({
    "www", "admin", "api", "app", "static", "media", "mail", "smtp", "ftp",
    "ns1", "ns2", "autodiscover", "rastisi", "dashboard", "panel", "portal",
    "support", "help", "status", "blog", "cdn", "assets", "docs", "shop",
    "store", "stores", "billing", "payments",
    # Platform-owned sibling services. ``chatchat.rastisi.ir`` is a separate
    # Rastisi project, never a Store. ``platformadmins`` is the operations host.
    "chatchat", "platformadmins",
})


def normalize_admin_subdomain(raw_value):
    """Normalize and validate a Store's stable merchant-admin subdomain label.

    Unlike ``normalize_hostname`` (a full, multi-label FQDN like
    ``example.com``), this validates exactly one DNS label — the part that
    goes before ``RASTISI_ADMIN_DOMAIN_SUFFIX`` (e.g. ``"digilool"`` in
    ``digilool.rastisi.ir``). Raises ``ValidationError`` for anything empty,
    too long, containing invalid characters, or on the reserved list.
    """
    if raw_value is None:
        raise ValidationError("زیردامنه‌ی مدیریت الزامی است.", code="admin_subdomain_required")

    value = str(raw_value).strip().lower()
    if not value:
        raise ValidationError("زیردامنه‌ی مدیریت الزامی است.", code="admin_subdomain_required")

    if len(value) > MAX_LABEL_LENGTH or not _LABEL_RE.match(value):
        raise ValidationError(
            "زیردامنه‌ی مدیریت باید فقط شامل حروف انگلیسی، رقم و خط تیره باشد "
            "(نه در ابتدا/انتها) و حداکثر ۶۳ نویسه.",
            code="admin_subdomain_invalid_characters",
        )

    if value in RESERVED_ADMIN_SUBDOMAINS:
        raise ValidationError(
            f"زیردامنه‌ی «{value}» رزرو شده و قابل استفاده نیست.",
            code="admin_subdomain_reserved",
        )

    return value


#: Reserved-word list for a paid owner's human-readable public subdomain
#: claim under ``RASTISI_ADMIN_DOMAIN_SUFFIX`` (Section J/K). Verbatim list
#: from the product decision, unioned with ``RESERVED_ADMIN_SUBDOMAINS`` —
#: any label already reserved by the existing merchant-admin routing must
#: stay reserved here too, not just the words newly listed for this surface.
RESERVED_PLATFORM_SUBDOMAINS = frozenset({
    "www", "admin", "administrator", "api", "app", "apps", "account",
    "accounts", "auth", "billing", "blog", "cdn", "checkout", "dashboard",
    "docs", "ftp", "help", "imap", "login", "logout", "mail", "media",
    "panel", "platform", "portal", "register", "registration", "root",
    "shop", "smtp", "static", "status", "store", "support", "system",
    "test", "wwwroot", "rastisi",
}) | RESERVED_ADMIN_SUBDOMAINS


def normalize_platform_subdomain_label(raw_value):
    """Normalize and validate a paid owner's chosen human-readable
    subdomain label (Section J) — same DNS-label rules as
    ``normalize_admin_subdomain``, but checked against the wider
    ``RESERVED_PLATFORM_SUBDOMAINS`` list. Returns just the label (e.g.
    ``"novinshop"``), not the full hostname — the caller builds
    ``f"{label}.{RASTISI_ADMIN_DOMAIN_SUFFIX}"``.
    """
    if raw_value is None:
        raise ValidationError("زیردامنه الزامی است.", code="platform_subdomain_required")

    value = str(raw_value).strip().lower()
    if not value:
        raise ValidationError("زیردامنه الزامی است.", code="platform_subdomain_required")

    if len(value) > MAX_LABEL_LENGTH or not _LABEL_RE.match(value):
        raise ValidationError(
            "زیردامنه باید فقط شامل حروف انگلیسی، رقم و خط تیره باشد "
            "(نه در ابتدا/انتها) و حداکثر ۶۳ نویسه.",
            code="platform_subdomain_invalid_characters",
        )

    if value in RESERVED_PLATFORM_SUBDOMAINS:
        raise ValidationError(
            f"زیردامنه‌ی «{value}» رزرو شده و قابل استفاده نیست.",
            code="platform_subdomain_reserved",
        )

    return value
