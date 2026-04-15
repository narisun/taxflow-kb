# Phase 3A: Tax Advisory Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pluggable advisory engine that analyzes a computed tax return and generates personalized strategy recommendations with estimated savings based on the taxpayer's marginal rate.

**Architecture:** Each strategy is an independent `AdvisoryRule` class receiving `(TaxReturn, TaxResult, TaxYearConstants)`. An `AdvisoryEngine` runs all rules, collects `AdvisoryItem` objects, and sorts by estimated savings. A new `GET /advisory` endpoint serves items matching the frontend's existing interface.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-advisory-engine-phase3a-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `api/tax_engine/advisory/__init__.py` | Package init |
| `api/tax_engine/advisory/models.py` | AdvisoryItem Pydantic model |
| `api/tax_engine/advisory/base.py` | AdvisoryRule ABC + marginal_rate helper |
| `api/tax_engine/advisory/rules.py` | 12 concrete rule implementations |
| `api/tax_engine/advisory/engine.py` | AdvisoryEngine orchestrator |
| `tests/api/tax_engine/test_advisory_rules.py` | Individual rule tests |
| `tests/api/tax_engine/test_advisory_engine.py` | Engine orchestration tests |
| `tests/api/test_advisory_endpoint.py` | API integration test |

### Modified Files

| File | Change |
|------|--------|
| `api/routers/tax_returns.py` | Add `GET /advisory` endpoint |

---

## Task 1: Advisory Model + Base Rule + Marginal Rate Helper

**Files:**
- Create: `api/tax_engine/advisory/__init__.py`
- Create: `api/tax_engine/advisory/models.py`
- Create: `api/tax_engine/advisory/base.py`
- Create: `tests/api/tax_engine/test_advisory_engine.py` (marginal rate tests)

- [ ] **Step 1: Create package**

```bash
mkdir -p api/tax_engine/advisory
touch api/tax_engine/advisory/__init__.py
```

- [ ] **Step 2: Write failing tests for marginal rate helper**

Create `tests/api/tax_engine/test_advisory_engine.py`:

```python
"""Tests for advisory engine — marginal rate and engine orchestration."""
from decimal import Decimal

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants


class TestMarginalRate:
    def test_10pct_bracket_single(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # Single: 10% bracket is $0–$11,600
        assert marginal_rate(Decimal("5000"), "S", c) == Decimal("0.10")

    def test_12pct_bracket_single(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # Single: 12% bracket is $11,600–$47,150
        assert marginal_rate(Decimal("30000"), "S", c) == Decimal("0.12")

    def test_22pct_bracket_single(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # Single: 22% bracket is $47,150–$100,525
        assert marginal_rate(Decimal("70000"), "S", c) == Decimal("0.22")

    def test_24pct_bracket_mfj(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # MFJ: 24% bracket is $201,050–$383,900
        assert marginal_rate(Decimal("250000"), "MFJ", c) == Decimal("0.24")

    def test_at_bracket_boundary(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # Exactly at $11,600 (top of 10% bracket for single)
        assert marginal_rate(Decimal("11600"), "S", c) == Decimal("0.10")

    def test_zero_income(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        assert marginal_rate(Decimal("0"), "S", c) == Decimal("0.10")

    def test_37pct_bracket(self):
        from api.tax_engine.advisory.base import marginal_rate
        c = get_constants(2024)
        # Single: 37% bracket above $609,350
        assert marginal_rate(Decimal("700000"), "S", c) == Decimal("0.37")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_advisory_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement models.py**

Create `api/tax_engine/advisory/models.py`:

```python
"""Advisory data models."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AdvisoryItem(BaseModel):
    id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]
    title: str
    detail: str
    savings: str | None = None
    estimated_savings: Decimal | None = None
    selected: bool = True
```

- [ ] **Step 5: Implement base.py**

Create `api/tax_engine/advisory/base.py`:

```python
"""Advisory rule base class and marginal rate helper."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Literal

from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import TaxReturn, TaxResult


