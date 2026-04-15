"""Form 8995 / 8995-A — Qualified Business Income Deduction (§199A)."""
from decimal import Decimal, ROUND_HALF_UP
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8995"

class Form8995Calculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.qbi_threshold[fs]
        phase_in = self.constants.qbi_phase_in_range[fs]
        upper_limit = threshold + phase_in
        rate = self.constants.qbi_deduction_rate
        ti_result = prior_results.get("taxable_income_before_qbi")
        taxable_income = ti_result.total if ti_result else Decimal("0")

        qbi_items: list[dict] = []
        for sc in tax_return.schedule_cs:
            qbi_items.append({"name": sc.business_name, "qbi": sc.net_profit, "w2_wages": sc.w2_wages_paid, "ubia": sc.ubia_qualified_property, "is_sstb": sc.is_sstb})
        for k1 in tax_return.k1s:
            if k1.box20z_section_199a_qbi != Decimal("0"):
                qbi_items.append({"name": k1.entity_name, "qbi": k1.box20z_section_199a_qbi, "w2_wages": k1.w2_wages_for_qbi, "ubia": k1.ubia_qualified_property, "is_sstb": k1.is_sstb})

        if not qbi_items:
            self.trace(FORM, "15", "QBI deduction", Decimal("0"), "no QBI sources")
            return self.build_result(FORM, Decimal("0"))

        total_deduction = Decimal("0")
        for item in qbi_items:
            qbi = item["qbi"]
            tentative = qbi * rate
            if taxable_income <= threshold:
                deduction = tentative
            elif taxable_income >= upper_limit:
                if item["is_sstb"]:
                    deduction = Decimal("0")
                else:
                    w2_limit = max(item["w2_wages"] * Decimal("0.50"), item["w2_wages"] * Decimal("0.25") + item["ubia"] * Decimal("0.025"))
                    deduction = min(tentative, w2_limit)
            else:
                if item["is_sstb"]:
                    applicable_pct = Decimal("1") - (taxable_income - threshold) / phase_in
                    adj_qbi = qbi * applicable_pct
                    adj_wages = item["w2_wages"] * applicable_pct
                    adj_ubia = item["ubia"] * applicable_pct
                    tentative = adj_qbi * rate
                    w2_limit = max(adj_wages * Decimal("0.50"), adj_wages * Decimal("0.25") + adj_ubia * Decimal("0.025"))
                    deduction = min(tentative, w2_limit)
                else:
                    w2_limit = max(item["w2_wages"] * Decimal("0.50"), item["w2_wages"] * Decimal("0.25") + item["ubia"] * Decimal("0.025"))
                    reduction_pct = (taxable_income - threshold) / phase_in
                    reduction = (tentative - w2_limit) * reduction_pct
                    deduction = tentative - max(Decimal("0"), reduction)
            total_deduction += max(Decimal("0"), deduction)

        ti_cap = (taxable_income * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        final = min(total_deduction, ti_cap).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "15", "QBI deduction", final, "min(sum_qbi_deductions, 20% * taxable_income)",
                   inputs={"total_qbi_deduction": str(total_deduction), "ti_cap": str(ti_cap)},
                   constants_used={"qbi_rate": str(rate), "threshold": str(threshold)}, irs_citation="IRC §199A")
        return self.build_result(FORM, final)
