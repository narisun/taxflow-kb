"""Tests for Form 8995."""
from decimal import Decimal
from api.tax_engine.models.income import ScheduleC, ScheduleK1
from api.tax_engine.models.tax_return import FormResult, LineTrace

def _ti_result(ti: Decimal) -> dict[str, FormResult]:
    return {"taxable_income_before_qbi": FormResult(form_name="pre-QBI", total=ti, lines={"15": LineTrace(form="1040", line="15", label="TI", value=ti, formula="test")})}

class TestForm8995Simple:
    def test_simple_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Consulting", gross_receipts=Decimal("100000"))]
        result = Form8995Calculator(constants_2024).compute(minimal_return, _ti_result(Decimal("85400")))
        assert result.lines["15"].value == Decimal("17080")

    def test_uncapped_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Consulting", gross_receipts=Decimal("50000"))]
        result = Form8995Calculator(constants_2024).compute(minimal_return, _ti_result(Decimal("100000")))
        assert result.lines["15"].value == Decimal("10000")

class TestForm8995Complex:
    def test_wage_limited(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Big Biz", gross_receipts=Decimal("500000"), w2_wages_paid=Decimal("100000"), ubia_qualified_property=Decimal("0"))]
        result = Form8995Calculator(constants_2024).compute(minimal_return, _ti_result(Decimal("500000")))
        assert result.lines["15"].value == Decimal("50000")

class TestForm8995SSTB:
    def test_sstb_fully_phased_out(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator
        minimal_return.schedule_cs = [ScheduleC(business_name="Law Firm", gross_receipts=Decimal("500000"), is_sstb=True, w2_wages_paid=Decimal("200000"))]
        result = Form8995Calculator(constants_2024).compute(minimal_return, _ti_result(Decimal("300000")))
        assert result.lines["15"].value == Decimal("0")

class TestForm8995K1:
    def test_k1_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator
        minimal_return.k1s = [ScheduleK1(entity_name="XYZ", entity_ein="11-2222222", entity_type="S", box20z_section_199a_qbi=Decimal("80000"), w2_wages_for_qbi=Decimal("50000"))]
        result = Form8995Calculator(constants_2024).compute(minimal_return, _ti_result(Decimal("100000")))
        assert result.lines["15"].value == Decimal("16000")
