"""Safe eNamad technical-domain verification helpers.

The eNamad dashboard may ask a site owner to place a verification ``<meta>``
tag on the site's home page. We never render merchant/platform supplied HTML
verbatim. The submitted snippet is parsed, must consist of one plain ``meta``
element with exactly ``name`` and ``content`` attributes, and the two values
are rendered through Django's normal auto-escaping.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re


class EnamadVerificationMetaError(ValueError):
    """The supplied technical-verification meta tag is unsafe or malformed."""


@dataclass(frozen=True)
class EnamadVerificationMeta:
    name: str
    content: str


_META_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_CONTENT_LENGTH = 1024


class _SingleMetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[list[tuple[str, str | None]]] = []
        self.invalid = False

    def _accept(self, tag, attrs):
        if tag.lower() != "meta" or self.elements:
            self.invalid = True
            return
        self.elements.append(attrs)

    def handle_starttag(self, tag, attrs):
        self._accept(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._accept(tag, attrs)

    def handle_endtag(self, tag):
        self.invalid = True

    def handle_data(self, data):
        if data.strip():
            self.invalid = True

    def handle_comment(self, data):
        self.invalid = True

    def handle_decl(self, decl):
        self.invalid = True

    def handle_pi(self, data):
        self.invalid = True


def parse_enamad_verification_meta_tag(raw: str) -> EnamadVerificationMeta | None:
    """Parse one safe ``<meta name="..." content="...">`` snippet."""
    raw = str(raw or "").strip()
    if not raw:
        return None

    parser = _SingleMetaParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:
        raise EnamadVerificationMetaError(
            "متاتگ اینماد قابل‌خواندن نیست."
        ) from exc

    if parser.invalid or len(parser.elements) != 1:
        raise EnamadVerificationMetaError(
            "فقط یک تگ meta ساده برای احراز اینماد مجاز است."
        )

    attrs = parser.elements[0]
    normalized: dict[str, str] = {}
    for key, value in attrs:
        key = (key or "").lower()
        if key not in {"name", "content"} or key in normalized or value is None:
            raise EnamadVerificationMetaError(
                "متاتگ اینماد فقط باید شامل دو ویژگی name و content باشد."
            )
        normalized[key] = value

    if set(normalized) != {"name", "content"}:
        raise EnamadVerificationMetaError(
            "متاتگ اینماد باید هر دو ویژگی name و content را داشته باشد."
        )

    name = normalized["name"].strip()
    content = normalized["content"].strip()

    if not _META_NAME_RE.fullmatch(name):
        raise EnamadVerificationMetaError(
            "مقدار name متاتگ اینماد معتبر نیست."
        )
    if not content:
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد نمی‌تواند خالی باشد."
        )
    if len(content) > _MAX_CONTENT_LENGTH:
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد بیش از حد طولانی است."
        )
    if any(ord(ch) < 32 and ch not in "\t\r\n" for ch in content):
        raise EnamadVerificationMetaError(
            "مقدار content متاتگ اینماد شامل نویسه‌ی کنترل نامعتبر است."
        )

    return EnamadVerificationMeta(name=name, content=content)


def validate_enamad_integration_values(values: dict) -> str | None:
    """Allow the pre-issuance meta tag or the existing post-issuance badge code."""
    meta_tag = str(values.get("verification_meta_tag") or "").strip()
    enamad_code = str(values.get("enamad_code") or "").strip()

    if not meta_tag and not enamad_code:
        return "متاتگ احراز فنی یا کد نماد اینماد را وارد کنید."

    if meta_tag:
        try:
            parse_enamad_verification_meta_tag(meta_tag)
        except EnamadVerificationMetaError as exc:
            return str(exc)

    if len(enamad_code) > 4000:
        return "کد نماد اینماد بیش از حد طولانی است."

    return None


def store_enamad_verification_meta_for_request(
    request, *, store_id: int
) -> EnamadVerificationMeta | None:
    """Expose the merchant meta only on that Store's verified custom homepage."""
    if getattr(request, "path", "") != "/":
        return None

    try:
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    except Exception:
        return None
    if not host:
        return None

    from apps.stores.models import StoreDomain, StoreIntegrationConnection

    domain_ok = StoreDomain.objects.filter(
        store_id=store_id,
        hostname=host,
        domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        retired_at__isnull=True,
    ).exists()
    if not domain_ok:
        return None

    connection = (
        StoreIntegrationConnection.objects
        .filter(store_id=store_id, provider_code="enamad", is_active=True)
        .only("encrypted_credentials")
        .first()
    )
    if connection is None:
        return None

    raw = connection.get_credentials().get("verification_meta_tag", "")
    try:
        return parse_enamad_verification_meta_tag(raw)
    except EnamadVerificationMetaError:
        return None
