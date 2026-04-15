# Phase 3B: PDF Form Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate filled IRS Form 1040 PDFs from computed tax results, merging only active schedules into a single downloadable PDF.

**Architecture:** A `PDFGenerator` class fills blank IRS PDF templates using pypdf's AcroForm field filling, with per-form field mapping functions that translate `TaxResult` values to IRS field names. Active forms are detected from the `TaxReturn`/`TaxResult` data. A `GET /pdf` endpoint generates on demand.

**Tech Stack:** Python 3.12, pypdf>=4.0, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-pdf-generation-phase3b-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `api/tax_engine/pdf/__init__.py` | Package init |
| `api/tax_engine/pdf/templates/` | Blank IRS PDF files (copied from reference) |
| `api/tax_engine/pdf/field_maps.py` | Per-form field mapping functions |
| `api/tax_engine/pdf/generator.py` | PDFGenerator class |
| `tests/api/tax_engine/test_pdf_field_maps.py` | Field map tests |
| `tests/api/tax_engine/test_pdf_generator.py` | Generator tests |
| `tests/api/test_pdf_endpoint.py` | API integration test |

### Modified Files

| File | Change |
|------|--------|
| `api/routers/tax_returns.py` | Add `GET /pdf` endpoint |
| `requirements-api.txt` | Add `pypdf>=4.0` |

---

## Task 1: Copy Templates + Add pypdf Dependency

**Files:**
- Create: `api/tax_engine/pdf/__init__.py`
- Create: `api/tax_engine/pdf/templates/` (copy PDFs)
- Modify: `requirements-api.txt`

- [ ] **Step 1: Create package and copy templates**

```bash
mkdir -p api/tax_engine/pdf/templates
touch api/tax_engine/pdf/__init__.py

# Copy blank IRS PDFs from reference codebase
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040sa.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040sb.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040sd.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040se.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040sse.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f1040s8.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f8959.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f8960.pdf api/tax_engine/pdf/templates/
cp ustaxes-master/ts-forms/public/forms/Y2024/irs/f8995.pdf api/tax_engine/pdf/templates/
```

- [ ] **Step 2: Add pypdf dependency**

Append to `requirements-api.txt`:
```
# PDF generation
pypdf>=4.0
```

Then install:
```bash
pip install pypdf>=4.0
```

- [ ] **Step 3: Verify templates are valid PDFs**

```bash
python -c "
from pypdf import PdfReader
from pathlib import Path
templates = Path('api/tax_engine/pdf/templates')
for pdf in sorted(templates.glob('*.pdf')):
    r = PdfReader(str(pdf))
    fields = r.get_fields() or {}
    print(f'{pdf.name}: {len(r.pages)} pages, {len(fields)} fields')
"
```
Expected: Each PDF shows page count and field count (no errors).

- [ ] **Step 4: Commit**

```bash
git add api/tax_engine/pdf/ requirements-api.txt
git commit -m "feat(pdf): add blank IRS PDF templates and pypdf dependency"
```

---

## Task 2: Field Mapping Functions

**Files:**
- Create: `api/tax_engine/pdf/field_maps.py`
- Create: `tests/api/tax_engine/test_pdf_field_maps.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/test_pdf_field_maps.py`:

