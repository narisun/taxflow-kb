"""Validation base classes."""
from abc import ABC, abstractmethod
from typing import Literal
from pydantic import BaseModel
from api.tax_engine.models.tax_return import TaxReturn

class ValidationResult(BaseModel):
    rule_id: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    message: str
    affected_fields: list[str] = []
    suggestion: str | None = None

class ValidationRule(ABC):
    rule_id: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    description: str

    @abstractmethod
    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        pass
