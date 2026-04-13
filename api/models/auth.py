"""Pydantic schemas for authentication responses."""

from pydantic import BaseModel
from datetime import datetime


class UserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    name: str
    role: str
    is_active: bool
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
    organization: OrganizationResponse
    permissions: dict[str, bool]