```python
"""Tests for PDF field mapping functions."""
from datetime import date
from decimal import Decimal

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import W2, Income1099Int, Income1099B
from api.tax_engine.models.deductions import ItemizedDeductions, RentalProperty
from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult, LineTrace


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))


def _address():
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")


def _make_return(**kwargs) -> TaxReturn:
    defaults = dict(tax_year=2024, filing_status="S", primary=_person(), address=_address())
    defaults.update(kwargs)
    return TaxReturn(**defaults)


def _make_result(**kwargs) -> TaxResult:
    defaults = dict(tax_year=2024, filing_status="S", total_income=Decimal("85000"),
                    agi=Decimal("85000"), taxable_income=Decimal("70400"),
                    total_tax=Decimal("10000"), total_payments=Decimal("15000"),
                    refund_or_owed=Decimal("5000"))
    defaults.update(kwargs)
    return TaxResult(**defaults)


class TestFmt:
    def test_formats_with_commas(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(Decimal("85000")) == "85,000"

    def test_zero_returns_empty(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(Decimal("0")) == ""

    def test_none_returns_empty(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt(None) == ""

    def test_string_passthrough(self):
        from api.tax_engine.pdf.field_maps import fmt
        assert fmt("IL") == "IL"


class TestForm1040Map:
    def test_basic_fields(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        tr = _make_return(w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                                  box1_wages=Decimal("85000"), box2_fed_withheld=Decimal("15000"))])
        result = _make_result(
            form_results={
                "1040": FormResult(form_name="1040", total=Decimal("5000"), lines={
                    "1a": LineTrace(form="1040", line="1a", label="Wages", value=Decimal("85000"), formula="test"),
                    "9": LineTrace(form="1040", line="9", label="Total income", value=Decimal("85000"), formula="test"),
                    "11": LineTrace(form="1040", line="11", label="AGI", value=Decimal("85000"), formula="test"),
                    "12": LineTrace(form="1040", line="12", label="Deduction", value=Decimal("14600"), formula="test"),
                    "15": LineTrace(form="1040", line="15", label="Taxable income", value=Decimal("70400"), formula="test"),
                    "16": LineTrace(form="1040", line="16", label="Tax", value=Decimal("11000"), formula="test"),
                    "24": LineTrace(form="1040", line="24", label="Total tax", value=Decimal("11000"), formula="test"),
                    "25": LineTrace(form="1040", line="25", label="Withholding", value=Decimal("15000"), formula="test"),
                    "33": LineTrace(form="1040", line="33", label="Total payments", value=Decimal("15000"), formula="test"),
                    "35a": LineTrace(form="1040", line="35a", label="Refund", value=Decimal("4000"), formula="test"),
                }),
            })
        fields = map_f1040(tr, result)
        assert 0 in fields  # Page 1
        assert 1 in fields  # Page 2
        assert fields[0]["f1_04[0]"] == "John"
        assert fields[0]["f1_05[0]"] == "Doe"
        assert fields[0]["f1_06[0]"] == "123456789"
        assert fields[0]["f1_10[0]"] == "123 Main St"
        assert fields[0]["c1_1[0]"] == "/1"  # Single filing status
        assert fields[0]["f1_32[0]"] == "85,000"  # Line 1a wages

    def test_mfj_checkbox(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        spouse = Person(first_name="Jane", last_name="Doe", ssn="987654321", date_of_birth=date(1987, 5, 10))
        tr = _make_return(filing_status="MFJ", spouse=spouse)
        result = _make_result(filing_status="MFJ", form_results={
            "1040": FormResult(form_name="1040", total=Decimal("0"), lines={})})
        fields = map_f1040(tr, result)
        assert fields[0]["c1_2[0]"] == "/1"  # MFJ
        assert fields[0]["f1_07[0]"] == "Jane"

    def test_dependents(self):
        from api.tax_engine.pdf.field_maps import map_f1040
        tr = _make_return(dependents=[
            Dependent(first_name="Kid", last_name="Doe", ssn="111223333",
                      relationship="son", date_of_birth=date(2015, 1, 1)),
        ])
        result = _make_result(form_results={
            "1040": FormResult(form_name="1040", total=Decimal("0"), lines={})})
        fields = map_f1040(tr, result)
        assert fields[0]["f1_20[0]"] == "Kid Doe"
        assert fields[0]["f1_21[0]"] == "111223333"


class TestActiveFormChecks:
    def test_schedule_d_active_with_broker(self):
        from api.tax_engine.pdf.field_maps import is_schedule_d_active
        tr = _make_return(broker_1099s=[Income1099B(payer="Fidelity", long_term_proceeds=Decimal("50000"))])
        assert is_schedule_d_active(tr, _make_result()) is True

    def test_schedule_d_inactive(self):
        from api.tax_engine.pdf.field_maps import is_schedule_d_active
        assert is_schedule_d_active(_make_return(), _make_result()) is False

    def test_schedule_a_active_when_itemizing(self):
        from api.tax_engine.pdf.field_maps import is_schedule_a_active
        result = _make_result(form_results={
            "Schedule A": FormResult(form_name="Schedule A", total=Decimal("20000")),
            "deduction": FormResult(form_name="deduction", total=Decimal("20000"),
                lines={"12": LineTrace(form="1040", line="12", label="Itemized", value=Decimal("20000"), formula="itemized")})})
        tr = _make_return(itemized=ItemizedDeductions(mortgage_interest_1098=Decimal("15000"), charity_cash=Decimal("5000")))
        assert is_schedule_a_active(tr, result) is True

    def test_schedule_a_inactive_standard(self):
        from api.tax_engine.pdf.field_maps import is_schedule_a_active
        result = _make_result(form_results={
            "deduction": FormResult(form_name="deduction", total=Decimal("14600"),
                lines={"12": LineTrace(form="1040", line="12", label="Standard", value=Decimal("14600"), formula="standard")})})
        assert is_schedule_a_active(_make_return(), result) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_pdf_field_maps.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement field_maps.py**

Create `api/tax_engine/pdf/field_maps.py`:

```python
"""Per-form field mapping functions for IRS PDF AcroForm filling.

Each map function takes (TaxReturn, TaxResult) and returns
{page_index: {field_name: value}} for pypdf to fill.

Field names sourced from ustaxes-master/engine/pdf_generator.py
and verified against IRS TY2024 PDF templates.
"""
from decimal import Decimal
from typing import Optional

