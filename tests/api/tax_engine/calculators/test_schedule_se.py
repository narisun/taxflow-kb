"""Tests for Schedule SE."""
from decimal import Decimal
from api.tax_engine.models.tax_return import FormResult, LineTrace
from api.tax_engine.models.income import W2

def _schedule_c_result(net_profit: Decimal) -> dict[str, FormResult]:
    return {"Schedule C": FormResult(form_name="Schedule C", lines={"31": LineTrace(form="Schedule C", line="31", label="Net profit", value=net_profit, formula="test")}, total=net_profit)}

class TestScheduleSE:
    def test_basic_se_tax(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
        result = ScheduleSECalculator(constants_2024).compute(minimal_return, _schedule_c_result(Decimal("100000")))
        assert result.lines["12"].value == Decimal("14129.55")

    def test_deductible_half(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
        result = ScheduleSECalculator(constants_2024).compute(minimal_return, _schedule_c_result(Decimal("100000")))
        assert result.lines["13"].value == Decimal("7064.78")

    def test_ss_wage_cap_with_w2(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
        minimal_return.w2s = [W2(employer_name="Acme", employer_ein="12-3456789", box3_ss_wages=Decimal("150000"))]
        result = ScheduleSECalculator(constants_2024).compute(minimal_return, _schedule_c_result(Decimal("50000")))
        assert result.lines["12"].value == Decimal("3645.48")

    def test_no_se_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
        result = ScheduleSECalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("0")
