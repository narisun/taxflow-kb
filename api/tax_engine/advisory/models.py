"""Advisory data models."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AdvisoryItem(BaseModel):
    id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]
    title: str
    detail: str
    savings: str | None = None
    estimated_savings: Decimal | None = None
    selected: bool = True
