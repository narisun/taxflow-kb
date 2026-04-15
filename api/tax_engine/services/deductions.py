"""DeductionService — adjustments, standard vs itemized, QBI."""
from decimal import Decimal
from api.tax_engine.calculators.schedule_a import ScheduleACalculator
from api.tax_engine.calculators.form_8995 import Form8995Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn

class DeductionService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute_adjustments(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> dict[str, FormResult]:
        adjustments = Decimal("0")
        traces: list[LineTrace] = []

        # Deductible half of SE tax
        se_result = results.get("Schedule SE")
        if se_result and "13" in se_result.lines:
            se_ded = se_result.lines["13"].value
            adjustments += se_ded
            traces.append(LineTrace(form="Schedule 1", line="15", label="Deductible half of SE tax", value=se_ded, formula="SE tax / 2"))

        # HSA deduction
        for hsa in tax_return.hsas:
            limit = self.constants.hsa_limit[hsa.coverage_type]
            ded = min(hsa.employee_contributions, limit - hsa.employer_contributions)
            ded = max(Decimal("0"), ded)
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="13", label="HSA deduction", value=ded, formula="min(employee, limit - employer)"))

        # Student loan interest
        for sl in tax_return.student_loans:
            ded = min(sl.box1_interest_paid, self.constants.student_loan_max_deduction)
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="21", label="Student loan interest", value=ded, formula="min(interest, max_deduction)"))

        # Educator expenses
        if tax_return.educator_expenses > Decimal("0"):
            ded = min(tax_return.educator_expenses, Decimal("300"))
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="11", label="Educator expenses", value=ded, formula="min(expenses, 300)"))

        # Compute total income
        income_total = Decimal("0")
        for key in ["Schedule B", "Schedule C", "Schedule D", "Schedule E"]:
            r = results.get(key)
            if r:
                income_total += r.total
        wages = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        income_total += wages
        nec = sum((n.nec_compensation for n in tax_return.nec_1099s), Decimal("0"))
        income_total += nec
        retirement = sum((r.box2a_taxable_amount for r in tax_return.retirement_1099rs), Decimal("0"))
        income_total += retirement
        ssa = sum((s.box5_net_benefits for s in tax_return.ssa_1099s), Decimal("0"))
        ssa_taxable = (ssa * Decimal("0.85")).quantize(Decimal("0.01"))
        income_total += ssa_taxable

        agi = income_total - adjustments

        out: dict[str, FormResult] = {}
        out["adjustments"] = FormResult(form_name="adjustments", lines={t.line: t for t in traces}, total=adjustments)
        out["total_income"] = FormResult(form_name="total_income", total=income_total,
            lines={"9": LineTrace(form="1040", line="9", label="Total income", value=income_total,
                                  formula="wages + interest + div + cap_gains + se + rental + nec + retirement + ssa")})

        se_profit = max(Decimal("0"), sum(sc.net_profit for sc in tax_return.schedule_cs))
        earned_total = wages + nec + se_profit
        out["earned_income"] = FormResult(form_name="earned_income", total=earned_total,
            lines={"earned": LineTrace(form="1040", line="earned", label="Earned income", value=earned_total, formula="wages + nec + se_profit")})

        out["AGI"] = FormResult(form_name="AGI", total=agi,
            lines={"11": LineTrace(form="1040", line="11", label="Adjusted gross income", value=agi,
                                   formula="total_income - adjustments",
                                   inputs={"total_income": str(income_total), "adjustments": str(adjustments)})})
        return out

    def compute_deductions(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}
        fs = tax_return.filing_status
        agi = results.get("AGI")
        agi_val = agi.total if agi else Decimal("0")

        sched_a = ScheduleACalculator(self.constants).compute(tax_return, results)
        out["Schedule A"] = sched_a

        standard = self.constants.standard_deduction[fs]
        deduction = max(standard, sched_a.total)
        used_standard = deduction == standard
        out["deduction"] = FormResult(form_name="deduction", total=deduction,
            lines={"12": LineTrace(form="1040", line="12",
                                   label="Standard deduction" if used_standard else "Itemized deductions",
                                   value=deduction, formula="max(standard, itemized)",
                                   inputs={"standard": str(standard), "itemized": str(sched_a.total)})})

        ti_before_qbi = max(Decimal("0"), agi_val - deduction)
        out["taxable_income_before_qbi"] = FormResult(form_name="pre-QBI", total=ti_before_qbi,
            lines={"15": LineTrace(form="1040", line="15", label="Taxable income (before QBI)", value=ti_before_qbi, formula="AGI - deduction")})

        merged = {**results, **out}
        out["Form 8995"] = Form8995Calculator(self.constants).compute(tax_return, merged)
        return out
