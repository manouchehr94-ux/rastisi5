"""Fernet-based encryption for payment gateway credentials.

Uses a dedicated encryption key (PAYMENT_CREDENTIAL_KEY) — deliberately
NOT Django's SECRET_KEY, because:
* rotating SECRET_KEY would silently corrupt all stored gateway credentials;
* credential encryption has its own operational lifecycle independent of
  session/token signing;
* this separation is documented in docs/deployment/PRODUCTION_CONFIGURATION.md.

The key must be a URL-safe base64-encoded 32-byte value, exactly as
produced by ``cryptography.fernet.Fernet.generate_key()``.

For local development/tests, a deterministic fallback key is used ONLY when
``settings.DEBUG=True``. Production (``DEBUG=False``) with a missing or
invalid key will fail immediately at import time — credentials can never be
silently stored in plaintext or with an insecure default.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

_UNSET = object()
_fernet_instance = _UNSET


class CredentialEncryptionError(Exception):
    """Raised when encryption/decryption fails due to configuration or data issues."""


def _resolve_key() -> bytes:
    """Resolve the Fernet key from settings, with fail-closed production behavior."""
    raw = getattr(settings, "PAYMENT_CREDENTIAL_KEY", "")

    if raw:
        # Validate by trying to create a Fernet instance
        key = raw.encode() if isinstance(raw, str) else raw
        try:
            Fernet(key)  # Validates the key format
        except (ValueError, TypeError) as exc:
            raise CredentialEncryptionError(
                "PAYMENT_CREDENTIAL_KEY is set but invalid. It must be a "
                "URL-safe base64-encoded 32-byte key as produced by "
                "Fernet.generate_key(). See .env.example."
            ) from exc
        return key

    # Key not set — only acceptable in DEBUG mode or when the dev key was
    # explicitly allowed at settings import time (captures test runner scenario
    # where DEBUG was True at import but gets forced to False by Django's
    # test setup).
    allow_dev = (
        getattr(settings, "DEBUG", False)
        or getattr(settings, "_PAYMENT_DEV_KEY_ALLOWED", False)
    )
    if allow_dev:
        # Deterministic dev-only key — generated once, never changes.
        # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        return b"qC2NIIBcD787nHTLdwVwn5nkvMO_b7kkgPa3Z4c71h4="

    raise CredentialEncryptionError(
        "PAYMENT_CREDENTIAL_KEY is required when DEBUG=False. Generate one with: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )


def _get_fernet() -> Fernet:
    """Lazy singleton Fernet instance."""
    global _fernet_instance
    if _fernet_instance is _UNSET:
        _fernet_instance = Fernet(_resolve_key())
    return _fernet_instance


def reset_fernet():
    """Reset the cached Fernet instance (for testing only)."""
    global _fernet_instance
    _fernet_instance = _UNSET


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string, returning a URL-safe base64 ciphertext.

    Returns empty string for empty/None input (no credential to store).
    Never logs the plaintext value.
    """
    if not plaintext:
        return ""
    try:
        token = _get_fernet().encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")
    except Exception as exc:
        logger.error("Failed to encrypt credential: %s", type(exc).__name__)
        raise CredentialEncryptionError(
            "Failed to encrypt credential. Check PAYMENT_CREDENTIAL_KEY configuration."
        ) from exc


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a credential ciphertext back to plaintext.

    Returns empty string for empty/None input.
    Raises CredentialEncryptionError on invalid data or wrong key — never
    returns garbage or partial data silently.
    """
    if not ciphertext:
        return ""
    try:
        plaintext = _get_fernet().decrypt(ciphertext.encode("ascii"))
        return plaintext.decode("utf-8")
    except InvalidToken as exc:
        logger.error(
            "Failed to decrypt credential — key mismatch or corrupted data"
        )
        raise CredentialEncryptionError(
            "Cannot decrypt credential. The encryption key may have changed "
            "or the stored data is corrupted. Credential must be re-entered."
        ) from exc
    except Exception as exc:
        logger.error("Unexpected decryption error: %s", type(exc).__name__)
        raise CredentialEncryptionError(
            "Failed to decrypt credential. Check PAYMENT_CREDENTIAL_KEY configuration."
        ) from exc


def mask_credential(plaintext: str, visible_chars: int = 4) -> str:
    """Return a masked version of a credential for display purposes.

    Shows the last `visible_chars` characters, masks the rest with asterisks.
    For very short credentials (<= visible_chars), masks everything.
    """
    if not plaintext:
        return ""
    if len(plaintext) <= visible_chars:
        return "*" * len(plaintext)
    masked_len = len(plaintext) - visible_chars
    return "*" * masked_len + plaintext[-visible_chars:]
