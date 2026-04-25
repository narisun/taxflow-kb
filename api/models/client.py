"""Client Pydantic schemas — strict validation, sized to match the DB columns.

Every string field carries an explicit ``max_length`` mirroring the SQLAlchemy
column width so submissions that exceed the schema fail validation
(HTTP 422) instead of bubbling up as a database constraint error at commit.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from api.models.enums import FilingStatus, WorkflowStep


# ── shared validation helpers ────────────────────────────────────────────────

def _normalize_optional(value: str | None) -> str | None:
    """Treat blank/whitespace strings as None so the DB stores NULL."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_phone(v: str | None) -> str | None:
    v = _normalize_optional(v)
    if v is None:
        return None
    # Accept digits, spaces, dashes, parens, leading +. Allow 7–20 chars.
    import re
    if not re.fullmatch(r"[\d \-\(\)\+]{7,20}", v):
        raise ValueError(
            "phone must be 7–20 chars; digits, spaces, dashes, parens, leading + allowed"
        )
    return v


def _validate_state(v: str | None) -> str | None:
    v = _normalize_optional(v)
    if v is None:
        return None
    if len(v) != 2 or not v.isalpha():
        raise ValueError("state must be a 2-letter US state code (e.g. CA)")
    return v.upper()


def _validate_state_list(v: list[str] | None) -> list[str] | None:
    """Normalize a list of 2-letter state codes; deduped, uppercased, sorted."""
    if v is None:
        return None
    cleaned: set[str] = set()
    for raw in v:
        if not isinstance(raw, str):
            raise ValueError("filing_states entries must be strings")
        s = raw.strip().upper()
        if len(s) != 2 or not s.isalpha():
            raise ValueError(f"filing_states entry must be a 2-letter US state code, got {raw!r}")
        cleaned.add(s)
    return sorted(cleaned)


def _validate_zip(v: str | None) -> str | None:
    v = _normalize_optional(v)
    if v is None:
        return None
    import re
    if not re.fullmatch(r"\d{5}(-\d{4})?", v):
        raise ValueError("zip_code must be 5 or 9 digits (12345 or 12345-6789)")
    return v


def _validate_ssn(v: str | None) -> str | None:
    """Validate SSN format: NNN-NN-NNNN or NNNNNNNNN. Reject invalid IRS ranges."""
    v = _normalize_optional(v)
    if v is None:
        return None
    import re
    if not re.fullmatch(r"\d{3}-?\d{2}-?\d{4}", v):
        raise ValueError("SSN must be 9 digits, optionally formatted as NNN-NN-NNNN")
    digits = v.replace("-", "")
    area, group, serial = digits[:3], digits[3:5], digits[5:]
    if area == "000" or group == "00" or serial == "0000":
        raise ValueError("SSN contains an invalid zero segment")
    if area == "666" or int(area) >= 900:
        raise ValueError("SSN area number is in a reserved/invalid range")
    return v


def _validate_dob(v: str | None) -> str | None:
    """Validate DOB is a valid ISO date (YYYY-MM-DD)."""
    v = _normalize_optional(v)
    if v is None:
        return None
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("DOB must be in ISO format: YYYY-MM-DD")
    from datetime import date
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ValueError("DOB must be a valid date in YYYY-MM-DD format")
    return v


