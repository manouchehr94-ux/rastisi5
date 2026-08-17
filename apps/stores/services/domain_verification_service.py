"""دامنه‌ی اختصاصیِ اختیاری (Section 12) — چهارمین مفهومِ متمایز §3.6-3.7
(جدا از نامِ نمایشی، نامِ دائمی روی rastisi.ir، و میزبانِ راستیسی).

قاعده‌ی مطلق: یک دامنه هرگز توسطِ خودِ تاجر «تأییدشده» علامت زده نمی‌شود —
تنها راهِ رسیدن به ``VERIFIED``، یک جست‌وجویِ واقعیِ رکوردِ DNS TXT است که
این ماژول خودش انجام می‌دهد (``dnspython``)، نه یک چک‌باکس در فرم. شکستِ
جست‌وجو هرگز چیزی را «تأییدشده» نمی‌کند و فاکتور را در همان وضعیتِ
``PENDING`` نگه می‌دارد تا تاجر بتواند دوباره تلاش کند."""

import secrets
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime

import dns.exception
import dns.resolver
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.hostnames import is_rastisi_owned_hostname, normalize_hostname
from apps.stores.models import Store, StoreDomain

VERIFICATION_RECORD_PREFIX = "_rastisi-verify"
VERIFICATION_VALUE_PREFIX = "rastisi-verify="
DNS_LOOKUP_TIMEOUT_SECONDS = 5.0
SSL_CHECK_TIMEOUT_SECONDS = 4.0


class DomainVerificationError(Exception):
    """خطای قابل‌نمایشِ درخواست/تأییدِ دامنه‌ی اختصاصی."""


def verification_record_name(hostname: str) -> str:
    return f"{VERIFICATION_RECORD_PREFIX}.{hostname}"


def _normalize_or_raise(raw_hostname: str) -> str:
    try:
        hostname = normalize_hostname(raw_hostname)
    except ValidationError as exc:
        raise DomainVerificationError("؛ ".join(exc.messages)) from exc

    if is_rastisi_owned_hostname(hostname):
        raise DomainVerificationError(
            "دامنه‌ی اختصاصی نمی‌تواند زیردامنه‌ای از خودِ راستیسی باشد؛ برای نامِ دائمی از "
            "بخشِ «نامِ دائمی فروشگاه» استفاده کنید."
        )
    return hostname


@transaction.atomic
def request_custom_domain(*, store: Store, hostname: str, actor) -> StoreDomain:
    """اولین گام: ثبتِ خودِ دامنه، بدونِ هیچ تأییدی هنوز."""
    normalized = _normalize_or_raise(hostname)
    try:
        domain = StoreDomain.objects.create(
            store=store, hostname=normalized, is_primary=False,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED,
        )
    except IntegrityError as exc:
        raise DomainVerificationError(f"دامنه‌ی «{normalized}» قبلاً در راستیسی ثبت شده است.") from exc

    record_audit_event(
        store=store, actor=actor, action_code="store.custom_domain_requested",
        object_type="StoreDomain", object_id=domain.pk, object_label=normalized,
    )
    return domain


@transaction.atomic
def begin_dns_verification(*, domain: StoreDomain, actor) -> StoreDomain:
    """توکنِ تأیید تازه می‌سازد و دامنه را به ``PENDING`` می‌برد — تاجر باید
    یک رکوردِ TXT به نامِ ``verification_record_name(domain.hostname)`` با
    مقدارِ ``rastisi-verify={token}`` در DNS خودش اضافه کند."""
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("فقط دامنه‌ی اختصاصی نیازِ تأییدِ DNS دارد.")
    if domain.verification_status == StoreDomain.VerificationStatus.VERIFIED:
        raise DomainVerificationError("این دامنه از قبل تأییدشده است.")

    locked = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    locked.verification_token = secrets.token_hex(16)
    locked.verification_status = StoreDomain.VerificationStatus.PENDING
    locked.verification_requested_at = timezone.now()
    locked.save(update_fields=[
        "verification_token", "verification_status", "verification_requested_at", "updated_at",
    ])
    return locked


def _txt_records_match(hostname: str, expected_value: str) -> bool:
    """جست‌وجویِ واقعیِ DNS — هرگز استثنا به بیرون نمی‌اندازد؛ هر خطای
    شبکه/تفکیک‌نام صرفاً «تطبیق نیافت» به‌حساب می‌آید."""
    record_name = verification_record_name(hostname)
    try:
        answers = dns.resolver.resolve(record_name, "TXT", lifetime=DNS_LOOKUP_TIMEOUT_SECONDS)
    except (dns.exception.DNSException, OSError):
        return False

    for rdata in answers:
        # هر رشته‌ی TXT ممکن است به چند بخشِ رشته‌ای تکه‌تکه شده باشد
        # (محدودیتِ ۲۵۵ نویسه‌ایِ هر رشته در پروتکلِ DNS)؛ باید بهم‌بچسبانیم.
        value = b"".join(rdata.strings).decode("utf-8", errors="replace")
        if value.strip() == expected_value:
            return True
    return False