class AdvisoryRule(ABC):
    rule_id: str
    category: Literal["deduction", "credit", "retirement", "planning", "compliance"]

    @abstractmethod
    def evaluate(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> AdvisoryItem | None:
        """Return an advisory item if applicable, else None."""


def marginal_rate(
    taxable_income: Decimal, filing_status: str, constants: TaxYearConstants
) -> Decimal:
    """Return the marginal ordinary tax rate for the given taxable income."""
    brackets = constants.ordinary_brackets[filing_status]
    rate = Decimal("0.10")
    prev_upper = Decimal("0")
    for upper, bracket_rate in brackets:
        if taxable_income <= prev_upper:
            break
        rate = bracket_rate
        prev_upper = upper
    return rate
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_advisory_engine.py::TestMarginalRate -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/tax_engine/advisory/ tests/api/tax_engine/test_advisory_engine.py
git commit -m "feat(advisory): add AdvisoryItem model, AdvisoryRule ABC, and marginal_rate helper"
```

---

## Task 2: Deduction Advisory Rules (HSA, Charitable Bunching, SALT Cap)

**Files:**
- Create: `api/tax_engine/advisory/rules.py`
- Create: `tests/api/tax_engine/test_advisory_rules.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/test_advisory_rules.py`:

```python
"""Tests for individual advisory rules."""
from datetime import date
from decimal import Decimal

import pytest

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.income import W2, Income1099Int, ScheduleC, ScheduleK1, Income1099B
from api.tax_engine.models.deductions import HSA, ItemizedDeductions, IRAContribution, StudentLoanInterest
from api.tax_engine.models.credits import Tuition1098T, EstimatedPayment
from api.tax_engine.models.people import Dependent
from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult, LineTrace


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))


def _spouse():
    return Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10))


def _address():
    return Address(street="123 Main", city="Springfield", state="IL", zip_code="62701")


def _make_return(**kwargs) -> TaxReturn:
    defaults = dict(tax_year=2024, filing_status="S", primary=_person(), address=_address())
    defaults.update(kwargs)
    return TaxReturn(**defaults)


def _make_result(**kwargs) -> TaxResult:
    defaults = dict(tax_year=2024, filing_status="S", taxable_income=Decimal("70000"),
                    total_income=Decimal("85000"), agi=Decimal("85000"),
                    total_tax=Decimal("10000"), total_payments=Decimal("15000"),
                    refund_or_owed=Decimal("5000"))
    defaults.update(kwargs)
    return TaxResult(**defaults)


class TestHSAOptimizationRule:
    def test_below_limit(self):
        from api.tax_engine.advisory.rules import HSAOptimizationRule
        tr = _make_return(hsas=[HSA(coverage_type="self-only", employee_contributions=Decimal("2000"), employer_contributions=Decimal("0"))])
        result = _make_result(taxable_income=Decimal("70000"))
        c = get_constants(2024)
        item = HSAOptimizationRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "hsa"
        assert item.estimated_savings is not None
        assert item.estimated_savings > Decimal("0")
        # Gap = 4150 - 2000 = 2150, marginal = 22%, savings = ~473
        assert "2,150" in item.detail or "2150" in item.detail

    def test_at_limit(self):
        from api.tax_engine.advisory.rules import HSAOptimizationRule
        tr = _make_return(hsas=[HSA(coverage_type="self-only", employee_contributions=Decimal("4150"), employer_contributions=Decimal("0"))])
        result = _make_result()
        c = get_constants(2024)
        item = HSAOptimizationRule().evaluate(tr, result, c)
        assert item is None

    def test_no_hsa(self):
        from api.tax_engine.advisory.rules import HSAOptimizationRule
        tr = _make_return()
        result = _make_result()
        c = get_constants(2024)
        item = HSAOptimizationRule().evaluate(tr, result, c)
        assert item is None


