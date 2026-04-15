"""Form 8960 — Net Investment Income Tax (3.8% NIIT)."""
from decimal import Decimal, ROUND_HALF_UP
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8960"

class Form8960Calculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.niit_threshold[fs]
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")
        nii = Decimal("0")
        sched_b = prior_results.get("Schedule B")
        if sched_b:
            nii += sched_b.total
        sched_d = prior_results.get("Schedule D")
        if sched_d and sched_d.total > Decimal("0"):
            nii += sched_d.total
        sched_e = prior_results.get("Schedule E")
        if sched_e:
            for line_key, lt in sched_e.lines.items():
                if line_key.startswith("26"):
                    nii += lt.value
        self.trace(FORM, "8", "Net investment income", nii, "interest + dividends + cap_gains + rental")
        excess_magi = max(Decimal("0"), agi - threshold)
        taxable = min(nii, excess_magi)
        tax = (taxable * self.constants.niit_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "17", "Net investment income tax", tax, "min(NII, MAGI - threshold) * 3.8%",
                   inputs={"nii": str(nii), "magi": str(agi), "threshold": str(threshold)},
                   constants_used={"niit_rate": str(self.constants.niit_rate)}, irs_citation="IRC §1411")
        return self.build_result(FORM, tax)
