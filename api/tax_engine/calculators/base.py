"""Base calculator with LineTrace support."""
from abc import ABC, abstractmethod
from decimal import Decimal
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn

class BaseCalculator(ABC):
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants
        self._traces: list[LineTrace] = []

    def trace(self, form: str, line: str, label: str, value: Decimal, formula: str,
              inputs: dict[str, str] | None = None, constants_used: dict[str, str] | None = None,
              irs_citation: str | None = None) -> Decimal:
        lt = LineTrace(form=form, line=line, label=label, value=value, formula=formula,
                       inputs=inputs or {}, constants_used=constants_used or {}, irs_citation=irs_citation)
        self._traces.append(lt)
        return value

    def build_result(self, form_name: str, total: Decimal) -> FormResult:
        lines = {t.line: t for t in self._traces}
        return FormResult(form_name=form_name, lines=lines, total=total)

    @abstractmethod
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        pass
