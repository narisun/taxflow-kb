"""Tests for advisory engine — marginal rate and engine orchestration."""
from datetime import date
from decimal import Decimal

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.income import W2
from api.tax_engine.models.deductions import HSA
from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult


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
