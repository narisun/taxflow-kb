"""LiabilityService — tax brackets, SE tax, surtaxes."""
from decimal import Decimal, ROUND_HALF_UP
from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
from api.tax_engine.calculators.form_8959 import Form8959Calculator
from api.tax_engine.calculators.form_8960 import Form8960Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn

class LiabilityService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def _compute_ordinary_tax(self, taxable_income: Decimal, filing_status: str) -> Decimal:
        brackets = self.constants.ordinary_brackets[filing_status]
        tax = Decimal("0")
        prev_upper = Decimal("0")
        for upper, rate in brackets:
            if taxable_income <= prev_upper:
                break
            width = min(taxable_income, upper) - prev_upper
            tax += width * rate
            prev_upper = upper
        return tax.quantize(Decimal("0.01"), ROUND_HALF_UP)

    def compute(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}

        se_result = ScheduleSECalculator(self.constants).compute(tax_return, results)
        out["Schedule SE"] = se_result

        ti_result = results.get("taxable_income_before_qbi")
        qbi_result = results.get("Form 8995")
        ti = ti_result.total if ti_result else Decimal("0")
        qbi_ded = qbi_result.total if qbi_result else Decimal("0")
        taxable_income = max(Decimal("0"), ti - qbi_ded)

        ordinary_tax = self._compute_ordinary_tax(taxable_income, tax_return.filing_status)
        out["ordinary_tax"] = FormResult(form_name="ordinary_tax",
            lines={"16": LineTrace(form="1040", line="16", label="Tax", value=ordinary_tax,
                                   formula="progressive_brackets(taxable_income)",
                                   inputs={"taxable_income": str(taxable_income)})},
            total=ordinary_tax)

        merged = {**results, **out}
        out["Form 8959"] = Form8959Calculator(self.constants).compute(tax_return, merged)
        out["Form 8960"] = Form8960Calculator(self.constants).compute(tax_return, merged)
        return out
