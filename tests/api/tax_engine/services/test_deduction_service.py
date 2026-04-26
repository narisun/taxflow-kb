"""Unit tests for :class:`api.tax_engine.services.deductions.DeductionService`.

Focuses on adjustments-to-income rules (educator, student loan, HSA) and the
standard-vs-itemized choice — areas not previously covered.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from api.tax_engine.models.deductions import (
    HSA,
    ItemizedDeductions,
    Mortgage1098,
    StudentLoanInterest,
)
from api.tax_engine.models.income import W2
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.services.deductions import DeductionService

pytestmark = pytest.mark.unit


def _simple_return(primary_person, address, **overrides) -> TaxReturn:
    return TaxReturn(
        tax_year=2024,
        filing_status="S",
        primary=primary_person,
        address=address,
        **overrides,
    )


class TestAdjustments:
    def test_educator_expenses_capped_at_300(
        self, constants_2024, primary_person, address
    ):
        tr = _simple_return(
            primary_person, address, educator_expenses=Decimal("500")
        )
        svc = DeductionService(constants_2024)
        out = svc.compute_adjustments(tr, {})
        assert out["adjustments"].total == Decimal("300")

    def test_educator_expenses_partial(self, constants_2024, primary_person, address):
        tr = _simple_return(
            primary_person, address, educator_expenses=Decimal("150")
        )
        svc = DeductionService(constants_2024)
        out = svc.compute_adjustments(tr, {})
        assert out["adjustments"].total == Decimal("150")

    def test_student_loan_interest_capped(
        self, constants_2024, primary_person, address
    ):
        """Cap is $2,500 for 2024 — paying $3,000 should only deduct $2,500."""
        tr = _simple_return(
            primary_person,
            address,
            student_loans=[
                StudentLoanInterest(
                    lender="LoanCo", box1_interest_paid=Decimal("3000")
                )
            ],
        )
        svc = DeductionService(constants_2024)
        out = svc.compute_adjustments(tr, {})
        assert out["adjustments"].total == Decimal("2500")

    def test_hsa_self_only_contribution(self, constants_2024, primary_person, address):
        tr = _simple_return(
            primary_person,
            address,
            hsas=[
                HSA(
                    coverage_type="self-only",
                    employee_contributions=Decimal("2000"),
                    employer_contributions=Decimal("500"),
                )
            ],
        )
        svc = DeductionService(constants_2024)
        out = svc.compute_adjustments(tr, {})
        # 2024 self-only limit $4,150, employer covered $500, so cap on
        # employee deduction is min($2,000, $3,650) = $2,000.
        assert out["adjustments"].total == Decimal("2000")

    def test_hsa_cannot_exceed_remaining_limit(
        self, constants_2024, primary_person, address
    ):
        tr = _simple_return(
            primary_person,
            address,
            hsas=[
                HSA(
                    coverage_type="self-only",
                    employee_contributions=Decimal("5000"),
                    employer_contributions=Decimal("500"),
                )
            ],
        )
        svc = DeductionService(constants_2024)
        out = svc.compute_adjustments(tr, {})
        # Limit - employer = $4,150 - $500 = $3,650 allowed
        assert out["adjustments"].total == Decimal("3650")


class TestStandardVsItemized:
    def test_picks_standard_when_itemized_is_lower(
        self, constants_2024, primary_person, address
    ):
        tr = _simple_return(
            primary_person,
            address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("50000"),
                    box2_fed_withheld=Decimal("5000"),
                    box3_ss_wages=Decimal("50000"),
                    box5_medicare_wages=Decimal("50000"),
                )
            ],
            mortgages=[
                Mortgage1098(
                    lender="Bank",
                    box1_interest=Decimal("1000"),  # tiny — well below standard
                )
            ],
        )
        svc = DeductionService(constants_2024)
        adj = svc.compute_adjustments(tr, {})
        ded = svc.compute_deductions(tr, adj)
        assert ded["deduction"].total == Decimal("14600")
        assert ded["deduction"].lines["12"].label == "Standard deduction"

    def test_picks_itemized_when_higher_than_standard(
        self, constants_2024, primary_person, address
    ):
        tr = _simple_return(
            primary_person,
            address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("200000"),
                    box2_fed_withheld=Decimal("30000"),
                    box3_ss_wages=Decimal("200000"),
                    box5_medicare_wages=Decimal("200000"),
                )
            ],
            itemized=ItemizedDeductions(
                mortgage_interest_1098=Decimal("25000"),
                salt_real_estate=Decimal("9000"),
                salt_income_or_sales=Decimal("8000"),
            ),
        )
        svc = DeductionService(constants_2024)
        adj = svc.compute_adjustments(tr, {})
        ded = svc.compute_deductions(tr, adj)
        # Itemized = 25k mortgage interest + $10k SALT cap = $35k > $14.6k standard
        assert ded["deduction"].total > Decimal("14600")
        assert ded["deduction"].lines["12"].label == "Itemized deductions"