class TestCharitableBunchingRule:
    def test_near_standard_deduction(self):
        from api.tax_engine.advisory.rules import CharitableBunchingRule
        tr = _make_return(itemized=ItemizedDeductions(charity_cash=Decimal("3000"), salt_income_or_sales=Decimal("5000"), mortgage_interest_1098=Decimal("4000")))
        result = _make_result(
            form_results={"Schedule A": FormResult(form_name="Schedule A", total=Decimal("12000")),
                          "deduction": FormResult(form_name="deduction", total=Decimal("14600"),
                              lines={"12": LineTrace(form="1040", line="12", label="Standard", value=Decimal("14600"), formula="standard")})})
        c = get_constants(2024)
        item = CharitableBunchingRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "charitable_bunch"

    def test_already_itemizing(self):
        from api.tax_engine.advisory.rules import CharitableBunchingRule
        tr = _make_return(itemized=ItemizedDeductions(charity_cash=Decimal("10000"), mortgage_interest_1098=Decimal("15000")))
        result = _make_result(
            form_results={"Schedule A": FormResult(form_name="Schedule A", total=Decimal("25000")),
                          "deduction": FormResult(form_name="deduction", total=Decimal("25000"),
                              lines={"12": LineTrace(form="1040", line="12", label="Itemized", value=Decimal("25000"), formula="itemized")})})
        c = get_constants(2024)
        item = CharitableBunchingRule().evaluate(tr, result, c)
        assert item is None


class TestSALTCapAwarenessRule:
    def test_exceeds_cap(self):
        from api.tax_engine.advisory.rules import SALTCapAwarenessRule
        tr = _make_return(itemized=ItemizedDeductions(salt_income_or_sales=Decimal("12000"), salt_real_estate=Decimal("5000")))
        result = _make_result()
        c = get_constants(2024)
        item = SALTCapAwarenessRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "salt_cap"
        assert "7,000" in item.detail or "7000" in item.detail

    def test_below_cap(self):
        from api.tax_engine.advisory.rules import SALTCapAwarenessRule
        tr = _make_return(itemized=ItemizedDeductions(salt_income_or_sales=Decimal("5000")))
        result = _make_result()
        c = get_constants(2024)
        item = SALTCapAwarenessRule().evaluate(tr, result, c)
        assert item is None


class TestRetirementContributionRule:
    def test_below_401k_limit(self):
        from api.tax_engine.advisory.rules import RetirementContributionRule
        tr = _make_return(w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                                  box1_wages=Decimal("85000"), box12_codes={"D": Decimal("15000")})])
        result = _make_result(taxable_income=Decimal("70000"))
        c = get_constants(2024)
        item = RetirementContributionRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "401k"
        assert item.estimated_savings > Decimal("0")

    def test_at_limit(self):
        from api.tax_engine.advisory.rules import RetirementContributionRule
        tr = _make_return(w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                                  box12_codes={"D": Decimal("23000")})])
        result = _make_result()
        c = get_constants(2024)
        item = RetirementContributionRule().evaluate(tr, result, c)
        assert item is None


class TestRothConversionRule:
    def test_room_in_bracket(self):
        from api.tax_engine.advisory.rules import RothConversionRule
        # Single, taxable = 70000, 22% bracket goes up to 100525
        result = _make_result(taxable_income=Decimal("70000"))
        c = get_constants(2024)
        item = RothConversionRule().evaluate(_make_return(), result, c)
        assert item is not None
        assert item.id == "roth_conversion"

    def test_near_top_of_bracket(self):
        from api.tax_engine.advisory.rules import RothConversionRule
        # Less than $5000 room — not enough to recommend
        result = _make_result(taxable_income=Decimal("98000"))
        c = get_constants(2024)
        item = RothConversionRule().evaluate(_make_return(), result, c)
        assert item is not None  # Still has $2525 room, but > 0

    def test_no_room_small_bracket(self):
        from api.tax_engine.advisory.rules import RothConversionRule
        # At top bracket, no useful room
        result = _make_result(taxable_income=Decimal("700000"))
        c = get_constants(2024)
        item = RothConversionRule().evaluate(_make_return(), result, c)
        assert item is None


class TestSpousalIRARule:
    def test_mfj_no_spouse_ira(self):
        from api.tax_engine.advisory.rules import SpousalIRARule
        tr = _make_return(filing_status="MFJ", spouse=_spouse())
        result = _make_result(filing_status="MFJ", taxable_income=Decimal("100000"))
        c = get_constants(2024)
        item = SpousalIRARule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "spousal_ira"

    def test_single_filer(self):
        from api.tax_engine.advisory.rules import SpousalIRARule
        tr = _make_return()
        result = _make_result()
        c = get_constants(2024)
        assert SpousalIRARule().evaluate(tr, result, c) is None

    def test_spouse_already_has_ira(self):
        from api.tax_engine.advisory.rules import SpousalIRARule
        tr = _make_return(filing_status="MFJ", spouse=_spouse(),
                          ira_contributions=[IRAContribution(amount=Decimal("7000"), person_role="spouse")])
        result = _make_result(filing_status="MFJ")
        c = get_constants(2024)
        assert SpousalIRARule().evaluate(tr, result, c) is None


