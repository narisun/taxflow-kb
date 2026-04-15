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
