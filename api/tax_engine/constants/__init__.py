"""Tax year constants package. Importing triggers auto-registration."""
import api.tax_engine.constants.ty2024 as _ty2024  # noqa: F401
import api.tax_engine.constants.ty2025 as _ty2025  # noqa: F401
from api.tax_engine.constants.registry import get_constants, available_years, TaxYearConstants

__all__ = ["get_constants", "available_years", "TaxYearConstants"]
