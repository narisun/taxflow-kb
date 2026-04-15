"""FastAPI dependency providers for the tax engine."""
import api.tax_engine.constants  # noqa: F401 — trigger registration
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.services.engine import TaxCalculationEngine
from api.tax_engine.validation.engine import ValidationEngine
from api.tax_engine.assembler import DocumentAssembler


def get_tax_engine(tax_year: int = 2024) -> TaxCalculationEngine:
    constants = get_constants(tax_year)
    return TaxCalculationEngine(constants)


def get_validation_engine() -> ValidationEngine:
    return ValidationEngine()


def get_assembler() -> DocumentAssembler:
    return DocumentAssembler()
