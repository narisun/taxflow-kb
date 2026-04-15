# Phase 1: Tax Domain Foundation — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Pydantic domain models, tax year constants, calculation engine, validation engine, document assembler, API integration

---

## 1. Overview

Add a tax calculation engine to the taxflow-kb backend that computes a full Form 1040 federal tax return from uploaded/approved documents and manual CPA overrides. Every calculation produces an auditable `LineTrace` linking back to the IRS form, line, and citation.

### Design Principles

- **OOP Python with dependency injection** — calculators receive `TaxYearConstants` via constructor; services compose calculators
- **Testability** — each calculator is independently unit-testable with no DB or network dependencies
- **Audit trail** — every computed value has a `LineTrace` (form, line, label, value, formula, inputs, IRS citation)
- **Year-agnostic architecture** — constants are a registry keyed by tax year; adding TY2026 is a new data file
- **Manual + automatic assembly** — documents seed data, CPA edits take precedence

### Reference Codebase

Business logic and tax rules are sourced from `ustaxes-master/` (unchanged, kept as reference). All implementation follows our OOP/DI patterns, not the monolithic style of the reference.

---

## 2. Directory Structure

```
api/
├── tax_engine/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── people.py          # Person, Dependent, Address
│   │   ├── income.py          # W2, 1099 variants, ScheduleC, ScheduleK1
│   │   ├── deductions.py      # ItemizedDeductions, HSA, IRA, StudentLoan, Mortgage, RentalProperty
│   │   ├── credits.py         # DependentCare, Tuition1098T, EnergyImprovement, Form1095A
│   │   └── tax_return.py      # TaxReturn, LineTrace, FormResult, TaxResult
│   ├── constants/
│   │   ├── __init__.py
│   │   ├── registry.py        # TaxYearConstants dataclass + registry functions
│   │   ├── ty2024.py          # TY2024 IRS values (auto-registers on import)
│   │   └── ty2025.py          # TY2025 IRS values (auto-registers on import)
│   ├── calculators/
│   │   ├── __init__.py
│   │   ├── base.py            # BaseCalculator ABC with LineTrace support
│   │   ├── schedule_b.py      # Interest & dividends
│   │   ├── schedule_c.py      # Self-employment income
│   │   ├── schedule_d.py      # Capital gains/losses
│   │   ├── schedule_e.py      # Rental & K-1 income
│   │   ├── schedule_a.py      # Itemized deductions
│   │   ├── schedule_se.py     # Self-employment tax
│   │   ├── form_8812.py       # Child tax credit
│   │   ├── form_8959.py       # Additional Medicare tax
│   │   ├── form_8960.py       # Net investment income tax
│   │   ├── form_8995.py       # QBI deduction
│   │   └── form_1040.py       # Form 1040 final assembly
│   ├── services/
│   │   ├── __init__.py
│   │   ├── income.py          # IncomeService orchestrator
│   │   ├── deductions.py      # DeductionService orchestrator
│   │   ├── credits.py         # CreditService orchestrator
│   │   ├── liability.py       # LiabilityService orchestrator
│   │   └── engine.py          # TaxCalculationEngine (top-level entry point)
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── base.py            # ValidationRule ABC, ValidationResult
│   │   ├── rules.py           # V001–V011 concrete rules
│   │   └── engine.py          # ValidationEngine
│   └── assembler.py           # DocumentAssembler (documents + overrides → TaxReturn)
```

---

## 3. Domain Models (`api/tax_engine/models/`)

All models are Pydantic v2 `BaseModel` subclasses. All monetary fields use `Decimal`. Fields default to `Decimal("0")` where appropriate.

### 3.1 `people.py`

```python
class Person(BaseModel):
    first_name: str
    last_name: str
    ssn: str                    # Validated: exactly 9 digits, no all-zero groups
    date_of_birth: date
    is_blind: bool = False

class Dependent(BaseModel):
    first_name: str
    last_name: str
    ssn: str
    relationship: str           # "son", "daughter", "stepchild", "foster", "sibling", "parent", "other"
    date_of_birth: date
    months_lived_with: int = 12 # 0–12
    is_student: bool = False
    is_qualifying_child: bool = True
    is_us_citizen: bool = True

class Address(BaseModel):
    street: str
    city: str
    state: str                  # 2-letter state code
    zip_code: str               # 5 or 9 digit
    apt: str | None = None
```

