"""Tests for Schedule E."""
from decimal import Decimal
from api.tax_engine.models.deductions import RentalProperty
from api.tax_engine.models.income import ScheduleK1

class TestScheduleE:
    def test_single_rental(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator
        minimal_return.rental_properties = [RentalProperty(address="456 Oak Ave", rent_received=Decimal("24000"), mortgage_interest=Decimal("8000"), taxes=Decimal("4000"), insurance=Decimal("2000"))]
        result = ScheduleECalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["26"].value == Decimal("10000")

    def test_k1_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator
        minimal_return.k1s = [ScheduleK1(entity_name="ABC Partners", entity_ein="98-7654321", entity_type="P", box1_ordinary_income=Decimal("50000"))]
        result = ScheduleECalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["32"].value == Decimal("50000")

    def test_combined(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator
        minimal_return.rental_properties = [RentalProperty(address="123 St", rent_received=Decimal("12000"), taxes=Decimal("2000"))]
        minimal_return.k1s = [ScheduleK1(entity_name="XYZ", entity_ein="11-2222222", entity_type="S", box1_ordinary_income=Decimal("30000"))]
        result = ScheduleECalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("40000")

    def test_empty(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator
        result = ScheduleECalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("0")
