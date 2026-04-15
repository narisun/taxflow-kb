"""Form 8812 / Schedule 8812 — Child Tax Credit and ACTC."""
import math
from datetime import date
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule 8812"

class Form8812Calculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        fs = tax_return.filing_status
        tax_year = tax_return.tax_year
        qualifying_children = 0
        other_dependents = 0
        age_cutoff = date(tax_year - 16, 1, 1)
        for dep in tax_return.dependents:
            if dep.is_qualifying_child and dep.date_of_birth > age_cutoff:
                qualifying_children += 1
            else:
                other_dependents += 1

        if qualifying_children == 0 and other_dependents == 0:
            self.trace(FORM, "nonrefundable", "CTC (nonrefundable)", Decimal("0"), "no dependents")
            self.trace(FORM, "other_dependent", "Other dependent credit", Decimal("0"), "no dependents")
            return self.build_result(FORM, Decimal("0"))

        ctc_gross = Decimal(qualifying_children) * self.constants.ctc_amount_per_child
        odc_gross = Decimal(other_dependents) * self.constants.ctc_other_dependent
        total_gross = ctc_gross + odc_gross

        threshold = self.constants.ctc_phase_out[fs]
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")
        if agi > threshold:
            excess = agi - threshold
            excess_thousands = math.ceil(int(excess) / 1000)
            phase_out = Decimal(excess_thousands) * Decimal("50")
        else:
            phase_out = Decimal("0")

        credit_after = max(Decimal("0"), total_gross - phase_out)
        if total_gross > Decimal("0"):
            ctc_share = ctc_gross / total_gross
            nonrefundable_ctc = (credit_after * ctc_share).quantize(Decimal("1"))
            other_dep_credit = credit_after - nonrefundable_ctc
        else:
            nonrefundable_ctc = Decimal("0")
            other_dep_credit = Decimal("0")

        tax_result = prior_results.get("tax_before_credits")
        tax_liability = tax_result.total if tax_result else Decimal("0")
        nonrefundable_ctc = min(nonrefundable_ctc, tax_liability)

        self.trace(FORM, "nonrefundable", "CTC (nonrefundable)", nonrefundable_ctc,
                   "min(ctc_after_phaseout, tax_liability)",
                   inputs={"qualifying_children": str(qualifying_children), "gross_ctc": str(ctc_gross), "phase_out": str(phase_out)},
                   constants_used={"per_child": str(self.constants.ctc_amount_per_child)})
        self.trace(FORM, "other_dependent", "Other dependent credit", other_dep_credit,
                   "other_dependents * 500 (after phase-out)",
                   inputs={"other_dependents": str(other_dependents)},
                   constants_used={"per_dependent": str(self.constants.ctc_other_dependent)})

        earned_result = prior_results.get("earned_income")
        earned = earned_result.total if earned_result else Decimal("0")
        remaining_ctc = max(Decimal("0"), ctc_gross - phase_out - nonrefundable_ctc)
        actc_max = Decimal(qualifying_children) * self.constants.ctc_refundable_max_per_child
        actc_earned = max(Decimal("0"), (earned - self.constants.ctc_earned_income_threshold) * Decimal("0.15"))
        actc = min(remaining_ctc, actc_max, actc_earned)
        self.trace(FORM, "refundable", "ACTC (refundable)", actc,
                   "min(remaining_ctc, max_per_child * kids, 15% * (earned - 2500))",
                   inputs={"remaining_ctc": str(remaining_ctc), "earned_income": str(earned)},
                   constants_used={"refundable_max": str(self.constants.ctc_refundable_max_per_child)})

        total = nonrefundable_ctc + other_dep_credit + actc
        return self.build_result(FORM, total)