### 3.2 `income.py`

```python
PersonRole = Literal["primary", "spouse"]

class W2(BaseModel):
    employer_name: str
    employer_ein: str                           # Validated: XX-XXXXXXX format
    box1_wages: Decimal = Decimal("0")
    box2_fed_withheld: Decimal = Decimal("0")
    box3_ss_wages: Decimal = Decimal("0")
    box4_ss_withheld: Decimal = Decimal("0")
    box5_medicare_wages: Decimal = Decimal("0")
    box6_medicare_withheld: Decimal = Decimal("0")
    box12_codes: dict[str, Decimal] = {}        # e.g. {"D": 19500, "W": 3600}
    box13_retirement_plan: bool = False
    box15_state: str | None = None
    box16_state_wages: Decimal = Decimal("0")
    box17_state_withheld: Decimal = Decimal("0")
    person_role: PersonRole = "primary"

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

class ScheduleC(BaseModel):
    business_name: str
    principal_business_code: str = ""
    ein: str | None = None
    accounting_method: Literal["cash", "accrual"] = "cash"
    gross_receipts: Decimal = Decimal("0")
    cost_of_goods_sold: Decimal = Decimal("0")
    # Expenses
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
    # QBI fields
    w2_wages_paid: Decimal = Decimal("0")
    ubia_qualified_property: Decimal = Decimal("0")
    is_sstb: bool = False
    person_role: PersonRole = "primary"

    @computed_field
    @property
    def total_expenses(self) -> Decimal:
        """Sum of all expense fields."""
        # Sum all Decimal expense fields

    @computed_field
    @property
    def net_profit(self) -> Decimal:
        return self.gross_receipts - self.cost_of_goods_sold - self.total_expenses

class ScheduleK1(BaseModel):
    entity_name: str
    entity_ein: str
    entity_type: Literal["P", "S"]              # Partnership or S-Corp
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
```

### 3.3 `deductions.py`

```python
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

class RentalProperty(BaseModel):
    address: str
    property_type: str = "single_family"
    fair_rental_days: int = 365
    personal_use_days: int = 0
    rent_received: Decimal = Decimal("0")
    # Expenses
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

    @computed_field
    @property
    def total_expenses(self) -> Decimal:
        """Sum of all expense fields."""

    @computed_field
    @property
    def net_income(self) -> Decimal:
        return self.rent_received - self.total_expenses
```

### 3.4 `credits.py`

```python
class DependentCareExpense(BaseModel):
    provider_name: str
    provider_tin: str | None = None
    provider_address: str | None = None
    amount_paid: Decimal = Decimal("0")
    dependent_name: str
    dependent_ssn: str

class Tuition1098T(BaseModel):
    institution: str
    box1_payments_received: Decimal = Decimal("0")
    box5_scholarships: Decimal = Decimal("0")
    student_name: str
    student_ssn: str
    is_half_time: bool = True
    is_graduate: bool = False
    person_role: PersonRole = "primary"

class EnergyImprovement(BaseModel):
    description: str
    amount: Decimal = Decimal("0")
    is_heat_pump_or_biomass: bool = False

class ResidentialCleanEnergy(BaseModel):
    description: str
    amount: Decimal = Decimal("0")

class Form1095A(BaseModel):
    marketplace_name: str = ""
    annual_enrollment_premium: Decimal = Decimal("0")
    annual_slcsp: Decimal = Decimal("0")
    annual_aptc: Decimal = Decimal("0")
    coverage_months: int = 12
    person_role: PersonRole = "primary"

class EstimatedPayment(BaseModel):
    label: str                                  # "Q1", "Q2", "Q3", "Q4"
    amount: Decimal = Decimal("0")
```

### 3.5 `tax_return.py`

