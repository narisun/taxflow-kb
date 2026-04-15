# Phase 3B: PDF Form Generation — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Fill IRS PDF templates with computed TaxResult values, merge active forms into a single downloadable PDF

---

## 1. Overview

Generate filled IRS Form 1040 PDFs from computed tax return results. When a CPA requests a PDF, the system fills blank IRS PDF templates with the taxpayer's data and computed values using pypdf's AcroForm field filling, then merges all active forms into a single downloadable PDF. Only forms with relevant data are included.

### Design Principles

- **On-demand generation** — PDF generated per request, not stored. Fast enough (< 1 second) that caching is unnecessary.
- **Active forms only** — Only include schedules/forms that have data. No blank pages.
- **Field mapping from reference** — AcroForm field names sourced from `ustaxes-master/engine/pdf_generator.py` (verified against IRS PDFs).
- **Bundled templates** — Blank IRS PDFs copied into our repo. Updated annually.
- **Testable** — Generator is a pure function of `(TaxReturn, TaxResult)`. No DB or network deps.

---

## 2. Directory Structure

```
api/tax_engine/pdf/
├── __init__.py
├── templates/           # Blank IRS PDF files (TY2024)
│   ├── f1040.pdf
│   ├── f1040sa.pdf      # Schedule A
│   ├── f1040sb.pdf      # Schedule B
│   ├── f1040sc.pdf      # Schedule C (not in reference — use f1040s1.pdf alt or skip)
│   ├── f1040sd.pdf      # Schedule D
│   ├── f1040se.pdf      # Schedule E
│   ├── f1040sse.pdf     # Schedule SE
│   ├── f1040s8.pdf      # Schedule 8812
│   ├── f8959.pdf        # Form 8959
│   ├── f8960.pdf        # Form 8960
│   └── f8995.pdf        # Form 8995
├── field_maps.py        # Per-form field mapping functions
└── generator.py         # PDFGenerator class
```

---

## 3. Components

### 3.1 Templates

Blank IRS PDF files copied from `ustaxes-master/ts-forms/public/forms/Y2024/irs/`. These are official IRS fillable PDFs with AcroForm fields. Only the forms our engine computes are included.

### 3.2 `field_maps.py` — Per-Form Field Mappings

One function per form. Each receives `(TaxReturn, TaxResult)` and returns `dict[int, dict[str, str]]` mapping page index → AcroForm field name → display value.

**Field name convention:** IRS PDFs use names like `f1_32[0]` (page 1, field 32), `f2_02[0]` (page 2, field 2). These are specific to each PDF template version.

**Value formatting:** Dollar amounts formatted as whole numbers with commas (IRS convention). Zero values left blank. Text values as-is.

#### Form 1040 Field Map (2 pages)

Page 1 key fields (from reference `_build_f1040_fields`):
- `f1_04[0]`/`f1_05[0]`/`f1_06[0]` — Primary name, SSN
- `f1_07[0]`/`f1_08[0]`/`f1_09[0]` — Spouse name, SSN
- `f1_10[0]`–`f1_14[0]` — Address
- Filing status checkbox: `c1_1[0]`(S), `c1_2[0]`(MFJ), `c1_3[0]`(MFS), `c1_4[0]`(HOH), `c1_5[0]`(QSS)
- `f1_20[0]`–`f1_31[0]` — Dependents (up to 4 rows: name, SSN, relationship)
- `f1_32[0]` — Line 1a wages
- `f1_43[0]` — Line 2b taxable interest
- `f1_45[0]` — Line 3b ordinary dividends
- `f1_52[0]` — Line 7 capital gain/loss
- `f1_53[0]` — Line 8 other income
- `f1_54[0]` — Line 9 total income
- `f1_55[0]` — Line 10 adjustments
- `f1_56[0]` — Line 11 AGI
- `f1_57[0]` — Line 12 deduction
- `f1_58[0]` — Line 13 QBI deduction
- `f1_60[0]` — Line 15 taxable income

Page 2 key fields:
- `f2_02[0]` — Line 16 tax
- `f2_05[0]` — Line 19 CTC
- `f2_09[0]` — Line 23 other taxes
- `f2_10[0]` — Line 24 total tax
- `f2_11[0]` — Line 25a W-2 withholding
- `f2_15[0]` — Line 26 estimated payments
- `f2_22[0]` — Line 33 total payments
- `f2_24[0]` — Line 35a refund
- `f2_28[0]` — Line 37 amount owed

#### Other Form Field Maps

