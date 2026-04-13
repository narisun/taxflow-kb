from pydantic import BaseModel
from datetime import datetime


class ClientCreate(BaseModel):
    name: str
    filing_status: str = "single"
    tax_year: int = 2025
    dependents: int = 0


class ClientUpdate(BaseModel):
    name: str | None = None
    filing_status: str | None = None
    workflow_step: str | None = None
    dependents: int | None = None


class ClientResponse(BaseModel):
    id: int
    name: str
    filing_status: str
    tax_year: int
    dependents: int
    workflow_step: str
    org_id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