```python
FilingStatus = Literal["S", "MFJ", "MFS", "HOH", "QSS"]

class LineTrace(BaseModel, frozen=True):
    """Immutable audit record for a single calculated value."""
    form: str                                   # "1040", "Schedule A", "Form 8812"
    line: str                                   # "1a", "7", "15"
    label: str                                  # Human-readable description
    value: Decimal
    formula: str                                # e.g. "box1_wages_total - standard_deduction"
    inputs: dict[str, str] = {}                 # Named inputs with their values as strings
    constants_used: dict[str, str] = {}         # Tax year constants referenced
    irs_citation: str | None = None             # e.g. "IRC §199A(b)(2)"

class FormResult(BaseModel):
    form_name: str                              # "Schedule A", "Form 8959"
    lines: dict[str, LineTrace] = {}            # line_number → trace
    total: Decimal = Decimal("0")               # Primary result of this form

class TaxResult(BaseModel):
    tax_year: int
    filing_status: FilingStatus
    form_results: dict[str, FormResult] = {}    # form_name → FormResult
    # Summary fields (derived from form_results for convenience)
    total_income: Decimal = Decimal("0")
    agi: Decimal = Decimal("0")
    taxable_income: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    total_payments: Decimal = Decimal("0")
    refund_or_owed: Decimal = Decimal("0")      # Positive = refund, negative = owed
    all_traces: list[LineTrace] = []
    warnings: list[str] = []

class TaxReturn(BaseModel):
    """Master container for all tax return input data."""
    tax_year: int
    filing_status: FilingStatus
    # People
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
```

---

## 4. Tax Year Constants (`api/tax_engine/constants/`)

### 4.1 `registry.py`

```python
@dataclass(frozen=True)
class TaxYearConstants:
    tax_year: int

    # Standard deductions by filing status
    standard_deduction: dict[str, Decimal]

    # Ordinary income brackets: list of (upper_bound, rate) per status
    # Final entry uses Decimal("Infinity") for the top bracket
    ordinary_brackets: dict[str, list[tuple[Decimal, Decimal]]]

    # Long-term capital gains brackets
    ltcg_brackets: dict[str, list[tuple[Decimal, Decimal]]]

    # Child Tax Credit
    ctc_amount_per_child: Decimal
    ctc_other_dependent: Decimal
    ctc_phase_out: dict[str, Decimal]
    ctc_refundable_max_per_child: Decimal
    ctc_earned_income_threshold: Decimal

    # Self-employment
    ss_wage_base: Decimal
    ss_tax_rate: Decimal                       # Employee portion (6.2%)
    ss_combined_rate: Decimal                   # Combined (12.4%)
    medicare_tax_rate: Decimal                  # Employee portion (1.45%)
    medicare_combined_rate: Decimal             # Combined (2.9%)
    additional_medicare_rate: Decimal           # 0.9%
    additional_medicare_threshold: dict[str, Decimal]

    # Net Investment Income Tax
    niit_rate: Decimal                          # 3.8%
    niit_threshold: dict[str, Decimal]

    # Deductions
    salt_cap: dict[str, Decimal]
    medical_agi_floor_pct: Decimal              # 7.5%

    # QBI (Section 199A)
    qbi_deduction_rate: Decimal                 # 20%
    qbi_threshold: dict[str, Decimal]
    qbi_phase_in_range: dict[str, Decimal]

    # HSA
    hsa_limit: dict[str, Decimal]
    hsa_catchup: Decimal

    # IRA
    ira_contribution_limit: Decimal
    ira_catchup: Decimal

    # AMT
    amt_exemption: dict[str, Decimal]
    amt_phase_out: dict[str, Decimal]
    amt_rates: list[tuple[Decimal, Decimal]]

    # Student loan interest
    student_loan_max_deduction: Decimal
    student_loan_phase_out: dict[str, tuple[Decimal, Decimal]]  # (start, end)

    # EITC
    eitc_max_credit: dict[int, Decimal]         # By number of qualifying children (0-3)
    eitc_phase_out_start: dict[str, dict[int, Decimal]]
    eitc_phase_out_end: dict[str, dict[int, Decimal]]

    # Capital loss
    capital_loss_limit: Decimal                 # $3,000 ($1,500 MFS)


_REGISTRY: dict[int, TaxYearConstants] = {}

def register(constants: TaxYearConstants) -> None:
    _REGISTRY[constants.tax_year] = constants

def get_constants(year: int) -> TaxYearConstants:
    if year not in _REGISTRY:
        raise ValueError(f"No tax constants registered for year {year}")
    return _REGISTRY[year]

def available_years() -> list[int]:
    return sorted(_REGISTRY.keys())
```

