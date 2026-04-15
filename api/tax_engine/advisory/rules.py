"""12 concrete advisory rules for tax optimization strategies."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.advisory.base import AdvisoryRule, marginal_rate
from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import TaxReturn, TaxResult


def _fmt(amount: Decimal) -> str:
    """Format a dollar amount with commas."""
    return f"{int(amount):,}"


class HSAOptimizationRule(AdvisoryRule):
    rule_id = "hsa"
    category = "deduction"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if not tax_return.hsas:
            return None
        for hsa in tax_return.hsas:
            limit = constants.hsa_limit[hsa.coverage_type]
            total = hsa.employee_contributions + hsa.employer_contributions
            gap = limit - total
            if gap > Decimal("0"):
                rate = marginal_rate(result.taxable_income, result.filing_status, constants)
                savings = (gap * rate).quantize(Decimal("1"), ROUND_HALF_UP)
                return AdvisoryItem(
                    id=self.rule_id, category=self.category,
                    title="Maximize HSA contributions",
                    detail=f"You contributed ${_fmt(total)} to your HSA but the {hsa.coverage_type} limit is ${_fmt(limit)}. Contributing ${_fmt(gap)} more would save ~${_fmt(savings)} in federal tax.",
                    savings=f"~${_fmt(savings)}/yr",
                    estimated_savings=savings,
                )
        return None


class CharitableBunchingRule(AdvisoryRule):
    rule_id = "charitable_bunch"
    category = "deduction"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        sched_a = result.form_results.get("Schedule A")
        deduction = result.form_results.get("deduction")
        if not sched_a or not deduction:
            return None
        standard = constants.standard_deduction[result.filing_status]
        itemized_total = sched_a.total
        # Only suggest if taxpayer is using standard deduction and itemized is within $5K
        if deduction.total > standard:
            return None  # Already itemizing
        gap = standard - itemized_total
        if gap > Decimal("5000") or gap <= Decimal("0"):
            return None
        charity = Decimal("0")
        if tax_return.itemized:
            charity = tax_return.itemized.charity_cash + tax_return.itemized.charity_noncash
        if charity <= Decimal("0"):
            return None
        rate = marginal_rate(result.taxable_income, result.filing_status, constants)
        bunch_benefit = (charity * rate).quantize(Decimal("1"), ROUND_HALF_UP)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Bunch charitable donations",
            detail=f"Your itemized deductions total ${_fmt(itemized_total)}, which is ${_fmt(gap)} below the standard deduction of ${_fmt(standard)}. Bunching two years of charitable donations into one year could push you over the threshold.",
            savings=f"~${_fmt(bunch_benefit)}/yr",
            estimated_savings=bunch_benefit,
        )


class SALTCapAwarenessRule(AdvisoryRule):
    rule_id = "salt_cap"
    category = "deduction"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if not tax_return.itemized:
            return None
        it = tax_return.itemized
        salt_total = it.salt_income_or_sales + it.salt_real_estate + it.salt_personal_property
        cap = constants.salt_cap[result.filing_status]
        excess = salt_total - cap
        if excess <= Decimal("0"):
            return None
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="SALT cap limits your deduction",
            detail=f"Your state and local taxes total ${_fmt(salt_total)} but are capped at ${_fmt(cap)}. You're losing ${_fmt(excess)} in deductions due to the SALT cap.",
            savings=None,
            estimated_savings=None,
        )


class RetirementContributionRule(AdvisoryRule):
    rule_id = "401k"
    category = "retirement"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        total_deferrals = Decimal("0")
        for w2 in tax_return.w2s:
            total_deferrals += w2.box12_codes.get("D", Decimal("0"))
            total_deferrals += w2.box12_codes.get("E", Decimal("0"))
            total_deferrals += w2.box12_codes.get("G", Decimal("0"))
        if total_deferrals == Decimal("0") and not tax_return.w2s:
            return None
        # Use a hardcoded 401(k) limit since TaxYearConstants doesn't have it
        limit_401k = Decimal("23000") if constants.tax_year == 2024 else Decimal("23500")
        gap = limit_401k - total_deferrals
        if gap <= Decimal("0"):
            return None
        rate = marginal_rate(result.taxable_income, result.filing_status, constants)
        savings = (gap * rate).quantize(Decimal("1"), ROUND_HALF_UP)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Increase 401(k) contributions",
            detail=f"You contributed ${_fmt(total_deferrals)} to your 401(k) but the limit is ${_fmt(limit_401k)}. Contributing ${_fmt(gap)} more would save ~${_fmt(savings)} in federal tax.",
            savings=f"~${_fmt(savings)}/yr",
            estimated_savings=savings,
        )


class RothConversionRule(AdvisoryRule):
    rule_id = "roth_conversion"
    category = "retirement"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        brackets = constants.ordinary_brackets[result.filing_status]
        ti = result.taxable_income
        # Find current bracket top
        current_rate = Decimal("0.10")
        bracket_top = Decimal("0")
        for upper, rate in brackets:
            if ti <= upper:
                bracket_top = upper
                current_rate = rate
                break
        room = bracket_top - ti
        if room <= Decimal("0") or bracket_top == Decimal("Infinity"):
            return None  # At top bracket
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Consider Roth IRA conversion",
            detail=f"You have ${_fmt(room)} of room before reaching the next tax bracket. Converting up to ${_fmt(room)} from a traditional IRA to Roth would be taxed at {current_rate * 100:.0f}% — a potentially favorable rate for long-term tax-free growth.",
            savings="Long-term benefit",
            estimated_savings=None,
        )


class SpousalIRARule(AdvisoryRule):
    rule_id = "spousal_ira"
    category = "retirement"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if tax_return.filing_status != "MFJ" or tax_return.spouse is None:
            return None
        spouse_has_ira = any(c.person_role == "spouse" for c in tax_return.ira_contributions)
        if spouse_has_ira:
            return None
        limit = constants.ira_contribution_limit
        rate = marginal_rate(result.taxable_income, result.filing_status, constants)
        savings = (limit * rate).quantize(Decimal("1"), ROUND_HALF_UP)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Spousal IRA contribution",
            detail=f"Your spouse can contribute up to ${_fmt(limit)} to a spousal IRA. If deductible, this would save ~${_fmt(savings)} in federal tax.",
            savings=f"~${_fmt(savings)}/yr",
            estimated_savings=savings,
        )


class CTCReviewRule(AdvisoryRule):
    rule_id = "ctc_review"
    category = "credit"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        qualifying = [d for d in tax_return.dependents
                      if d.is_qualifying_child and d.date_of_birth > date(result.tax_year - 16, 1, 1)]
        if not qualifying:
            return None
        threshold = constants.ctc_phase_out[result.filing_status]
        if result.agi <= threshold:
            return None
        full_credit = Decimal(len(qualifying)) * constants.ctc_amount_per_child
        sched_8812 = result.form_results.get("Schedule 8812")
        actual = Decimal("0")
        if sched_8812 and "nonrefundable" in sched_8812.lines:
            actual = sched_8812.lines["nonrefundable"].value
        lost = full_credit - actual
        if lost <= Decimal("0"):
            return None
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Child Tax Credit reduced by phase-out",
            detail=f"Your AGI of ${_fmt(result.agi)} exceeds the ${_fmt(threshold)} CTC threshold. Your credit was reduced by ${_fmt(lost)}. Consider strategies to reduce AGI below ${_fmt(threshold)}.",
            savings=f"${_fmt(lost)} potential",
            estimated_savings=lost,
        )


class EducationCreditRule(AdvisoryRule):
    rule_id = "education_credit"
    category = "credit"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if not tax_return.tuition_1098ts:
            return None
        total_expenses = sum(
            max(Decimal("0"), t.box1_payments_received - t.box5_scholarships)
            for t in tax_return.tuition_1098ts
        )
        if total_expenses <= Decimal("0"):
            return None
        # AOTC = 100% of first $2000 + 25% of next $2000 = max $2500
        aotc_estimate = min(total_expenses, Decimal("2000")) + min(max(Decimal("0"), total_expenses - Decimal("2000")), Decimal("2000")) * Decimal("0.25")
        aotc_estimate = min(aotc_estimate, Decimal("2500"))
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Education credit opportunity",
            detail=f"You have ${_fmt(total_expenses)} in qualified education expenses. The American Opportunity Credit provides up to $2,500 per student (40% refundable).",
            savings=f"Up to ${_fmt(aotc_estimate)}",
            estimated_savings=aotc_estimate,
        )


class EstimatedPaymentRule(AdvisoryRule):
    rule_id = "estimated_payments"
    category = "compliance"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if result.refund_or_owed >= Decimal("-1000"):
            return None  # Doesn't owe more than $1000
        has_estimated = len(tax_return.estimated_payments) > 0
        if has_estimated:
            return None
        owed = -result.refund_or_owed
        quarterly = (owed / 4).quantize(Decimal("1"), ROUND_HALF_UP)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Set up quarterly estimated payments",
            detail=f"You owe ${_fmt(owed)} this year with no estimated payments. To avoid underpayment penalties next year, consider quarterly estimated payments of ~${_fmt(quarterly)} (Form 1040-ES).",
            savings=None,
            estimated_savings=None,
            selected=True,
        )


class WithholdingReviewRule(AdvisoryRule):
    rule_id = "withholding"
    category = "compliance"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        refund = result.refund_or_owed
        if refund > Decimal("2000"):
            monthly = (refund / 12).quantize(Decimal("1"), ROUND_HALF_UP)
            return AdvisoryItem(
                id=self.rule_id, category=self.category,
                title="Review W-4 withholding",
                detail=f"Your refund of ${_fmt(refund)} means too much is being withheld. Adjusting your W-4 could increase your paycheck by ~${_fmt(monthly)}/month.",
                savings=None, estimated_savings=None, selected=True,
            )
        if refund < Decimal("-500"):
            owed = -refund
            return AdvisoryItem(
                id=self.rule_id, category=self.category,
                title="Review W-4 withholding",
                detail=f"You owe ${_fmt(owed)}. Adjusting your W-4 to increase withholding would avoid a year-end tax bill.",
                savings=None, estimated_savings=None, selected=True,
            )
        return None


class Plan529Rule(AdvisoryRule):
    rule_id = "529"
    category = "planning"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        if not tax_return.dependents:
            return None
        n = len(tax_return.dependents)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Open or fund 529 education plan",
            detail=f"With {n} dependent{'s' if n > 1 else ''}, a 529 plan offers tax-free growth for education expenses. Some states offer a state tax deduction for contributions.",
            savings="State deduction varies",
            estimated_savings=None,
        )


class CapitalLossHarvestRule(AdvisoryRule):
    rule_id = "capital_loss_harvest"
    category = "planning"

    def evaluate(self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants) -> AdvisoryItem | None:
        sched_d = result.form_results.get("Schedule D")
        if not sched_d or sched_d.total <= Decimal("0"):
            return None
        gains = sched_d.total
        # Estimate at 15% LTCG rate
        savings = (gains * Decimal("0.15")).quantize(Decimal("1"), ROUND_HALF_UP)
        return AdvisoryItem(
            id=self.rule_id, category=self.category,
            title="Consider capital loss harvesting",
            detail=f"You have ${_fmt(gains)} in net capital gains this year. Selling underperforming positions before year-end to offset gains could save ~${_fmt(savings)} in tax.",
            savings=f"~${_fmt(savings)}",
            estimated_savings=savings,
        )


def default_rules() -> list[AdvisoryRule]:
    """All 12 built-in advisory rules."""
    return [
        HSAOptimizationRule(),
        CharitableBunchingRule(),
        SALTCapAwarenessRule(),
        RetirementContributionRule(),
        RothConversionRule(),
        SpousalIRARule(),
        CTCReviewRule(),
        EducationCreditRule(),
        EstimatedPaymentRule(),
        WithholdingReviewRule(),
        Plan529Rule(),
        CapitalLossHarvestRule(),
    ]
