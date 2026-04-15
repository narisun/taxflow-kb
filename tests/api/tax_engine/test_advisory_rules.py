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
