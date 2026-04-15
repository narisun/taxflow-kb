"""Tests for tax year constants registry."""
import pytest
from decimal import Decimal


class TestRegistry:
    def test_get_2024(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.tax_year == 2024

    def test_get_2025(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2025)
        assert c.tax_year == 2025

    def test_unknown_year_raises(self):
        from api.tax_engine.constants.registry import get_constants
        with pytest.raises(ValueError, match="No tax constants"):
            get_constants(1999)

    def test_available_years(self):
        from api.tax_engine.constants.registry import available_years
        years = available_years()
        assert 2024 in years
        assert 2025 in years


class TestTY2024Values:
    def test_standard_deduction_single(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.standard_deduction["S"] == Decimal("14600")

    def test_standard_deduction_mfj(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.standard_deduction["MFJ"] == Decimal("29200")

    def test_ss_wage_base(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.ss_wage_base == Decimal("168600")

    def test_ctc_amount(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.ctc_amount_per_child == Decimal("2000")

    def test_salt_cap(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.salt_cap["MFJ"] == Decimal("10000")

    def test_tax_brackets_7_rates(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert len(c.ordinary_brackets["S"]) == 7
        assert c.ordinary_brackets["S"][0] == (Decimal("11600"), Decimal("0.10"))

    def test_qbi_threshold(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2024)
        assert c.qbi_threshold["MFJ"] == Decimal("383900")


class TestTY2025Values:
    def test_standard_deduction_single(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2025)
        assert c.standard_deduction["S"] == Decimal("15000")

    def test_ctc_amount_increased(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2025)
        assert c.ctc_amount_per_child == Decimal("2200")

    def test_salt_cap_increased(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2025)
        assert c.salt_cap["MFJ"] == Decimal("40000")

    def test_ss_wage_base_2025(self):
        from api.tax_engine.constants.registry import get_constants
        c = get_constants(2025)
        assert c.ss_wage_base == Decimal("176100")