### 4.2 `ty2024.py` / `ty2025.py`

Each module creates a `TaxYearConstants` instance with that year's IRS-published values and calls `register()` at module level. Values are sourced from `ustaxes-master/engine/constants/ty2024.py` and `ty2025.py`.

---

## 5. Calculators (`api/tax_engine/calculators/`)

### 5.1 `base.py`

```python
class BaseCalculator(ABC):
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants
        self._traces: list[LineTrace] = []

    def trace(
        self, form: str, line: str, label: str, value: Decimal,
        formula: str, inputs: dict[str, str] | None = None,
        constants_used: dict[str, str] | None = None,
        irs_citation: str | None = None,
    ) -> Decimal:
        """Record a LineTrace and return the value for chaining."""
        lt = LineTrace(
            form=form, line=line, label=label, value=value,
            formula=formula, inputs=inputs or {}, constants_used=constants_used or {},
            irs_citation=irs_citation,
        )
        self._traces.append(lt)
        return value

    def build_result(self, form_name: str, total: Decimal) -> FormResult:
        """Package traces into a FormResult."""
        lines = {t.line: t for t in self._traces}
        return FormResult(form_name=form_name, lines=lines, total=total)

    @abstractmethod
    def compute(self, tax_return: TaxReturn, prior_results: dict[str, FormResult]) -> FormResult:
        """Compute this form. May read prior_results from other calculators."""
```

### 5.2 Calculator Implementations

Each calculator follows the same pattern: constructor receives `TaxYearConstants`, `compute()` receives `TaxReturn` + `prior_results`, returns `FormResult`.

**Execution dependency order** (enforced by the services layer):

```
Phase 1 - Income (no deps):
  ScheduleBCalculator    → total interest, total dividends
  ScheduleCCalculator    → net profit per business
  ScheduleDCalculator    → net capital gains
  ScheduleECalculator    → rental + K-1 income

Phase 2 - SE Tax + AGI Adjustments (depends on Phase 1):
  ScheduleSECalculator   → SE tax, deductible half (needs Schedule C)
  (AGI adjustments: HSA, IRA, student loan, educator, SE deduction)

Phase 3 - Deductions (depends on AGI):
  ScheduleACalculator    → itemized deductions (SALT cap, medical floor)
  Form8995Calculator     → QBI deduction (needs taxable income estimate)

Phase 4 - Tax Liability (depends on taxable income):
  OrdinaryTaxCalculator  → tax via brackets
  ScheduleDTaxWorksheet  → preferential rates (0/15/20%)
  Form8959Calculator     → additional Medicare (needs total wages)
  Form8960Calculator     → NIIT (needs investment income + AGI)

Phase 5 - Credits (depends on tax liability):
  Form8812Calculator     → CTC/ACTC (needs tax, dependents)
  (EITC, education, dependent care, energy — each independent)

Phase 6 - Assembly:
  Form1040Calculator     → lines 1–37, final refund/owed
```

**Key calculation logic per calculator** (reference: `ustaxes-master/engine/calculator.py`):

