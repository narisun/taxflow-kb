"""Tests for Schedule C."""
from decimal import Decimal
from api.tax_engine.models.income import ScheduleC

class TestScheduleC:
    def test_single_business(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Consulting LLC", gross_receipts=Decimal("120000"), cost_of_goods_sold=Decimal("10000"), advertising=Decimal("2000"), supplies=Decimal("3000"))]
        result = ScheduleCCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["31"].value == Decimal("105000")

    def test_multiple_businesses(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
        minimal_return.schedule_cs = [ScheduleC(business_name="A", gross_receipts=Decimal("50000")), ScheduleC(business_name="B", gross_receipts=Decimal("30000"), advertising=Decimal("5000"))]
        result = ScheduleCCalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("75000")

    def test_no_businesses(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
        result = ScheduleCCalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("0")

    def test_loss(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Startup", gross_receipts=Decimal("5000"), rent_lease=Decimal("12000"))]
        result = ScheduleCCalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("-7000")