@transaction.atomic
def check_dns_verification(*, domain: StoreDomain, actor) -> bool:
    """تأییدِ واقعیِ DNS را انجام می‌دهد. فقط در صورتِ یافتنِ رکوردِ TXT
    درست، ``VERIFIED`` می‌شود؛ در غیرِ این صورت بدونِ هیچ تغییری False
    برمی‌گرداند (قابلِ تلاشِ دوباره، هرگز قفل‌شده در حالتِ ناموفق)."""
    if domain.verification_status != StoreDomain.VerificationStatus.PENDING or not domain.verification_token:
        raise DomainVerificationError("این دامنه هنوز درخواستِ تأییدی ثبت نکرده است.")

    expected_value = f"{VERIFICATION_VALUE_PREFIX}{domain.verification_token}"
    if not _txt_records_match(domain.hostname, expected_value):
        return False

    locked = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    locked.verification_status = StoreDomain.VerificationStatus.VERIFIED
    locked.verified_at = timezone.now()
    locked.save(update_fields=["verification_status", "verified_at", "updated_at"])

    record_audit_event(
        store=locked.store, actor=actor, action_code="store.custom_domain_verified",
        object_type="StoreDomain", object_id=locked.pk, object_label=locked.hostname,
    )
    return True


@dataclass(frozen=True)
class SslConnectionCheck:
    """نتیجه‌ی «تستِ نهاییِ اتصال» — یک تشخیصِ صرفِ خواندنی، هیچ فیلدی از
    ``StoreDomain`` را تغییر نمی‌دهد (فعال‌سازی همچنان فقط از طریقِ
    ``activate_custom_domain`` انجام می‌شود، نه بر اساسِ نتیجه‌ی این تابع)."""

    reachable: bool
    certificate_expires_at: datetime | None
    error: str


def check_ssl_connection(hostname: str) -> SslConnectionCheck:
    """اتصالِ HTTPS واقعی به ``hostname:443`` را امتحان می‌کند — دقیقاً همان
    الگویِ ``_txt_records_match``: هرگز استثنا به بیرون نمی‌اندازد، هر خطای
    شبکه/گواهی صرفاً «در دسترس نیست» به‌حساب می‌آید، نه یک ۵۰۰."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=SSL_CHECK_TIMEOUT_SECONDS) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert()
    except Exception as exc:  # noqa: BLE001 — هر خطای شبکه/TLS/DNS باید بی‌صدا «ناموفق» شود
        return SslConnectionCheck(reachable=False, certificate_expires_at=None, error=str(exc))

    expires_at = None
    not_after = cert.get("notAfter") if cert else None
    if not_after:
        try:
            expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        except ValueError:
            expires_at = None
    return SslConnectionCheck(reachable=True, certificate_expires_at=expires_at, error="")


@transaction.atomic
def activate_custom_domain(*, store: Store, domain: StoreDomain, actor) -> StoreDomain:
    """دامنه‌ی اختصاصیِ تأییدشده را دامنه‌ی اصلیِ فروشگاه می‌کند.

    اگر دامنه‌ی اصلیِ قبلی ``PLATFORM_SUBDOMAIN`` باشد (مثلاً
    ``digilool.rastisi.ir``)، آن نام دائمی متعلق به همان Store باقی می‌ماند:
    فقط ``is_primary`` از آن برداشته می‌شود و بازنشسته نمی‌شود تا Middleware
    بتواند صفحات عمومی آن را به دامنه‌ی اختصاصی جدید 301 کند و
    ``/admin-portal/`` همچنان روی میزبان RastiSi قابل استفاده باشد.

    دامنه‌ی آزمایشی تصادفی و دامنه‌ی اختصاصی قدیمی، در صورت جایگزینی،
    همچنان بازنشسته می‌شوند. Step-up OTP
    (action=``custom_domain_activate``) در لایه‌ی ویو اعمال می‌شود، نه اینجا.
    """
    if domain.store_id != store.pk:
        raise DomainVerificationError("این دامنه متعلق به این فروشگاه نیست.")
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("فقط دامنه‌ی اختصاصیِ تأییدشده قابلِ فعال‌سازی است.")
    if domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
        raise DomainVerificationError("این دامنه هنوز تأیید نشده؛ ابتدا تأییدِ DNS را کامل کنید.")

    locked_store = Store.objects.select_for_update().get(pk=store.pk)
    old_primary = StoreDomain.objects.select_for_update().filter(store=locked_store, is_primary=True).first()
    if old_primary is not None and old_primary.pk != domain.pk:
        old_primary.is_primary = False
        update_fields = ["is_primary", "updated_at"]
        if old_primary.domain_type == StoreDomain.DomainType.PLATFORM_SUBDOMAIN:
            old_primary.retired_at = None
        else:
            old_primary.retired_at = timezone.now()
            update_fields.append("retired_at")
        old_primary.save(update_fields=update_fields)

    locked_domain = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    locked_domain.is_primary = True
    locked_domain.save(update_fields=["is_primary", "updated_at"])

    record_audit_event(
        store=locked_store, actor=actor, action_code="store.custom_domain_activated",
        object_type="StoreDomain", object_id=locked_domain.pk, object_label=locked_domain.hostname,
        before={"old_primary": old_primary.hostname if old_primary else None},
        after={"hostname": locked_domain.hostname},
    )
    return locked_domain
