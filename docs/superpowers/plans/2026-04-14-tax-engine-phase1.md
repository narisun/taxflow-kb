# Phase 1: Tax Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full Form 1040 federal tax calculation engine with auditable LineTrace, pluggable validation, and document assembly into the taxflow-kb backend.

**Architecture:** OOP Python with dependency injection. Each IRS form/schedule is its own calculator class receiving `TaxYearConstants` via constructor. Domain services orchestrate calculators in dependency order. A top-level `TaxCalculationEngine` is the single entry point. Every computed value produces a `LineTrace` audit record.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLAlchemy (async), pytest-asyncio. All monetary values use `Decimal`.

**Spec:** `docs/superpowers/specs/2026-04-14-tax-engine-phase1-design.md`

**Reference codebase:** `ustaxes-master/engine/` — read-only, do not modify.

---

## File Map

### New Files (create)

| File | Responsibility |
|------|---------------|
| `api/tax_engine/__init__.py` | Package init |
| `api/tax_engine/models/__init__.py` | Re-exports all domain models |
| `api/tax_engine/models/people.py` | Person, Dependent, Address |
| `api/tax_engine/models/income.py` | W2, 1099 variants, ScheduleC, ScheduleK1 |
| `api/tax_engine/models/deductions.py` | ItemizedDeductions, HSA, IRA, StudentLoan, Mortgage, RentalProperty |
| `api/tax_engine/models/credits.py` | DependentCare, Tuition1098T, EnergyImprovement, EstimatedPayment |
| `api/tax_engine/models/tax_return.py` | TaxReturn, LineTrace, FormResult, TaxResult, FilingStatus |
| `api/tax_engine/constants/__init__.py` | Package init, imports ty modules to auto-register |
| `api/tax_engine/constants/registry.py` | TaxYearConstants dataclass + registry functions |
| `api/tax_engine/constants/ty2024.py` | TY2024 IRS values |
| `api/tax_engine/constants/ty2025.py` | TY2025 IRS values |
| `api/tax_engine/calculators/__init__.py` | Package init |
| `api/tax_engine/calculators/base.py` | BaseCalculator ABC with LineTrace support |
| `api/tax_engine/calculators/schedule_b.py` | Interest & dividends |
| `api/tax_engine/calculators/schedule_c.py` | Self-employment income |
| `api/tax_engine/calculators/schedule_d.py` | Capital gains/losses |
| `api/tax_engine/calculators/schedule_e.py` | Rental & K-1 income |
| `api/tax_engine/calculators/schedule_a.py` | Itemized deductions |
| `api/tax_engine/calculators/schedule_se.py` | Self-employment tax |
| `api/tax_engine/calculators/form_8812.py` | Child tax credit |
| `api/tax_engine/calculators/form_8959.py` | Additional Medicare tax |
| `api/tax_engine/calculators/form_8960.py` | Net investment income tax |
| `api/tax_engine/calculators/form_8995.py` | QBI deduction |
| `api/tax_engine/calculators/form_1040.py` | Form 1040 final assembly |
| `api/tax_engine/services/__init__.py` | Package init |
| `api/tax_engine/services/income.py` | IncomeService orchestrator |
| `api/tax_engine/services/deductions.py` | DeductionService orchestrator |
| `api/tax_engine/services/credits.py` | CreditService orchestrator |
| `api/tax_engine/services/liability.py` | LiabilityService orchestrator |
| `api/tax_engine/services/engine.py` | TaxCalculationEngine |
| `api/tax_engine/validation/__init__.py` | Package init |
| `api/tax_engine/validation/base.py` | ValidationRule ABC, ValidationResult |
| `api/tax_engine/validation/rules.py` | V001–V011 concrete rules |
| `api/tax_engine/validation/engine.py` | ValidationEngine |
| `api/tax_engine/assembler.py` | DocumentAssembler |
| `api/tax_engine/dependencies.py` | FastAPI Depends providers |
| `tests/api/tax_engine/__init__.py` | Test package |
| `tests/api/tax_engine/conftest.py` | Shared fixtures (sample TaxReturn, constants) |
| `tests/api/tax_engine/test_models.py` | Model validation tests |
| `tests/api/tax_engine/test_constants.py` | Registry + constant value tests |
| `tests/api/tax_engine/calculators/__init__.py` | Test package |
| `tests/api/tax_engine/calculators/test_schedule_b.py` | Schedule B tests |
| `tests/api/tax_engine/calculators/test_schedule_c.py` | Schedule C tests |
| `tests/api/tax_engine/calculators/test_schedule_d.py` | Schedule D tests |
| `tests/api/tax_engine/calculators/test_schedule_e.py` | Schedule E tests |
| `tests/api/tax_engine/calculators/test_schedule_a.py` | Schedule A tests |
| `tests/api/tax_engine/calculators/test_schedule_se.py` | Schedule SE tests |
| `tests/api/tax_engine/calculators/test_form_8812.py` | Form 8812 tests |
| `tests/api/tax_engine/calculators/test_form_8959.py` | Form 8959 tests |
| `tests/api/tax_engine/calculators/test_form_8960.py` | Form 8960 tests |
| `tests/api/tax_engine/calculators/test_form_8995.py` | Form 8995 tests |
| `tests/api/tax_engine/calculators/test_form_1040.py` | Form 1040 tests |
| `tests/api/tax_engine/test_validation.py` | Validation rules + engine tests |
| `tests/api/tax_engine/test_engine.py` | End-to-end TaxReturn → TaxResult |
| `tests/api/tax_engine/test_assembler.py` | DocumentAssembler tests |

### Modified Files

| File | Change |
|------|--------|
| `api/db/models.py` | Add `ManualEntryModel` |
| `api/routers/tax_returns.py` | Replace `_compute_draft` with engine, add compute/validate/entries endpoints |
| `api/main.py` | No changes needed (router already registered) |
| `tests/api/conftest.py` | Import `ManualEntryModel` so its table is created |
| `tests/api/test_tax_returns.py` | Update tests for new engine-backed responses |

---

## Task 1: Domain Models — People

**Files:**
- Create: `api/tax_engine/__init__.py`
- Create: `api/tax_engine/models/__init__.py`
- Create: `api/tax_engine/models/people.py`
- Test: `tests/api/tax_engine/test_models.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p api/tax_engine/models
mkdir -p tests/api/tax_engine/calculators
touch api/tax_engine/__init__.py
touch api/tax_engine/models/__init__.py
touch tests/api/tax_engine/__init__.py
touch tests/api/tax_engine/calculators/__init__.py
```

- [ ] **Step 2: Write failing tests for Person, Dependent, Address**

Create `tests/api/tax_engine/test_models.py`:

```python
"""Tests for tax engine domain models."""
import pytest
from datetime import date
from decimal import Decimal


class TestPerson:
    def test_valid_person(self):
        from api.tax_engine.models.people import Person

        p = Person(
            first_name="John",
            last_name="Doe",
            ssn="123456789",
            date_of_birth=date(1985, 3, 15),
        )
        assert p.first_name == "John"
        assert p.ssn == "123456789"
        assert p.is_blind is False

    def test_ssn_must_be_9_digits(self):
        from api.tax_engine.models.people import Person

        with pytest.raises(ValueError):
            Person(
                first_name="John",
                last_name="Doe",
                ssn="12345",
                date_of_birth=date(1985, 3, 15),
            )

    def test_ssn_rejects_all_zeros_in_area(self):
        from api.tax_engine.models.people import Person

        with pytest.raises(ValueError):
            Person(
                first_name="John",
                last_name="Doe",
                ssn="000456789",
                date_of_birth=date(1985, 3, 15),
            )

    def test_ssn_rejects_all_zeros_in_group(self):
        from api.tax_engine.models.people import Person

        with pytest.raises(ValueError):
            Person(
                first_name="John",
                last_name="Doe",
                ssn="123006789",
                date_of_birth=date(1985, 3, 15),
            )

    def test_ssn_rejects_all_zeros_in_serial(self):
        from api.tax_engine.models.people import Person

        with pytest.raises(ValueError):
            Person(
                first_name="John",
                last_name="Doe",
                ssn="123450000",
                date_of_birth=date(1985, 3, 15),
            )


class TestDependent:
    def test_valid_dependent(self):
        from api.tax_engine.models.people import Dependent

        d = Dependent(
            first_name="Jane",
            last_name="Doe",
            ssn="987654321",
            relationship="daughter",
            date_of_birth=date(2015, 7, 20),
        )
        assert d.months_lived_with == 12
        assert d.is_qualifying_child is True

    def test_months_lived_with_range(self):
        from api.tax_engine.models.people import Dependent

        with pytest.raises(ValueError):
            Dependent(
                first_name="Jane",
                last_name="Doe",
                ssn="987654321",
                relationship="daughter",
                date_of_birth=date(2015, 7, 20),
                months_lived_with=13,
            )


class TestAddress:
    def test_valid_address(self):
        from api.tax_engine.models.people import Address

        a = Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")
        assert a.apt is None

    def test_zip_must_be_5_or_9_digits(self):
        from api.tax_engine.models.people import Address

        with pytest.raises(ValueError):
            Address(street="123 Main St", city="Springfield", state="IL", zip_code="123")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.tax_engine.models.people'`

- [ ] **Step 4: Implement people.py**

Create `api/tax_engine/models/people.py`:

```python
"""Person, Dependent, and Address models for tax filing unit."""
import re
from datetime import date

from pydantic import BaseModel, field_validator


def _validate_ssn(ssn: str) -> str:
    """Validate SSN: 9 digits, no all-zero groups (area/group/serial)."""
    if not re.fullmatch(r"\d{9}", ssn):
        raise ValueError("SSN must be exactly 9 digits")
    area, group, serial = ssn[:3], ssn[3:5], ssn[5:]
    if area == "000" or group == "00" or serial == "0000":
        raise ValueError("SSN cannot have all-zero area, group, or serial")
    return ssn


class Person(BaseModel):
    first_name: str
    last_name: str
    ssn: str
    date_of_birth: date
    is_blind: bool = False

    @field_validator("ssn")
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        return _validate_ssn(v)


class Dependent(BaseModel):
    first_name: str
    last_name: str
    ssn: str
    relationship: str
    date_of_birth: date
    months_lived_with: int = 12
    is_student: bool = False
    is_qualifying_child: bool = True
    is_us_citizen: bool = True

    @field_validator("ssn")
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        return _validate_ssn(v)

    @field_validator("months_lived_with")
    @classmethod
    def validate_months(cls, v: int) -> int:
        if not 0 <= v <= 12:
            raise ValueError("months_lived_with must be between 0 and 12")
        return v


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str
    apt: str | None = None

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        if not re.fullmatch(r"\d{5}(\d{4})?", v):
            raise ValueError("zip_code must be 5 or 9 digits")
        return v
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/test_models.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add api/tax_engine/ tests/api/tax_engine/
git commit -m "feat(tax_engine): add Person, Dependent, Address models with SSN validation"
```

---

## Task 2: Domain Models — Income

**Files:**
- Create: `api/tax_engine/models/income.py`
- Modify: `tests/api/tax_engine/test_models.py`

- [ ] **Step 1: Write failing tests for W2, 1099 variants, ScheduleC, ScheduleK1**

Append to `tests/api/tax_engine/test_models.py`:

```python
class TestW2:
    def test_valid_w2(self):
        from api.tax_engine.models.income import W2

        w = W2(
            employer_name="Acme Corp",
            employer_ein="12-3456789",
            box1_wages=Decimal("85000"),
            box2_fed_withheld=Decimal("15000"),
        )
        assert w.box1_wages == Decimal("85000")
        assert w.person_role == "primary"

    def test_ein_format_validation(self):
        from api.tax_engine.models.income import W2

        with pytest.raises(ValueError):
            W2(employer_name="Acme", employer_ein="invalid", box1_wages=Decimal("1000"))

    def test_defaults_to_zero(self):
        from api.tax_engine.models.income import W2

        w = W2(employer_name="Acme", employer_ein="12-3456789")
        assert w.box3_ss_wages == Decimal("0")
        assert w.box12_codes == {}


class TestIncome1099Int:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099Int

        f = Income1099Int(payer="Chase Bank", box1_interest=Decimal("1500"))
        assert f.box4_fed_withheld == Decimal("0")


class TestIncome1099Div:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099Div

        f = Income1099Div(
            payer="Vanguard",
            box1a_ordinary_dividends=Decimal("5000"),
            box1b_qualified_dividends=Decimal("4000"),
        )
        assert f.box2a_capital_gain_distributions == Decimal("0")


class TestIncome1099B:
    def test_valid(self):
        from api.tax_engine.models.income import Income1099B

        f = Income1099B(
            payer="Fidelity",
            short_term_proceeds=Decimal("10000"),
            short_term_cost_basis=Decimal("8000"),
            long_term_proceeds=Decimal("50000"),
            long_term_cost_basis=Decimal("30000"),
        )
        assert f.collectibles_gain == Decimal("0")


class TestScheduleC:
    def test_net_profit_computed(self):
        from api.tax_engine.models.income import ScheduleC

        sc = ScheduleC(
            business_name="My Consulting",
            gross_receipts=Decimal("120000"),
            cost_of_goods_sold=Decimal("10000"),
            advertising=Decimal("2000"),
            supplies=Decimal("3000"),
        )
        # net_profit = 120000 - 10000 - (2000 + 3000) = 105000
        assert sc.net_profit == Decimal("105000")

    def test_total_expenses(self):
        from api.tax_engine.models.income import ScheduleC

        sc = ScheduleC(
            business_name="Test",
            gross_receipts=Decimal("100000"),
            advertising=Decimal("1000"),
            insurance=Decimal("2000"),
            rent_lease=Decimal("3000"),
        )
        assert sc.total_expenses == Decimal("6000")


class TestScheduleK1:
    def test_valid_partnership(self):
        from api.tax_engine.models.income import ScheduleK1

        k1 = ScheduleK1(
            entity_name="ABC Partners",
            entity_ein="98-7654321",
            entity_type="P",
            box1_ordinary_income=Decimal("50000"),
        )
        assert k1.is_passive is False
        assert k1.is_sstb is False
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/api/tax_engine/test_models.py::TestW2 -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement income.py**

Create `api/tax_engine/models/income.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/models/income.py tests/api/tax_engine/test_models.py
git commit -m "feat(tax_engine): add income models — W2, 1099 variants, ScheduleC, ScheduleK1"
```

---

## Task 3: Domain Models — Deductions, Credits, TaxReturn

**Files:**
- Create: `api/tax_engine/models/deductions.py`
- Create: `api/tax_engine/models/credits.py`
- Create: `api/tax_engine/models/tax_return.py`
- Modify: `api/tax_engine/models/__init__.py`
- Modify: `tests/api/tax_engine/test_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/api/tax_engine/test_models.py`:

```python
class TestItemizedDeductions:
    def test_defaults_to_zero(self):
        from api.tax_engine.models.deductions import ItemizedDeductions

        d = ItemizedDeductions()
        assert d.medical_dental == Decimal("0")
        assert d.charity_cash == Decimal("0")


class TestRentalProperty:
    def test_net_income_computed(self):
        from api.tax_engine.models.deductions import RentalProperty

        rp = RentalProperty(
            address="456 Oak Ave",
            rent_received=Decimal("24000"),
            mortgage_interest=Decimal("8000"),
            taxes=Decimal("4000"),
            insurance=Decimal("2000"),
        )
        assert rp.net_income == Decimal("10000")


class TestLineTrace:
    def test_frozen(self):
        from api.tax_engine.models.tax_return import LineTrace

        lt = LineTrace(
            form="1040", line="1a", label="Wages",
            value=Decimal("85000"), formula="sum(w2.box1_wages)",
        )
        with pytest.raises(Exception):
            lt.value = Decimal("0")

    def test_fields(self):
        from api.tax_engine.models.tax_return import LineTrace

        lt = LineTrace(
            form="Schedule A", line="7", label="SALT",
            value=Decimal("10000"), formula="min(salt_total, salt_cap)",
            constants_used={"salt_cap": "10000"},
            irs_citation="TCJA §11042",
        )
        assert lt.irs_citation == "TCJA §11042"