Each additional form's field map follows the same pattern. Field names are discovered by examining the AcroForm fields in each PDF template (the reference codebase has verified mappings for Schedule A, D, E, Forms 8959, 8960). For forms not in the reference (Schedule B, C, SE, 8812, 8995), field names are extracted from the PDF using pypdf's `PdfReader.get_fields()`.

### 3.3 `generator.py` — PDFGenerator

```python
class PDFGenerator:
    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR

    def generate(self, tax_return: TaxReturn, result: TaxResult) -> bytes:
        """Generate a merged PDF of Form 1040 + active schedules/forms."""
        # 1. Always fill Form 1040
        # 2. Check which other forms are active
        # 3. Fill each active form
        # 4. Merge all filled forms (rename fields to avoid collisions)
        # 5. Return PDF bytes

    def _fill_form(self, template_name: str, fields_by_page: dict) -> io.BytesIO | None:
        """Fill a single PDF template and return as BytesIO."""

    def _rename_fields(self, reader: PdfReader, prefix: str) -> None:
        """Rename AcroForm fields with prefix to avoid collisions in merged PDF."""
```

### 3.4 Active Form Detection

```python
FORM_CHECKERS: list[tuple[str, str, Callable]] = [
    # (template_filename, field_map_function_name, is_active_check)
    ("f1040.pdf",    "map_f1040",      lambda tr, r: True),  # Always
    ("f1040sb.pdf",  "map_schedule_b", lambda tr, r: bool(tr.interest_1099s or tr.dividend_1099s)),
    ("f1040sd.pdf",  "map_schedule_d", lambda tr, r: bool(tr.broker_1099s)),
    ("f1040se.pdf",  "map_schedule_e", lambda tr, r: bool(tr.rental_properties or tr.k1s)),
    ("f1040sa.pdf",  "map_schedule_a", lambda tr, r: _is_itemizing(r)),
    ("f1040sse.pdf", "map_schedule_se",lambda tr, r: _has_se_tax(r)),
    ("f1040s8.pdf",  "map_form_8812", lambda tr, r: _has_ctc(tr)),
    ("f8959.pdf",    "map_form_8959", lambda tr, r: _has_form_result(r, "Form 8959")),
    ("f8960.pdf",    "map_form_8960", lambda tr, r: _has_form_result(r, "Form 8960")),
    ("f8995.pdf",    "map_form_8995", lambda tr, r: _has_form_result(r, "Form 8995")),
]
```

Note: Schedule C PDF (`f1040sc.pdf`) is not in the reference template set. We'll skip Schedule C PDF for now — the Schedule C data flows into Form 1040 Line 8 via Schedule 1. This can be added when we source the template.

---

## 4. API Endpoint

### `GET /api/clients/{client_id}/returns/pdf`

Added to `api/routers/tax_returns.py`.

**Flow:**
1. Load client, verify access
2. Assemble TaxReturn via DocumentAssembler
3. Compute TaxResult via TaxCalculationEngine
4. Generate PDF via PDFGenerator
5. Return as `StreamingResponse` with `Content-Type: application/pdf`

**Response headers:**
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="1040_Smith_Family_2024.pdf"
```

**Error cases:**
- Client not found → 404
- No data to compute → returns Form 1040 with zeros (valid but empty)

---

## 5. Dependencies

Add to `requirements-api.txt`: `pypdf>=4.0`

---

## 6. Testing Strategy

### Unit Tests

- `test_field_maps.py` — verify Form 1040 mapper produces correct field names and values for known inputs
- `test_generator.py` — verify:
  - Generated bytes start with `%PDF`
  - Page count matches number of active forms
  - Empty return produces just Form 1040 (2 pages)
  - Return with capital gains includes Schedule D pages
  - Field collision avoidance works (renamed fields)

### Integration Test

- `test_pdf_endpoint.py` — verify:
  - Endpoint returns 200 with `application/pdf` content type
  - Response body starts with `%PDF`
  - Nonexistent client → 404

---

## 7. Scope Summary

| Component | Type | Description |
|-----------|------|-------------|
| `templates/` | New dir | 10 blank IRS PDF files (TY2024) |
| `field_maps.py` | New | Per-form field mapping functions |
| `generator.py` | New | PDFGenerator with merge + rename |
| `tax_returns.py` | Modified | Add GET /pdf endpoint |
| `requirements-api.txt` | Modified | Add pypdf>=4.0 |
| Test files | 3 new | Field maps, generator, endpoint |

### Out of Scope

- Schedule C PDF (template not available in reference set)
- Schedule 1/2/3 PDFs (supplemental schedules — data flows into 1040)
- E-file (Form 8879) authorization
- MeF XML generation
- PDF visual rendering tests
- Multi-year template support (TY2024 only for now)
