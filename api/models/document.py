"""Document-related Pydantic schemas."""
from pydantic import BaseModel
from datetime import datetime

from api.models.enums import FormType, DocumentStatus


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
    page: int = 1
    page_size: int = 50


class ExtractedField(BaseModel):
    name: str               # Structured key: "box1_wages"
    value: str              # Clean value: "112400.00"
    confidence: float
    flagged: bool = False
    flag_reason: str = ""
    label: str = ""         # Display label, populated by router


class ExtractionResult(BaseModel):
    fields: list[ExtractedField]
    overall_confidence: float
    has_flags: bool
    flags: list[str]

    @property
    def structured_data(self) -> dict[str, str]:
        """Return model-ready dict of field name -> value."""
        return {f.name: f.value for f in self.fields}