from api.tax_engine.models.tax_return import TaxReturn, TaxResult, FormResult


def fmt(value, default="") -> str:
    """Format a value as whole-dollar string with commas. Zero/None → empty."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        if value == Decimal("0"):
            return default
        return f"{int(value):,}"
    if isinstance(value, (int, float)):
        if value == 0:
            return default
        return f"{round(value):,}"
    return str(value)


def _line_val(result: TaxResult, form_name: str, line: str) -> Decimal:
    """Get a line value from TaxResult, returning 0 if not found."""
    fr = result.form_results.get(form_name)
    if fr and line in fr.lines:
        return fr.lines[line].value
    return Decimal("0")


def _taxpayer_name(tr: TaxReturn) -> str:
    name = f"{tr.primary.first_name} {tr.primary.last_name}"
    if tr.spouse:
        name += f" & {tr.spouse.first_name} {tr.spouse.last_name}"
    return name


_FILING_STATUS_CHECKBOX = {
    "S": "c1_1[0]", "MFJ": "c1_2[0]", "MFS": "c1_3[0]",
    "HOH": "c1_4[0]", "QSS": "c1_5[0]",
}


# ── Form 1040 (2 pages) ─────────────────────────────────────────────────────

def map_f1040(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    f1040 = result.form_results.get("1040")

    def g(line: str) -> Decimal:
        if f1040 and line in f1040.lines:
            return f1040.lines[line].value
        return Decimal("0")

    p1: dict[str, str] = {}

    # Header
    p1["f1_04[0]"] = tr.primary.first_name
    p1["f1_05[0]"] = tr.primary.last_name
    p1["f1_06[0]"] = tr.primary.ssn
    if tr.spouse:
        p1["f1_07[0]"] = tr.spouse.first_name
        p1["f1_08[0]"] = tr.spouse.last_name
        p1["f1_09[0]"] = tr.spouse.ssn
    p1["f1_10[0]"] = tr.address.street
    if tr.address.apt:
        p1["f1_11[0]"] = tr.address.apt
    p1["f1_12[0]"] = tr.address.city
    p1["f1_13[0]"] = tr.address.state
    p1["f1_14[0]"] = tr.address.zip_code

    # Filing status
    cb = _FILING_STATUS_CHECKBOX.get(tr.filing_status)
    if cb:
        p1[cb] = "/1"

    # Dependents (up to 4)
    dep_fields = [
        ("f1_20[0]", "f1_21[0]", "f1_22[0]", "c1_14[0]"),
        ("f1_23[0]", "f1_24[0]", "f1_25[0]", "c1_16[0]"),
        ("f1_26[0]", "f1_27[0]", "f1_28[0]", "c1_18[0]"),
        ("f1_29[0]", "f1_30[0]", "f1_31[0]", "c1_20[0]"),
    ]
    for i, dep in enumerate(tr.dependents[:4]):
        name_f, ssn_f, rel_f, ctc_cb = dep_fields[i]
        p1[name_f] = f"{dep.first_name} {dep.last_name}"
        p1[ssn_f] = dep.ssn
        p1[rel_f] = dep.relationship
        if dep.is_qualifying_child:
            p1[ctc_cb] = "/1"

    # Income (page 1)
    p1["f1_32[0]"] = fmt(g("1a"))
    p1["f1_43[0]"] = fmt(g("2b"))
    p1["f1_45[0]"] = fmt(g("3b"))
    p1["f1_52[0]"] = fmt(g("7"))
    p1["f1_53[0]"] = fmt(g("8"))
    p1["f1_54[0]"] = fmt(g("9"))
    p1["f1_55[0]"] = fmt(g("10"))
    p1["f1_56[0]"] = fmt(g("11"))
    p1["f1_57[0]"] = fmt(g("12"))
    p1["f1_58[0]"] = fmt(g("13a"))
    p1["f1_60[0]"] = fmt(g("15"))

    # Page 2
    p2: dict[str, str] = {}
    p2["f2_02[0]"] = fmt(g("16"))
    p2["f2_09[0]"] = fmt(g("23"))
    p2["f2_10[0]"] = fmt(g("24"))
    p2["f2_11[0]"] = fmt(g("25"))
    p2["f2_15[0]"] = fmt(g("26"))
    p2["f2_22[0]"] = fmt(g("33"))
    p2["f2_24[0]"] = fmt(g("35a"))
    p2["f2_28[0]"] = fmt(g("37") if "37" in (f1040.lines if f1040 else {}) else Decimal("0"))

    return {0: p1, 1: p2}


# ── Schedule A (1 page) ─────────────────────────────────────────────────────

def map_schedule_a(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    it = tr.itemized
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    if it:
        fields["f1_3[0]"] = fmt(it.medical_dental)
        fields["f1_4[0]"] = fmt(result.agi)
        fields["f1_7[0]"] = fmt(it.salt_income_or_sales)
        fields["f1_8[0]"] = fmt(it.salt_real_estate)
        fields["f1_9[0]"] = fmt(it.salt_personal_property)
        fields["f1_16[0]"] = fmt(it.mortgage_interest_1098)
        fields["f1_19[0]"] = fmt(it.mortgage_interest_other)
        fields["f1_23[0]"] = fmt(it.investment_interest)
        fields["f1_25[0]"] = fmt(it.charity_cash)
        fields["f1_26[0]"] = fmt(it.charity_noncash)
        fields["f1_29[0]"] = fmt(it.casualty_loss)

    sched_a = result.form_results.get("Schedule A")
    if sched_a:
        fields["f1_34[0]"] = fmt(sched_a.total)

    return {0: fields}


# ── Schedule D (2 pages) ─────────────────────────────────────────────────────

def map_schedule_d(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    p1: dict[str, str] = {}
    p1["f1_01[0]"] = _taxpayer_name(tr)
    p1["f1_02[0]"] = tr.primary.ssn

    sched_d = result.form_results.get("Schedule D")
    if sched_d:
        p1["f1_22[0]"] = fmt(sched_d.lines.get("7", None) and sched_d.lines["7"].value)
        p1["f1_43[0]"] = fmt(sched_d.lines.get("15", None) and sched_d.lines["15"].value)

    p2: dict[str, str] = {}
    if sched_d:
        p2["f2_01[0]"] = fmt(sched_d.lines.get("21", None) and sched_d.lines["21"].value)

    return {0: p1, 1: p2}


# ── Schedule E (2 pages) ─────────────────────────────────────────────────────

def map_schedule_e(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    p1: dict[str, str] = {}
    p1["f1_1[0]"] = _taxpayer_name(tr)
    p1["f1_2[0]"] = tr.primary.ssn

    if tr.rental_properties:
        p1["f1_3[0]"] = tr.rental_properties[0].address

    sched_e = result.form_results.get("Schedule E")
    if sched_e:
        if "26" in sched_e.lines:
            p1["f1_84[0]"] = fmt(sched_e.lines["26"].value)

    p2: dict[str, str] = {}
    p2["f2_1[0]"] = _taxpayer_name(tr)
    p2["f2_2[0]"] = tr.primary.ssn
    if sched_e:
        if "32" in sched_e.lines:
            p2["f2_47[0]"] = fmt(sched_e.lines["32"].value)

    return {0: p1, 1: p2}


# ── Form 8959 (1 page) ──────────────────────────────────────────────────────

def map_form_8959(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    total_medicare = sum(w.box5_medicare_wages for w in tr.w2s)
    threshold = {"S": 200000, "MFJ": 250000, "MFS": 125000, "HOH": 200000, "QSS": 200000}
    thresh = threshold.get(tr.filing_status, 200000)
    excess = max(0, int(total_medicare) - thresh)

    fields["f1_3[0]"] = fmt(total_medicare)
    fields["f1_6[0]"] = fmt(total_medicare)
    fields["f1_7[0]"] = f"{thresh:,}"
    fields["f1_8[0]"] = fmt(Decimal(str(excess)))
    fields["f1_9[0]"] = fmt(Decimal(str(round(excess * 0.009))))

    f8959 = result.form_results.get("Form 8959")
    if f8959 and "18" in f8959.lines:
        fields["f1_20[0]"] = fmt(f8959.lines["18"].value)

    return {0: fields}


# ── Form 8960 (1 page) ──────────────────────────────────────────────────────

def map_form_8960(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    threshold = {"S": 200000, "MFJ": 250000, "MFS": 125000, "HOH": 200000, "QSS": 250000}
    thresh = threshold.get(tr.filing_status, 200000)

    f8960 = result.form_results.get("Form 8960")
    if f8960:
        nii = f8960.lines.get("8", None)
        if nii:
            fields["f1_15[0]"] = fmt(nii.value)
        fields["f1_23[0]"] = fmt(result.agi)
        fields["f1_24[0]"] = f"{thresh:,}"
        excess = max(Decimal("0"), result.agi - Decimal(str(thresh)))
        fields["f1_25[0]"] = fmt(excess)
        if "17" in f8960.lines:
            fields["f1_27[0]"] = fmt(f8960.lines["17"].value)

    return {0: fields}


# ── Schedule B (1 page) — basic fill ────────────────────────────────────────

def map_schedule_b(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    sched_b = result.form_results.get("Schedule B")
    if sched_b:
        if "4" in sched_b.lines:
            fields["f1_15[0]"] = fmt(sched_b.lines["4"].value)
        if "6" in sched_b.lines:
            fields["f1_32[0]"] = fmt(sched_b.lines["6"].value)

    return {0: fields}


# ── Schedule SE (2 pages) — basic fill ──────────────────────────────────────

def map_schedule_se(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    sched_se = result.form_results.get("Schedule SE")
    if sched_se:
        if "4a" in sched_se.lines:
            fields["f1_5[0]"] = fmt(sched_se.lines["4a"].value)
        if "12" in sched_se.lines:
            fields["f1_11[0]"] = fmt(sched_se.lines["12"].value)
        if "13" in sched_se.lines:
            fields["f1_12[0]"] = fmt(sched_se.lines["13"].value)

    return {0: fields}


# ── Form 8812 (3 pages) — basic fill ────────────────────────────────────────

def map_form_8812(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    sched_8812 = result.form_results.get("Schedule 8812")
    if sched_8812:
        if "nonrefundable" in sched_8812.lines:
            fields["f1_9[0]"] = fmt(sched_8812.lines["nonrefundable"].value)
        if "refundable" in sched_8812.lines:
            fields["f1_20[0]"] = fmt(sched_8812.lines["refundable"].value)

    return {0: fields}


# ── Form 8995 (1 page) — basic fill ─────────────────────────────────────────

def map_form_8995(tr: TaxReturn, result: TaxResult) -> dict[int, dict[str, str]]:
    fields: dict[str, str] = {}
    fields["f1_1[0]"] = _taxpayer_name(tr)
    fields["f1_2[0]"] = tr.primary.ssn

    f8995 = result.form_results.get("Form 8995")
    if f8995:
        if "15" in f8995.lines:
            fields["f1_16[0]"] = fmt(f8995.lines["15"].value)

    return {0: fields}


# ── Active form detection ────────────────────────────────────────────────────

def is_schedule_b_active(tr: TaxReturn, result: TaxResult) -> bool:
    return bool(tr.interest_1099s or tr.dividend_1099s)


def is_schedule_d_active(tr: TaxReturn, result: TaxResult) -> bool:
    return bool(tr.broker_1099s)


def is_schedule_e_active(tr: TaxReturn, result: TaxResult) -> bool:
    return bool(tr.rental_properties or tr.k1s)


def is_schedule_a_active(tr: TaxReturn, result: TaxResult) -> bool:
    ded = result.form_results.get("deduction")
    sched_a = result.form_results.get("Schedule A")
    if not ded or not sched_a:
        return False
    return sched_a.total > Decimal("0") and ded.total == sched_a.total


def is_schedule_se_active(tr: TaxReturn, result: TaxResult) -> bool:
    se = result.form_results.get("Schedule SE")
    return bool(se and se.total > Decimal("0"))


def is_form_8812_active(tr: TaxReturn, result: TaxResult) -> bool:
    from datetime import date
    return any(d.is_qualifying_child and d.date_of_birth > date(tr.tax_year - 16, 1, 1)
               for d in tr.dependents)


def is_form_active(tr: TaxReturn, result: TaxResult, form_key: str) -> bool:
    fr = result.form_results.get(form_key)
    return bool(fr and fr.total > Decimal("0"))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_pdf_field_maps.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/pdf/field_maps.py tests/api/tax_engine/test_pdf_field_maps.py
git commit -m "feat(pdf): add field mapping functions for Form 1040 and all schedules"
```

---

## Task 3: PDF Generator

**Files:**
- Create: `api/tax_engine/pdf/generator.py`
- Create: `tests/api/tax_engine/test_pdf_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/tax_engine/test_pdf_generator.py`:

```python
"""Tests for PDF generator."""
from datetime import date
from decimal import Decimal

import pytest

import api.tax_engine.constants  # noqa: F401
from api.tax_engine.constants.registry import get_constants
from api.tax_engine.models.people import Person, Address, Dependent
from api.tax_engine.models.income import W2, Income1099B
from api.tax_engine.models.tax_return import TaxReturn
from api.tax_engine.services.engine import TaxCalculationEngine


def _person():
    return Person(first_name="John", last_name="Doe", ssn="123456789", date_of_birth=date(1985, 1, 1))


def _address():
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62701")


class TestPDFGenerator:
    def test_generates_valid_pdf(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box2_fed_withheld=Decimal("15000"),
                               box3_ss_wages=Decimal("85000"), box5_medicare_wages=Decimal("85000"))])
        c = get_constants(2024)
        result = TaxCalculationEngine(c).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 1000

    def test_empty_return_produces_1040_only(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        from pypdf import PdfReader
        import io
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address())
        c = get_constants(2024)
        result = TaxCalculationEngine(c).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 2  # Form 1040 is 2 pages

    def test_return_with_capital_gains_includes_schedule_d(self):
        from api.tax_engine.pdf.generator import PDFGenerator
        from pypdf import PdfReader
        import io
        tr = TaxReturn(tax_year=2024, filing_status="S", primary=_person(), address=_address(),
                       w2s=[W2(employer_name="Acme", employer_ein="12-3456789",
                               box1_wages=Decimal("85000"), box3_ss_wages=Decimal("85000"),
                               box5_medicare_wages=Decimal("85000"))],
                       broker_1099s=[Income1099B(payer="Fidelity",
                                                 long_term_proceeds=Decimal("50000"),
                                                 long_term_cost_basis=Decimal("30000"))])
        c = get_constants(2024)
        result = TaxCalculationEngine(c).compute(tr)
        pdf_bytes = PDFGenerator().generate(tr, result)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        # 1040 (2 pages) + Schedule D (2 pages) = 4 pages
        assert len(reader.pages) >= 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/tax_engine/test_pdf_generator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement generator.py**

Create `api/tax_engine/pdf/generator.py`:

```python
"""PDFGenerator — fills IRS PDF templates and merges active forms."""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

from api.tax_engine.models.tax_return import TaxReturn, TaxResult
from api.tax_engine.pdf.field_maps import (
    map_f1040, map_schedule_a, map_schedule_b, map_schedule_d,
    map_schedule_e, map_schedule_se, map_form_8812,
    map_form_8959, map_form_8960, map_form_8995,
    is_schedule_a_active, is_schedule_b_active, is_schedule_d_active,
    is_schedule_e_active, is_schedule_se_active, is_form_8812_active,
    is_form_active,
)

DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"

# (template_filename, field_prefix_for_rename, map_function, active_check)
_FORM_REGISTRY: list[tuple[str, str | None, callable, callable]] = [
    ("f1040.pdf",    None,   map_f1040,       lambda tr, r: True),
    ("f1040sb.pdf",  "sb",   map_schedule_b,  is_schedule_b_active),
    ("f1040sa.pdf",  "sa",   map_schedule_a,  is_schedule_a_active),
    ("f1040sd.pdf",  "sd",   map_schedule_d,  is_schedule_d_active),
    ("f1040se.pdf",  "se",   map_schedule_e,  is_schedule_e_active),
    ("f1040sse.pdf", "sse",  map_schedule_se, is_schedule_se_active),
    ("f1040s8.pdf",  "s8",   map_form_8812,   is_form_8812_active),
    ("f8959.pdf",    "m89",  map_form_8959,   lambda tr, r: is_form_active(tr, r, "Form 8959")),
    ("f8960.pdf",    "n89",  map_form_8960,   lambda tr, r: is_form_active(tr, r, "Form 8960")),
    ("f8995.pdf",    "q89",  map_form_8995,   lambda tr, r: is_form_active(tr, r, "Form 8995")),
]


class PDFGenerator:
    """Generates filled IRS PDF returns from TaxReturn + TaxResult."""

    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR

    def generate(self, tax_return: TaxReturn, result: TaxResult) -> bytes:
        """Generate a merged PDF of Form 1040 + active schedules/forms.

        Returns the PDF as bytes.
        """
        filled_buffers: list[tuple[str | None, io.BytesIO]] = []

        for template_name, prefix, map_fn, active_fn in _FORM_REGISTRY:
            if not active_fn(tax_return, result):
                continue
            fields_by_page = map_fn(tax_return, result)
            buf = self._fill_form(template_name, fields_by_page)
            if buf is not None:
                filled_buffers.append((prefix, buf))

        # Merge all filled forms
        final_writer = PdfWriter()
        for prefix, buf in filled_buffers:
            reader = PdfReader(buf)
            if prefix is not None:
                self._rename_fields(reader, prefix)
            final_writer.append(reader)

        output = io.BytesIO()
        final_writer.write(output)
        return output.getvalue()

    def _fill_form(
        self, template_name: str, fields_by_page: dict[int, dict[str, str]]
    ) -> io.BytesIO | None:
        """Fill a single PDF template. Returns BytesIO or None if template missing."""
        path = self.templates_dir / template_name
        if not path.exists():
            return None

        reader = PdfReader(str(path))
        writer = PdfWriter()
        writer.append(reader)

        for page_idx, fields in fields_by_page.items():
            cleaned = {k: v for k, v in fields.items() if v not in (None, "")}
            if cleaned and page_idx < len(writer.pages):
                writer.update_page_form_field_values(writer.pages[page_idx], cleaned)

        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        return buf

    def _rename_fields(self, reader: PdfReader, prefix: str) -> None:
        """Rename AcroForm fields with prefix to avoid collisions in merged PDF."""
        for page in reader.pages:
            annots = page.get("/Annots")
            if annots:
                for annot in annots:
                    obj = annot.get_object()
                    if "/T" in obj:
                        old_name = str(obj["/T"])
                        obj[NameObject("/T")] = TextStringObject(f"{prefix}_{old_name}")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/tax_engine/test_pdf_generator.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/tax_engine/pdf/generator.py tests/api/tax_engine/test_pdf_generator.py
git commit -m "feat(pdf): add PDFGenerator with template filling and form merging"
```

---

## Task 4: API Endpoint + Integration Test

**Files:**
- Modify: `api/routers/tax_returns.py`
- Create: `tests/api/test_pdf_endpoint.py`

- [ ] **Step 1: Add PDF endpoint to router**

Append to `api/routers/tax_returns.py`:

```python
from fastapi.responses import Response
from api.tax_engine.pdf.generator import PDFGenerator


@router.get("/pdf")
async def download_pdf(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    """Generate and download a filled Form 1040 PDF."""
    client = await get_client_or_404(client_id, session, user)

    assembler = DocumentAssembler()
    tax_return = await assembler.assemble(client_id, session)

    import api.tax_engine.constants  # noqa: F401
    from api.tax_engine.constants.registry import get_constants
    constants = get_constants(client.tax_year)
    engine = TaxCalculationEngine(constants)
    result = engine.compute(tax_return)

    generator = PDFGenerator()
    pdf_bytes = generator.generate(tax_return, result)

    safe_name = client.name.replace(" ", "_") if client.name else "client"
    filename = f"1040_{safe_name}_{client.tax_year}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Write integration test**

Create `tests/api/test_pdf_endpoint.py`:

```python
"""Integration test: PDF download endpoint."""
import pytest


@pytest.mark.asyncio
async def test_pdf_download(client):
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 1000


@pytest.mark.asyncio
async def test_pdf_with_documents(client):
    c = await client.post("/api/clients", json={"name": "Smith Family", "filing_status": "mfj", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    await client.patch(f"/api/documents/{did}/approve")
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_pdf_content_disposition(client):
    c = await client.post("/api/clients", json={"name": "John Doe", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/returns/pdf")
    assert "1040_John_Doe_2024.pdf" in resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_pdf_nonexistent_client(client):
    resp = await client.get("/api/clients/9999/returns/pdf")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/test_pdf_endpoint.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/tax_returns.py tests/api/test_pdf_endpoint.py
git commit -m "feat(pdf): add GET /pdf endpoint for Form 1040 PDF download"
```
