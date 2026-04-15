"""Master TaxReturn container, LineTrace audit record, FormResult, TaxResult."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import (
    W2, Income1099Int, Income1099Div, Income1099B, Income1099NEC,
    Income1099R, IncomeSSA1099, ScheduleC, ScheduleK1,
)
from api.tax_engine.models.deductions import (
    ItemizedDeductions, Mortgage1098, HSA, IRAContribution,
    StudentLoanInterest, RentalProperty,
)
from api.tax_engine.models.credits import (
    DependentCareExpense, Tuition1098T, EnergyImprovement,
    ResidentialCleanEnergy, Form1095A, EstimatedPayment,
)

FilingStatus = Literal["S", "MFJ", "MFS", "HOH", "QSS"]


class LineTrace(BaseModel, frozen=True):
    """Immutable audit record for a single calculated value."""
    form: str
    line: str
    label: str
    value: Decimal
    formula: str
    inputs: dict[str, str] = {}
    constants_used: dict[str, str] = {}
    irs_citation: str | None = None


class FormResult(BaseModel):
    form_name: str
    lines: dict[str, LineTrace] = {}
    total: Decimal = Decimal("0")


class TaxResult(BaseModel):
    tax_year: int
    filing_status: FilingStatus
    form_results: dict[str, FormResult] = {}
    total_income: Decimal = Decimal("0")
    agi: Decimal = Decimal("0")
    taxable_income: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    total_payments: Decimal = Decimal("0")
    refund_or_owed: Decimal = Decimal("0")
    all_traces: list[LineTrace] = []
    warnings: list[str] = []


class TaxReturn(BaseModel):
    """Master container for all tax return input data."""
    tax_year: int
    filing_status: FilingStatus
    primary: Person
    spouse: Person | None = None
    dependents: list[Dependent] = []
    address: Address
    # Income
    w2s: list[W2] = []
    interest_1099s: list[Income1099Int] = []
    dividend_1099s: list[Income1099Div] = []
    broker_1099s: list[Income1099B] = []
    nec_1099s: list[Income1099NEC] = []
    retirement_1099rs: list[Income1099R] = []
    ssa_1099s: list[IncomeSSA1099] = []
    schedule_cs: list[ScheduleC] = []
    k1s: list[ScheduleK1] = []
    rental_properties: list[RentalProperty] = []
    # Deductions
    itemized: ItemizedDeductions | None = None
    mortgages: list[Mortgage1098] = []
    hsas: list[HSA] = []
    ira_contributions: list[IRAContribution] = []
    student_loans: list[StudentLoanInterest] = []
    educator_expenses: Decimal = Decimal("0")
    # Credits
    dependent_care: list[DependentCareExpense] = []
    tuition_1098ts: list[Tuition1098T] = []
    energy_improvements: list[EnergyImprovement] = []
    clean_energy: list[ResidentialCleanEnergy] = []
    form_1095a: Form1095A | None = None
    # Payments
    estimated_payments: list[EstimatedPayment] = []
    # Carryforwards
    capital_loss_carryforward_st: Decimal = Decimal("0")
    capital_loss_carryforward_lt: Decimal = Decimal("0")
    nol_carryforward: Decimal = Decimal("0")
    prior_year_amt_credit: Decimal = Decimal("0")
    charity_carryover: Decimal = Decimal("0")
    qbi_loss_carryforward: Decimal = Decimal("0")
    # Prior year
    prior_year_agi: Decimal = Decimal("0")
    prior_year_tax: Decimal = Decimal("0")
