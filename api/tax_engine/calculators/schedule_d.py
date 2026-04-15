"""Schedule D — Capital Gains and Losses."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule D"

class ScheduleDCalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        fs = tax_return.filing_status
        loss_limit = self.constants.capital_loss_limit[fs]

        # Part I: Short-term
        st_proceeds = sum((b.short_term_proceeds for b in tax_return.broker_1099s), Decimal("0"))
        st_basis = sum((b.short_term_cost_basis for b in tax_return.broker_1099s), Decimal("0"))
        st_wash = sum((b.short_term_wash_sales for b in tax_return.broker_1099s), Decimal("0"))
        st_carryforward = -tax_return.capital_loss_carryforward_st
        net_st = st_proceeds - st_basis + st_wash + st_carryforward
        self.trace(FORM, "7", "Net short-term capital gain/loss", net_st,
                   "proceeds - basis + wash_sale_disallowed + carryforward",
                   inputs={"proceeds": str(st_proceeds), "basis": str(st_basis), "wash_sales": str(st_wash), "carryforward": str(st_carryforward)})

        # Part II: Long-term
        lt_proceeds = sum((b.long_term_proceeds for b in tax_return.broker_1099s), Decimal("0"))
        lt_basis = sum((b.long_term_cost_basis for b in tax_return.broker_1099s), Decimal("0"))
        lt_wash = sum((b.long_term_wash_sales for b in tax_return.broker_1099s), Decimal("0"))
        lt_carryforward = -tax_return.capital_loss_carryforward_lt
        cap_gain_dist = sum((d.box2a_capital_gain_distributions for d in tax_return.dividend_1099s), Decimal("0"))
        net_lt = lt_proceeds - lt_basis + lt_wash + lt_carryforward + cap_gain_dist
        self.trace(FORM, "15", "Net long-term capital gain/loss", net_lt,
                   "proceeds - basis + wash_sales + carryforward + cap_gain_distributions",
                   inputs={"proceeds": str(lt_proceeds), "basis": str(lt_basis), "wash_sales": str(lt_wash),
                           "carryforward": str(lt_carryforward), "distributions": str(cap_gain_dist)})

        # Part III: Summary — apply capital loss limitation
        net_total = net_st + net_lt
        if net_total < Decimal("0"):
            limited = max(net_total, -loss_limit)
        else:
            limited = net_total
        self.trace(FORM, "21", "Capital gain/loss (limited)", limited,
                   "max(net_st + net_lt, -loss_limit)",
                   inputs={"net_st": str(net_st), "net_lt": str(net_lt)},
                   constants_used={"loss_limit": str(loss_limit)}, irs_citation="IRC §1211(b)")
        return self.build_result(FORM, limited)
