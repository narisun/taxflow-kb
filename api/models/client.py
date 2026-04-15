"""Client Pydantic schemas with PII support."""
from pydantic import BaseModel, Field
from datetime import datetime
from api.models.enums import FilingStatus, WorkflowStep


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    filing_status: FilingStatus = "single"
    tax_year: int = Field(default=2025, ge=2000, le=2100)
    dependents: int = Field(default=0, ge=0, le=99)
    primary_ssn: str | None = None
    primary_dob: str | None = None
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn: str | None = None
    spouse_dob: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    family_group_name: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    filing_status: FilingStatus | None = None
    workflow_step: WorkflowStep | None = None
    dependents: int | None = Field(default=None, ge=0, le=99)
    primary_ssn: str | None = None
    primary_dob: str | None = None
    spouse_first_name: str | None = None
    spouse_last_name: str | None = None
    spouse_ssn: str | None = None
    spouse_dob: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


class ClientResponse(BaseModel):
    id: int
    name: str
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
    family_group_name: str | None = None
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