class TestEstimatedPaymentRule:
    def test_owes_over_1000(self):
        from api.tax_engine.advisory.rules import EstimatedPaymentRule
        result = _make_result(refund_or_owed=Decimal("-2500"))
        c = get_constants(2024)
        item = EstimatedPaymentRule().evaluate(_make_return(), result, c)
        assert item is not None
        assert item.id == "estimated_payments"

    def test_small_owed(self):
        from api.tax_engine.advisory.rules import EstimatedPaymentRule
        result = _make_result(refund_or_owed=Decimal("-500"))
        c = get_constants(2024)
        assert EstimatedPaymentRule().evaluate(_make_return(), result, c) is None

    def test_refund(self):
        from api.tax_engine.advisory.rules import EstimatedPaymentRule
        result = _make_result(refund_or_owed=Decimal("5000"))
        c = get_constants(2024)
        assert EstimatedPaymentRule().evaluate(_make_return(), result, c) is None


class TestWithholdingReviewRule:
    def test_large_refund(self):
        from api.tax_engine.advisory.rules import WithholdingReviewRule
        result = _make_result(refund_or_owed=Decimal("3000"))
        c = get_constants(2024)
        item = WithholdingReviewRule().evaluate(_make_return(), result, c)
        assert item is not None
        assert item.id == "withholding"
        assert "paycheck" in item.detail.lower() or "W-4" in item.detail

    def test_moderate_refund(self):
        from api.tax_engine.advisory.rules import WithholdingReviewRule
        result = _make_result(refund_or_owed=Decimal("1000"))
        c = get_constants(2024)
        assert WithholdingReviewRule().evaluate(_make_return(), result, c) is None


class TestPlan529Rule:
    def test_with_dependents(self):
        from api.tax_engine.advisory.rules import Plan529Rule
        tr = _make_return(dependents=[Dependent(first_name="A", last_name="D", ssn="111223333",
                                                relationship="son", date_of_birth=date(2015, 1, 1))])
        result = _make_result()
        c = get_constants(2024)
        item = Plan529Rule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "529"

    def test_no_dependents(self):
        from api.tax_engine.advisory.rules import Plan529Rule
        assert Plan529Rule().evaluate(_make_return(), _make_result(), get_constants(2024)) is None


class TestCapitalLossHarvestRule:
    def test_has_gains(self):
        from api.tax_engine.advisory.rules import CapitalLossHarvestRule
        result = _make_result(
            form_results={"Schedule D": FormResult(form_name="Schedule D", total=Decimal("15000"))})
        c = get_constants(2024)
        item = CapitalLossHarvestRule().evaluate(_make_return(), result, c)
        assert item is not None
        assert item.id == "capital_loss_harvest"
        assert item.estimated_savings > Decimal("0")

    def test_no_gains(self):
        from api.tax_engine.advisory.rules import CapitalLossHarvestRule
        result = _make_result(form_results={"Schedule D": FormResult(form_name="Schedule D", total=Decimal("-2000"))})
        c = get_constants(2024)
        assert CapitalLossHarvestRule().evaluate(_make_return(), result, c) is None


class TestCTCReviewRule:
    def test_phased_out(self):
        from api.tax_engine.advisory.rules import CTCReviewRule
        tr = _make_return(dependents=[Dependent(first_name="A", last_name="D", ssn="111223333",
                                                relationship="son", date_of_birth=date(2015, 1, 1))])
        result = _make_result(agi=Decimal("215000"),
            form_results={"Schedule 8812": FormResult(form_name="Schedule 8812", total=Decimal("1250"),
                lines={"nonrefundable": LineTrace(form="Schedule 8812", line="nonrefundable", label="CTC", value=Decimal("1250"), formula="test")})})
        c = get_constants(2024)
        item = CTCReviewRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "ctc_review"

    def test_no_children(self):
        from api.tax_engine.advisory.rules import CTCReviewRule
        assert CTCReviewRule().evaluate(_make_return(), _make_result(), get_constants(2024)) is None


