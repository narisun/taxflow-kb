"""Person, Dependent, and Address models for tax filing unit."""
import re
from datetime import date

from pydantic import BaseModel, field_validator


def _validate_ssn(ssn: str) -> str:
    """Validate SSN: 9 digits, no all-zero groups (area/group/serial)."""
    if not re.fullmatch(r"\d{9}", ssn):
        raise ValueError("SSN must be exactly 9 digits")
    area, group, serial = ssn[:3], ssn[3:5], ssn[5:]
    if area == "000" or group == "00" or serial == "0000":
        raise ValueError("SSN cannot have all-zero area, group, or serial")
    return ssn


class Person(BaseModel):
    first_name: str
    last_name: str
    ssn: str
    date_of_birth: date
    is_blind: bool = False

    @field_validator("ssn")
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        return _validate_ssn(v)


class Dependent(BaseModel):
    first_name: str
    last_name: str
    ssn: str
    relationship: str
    date_of_birth: date
    months_lived_with: int = 12
    is_student: bool = False
    is_qualifying_child: bool = True
    is_us_citizen: bool = True

    @field_validator("ssn")
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        return _validate_ssn(v)

    @field_validator("months_lived_with")
    @classmethod
    def validate_months(cls, v: int) -> int:
        if not 0 <= v <= 12:
            raise ValueError("months_lived_with must be between 0 and 12")
        return v


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str
    apt: str | None = None

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        if not re.fullmatch(r"\d{5}(\d{4})?", v):
            raise ValueError("zip_code must be 5 or 9 digits")
        return v
