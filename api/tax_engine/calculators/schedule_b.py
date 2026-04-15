"""Schedule B — Interest and Ordinary Dividends."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule B"

class ScheduleBCalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        total_interest = sum((f.box1_interest for f in tax_return.interest_1099s), Decimal("0"))
        self.trace(FORM, "4", "Total interest", total_interest, "sum(1099-INT box 1)")

        total_ordinary_div = sum((f.box1a_ordinary_dividends for f in tax_return.dividend_1099s), Decimal("0"))
        self.trace(FORM, "6", "Total ordinary dividends", total_ordinary_div, "sum(1099-DIV box 1a)")

        total_qualified_div = sum((f.box1b_qualified_dividends for f in tax_return.dividend_1099s), Decimal("0"))
        self.trace(FORM, "qualified", "Total qualified dividends", total_qualified_div, "sum(1099-DIV box 1b)")

        total = total_interest + total_ordinary_div
        return self.build_result(FORM, total)