# ── create ───────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    primary_first_name: str | None = Field(default=None, max_length=100)
    primary_last_name: str | None = Field(default=None, max_length=100)
    filing_status: FilingStatus = "single"
    tax_year: int = Field(default=2025, ge=2000, le=2100)
    dependents: int = Field(default=0, ge=0, le=99)

    # PII
    primary_ssn: str | None = Field(default=None, max_length=20)
    primary_dob: str | None = Field(default=None, max_length=20)
    spouse_first_name: str | None = Field(default=None, max_length=100)
    spouse_last_name: str | None = Field(default=None, max_length=100)
    spouse_ssn: str | None = Field(default=None, max_length=20)
    spouse_dob: str | None = Field(default=None, max_length=20)

    # Address
    street: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=2)
    zip_code: str | None = Field(default=None, max_length=10)

    # Contact details — match DB column widths
    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    spouse_email: EmailStr | None = Field(default=None, max_length=254)
    spouse_phone: str | None = Field(default=None, max_length=20)

    family_group_name: str | None = Field(default=None, max_length=200)

    # Filing requirements
    filing_federal: bool = True
    filing_states: list[str] = Field(default_factory=list)

    @field_validator("phone", "spouse_phone")
    @classmethod
    def _v_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v)

    @field_validator("state")
    @classmethod
    def _v_state(cls, v: str | None) -> str | None:
        return _validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def _v_zip(cls, v: str | None) -> str | None:
        return _validate_zip(v)

    @field_validator("filing_states")
    @classmethod
    def _v_filing_states(cls, v: list[str]) -> list[str]:
        return _validate_state_list(v) or []

    @field_validator("primary_ssn", "spouse_ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        return _validate_ssn(v)

    @field_validator("primary_dob", "spouse_dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        return _validate_dob(v)


# ── update ───────────────────────────────────────────────────────────────────

class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    primary_first_name: str | None = Field(default=None, max_length=100)
    primary_last_name: str | None = Field(default=None, max_length=100)
    filing_status: FilingStatus | None = None
    workflow_step: WorkflowStep | None = None
    dependents: int | None = Field(default=None, ge=0, le=99)

    primary_ssn: str | None = Field(default=None, max_length=20)
    primary_dob: str | None = Field(default=None, max_length=20)
    spouse_first_name: str | None = Field(default=None, max_length=100)
    spouse_last_name: str | None = Field(default=None, max_length=100)
    spouse_ssn: str | None = Field(default=None, max_length=20)
    spouse_dob: str | None = Field(default=None, max_length=20)

    street: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=2)
    zip_code: str | None = Field(default=None, max_length=10)

    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    spouse_email: EmailStr | None = Field(default=None, max_length=254)
    spouse_phone: str | None = Field(default=None, max_length=20)

    # Filing requirements (None = leave unchanged on PATCH)
    filing_federal: bool | None = None
    filing_states: list[str] | None = None

    @field_validator("phone", "spouse_phone")
    @classmethod
    def _v_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v)

    @field_validator("state")
    @classmethod
    def _v_state(cls, v: str | None) -> str | None:
        return _validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def _v_zip(cls, v: str | None) -> str | None:
        return _validate_zip(v)

    @field_validator("filing_states")
    @classmethod
    def _v_filing_states(cls, v: list[str] | None) -> list[str] | None:
        return _validate_state_list(v)

    @field_validator("primary_ssn", "spouse_ssn")
    @classmethod
    def _v_ssn(cls, v: str | None) -> str | None:
        return _validate_ssn(v)

    @field_validator("primary_dob", "spouse_dob")
    @classmethod
    def _v_dob(cls, v: str | None) -> str | None:
        return _validate_dob(v)


# ── response ─────────────────────────────────────────────────────────────────

class ClientResponse(BaseModel):
    id: str
    name: str
    primary_first_name: str | None = None
    primary_last_name: str | None = None
    filing_status: str
    tax_year: int
    dependents: int
    workflow_step: str
    primary_ssn_masked: str = ""
    primary_dob_masked: str = ""
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn_masked: str = ""
    spouse_dob_masked: str = ""
    street_masked: str = ""
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    email: str | None = None
    phone: str | None = None
    spouse_email: str | None = None
    spouse_phone: str | None = None
    family_group_name: str | None = None
    filing_federal: bool = True
    filing_states: list[str] = Field(default_factory=list)
    org_id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
    page: int = 1
    page_size: int = 50


class PIIRevealRequest(BaseModel):
    fields: list[str]