- **ScheduleBCalculator**: Sum 1099-INT box 1 → total interest. Sum 1099-DIV box 1a → total ordinary dividends. Separate qualified dividends for preferential rate treatment.
- **ScheduleCCalculator**: Per business: gross_receipts − COGS − total_expenses = net_profit. Aggregate across businesses.
- **ScheduleDCalculator**: Net ST gain = Σ(proceeds − basis + wash_sale_disallowed) for short-term. Net LT gain likewise. Apply $3,000 capital loss limit. Determine if Schedule D tax worksheet is needed (net LTCG > 0 or qualified dividends > 0).
- **ScheduleECalculator**: Per rental: rent_received − total_expenses = net_income. Aggregate K-1 ordinary income, rental income, interest, dividends, capital gains.
- **ScheduleACalculator**: Medical (amount exceeding 7.5% AGI floor). SALT (income/sales + real estate + personal property, capped per filing status). Mortgage interest. Charity. Compare total to standard deduction.
- **ScheduleSECalculator**: SE income × 92.35% = taxable SE income. SS portion: min(taxable, SS wage base − W-2 SS wages) × 12.4%. Medicare: taxable × 2.9%. Total SE tax. Deductible half = SE tax × 50%.
- **Form8959Calculator**: Total Medicare wages (W-2 box 5 + SE income). Excess over threshold × 0.9%. Credit for W-2 Medicare withheld above standard 1.45%.
- **Form8960Calculator**: Net investment income (interest + dividends + capital gains + rental). MAGI − threshold = excess. Tax = min(NII, excess) × 3.8%.
- **Form8995Calculator**: Two paths based on taxable income vs threshold.
  - **Simple** (below threshold): 20% of total QBI, capped at 20% of taxable income.
  - **Complex** (above threshold): Per-business: lesser of 20% QBI or wage/UBIA limit (50% W-2 wages or 25% W-2 + 2.5% UBIA). SSTB phase-out applies in phase-in range. Sum across businesses, cap at 20% taxable income.
- **Form8812Calculator**: Qualifying children (age < 17, valid SSN) × CTC amount. Other dependents × $500. Phase-out: 5% per $1,000 over threshold. Nonrefundable portion capped at tax liability. ACTC (refundable): 15% of earned income over $2,500, capped at refundable max per child.
- **Form1040Calculator**: Assembles all prior results into lines 1–37. Total income (L9). AGI (L11 = L9 − adjustments). Deduction (L12 = max of standard, itemized). QBI (L13a). Taxable income (L15 = L11 − L12 − L13a). Tax (L16). Credits (L21). Other taxes (L23 = SE + additional Medicare + NIIT). Total tax (L24). Payments (L33 = withholding + estimated + refundable credits). Refund or owed (L35a or L37).

---

## 6. Domain Services (`api/tax_engine/services/`)

### 6.1 `engine.py` — TaxCalculationEngine

```python
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

        # Phase 2: AGI adjustments (SE deduction, HSA, IRA, student loan)
        results.update(self.deduction_service.compute_adjustments(tax_return, results))

        # Phase 3: Deductions (standard vs itemized, QBI)
        results.update(self.deduction_service.compute_deductions(tax_return, results))

        # Phase 4: Tax liability (brackets, preferential rates, surtaxes)
        results.update(self.liability_service.compute(tax_return, results))

        # Phase 5: Credits (CTC, EITC, education, energy)
        results.update(self.credit_service.compute(tax_return, results))

        # Phase 6: Final 1040 assembly
        form1040 = Form1040Calculator(self.constants)
        results["1040"] = form1040.compute(tax_return, results)

        return self._build_result(tax_return, results)

    def _build_result(self, tax_return: TaxReturn, results: dict[str, FormResult]) -> TaxResult:
        f1040 = results.get("1040")
        all_traces = []
        for fr in results.values():
            all_traces.extend(fr.lines.values())
        return TaxResult(
            tax_year=tax_return.tax_year,
            filing_status=tax_return.filing_status,
            form_results=results,
            total_income=f1040.lines.get("9", LineTrace(...)).value,
            agi=f1040.lines.get("11", LineTrace(...)).value,
            # ... remaining summary fields from 1040 lines
            all_traces=all_traces,
        )
```

### 6.2 Service Internals

Each service instantiates its calculators in `__init__` and calls them in dependency order in `compute()`. Services return `dict[str, FormResult]` which the engine merges into the master results dict.

**IncomeService.compute()**: Runs ScheduleB, ScheduleC, ScheduleD, ScheduleE. Returns their FormResults.

