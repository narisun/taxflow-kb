"""Advisory rule base class and marginal rate helper."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Literal

from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import TaxReturn, TaxResult


class AdvisoryRule(ABC):
    rule_id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]

    @abstractmethod
    def evaluate(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> AdvisoryItem | None:
        """Return an advisory item if applicable, else None."""


def marginal_rate(
    taxable_income: Decimal, filing_status: str, constants: TaxYearConstants
) -> Decimal:
    """Return the marginal ordinary tax rate for the given taxable income."""
    brackets = constants.ordinary_brackets[filing_status]
    rate = Decimal("0.10")
    prev_upper = Decimal("0")
    for upper, bracket_rate in brackets:
        if taxable_income <= prev_upper:
            break
        rate = bracket_rate
        prev_upper = upper
    return rate
