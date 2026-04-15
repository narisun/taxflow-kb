"""PII encryption service using Fernet (AES-128-CBC).

All PII (SSN, DOB, street address) is encrypted before storage
and decrypted only when needed. API responses show masked values.
"""
import json
import os
from datetime import date

from cryptography.fernet import Fernet

# Dev-only key — NOT SECURE. Used when PII_ENCRYPTION_KEY is not set.
# Generate a real key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_DEV_KEY = Fernet.generate_key()  # Random key per process in dev


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
            # Handle ISO string
            year = dob.split("-")[0] if "-" in dob else dob[-4:]
            return f"**/**/{year}"
        return f"**/**/{dob.year}"

    @staticmethod
    def mask_address(street: str | None) -> str:
        if not street:
            return ""
        visible = street[:5] if len(street) >= 5 else street
        return f"{visible}***"


def get_pii_encryptor() -> PIIEncryptor:
    """Get a PIIEncryptor instance. Uses dev key if PII_ENCRYPTION_KEY not set."""
    key_str = os.getenv("PII_ENCRYPTION_KEY")
    if key_str:
        key = key_str.encode()
    else:
        key = _DEV_KEY
    return PIIEncryptor(key)
