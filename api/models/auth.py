"""Pydantic schemas for authentication and onboarding."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class UserResponse(BaseModel):
    id: str
    org_id: str | None = None
    email: str
    name: str
    role: str
    is_active: bool
    onboarding_status: Literal["pending", "complete"]
    timezone: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserResponse
    organization: Optional[OrganizationResponse] = None
    permissions: dict[str, bool]


# ── Profile update ─────────────────────────────────────────────────────────


class ProfileUpdatePayload(BaseModel):
    """Body of PATCH /api/auth/profile — editable profile fields."""

    timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from zoneinfo import available_timezones
        if v not in available_timezones():
            raise ValueError(f"Invalid IANA timezone: {v}")
        return v


# ── Onboarding ──────────────────────────────────────────────────────────────


class OnboardingPayload(BaseModel):
    """Body of POST /api/auth/complete-onboarding.

    Industry-standard split: Auth0 only owns identity (email/password).
    Everything below is collected by the in-app wizard on first login.
    """

    firm_name: str = Field(min_length=2, max_length=200)
    role: Literal["admin", "supervisor", "preparer", "analyst"] = "admin"
    timezone: Optional[str] = Field(default=None, max_length=64)
    # Reserved for Phase 2 ("join existing firm" via emailed invite link).
    invite_token: Optional[str] = Field(default=None, max_length=200)

    @field_validator("firm_name")
    @classmethod
    def _strip_firm_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("firm_name must not be blank")
        return cleaned
