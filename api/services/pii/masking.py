"""PII masking helpers for data that must stay searchable in plaintext.

``documents.extracted_data`` is kept as a plaintext JSON Text column today for
backward compatibility with routers/UI that read it directly (fields endpoint,
assembler). Until the migration to encrypted-only storage (Phase C), any SSN
value in that payload must be masked before persistence. The encrypted column
still carries the unmasked data.

Usage:
    from api.services.pii.masking import mask_ssns_in_payload
    plaintext = mask_ssns_in_payload(raw_dict)
"""
from __future__ import annotations

import re
from typing import Any

# Matches 9-digit SSN formats:
#   "123-45-6789", "123456789", "123 45 6789"
# Avoids matching longer digit runs (phone numbers, account numbers).
_SSN_RE = re.compile(r"(?<!\d)(\d{3})[- ]?(\d{2})[- ]?(\d{4})(?!\d)")

# Key names whose *values* are treated as SSNs even if the value happens not to
# match the regex (e.g., partially-entered form data). EINs are deliberately
# excluded — they are public identifiers and share the 9-digit shape but fail
# SSN-specific validators (see W2.employer_ein).
_SSN_KEY_HINTS = (
    "ssn",
    "social_security",
)


def _mask_ssn_string(ssn: str) -> str:
    """Return ``***-**-####`` given any SSN-shaped value."""
    digits = re.sub(r"\D", "", ssn)
    if len(digits) < 4:
        return "***-**-****"
    return f"***-**-{digits[-4:]}"


def _looks_like_ssn_key(key: str) -> bool:
    lower = key.lower()
    return any(hint in lower for hint in _SSN_KEY_HINTS)


def _mask_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        if _looks_like_ssn_key(key):
            return _mask_ssn_string(value)
        # Mask inline SSN-shaped substrings regardless of key.
        return _SSN_RE.sub(lambda m: _mask_ssn_string(m.group(0)), value)
    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(key, v) for v in value]
    return value


def mask_ssns_in_payload(data: Any) -> Any:
    """Return a deep-copied payload with all SSN-shaped values masked.

    Safe to call on ``dict``, ``list``, or scalar; non-string scalars are
    returned unchanged. The input is not mutated.
    """
    if isinstance(data, dict):
        return {k: _mask_value(k, v) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_value("", v) for v in data]
    return _mask_value("", data)
