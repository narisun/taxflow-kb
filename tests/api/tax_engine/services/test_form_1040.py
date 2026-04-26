"""End-to-end assertions on the Form 1040 line composition.

These are integration-flavored unit tests: they run the real service graph
via :class:`TaxCalculationEngine`, then assert on specific 1040 lines. They
cover the gap left by ``test_engine.py`` which only checked aggregate totals.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from api.tax_engine.models.income import (
    Income1099Div,
    Income1099Int,
    Income1099NEC,
    W2,
)
from api.tax_engine.models.people import Address, Dependent, Person
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.services.engine import TaxCalculationEngine

pytestmark = pytest.mark.unit


def _line(result, line_num: str) -> Decimal:
    f1040 = result.form_results["1040"]
    return f1040.lines[line_num].value


class TestForm1040LineComposition:
    def test_wages_flow_to_line_1a(self, constants_2024, primary_person, address):
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("40000"),
                    box2_fed_withheld=Decimal("4000"),
                    box3_ss_wages=Decimal("40000"),
                    box5_medicare_wages=Decimal("40000"),
                ),
                W2(
                    employer_name="BETA",
                    employer_ein="98-7654321",
                    box1_wages=Decimal("25000"),
                    box2_fed_withheld=Decimal("2500"),
                    box3_ss_wages=Decimal("25000"),
                    box5_medicare_wages=Decimal("25000"),
                ),
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert _line(result, "1a") == Decimal("65000")

    def test_interest_and_dividends_populate_lines_2b_and_3b(
        self, constants_2024, primary_person, address
    ):
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            interest_1099s=[Income1099Int(payer="Chase", box1_interest=Decimal("1500"))],
            dividend_1099s=[
                Income1099Div(
                    payer="Vanguard",
                    box1a_ordinary_dividends=Decimal("2200"),
                    box1b_qualified_dividends=Decimal("1800"),
                )
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert _line(result, "2b") == Decimal("1500")
        assert _line(result, "3b") == Decimal("2200")

    def test_nec_income_included_in_line_8(self, constants_2024, primary_person, address):
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            nec_1099s=[
                Income1099NEC(
                    payer="Consulting",
                    nec_compensation=Decimal("18000"),
                    fed_tax_withheld=Decimal("0"),
                )
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        # Schedule C flows to line 8, 1099-NEC stacked on top.
        assert _line(result, "8") >= Decimal("18000")

    def test_standard_deduction_applied_single_2024(
        self, constants_2024, primary_person, address
    ):
        """Single standard deduction for 2024 is $14,600."""
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("60000"),
                    box2_fed_withheld=Decimal("6000"),
                    box3_ss_wages=Decimal("60000"),
                    box5_medicare_wages=Decimal("60000"),
                )
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert _line(result, "12") == Decimal("14600")
        assert _line(result, "15") == Decimal("45400")  # 60k - 14.6k

    def test_refund_surfaces_on_line_35a_when_withholding_exceeds_tax(
        self, constants_2024, primary_person, address
    ):
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("40000"),
                    box2_fed_withheld=Decimal("15000"),  # massively over-withheld
                    box3_ss_wages=Decimal("40000"),
                    box5_medicare_wages=Decimal("40000"),
                )
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert "35a" in result.form_results["1040"].lines
        assert _line(result, "35a") > Decimal("0")
        assert "37" not in result.form_results["1040"].lines

    def test_balance_due_surfaces_on_line_37_when_tax_exceeds_withholding(
        self, constants_2024, primary_person, address
    ):
        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=primary_person,
            address=address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("150000"),
                    box2_fed_withheld=Decimal("0"),  # nothing withheld
                    box3_ss_wages=Decimal("150000"),
                    box5_medicare_wages=Decimal("150000"),
                )
            ],
        )
        result = TaxCalculationEngine(constants_2024).compute(tr)
        assert "37" in result.form_results["1040"].lines
        assert _line(result, "37") > Decimal("0")

    def test_ctc_reduces_total_tax_mfj(
        self, constants_2024, primary_person, spouse_person, address
    ):
        """MFJ with one qualifying child — CTC should reduce total tax."""
        kid = Dependent(
            first_name="K",
            last_name="D",
            ssn="111223333",
            relationship="son",
            date_of_birth=date(2015, 1, 1),
        )
        without_kid = TaxReturn(
            tax_year=2024,
            filing_status="MFJ",
            primary=primary_person,
            spouse=spouse_person,
            address=address,
            w2s=[
                W2(
                    employer_name="ACME",
                    employer_ein="12-3456789",
                    box1_wages=Decimal("90000"),
                    box2_fed_withheld=Decimal("10000"),
                    box3_ss_wages=Decimal("90000"),
                    box5_medicare_wages=Decimal("90000"),
                )
            ],
        )
        with_kid = without_kid.model_copy(update={"dependents": [kid]})

        baseline = TaxCalculationEngine(constants_2024).compute(without_kid)
        with_credit = TaxCalculationEngine(constants_2024).compute(with_kid)
        # With one qualifying child and wages ~90k, CTC is $2,000.
        assert _line(baseline, "24") - _line(with_credit, "24") == Decimal("2000")
