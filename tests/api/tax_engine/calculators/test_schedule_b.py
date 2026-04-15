"""Tests for Schedule B — Interest and Ordinary Dividends."""
from decimal import Decimal
from api.tax_engine.models.income import Income1099Int, Income1099Div

class TestScheduleB:
    def test_single_interest(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
        minimal_return.interest_1099s = [Income1099Int(payer="Chase", box1_interest=Decimal("1500"))]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("1500")

    def test_multiple_interest_sources(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
        minimal_return.interest_1099s = [
            Income1099Int(payer="Chase", box1_interest=Decimal("1500")),
            Income1099Int(payer="Ally", box1_interest=Decimal("800")),
        ]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("2300")

    def test_dividends(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
        minimal_return.dividend_1099s = [Income1099Div(payer="Vanguard", box1a_ordinary_dividends=Decimal("5000"), box1b_qualified_dividends=Decimal("4000"))]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["6"].value == Decimal("5000")

    def test_no_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("0")
        assert result.total == Decimal("0")

    def test_traces_have_form_name(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
        minimal_return.interest_1099s = [Income1099Int(payer="Chase", box1_interest=Decimal("1000"))]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.form_name == "Schedule B"
        assert result.lines["4"].form == "Schedule B"
