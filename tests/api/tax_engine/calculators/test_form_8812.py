"""Tests for Form 8812."""
from datetime import date
from decimal import Decimal
from api.tax_engine.models.people import Dependent
from api.tax_engine.models.tax_return import FormResult, LineTrace

def _tax_result(agi: Decimal, tax: Decimal, earned: Decimal) -> dict[str, FormResult]:
    return {
        "AGI": FormResult(form_name="AGI", total=agi, lines={"11": LineTrace(form="1040", line="11", label="AGI", value=agi, formula="test")}),
        "tax_before_credits": FormResult(form_name="tax", total=tax, lines={"16": LineTrace(form="1040", line="16", label="Tax", value=tax, formula="test")}),
        "earned_income": FormResult(form_name="earned", total=earned, lines={"earned": LineTrace(form="1040", line="earned", label="Earned income", value=earned, formula="test")}),
    }

class TestForm8812:
    def test_two_children_2024(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator
        minimal_return.dependents = [
            Dependent(first_name="A", last_name="Doe", ssn="111223333", relationship="son", date_of_birth=date(2015, 1, 1)),
            Dependent(first_name="B", last_name="Doe", ssn="444556666", relationship="daughter", date_of_birth=date(2018, 6, 1)),
        ]
        result = Form8812Calculator(constants_2024).compute(minimal_return, _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000")))
        assert result.lines["nonrefundable"].value == Decimal("4000")

    def test_phase_out_single(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator
        minimal_return.dependents = [Dependent(first_name="A", last_name="Doe", ssn="111223333", relationship="son", date_of_birth=date(2015, 1, 1))]
        result = Form8812Calculator(constants_2024).compute(minimal_return, _tax_result(Decimal("210000"), Decimal("30000"), Decimal("210000")))
        assert result.lines["nonrefundable"].value == Decimal("1500")

    def test_other_dependent(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator
        minimal_return.dependents = [Dependent(first_name="A", last_name="Doe", ssn="111223333", relationship="parent", date_of_birth=date(1955, 1, 1), is_qualifying_child=False)]
        result = Form8812Calculator(constants_2024).compute(minimal_return, _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000")))
        assert result.lines["other_dependent"].value == Decimal("500")

    def test_no_dependents(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator
        result = Form8812Calculator(constants_2024).compute(minimal_return, _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000")))
        assert result.total == Decimal("0")

    def test_2025_increased(self, minimal_return, constants_2025):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator
        minimal_return.tax_year = 2025
        minimal_return.dependents = [Dependent(first_name="A", last_name="Doe", ssn="111223333", relationship="son", date_of_birth=date(2015, 1, 1))]
        result = Form8812Calculator(constants_2025).compute(minimal_return, _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000")))
        assert result.lines["nonrefundable"].value == Decimal("2200")
