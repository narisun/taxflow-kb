"""AdvisoryEngine — runs all advisory rules and returns sorted items."""
from decimal import Decimal

from api.tax_engine.advisory.models import AdvisoryItem
from api.tax_engine.advisory.base import AdvisoryRule
from api.tax_engine.advisory.rules import default_rules
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import TaxReturn, TaxResult


class AdvisoryEngine:
    def __init__(self, rules: list[AdvisoryRule] | None = None):
        self.rules = rules or default_rules()

    def analyze(
        self, tax_return: TaxReturn, result: TaxResult, constants: TaxYearConstants
    ) -> list[AdvisoryItem]:
        """Run all rules, return items sorted by estimated savings (highest first)."""
        items: list[AdvisoryItem] = []
        for rule in self.rules:
            item = rule.evaluate(tax_return, result, constants)
            if item is not None:
                items.append(item)
        items.sort(
            key=lambda i: i.estimated_savings if i.estimated_savings is not None else Decimal("-1"),
            reverse=True,
        )
        return items
