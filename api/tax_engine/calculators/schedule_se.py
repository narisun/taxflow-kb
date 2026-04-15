"""Schedule SE — Self-Employment Tax."""
from decimal import Decimal, ROUND_HALF_UP
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule SE"
SE_ADJUSTMENT = Decimal("0.9235")

class ScheduleSECalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        sched_c = prior_results.get("Schedule C")
        se_from_c = sched_c.total if sched_c else Decimal("0")
        se_from_k1 = sum((k.box14a_se_earnings for k in tax_return.k1s), Decimal("0"))
        net_se = se_from_c + se_from_k1

        if net_se <= Decimal("0"):
            self.trace(FORM, "12", "Total SE tax", Decimal("0"), "no SE income")
            self.trace(FORM, "13", "Deductible half of SE tax", Decimal("0"), "no SE tax")
            return self.build_result(FORM, Decimal("0"))

        taxable_se = (net_se * SE_ADJUSTMENT).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "4a", "Taxable SE income (92.35%)", taxable_se, "net_se * 0.9235", inputs={"net_se": str(net_se)})

        w2_ss_wages = sum((w.box3_ss_wages for w in tax_return.w2s), Decimal("0"))
        ss_room = max(Decimal("0"), self.constants.ss_wage_base - w2_ss_wages)
        ss_taxable = min(taxable_se, ss_room)
        ss_tax = (ss_taxable * self.constants.ss_combined_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "10", "Social Security tax", ss_tax, "min(taxable_se, ss_room) * ss_combined_rate",
                   inputs={"taxable_se": str(taxable_se), "ss_room": str(ss_room)},
                   constants_used={"ss_wage_base": str(self.constants.ss_wage_base), "ss_combined_rate": str(self.constants.ss_combined_rate)})

        medicare_tax = (taxable_se * self.constants.medicare_combined_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "11", "Medicare tax", medicare_tax, "taxable_se * medicare_combined_rate",
                   constants_used={"medicare_combined_rate": str(self.constants.medicare_combined_rate)})

        total_se = ss_tax + medicare_tax
        self.trace(FORM, "12", "Total SE tax", total_se, "ss_tax + medicare_tax")

        half = (total_se / 2).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "13", "Deductible half of SE tax", half, "total_se / 2", irs_citation="IRC §164(f)")
        return self.build_result(FORM, total_se)
