"""Tests for Schedule D."""
from decimal import Decimal
from api.tax_engine.models.income import Income1099B

class TestScheduleD:
    def test_net_short_term_gain(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        minimal_return.broker_1099s = [Income1099B(payer="Fidelity", short_term_proceeds=Decimal("15000"), short_term_cost_basis=Decimal("10000"))]
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["7"].value == Decimal("5000")

    def test_net_long_term_gain(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        minimal_return.broker_1099s = [Income1099B(payer="Fidelity", long_term_proceeds=Decimal("50000"), long_term_cost_basis=Decimal("30000"))]
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["15"].value == Decimal("20000")

    def test_capital_loss_limited(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        minimal_return.broker_1099s = [Income1099B(payer="Fidelity", long_term_proceeds=Decimal("5000"), long_term_cost_basis=Decimal("20000"))]
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["21"].value == Decimal("-3000")

    def test_capital_loss_limit_mfs(self, mfj_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        mfj_return.filing_status = "MFS"
        mfj_return.broker_1099s = [Income1099B(payer="Fidelity", short_term_proceeds=Decimal("1000"), short_term_cost_basis=Decimal("10000"))]
        result = ScheduleDCalculator(constants_2024).compute(mfj_return, {})
        assert result.lines["21"].value == Decimal("-1500")

    def test_wash_sale_adjustment(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        minimal_return.broker_1099s = [Income1099B(payer="Fidelity", short_term_proceeds=Decimal("10000"), short_term_cost_basis=Decimal("12000"), short_term_wash_sales=Decimal("500"))]
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["7"].value == Decimal("-1500")

    def test_no_investments(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.total == Decimal("0")

    def test_carryforward(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
        minimal_return.capital_loss_carryforward_lt = Decimal("2000")
        minimal_return.broker_1099s = [Income1099B(payer="Fidelity", long_term_proceeds=Decimal("5000"), long_term_cost_basis=Decimal("3000"))]
        result = ScheduleDCalculator(constants_2024).compute(minimal_return, {})
        assert result.lines["15"].value == Decimal("0")
