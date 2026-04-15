"""Tests for Form 8960."""
from decimal import Decimal
from api.tax_engine.models.tax_return import FormResult, LineTrace

def _agi_result(agi: Decimal) -> dict[str, FormResult]:
    return {
        "AGI": FormResult(form_name="AGI", total=agi, lines={"11": LineTrace(form="1040", line="11", label="AGI", value=agi, formula="test")}),
        "Schedule B": FormResult(form_name="Schedule B", total=Decimal("5000"),
            lines={"4": LineTrace(form="Schedule B", line="4", label="Interest", value=Decimal("3000"), formula="test"),
                   "6": LineTrace(form="Schedule B", line="6", label="Dividends", value=Decimal("2000"), formula="test")}),
    }

class TestForm8960:
    def test_above_threshold(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator
        result = Form8960Calculator(constants_2024).compute(minimal_return, _agi_result(Decimal("250000")))
        assert result.lines["17"].value == Decimal("190.00")

    def test_below_threshold(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator
        result = Form8960Calculator(constants_2024).compute(minimal_return, _agi_result(Decimal("150000")))
        assert result.lines["17"].value == Decimal("0")

    def test_nii_less_than_excess(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator
        result = Form8960Calculator(constants_2024).compute(minimal_return, _agi_result(Decimal("300000")))
        assert result.lines["17"].value == Decimal("190.00")