**DeductionService.compute_adjustments()**: Computes HSA deduction, IRA deduction, student loan deduction (with phase-out), SE deduction (from prior ScheduleSE result), educator expenses. Returns adjustments FormResult.

**DeductionService.compute_deductions()**: Runs ScheduleA, compares to standard deduction. Runs Form8995 for QBI. Returns deduction FormResults.

**LiabilityService.compute()**: Computes ordinary tax via brackets. If qualified dividends or net LTCG exist, runs preferential rate worksheet. Runs ScheduleSE, Form8959, Form8960. Returns all liability FormResults.

**CreditService.compute()**: Runs Form8812, EITC, education credits, dependent care, energy. Each is independent. Returns all credit FormResults.

### 6.3 FastAPI Integration

```python
# api/tax_engine/dependencies.py
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.services.engine import TaxCalculationEngine

def get_tax_engine(tax_year: int = Query(default=2024)) -> TaxCalculationEngine:
    constants = get_constants(tax_year)
    return TaxCalculationEngine(constants)
```

Used in routers via `Depends(get_tax_engine)`.

---

## 7. Validation Engine (`api/tax_engine/validation/`)

### 7.1 `base.py`

```python
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
        """Return empty list if valid, or list of issues found."""
```

### 7.2 Concrete Rules (`rules.py`)

| ID | Class | Severity | Check |
|----|-------|----------|-------|
| V001 | `SCorporateW2Rule` | WARNING | S-Corp K-1 without matching W-2 employer EIN |
| V002 | `SSNFormatRule` | ERROR | SSN is 9 digits with no all-zero groups |
| V003 | `MFJSpouseRequiredRule` | ERROR | MFJ filing status requires spouse data |
| V004 | `HSAContributionMatchRule` | WARNING | HSA employer amount matches W-2 box 12 code W |
| V005 | `CapitalGainDistributionRule` | WARNING | 1099-DIV capital gain distributions without 1099-B |
| V006 | `WithholdingExceedsIncomeRule` | WARNING | Total withholding > total income |
| V007 | `DuplicateSSNRule` | ERROR | Same SSN on multiple dependents |
| V008 | `HOHRequiresDependentRule` | ERROR | HOH filing status without qualifying dependent |
| V009 | `ExcessBusinessLossRule` | INFO | Schedule C net loss > $250K |
| V010 | `QBIWithoutBusinessRule` | WARNING | QBI deduction claimed but no Schedule C or K-1 QBI |
| V011 | `OverpaymentLikelyRule` | INFO | Estimated payments > prior year tax |

### 7.3 `engine.py`

```python
def default_rules() -> list[ValidationRule]:
    """Returns all built-in validation rules."""

class ValidationEngine:
    def __init__(self, rules: list[ValidationRule] | None = None):
        self.rules = rules or default_rules()

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        """Run all rules, return results sorted by severity (ERROR first)."""

    def validate_errors_only(self, tax_return: TaxReturn) -> list[ValidationResult]:
        """Return only ERROR-severity results."""

    def has_errors(self, tax_return: TaxReturn) -> bool:
        """Quick check: any ERROR-severity issues?"""
```

---

## 8. Document Assembler (`api/tax_engine/assembler.py`)

```python
class DocumentAssembler:
    """Builds a TaxReturn from approved documents + manual CPA overrides."""

    # Mapping from form_type string to Pydantic model class
    FORM_TYPE_MAP: dict[str, type] = {
        "W-2": W2,
        "1099-INT": Income1099Int,
        "1099-DIV": Income1099Div,
        "1099-B": Income1099B,
        "1099-NEC": Income1099NEC,
        "1099-R": Income1099R,
        "SSA-1099": IncomeSSA1099,
        "1098": Mortgage1098,
        "K-1": ScheduleK1,
    }

    async def assemble(self, client_id: int, session: AsyncSession) -> TaxReturn:
        """
        1. Load ClientModel (filing_status, tax_year, dependents)
        2. Query DocumentModel WHERE client_id AND status='approved'
        3. For each document: parse extracted_data JSON into typed model
        4. Query ManualEntryModel WHERE client_id
        5. Apply manual overrides (field-level merge, manual wins)
        6. Return assembled TaxReturn
        """
```

