"""Income source models: W-2, 1099 variants, Schedule C, Schedule K-1."""
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, computed_field, field_validator

PersonRole = Literal["primary", "spouse"]


def _validate_ein(ein: str) -> str:
    """Validate EIN: XX-XXXXXXX format."""
    if not re.fullmatch(r"\d{2}-\d{7}", ein):
        raise ValueError("EIN must be in XX-XXXXXXX format")
    return ein


class W2(BaseModel):
    employer_name: str
    employer_ein: str
    box1_wages: Decimal = Decimal("0")
    box2_fed_withheld: Decimal = Decimal("0")
    box3_ss_wages: Decimal = Decimal("0")
    box4_ss_withheld: Decimal = Decimal("0")
    box5_medicare_wages: Decimal = Decimal("0")
    box6_medicare_withheld: Decimal = Decimal("0")
    box12_codes: dict[str, Decimal] = {}
    box13_retirement_plan: bool = False
    box15_state: str | None = None
    box16_state_wages: Decimal = Decimal("0")
    box17_state_withheld: Decimal = Decimal("0")
    person_role: PersonRole = "primary"

    @field_validator("employer_ein")
    @classmethod
    def validate_ein(cls, v: str) -> str:
        return _validate_ein(v)


class Income1099Int(BaseModel):
    payer: str
    box1_interest: Decimal = Decimal("0")
    box2_early_withdrawal_penalty: Decimal = Decimal("0")
    box4_fed_withheld: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


class Income1099Div(BaseModel):
    payer: str
    box1a_ordinary_dividends: Decimal = Decimal("0")
    box1b_qualified_dividends: Decimal = Decimal("0")
    box2a_capital_gain_distributions: Decimal = Decimal("0")
    box5_section_199a_dividends: Decimal = Decimal("0")
    box7_foreign_tax_paid: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


class Income1099B(BaseModel):
    payer: str
    short_term_proceeds: Decimal = Decimal("0")
    short_term_cost_basis: Decimal = Decimal("0")
    short_term_wash_sales: Decimal = Decimal("0")
    long_term_proceeds: Decimal = Decimal("0")
    long_term_cost_basis: Decimal = Decimal("0")
    long_term_wash_sales: Decimal = Decimal("0")
    collectibles_gain: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


class Income1099NEC(BaseModel):
    payer: str
    nec_compensation: Decimal = Decimal("0")
    fed_tax_withheld: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


class Income1099R(BaseModel):
    payer: str
    box1_gross_distribution: Decimal = Decimal("0")
    box2a_taxable_amount: Decimal = Decimal("0")
    box2b_taxable_not_determined: bool = False
    box4_fed_withheld: Decimal = Decimal("0")
    box7_distribution_code: str = ""
    is_ira: bool = False
    is_roth: bool = False
    person_role: PersonRole = "primary"


class IncomeSSA1099(BaseModel):
    box5_net_benefits: Decimal = Decimal("0")
    box6_voluntary_withheld: Decimal = Decimal("0")
    person_role: PersonRole = "primary"


_EXPENSE_FIELDS = [
    "advertising", "car_and_truck", "commissions", "insurance",
    "interest_mortgage", "interest_other", "legal_professional",
    "office_expense", "rent_lease", "repairs", "supplies",
    "taxes_licenses", "travel", "meals", "utilities", "other_expenses",
]


class ScheduleC(BaseModel):
    business_name: str
    principal_business_code: str = ""
    ein: str | None = None
    accounting_method: Literal["cash", "accrual"] = "cash"
    gross_receipts: Decimal = Decimal("0")
    cost_of_goods_sold: Decimal = Decimal("0")
    advertising: Decimal = Decimal("0")
    car_and_truck: Decimal = Decimal("0")
    commissions: Decimal = Decimal("0")
    insurance: Decimal = Decimal("0")
    interest_mortgage: Decimal = Decimal("0")
    interest_other: Decimal = Decimal("0")
    legal_professional: Decimal = Decimal("0")
    office_expense: Decimal = Decimal("0")
    rent_lease: Decimal = Decimal("0")
    repairs: Decimal = Decimal("0")
    supplies: Decimal = Decimal("0")
    taxes_licenses: Decimal = Decimal("0")
    travel: Decimal = Decimal("0")
    meals: Decimal = Decimal("0")
    utilities: Decimal = Decimal("0")
    other_expenses: Decimal = Decimal("0")
    w2_wages_paid: Decimal = Decimal("0")
    ubia_qualified_property: Decimal = Decimal("0")
    is_sstb: bool = False
    person_role: PersonRole = "primary"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_expenses(self) -> Decimal:
        return sum(getattr(self, f) for f in _EXPENSE_FIELDS)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_profit(self) -> Decimal:
        return self.gross_receipts - self.cost_of_goods_sold - self.total_expenses


class ScheduleK1(BaseModel):
    entity_name: str
    entity_ein: str
    entity_type: Literal["P", "S"]
    is_passive: bool = False
    box1_ordinary_income: Decimal = Decimal("0")
    box2_rental_income: Decimal = Decimal("0")
    box4a_guaranteed_payments: Decimal = Decimal("0")
    box5_interest: Decimal = Decimal("0")
    box6a_dividends: Decimal = Decimal("0")
    box7_royalties: Decimal = Decimal("0")
    box9a_lt_capital_gain: Decimal = Decimal("0")
    box10_net_1231_gain: Decimal = Decimal("0")
    box14a_se_earnings: Decimal = Decimal("0")
    box19a_distributions: Decimal = Decimal("0")
    box20z_section_199a_qbi: Decimal = Decimal("0")
    w2_wages_for_qbi: Decimal = Decimal("0")
    ubia_qualified_property: Decimal = Decimal("0")
    is_sstb: bool = False
    person_role: PersonRole = "primary"

    @field_validator("entity_ein")
    @classmethod
    def validate_ein(cls, v: str) -> str:
        return _validate_ein(v)
