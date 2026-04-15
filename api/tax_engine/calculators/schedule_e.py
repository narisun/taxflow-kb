"""Schedule E — Supplemental Income (Rental Real Estate, K-1 Passthrough)."""
from decimal import Decimal
from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule E"

class ScheduleECalculator(BaseCalculator):
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        total_rental = Decimal("0")
        for i, rp in enumerate(tax_return.rental_properties):
            net = rp.net_income
            line = "26" if i == 0 else f"26_{i+1}"
            self.trace(FORM, line, f"Net rental income — {rp.address}", net,
                       "rent_received - total_expenses",
                       inputs={"rent": str(rp.rent_received), "expenses": str(rp.total_expenses)})
            total_rental += net
        if not tax_return.rental_properties:
            self.trace(FORM, "26", "Net rental income", Decimal("0"), "no rental properties")

        total_k1 = Decimal("0")
        for i, k1 in enumerate(tax_return.k1s):
            income = k1.box1_ordinary_income + k1.box2_rental_income + k1.box4a_guaranteed_payments
            line = "32" if i == 0 else f"32_{i+1}"
            self.trace(FORM, line, f"K-1 income — {k1.entity_name}", income,
                       "box1 + box2 + box4a",
                       inputs={"box1": str(k1.box1_ordinary_income), "box2": str(k1.box2_rental_income), "box4a": str(k1.box4a_guaranteed_payments)})
            total_k1 += income
        if not tax_return.k1s:
            self.trace(FORM, "32", "K-1 income", Decimal("0"), "no K-1s")

        total = total_rental + total_k1
        return self.build_result(FORM, total)
