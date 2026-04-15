"""Schedule A — Itemized Deductions."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule A"

class ScheduleACalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        itemized = tax_return.itemized
        if itemized is None:
            self.trace(FORM, "17", "Total itemized deductions", Decimal("0"), "no itemized deductions provided")
            return self.build_result(FORM, Decimal("0"))

        fs = tax_return.filing_status
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")

        # Line 1-4: Medical (7.5% AGI floor)
        floor = agi * self.constants.medical_agi_floor_pct
        medical = max(Decimal("0"), itemized.medical_dental - floor)
        self.trace(FORM, "4", "Medical & dental (after AGI floor)", medical, "max(0, medical - agi * 7.5%)",
                   inputs={"medical": str(itemized.medical_dental), "agi": str(agi)},
                   constants_used={"floor_pct": str(self.constants.medical_agi_floor_pct)})

        # Line 5-7: SALT (capped)
        salt_total = itemized.salt_income_or_sales + itemized.salt_real_estate + itemized.salt_personal_property
        salt_cap = self.constants.salt_cap[fs]
        salt = min(salt_total, salt_cap)
        self.trace(FORM, "7", "State and local taxes (capped)", salt, "min(salt_total, salt_cap)",
                   inputs={"salt_total": str(salt_total)}, constants_used={"salt_cap": str(salt_cap)}, irs_citation="TCJA §11042")

        # Line 8-9: Interest
        interest = itemized.mortgage_interest_1098 + itemized.mortgage_interest_other + itemized.investment_interest
        self.trace(FORM, "10", "Total interest", interest, "mortgage_1098 + mortgage_other + investment_interest")

        # Line 11-14: Charity
        charity = itemized.charity_cash + itemized.charity_noncash
        self.trace(FORM, "14", "Total charitable contributions", charity, "charity_cash + charity_noncash")

        casualty = itemized.casualty_loss
        other = itemized.other_deductions
        total = medical + salt + interest + charity + casualty + other
        self.trace(FORM, "17", "Total itemized deductions", total, "medical + salt + interest + charity + casualty + other",
                   inputs={"medical": str(medical), "salt": str(salt), "interest": str(interest), "charity": str(charity)})
        return self.build_result(FORM, total)
