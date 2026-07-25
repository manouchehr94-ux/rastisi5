"""Authoritative hostname normalization for ``StoreDomain``.

This is the single reusable normalization function for Store domains. It is
called from the model write path (``StoreDomain.save()``/``clean()``) so
that no code path — admin, shell, data migration, or a future API — can
persist an un-normalized or malformed hostname. Do not duplicate this logic
elsewhere; import and call this function instead.

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
