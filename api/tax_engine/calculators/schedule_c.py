"""Schedule C — Profit or Loss from Business (Sole Proprietorship)."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule C"

class ScheduleCCalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        total_net = Decimal("0")
        for i, sc in enumerate(tax_return.schedule_cs):
            net = sc.net_profit
            self.trace(FORM, "31" if i == 0 else f"31_{i+1}", f"Net profit — {sc.business_name}", net,
                       "gross_receipts - COGS - total_expenses",
                       inputs={"gross_receipts": str(sc.gross_receipts), "cogs": str(sc.cost_of_goods_sold), "total_expenses": str(sc.total_expenses)})
            total_net += net
        if not tax_return.schedule_cs:
            self.trace(FORM, "31", "Net profit", Decimal("0"), "no businesses")
        return self.build_result(FORM, total_net)
