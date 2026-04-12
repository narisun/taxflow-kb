"""Document-related Pydantic schemas."""
from pydantic import BaseModel
from datetime import datetime


class DocumentResponse(BaseModel):
    id: int
    client_id: int
    form_type: str
    title: str
    status: str
    confidence: float
    extracted_data: str  # JSON string
    flags: str  # JSON string
    created_at: datetime
    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class ExtractedField(BaseModel):
    name: str
    value: str
    confidence: float
    flagged: bool = False
    flag_reason: str = ""


class ExtractionResult(BaseModel):
    fields: list[ExtractedField]
    overall_confidence: float
    has_flags: bool
    flags: list[str]
