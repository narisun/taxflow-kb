"""Form 8959 — Additional Medicare Tax (0.9% on wages above threshold)."""
from decimal import Decimal, ROUND_HALF_UP
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8959"

class Form8959Calculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.additional_medicare_threshold[fs]
        w2_medicare = sum((w.box5_medicare_wages for w in tax_return.w2s), Decimal("0"))
        sched_se = prior_results.get("Schedule SE")
        se_income = Decimal("0")
        if sched_se and "4a" in sched_se.lines:
            se_income = sched_se.lines["4a"].value
        total_medicare_wages = w2_medicare + se_income
        excess = max(Decimal("0"), total_medicare_wages - threshold)
        tax = (excess * self.constants.additional_medicare_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "18", "Additional Medicare tax", tax, "max(0, total_wages - threshold) * 0.9%",
                   inputs={"total_wages": str(total_medicare_wages), "threshold": str(threshold)},
                   constants_used={"rate": str(self.constants.additional_medicare_rate)}, irs_citation="IRC §3101(b)(2)")
        return self.build_result(FORM, tax)
