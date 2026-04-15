"""TaxCalculationEngine — top-level orchestrator."""
from decimal import Decimal
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.calculators.form_1040 import Form1040Calculator
from api.tax_engine.models.tax_return import FormResult, TaxResult, TaxReturn
from api.tax_engine.services.income import IncomeService
from api.tax_engine.services.deductions import DeductionService
from api.tax_engine.services.credits import CreditService
from api.tax_engine.services.liability import LiabilityService

class TaxCalculationEngine:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants
        self.income_service = IncomeService(constants)
        self.deduction_service = DeductionService(constants)
        self.credit_service = CreditService(constants)
        self.liability_service = LiabilityService(constants)

    def compute(self, tax_return: TaxReturn) -> TaxResult:
        results: dict[str, FormResult] = {}

        # Phase 1: Income
        results.update(self.income_service.compute(tax_return, results))

        # Phase 2: SE tax (needed for SE deduction in adjustments)
        se_results = self.liability_service.compute(tax_return, results)
        if "Schedule SE" in se_results:
            results["Schedule SE"] = se_results["Schedule SE"]

        # Phase 3: AGI adjustments
        results.update(self.deduction_service.compute_adjustments(tax_return, results))

        # Phase 4: Deductions (standard vs itemized, QBI)
        results.update(self.deduction_service.compute_deductions(tax_return, results))

        # Phase 5: Tax liability (brackets, surtaxes)
        liability_results = self.liability_service.compute(tax_return, results)
        results.update(liability_results)

        # Phase 6: Credits
        ordinary_tax = results.get("ordinary_tax")
        if ordinary_tax:
            results["tax_before_credits"] = FormResult(
                form_name="tax", total=ordinary_tax.total,
                lines={"16": ordinary_tax.lines.get("16")})  # type: ignore[dict-item]
        results.update(self.credit_service.compute(tax_return, results))

        # Phase 7: Final 1040 assembly
        form1040 = Form1040Calculator(self.constants)
        results["1040"] = form1040.compute(tax_return, results)

        return self._build_result(tax_return, results)

    def _build_result(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> TaxResult:
        f1040 = results.get("1040")
        all_traces = []
        for fr in results.values():
            all_traces.extend(fr.lines.values())

        def _line_val(line: str) -> Decimal:
            if f1040 and line in f1040.lines:
                return f1040.lines[line].value
            return Decimal("0")

        return TaxResult(
            tax_year=tax_return.tax_year,
            filing_status=tax_return.filing_status,
            form_results=results,
            total_income=_line_val("9"),
            agi=_line_val("11"),
            taxable_income=_line_val("15"),
            total_tax=_line_val("24"),
            total_credits=Decimal("0"),
            total_payments=_line_val("33"),
            refund_or_owed=f1040.total if f1040 else Decimal("0"),
            all_traces=all_traces,
        )
