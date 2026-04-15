"""Year-over-year comparison data models."""
from decimal import Decimal
from pydantic import BaseModel


class ComparisonRow(BaseModel):
    label: str
    line: str
    current: Decimal
    prior: Decimal
    change: Decimal
    pct_change: float


class ComparisonSection(BaseModel):
    title: str
    rows: list[ComparisonRow]


class ComparisonReport(BaseModel):
    current_year: int
    prior_year: int
    client_id: int
    sections: list[ComparisonSection]
    summary: ComparisonRow