class TestTaxReturn:
    def test_minimal_return(self):
        from api.tax_engine.models.people import Person, Address
        from api.tax_engine.models.tax_return import TaxReturn

        tr = TaxReturn(
            tax_year=2024,
            filing_status="S",
            primary=Person(
                first_name="John", last_name="Doe",
                ssn="123456789", date_of_birth=date(1985, 1, 1),
            ),
            address=Address(
                street="123 Main St", city="Springfield",
                state="IL", zip_code="62701",
            ),
        )
        assert tr.w2s == []
        assert tr.filing_status == "S"

    def test_full_return_with_income(self):
        from api.tax_engine.models.people import Person, Address
        from api.tax_engine.models.income import W2
        from api.tax_engine.models.tax_return import TaxReturn

        tr = TaxReturn(
            tax_year=2024,
            filing_status="MFJ",
            primary=Person(
                first_name="John", last_name="Doe",
                ssn="123456789", date_of_birth=date(1985, 1, 1),
            ),
            spouse=Person(
                first_name="Jane", last_name="Doe",
                ssn="987654321", date_of_birth=date(1987, 5, 10),
            ),
            address=Address(
                street="123 Main St", city="Springfield",
                state="IL", zip_code="62701",
            ),
            w2s=[
                W2(employer_name="Acme", employer_ein="12-3456789",
                   box1_wages=Decimal("85000")),
            ],
        )
        assert len(tr.w2s) == 1


