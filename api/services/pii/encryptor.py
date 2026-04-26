"""PII encryption service using Fernet (AES-128-CBC).

All PII (SSN, DOB, street address) is encrypted before storage
and decrypted only when needed. API responses show masked values.

Architecture:
- :class:`PIIEncryptor` is pure and takes the key in its constructor — makes it
  trivially testable.
- :func:`build_pii_encryptor` is the only factory that reads configuration; it
  is wired into FastAPI through ``api.dependencies.get_pii_encryptor``.
- Legacy callers can still use :func:`get_pii_encryptor` which reads
  :class:`api.config.Settings`. New code SHOULD inject ``PIIEncryptor`` rather
  than call the module-level factory.
"""
from __future__ import annotations

import json
from datetime import date

from cryptography.fernet import Fernet


class ConfigError(RuntimeError):
    """Raised when the runtime configuration is invalid (missing secret, etc.)."""


# Deterministic key used ONLY when APP_ENV is development/test and
# PII_ENCRYPTION_KEY is not provided. Ensures test fixtures and dev data
# round-trip without forcing each developer to generate a key.
_DEV_FALLBACK_KEY = b"1GSIXE2641DMBbBishzM5Oa6f9DqLzzmsD6m0I1RqPk="


class PIIEncryptor:
    """Encrypts and decrypts PII fields using Fernet symmetric encryption."""

    def __init__(self, key: bytes):
        self.fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self.fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        return self.fernet.decrypt(ciphertext).decode("utf-8")

    def encrypt_json(self, data: dict) -> bytes:
        return self.encrypt(json.dumps(data))

    def decrypt_json(self, ciphertext: bytes) -> dict:
        return json.loads(self.decrypt(ciphertext))

    @staticmethod
    def mask_ssn(ssn: str | None) -> str:
        if not ssn:
            return ""
        last4 = ssn[-4:] if len(ssn) >= 4 else ssn
        return f"***-**-{last4}"

    @staticmethod
    def mask_dob(dob: date | None) -> str:
        if not dob:
            return ""
        if isinstance(dob, str):
            year = dob.split("-")[0] if "-" in dob else dob[-4:]
            return f"**/**/{year}"
        return f"**/**/{dob.year}"

    @staticmethod
    def mask_address(street: str | None) -> str:
        if not street:
            return ""
        visible = street[:5] if len(street) >= 5 else street
        return f"{visible}***"


def build_pii_encryptor(
    *,
    key: str | None,
    is_production: bool,
) -> PIIEncryptor:
    """Factory — builds an encryptor for a given configuration.

    Pure function: given the same inputs, returns an equivalent encryptor.
    Callers (typically :mod:`api.dependencies`) are responsible for sourcing
    ``key`` and ``is_production`` from :class:`api.config.Settings`.
    """
    if key:
        return PIIEncryptor(key.encode())
    if is_production:
        raise ConfigError(
            "PII_ENCRYPTION_KEY is required in production. "
            "Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return PIIEncryptor(_DEV_FALLBACK_KEY)


def get_pii_encryptor() -> PIIEncryptor:
    """Legacy module-level factory — delegates to :class:`api.config.Settings`.

    Prefer dependency-injection via ``api.dependencies.get_pii_encryptor`` for
    new code. This shim exists so existing call sites continue to work during
    the migration.
    """
    from api.config import get_settings

    settings = get_settings()
    return build_pii_encryptor(
        key=settings.pii_encryption_key.get_secret_value(),
        is_production=settings.is_production,
    )