### New DB Model

```python
# Added to api/db/models.py
class ManualEntryModel(TenantMixin, Base):
    __tablename__ = "manual_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    form_type: Mapped[str]          # "W-2", "Schedule C", etc.
    form_index: Mapped[int] = mapped_column(default=0)  # Which instance (0 = first W-2)
    field_name: Mapped[str]         # "box1_wages"
    value: Mapped[str]              # Stored as string, parsed by assembler
    entered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

### New API Endpoints

Added to `api/routers/tax_returns.py`:

- `POST /api/clients/{client_id}/returns/entries` — Create/update manual entry
- `GET /api/clients/{client_id}/returns/entries` — List all manual entries for client
- `DELETE /api/clients/{client_id}/returns/entries/{entry_id}` — Remove a manual override
- `POST /api/clients/{client_id}/returns/compute` — Assemble + validate + compute full return
- `GET /api/clients/{client_id}/returns/validate` — Validate without computing

---

## 9. Testing Strategy

All calculators are pure functions of `(TaxReturn, prior_results, TaxYearConstants)` — no DB, no network.

### Unit Tests (per calculator)

```
tests/api/tax_engine/
├── test_models.py              # Pydantic validation (SSN, EIN, computed fields)
├── test_constants.py           # Registry, correct values for TY2024/2025
├── calculators/
│   ├── test_schedule_b.py      # Interest/dividend aggregation
│   ├── test_schedule_c.py      # Business income, expense totals, net profit
│   ├── test_schedule_d.py      # Capital gains, loss limits, wash sales
│   ├── test_schedule_e.py      # Rental income, K-1 passthrough
│   ├── test_schedule_a.py      # SALT cap, medical floor, charity limits
│   ├── test_schedule_se.py     # SE tax, SS wage cap, deductible half
│   ├── test_form_8812.py       # CTC phase-out, ACTC refundable
│   ├── test_form_8959.py       # Additional Medicare thresholds
│   ├── test_form_8960.py       # NIIT calculation
│   ├── test_form_8995.py       # QBI simple + complex paths, SSTB
│   └── test_form_1040.py       # Full assembly, summary values
├── test_services.py            # Service orchestration, dependency order
├── test_engine.py              # End-to-end: TaxReturn → TaxResult
├── test_validation.py          # Each rule + engine
└── test_assembler.py           # Document → TaxReturn assembly
```

### Test Patterns

- Each test creates a `TaxReturn` with specific inputs, runs the calculator, asserts `LineTrace` values
- Constants injected via `TY2024` instance (deterministic)
- No mocking of other calculators — use real `prior_results` dicts
- Edge cases: zero income, maximum values, phase-out boundaries, MFJ vs Single differences

### Integration Tests

- Existing `tests/api/test_tax_returns.py` updated to use real engine instead of mock `_compute_draft`
- Full round-trip: create client → upload documents → approve → compute → verify result

---

## 10. Scope Summary

| Component | Count | Description |
|-----------|-------|-------------|
| Pydantic models | ~25 | People, income, deductions, credits, TaxReturn, TaxResult, LineTrace |
| Tax year constants | 2 modules | TY2024, TY2025 + registry |
| Calculators | 12 classes | One per IRS form/schedule |
| Domain services | 5 classes | 4 orchestrators + 1 engine |
| Validation rules | 11 classes | Pluggable cross-form checks |
| Assembler | 1 class | Documents + overrides → TaxReturn |
| DB model | 1 new table | ManualEntryModel |
| API endpoints | 5 new | Manual entries CRUD + compute + validate |
| Test files | ~16 | Unit + integration |

### Out of Scope (Phase 2+)

- Real OCR extraction (stays as MockOCRExtractor)
- PDF form generation
- MeF XML output
- State tax calculations
- AMT (Form 6251) — stubbed to return zero
- Advisory/strategy engine
- Year-over-year comparison