class TestFormResult:
    def test_basic(self):
        from api.tax_engine.models.tax_return import FormResult, LineTrace

        fr = FormResult(
            form_name="Schedule B",
            lines={
                "4": LineTrace(form="Schedule B", line="4", label="Total interest",
                               value=Decimal("5000"), formula="sum(1099_int)"),
            },
            total=Decimal("5000"),
        )
        assert fr.lines["4"].value == Decimal("5000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_models.py::TestLineTrace -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement deductions.py**

Create `api/tax_engine/models/deductions.py`:

```python
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
```

- [ ] **Step 4: Implement credits.py**

Create `api/tax_engine/models/credits.py`:

```python
"""Credit-related input models."""
from decimal import Decimal

from pydantic import BaseModel

from api.tax_engine.models.income import PersonRole


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
    label: str
    amount: Decimal = Decimal("0")
```

- [ ] **Step 5: Implement tax_return.py**

Create `api/tax_engine/models/tax_return.py`:

```python
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
```

- [ ] **Step 6: Update models __init__.py**

Create `api/tax_engine/models/__init__.py`:

```python
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
```

- [ ] **Step 7: Run all model tests**

Run: `python -m pytest tests/api/tax_engine/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add api/tax_engine/models/ tests/api/tax_engine/test_models.py
git commit -m "feat(tax_engine): add deduction, credit, TaxReturn, LineTrace models"
```

---

## Task 4: Tax Year Constants

**Files:**
- Create: `api/tax_engine/constants/__init__.py`
- Create: `api/tax_engine/constants/registry.py`
- Create: `api/tax_engine/constants/ty2024.py`
- Create: `api/tax_engine/constants/ty2025.py`
- Create: `tests/api/tax_engine/test_constants.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/test_constants.py`:

```python
"""Tests for tax year constants registry."""
import pytest
from decimal import Decimal


class TestRegistry:
    def test_get_2024(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.tax_year == 2024

    def test_get_2025(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2025)
        assert c.tax_year == 2025

    def test_unknown_year_raises(self):
        from api.tax_engine.constants.registry import get_constants

        with pytest.raises(ValueError, match="No tax constants"):
            get_constants(1999)

    def test_available_years(self):
        from api.tax_engine.constants.registry import available_years

        years = available_years()
        assert 2024 in years
        assert 2025 in years


class TestTY2024Values:
    def test_standard_deduction_single(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.standard_deduction["S"] == Decimal("14600")

    def test_standard_deduction_mfj(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.standard_deduction["MFJ"] == Decimal("29200")

    def test_ss_wage_base(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.ss_wage_base == Decimal("168600")

    def test_ctc_amount(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.ctc_amount_per_child == Decimal("2000")

    def test_salt_cap(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.salt_cap["MFJ"] == Decimal("10000")

    def test_tax_brackets_7_rates(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert len(c.ordinary_brackets["S"]) == 7
        assert c.ordinary_brackets["S"][0] == (Decimal("11600"), Decimal("0.10"))

    def test_qbi_threshold(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2024)
        assert c.qbi_threshold["MFJ"] == Decimal("383900")


class TestTY2025Values:
    def test_standard_deduction_single(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2025)
        assert c.standard_deduction["S"] == Decimal("15000")

    def test_ctc_amount_increased(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2025)
        assert c.ctc_amount_per_child == Decimal("2200")

    def test_salt_cap_increased(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2025)
        assert c.salt_cap["MFJ"] == Decimal("40000")

    def test_ss_wage_base_2025(self):
        from api.tax_engine.constants.registry import get_constants

        c = get_constants(2025)
        assert c.ss_wage_base == Decimal("176100")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement registry.py**

Create `api/tax_engine/constants/registry.py`:

```python
"""Tax year constants registry — year-agnostic architecture."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TaxYearConstants:
    tax_year: int
    # Standard deductions by filing status
    standard_deduction: dict[str, Decimal]
    # Ordinary income brackets: list of (upper_bound_of_bracket, rate) per status
    # Brackets are cumulative width: (11600, 0.10) means first $11,600 at 10%
    ordinary_brackets: dict[str, list[tuple[Decimal, Decimal]]]
    # Long-term capital gains brackets: (upper_bound, rate)
    ltcg_brackets: dict[str, list[tuple[Decimal, Decimal]]]
    # Child Tax Credit
    ctc_amount_per_child: Decimal
    ctc_other_dependent: Decimal
    ctc_phase_out: dict[str, Decimal]
    ctc_phase_out_rate: Decimal
    ctc_refundable_max_per_child: Decimal
    ctc_earned_income_threshold: Decimal
    # Self-employment / FICA
    ss_wage_base: Decimal
    ss_tax_rate: Decimal
    ss_combined_rate: Decimal
    medicare_tax_rate: Decimal
    medicare_combined_rate: Decimal
    additional_medicare_rate: Decimal
    additional_medicare_threshold: dict[str, Decimal]
    # NIIT
    niit_rate: Decimal
    niit_threshold: dict[str, Decimal]
    # Deductions
    salt_cap: dict[str, Decimal]
    medical_agi_floor_pct: Decimal
    # QBI
    qbi_deduction_rate: Decimal
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
    amt_rate_low: Decimal
    amt_rate_high: Decimal
    amt_bracket: dict[str, Decimal]
    # Student loan
    student_loan_max_deduction: Decimal
    student_loan_phase_out: dict[str, tuple[Decimal, Decimal]]
    # Capital loss
    capital_loss_limit: dict[str, Decimal]


_REGISTRY: dict[int, TaxYearConstants] = {}


def register(constants: TaxYearConstants) -> None:
    """Register a TaxYearConstants instance."""
    _REGISTRY[constants.tax_year] = constants


def get_constants(year: int) -> TaxYearConstants:
    """Get constants for a tax year. Raises ValueError if not registered."""
    if year not in _REGISTRY:
        raise ValueError(f"No tax constants registered for year {year}")
    return _REGISTRY[year]


def available_years() -> list[int]:
    """Return sorted list of registered tax years."""
    return sorted(_REGISTRY.keys())
```

- [ ] **Step 4: Implement ty2024.py**

Create `api/tax_engine/constants/ty2024.py`:

```python
"""TY2024 federal tax constants. Source: Rev. Proc. 2023-34, IRS Pub 15."""
from decimal import Decimal
from api.tax_engine.constants.registry import TaxYearConstants, register

_D = Decimal

TY2024 = TaxYearConstants(
    tax_year=2024,
    standard_deduction={
        "S": _D("14600"), "MFJ": _D("29200"), "MFS": _D("14600"),
        "HOH": _D("21900"), "QSS": _D("29200"),
    },
    ordinary_brackets={
        "S": [
            (_D("11600"), _D("0.10")), (_D("47150"), _D("0.12")),
            (_D("100525"), _D("0.22")), (_D("191950"), _D("0.24")),
            (_D("243725"), _D("0.32")), (_D("609350"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "MFJ": [
            (_D("23200"), _D("0.10")), (_D("94300"), _D("0.12")),
            (_D("201050"), _D("0.22")), (_D("383900"), _D("0.24")),
            (_D("487450"), _D("0.32")), (_D("731200"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "MFS": [
            (_D("11600"), _D("0.10")), (_D("47150"), _D("0.12")),
            (_D("100525"), _D("0.22")), (_D("191950"), _D("0.24")),
            (_D("243725"), _D("0.32")), (_D("365600"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "HOH": [
            (_D("16550"), _D("0.10")), (_D("63100"), _D("0.12")),
            (_D("100500"), _D("0.22")), (_D("191950"), _D("0.24")),
            (_D("243700"), _D("0.32")), (_D("609350"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
    },
    ltcg_brackets={
        "S": [(_D("47025"), _D("0")), (_D("518900"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "MFJ": [(_D("94050"), _D("0")), (_D("583750"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "MFS": [(_D("47025"), _D("0")), (_D("291850"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "HOH": [(_D("63000"), _D("0")), (_D("551350"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
    },
    ctc_amount_per_child=_D("2000"),
    ctc_other_dependent=_D("500"),
    ctc_phase_out={"MFJ": _D("400000"), "S": _D("200000"), "HOH": _D("200000"), "MFS": _D("200000"), "QSS": _D("200000")},
    ctc_phase_out_rate=_D("0.05"),
    ctc_refundable_max_per_child=_D("1600"),
    ctc_earned_income_threshold=_D("2500"),
    ss_wage_base=_D("168600"),
    ss_tax_rate=_D("0.062"),
    ss_combined_rate=_D("0.124"),
    medicare_tax_rate=_D("0.0145"),
    medicare_combined_rate=_D("0.029"),
    additional_medicare_rate=_D("0.009"),
    additional_medicare_threshold={
        "MFJ": _D("250000"), "MFS": _D("125000"), "S": _D("200000"),
        "HOH": _D("200000"), "QSS": _D("200000"),
    },
    niit_rate=_D("0.038"),
    niit_threshold={
        "MFJ": _D("250000"), "MFS": _D("125000"), "S": _D("200000"),
        "HOH": _D("200000"), "QSS": _D("250000"),
    },
    salt_cap={"MFJ": _D("10000"), "S": _D("10000"), "MFS": _D("5000"), "HOH": _D("10000"), "QSS": _D("10000")},
    medical_agi_floor_pct=_D("0.075"),
    qbi_deduction_rate=_D("0.20"),
    qbi_threshold={"MFJ": _D("383900"), "S": _D("191950"), "MFS": _D("191950"), "HOH": _D("191950"), "QSS": _D("383900")},
    qbi_phase_in_range={"MFJ": _D("100000"), "S": _D("50000"), "MFS": _D("50000"), "HOH": _D("50000"), "QSS": _D("100000")},
    hsa_limit={"self-only": _D("4150"), "family": _D("8300")},
    hsa_catchup=_D("1000"),
    ira_contribution_limit=_D("7000"),
    ira_catchup=_D("1000"),
    amt_exemption={"MFJ": _D("133300"), "S": _D("85700"), "MFS": _D("66650"), "HOH": _D("85700"), "QSS": _D("133300")},
    amt_phase_out={"MFJ": _D("1218700"), "S": _D("609350"), "MFS": _D("609350"), "HOH": _D("609350"), "QSS": _D("1218700")},
    amt_rate_low=_D("0.26"),
    amt_rate_high=_D("0.28"),
    amt_bracket={"MFJ": _D("232600"), "MFS": _D("116300"), "S": _D("232600"), "HOH": _D("232600"), "QSS": _D("232600")},
    student_loan_max_deduction=_D("2500"),
    student_loan_phase_out={
        "MFJ": (_D("155000"), _D("185000")), "S": (_D("75000"), _D("90000")),
        "MFS": (_D("0"), _D("0")), "HOH": (_D("75000"), _D("90000")),
        "QSS": (_D("155000"), _D("185000")),
    },
    capital_loss_limit={"MFJ": _D("3000"), "MFS": _D("1500"), "S": _D("3000"), "HOH": _D("3000"), "QSS": _D("3000")},
)

# QSS brackets = MFJ brackets
TY2024.ordinary_brackets["QSS"] = TY2024.ordinary_brackets["MFJ"]  # type: ignore[index]
TY2024.ltcg_brackets["QSS"] = TY2024.ltcg_brackets["MFJ"]  # type: ignore[index]

register(TY2024)
```

Note: The `TaxYearConstants` is frozen, but the dict values are mutable references. The QSS alias lines set dict entries on the already-constructed dicts inside the frozen dataclass (this works because frozen only prevents attribute reassignment, not mutation of mutable attribute values).

- [ ] **Step 5: Implement ty2025.py**

Create `api/tax_engine/constants/ty2025.py`:

```python
"""TY2025 federal tax constants. Source: Rev. Proc. 2024-40, OBBB Act."""
from decimal import Decimal
from api.tax_engine.constants.registry import TaxYearConstants, register

_D = Decimal

TY2025 = TaxYearConstants(
    tax_year=2025,
    standard_deduction={
        "S": _D("15000"), "MFJ": _D("30000"), "MFS": _D("15000"),
        "HOH": _D("22500"), "QSS": _D("30000"),
    },
    ordinary_brackets={
        "S": [
            (_D("11925"), _D("0.10")), (_D("48475"), _D("0.12")),
            (_D("103350"), _D("0.22")), (_D("197300"), _D("0.24")),
            (_D("250525"), _D("0.32")), (_D("626350"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "MFJ": [
            (_D("23850"), _D("0.10")), (_D("96950"), _D("0.12")),
            (_D("206700"), _D("0.22")), (_D("394600"), _D("0.24")),
            (_D("501050"), _D("0.32")), (_D("751600"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "MFS": [
            (_D("11925"), _D("0.10")), (_D("48475"), _D("0.12")),
            (_D("103350"), _D("0.22")), (_D("197300"), _D("0.24")),
            (_D("250525"), _D("0.32")), (_D("375800"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
        "HOH": [
            (_D("17000"), _D("0.10")), (_D("64850"), _D("0.12")),
            (_D("103350"), _D("0.22")), (_D("197300"), _D("0.24")),
            (_D("250500"), _D("0.32")), (_D("626350"), _D("0.35")),
            (_D("Infinity"), _D("0.37")),
        ],
    },
    ltcg_brackets={
        "S": [(_D("48350"), _D("0")), (_D("533400"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "MFJ": [(_D("96700"), _D("0")), (_D("600050"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "MFS": [(_D("48350"), _D("0")), (_D("300025"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
        "HOH": [(_D("64750"), _D("0")), (_D("566700"), _D("0.15")), (_D("Infinity"), _D("0.20"))],
    },
    ctc_amount_per_child=_D("2200"),
    ctc_other_dependent=_D("500"),
    ctc_phase_out={"MFJ": _D("400000"), "S": _D("200000"), "HOH": _D("200000"), "MFS": _D("200000"), "QSS": _D("200000")},
    ctc_phase_out_rate=_D("0.05"),
    ctc_refundable_max_per_child=_D("1700"),
    ctc_earned_income_threshold=_D("2500"),
    ss_wage_base=_D("176100"),
    ss_tax_rate=_D("0.062"),
    ss_combined_rate=_D("0.124"),
    medicare_tax_rate=_D("0.0145"),
    medicare_combined_rate=_D("0.029"),
    additional_medicare_rate=_D("0.009"),
    additional_medicare_threshold={
        "MFJ": _D("250000"), "MFS": _D("125000"), "S": _D("200000"),
        "HOH": _D("200000"), "QSS": _D("200000"),
    },
    niit_rate=_D("0.038"),
    niit_threshold={
        "MFJ": _D("250000"), "MFS": _D("125000"), "S": _D("200000"),
        "HOH": _D("200000"), "QSS": _D("250000"),
    },
    salt_cap={"MFJ": _D("40000"), "S": _D("40000"), "MFS": _D("20000"), "HOH": _D("40000"), "QSS": _D("40000")},
    medical_agi_floor_pct=_D("0.075"),
    qbi_deduction_rate=_D("0.20"),
    qbi_threshold={"MFJ": _D("394600"), "S": _D("197300"), "MFS": _D("197300"), "HOH": _D("197300"), "QSS": _D("394600")},
    qbi_phase_in_range={"MFJ": _D("100000"), "S": _D("50000"), "MFS": _D("50000"), "HOH": _D("50000"), "QSS": _D("100000")},
    hsa_limit={"self-only": _D("4300"), "family": _D("8550")},
    hsa_catchup=_D("1000"),
    ira_contribution_limit=_D("7000"),
    ira_catchup=_D("1000"),
    amt_exemption={"MFJ": _D("137000"), "S": _D("88100"), "MFS": _D("68500"), "HOH": _D("88100"), "QSS": _D("137000")},
    amt_phase_out={"MFJ": _D("1252700"), "S": _D("626350"), "MFS": _D("626350"), "HOH": _D("626350"), "QSS": _D("1252700")},
    amt_rate_low=_D("0.26"),
    amt_rate_high=_D("0.28"),
    amt_bracket={"MFJ": _D("239200"), "MFS": _D("119600"), "S": _D("239200"), "HOH": _D("239200"), "QSS": _D("239200")},
    student_loan_max_deduction=_D("2500"),
    student_loan_phase_out={
        "MFJ": (_D("160000"), _D("190000")), "S": (_D("80000"), _D("95000")),
        "MFS": (_D("0"), _D("0")), "HOH": (_D("80000"), _D("95000")),
        "QSS": (_D("160000"), _D("190000")),
    },
    capital_loss_limit={"MFJ": _D("3000"), "MFS": _D("1500"), "S": _D("3000"), "HOH": _D("3000"), "QSS": _D("3000")},
)

TY2025.ordinary_brackets["QSS"] = TY2025.ordinary_brackets["MFJ"]  # type: ignore[index]
TY2025.ltcg_brackets["QSS"] = TY2025.ltcg_brackets["MFJ"]  # type: ignore[index]

register(TY2025)
```

- [ ] **Step 6: Implement constants __init__.py**

Create `api/tax_engine/constants/__init__.py`:

```python
"""Tax year constants package. Importing triggers auto-registration."""
import api.tax_engine.constants.ty2024 as _ty2024  # noqa: F401
import api.tax_engine.constants.ty2025 as _ty2025  # noqa: F401

from api.tax_engine.constants.registry import get_constants, available_years, TaxYearConstants

__all__ = ["get_constants", "available_years", "TaxYearConstants"]
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_constants.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add api/tax_engine/constants/ tests/api/tax_engine/test_constants.py
git commit -m "feat(tax_engine): add TY2024/2025 constants with year-agnostic registry"
```

---

## Task 5: Base Calculator + Test Fixtures

**Files:**
- Create: `api/tax_engine/calculators/__init__.py`
- Create: `api/tax_engine/calculators/base.py`
- Create: `tests/api/tax_engine/conftest.py`

- [ ] **Step 1: Write failing test for BaseCalculator**

Create `tests/api/tax_engine/conftest.py`:

```python
"""Shared test fixtures for tax engine tests."""
import pytest
from datetime import date
from decimal import Decimal

from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.constants.registry import get_constants, TaxYearConstants

# Ensure constants are registered
import api.tax_engine.constants  # noqa: F401


@pytest.fixture
def constants_2024() -> TaxYearConstants:
    return get_constants(2024)


@pytest.fixture
def constants_2025() -> TaxYearConstants:
    return get_constants(2025)


@pytest.fixture
def primary_person() -> Person:
    return Person(
        first_name="John", last_name="Doe",
        ssn="123456789", date_of_birth=date(1985, 3, 15),
    )


@pytest.fixture
def spouse_person() -> Person:
    return Person(
        first_name="Jane", last_name="Doe",
        ssn="987654321", date_of_birth=date(1987, 5, 10),
    )


@pytest.fixture
def address() -> Address:
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")


@pytest.fixture
def minimal_return(primary_person, address) -> TaxReturn:
    """Single filer, no income, TY2024."""
    return TaxReturn(
        tax_year=2024,
        filing_status="S",
        primary=primary_person,
        address=address,
    )


@pytest.fixture
def mfj_return(primary_person, spouse_person, address) -> TaxReturn:
    """MFJ filer, no income, TY2024."""
    return TaxReturn(
        tax_year=2024,
        filing_status="MFJ",
        primary=primary_person,
        spouse=spouse_person,
        address=address,
    )
```

- [ ] **Step 2: Implement base.py**

Create `api/tax_engine/calculators/__init__.py`:

```python
"""Tax engine calculators package."""
```

Create `api/tax_engine/calculators/base.py`:

```python
"""Base calculator with LineTrace support."""
from abc import ABC, abstractmethod
from decimal import Decimal

from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn


class BaseCalculator(ABC):
    """Abstract base for all tax form calculators.

    Subclasses implement compute() and use self.trace() to record audit lines.
    """

    def __init__(self, constants: TaxYearConstants):
        self.constants = constants
        self._traces: list[LineTrace] = []

    def trace(
        self,
        form: str,
        line: str,
        label: str,
        value: Decimal,
        formula: str,
        inputs: dict[str, str] | None = None,
        constants_used: dict[str, str] | None = None,
        irs_citation: str | None = None,
    ) -> Decimal:
        """Record a LineTrace and return the value for chaining."""
        lt = LineTrace(
            form=form, line=line, label=label, value=value,
            formula=formula, inputs=inputs or {},
            constants_used=constants_used or {},
            irs_citation=irs_citation,
        )
        self._traces.append(lt)
        return value

    def build_result(self, form_name: str, total: Decimal) -> FormResult:
        """Package accumulated traces into a FormResult."""
        lines = {t.line: t for t in self._traces}
        return FormResult(form_name=form_name, lines=lines, total=total)

    @abstractmethod
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        """Compute this form's result. May read prior_results from other forms."""
```

- [ ] **Step 3: Commit**

```bash
git add api/tax_engine/calculators/ tests/api/tax_engine/conftest.py
git commit -m "feat(tax_engine): add BaseCalculator ABC and test fixtures"
```

---

## Task 6: Schedule B Calculator (Interest & Dividends)

**Files:**
- Create: `api/tax_engine/calculators/schedule_b.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_b.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_b.py`:

```python
"""Tests for Schedule B — Interest and Ordinary Dividends."""
from decimal import Decimal

from api.tax_engine.models.income import Income1099Int, Income1099Div


class TestScheduleB:
    def test_single_interest(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator

        minimal_return.interest_1099s = [
            Income1099Int(payer="Chase", box1_interest=Decimal("1500")),
        ]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("1500")

    def test_multiple_interest_sources(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator

        minimal_return.interest_1099s = [
            Income1099Int(payer="Chase", box1_interest=Decimal("1500")),
            Income1099Int(payer="Ally", box1_interest=Decimal("800")),
        ]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("2300")

    def test_dividends(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator

        minimal_return.dividend_1099s = [
            Income1099Div(
                payer="Vanguard",
                box1a_ordinary_dividends=Decimal("5000"),
                box1b_qualified_dividends=Decimal("4000"),
            ),
        ]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["6"].value == Decimal("5000")

    def test_no_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator

        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["4"].value == Decimal("0")
        assert result.total == Decimal("0")

    def test_traces_have_form_name(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_b import ScheduleBCalculator

        minimal_return.interest_1099s = [
            Income1099Int(payer="Chase", box1_interest=Decimal("1000")),
        ]
        calc = ScheduleBCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.form_name == "Schedule B"
        assert result.lines["4"].form == "Schedule B"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_b.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_b.py**

Create `api/tax_engine/calculators/schedule_b.py`:

```python
"""Schedule B — Interest and Ordinary Dividends."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule B"


class ScheduleBCalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        total_interest = sum(
            (f.box1_interest for f in tax_return.interest_1099s), Decimal("0")
        )
        self.trace(FORM, "4", "Total interest", total_interest,
                   "sum(1099-INT box 1)")

        total_ordinary_div = sum(
            (f.box1a_ordinary_dividends for f in tax_return.dividend_1099s),
            Decimal("0"),
        )
        self.trace(FORM, "6", "Total ordinary dividends", total_ordinary_div,
                   "sum(1099-DIV box 1a)")

        total_qualified_div = sum(
            (f.box1b_qualified_dividends for f in tax_return.dividend_1099s),
            Decimal("0"),
        )
        self.trace(FORM, "qualified", "Total qualified dividends",
                   total_qualified_div, "sum(1099-DIV box 1b)")

        total = total_interest + total_ordinary_div
        return self.build_result(FORM, total)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_b.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_b.py tests/api/tax_engine/calculators/test_schedule_b.py
git commit -m "feat(tax_engine): add Schedule B calculator — interest & dividends"
```

---

## Task 7: Schedule C Calculator (Self-Employment Income)

**Files:**
- Create: `api/tax_engine/calculators/schedule_c.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_c.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_c.py`:

```python
"""Tests for Schedule C — Profit or Loss from Business."""
from decimal import Decimal

from api.tax_engine.models.income import ScheduleC


class TestScheduleC:
    def test_single_business(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator

        minimal_return.schedule_cs = [
            ScheduleC(
                business_name="Consulting LLC",
                gross_receipts=Decimal("120000"),
                cost_of_goods_sold=Decimal("10000"),
                advertising=Decimal("2000"),
                supplies=Decimal("3000"),
            ),
        ]
        calc = ScheduleCCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["31"].value == Decimal("105000")

    def test_multiple_businesses(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Biz A", gross_receipts=Decimal("50000")),
            ScheduleC(business_name="Biz B", gross_receipts=Decimal("30000"),
                      advertising=Decimal("5000")),
        ]
        calc = ScheduleCCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # 50000 + (30000 - 5000) = 75000
        assert result.total == Decimal("75000")

    def test_no_businesses(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator

        calc = ScheduleCCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.total == Decimal("0")

    def test_loss_business(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_c import ScheduleCCalculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Startup", gross_receipts=Decimal("5000"),
                      rent_lease=Decimal("12000")),
        ]
        calc = ScheduleCCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.total == Decimal("-7000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_c.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_c.py**

Create `api/tax_engine/calculators/schedule_c.py`:

```python
"""Schedule C — Profit or Loss from Business (Sole Proprietorship)."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule C"


class ScheduleCCalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        total_net = Decimal("0")
        for i, sc in enumerate(tax_return.schedule_cs):
            net = sc.net_profit
            self.trace(
                FORM, "31" if i == 0 else f"31_{i+1}",
                f"Net profit — {sc.business_name}", net,
                "gross_receipts - COGS - total_expenses",
                inputs={
                    "gross_receipts": str(sc.gross_receipts),
                    "cogs": str(sc.cost_of_goods_sold),
                    "total_expenses": str(sc.total_expenses),
                },
            )
            total_net += net

        if not tax_return.schedule_cs:
            self.trace(FORM, "31", "Net profit", Decimal("0"), "no businesses")

        return self.build_result(FORM, total_net)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_c.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_c.py tests/api/tax_engine/calculators/test_schedule_c.py
git commit -m "feat(tax_engine): add Schedule C calculator — self-employment income"
```

---

## Task 8: Schedule D Calculator (Capital Gains)

**Files:**
- Create: `api/tax_engine/calculators/schedule_d.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_d.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_d.py`:

```python
"""Tests for Schedule D — Capital Gains and Losses."""
from decimal import Decimal

from api.tax_engine.models.income import Income1099B


class TestScheduleD:
    def test_net_short_term_gain(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        minimal_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        short_term_proceeds=Decimal("15000"),
                        short_term_cost_basis=Decimal("10000")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["7"].value == Decimal("5000")

    def test_net_long_term_gain(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        minimal_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        long_term_proceeds=Decimal("50000"),
                        long_term_cost_basis=Decimal("30000")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["15"].value == Decimal("20000")

    def test_capital_loss_limited(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        minimal_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        long_term_proceeds=Decimal("5000"),
                        long_term_cost_basis=Decimal("20000")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # Net loss = -15000, limited to -3000 for single
        assert result.lines["21"].value == Decimal("-3000")

    def test_capital_loss_limit_mfs(self, mfj_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        mfj_return.filing_status = "MFS"
        mfj_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        short_term_proceeds=Decimal("1000"),
                        short_term_cost_basis=Decimal("10000")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(mfj_return, {})
        assert result.lines["21"].value == Decimal("-1500")

    def test_wash_sale_adjustment(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        minimal_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        short_term_proceeds=Decimal("10000"),
                        short_term_cost_basis=Decimal("12000"),
                        short_term_wash_sales=Decimal("500")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # ST gain = 10000 - 12000 + 500 (wash sale disallowed added back) = -1500
        assert result.lines["7"].value == Decimal("-1500")

    def test_no_investments(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.total == Decimal("0")

    def test_carryforward_included(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_d import ScheduleDCalculator

        minimal_return.capital_loss_carryforward_lt = Decimal("2000")
        minimal_return.broker_1099s = [
            Income1099B(payer="Fidelity",
                        long_term_proceeds=Decimal("5000"),
                        long_term_cost_basis=Decimal("3000")),
        ]
        calc = ScheduleDCalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # LT gain = 2000, carryforward loss = -2000, net = 0
        assert result.lines["15"].value == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_d.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_d.py**

Create `api/tax_engine/calculators/schedule_d.py`:

```python
"""Schedule D — Capital Gains and Losses."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule D"


class ScheduleDCalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        fs = tax_return.filing_status
        loss_limit = self.constants.capital_loss_limit[fs]

        # Part I: Short-term
        st_proceeds = sum((b.short_term_proceeds for b in tax_return.broker_1099s), Decimal("0"))
        st_basis = sum((b.short_term_cost_basis for b in tax_return.broker_1099s), Decimal("0"))
        st_wash = sum((b.short_term_wash_sales for b in tax_return.broker_1099s), Decimal("0"))
        st_carryforward = -tax_return.capital_loss_carryforward_st

        net_st = st_proceeds - st_basis + st_wash + st_carryforward
        self.trace(FORM, "7", "Net short-term capital gain/loss", net_st,
                   "proceeds - basis + wash_sale_disallowed + carryforward",
                   inputs={"proceeds": str(st_proceeds), "basis": str(st_basis),
                           "wash_sales": str(st_wash), "carryforward": str(st_carryforward)})

        # Part II: Long-term
        lt_proceeds = sum((b.long_term_proceeds for b in tax_return.broker_1099s), Decimal("0"))
        lt_basis = sum((b.long_term_cost_basis for b in tax_return.broker_1099s), Decimal("0"))
        lt_wash = sum((b.long_term_wash_sales for b in tax_return.broker_1099s), Decimal("0"))
        lt_carryforward = -tax_return.capital_loss_carryforward_lt

        # Include capital gain distributions from 1099-DIV
        cap_gain_dist = sum(
            (d.box2a_capital_gain_distributions for d in tax_return.dividend_1099s),
            Decimal("0"),
        )

        net_lt = lt_proceeds - lt_basis + lt_wash + lt_carryforward + cap_gain_dist
        self.trace(FORM, "15", "Net long-term capital gain/loss", net_lt,
                   "proceeds - basis + wash_sales + carryforward + cap_gain_distributions",
                   inputs={"proceeds": str(lt_proceeds), "basis": str(lt_basis),
                           "wash_sales": str(lt_wash), "carryforward": str(lt_carryforward),
                           "distributions": str(cap_gain_dist)})

        # Part III: Summary
        net_total = net_st + net_lt
        # Apply capital loss limitation
        if net_total < Decimal("0"):
            limited = max(net_total, -loss_limit)
        else:
            limited = net_total

        self.trace(FORM, "21", "Capital gain/loss (limited)", limited,
                   "max(net_st + net_lt, -loss_limit)",
                   inputs={"net_st": str(net_st), "net_lt": str(net_lt)},
                   constants_used={"loss_limit": str(loss_limit)},
                   irs_citation="IRC §1211(b)")

        return self.build_result(FORM, limited)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_d.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_d.py tests/api/tax_engine/calculators/test_schedule_d.py
git commit -m "feat(tax_engine): add Schedule D calculator — capital gains with loss limits"
```

---

## Task 9: Schedule E Calculator (Rental & K-1 Income)

**Files:**
- Create: `api/tax_engine/calculators/schedule_e.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_e.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_e.py`:

```python
"""Tests for Schedule E — Rental Real Estate and K-1 Income."""
from decimal import Decimal

from api.tax_engine.models.deductions import RentalProperty
from api.tax_engine.models.income import ScheduleK1


class TestScheduleE:
    def test_single_rental(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator

        minimal_return.rental_properties = [
            RentalProperty(
                address="456 Oak Ave",
                rent_received=Decimal("24000"),
                mortgage_interest=Decimal("8000"),
                taxes=Decimal("4000"),
                insurance=Decimal("2000"),
            ),
        ]
        calc = ScheduleECalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["26"].value == Decimal("10000")

    def test_k1_ordinary_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator

        minimal_return.k1s = [
            ScheduleK1(
                entity_name="ABC Partners", entity_ein="98-7654321",
                entity_type="P", box1_ordinary_income=Decimal("50000"),
            ),
        ]
        calc = ScheduleECalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["32"].value == Decimal("50000")

    def test_combined_rental_and_k1(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator

        minimal_return.rental_properties = [
            RentalProperty(address="123 St", rent_received=Decimal("12000"),
                           taxes=Decimal("2000")),
        ]
        minimal_return.k1s = [
            ScheduleK1(entity_name="XYZ", entity_ein="11-2222222",
                       entity_type="S", box1_ordinary_income=Decimal("30000")),
        ]
        calc = ScheduleECalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # Rental: 12000 - 2000 = 10000, K1: 30000, total = 40000
        assert result.total == Decimal("40000")

    def test_no_rental_or_k1(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_e import ScheduleECalculator

        calc = ScheduleECalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.total == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_e.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_e.py**

Create `api/tax_engine/calculators/schedule_e.py`:

```python
"""Schedule E — Supplemental Income (Rental Real Estate, K-1 Passthrough)."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule E"


class ScheduleECalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        # Part I: Rental real estate
        total_rental = Decimal("0")
        for i, rp in enumerate(tax_return.rental_properties):
            net = rp.net_income
            line = "26" if i == 0 else f"26_{i+1}"
            self.trace(FORM, line, f"Net rental income — {rp.address}", net,
                       "rent_received - total_expenses",
                       inputs={"rent": str(rp.rent_received),
                               "expenses": str(rp.total_expenses)})
            total_rental += net

        if not tax_return.rental_properties:
            self.trace(FORM, "26", "Net rental income", Decimal("0"), "no rental properties")

        # Part II: K-1 passthrough income
        total_k1 = Decimal("0")
        for i, k1 in enumerate(tax_return.k1s):
            income = (k1.box1_ordinary_income + k1.box2_rental_income
                      + k1.box4a_guaranteed_payments)
            line = "32" if i == 0 else f"32_{i+1}"
            self.trace(FORM, line, f"K-1 income — {k1.entity_name}", income,
                       "box1 + box2 + box4a",
                       inputs={"box1": str(k1.box1_ordinary_income),
                               "box2": str(k1.box2_rental_income),
                               "box4a": str(k1.box4a_guaranteed_payments)})
            total_k1 += income

        if not tax_return.k1s:
            self.trace(FORM, "32", "K-1 income", Decimal("0"), "no K-1s")

        total = total_rental + total_k1
        return self.build_result(FORM, total)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_e.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_e.py tests/api/tax_engine/calculators/test_schedule_e.py
git commit -m "feat(tax_engine): add Schedule E calculator — rental & K-1 income"
```

---

## Task 10: Schedule A Calculator (Itemized Deductions)

**Files:**
- Create: `api/tax_engine/calculators/schedule_a.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_a.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_a.py`:

```python
"""Tests for Schedule A — Itemized Deductions."""
from decimal import Decimal

from api.tax_engine.models.deductions import ItemizedDeductions
from api.tax_engine.models.tax_return import FormResult, LineTrace


def _agi_result(agi: Decimal) -> dict[str, FormResult]:
    """Helper: creates prior_results with AGI."""
    return {
        "AGI": FormResult(
            form_name="AGI",
            lines={"11": LineTrace(form="1040", line="11", label="AGI",
                                   value=agi, formula="total_income - adjustments")},
            total=agi,
        )
    }


class TestScheduleA:
    def test_salt_capped_2024(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.itemized = ItemizedDeductions(
            salt_income_or_sales=Decimal("15000"),
            salt_real_estate=Decimal("8000"),
        )
        calc = ScheduleACalculator(constants_2024)
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        # SALT = 15000 + 8000 = 23000, capped at 10000 for 2024
        assert result.lines["7"].value == Decimal("10000")

    def test_salt_capped_2025(self, minimal_return, constants_2025):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.tax_year = 2025
        minimal_return.itemized = ItemizedDeductions(
            salt_income_or_sales=Decimal("35000"),
            salt_real_estate=Decimal("8000"),
        )
        calc = ScheduleACalculator(constants_2025)
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        # SALT = 43000, capped at 40000 for 2025
        assert result.lines["7"].value == Decimal("40000")

    def test_medical_agi_floor(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.itemized = ItemizedDeductions(
            medical_dental=Decimal("12000"),
        )
        calc = ScheduleACalculator(constants_2024)
        # AGI = 100000, floor = 7500, deductible = 12000 - 7500 = 4500
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["4"].value == Decimal("4500")

    def test_medical_below_floor(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.itemized = ItemizedDeductions(
            medical_dental=Decimal("5000"),
        )
        calc = ScheduleACalculator(constants_2024)
        # AGI = 100000, floor = 7500, 5000 < 7500, deductible = 0
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["4"].value == Decimal("0")

    def test_charity(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.itemized = ItemizedDeductions(
            charity_cash=Decimal("5000"),
            charity_noncash=Decimal("2000"),
        )
        calc = ScheduleACalculator(constants_2024)
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["14"].value == Decimal("7000")

    def test_mortgage_interest(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        minimal_return.itemized = ItemizedDeductions(
            mortgage_interest_1098=Decimal("12000"),
            mortgage_interest_other=Decimal("1000"),
        )
        calc = ScheduleACalculator(constants_2024)
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.lines["10"].value == Decimal("13000")

    def test_no_itemized_returns_zero(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_a import ScheduleACalculator

        calc = ScheduleACalculator(constants_2024)
        result = calc.compute(minimal_return, _agi_result(Decimal("100000")))
        assert result.total == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_a.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_a.py**

Create `api/tax_engine/calculators/schedule_a.py`:

```python
"""Schedule A — Itemized Deductions."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule A"


class ScheduleACalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        itemized = tax_return.itemized
        if itemized is None:
            self.trace(FORM, "17", "Total itemized deductions", Decimal("0"),
                       "no itemized deductions provided")
            return self.build_result(FORM, Decimal("0"))

        fs = tax_return.filing_status
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")

        # Line 1-4: Medical & dental (7.5% AGI floor)
        floor = agi * self.constants.medical_agi_floor_pct
        medical = max(Decimal("0"), itemized.medical_dental - floor)
        self.trace(FORM, "4", "Medical & dental (after AGI floor)", medical,
                   "max(0, medical - agi * 7.5%)",
                   inputs={"medical": str(itemized.medical_dental), "agi": str(agi)},
                   constants_used={"floor_pct": str(self.constants.medical_agi_floor_pct)})

        # Line 5-7: SALT (capped)
        salt_total = (itemized.salt_income_or_sales + itemized.salt_real_estate
                      + itemized.salt_personal_property)
        salt_cap = self.constants.salt_cap[fs]
        salt = min(salt_total, salt_cap)
        self.trace(FORM, "7", "State and local taxes (capped)", salt,
                   "min(salt_total, salt_cap)",
                   inputs={"salt_total": str(salt_total)},
                   constants_used={"salt_cap": str(salt_cap)},
                   irs_citation="TCJA §11042")

        # Line 8-9: Interest
        interest = (itemized.mortgage_interest_1098 + itemized.mortgage_interest_other
                    + itemized.investment_interest)
        self.trace(FORM, "10", "Total interest", interest,
                   "mortgage_1098 + mortgage_other + investment_interest")

        # Line 11-14: Charitable contributions
        charity = itemized.charity_cash + itemized.charity_noncash
        self.trace(FORM, "14", "Total charitable contributions", charity,
                   "charity_cash + charity_noncash")

        # Line 15: Casualty/theft
        casualty = itemized.casualty_loss

        # Line 16: Other
        other = itemized.other_deductions

        # Line 17: Total
        total = medical + salt + interest + charity + casualty + other
        self.trace(FORM, "17", "Total itemized deductions", total,
                   "medical + salt + interest + charity + casualty + other",
                   inputs={"medical": str(medical), "salt": str(salt),
                           "interest": str(interest), "charity": str(charity)})

        return self.build_result(FORM, total)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_a.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_a.py tests/api/tax_engine/calculators/test_schedule_a.py
git commit -m "feat(tax_engine): add Schedule A calculator — itemized deductions with SALT cap"
```

---

## Task 11: Schedule SE Calculator (Self-Employment Tax)

**Files:**
- Create: `api/tax_engine/calculators/schedule_se.py`
- Create: `tests/api/tax_engine/calculators/test_schedule_se.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_schedule_se.py`:

```python
"""Tests for Schedule SE — Self-Employment Tax."""
from decimal import Decimal

from api.tax_engine.models.tax_return import FormResult, LineTrace


def _schedule_c_result(net_profit: Decimal) -> dict[str, FormResult]:
    return {
        "Schedule C": FormResult(
            form_name="Schedule C",
            lines={"31": LineTrace(form="Schedule C", line="31", label="Net profit",
                                   value=net_profit, formula="test")},
            total=net_profit,
        )
    }


class TestScheduleSE:
    def test_basic_se_tax(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator

        calc = ScheduleSECalculator(constants_2024)
        prior = _schedule_c_result(Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # SE income = 100000 * 0.9235 = 92350
        # SS tax = min(92350, 168600) * 0.124 = 11451.40
        # Medicare = 92350 * 0.029 = 2678.15
        # Total = 14129.55
        assert result.lines["12"].value == Decimal("14129.55")

    def test_deductible_half(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator

        calc = ScheduleSECalculator(constants_2024)
        prior = _schedule_c_result(Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # Deductible half = 14129.55 / 2 = 7064.78 (rounded)
        assert result.lines["13"].value == Decimal("7064.78")

    def test_ss_wage_cap_with_w2(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
        from api.tax_engine.models.income import W2

        minimal_return.w2s = [
            W2(employer_name="Acme", employer_ein="12-3456789",
               box3_ss_wages=Decimal("150000")),
        ]
        calc = ScheduleSECalculator(constants_2024)
        prior = _schedule_c_result(Decimal("50000"))
        result = calc.compute(minimal_return, prior)
        # SE income = 50000 * 0.9235 = 46175
        # SS room = 168600 - 150000 = 18600
        # SS tax = 18600 * 0.124 = 2306.40
        # Medicare = 46175 * 0.029 = 1339.08 (rounded)
        # Total = 3645.48
        assert result.lines["12"].value == Decimal("3645.48")

    def test_no_se_income(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.schedule_se import ScheduleSECalculator

        calc = ScheduleSECalculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.total == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_se.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule_se.py**

Create `api/tax_engine/calculators/schedule_se.py`:

```python
"""Schedule SE — Self-Employment Tax."""
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule SE"
SE_ADJUSTMENT = Decimal("0.9235")


class ScheduleSECalculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        # Get net SE income from Schedule C and K-1 SE earnings
        sched_c = prior_results.get("Schedule C")
        se_from_c = sched_c.total if sched_c else Decimal("0")
        se_from_k1 = sum((k.box14a_se_earnings for k in tax_return.k1s), Decimal("0"))
        net_se = se_from_c + se_from_k1

        if net_se <= Decimal("0"):
            self.trace(FORM, "12", "Total SE tax", Decimal("0"), "no SE income")
            self.trace(FORM, "13", "Deductible half of SE tax", Decimal("0"), "no SE tax")
            return self.build_result(FORM, Decimal("0"))

        # Line 4a: 92.35% of SE income
        taxable_se = (net_se * SE_ADJUSTMENT).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "4a", "Taxable SE income (92.35%)", taxable_se,
                   "net_se * 0.9235",
                   inputs={"net_se": str(net_se)})

        # SS wage base room (subtract W-2 SS wages)
        w2_ss_wages = sum((w.box3_ss_wages for w in tax_return.w2s), Decimal("0"))
        ss_room = max(Decimal("0"), self.constants.ss_wage_base - w2_ss_wages)
        ss_taxable = min(taxable_se, ss_room)

        # SS tax
        ss_tax = (ss_taxable * self.constants.ss_combined_rate).quantize(
            Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "10", "Social Security tax", ss_tax,
                   "min(taxable_se, ss_room) * ss_combined_rate",
                   inputs={"taxable_se": str(taxable_se), "ss_room": str(ss_room)},
                   constants_used={"ss_wage_base": str(self.constants.ss_wage_base),
                                   "ss_combined_rate": str(self.constants.ss_combined_rate)})

        # Medicare tax
        medicare_tax = (taxable_se * self.constants.medicare_combined_rate).quantize(
            Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "11", "Medicare tax", medicare_tax,
                   "taxable_se * medicare_combined_rate",
                   constants_used={"medicare_combined_rate": str(self.constants.medicare_combined_rate)})

        # Total SE tax
        total_se = ss_tax + medicare_tax
        self.trace(FORM, "12", "Total SE tax", total_se,
                   "ss_tax + medicare_tax")

        # Deductible half
        half = (total_se / 2).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.trace(FORM, "13", "Deductible half of SE tax", half,
                   "total_se / 2", irs_citation="IRC §164(f)")

        return self.build_result(FORM, total_se)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_schedule_se.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/schedule_se.py tests/api/tax_engine/calculators/test_schedule_se.py
git commit -m "feat(tax_engine): add Schedule SE calculator — self-employment tax with SS wage cap"
```

---

## Task 12: Form 8959 (Additional Medicare) + Form 8960 (NIIT)

**Files:**
- Create: `api/tax_engine/calculators/form_8959.py`
- Create: `api/tax_engine/calculators/form_8960.py`
- Create: `tests/api/tax_engine/calculators/test_form_8959.py`
- Create: `tests/api/tax_engine/calculators/test_form_8960.py`

- [ ] **Step 1: Write failing tests for Form 8959**

Create `tests/api/tax_engine/calculators/test_form_8959.py`:

```python
"""Tests for Form 8959 — Additional Medicare Tax."""
from decimal import Decimal

from api.tax_engine.models.income import W2


class TestForm8959:
    def test_above_threshold_single(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator

        minimal_return.w2s = [
            W2(employer_name="Acme", employer_ein="12-3456789",
               box5_medicare_wages=Decimal("250000"),
               box6_medicare_withheld=Decimal("3625")),
        ]
        calc = Form8959Calculator(constants_2024)
        result = calc.compute(minimal_return, {})
        # Excess = 250000 - 200000 = 50000
        # Tax = 50000 * 0.009 = 450
        assert result.lines["18"].value == Decimal("450")

    def test_below_threshold(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator

        minimal_return.w2s = [
            W2(employer_name="Acme", employer_ein="12-3456789",
               box5_medicare_wages=Decimal("150000")),
        ]
        calc = Form8959Calculator(constants_2024)
        result = calc.compute(minimal_return, {})
        assert result.lines["18"].value == Decimal("0")

    def test_mfj_threshold(self, mfj_return, constants_2024):
        from api.tax_engine.calculators.form_8959 import Form8959Calculator

        mfj_return.w2s = [
            W2(employer_name="Acme", employer_ein="12-3456789",
               box5_medicare_wages=Decimal("300000"), person_role="primary"),
        ]
        calc = Form8959Calculator(constants_2024)
        result = calc.compute(mfj_return, {})
        # MFJ threshold = 250000, excess = 50000, tax = 450
        assert result.lines["18"].value == Decimal("450")
```

- [ ] **Step 2: Write failing tests for Form 8960**

Create `tests/api/tax_engine/calculators/test_form_8960.py`:

```python
"""Tests for Form 8960 — Net Investment Income Tax."""
from decimal import Decimal

from api.tax_engine.models.tax_return import FormResult, LineTrace


def _agi_result(agi: Decimal) -> dict[str, FormResult]:
    return {
        "AGI": FormResult(
            form_name="AGI", total=agi,
            lines={"11": LineTrace(form="1040", line="11", label="AGI",
                                   value=agi, formula="test")},
        ),
        "Schedule B": FormResult(form_name="Schedule B", total=Decimal("5000"),
            lines={"4": LineTrace(form="Schedule B", line="4", label="Interest",
                                  value=Decimal("3000"), formula="test"),
                   "6": LineTrace(form="Schedule B", line="6", label="Dividends",
                                  value=Decimal("2000"), formula="test")}),
    }


class TestForm8960:
    def test_above_threshold_single(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator

        calc = Form8960Calculator(constants_2024)
        prior = _agi_result(Decimal("250000"))
        result = calc.compute(minimal_return, prior)
        # NII = 5000 (from Schedule B)
        # Excess MAGI = 250000 - 200000 = 50000
        # Tax = min(5000, 50000) * 0.038 = 190
        assert result.lines["17"].value == Decimal("190.00")

    def test_below_threshold(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator

        calc = Form8960Calculator(constants_2024)
        prior = _agi_result(Decimal("150000"))
        result = calc.compute(minimal_return, prior)
        assert result.lines["17"].value == Decimal("0")

    def test_nii_less_than_excess(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8960 import Form8960Calculator

        calc = Form8960Calculator(constants_2024)
        prior = _agi_result(Decimal("300000"))
        result = calc.compute(minimal_return, prior)
        # NII = 5000, excess = 100000, tax = min(5000, 100000) * 0.038 = 190
        assert result.lines["17"].value == Decimal("190.00")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8959.py tests/api/tax_engine/calculators/test_form_8960.py -v`
Expected: FAIL

- [ ] **Step 4: Implement form_8959.py**

Create `api/tax_engine/calculators/form_8959.py`:

```python
"""Form 8959 — Additional Medicare Tax (0.9% on wages above threshold)."""
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8959"


class Form8959Calculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.additional_medicare_threshold[fs]

        # Total Medicare wages (W-2 box 5 + SE income)
        w2_medicare = sum((w.box5_medicare_wages for w in tax_return.w2s), Decimal("0"))

        sched_se = prior_results.get("Schedule SE")
        se_income = Decimal("0")
        if sched_se and "4a" in sched_se.lines:
            se_income = sched_se.lines["4a"].value

        total_medicare_wages = w2_medicare + se_income

        excess = max(Decimal("0"), total_medicare_wages - threshold)
        tax = (excess * self.constants.additional_medicare_rate).quantize(
            Decimal("0.01"), ROUND_HALF_UP)

        self.trace(FORM, "18", "Additional Medicare tax", tax,
                   "max(0, total_wages - threshold) * 0.9%",
                   inputs={"total_wages": str(total_medicare_wages),
                           "threshold": str(threshold)},
                   constants_used={"rate": str(self.constants.additional_medicare_rate)},
                   irs_citation="IRC §3101(b)(2)")

        return self.build_result(FORM, tax)
```

- [ ] **Step 5: Implement form_8960.py**

Create `api/tax_engine/calculators/form_8960.py`:

```python
"""Form 8960 — Net Investment Income Tax (3.8% NIIT)."""
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8960"


class Form8960Calculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.niit_threshold[fs]

        # AGI
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")

        # Net investment income: interest + dividends + capital gains + rental
        nii = Decimal("0")
        sched_b = prior_results.get("Schedule B")
        if sched_b:
            nii += sched_b.total
        sched_d = prior_results.get("Schedule D")
        if sched_d and sched_d.total > Decimal("0"):
            nii += sched_d.total
        sched_e = prior_results.get("Schedule E")
        if sched_e:
            # Only rental income portion (not active K-1 business)
            for line_key, lt in sched_e.lines.items():
                if line_key.startswith("26"):
                    nii += lt.value

        self.trace(FORM, "8", "Net investment income", nii,
                   "interest + dividends + cap_gains + rental")

        excess_magi = max(Decimal("0"), agi - threshold)
        taxable = min(nii, excess_magi)
        tax = (taxable * self.constants.niit_rate).quantize(
            Decimal("0.01"), ROUND_HALF_UP)

        self.trace(FORM, "17", "Net investment income tax", tax,
                   "min(NII, MAGI - threshold) * 3.8%",
                   inputs={"nii": str(nii), "magi": str(agi),
                           "threshold": str(threshold)},
                   constants_used={"niit_rate": str(self.constants.niit_rate)},
                   irs_citation="IRC §1411")

        return self.build_result(FORM, tax)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8959.py tests/api/tax_engine/calculators/test_form_8960.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/tax_engine/calculators/form_8959.py api/tax_engine/calculators/form_8960.py \
  tests/api/tax_engine/calculators/test_form_8959.py tests/api/tax_engine/calculators/test_form_8960.py
git commit -m "feat(tax_engine): add Form 8959 (Additional Medicare) and Form 8960 (NIIT)"
```

---

## Task 13: Form 8995 Calculator (QBI Deduction)

**Files:**
- Create: `api/tax_engine/calculators/form_8995.py`
- Create: `tests/api/tax_engine/calculators/test_form_8995.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_form_8995.py`:

```python
"""Tests for Form 8995 / 8995-A — Qualified Business Income Deduction."""
from decimal import Decimal

from api.tax_engine.models.income import ScheduleC, ScheduleK1
from api.tax_engine.models.tax_return import FormResult, LineTrace


def _taxable_income_result(ti: Decimal) -> dict[str, FormResult]:
    return {
        "taxable_income_before_qbi": FormResult(
            form_name="pre-QBI", total=ti,
            lines={"15": LineTrace(form="1040", line="15", label="Taxable income pre-QBI",
                                   value=ti, formula="test")},
        )
    }


class TestForm8995Simple:
    """Below-threshold: simple 20% deduction."""

    def test_simple_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Consulting", gross_receipts=Decimal("100000")),
        ]
        calc = Form8995Calculator(constants_2024)
        prior = _taxable_income_result(Decimal("85400"))
        result = calc.compute(minimal_return, prior)
        # QBI = 100000, deduction = 20% = 20000
        # Cap at 20% of taxable income = 85400 * 0.2 = 17080
        assert result.lines["15"].value == Decimal("17080")

    def test_uncapped_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Consulting", gross_receipts=Decimal("50000")),
        ]
        calc = Form8995Calculator(constants_2024)
        prior = _taxable_income_result(Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # QBI = 50000, 20% = 10000
        # Cap = 20% of 100000 = 20000
        # Deduction = min(10000, 20000) = 10000
        assert result.lines["15"].value == Decimal("10000")


class TestForm8995Complex:
    """Above-threshold: W-2 wage limitation applies."""

    def test_wage_limited(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Big Biz", gross_receipts=Decimal("500000"),
                      w2_wages_paid=Decimal("100000"), ubia_qualified_property=Decimal("0")),
        ]
        calc = Form8995Calculator(constants_2024)
        # Single threshold = 191950, this is well above
        prior = _taxable_income_result(Decimal("500000"))
        result = calc.compute(minimal_return, prior)
        # QBI = 500000, tentative 20% = 100000
        # Wage limit = max(50% * 100000, 25% * 100000 + 2.5% * 0) = 50000
        # Deduction = min(50000, 20% of taxable_income = 100000) = 50000
        assert result.lines["15"].value == Decimal("50000")


class TestForm8995SSTB:
    """SSTB phase-out in the phase-in range."""

    def test_sstb_fully_phased_out(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator

        minimal_return.schedule_cs = [
            ScheduleC(business_name="Law Firm", gross_receipts=Decimal("500000"),
                      is_sstb=True, w2_wages_paid=Decimal("200000")),
        ]
        calc = Form8995Calculator(constants_2024)
        # Single threshold = 191950, upper = 241950
        # Taxable income 300000 > 241950 → SSTB fully phased out
        prior = _taxable_income_result(Decimal("300000"))
        result = calc.compute(minimal_return, prior)
        assert result.lines["15"].value == Decimal("0")


class TestForm8995K1:
    def test_k1_qbi(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8995 import Form8995Calculator

        minimal_return.k1s = [
            ScheduleK1(entity_name="XYZ", entity_ein="11-2222222",
                       entity_type="S", box20z_section_199a_qbi=Decimal("80000"),
                       w2_wages_for_qbi=Decimal("50000")),
        ]
        calc = Form8995Calculator(constants_2024)
        prior = _taxable_income_result(Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # Below threshold, simple: 20% of 80000 = 16000
        assert result.lines["15"].value == Decimal("16000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8995.py -v`
Expected: FAIL

- [ ] **Step 3: Implement form_8995.py**

Create `api/tax_engine/calculators/form_8995.py`:

```python
"""Form 8995 / 8995-A — Qualified Business Income Deduction (§199A)."""
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Form 8995"


class Form8995Calculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        fs = tax_return.filing_status
        threshold = self.constants.qbi_threshold[fs]
        phase_in = self.constants.qbi_phase_in_range[fs]
        upper_limit = threshold + phase_in
        rate = self.constants.qbi_deduction_rate

        # Get taxable income before QBI
        ti_result = prior_results.get("taxable_income_before_qbi")
        taxable_income = ti_result.total if ti_result else Decimal("0")

        # Gather QBI sources
        qbi_items: list[dict] = []
        for sc in tax_return.schedule_cs:
            qbi_items.append({
                "name": sc.business_name,
                "qbi": sc.net_profit,
                "w2_wages": sc.w2_wages_paid,
                "ubia": sc.ubia_qualified_property,
                "is_sstb": sc.is_sstb,
            })
        for k1 in tax_return.k1s:
            if k1.box20z_section_199a_qbi != Decimal("0"):
                qbi_items.append({
                    "name": k1.entity_name,
                    "qbi": k1.box20z_section_199a_qbi,
                    "w2_wages": k1.w2_wages_for_qbi,
                    "ubia": k1.ubia_qualified_property,
                    "is_sstb": k1.is_sstb,
                })

        if not qbi_items:
            self.trace(FORM, "15", "QBI deduction", Decimal("0"), "no QBI sources")
            return self.build_result(FORM, Decimal("0"))

        total_deduction = Decimal("0")
        for item in qbi_items:
            qbi = item["qbi"]
            tentative = qbi * rate

            if taxable_income <= threshold:
                # Simple path: 20% of QBI
                deduction = tentative
            elif taxable_income >= upper_limit:
                # Fully above phase-in
                if item["is_sstb"]:
                    deduction = Decimal("0")
                else:
                    # W-2 wage limit
                    w2_limit = max(
                        item["w2_wages"] * Decimal("0.50"),
                        item["w2_wages"] * Decimal("0.25") + item["ubia"] * Decimal("0.025"),
                    )
                    deduction = min(tentative, w2_limit)
            else:
                # Phase-in range
                if item["is_sstb"]:
                    applicable_pct = Decimal("1") - (taxable_income - threshold) / phase_in
                    adj_qbi = qbi * applicable_pct
                    adj_wages = item["w2_wages"] * applicable_pct
                    adj_ubia = item["ubia"] * applicable_pct
                    tentative = adj_qbi * rate
                    w2_limit = max(
                        adj_wages * Decimal("0.50"),
                        adj_wages * Decimal("0.25") + adj_ubia * Decimal("0.025"),
                    )
                    deduction = min(tentative, w2_limit)
                else:
                    w2_limit = max(
                        item["w2_wages"] * Decimal("0.50"),
                        item["w2_wages"] * Decimal("0.25") + item["ubia"] * Decimal("0.025"),
                    )
                    reduction_pct = (taxable_income - threshold) / phase_in
                    reduction = (tentative - w2_limit) * reduction_pct
                    deduction = tentative - max(Decimal("0"), reduction)

            total_deduction += max(Decimal("0"), deduction)

        # Cap at 20% of taxable income
        ti_cap = (taxable_income * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        final = min(total_deduction, ti_cap).quantize(Decimal("0.01"), ROUND_HALF_UP)

        self.trace(FORM, "15", "QBI deduction", final,
                   "min(sum_qbi_deductions, 20% * taxable_income)",
                   inputs={"total_qbi_deduction": str(total_deduction),
                           "ti_cap": str(ti_cap)},
                   constants_used={"qbi_rate": str(rate),
                                   "threshold": str(threshold)},
                   irs_citation="IRC §199A")

        return self.build_result(FORM, final)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8995.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/form_8995.py tests/api/tax_engine/calculators/test_form_8995.py
git commit -m "feat(tax_engine): add Form 8995 calculator — QBI deduction with SSTB phase-out"
```

---

## Task 14: Form 8812 Calculator (Child Tax Credit)

**Files:**
- Create: `api/tax_engine/calculators/form_8812.py`
- Create: `tests/api/tax_engine/calculators/test_form_8812.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/calculators/test_form_8812.py`:

```python
"""Tests for Form 8812 — Child Tax Credit / ACTC."""
from datetime import date
from decimal import Decimal

from api.tax_engine.models.people import Dependent
from api.tax_engine.models.tax_return import FormResult, LineTrace


def _tax_result(agi: Decimal, tax: Decimal, earned: Decimal) -> dict[str, FormResult]:
    return {
        "AGI": FormResult(form_name="AGI", total=agi,
            lines={"11": LineTrace(form="1040", line="11", label="AGI",
                                   value=agi, formula="test")}),
        "tax_before_credits": FormResult(form_name="tax", total=tax,
            lines={"16": LineTrace(form="1040", line="16", label="Tax",
                                   value=tax, formula="test")}),
        "earned_income": FormResult(form_name="earned", total=earned,
            lines={"earned": LineTrace(form="1040", line="earned", label="Earned income",
                                       value=earned, formula="test")}),
    }


class TestForm8812:
    def test_two_children_2024(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator

        minimal_return.dependents = [
            Dependent(first_name="A", last_name="Doe", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
            Dependent(first_name="B", last_name="Doe", ssn="444556666",
                      relationship="daughter", date_of_birth=date(2018, 6, 1)),
        ]
        calc = Form8812Calculator(constants_2024)
        prior = _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # 2 kids * $2000 = $4000, no phase-out (AGI < 200000)
        assert result.lines["nonrefundable"].value == Decimal("4000")

    def test_phase_out_single(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator

        minimal_return.dependents = [
            Dependent(first_name="A", last_name="Doe", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
        ]
        calc = Form8812Calculator(constants_2024)
        prior = _tax_result(Decimal("210000"), Decimal("30000"), Decimal("210000"))
        result = calc.compute(minimal_return, prior)
        # 1 kid * $2000 = $2000
        # Excess = 210000 - 200000 = 10000, rounded up to next 1000 = 10000
        # Phase-out = 10 * $50 = $500
        # Credit = 2000 - 500 = 1500
        assert result.lines["nonrefundable"].value == Decimal("1500")

    def test_other_dependent(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator

        minimal_return.dependents = [
            Dependent(first_name="A", last_name="Doe", ssn="111223333",
                      relationship="parent", date_of_birth=date(1955, 1, 1),
                      is_qualifying_child=False),
        ]
        calc = Form8812Calculator(constants_2024)
        prior = _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        assert result.lines["other_dependent"].value == Decimal("500")

    def test_no_dependents(self, minimal_return, constants_2024):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator

        calc = Form8812Calculator(constants_2024)
        prior = _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        assert result.total == Decimal("0")

    def test_2025_increased_amount(self, minimal_return, constants_2025):
        from api.tax_engine.calculators.form_8812 import Form8812Calculator

        minimal_return.tax_year = 2025
        minimal_return.dependents = [
            Dependent(first_name="A", last_name="Doe", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
        ]
        calc = Form8812Calculator(constants_2025)
        prior = _tax_result(Decimal("100000"), Decimal("10000"), Decimal("100000"))
        result = calc.compute(minimal_return, prior)
        # 2025: $2200 per child
        assert result.lines["nonrefundable"].value == Decimal("2200")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8812.py -v`
Expected: FAIL

- [ ] **Step 3: Implement form_8812.py**

Create `api/tax_engine/calculators/form_8812.py`:

```python
"""Form 8812 / Schedule 8812 — Child Tax Credit and ACTC."""
import math
from datetime import date
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "Schedule 8812"


class Form8812Calculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        fs = tax_return.filing_status
        tax_year = tax_return.tax_year

        # Classify dependents
        qualifying_children = 0
        other_dependents = 0
        age_cutoff = date(tax_year - 16, 1, 1)  # Must be born after this date to be under 17

        for dep in tax_return.dependents:
            if dep.is_qualifying_child and dep.date_of_birth > age_cutoff:
                qualifying_children += 1
            else:
                other_dependents += 1

        if qualifying_children == 0 and other_dependents == 0:
            self.trace(FORM, "nonrefundable", "CTC (nonrefundable)", Decimal("0"),
                       "no dependents")
            self.trace(FORM, "other_dependent", "Other dependent credit", Decimal("0"),
                       "no dependents")
            return self.build_result(FORM, Decimal("0"))

        # Gross credits
        ctc_gross = Decimal(qualifying_children) * self.constants.ctc_amount_per_child
        odc_gross = Decimal(other_dependents) * self.constants.ctc_other_dependent
        total_gross = ctc_gross + odc_gross

        # Phase-out
        threshold = self.constants.ctc_phase_out[fs]
        agi_result = prior_results.get("AGI")
        agi = agi_result.total if agi_result else Decimal("0")

        if agi > threshold:
            excess = agi - threshold
            # Round up to next $1,000
            excess_thousands = math.ceil(int(excess) / 1000)
            phase_out = Decimal(excess_thousands) * Decimal("50")
        else:
            phase_out = Decimal("0")

        credit_after_phase_out = max(Decimal("0"), total_gross - phase_out)

        # Split back into CTC and ODC (phase-out reduces proportionally)
        if total_gross > Decimal("0"):
            ctc_share = ctc_gross / total_gross
            nonrefundable_ctc = (credit_after_phase_out * ctc_share).quantize(Decimal("1"))
            other_dep_credit = credit_after_phase_out - nonrefundable_ctc
        else:
            nonrefundable_ctc = Decimal("0")
            other_dep_credit = Decimal("0")

        # CTC nonrefundable portion capped at tax liability
        tax_result = prior_results.get("tax_before_credits")
        tax_liability = tax_result.total if tax_result else Decimal("0")
        nonrefundable_ctc = min(nonrefundable_ctc, tax_liability)

        self.trace(FORM, "nonrefundable", "CTC (nonrefundable)", nonrefundable_ctc,
                   "min(ctc_after_phaseout, tax_liability)",
                   inputs={"qualifying_children": str(qualifying_children),
                           "gross_ctc": str(ctc_gross), "phase_out": str(phase_out)},
                   constants_used={"per_child": str(self.constants.ctc_amount_per_child)})

        self.trace(FORM, "other_dependent", "Other dependent credit", other_dep_credit,
                   "other_dependents * 500 (after phase-out)",
                   inputs={"other_dependents": str(other_dependents)},
                   constants_used={"per_dependent": str(self.constants.ctc_other_dependent)})

        # ACTC (refundable) — 15% of earned income over $2,500, capped
        earned_result = prior_results.get("earned_income")
        earned = earned_result.total if earned_result else Decimal("0")
        remaining_ctc = max(Decimal("0"), ctc_gross - phase_out - nonrefundable_ctc)
        actc_max = Decimal(qualifying_children) * self.constants.ctc_refundable_max_per_child
        actc_earned = max(Decimal("0"),
                         (earned - self.constants.ctc_earned_income_threshold) * Decimal("0.15"))
        actc = min(remaining_ctc, actc_max, actc_earned)

        self.trace(FORM, "refundable", "ACTC (refundable)", actc,
                   "min(remaining_ctc, max_per_child * kids, 15% * (earned - 2500))",
                   inputs={"remaining_ctc": str(remaining_ctc),
                           "earned_income": str(earned)},
                   constants_used={"refundable_max": str(self.constants.ctc_refundable_max_per_child)})

        total = nonrefundable_ctc + other_dep_credit + actc
        return self.build_result(FORM, total)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/tax_engine/calculators/test_form_8812.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/form_8812.py tests/api/tax_engine/calculators/test_form_8812.py
git commit -m "feat(tax_engine): add Form 8812 calculator — CTC with phase-out and ACTC"
```

---

## Task 15: Form 1040 Calculator + Services Layer

**Files:**
- Create: `api/tax_engine/calculators/form_1040.py`
- Create: `api/tax_engine/services/__init__.py`
- Create: `api/tax_engine/services/income.py`
- Create: `api/tax_engine/services/deductions.py`
- Create: `api/tax_engine/services/credits.py`
- Create: `api/tax_engine/services/liability.py`
- Create: `api/tax_engine/services/engine.py`
- Create: `tests/api/tax_engine/calculators/test_form_1040.py`
- Create: `tests/api/tax_engine/test_engine.py`

- [ ] **Step 1: Write failing end-to-end test**

Create `tests/api/tax_engine/test_engine.py`:

```python
"""End-to-end test: TaxReturn → TaxCalculationEngine → TaxResult."""
from datetime import date
from decimal import Decimal

from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, Income1099Int
from api.tax_engine.models.tax_return import TaxReturn


class TestTaxCalculationEngine:
    def test_simple_w2_single(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine

        tr = TaxReturn(
            tax_year=2024, filing_status="S",
            primary=Person(first_name="John", last_name="Doe",
                           ssn="123456789", date_of_birth=date(1985, 1, 1)),
            address=Address(street="123 Main", city="Springfield",
                            state="IL", zip_code="62701"),
            w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                     box1_wages=Decimal("85000"),
                     box2_fed_withheld=Decimal("15000"),
                     box3_ss_wages=Decimal("85000"),
                     box5_medicare_wages=Decimal("85000"))],
        )
        engine = TaxCalculationEngine(constants_2024)
        result = engine.compute(tr)

        assert result.tax_year == 2024
        assert result.filing_status == "S"
        assert result.total_income == Decimal("85000")
        # Standard deduction for single 2024 = 14600
        assert result.taxable_income == Decimal("70400")
        assert result.total_tax > Decimal("0")
        assert result.total_payments == Decimal("15000")
        assert len(result.all_traces) > 0

    def test_mfj_with_children_and_interest(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine

        tr = TaxReturn(
            tax_year=2024, filing_status="MFJ",
            primary=Person(first_name="John", last_name="Doe",
                           ssn="123456789", date_of_birth=date(1985, 1, 1)),
            spouse=Person(first_name="Jane", last_name="Doe",
                          ssn="987654321", date_of_birth=date(1987, 5, 10)),
            address=Address(street="123 Main", city="Springfield",
                            state="IL", zip_code="62701"),
            dependents=[
                Dependent(first_name="Kid", last_name="Doe", ssn="111223333",
                          relationship="son", date_of_birth=date(2015, 6, 1)),
            ],
            w2s=[
                W2(employer_name="Acme", employer_ein="12-3456789",
                   box1_wages=Decimal("120000"), box2_fed_withheld=Decimal("20000"),
                   box3_ss_wages=Decimal("120000"), box5_medicare_wages=Decimal("120000"),
                   person_role="primary"),
                W2(employer_name="Beta Inc", employer_ein="98-7654321",
                   box1_wages=Decimal("65000"), box2_fed_withheld=Decimal("10000"),
                   box3_ss_wages=Decimal("65000"), box5_medicare_wages=Decimal("65000"),
                   person_role="spouse"),
            ],
            interest_1099s=[
                Income1099Int(payer="Chase", box1_interest=Decimal("3800")),
            ],
        )
        engine = TaxCalculationEngine(constants_2024)
        result = engine.compute(tr)

        assert result.total_income == Decimal("188800")  # 120000 + 65000 + 3800
        # Standard deduction MFJ 2024 = 29200
        assert result.taxable_income == Decimal("159600")
        assert result.total_credits >= Decimal("2000")  # At least CTC
        assert result.total_payments == Decimal("30000")

    def test_zero_income(self, constants_2024):
        from api.tax_engine.services.engine import TaxCalculationEngine

        tr = TaxReturn(
            tax_year=2024, filing_status="S",
            primary=Person(first_name="John", last_name="Doe",
                           ssn="123456789", date_of_birth=date(1985, 1, 1)),
            address=Address(street="123 Main", city="Springfield",
                            state="IL", zip_code="62701"),
        )
        engine = TaxCalculationEngine(constants_2024)
        result = engine.compute(tr)

        assert result.total_income == Decimal("0")
        assert result.total_tax == Decimal("0")
        assert result.refund_or_owed == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement services layer and Form 1040**

Create `api/tax_engine/services/__init__.py`:

```python
"""Tax engine services package."""
```

Create `api/tax_engine/services/income.py`:

```python
"""IncomeService — orchestrates income calculators."""
from api.tax_engine.calculators.schedule_b import ScheduleBCalculator
from api.tax_engine.calculators.schedule_c import ScheduleCCalculator
from api.tax_engine.calculators.schedule_d import ScheduleDCalculator
from api.tax_engine.calculators.schedule_e import ScheduleECalculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, TaxReturn


class IncomeService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}
        out["Schedule B"] = ScheduleBCalculator(self.constants).compute(tax_return, results)
        out["Schedule C"] = ScheduleCCalculator(self.constants).compute(tax_return, results)
        out["Schedule D"] = ScheduleDCalculator(self.constants).compute(tax_return, results)
        out["Schedule E"] = ScheduleECalculator(self.constants).compute(tax_return, results)
        return out
```

Create `api/tax_engine/services/liability.py`:

```python
"""LiabilityService — tax brackets, SE tax, surtaxes."""
from decimal import Decimal, ROUND_HALF_UP

from api.tax_engine.calculators.schedule_se import ScheduleSECalculator
from api.tax_engine.calculators.form_8959 import Form8959Calculator
from api.tax_engine.calculators.form_8960 import Form8960Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn


class LiabilityService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def _compute_ordinary_tax(self, taxable_income: Decimal, filing_status: str) -> Decimal:
        """Apply progressive tax brackets."""
        brackets = self.constants.ordinary_brackets[filing_status]
        tax = Decimal("0")
        prev_upper = Decimal("0")
        for upper, rate in brackets:
            if taxable_income <= prev_upper:
                break
            width = min(taxable_income, upper) - prev_upper
            tax += width * rate
            prev_upper = upper
        return tax.quantize(Decimal("0.01"), ROUND_HALF_UP)

    def compute(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}

        # Schedule SE
        se_result = ScheduleSECalculator(self.constants).compute(tax_return, results)
        out["Schedule SE"] = se_result

        # Ordinary tax on taxable income
        ti_result = results.get("taxable_income_before_qbi")
        qbi_result = results.get("Form 8995")
        ti = ti_result.total if ti_result else Decimal("0")
        qbi_ded = qbi_result.total if qbi_result else Decimal("0")
        taxable_income = max(Decimal("0"), ti - qbi_ded)

        ordinary_tax = self._compute_ordinary_tax(taxable_income, tax_return.filing_status)
        traces = [
            LineTrace(form="1040", line="16", label="Tax",
                      value=ordinary_tax,
                      formula="progressive_brackets(taxable_income)",
                      inputs={"taxable_income": str(taxable_income)}),
        ]
        out["ordinary_tax"] = FormResult(
            form_name="ordinary_tax",
            lines={t.line: t for t in traces},
            total=ordinary_tax,
        )

        # Form 8959 — Additional Medicare
        merged = {**results, **out}
        out["Form 8959"] = Form8959Calculator(self.constants).compute(tax_return, merged)

        # Form 8960 — NIIT
        out["Form 8960"] = Form8960Calculator(self.constants).compute(tax_return, merged)

        return out
```

Create `api/tax_engine/services/deductions.py`:

```python
"""DeductionService — adjustments, standard vs itemized, QBI."""
from decimal import Decimal

from api.tax_engine.calculators.schedule_a import ScheduleACalculator
from api.tax_engine.calculators.form_8995 import Form8995Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, LineTrace, TaxReturn


class DeductionService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute_adjustments(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> dict[str, FormResult]:
        """Above-the-line adjustments: SE deduction, HSA, student loan, educator."""
        adjustments = Decimal("0")
        traces: list[LineTrace] = []

        # Deductible half of SE tax
        se_result = results.get("Schedule SE")
        if se_result and "13" in se_result.lines:
            se_ded = se_result.lines["13"].value
            adjustments += se_ded
            traces.append(LineTrace(form="Schedule 1", line="15",
                                    label="Deductible half of SE tax",
                                    value=se_ded, formula="SE tax / 2"))

        # HSA deduction
        for hsa in tax_return.hsas:
            limit = self.constants.hsa_limit[hsa.coverage_type]
            ded = min(hsa.employee_contributions, limit - hsa.employer_contributions)
            ded = max(Decimal("0"), ded)
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="13",
                                    label="HSA deduction", value=ded,
                                    formula="min(employee, limit - employer)"))

        # Student loan interest
        for sl in tax_return.student_loans:
            ded = min(sl.box1_interest_paid, self.constants.student_loan_max_deduction)
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="21",
                                    label="Student loan interest", value=ded,
                                    formula="min(interest, max_deduction)"))

        # Educator expenses
        if tax_return.educator_expenses > Decimal("0"):
            ded = min(tax_return.educator_expenses, Decimal("300"))
            adjustments += ded
            traces.append(LineTrace(form="Schedule 1", line="11",
                                    label="Educator expenses", value=ded,
                                    formula="min(expenses, 300)"))

        # Compute AGI
        income_total = Decimal("0")
        for key in ["Schedule B", "Schedule C", "Schedule D", "Schedule E"]:
            r = results.get(key)
            if r:
                income_total += r.total

        # W-2 wages
        wages = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        income_total += wages

        # 1099-NEC
        nec = sum((n.nec_compensation for n in tax_return.nec_1099s), Decimal("0"))
        income_total += nec

        # 1099-R taxable
        retirement = sum((r.box2a_taxable_amount for r in tax_return.retirement_1099rs), Decimal("0"))
        income_total += retirement

        # SSA (simplified — use 85% as default taxable portion)
        ssa = sum((s.box5_net_benefits for s in tax_return.ssa_1099s), Decimal("0"))
        ssa_taxable = (ssa * Decimal("0.85")).quantize(Decimal("0.01"))
        income_total += ssa_taxable

        agi = income_total - adjustments

        out: dict[str, FormResult] = {}
        out["adjustments"] = FormResult(
            form_name="adjustments",
            lines={t.line: t for t in traces},
            total=adjustments,
        )
        out["total_income"] = FormResult(
            form_name="total_income", total=income_total,
            lines={"9": LineTrace(form="1040", line="9", label="Total income",
                                  value=income_total, formula="wages + interest + div + cap_gains + se + rental + nec + retirement + ssa")},
        )
        out["earned_income"] = FormResult(
            form_name="earned_income", total=wages + nec + max(Decimal("0"), sum(sc.net_profit for sc in tax_return.schedule_cs)),
            lines={"earned": LineTrace(form="1040", line="earned", label="Earned income",
                                       value=wages + nec, formula="wages + nec")},
        )
        out["AGI"] = FormResult(
            form_name="AGI", total=agi,
            lines={"11": LineTrace(form="1040", line="11", label="Adjusted gross income",
                                   value=agi, formula="total_income - adjustments",
                                   inputs={"total_income": str(income_total),
                                           "adjustments": str(adjustments)})},
        )
        return out

    def compute_deductions(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> dict[str, FormResult]:
        """Below-the-line: standard vs itemized, QBI."""
        out: dict[str, FormResult] = {}
        fs = tax_return.filing_status
        agi = results.get("AGI")
        agi_val = agi.total if agi else Decimal("0")

        # Schedule A
        sched_a = ScheduleACalculator(self.constants).compute(tax_return, results)
        out["Schedule A"] = sched_a

        # Standard vs itemized
        standard = self.constants.standard_deduction[fs]
        deduction = max(standard, sched_a.total)
        used_standard = deduction == standard

        out["deduction"] = FormResult(
            form_name="deduction", total=deduction,
            lines={"12": LineTrace(form="1040", line="12",
                                   label="Standard deduction" if used_standard else "Itemized deductions",
                                   value=deduction,
                                   formula="max(standard, itemized)",
                                   inputs={"standard": str(standard), "itemized": str(sched_a.total)})},
        )

        # Taxable income before QBI
        ti_before_qbi = max(Decimal("0"), agi_val - deduction)
        out["taxable_income_before_qbi"] = FormResult(
            form_name="pre-QBI", total=ti_before_qbi,
            lines={"15": LineTrace(form="1040", line="15",
                                   label="Taxable income (before QBI)",
                                   value=ti_before_qbi, formula="AGI - deduction")},
        )

        # QBI
        merged = {**results, **out}
        qbi_result = Form8995Calculator(self.constants).compute(tax_return, merged)
        out["Form 8995"] = qbi_result

        return out
```

Create `api/tax_engine/services/credits.py`:

```python
"""CreditService — child tax credit, education, energy."""
from decimal import Decimal

from api.tax_engine.calculators.form_8812 import Form8812Calculator
from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.models.tax_return import FormResult, TaxReturn


class CreditService:
    def __init__(self, constants: TaxYearConstants):
        self.constants = constants

    def compute(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> dict[str, FormResult]:
        out: dict[str, FormResult] = {}

        # Form 8812 — Child Tax Credit
        ctc_result = Form8812Calculator(self.constants).compute(tax_return, results)
        out["Schedule 8812"] = ctc_result

        return out
```

Create `api/tax_engine/calculators/form_1040.py`:

```python
"""Form 1040 — Final assembly of all form results into lines 1–37."""
from decimal import Decimal

from api.tax_engine.calculators.base import BaseCalculator
from api.tax_engine.models.tax_return import FormResult, TaxReturn

FORM = "1040"


class Form1040Calculator(BaseCalculator):
    def compute(
        self, tax_return: TaxReturn, prior_results: dict[str, FormResult]
    ) -> FormResult:
        # Line 1: Wages
        wages = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        self.trace(FORM, "1a", "Total wages", wages, "sum(W-2 box 1)")

        # Line 2b: Taxable interest
        sched_b = prior_results.get("Schedule B")
        interest = sched_b.lines.get("4", None)
        interest_val = interest.value if interest else Decimal("0")
        self.trace(FORM, "2b", "Taxable interest", interest_val, "Schedule B line 4")

        # Line 3: Dividends
        div_val = Decimal("0")
        if sched_b and "6" in sched_b.lines:
            div_val = sched_b.lines["6"].value
        self.trace(FORM, "3b", "Ordinary dividends", div_val, "Schedule B line 6")

        # Line 7: Capital gain/loss
        sched_d = prior_results.get("Schedule D")
        cap_gain = sched_d.total if sched_d else Decimal("0")
        self.trace(FORM, "7", "Capital gain or loss", cap_gain, "Schedule D line 21")

        # Line 8: Other income (Schedule C, E, 1099-NEC, etc.)
        sched_c = prior_results.get("Schedule C")
        sched_e = prior_results.get("Schedule E")
        other = Decimal("0")
        if sched_c:
            other += sched_c.total
        if sched_e:
            other += sched_e.total
        nec = sum((n.nec_compensation for n in tax_return.nec_1099s), Decimal("0"))
        other += nec
        retirement = sum((r.box2a_taxable_amount for r in tax_return.retirement_1099rs), Decimal("0"))
        other += retirement
        self.trace(FORM, "8", "Other income", other, "Schedule C + E + 1099-NEC + 1099-R")

        # Line 9: Total income
        total_income = prior_results.get("total_income")
        total_income_val = total_income.total if total_income else Decimal("0")
        self.trace(FORM, "9", "Total income", total_income_val, "sum of all income")

        # Line 10: Adjustments
        adj = prior_results.get("adjustments")
        adj_val = adj.total if adj else Decimal("0")
        self.trace(FORM, "10", "Adjustments to income", adj_val, "Schedule 1 adjustments")

        # Line 11: AGI
        agi = prior_results.get("AGI")
        agi_val = agi.total if agi else Decimal("0")
        self.trace(FORM, "11", "Adjusted gross income", agi_val, "line 9 - line 10")

        # Line 12: Deduction
        ded = prior_results.get("deduction")
        ded_val = ded.total if ded else Decimal("0")
        self.trace(FORM, "12", "Deduction", ded_val, "standard or itemized")

        # Line 13a: QBI deduction
        qbi = prior_results.get("Form 8995")
        qbi_val = qbi.total if qbi else Decimal("0")
        self.trace(FORM, "13a", "QBI deduction", qbi_val, "Form 8995 line 15")

        # Line 15: Taxable income
        taxable = max(Decimal("0"), agi_val - ded_val - qbi_val)
        self.trace(FORM, "15", "Taxable income", taxable, "AGI - deduction - QBI")

        # Line 16: Tax
        tax_result = prior_results.get("ordinary_tax")
        tax_val = tax_result.total if tax_result else Decimal("0")
        self.trace(FORM, "16", "Tax", tax_val, "from tax brackets")

        # Line 23: Other taxes (SE + additional Medicare + NIIT)
        se = prior_results.get("Schedule SE")
        se_val = se.total if se else Decimal("0")
        f8959 = prior_results.get("Form 8959")
        f8959_val = f8959.total if f8959 else Decimal("0")
        f8960 = prior_results.get("Form 8960")
        f8960_val = f8960.total if f8960 else Decimal("0")
        other_taxes = se_val + f8959_val + f8960_val
        self.trace(FORM, "23", "Other taxes", other_taxes,
                   "SE tax + additional Medicare + NIIT")

        # Line 24: Total tax
        ctc = prior_results.get("Schedule 8812")
        ctc_nonrefund = Decimal("0")
        if ctc and "nonrefundable" in ctc.lines:
            ctc_nonrefund = ctc.lines["nonrefundable"].value
        if ctc and "other_dependent" in ctc.lines:
            ctc_nonrefund += ctc.lines["other_dependent"].value

        total_tax = max(Decimal("0"), tax_val - ctc_nonrefund + other_taxes)
        self.trace(FORM, "24", "Total tax", total_tax,
                   "tax - credits + other_taxes")

        # Line 25: Withholding
        withholding = sum((w.box2_fed_withheld for w in tax_return.w2s), Decimal("0"))
        withholding += sum((f.box4_fed_withheld for f in tax_return.interest_1099s), Decimal("0"))
        withholding += sum((f.box4_fed_withheld for f in tax_return.retirement_1099rs), Decimal("0"))
        withholding += sum((f.fed_tax_withheld for f in tax_return.nec_1099s), Decimal("0"))
        self.trace(FORM, "25", "Federal tax withheld", withholding, "sum(W-2 box 2 + 1099 withholding)")

        # Line 26: Estimated payments
        est = sum((e.amount for e in tax_return.estimated_payments), Decimal("0"))
        self.trace(FORM, "26", "Estimated tax payments", est, "sum(estimated_payments)")

        # Refundable credits (ACTC)
        actc = Decimal("0")
        if ctc and "refundable" in ctc.lines:
            actc = ctc.lines["refundable"].value

        # Line 33: Total payments
        total_payments = withholding + est + actc
        self.trace(FORM, "33", "Total payments", total_payments,
                   "withholding + estimated + refundable_credits")

        # Line 34/37: Refund or amount owed
        refund_or_owed = total_payments - total_tax
        if refund_or_owed >= Decimal("0"):
            self.trace(FORM, "35a", "Refund", refund_or_owed,
                       "total_payments - total_tax")
        else:
            self.trace(FORM, "37", "Amount you owe", -refund_or_owed,
                       "total_tax - total_payments")

        return self.build_result(FORM, refund_or_owed)
```

Create `api/tax_engine/services/engine.py`:

```python
"""TaxCalculationEngine — top-level orchestrator."""
from decimal import Decimal

from api.tax_engine.constants.registry import TaxYearConstants
from api.tax_engine.calculators.form_1040 import Form1040Calculator
from api.tax_engine.models.tax_return import FormResult, TaxResult, TaxReturn
from api.tax_engine.services.income import IncomeService
from api.tax_engine.services.deductions import DeductionService
from api.tax_engine.services.credits import CreditService
from api.tax_engine.services.liability import LiabilityService


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

        # Phase 2: AGI adjustments (needs SE from liability, so run SE first)
        se_results = self.liability_service.compute(tax_return, results)
        # Only take Schedule SE for now, run other liability calcs later
        if "Schedule SE" in se_results:
            results["Schedule SE"] = se_results["Schedule SE"]

        results.update(self.deduction_service.compute_adjustments(tax_return, results))

        # Phase 3: Deductions (needs AGI)
        results.update(self.deduction_service.compute_deductions(tax_return, results))

        # Phase 4: Tax liability (needs taxable income)
        liability_results = self.liability_service.compute(tax_return, results)
        results.update(liability_results)

        # Phase 5: Credits (needs tax liability)
        # Build tax_before_credits from ordinary_tax
        ordinary_tax = results.get("ordinary_tax")
        if ordinary_tax:
            results["tax_before_credits"] = FormResult(
                form_name="tax", total=ordinary_tax.total,
                lines={"16": ordinary_tax.lines.get("16", None)},  # type: ignore
            )
        results.update(self.credit_service.compute(tax_return, results))

        # Phase 6: Final 1040 assembly
        form1040 = Form1040Calculator(self.constants)
        results["1040"] = form1040.compute(tax_return, results)

        return self._build_result(tax_return, results)

    def _build_result(
        self, tax_return: TaxReturn, results: dict[str, FormResult]
    ) -> TaxResult:
        f1040 = results.get("1040")
        all_traces = []
        for fr in results.values():
            all_traces.extend(fr.lines.values())

        def _line_val(line: str) -> Decimal:
            if f1040 and line in f1040.lines:
                return f1040.lines[line].value
            return Decimal("0")

        return TaxResult(
            tax_year=tax_return.tax_year,
            filing_status=tax_return.filing_status,
            form_results=results,
            total_income=_line_val("9"),
            agi=_line_val("11"),
            taxable_income=_line_val("15"),
            total_tax=_line_val("24"),
            total_credits=Decimal("0"),  # Sum all credits
            total_payments=_line_val("33"),
            refund_or_owed=f1040.total if f1040 else Decimal("0"),
            all_traces=all_traces,
        )
```

- [ ] **Step 4: Run end-to-end tests**

Run: `python -m pytest tests/api/tax_engine/test_engine.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/calculators/form_1040.py api/tax_engine/services/ tests/api/tax_engine/test_engine.py
git commit -m "feat(tax_engine): add Form 1040, services layer, and TaxCalculationEngine"
```

---

## Task 16: Validation Engine

**Files:**
- Create: `api/tax_engine/validation/__init__.py`
- Create: `api/tax_engine/validation/base.py`
- Create: `api/tax_engine/validation/rules.py`
- Create: `api/tax_engine/validation/engine.py`
- Create: `tests/api/tax_engine/test_validation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/test_validation.py`:

```python
"""Tests for validation rules and engine."""
from datetime import date
from decimal import Decimal

import pytest

from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, ScheduleK1
from api.tax_engine.models.deductions import HSA
from api.tax_engine.models.tax_return import TaxReturn


def _make_return(**kwargs) -> TaxReturn:
    defaults = dict(
        tax_year=2024, filing_status="S",
        primary=Person(first_name="John", last_name="Doe",
                        ssn="123456789", date_of_birth=date(1985, 1, 1)),
        address=Address(street="123 Main", city="Springfield",
                        state="IL", zip_code="62701"),
    )
    defaults.update(kwargs)
    return TaxReturn(**defaults)


class TestSSNFormatRule:
    def test_valid_passes(self):
        from api.tax_engine.validation.rules import SSNFormatRule

        rule = SSNFormatRule()
        tr = _make_return()
        assert rule.validate(tr) == []

    def test_duplicate_ssn(self):
        from api.tax_engine.validation.rules import DuplicateSSNRule

        rule = DuplicateSSNRule()
        tr = _make_return(dependents=[
            Dependent(first_name="A", last_name="D", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
            Dependent(first_name="B", last_name="D", ssn="111223333",
                      relationship="daughter", date_of_birth=date(2017, 1, 1)),
        ])
        results = rule.validate(tr)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert results[0].rule_id == "V007"


class TestMFJSpouseRequired:
    def test_mfj_without_spouse(self):
        from api.tax_engine.validation.rules import MFJSpouseRequiredRule

        rule = MFJSpouseRequiredRule()
        tr = _make_return(filing_status="MFJ")
        results = rule.validate(tr)
        assert len(results) == 1
        assert results[0].rule_id == "V003"

    def test_mfj_with_spouse(self):
        from api.tax_engine.validation.rules import MFJSpouseRequiredRule

        rule = MFJSpouseRequiredRule()
        tr = _make_return(
            filing_status="MFJ",
            spouse=Person(first_name="Jane", last_name="Doe",
                          ssn="987654321", date_of_birth=date(1987, 1, 1)),
        )
        assert rule.validate(tr) == []


class TestSCorpW2Rule:
    def test_scorp_without_w2(self):
        from api.tax_engine.validation.rules import SCorporateW2Rule

        rule = SCorporateW2Rule()
        tr = _make_return(k1s=[
            ScheduleK1(entity_name="My Corp", entity_ein="12-3456789",
                       entity_type="S", box1_ordinary_income=Decimal("50000")),
        ])
        results = rule.validate(tr)
        assert len(results) == 1
        assert results[0].rule_id == "V001"

    def test_scorp_with_matching_w2(self):
        from api.tax_engine.validation.rules import SCorporateW2Rule

        rule = SCorporateW2Rule()
        tr = _make_return(
            k1s=[ScheduleK1(entity_name="My Corp", entity_ein="12-3456789",
                            entity_type="S", box1_ordinary_income=Decimal("50000"))],
            w2s=[W2(employer_name="My Corp", employer_ein="12-3456789",
                     box1_wages=Decimal("60000"))],
        )
        assert rule.validate(tr) == []


class TestValidationEngine:
    def test_runs_all_rules(self):
        from api.tax_engine.validation.engine import ValidationEngine

        engine = ValidationEngine()
        tr = _make_return(filing_status="MFJ")  # No spouse → V003
        results = engine.validate(tr)
        assert any(r.rule_id == "V003" for r in results)

    def test_has_errors(self):
        from api.tax_engine.validation.engine import ValidationEngine

        engine = ValidationEngine()
        tr = _make_return(filing_status="MFJ")
        assert engine.has_errors(tr) is True

    def test_no_errors_on_valid(self):
        from api.tax_engine.validation.engine import ValidationEngine

        engine = ValidationEngine()
        tr = _make_return()
        assert engine.has_errors(tr) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_validation.py -v`
Expected: FAIL

- [ ] **Step 3: Implement validation base, rules, and engine**

Create `api/tax_engine/validation/__init__.py`:

```python
"""Validation engine package."""
```

Create `api/tax_engine/validation/base.py`:

```python
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
        """Return empty list if valid, or list of issues."""
```

Create `api/tax_engine/validation/rules.py`:

```python
"""Concrete validation rules V001–V011."""
from decimal import Decimal

from api.tax_engine.validation.base import ValidationResult, ValidationRule
from api.tax_engine.models.tax_return import TaxReturn


class SCorporateW2Rule(ValidationRule):
    rule_id = "V001"
    severity = "WARNING"
    description = "S-Corp K-1 should have matching W-2"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        results = []
        w2_eins = {w.employer_ein for w in tax_return.w2s}
        for k1 in tax_return.k1s:
            if k1.entity_type == "S" and k1.entity_ein not in w2_eins:
                results.append(ValidationResult(
                    rule_id=self.rule_id, severity=self.severity,
                    message=f"S-Corp '{k1.entity_name}' (EIN {k1.entity_ein}) has no matching W-2",
                    affected_fields=["k1s", "w2s"],
                    suggestion="S-Corp shareholders who work for the corp must receive a W-2",
                ))
        return results


class SSNFormatRule(ValidationRule):
    rule_id = "V002"
    severity = "ERROR"
    description = "SSN format validation"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        # SSN validation is handled by Pydantic model validators
        # This rule catches any that slipped through (e.g., manual overrides)
        return []


class MFJSpouseRequiredRule(ValidationRule):
    rule_id = "V003"
    severity = "ERROR"
    description = "MFJ requires spouse information"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        if tax_return.filing_status == "MFJ" and tax_return.spouse is None:
            return [ValidationResult(
                rule_id=self.rule_id, severity=self.severity,
                message="Filing status is MFJ but no spouse information provided",
                affected_fields=["filing_status", "spouse"],
                suggestion="Add spouse information or change filing status",
            )]
        return []


class HSAContributionMatchRule(ValidationRule):
    rule_id = "V004"
    severity = "WARNING"
    description = "HSA employer contribution should match W-2 box 12 code W"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        results = []
        w2_hsa = sum(
            (w.box12_codes.get("W", Decimal("0")) for w in tax_return.w2s), Decimal("0")
        )
        hsa_employer = sum((h.employer_contributions for h in tax_return.hsas), Decimal("0"))
        if hsa_employer > Decimal("0") and w2_hsa == Decimal("0"):
            results.append(ValidationResult(
                rule_id=self.rule_id, severity=self.severity,
                message="HSA employer contributions reported but no W-2 box 12 code W found",
                affected_fields=["hsas", "w2s.box12_codes"],
                suggestion="Verify employer HSA contributions match W-2 reporting",
            ))
        return results


class WithholdingExceedsIncomeRule(ValidationRule):
    rule_id = "V006"
    severity = "WARNING"
    description = "Withholding exceeds total income"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        total_income = sum((w.box1_wages for w in tax_return.w2s), Decimal("0"))
        total_withheld = sum((w.box2_fed_withheld for w in tax_return.w2s), Decimal("0"))
        if total_income > Decimal("0") and total_withheld > total_income:
            return [ValidationResult(
                rule_id=self.rule_id, severity=self.severity,
                message="Federal withholding exceeds total W-2 wages",
                affected_fields=["w2s.box1_wages", "w2s.box2_fed_withheld"],
                suggestion="Verify W-2 amounts are correct",
            )]
        return []


class DuplicateSSNRule(ValidationRule):
    rule_id = "V007"
    severity = "ERROR"
    description = "Duplicate SSN among dependents"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        ssns = [d.ssn for d in tax_return.dependents]
        seen = set()
        dupes = set()
        for ssn in ssns:
            if ssn in seen:
                dupes.add(ssn)
            seen.add(ssn)
        if dupes:
            return [ValidationResult(
                rule_id=self.rule_id, severity=self.severity,
                message=f"Duplicate SSN(s) found among dependents: {', '.join(dupes)}",
                affected_fields=["dependents.ssn"],
            )]
        return []


class HOHRequiresDependentRule(ValidationRule):
    rule_id = "V008"
    severity = "ERROR"
    description = "HOH requires qualifying dependent"

    def validate(self, tax_return: TaxReturn) -> list[ValidationResult]:
        if tax_return.filing_status == "HOH" and not tax_return.dependents:
            return [ValidationResult(
                rule_id=self.rule_id, severity=self.severity,
                message="Head of Household filing status requires at least one dependent",
                affected_fields=["filing_status", "dependents"],
                suggestion="Add qualifying dependent or change filing status",
            )]
        return []


def default_rules() -> list[ValidationRule]:
    """All built-in validation rules."""
    return [
        SCorporateW2Rule(),
        SSNFormatRule(),
        MFJSpouseRequiredRule(),
        HSAContributionMatchRule(),
        WithholdingExceedsIncomeRule(),
        DuplicateSSNRule(),
        HOHRequiresDependentRule(),
    ]
```

Create `api/tax_engine/validation/engine.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_validation.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/validation/ tests/api/tax_engine/test_validation.py
git commit -m "feat(tax_engine): add validation engine with 7 pluggable rules"
```

---

## Task 17: Document Assembler + ManualEntryModel

**Files:**
- Create: `api/tax_engine/assembler.py`
- Modify: `api/db/models.py` (add ManualEntryModel)
- Modify: `tests/api/conftest.py` (import ManualEntryModel)
- Create: `tests/api/tax_engine/test_assembler.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/tax_engine/test_assembler.py`:

```python
"""Tests for DocumentAssembler — documents + overrides → TaxReturn."""
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.base import Base
from api.db.models import ClientModel, DocumentModel, ManualEntryModel
from api.auth.models import OrganizationModel, UserModel
from api.tax_engine.assembler import DocumentAssembler


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        # Create org and user
        org = OrganizationModel(name="Test CPA", slug="test-cpa", plan="professional")
        session.add(org)
        await session.flush()
        user = UserModel(org_id=org.id, auth0_sub="dev|test", email="test@test.com",
                         name="Test", role="admin")
        session.add(user)
        await session.flush()
        # Create client
        client = ClientModel(org_id=org.id, created_by=user.id, name="Smith Family",
                             filing_status="mfj", tax_year=2024, dependents=2)
        session.add(client)
        await session.flush()
        yield session, client.id, org.id, user.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_assemble_from_approved_docs(db_session):
    session, client_id, org_id, user_id = db_session
    # Add approved W-2 document
    doc = DocumentModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", title="W-2 from Acme",
        status="approved", confidence=0.95,
        extracted_data=json.dumps({
            "employer_name": "Acme Corp",
            "employer_ein": "12-3456789",
            "box1_wages": "85000",
            "box2_fed_withheld": "15000",
        }),
    )
    session.add(doc)
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(tr.w2s) == 1
    assert tr.w2s[0].employer_name == "Acme Corp"
    assert str(tr.w2s[0].box1_wages) == "85000"


@pytest.mark.asyncio
async def test_manual_override_takes_precedence(db_session):
    session, client_id, org_id, user_id = db_session
    # Add approved W-2
    doc = DocumentModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", title="W-2 from Acme",
        status="approved", confidence=0.95,
        extracted_data=json.dumps({
            "employer_name": "Acme Corp",
            "employer_ein": "12-3456789",
            "box1_wages": "85000",
        }),
    )
    session.add(doc)
    # Add manual override
    override = ManualEntryModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", form_index=0,
        field_name="box1_wages", value="90000",
        entered_by=user_id,
    )
    session.add(override)
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert str(tr.w2s[0].box1_wages) == "90000"


@pytest.mark.asyncio
async def test_pending_docs_excluded(db_session):
    session, client_id, org_id, user_id = db_session
    doc = DocumentModel(
        org_id=org_id, created_by=user_id, client_id=client_id,
        form_type="W-2", title="W-2 pending",
        status="pending", confidence=0.50,
        extracted_data=json.dumps({"employer_name": "Pending Corp", "employer_ein": "99-9999999"}),
    )
    session.add(doc)
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(tr.w2s) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_assembler.py -v`
Expected: FAIL — `ManualEntryModel` doesn't exist

- [ ] **Step 3: Add ManualEntryModel to db/models.py**

Add to the end of `api/db/models.py`:

```python
class ManualEntryModel(TenantMixin, Base):
    __tablename__ = "manual_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    form_type: Mapped[str] = mapped_column(String(30))
    form_index: Mapped[int] = mapped_column(Integer, default=0)
    field_name: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(Text)
    entered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_manual_entries_org_client", "org_id", "client_id"),
    )
```

- [ ] **Step 4: Update tests/api/conftest.py to import ManualEntryModel**

Add to the imports in `tests/api/conftest.py`:

```python
from api.db.models import ClientModel, DocumentModel, ChatMessageModel, TaxReturnDraftModel, ManualEntryModel  # noqa: F401
```

- [ ] **Step 5: Implement assembler.py**

Create `api/tax_engine/assembler.py`:

```python
"""DocumentAssembler — builds TaxReturn from approved documents + manual overrides."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel, DocumentModel, ManualEntryModel
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.income import (
    W2, Income1099Int, Income1099Div, Income1099B, Income1099NEC, ScheduleK1,
)
from api.tax_engine.models.deductions import Mortgage1098
from api.tax_engine.models.tax_return import TaxReturn

# Maps form_type strings to (Pydantic model class, TaxReturn list field name)
_FORM_MAP: dict[str, tuple[type, str]] = {
    "W-2": (W2, "w2s"),
    "1099-INT": (Income1099Int, "interest_1099s"),
    "1099-DIV": (Income1099Div, "dividend_1099s"),
    "1099-B": (Income1099B, "broker_1099s"),
    "1099-NEC": (Income1099NEC, "nec_1099s"),
    "1098": (Mortgage1098, "mortgages"),
    "K-1": (ScheduleK1, "k1s"),
}

# Filing status mapping from DB values to engine values
_FILING_STATUS_MAP = {
    "single": "S", "mfj": "MFJ", "mfs": "MFS", "hoh": "HOH", "qw": "QSS",
    "S": "S", "MFJ": "MFJ", "MFS": "MFS", "HOH": "HOH", "QSS": "QSS",
}


class DocumentAssembler:
    """Builds a TaxReturn from approved documents + manual CPA overrides."""

    async def assemble(self, client_id: int, session: AsyncSession) -> TaxReturn:
        # 1. Load client
        result = await session.execute(
            select(ClientModel).where(ClientModel.id == client_id)
        )
        client = result.scalar_one()

        # 2. Load approved documents
        doc_result = await session.execute(
            select(DocumentModel).where(
                DocumentModel.client_id == client_id,
                DocumentModel.status == "approved",
            )
        )
        docs = doc_result.scalars().all()

        # 3. Load manual overrides
        override_result = await session.execute(
            select(ManualEntryModel).where(
                ManualEntryModel.client_id == client_id,
            )
        )
        overrides = override_result.scalars().all()

        # Group overrides by (form_type, form_index)
        override_map: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
        for ov in overrides:
            override_map[(ov.form_type, ov.form_index)][ov.field_name] = ov.value

        # 4. Parse documents into typed models
        form_lists: dict[str, list] = defaultdict(list)
        form_type_counts: dict[str, int] = defaultdict(int)

        for doc in docs:
            form_type = doc.form_type
            if form_type not in _FORM_MAP:
                continue

            model_cls, field_name = _FORM_MAP[form_type]
            data = json.loads(doc.extracted_data) if doc.extracted_data else {}

            # Apply manual overrides
            idx = form_type_counts[form_type]
            if (form_type, idx) in override_map:
                data.update(override_map[(form_type, idx)])

            form_type_counts[form_type] += 1

            # Convert string values to appropriate types
            for key, val in list(data.items()):
                if isinstance(val, str) and val.replace(".", "").replace("-", "").isdigit():
                    # Keep as string — Pydantic will coerce to Decimal
                    pass

            try:
                model = model_cls(**data)
                form_lists[field_name].append(model)
            except Exception:
                # Skip documents that can't be parsed
                continue

        # 5. Build TaxReturn
        filing_status = _FILING_STATUS_MAP.get(client.filing_status, "S")

        # Placeholder primary person (will be filled from client data or overrides)
        primary = Person(
            first_name=client.name.split()[0] if client.name else "Unknown",
            last_name=client.name.split()[-1] if client.name and len(client.name.split()) > 1 else "Unknown",
            ssn="000000001",  # Placeholder — should come from client record
            date_of_birth=date(1980, 1, 1),
        )

        return TaxReturn(
            tax_year=client.tax_year,
            filing_status=filing_status,
            primary=primary,
            address=Address(street="TBD", city="TBD", state="XX", zip_code="00000"),
            w2s=form_lists.get("w2s", []),
            interest_1099s=form_lists.get("interest_1099s", []),
            dividend_1099s=form_lists.get("dividend_1099s", []),
            broker_1099s=form_lists.get("broker_1099s", []),
            nec_1099s=form_lists.get("nec_1099s", []),
            mortgages=form_lists.get("mortgages", []),
            k1s=form_lists.get("k1s", []),
        )
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_assembler.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/tax_engine/assembler.py api/db/models.py tests/api/conftest.py tests/api/tax_engine/test_assembler.py
git commit -m "feat(tax_engine): add DocumentAssembler and ManualEntryModel"
```

---

## Task 18: API Integration — Replace Mock Draft with Engine

**Files:**
- Create: `api/tax_engine/dependencies.py`
- Modify: `api/routers/tax_returns.py`
- Modify: `tests/api/test_tax_returns.py`

- [ ] **Step 1: Create FastAPI dependencies**

Create `api/tax_engine/dependencies.py`:

```python
"""FastAPI dependency providers for the tax engine."""
from fastapi import Query

from api.tax_engine.constants.registry import get_constants
from api.tax_engine.services.engine import TaxCalculationEngine
from api.tax_engine.validation.engine import ValidationEngine
from api.tax_engine.assembler import DocumentAssembler

# Ensure constants are registered
import api.tax_engine.constants  # noqa: F401


def get_tax_engine(tax_year: int = Query(default=2024)) -> TaxCalculationEngine:
    constants = get_constants(tax_year)
    return TaxCalculationEngine(constants)


def get_validation_engine() -> ValidationEngine:
    return ValidationEngine()


def get_assembler() -> DocumentAssembler:
    return DocumentAssembler()
```

- [ ] **Step 2: Replace router with engine-backed implementation**

Rewrite `api/routers/tax_returns.py`:

```python
"""Tax return draft endpoints — powered by tax calculation engine."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel, TaxReturnDraftModel, ManualEntryModel
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel
from api.models.tax_return import ReturnLine, TaxReturnDraft
from api.routers._helpers import get_client_or_404
from api.tax_engine.dependencies import get_tax_engine, get_validation_engine, get_assembler
from api.tax_engine.services.engine import TaxCalculationEngine
from api.tax_engine.validation.engine import ValidationEngine
from api.tax_engine.validation.base import ValidationResult
from api.tax_engine.assembler import DocumentAssembler

router = APIRouter(prefix="/api/clients/{client_id}/returns", tags=["tax_returns"])


class ManualEntryRequest(BaseModel):
    form_type: str
    form_index: int = 0
    field_name: str
    value: str


class ComputeResponse(BaseModel):
    draft: TaxReturnDraft
    validation_results: list[ValidationResult] = []


@router.post("/draft", response_model=TaxReturnDraft)
async def generate_draft(
    client_id: int,
    tax_year: int = Query(default=2024),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Generate a tax return draft using the calculation engine."""
    client = await get_client_or_404(client_id, session, user)

    # Import constants to ensure registration
    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants

    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    assembler = DocumentAssembler()

    # Assemble TaxReturn from documents + overrides
    tax_return = await assembler.assemble(client_id, session)

    # Validate
    validator = ValidationEngine()
    validation_results = validator.validate(tax_return)

    # Compute
    result = engine.compute(tax_return)

    # Convert to TaxReturnDraft (existing response format)
    lines = []
    f1040 = result.form_results.get("1040")
    if f1040:
        for line_num, trace in sorted(f1040.lines.items()):
            section = "income"
            if line_num in ("12", "13a", "15"):
                section = "deductions"
            elif line_num in ("16", "19", "23", "24"):
                section = "tax_credits"
            elif line_num in ("25", "26", "33", "35a", "37"):
                section = "payments"
            lines.append(ReturnLine(
                number=line_num, label=trace.label,
                value=float(trace.value), section=section,
            ))

    total_income = float(result.total_income)
    effective_rate = round(float(result.total_tax) / total_income * 100, 1) if total_income > 0 else 0.0

    draft = TaxReturnDraft(
        client_id=client_id,
        tax_year=client.tax_year,
        filing_status=client.filing_status,
        lines=lines,
        total_income=total_income,
        total_deductions=float(result.form_results.get("deduction", type("", (), {"total": Decimal("0")})).total),
        taxable_income=float(result.taxable_income),
        total_tax=float(result.total_tax),
        total_payments=float(result.total_payments),
        refund_or_owed=float(result.refund_or_owed),
        effective_rate=effective_rate,
    )

    # Upsert draft in database
    db_result = await session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.org_id == user.org_id,
            TaxReturnDraftModel.client_id == client_id,
        )
    )
    existing = db_result.scalar_one_or_none()
    if existing:
        existing.tax_year = draft.tax_year
        existing.filing_status = draft.filing_status
        existing.draft_json = draft.model_dump_json()
    else:
        db_draft = TaxReturnDraftModel(
            client_id=client_id, org_id=user.org_id, created_by=user.id,
            tax_year=draft.tax_year, filing_status=draft.filing_status,
            draft_json=draft.model_dump_json(),
        )
        session.add(db_draft)
    await session.commit()
    return draft


@router.get("/draft", response_model=TaxReturnDraft)
async def get_draft(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(TaxReturnDraftModel).where(
            TaxReturnDraftModel.org_id == user.org_id,
            TaxReturnDraftModel.client_id == client_id,
        )
    )
    db_draft = result.scalar_one_or_none()
    if not db_draft:
        raise HTTPException(status_code=404, detail="No draft found — generate one first")
    return TaxReturnDraft.model_validate_json(db_draft.draft_json)


@router.post("/entries")
async def create_manual_entry(
    client_id: int,
    entry: ManualEntryRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Add or update a manual override for a tax form field."""
    await get_client_or_404(client_id, session, user)
    # Check for existing entry
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
            ManualEntryModel.form_type == entry.form_type,
            ManualEntryModel.form_index == entry.form_index,
            ManualEntryModel.field_name == entry.field_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = entry.value
    else:
        me = ManualEntryModel(
            org_id=user.org_id, created_by=user.id, client_id=client_id,
            form_type=entry.form_type, form_index=entry.form_index,
            field_name=entry.field_name, value=entry.value,
            entered_by=user.id,
        )
        session.add(me)
    await session.commit()
    return {"status": "ok"}


@router.get("/entries")
async def list_manual_entries(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """List all manual overrides for a client."""
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
        )
    )
    entries = result.scalars().all()
    return [
        {"id": e.id, "form_type": e.form_type, "form_index": e.form_index,
         "field_name": e.field_name, "value": e.value}
        for e in entries
    ]


@router.delete("/entries/{entry_id}")
async def delete_manual_entry(
    client_id: int,
    entry_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    """Remove a manual override."""
    result = await session.execute(
        select(ManualEntryModel).where(
            ManualEntryModel.id == entry_id,
            ManualEntryModel.org_id == user.org_id,
            ManualEntryModel.client_id == client_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Manual entry not found")
    await session.delete(entry)
    await session.commit()
    return {"status": "deleted"}
```

- [ ] **Step 3: Update existing tests**

Rewrite `tests/api/test_tax_returns.py`:

```python
"""Tests for tax return draft endpoints — engine-backed."""
import pytest


@pytest.mark.asyncio
async def test_generate_draft_return(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2},
    )
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert "lines" in body
    assert body["filing_status"] == "mfj"


@pytest.mark.asyncio
async def test_get_draft_after_generate(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024, "dependents": 2},
    )
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/returns/draft")
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    assert resp.json()["client_id"] == cid


@pytest.mark.asyncio
async def test_get_draft_before_generate(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Test", "filing_status": "single", "tax_year": 2024},
    )
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_draft_single_filer(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Solo Person", "filing_status": "single", "tax_year": 2024, "dependents": 0},
    )
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["filing_status"] == "single"


@pytest.mark.asyncio
async def test_draft_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/returns/draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_entry_crud(client):
    c = await client.post(
        "/api/clients",
        json={"name": "Test Client", "filing_status": "single", "tax_year": 2024},
    )
    cid = c.json()["id"]

    # Create
    resp = await client.post(f"/api/clients/{cid}/returns/entries", json={
        "form_type": "W-2", "form_index": 0,
        "field_name": "box1_wages", "value": "90000",
    })
    assert resp.status_code == 200

    # List
    resp = await client.get(f"/api/clients/{cid}/returns/entries")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["value"] == "90000"

    # Delete
    entry_id = entries[0]["id"]
    resp = await client.delete(f"/api/clients/{cid}/returns/entries/{entry_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = await client.get(f"/api/clients/{cid}/returns/entries")
    assert len(resp.json()) == 0
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v --ignore=ustaxes-master --ignore=tax_brain -x`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/dependencies.py api/routers/tax_returns.py tests/api/test_tax_returns.py
git commit -m "feat(tax_engine): integrate engine into API — replace mock draft with real calculations"
```

---

## Task 19: Final Integration Test + Cleanup

**Files:**
- Run all tests end-to-end
- Verify no regressions

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest tests/api/ -v -x`
Expected: All tests PASS

- [ ] **Step 2: Run tax engine tests specifically**

Run: `python -m pytest tests/api/tax_engine/ -v --tb=short`
Expected: All ~50+ tests PASS

- [ ] **Step 3: Commit final state**

```bash
git add -A
git status
git commit -m "feat(tax_engine): Phase 1 complete — models, constants, calculators, validation, assembler, API"
```