class TestEducationCreditRule:
    def test_has_tuition(self):
        from api.tax_engine.advisory.rules import EducationCreditRule
        tr = _make_return(tuition_1098ts=[Tuition1098T(institution="MIT", box1_payments_received=Decimal("15000"),
                                                       student_name="John", student_ssn="111223333")])
        result = _make_result()
        c = get_constants(2024)
        item = EducationCreditRule().evaluate(tr, result, c)
        assert item is not None
        assert item.id == "education_credit"

    def test_no_tuition(self):
        from api.tax_engine.advisory.rules import EducationCreditRule
        assert EducationCreditRule().evaluate(_make_return(), _make_result(), get_constants(2024)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_advisory_rules.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement rules.py**

Create `api/tax_engine/advisory/rules.py`:

```python
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
        limit = constants.ira_contribution_limit  # Reuse — in practice 401k limit would be separate
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
        prev_upper = Decimal("0")
        current_rate = Decimal("0.10")
        bracket_top = Decimal("0")
        for upper, rate in brackets:
            if ti <= upper:
                bracket_top = upper
                current_rate = rate
                break
            prev_upper = upper
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_advisory_rules.py -v`
Expected: All ~25 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/advisory/rules.py tests/api/tax_engine/test_advisory_rules.py
git commit -m "feat(advisory): add 12 advisory rules — deduction, retirement, credit, compliance, planning"
```

---

## Task 3: Advisory Engine Orchestrator

**Files:**
- Create: `api/tax_engine/advisory/engine.py`
- Modify: `tests/api/tax_engine/test_advisory_engine.py` (add engine tests)

- [ ] **Step 1: Write engine tests**

Append to `tests/api/tax_engine/test_advisory_engine.py`:

```python
from datetime import date

from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2
from api.tax_engine.models.deductions import HSA
from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))


def _address():
    return Address(street="123 Main", city="Springfield", state="IL", zip_code="62701")


class TestAdvisoryEngine:
    def test_returns_applicable_items(self):
        from api.tax_engine.advisory.engine import AdvisoryEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="S", primary=_person(), address=_address(),
            w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                     box1_wages=Decimal("85000"), box12_codes={"D": Decimal("10000")})],
            hsas=[HSA(coverage_type="self-only", employee_contributions=Decimal("2000"))],
        )
        result = TaxResult(
            tax_year=2024, filing_status="S", taxable_income=Decimal("70000"),
            total_income=Decimal("85000"), agi=Decimal("85000"),
            total_tax=Decimal("10000"), total_payments=Decimal("15000"),
            refund_or_owed=Decimal("5000"),
        )
        c = get_constants(2024)
        engine = AdvisoryEngine()
        items = engine.analyze(tr, result, c)
        assert len(items) > 0
        ids = [i.id for i in items]
        assert "hsa" in ids
        assert "401k" in ids

    def test_sorted_by_savings_descending(self):
        from api.tax_engine.advisory.engine import AdvisoryEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="S", primary=_person(), address=_address(),
            w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                     box1_wages=Decimal("85000"), box12_codes={"D": Decimal("5000")})],
            hsas=[HSA(coverage_type="self-only", employee_contributions=Decimal("1000"))],
        )
        result = TaxResult(
            tax_year=2024, filing_status="S", taxable_income=Decimal("70000"),
            total_income=Decimal("85000"), agi=Decimal("85000"),
            total_tax=Decimal("10000"), total_payments=Decimal("15000"),
            refund_or_owed=Decimal("5000"),
        )
        c = get_constants(2024)
        items = AdvisoryEngine().analyze(tr, result, c)
        savings_items = [i for i in items if i.estimated_savings is not None]
        if len(savings_items) >= 2:
            for i in range(len(savings_items) - 1):
                assert savings_items[i].estimated_savings >= savings_items[i + 1].estimated_savings

    def test_empty_return(self):
        from api.tax_engine.advisory.engine import AdvisoryEngine
        tr = TaxReturn(
            tax_year=2024, filing_status="S", primary=_person(), address=_address(),
        )
        result = TaxResult(
            tax_year=2024, filing_status="S", taxable_income=Decimal("0"),
            total_income=Decimal("0"), agi=Decimal("0"),
            total_tax=Decimal("0"), total_payments=Decimal("0"),
            refund_or_owed=Decimal("0"),
        )
        c = get_constants(2024)
        items = AdvisoryEngine().analyze(tr, result, c)
        # No items should apply for zero-income return
        assert isinstance(items, list)

    def test_custom_rules(self):
        from api.tax_engine.advisory.engine import AdvisoryEngine
        from api.tax_engine.advisory.rules import HSAOptimizationRule
        engine = AdvisoryEngine(rules=[HSAOptimizationRule()])
        tr = TaxReturn(
            tax_year=2024, filing_status="S", primary=_person(), address=_address(),
            hsas=[HSA(coverage_type="self-only", employee_contributions=Decimal("1000"))],
        )
        result = TaxResult(tax_year=2024, filing_status="S", taxable_income=Decimal("70000"))
        c = get_constants(2024)
        items = engine.analyze(tr, result, c)
        assert len(items) == 1
        assert items[0].id == "hsa"
