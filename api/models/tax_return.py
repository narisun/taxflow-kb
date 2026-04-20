"""Tax return Pydantic schemas."""
from pydantic import BaseModel

from api.models.enums import FilingStatus, ReturnSection


class ReturnLine(BaseModel):
    number: str        # "1a", "2b", "9", "12", "15", "16", "19", "24", "25", "35a"
    label: str         # "Total wages, salaries, tips"
    value: float       # 185200.00
    section: ReturnSection = "income"


class TaxReturnDraft(BaseModel):
    client_id: str
    tax_year: int
    filing_status: str
    lines: list[ReturnLine]
    total_income: float
    total_deductions: float
    taxable_income: float
    total_tax: float
    total_payments: float
    refund_or_owed: float
    effective_rate: float
    validation_results: list[dict] = []
    computed_at: str | None = None


class FormManifestEntry(BaseModel):
    id: str
    label: str
    active: bool
    start_page: int | None
    page_count: int


class ReturnManifest(BaseModel):
    total_pages: int
    forms: list[FormManifestEntry]
