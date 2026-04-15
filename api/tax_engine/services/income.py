"""IncomeService — orchestrates income calculators."""
from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
from api.tax_engine.calculators.schedule_e import ScheduleECalculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, TaxReturn

class IncomeService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}
        out["Schedule B"] = ScheduleBCalculator(self.constants).compute(tax_return, results)
        out["Schedule C"] = ScheduleCCalculator(self.constants).compute(tax_return, results)
        out["Schedule D"] = ScheduleDCalculator(self.constants).compute(tax_return, results)
        out["Schedule E"] = ScheduleECalculator(self.constants).compute(tax_return, results)
        return out