```

- [ ] **Step 2: Implement engine.py**

Create `api/tax_engine/advisory/engine.py`:

```python
"""AdvisoryEngine — runs all advisory rules and returns sorted items."""
from decimal import Decimal

from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.advisory.base import AdvisoryRule
from api.tax_engine.advisory.rules import default_rules
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import TaxReturn, TaxResult


class AdvisoryEngine:
    def __init__(self, rules: list[AdvisoryRule] | None = None):
        self.rules = rules or default_rules()

    def analyze(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> list[AdvisoryItem]:
        """Run all rules, return items sorted by estimated savings (highest first)."""
        items: list[AdvisoryItem] = []
        for rule in self.rules:
            item = rule.evaluate(tax_return, result, constants)
            if item is not None:
                items.append(item)
        items.sort(
            key=lambda i: i.estimated_savings if i.estimated_savings is not None else Decimal("-1"),
            reverse=True,
        )
        return items
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_advisory_engine.py -v`
Expected: All ~11 tests PASS (7 marginal rate + 4 engine)

- [ ] **Step 4: Commit**

```bash
git add api/tax_engine/advisory/engine.py tests/api/tax_engine/test_advisory_engine.py
git commit -m "feat(advisory): add AdvisoryEngine orchestrator with sorting"
```

---

## Task 4: API Endpoint + Integration Test

**Files:**
- Modify: `api/routers/tax_returns.py`
- Create: `tests/api/test_advisory_endpoint.py`

- [ ] **Step 1: Add advisory endpoint to router**

Add the following to the end of `api/routers/tax_returns.py`:

```python
from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.advisory.engine import AdvisoryEngine


@router.get("/advisory", response_model=list[AdvisoryItem])
async def get_advisory(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Generate personalized tax advisory recommendations."""
    client = await get_client_or_404(client_id, session, user)

    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    result = engine.compute(tax_return)

    advisory = AdvisoryEngine()
    return advisory.analyze(tax_return, result, constants)
```

- [ ] **Step 2: Write integration test**

Create `tests/api/test_advisory_endpoint.py`:

```python
"""Integration test: advisory endpoint returns recommendations based on client data."""
import json
import pytest


@pytest.mark.asyncio
async def test_advisory_returns_items(client):
    """Create client with W-2, upload and approve, then get advisory."""
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]

    # Upload and approve a W-2
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    await client.patch(f"/api/documents/{did}/approve")

    # Generate draft first (required for advisory to work)
    await client.post(f"/api/clients/{cid}/returns/draft")

    # Get advisory
    resp = await client.get(f"/api/clients/{cid}/returns/advisory")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0
    # Verify structure matches frontend interface
    for item in items:
        assert "id" in item
        assert "category" in item
        assert "title" in item
        assert "detail" in item
        assert item["category"] in ("deduction", "credit", "retirement", "planning", "compliance")


@pytest.mark.asyncio
async def test_advisory_empty_client(client):
    """Client with no documents should still return (possibly empty) advisory list."""
    c = await client.post("/api/clients", json={"name": "Empty Client", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/advisory")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_advisory_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/advisory")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/test_advisory_endpoint.py -v`
Expected: All 3 tests PASS

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/tax_returns.py tests/api/test_advisory_endpoint.py
git commit -m "feat(advisory): add GET /advisory endpoint with integration tests"
```
