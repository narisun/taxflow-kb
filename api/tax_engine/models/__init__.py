"""Tax engine domain models — re-exports for convenience."""
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import (
    W2, Income1099Int, Income1099Div, Income1099B, Income1099NEC,
    Income1099R, IncomeSSA1099, ScheduleC, ScheduleK1, PersonRole,
)
from api.tax_engine.models.deductions import (
    ItemizedDeductions, Mortgage1098, HSA, IRAContribution,
    StudentLoanInterest, RentalProperty,
)
from api.tax_engine.models.credits import (
    DependentCareExpense, Tuition1098T, EnergyImprovement,
    ResidentialCleanEnergy, Form1095A, EstimatedPayment,
)
from api.tax_engine.models.tax_return import (
    TaxReturn, LineTrace, FormResult, TaxResult, FilingStatus,
)

__all__ = [
    "Person", "Dependent", "Address",
    "W2", "Income1099Int", "Income1099Div", "Income1099B", "Income1099NEC",
    "Income1099R", "IncomeSSA1099", "ScheduleC", "ScheduleK1", "PersonRole",
    "ItemizedDeductions", "Mortgage1098", "HSA", "IRAContribution",
    "StudentLoanInterest", "RentalProperty",
    "DependentCareExpense", "Tuition1098T", "EnergyImprovement",
    "ResidentialCleanEnergy", "Form1095A", "EstimatedPayment",
    "TaxReturn", "LineTrace", "FormResult", "TaxResult", "FilingStatus",
]
