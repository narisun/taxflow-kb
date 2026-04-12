"""Tax return Pydantic schemas."""
from pydantic import BaseModel


class ReturnLine(BaseModel):
    number: str        # "1a", "2b", "9", "12", "15", "16", "19", "24", "25", "35a"
    label: str         # "Total wages, salaries, tips"
    value: float       # 185200.00
    section: str = ""  # "income", "deductions", "tax_credits", "payments"


class TaxReturnDraft(BaseModel):
    client_id: int
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
