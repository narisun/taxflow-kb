"""Tests for Schedule A."""
from decimal import Decimal
from api.tax_engine.models.deductions import ItemizedDeductions
from api.tax_engine.models.tax_return import FormResult, LineTrace

def _agi_result(agi: Decimal) -> dict[str, FormResult]:
    return {"AGI": FormResult(form_name="AGI", lines={"11": LineTrace(form="1040", line="11", label="AGI", value=agi, formula="test")}, total=agi)}

class TestScheduleA:
    def test_salt_capped_2024(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.itemized = ItemizedDeductions(salt_income_or_sales=Decimal("15000"), salt_real_estate=Decimal("8000"))
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["7"].value == Decimal("10000")

    def test_salt_capped_2025(self, minimal_return, constants_2025):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.tax_year = 2025
        minimal_return.itemized = ItemizedDeductions(salt_income_or_sales=Decimal("35000"), salt_real_estate=Decimal("8000"))
        result = ScheduleACalculator(constants_2025).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["7"].value == Decimal("40000")

    def test_medical_agi_floor(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.itemized = ItemizedDeductions(medical_dental=Decimal("12000"))
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["4"].value == Decimal("4500")

    def test_medical_below_floor(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.itemized = ItemizedDeductions(medical_dental=Decimal("5000"))
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["4"].value == Decimal("0")

    def test_charity(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.itemized = ItemizedDeductions(charity_cash=Decimal("5000"), charity_noncash=Decimal("2000"))
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["14"].value == Decimal("7000")

    def test_mortgage_interest(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        minimal_return.itemized = ItemizedDeductions(mortgage_interest_1098=Decimal("12000"), mortgage_interest_other=Decimal("1000"))
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["10"].value == Decimal("13000")

    def test_no_itemized(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator
        result = ScheduleACalculator(constants_2024).compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.total == Decimal("0")
