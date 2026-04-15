"""CreditService — child tax credit, education, energy."""
from decimal import Decimal
from api.tax_engine.calculators.form_8812 import Form8812Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, TaxReturn

class CreditService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}
        out["Schedule 8812"] = Form8812Calculator(self.constants).compute(tax_return, results)
        return out
