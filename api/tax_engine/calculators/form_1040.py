"""Form 1040 — Final assembly of all form results into lines 1–37."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "1040"

class Form1040Calculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        wages = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        self.trace(FORM, "1a", "Total wages", wages, "sum(W-2 box 1)")

        sched_b = prior_results.get("Schedule B")
        interest_val = sched_b.lines["4"].value if sched_b and "4" in sched_b.lines else Decimal("0")
        self.trace(FORM, "2b", "Taxable interest", interest_val, "Schedule B line 4")

        div_val = sched_b.lines["6"].value if sched_b and "6" in sched_b.lines else Decimal("0")
        self.trace(FORM, "3b", "Ordinary dividends", div_val, "Schedule B line 6")

        sched_d = prior_results.get("Schedule D")
        cap_gain = sched_d.total if sched_d else Decimal("0")
        self.trace(FORM, "7", "Capital gain or loss", cap_gain, "Schedule D line 21")

        sched_c = prior_results.get("Schedule C")
        sched_e = prior_results.get("Schedule E")
        other = Decimal("0")
        if sched_c: other += sched_c.total
        if sched_e: other += sched_e.total
        nec = sum((n.nec_compensation for n in tax_return.nec_1099s), Decimal("0"))
        other += nec
        retirement = sum((r.box2a_taxable_amount for r in tax_return.retirement_1099rs), Decimal("0"))
        other += retirement
        self.trace(FORM, "8", "Other income", other, "Schedule C + E + 1099-NEC + 1099-R")

        total_income = prior_results.get("total_income")
        total_income_val = total_income.total if total_income else Decimal("0")
        self.trace(FORM, "9", "Total income", total_income_val, "sum of all income")

        adj = prior_results.get("adjustments")
        adj_val = adj.total if adj else Decimal("0")
        self.trace(FORM, "10", "Adjustments to income", adj_val, "Schedule 1 adjustments")

        agi = prior_results.get("AGI")
        agi_val = agi.total if agi else Decimal("0")
        self.trace(FORM, "11", "Adjusted gross income", agi_val, "line 9 - line 10")

        ded = prior_results.get("deduction")
        ded_val = ded.total if ded else Decimal("0")
        self.trace(FORM, "12", "Deduction", ded_val, "standard or itemized")

        qbi = prior_results.get("Form 8995")
        qbi_val = qbi.total if qbi else Decimal("0")
        self.trace(FORM, "13a", "QBI deduction", qbi_val, "Form 8995 line 15")

        taxable = max(Decimal("0"), agi_val - ded_val - qbi_val)
        self.trace(FORM, "15", "Taxable income", taxable, "AGI - deduction - QBI")

        tax_result = prior_results.get("ordinary_tax")
        tax_val = tax_result.total if tax_result else Decimal("0")
        self.trace(FORM, "16", "Tax", tax_val, "from tax brackets")

        se = prior_results.get("Schedule SE")
        se_val = se.total if se else Decimal("0")
        f8959 = prior_results.get("Form 8959")
        f8959_val = f8959.total if f8959 else Decimal("0")
        f8960 = prior_results.get("Form 8960")
        f8960_val = f8960.total if f8960 else Decimal("0")
        other_taxes = se_val + f8959_val + f8960_val
        self.trace(FORM, "23", "Other taxes", other_taxes, "SE tax + additional Medicare + NIIT")

        ctc = prior_results.get("Schedule 8812")
        ctc_nonrefund = Decimal("0")
        if ctc and "nonrefundable" in ctc.lines:
            ctc_nonrefund = ctc.lines["nonrefundable"].value
        if ctc and "other_dependent" in ctc.lines:
            ctc_nonrefund += ctc.lines["other_dependent"].value

        total_tax = max(Decimal("0"), tax_val - ctc_nonrefund + other_taxes)
        self.trace(FORM, "24", "Total tax", total_tax, "tax - credits + other_taxes")

        withholding = sum((w.box2_fed_withheld for w in tax_return.w2s), Decimal("0"))
        withholding += sum((f.box4_fed_withheld for f in tax_return.interest_1099s), Decimal("0"))
        withholding += sum((f.box4_fed_withheld for f in tax_return.retirement_1099rs), Decimal("0"))
        withholding += sum((f.fed_tax_withheld for f in tax_return.nec_1099s), Decimal("0"))
        self.trace(FORM, "25", "Federal tax withheld", withholding, "sum(W-2 box 2 + 1099 withholding)")

        est = sum((e.amount for e in tax_return.estimated_payments), Decimal("0"))
        self.trace(FORM, "26", "Estimated tax payments", est, "sum(estimated_payments)")

        actc = Decimal("0")
        if ctc and "refundable" in ctc.lines:
            actc = ctc.lines["refundable"].value

        total_payments = withholding + est + actc
        self.trace(FORM, "33", "Total payments", total_payments, "withholding + estimated + refundable_credits")

        refund_or_owed = total_payments - total_tax
        if refund_or_owed >= Decimal("0"):
            self.trace(FORM, "35a", "Refund", refund_or_owed, "total_payments - total_tax")
        else:
            self.trace(FORM, "37", "Amount you owe", -refund_or_owed, "total_tax - total_payments")

        return self.build_result(FORM, refund_or_owed)
