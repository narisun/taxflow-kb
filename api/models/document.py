"""Document-related Pydantic schemas."""
from pydantic import BaseModel
from datetime import datetime

from api.models.enums import FormType, DocumentStatus


class DocumentResponse(BaseModel):
    id: str
    client_id: str
    form_type: str
    title: str
    status: str
    confidence: float
    extracted_data: str  # JSON string
    flags: str  # JSON string
    file_name: str = ""
    created_at: datetime
    created_by: str | None = None
    created_by_name: str | None = None
    # Review audit
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    reviewed_by_name: str | None = None
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
