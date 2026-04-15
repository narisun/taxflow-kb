"""Deduction-related models: itemized, HSA, IRA, student loan, rental property."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, computed_field

from api.tax_engine.models.income import PersonRole


class ItemizedDeductions(BaseModel):
    medical_dental: Decimal = Decimal("0")
    salt_income_or_sales: Decimal = Decimal("0")
    is_sales_tax: bool = False
    salt_real_estate: Decimal = Decimal("0")
    salt_personal_property: Decimal = Decimal("0")
    mortgage_interest_1098: Decimal = Decimal("0")
    mortgage_interest_other: Decimal = Decimal("0")
    investment_interest: Decimal = Decimal("0")
    charity_cash: Decimal = Decimal("0")
    charity_noncash: Decimal = Decimal("0")
    casualty_loss: Decimal = Decimal("0")
    other_deductions: Decimal = Decimal("0")


class Mortgage1098(BaseModel):
    lender: str
    property_address: str | None = None
    box1_interest: Decimal = Decimal("0")
    box2_principal: Decimal = Decimal("0")
    box10_property_taxes: Decimal = Decimal("0")


class HSA(BaseModel):
    coverage_type: Literal["self-only", "family"]
    employee_contributions: Decimal = Decimal("0")
    employer_contributions: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


class IRAContribution(BaseModel):
    amount: Decimal = Decimal("0")
    is_deductible: bool = True
    is_roth: bool = False
    person_role: PersonRole = "primary"
    age_50_plus: bool = False


class StudentLoanInterest(BaseModel):
    lender: str
    box1_interest_paid: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


_RENTAL_EXPENSE_FIELDS = [
    "advertising", "auto_travel", "cleaning", "commissions", "insurance",
    "legal", "management", "mortgage_interest", "other_interest", "repairs",
    "supplies", "taxes", "utilities", "depreciation", "other_expenses",
]


class RentalProperty(BaseModel):
    address: str
    property_type: str = "single_family"
    fair_rental_days: int = 365
    personal_use_days: int = 0
    rent_received: Decimal = Decimal("0")
    advertising: Decimal = Decimal("0")
    auto_travel: Decimal = Decimal("0")
    cleaning: Decimal = Decimal("0")
    commissions: Decimal = Decimal("0")
    insurance: Decimal = Decimal("0")
    legal: Decimal = Decimal("0")
    management: Decimal = Decimal("0")
    mortgage_interest: Decimal = Decimal("0")
    other_interest: Decimal = Decimal("0")
    repairs: Decimal = Decimal("0")
    supplies: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    utilities: Decimal = Decimal("0")
    depreciation: Decimal = Decimal("0")
    other_expenses: Decimal = Decimal("0")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_expenses(self) -> Decimal:
        return sum(getattr(self, f) for f in _RENTAL_EXPENSE_FIELDS)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_income(self) -> Decimal:
        return self.rent_received - self.total_expenses
