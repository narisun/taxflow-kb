"""ValidationEngine — runs all rules against a TaxReturn."""
from api.tax_engine.validation.base import ValidationResult, ValidationRule
from api.tax_engine.validation.rules import default_rules
from api.tax_engine.models.tax_return import TaxReturn

_SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

class ValidationEngine:
    def __init__(self, rules: list[ValidationRule] | None = None):
        self.rules = rules or default_rules()

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for rule in self.rules:
            results.extend(rule.validate(tax_return))
        results.sort(key=lambda r: _SEVERITY_ORDER.get(r.severity, 99))
        return results

    def validate_errors_only(self, tax_return: TaxReturn) -> list[ValidationResult]:
        return [r for r in self.validate(tax_return) if r.severity == "ERROR"]

    def has_errors(self, tax_return: TaxReturn) -> bool:
        return any(r.severity == "ERROR" for r in self.validate(tax_return))
