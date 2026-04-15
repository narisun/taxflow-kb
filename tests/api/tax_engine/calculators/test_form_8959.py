"""Tests for Form 8959."""
from decimal import Decimal
from api.tax_engine.models.income import W2

class TestForm8959:
    def test_above_threshold_single(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator
        minimal_return.w2s = [W2(employer_name="Acme", employer_ein="12-3456789", box5_medicare_wages=Decimal("250000"), box6_medicare_withheld=Decimal("3625"))]
        result = Form8959Calculator(constants_2024).compute(minimal_return, {})
        assert result.lines["18"].value == Decimal("450")

    def test_below_threshold(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator
        minimal_return.w2s = [W2(employer_name="Acme", employer_ein="12-3456789", box5_medicare_wages=Decimal("150000"))]
        result = Form8959Calculator(constants_2024).compute(minimal_return, {})
        assert result.lines["18"].value == Decimal("0")

    def test_mfj_threshold(self, mfj_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator
        mfj_return.w2s = [W2(employer_name="Acme", employer_ein="12-3456789", box5_medicare_wages=Decimal("300000"), person_role="primary")]
        result = Form8959Calculator(constants_2024).compute(mfj_return, {})
        assert result.lines["18"].value == Decimal("450")
