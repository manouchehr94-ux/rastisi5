"""Cloudflare Turnstile server-side validation."""

from dataclasses import dataclass
import logging

import requests
from django.conf import settings

from apps.core.services.rate_limit import client_ip_or_unknown

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
RESPONSE_FIELD = "cf-turnstile-response"
MAX_TOKEN_LENGTH = 2048
PUBLIC_ERROR_MESSAGE = "تأیید امنیتی ناموفق بود؛ لطفاً دوباره تلاش کنید."


@dataclass(frozen=True)
class TurnstileValidationResult:
    success: bool
    error_code: str = ""
    hostname: str = ""
    action: str = ""
    skipped: bool = False


def _normalized_hostname(value: str) -> str:
    return str(value or "").strip().lower().rstrip(".")


def verify_token(*, token: str, remote_ip: str = "", expected_action: str = ""):
    if not getattr(settings, "TURNSTILE_ENABLED", False):
        return TurnstileValidationResult(success=True, skipped=True)

    token = str(token or "").strip()
    if not token:
        return TurnstileValidationResult(False, "missing-token")
    if len(token) > MAX_TOKEN_LENGTH:
        return TurnstileValidationResult(False, "token-too-long")

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = str(remote_ip)

    try:
        response = requests.post(
            SITEVERIFY_URL,
            data=payload,
            timeout=max(
                1,
                int(getattr(settings, "TURNSTILE_VERIFY_TIMEOUT_SECONDS", 5)),
            ),
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(
            "Turnstile Siteverify request failed: %s",
            exc.__class__.__name__,
        )
        return TurnstileValidationResult(False, "siteverify-unavailable")

    if not isinstance(result, dict):
        return TurnstileValidationResult(False, "invalid-siteverify-response")

    if not bool(result.get("success")):
        codes = result.get("error-codes") or []
        code = str(codes[0]) if codes else "verification-failed"
        return TurnstileValidationResult(False, code)

    action = str(result.get("action") or "")
    hostname = _normalized_hostname(result.get("hostname"))

    if expected_action and action != expected_action:
        return TurnstileValidationResult(
            False, "action-mismatch", hostname=hostname, action=action
        )

    expected_hostnames = {
        _normalized_hostname(value)
        for value in getattr(settings, "TURNSTILE_EXPECTED_HOSTNAMES", ())
        if _normalized_hostname(value)
    }
    if expected_hostnames and hostname not in expected_hostnames:
        return TurnstileValidationResult(
            False, "hostname-mismatch", hostname=hostname, action=action
        )

    return TurnstileValidationResult(
        True, hostname=hostname, action=action
    )


def verify_request(request, *, expected_action: str):
    # همان هلپرِ مرکزیِ apps.core.services.rate_limit — یک محلِ واحد برایِ
    # استخراجِ IPِ کلاینت در کلِ کدبیس، پشتِ همان RASTISI_TRUST_PROXY_
    # CLIENT_IP. "unknown" (فالبکِ استانداردِ آن هلپر) عمداً به رشته‌ی
    # خالی نگاشت می‌شود، نه به Cloudflare فرستاده می‌شود: verify_token فقط
    # وقتی remote_ip truthy باشد فیلدِ اختیاریِ "remoteip" را می‌سازد؛
    # فرستادنِ رشته‌ی "unknown" یک مقدارِ نامعتبر به یک API خارجی می‌بود.
    ip_address = client_ip_or_unknown(request)
    return verify_token(
        token=request.POST.get(RESPONSE_FIELD, ""),
        remote_ip=ip_address if ip_address != "unknown" else "",
        expected_action=expected_action,
    )
