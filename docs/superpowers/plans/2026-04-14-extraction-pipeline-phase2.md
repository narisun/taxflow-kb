# Phase 2: Document Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mock document extraction with Claude Vision-powered extraction that outputs structured JSON matching our Pydantic tax models, so the DocumentAssembler can build TaxReturn objects directly from uploaded documents.

**Architecture:** A `ClaudeVisionExtractor` sends uploaded PDFs/images to Claude's vision API with form-specific prompts. Claude returns structured JSON with field keys matching our Pydantic model fields. A config-driven DI switch selects between mock (dev/test) and Claude (production) extractors. Display labels for the CPA review UI come from a static mapping.

**Tech Stack:** Python 3.12, Anthropic SDK (`anthropic>=0.40`), Pydantic v2, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-extraction-pipeline-phase2-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `api/services/ocr/prompts.py` | Form-specific extraction prompt templates |
| `api/services/ocr/field_mapping.py` | Structured field key → display label mapping |
| `api/services/ocr/claude_extractor.py` | Claude Vision extraction implementation |
| `tests/api/services/__init__.py` | Test package |
| `tests/api/services/ocr/__init__.py` | Test package |
| `tests/api/services/ocr/test_prompts.py` | Prompt coverage tests |
| `tests/api/services/ocr/test_field_mapping.py` | Label mapping tests |
| `tests/api/services/ocr/test_claude_extractor.py` | Extractor tests with mocked Anthropic client |
| `tests/api/services/ocr/test_mock_extractor.py` | Structured format tests for mock |

### Modified Files

| File | Change |
|------|--------|
| `api/models/document.py` | Add `label` field to `ExtractedField` |
| `api/services/ocr/mock_extractor.py` | Return structured format (model field names, clean values) |
| `api/routers/documents.py` | DI extractor selection, structured storage, label mapping on fields endpoint |
| `api/tax_engine/assembler.py` | Handle both old list and new dict formats for backward compat |
| `requirements-api.txt` | Add `anthropic>=0.40` |
| `tests/api/test_documents.py` | Update assertions for structured field names |

---

## Task 1: Form-Specific Prompts

**Files:**
- Create: `api/services/ocr/prompts.py`
- Create: `tests/api/services/__init__.py`
- Create: `tests/api/services/ocr/__init__.py`
- Create: `tests/api/services/ocr/test_prompts.py`

- [ ] **Step 1: Create test packages**

```bash
mkdir -p tests/api/services/ocr
touch tests/api/services/__init__.py
touch tests/api/services/ocr/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `tests/api/services/ocr/test_prompts.py`:

```python
"""Tests for form-specific extraction prompts."""
from api.services.ocr.prompts import get_prompt, SUPPORTED_FORM_TYPES


class TestGetPrompt:
    def test_w2_prompt_contains_field_keys(self):
        prompt = get_prompt("W-2")
        assert "box1_wages" in prompt
        assert "employer_name" in prompt
        assert "employer_ein" in prompt
        assert "box2_fed_withheld" in prompt

    def test_1099_int_prompt(self):
        prompt = get_prompt("1099-INT")
        assert "box1_interest" in prompt
        assert "payer" in prompt

    def test_1099_div_prompt(self):
        prompt = get_prompt("1099-DIV")
        assert "box1a_ordinary_dividends" in prompt
        assert "box1b_qualified_dividends" in prompt

    def test_1099_b_prompt(self):
        prompt = get_prompt("1099-B")
        assert "short_term_proceeds" in prompt
        assert "long_term_proceeds" in prompt

    def test_1099_nec_prompt(self):
        prompt = get_prompt("1099-NEC")
        assert "nec_compensation" in prompt

    def test_1098_prompt(self):
        prompt = get_prompt("1098")
        assert "box1_interest" in prompt
        assert "lender" in prompt

    def test_k1_prompt(self):
        prompt = get_prompt("K-1")
        assert "entity_name" in prompt
        assert "entity_ein" in prompt
        assert "box1_ordinary_income" in prompt

    def test_unknown_form_returns_fallback(self):
        prompt = get_prompt("unknown-form")
        assert "identify" in prompt.lower() or "extract" in prompt.lower()

    def test_all_supported_types_have_prompts(self):
        for form_type in SUPPORTED_FORM_TYPES:
            prompt = get_prompt(form_type)
            assert len(prompt) > 50, f"Prompt for {form_type} is too short"

    def test_all_prompts_request_json_format(self):
        for form_type in SUPPORTED_FORM_TYPES:
            prompt = get_prompt(form_type)
            assert "json" in prompt.lower() or "JSON" in prompt

    def test_all_prompts_mention_confidence(self):
        for form_type in SUPPORTED_FORM_TYPES:
            prompt = get_prompt(form_type)
            assert "confidence" in prompt.lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/api/services/ocr/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement prompts.py**

Create `api/services/ocr/prompts.py`:

```python
"""Form-specific extraction prompts for Claude Vision API."""

SUPPORTED_FORM_TYPES = ["W-2", "1099-INT", "1099-DIV", "1099-B", "1099-NEC", "1098", "K-1"]

_RESPONSE_FORMAT = """
Return ONLY valid JSON in this exact format (no markdown fences, no extra text):
{
  "fields": {
    "field_key": {"value": "extracted_value", "confidence": 0.95},
    ...
  }
}
"""

_COMMON_RULES = """
Rules:
- Return numeric values as plain numbers without $ signs or commas (e.g., "112400.00" not "$112,400.00")
- EINs should be in XX-XXXXXXX format (e.g., "12-3456789")
- For each field, assess your confidence from 0.0 to 1.0
- If a field is not present on the form, omit it from the response
- If a field is partially illegible, include your best guess and set confidence below 0.8
"""

_PROMPTS: dict[str, str] = {
    "W-2": f"""You are extracting data from a US tax form W-2 (Wage and Tax Statement).

Extract the following fields using these exact JSON keys:
- employer_name: Employer's name (box c)
- employer_ein: Employer's EIN (box b), in XX-XXXXXXX format
- box1_wages: Wages, salaries, tips (box 1)
- box2_fed_withheld: Federal income tax withheld (box 2)
- box3_ss_wages: Social Security wages (box 3)
- box4_ss_withheld: Social Security tax withheld (box 4)
- box5_medicare_wages: Medicare wages and tips (box 5)
- box6_medicare_withheld: Medicare tax withheld (box 6)
- box15_state: State abbreviation (box 15)
- box16_state_wages: State wages, tips, etc. (box 16)
- box17_state_withheld: State income tax (box 17)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-INT": f"""You are extracting data from a US tax form 1099-INT (Interest Income).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- box1_interest: Interest income (box 1)
- box4_fed_withheld: Federal income tax withheld (box 4)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-DIV": f"""You are extracting data from a US tax form 1099-DIV (Dividends and Distributions).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- box1a_ordinary_dividends: Total ordinary dividends (box 1a)
- box1b_qualified_dividends: Qualified dividends (box 1b)
- box2a_capital_gain_distributions: Total capital gain distributions (box 2a)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-B": f"""You are extracting data from a US tax form 1099-B (Proceeds from Broker Transactions).

Extract the following fields using these exact JSON keys:
- payer: Broker's name
- short_term_proceeds: Total short-term proceeds (box 1d, short-term)
- short_term_cost_basis: Total short-term cost basis (box 1e, short-term)
- long_term_proceeds: Total long-term proceeds (box 1d, long-term)
- long_term_cost_basis: Total long-term cost basis (box 1e, long-term)

If the form shows individual transactions rather than totals, sum them by holding period (short-term vs long-term).

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-NEC": f"""You are extracting data from a US tax form 1099-NEC (Nonemployee Compensation).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- nec_compensation: Nonemployee compensation (box 1)
- fed_tax_withheld: Federal income tax withheld (box 4)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1098": f"""You are extracting data from a US tax form 1098 (Mortgage Interest Statement).

Extract the following fields using these exact JSON keys:
- lender: Recipient/lender name
- box1_interest: Mortgage interest received (box 1)
- box10_property_taxes: Property taxes (box 10), if present

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "K-1": f"""You are extracting data from a US tax form Schedule K-1 (Partner's or Shareholder's Share of Income).

Extract the following fields using these exact JSON keys:
- entity_name: Partnership or S-Corporation name
- entity_ein: Entity's EIN, in XX-XXXXXXX format
- entity_type: "P" for Partnership (Form 1065) or "S" for S-Corporation (Form 1120-S)
- box1_ordinary_income: Ordinary business income/loss (box 1)
- box2_rental_income: Net rental real estate income/loss (box 2)
- box4a_guaranteed_payments: Guaranteed payments for services (box 4a)
- box14a_se_earnings: Net earnings from self-employment (box 14, code A)
- box20z_section_199a_qbi: Qualified business income (box 20, code Z)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",
}

_FALLBACK_PROMPT = f"""You are extracting data from a US tax document. The exact form type is unknown.

Please:
1. Identify what type of tax form this is
2. Extract all visible numeric values and their labels
3. Use descriptive field keys (e.g., "total_income", "tax_withheld")

{_COMMON_RULES}
{_RESPONSE_FORMAT}"""


def get_prompt(form_type: str) -> str:
    """Return the extraction prompt for the given form type."""
    return _PROMPTS.get(form_type, _FALLBACK_PROMPT)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/services/ocr/test_prompts.py -v`
Expected: All 11 tests PASS

- [ ] **Step 6: Commit**

```bash
git add api/services/ocr/prompts.py tests/api/services/
git commit -m "feat(extraction): add form-specific extraction prompts for Claude Vision"
```

---

## Task 2: Field Mapping (Display Labels)

**Files:**
- Create: `api/services/ocr/field_mapping.py`
- Create: `tests/api/services/ocr/test_field_mapping.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/services/ocr/test_field_mapping.py`:

```python
"""Tests for field display label mapping."""
from api.services.ocr.field_mapping import get_display_label, FIELD_LABELS
from api.services.ocr.prompts import SUPPORTED_FORM_TYPES


class TestGetDisplayLabel:
    def test_w2_wages(self):
        assert get_display_label("W-2", "box1_wages") == "Box 1 — Wages, salaries, tips"

    def test_w2_employer(self):
        assert get_display_label("W-2", "employer_name") == "Employer Name"

    def test_1099_int_interest(self):
        assert get_display_label("1099-INT", "box1_interest") == "Box 1 — Interest income"

    def test_1099_div_qualified(self):
        assert get_display_label("1099-DIV", "box1b_qualified_dividends") == "Box 1b — Qualified dividends"

    def test_k1_entity_name(self):
        assert get_display_label("K-1", "entity_name") == "Entity Name"

    def test_unknown_key_returns_key(self):
        assert get_display_label("W-2", "nonexistent_field") == "nonexistent_field"

    def test_unknown_form_returns_key(self):
        assert get_display_label("unknown-form", "some_field") == "some_field"

    def test_all_supported_forms_have_labels(self):
        for form_type in SUPPORTED_FORM_TYPES:
            assert form_type in FIELD_LABELS, f"No labels for {form_type}"
            assert len(FIELD_LABELS[form_type]) >= 2, f"Too few labels for {form_type}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/services/ocr/test_field_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement field_mapping.py**

Create `api/services/ocr/field_mapping.py`:

```python
"""Maps structured field keys to human-readable display labels for the CPA review UI."""

FIELD_LABELS: dict[str, dict[str, str]] = {
    "W-2": {
        "employer_name": "Employer Name",
        "employer_ein": "Employer EIN",
        "box1_wages": "Box 1 — Wages, salaries, tips",
        "box2_fed_withheld": "Box 2 — Federal income tax withheld",
        "box3_ss_wages": "Box 3 — Social Security wages",
        "box4_ss_withheld": "Box 4 — Social Security tax withheld",
        "box5_medicare_wages": "Box 5 — Medicare wages and tips",
        "box6_medicare_withheld": "Box 6 — Medicare tax withheld",
        "box15_state": "Box 15 — State",
        "box16_state_wages": "Box 16 — State wages, tips",
        "box17_state_withheld": "Box 17 — State income tax",
    },
    "1099-INT": {
        "payer": "Payer Name",
        "box1_interest": "Box 1 — Interest income",
        "box4_fed_withheld": "Box 4 — Federal income tax withheld",
    },
    "1099-DIV": {
        "payer": "Payer Name",
        "box1a_ordinary_dividends": "Box 1a — Total ordinary dividends",
        "box1b_qualified_dividends": "Box 1b — Qualified dividends",
        "box2a_capital_gain_distributions": "Box 2a — Total capital gain distributions",
    },
    "1099-B": {
        "payer": "Broker Name",
        "short_term_proceeds": "Short-term proceeds",
        "short_term_cost_basis": "Short-term cost basis",
        "long_term_proceeds": "Long-term proceeds",
        "long_term_cost_basis": "Long-term cost basis",
    },
    "1099-NEC": {
        "payer": "Payer Name",
        "nec_compensation": "Box 1 — Nonemployee compensation",
        "fed_tax_withheld": "Box 4 — Federal income tax withheld",
    },
    "1098": {
        "lender": "Lender Name",
        "box1_interest": "Box 1 — Mortgage interest received",
        "box10_property_taxes": "Box 10 — Property taxes",
    },
    "K-1": {
        "entity_name": "Entity Name",
        "entity_ein": "Entity EIN",
        "entity_type": "Entity Type (P=Partnership, S=S-Corp)",
        "box1_ordinary_income": "Box 1 — Ordinary business income/loss",
        "box2_rental_income": "Box 2 — Net rental real estate income/loss",
        "box4a_guaranteed_payments": "Box 4a — Guaranteed payments",
        "box14a_se_earnings": "Box 14a — Self-employment earnings",
        "box20z_section_199a_qbi": "Box 20 Code Z — Section 199A QBI",
    },
}


def get_display_label(form_type: str, field_key: str) -> str:
    """Return human-readable label for a structured field key."""
    return FIELD_LABELS.get(form_type, {}).get(field_key, field_key)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/services/ocr/test_field_mapping.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/ocr/field_mapping.py tests/api/services/ocr/test_field_mapping.py
git commit -m "feat(extraction): add field display label mapping for CPA review UI"
```

---

## Task 3: Update Mock Extractor to Structured Format

**Files:**
- Modify: `api/services/ocr/mock_extractor.py`
- Modify: `api/models/document.py`
- Create: `tests/api/services/ocr/test_mock_extractor.py`

- [ ] **Step 1: Write failing tests for updated mock**

Create `tests/api/services/ocr/test_mock_extractor.py`:

```python
"""Tests for mock extractor — structured format."""
import pytest
from api.services.ocr.mock_extractor import MockOCRExtractor


@pytest.fixture
def extractor():
    return MockOCRExtractor()


class TestMockExtractor:
    @pytest.mark.asyncio
    async def test_w2_returns_structured_keys(self, extractor):
        result = await extractor.extract("fake.pdf", "W-2")
        field_names = [f.name for f in result.fields]
        assert "box1_wages" in field_names
        assert "employer_name" in field_names
        assert "box2_fed_withheld" in field_names

    @pytest.mark.asyncio
    async def test_w2_values_are_clean_numbers(self, extractor):
        result = await extractor.extract("fake.pdf", "W-2")
        wages = next(f for f in result.fields if f.name == "box1_wages")
        assert "$" not in wages.value
        assert "," not in wages.value

    @pytest.mark.asyncio
    async def test_1099_int_has_flag(self, extractor):
        result = await extractor.extract("fake.pdf", "1099-INT")
        assert result.has_flags is True
        flagged = [f for f in result.fields if f.flagged]
        assert len(flagged) >= 1

    @pytest.mark.asyncio
    async def test_1099_div_structured(self, extractor):
        result = await extractor.extract("fake.pdf", "1099-DIV")
        field_names = [f.name for f in result.fields]
        assert "box1a_ordinary_dividends" in field_names

    @pytest.mark.asyncio
    async def test_1099_b_structured(self, extractor):
        result = await extractor.extract("fake.pdf", "1099-B")
        field_names = [f.name for f in result.fields]
        assert "short_term_proceeds" in field_names or "long_term_proceeds" in field_names

    @pytest.mark.asyncio
    async def test_1099_nec_structured(self, extractor):
        result = await extractor.extract("fake.pdf", "1099-NEC")
        field_names = [f.name for f in result.fields]
        assert "nec_compensation" in field_names

    @pytest.mark.asyncio
    async def test_1098_structured(self, extractor):
        result = await extractor.extract("fake.pdf", "1098")
        field_names = [f.name for f in result.fields]
        assert "box1_interest" in field_names
        assert "lender" in field_names

    @pytest.mark.asyncio
    async def test_k1_structured(self, extractor):
        result = await extractor.extract("fake.pdf", "K-1")
        field_names = [f.name for f in result.fields]
        assert "entity_name" in field_names
        assert "box1_ordinary_income" in field_names

    @pytest.mark.asyncio
    async def test_unknown_form(self, extractor):
        result = await extractor.extract("fake.pdf", "unknown")
        assert result.overall_confidence == 0.0

    @pytest.mark.asyncio
    async def test_structured_data_dict(self, extractor):
        """Verify structured_data returns model-ready dict."""
        result = await extractor.extract("fake.pdf", "W-2")
        data = result.structured_data
        assert isinstance(data, dict)
        assert "box1_wages" in data
        assert "$" not in data["box1_wages"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/services/ocr/test_mock_extractor.py -v`
Expected: FAIL

- [ ] **Step 3: Update document models**

Modify `api/models/document.py` — add `label` field to `ExtractedField` and `structured_data` property to `ExtractionResult`:

```python
"""Document-related Pydantic schemas."""
from pydantic import BaseModel
from datetime import datetime

from api.models.enums import FormType, DocumentStatus


class DocumentResponse(BaseModel):
    id: int
    client_id: int
    form_type: str
    title: str
    status: str
    confidence: float
    extracted_data: str  # JSON string
    flags: str  # JSON string
    created_at: datetime
    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ExtractedField(BaseModel):
    name: str               # Structured key: "box1_wages"
    value: str              # Clean value: "112400.00"
    confidence: float
    flagged: bool = False
    flag_reason: str = ""
    label: str = ""         # Display label, populated by router


class ExtractionResult(BaseModel):
    fields: list[ExtractedField]
    overall_confidence: float
    has_flags: bool
    flags: list[str]

    @property
    def structured_data(self) -> dict[str, str]:
        """Return model-ready dict of field name → value."""
        return {f.name: f.value for f in self.fields}
```

- [ ] **Step 4: Rewrite mock_extractor.py with structured format**

```python
"""Mock OCR extractor for development — returns structured data matching Pydantic model fields."""
from api.models.document import ExtractionResult, ExtractedField


class MockOCRExtractor:
    async def extract(self, file_path: str, form_type: str) -> ExtractionResult:
        """Return realistic mock data using structured field keys."""
        if form_type == "W-2":
            fields = [
                ExtractedField(name="box1_wages", value="112400.00", confidence=0.99),
                ExtractedField(name="box2_fed_withheld", value="18750.00", confidence=0.99),
                ExtractedField(name="employer_name", value="ACME CORPORATION", confidence=0.97),
                ExtractedField(name="employer_ein", value="12-3456789", confidence=0.95),
                ExtractedField(name="box3_ss_wages", value="112400.00", confidence=0.98),
                ExtractedField(name="box5_medicare_wages", value="112400.00", confidence=0.98),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1099-INT":
            fields = [
                ExtractedField(name="payer", value="CHASE BANK", confidence=0.96),
                ExtractedField(name="box1_interest", value="3847.00", confidence=0.96),
                ExtractedField(
                    name="box4_fed_withheld", value="0.00", confidence=0.82,
                    flagged=True, flag_reason="Value partially illegible",
                ),
            ]
            return ExtractionResult(
                fields=fields, overall_confidence=0.82, has_flags=True,
                flags=["box4_fed_withheld: 82% confidence"],
            )

        elif form_type == "1099-DIV":
            fields = [
                ExtractedField(name="payer", value="VANGUARD", confidence=0.97),
                ExtractedField(name="box1a_ordinary_dividends", value="5200.00", confidence=0.95),
                ExtractedField(name="box1b_qualified_dividends", value="4100.00", confidence=0.95),
                ExtractedField(name="box2a_capital_gain_distributions", value="1200.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "1099-B":
            fields = [
                ExtractedField(name="payer", value="FIDELITY INVESTMENTS", confidence=0.94),
                ExtractedField(name="short_term_proceeds", value="15200.00", confidence=0.91),
                ExtractedField(name="short_term_cost_basis", value="13800.00", confidence=0.91),
                ExtractedField(name="long_term_proceeds", value="52300.00", confidence=0.94),
                ExtractedField(name="long_term_cost_basis", value="48100.00", confidence=0.91),
            ]
            return ExtractionResult(
                fields=fields, overall_confidence=0.91, has_flags=False, flags=[],
            )

        elif form_type == "1099-NEC":
            fields = [
                ExtractedField(name="payer", value="CONSULTING CLIENT INC", confidence=0.95),
                ExtractedField(name="nec_compensation", value="25000.00", confidence=0.97),
                ExtractedField(name="fed_tax_withheld", value="0.00", confidence=0.99),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1098":
            fields = [
                ExtractedField(name="lender", value="FIRST NATIONAL BANK", confidence=0.95),
                ExtractedField(name="box1_interest", value="14220.00", confidence=0.98),
                ExtractedField(name="box10_property_taxes", value="6800.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "K-1":
            fields = [
                ExtractedField(name="entity_name", value="SMITH HOLDINGS LLC", confidence=0.93),
                ExtractedField(name="entity_ein", value="98-7654321", confidence=0.90),
                ExtractedField(name="entity_type", value="P", confidence=0.95),
                ExtractedField(name="box1_ordinary_income", value="8400.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.90, has_flags=False, flags=[])

        return ExtractionResult(fields=[], overall_confidence=0.0, has_flags=False, flags=[])
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/services/ocr/test_mock_extractor.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add api/services/ocr/mock_extractor.py api/models/document.py tests/api/services/ocr/test_mock_extractor.py
git commit -m "feat(extraction): update mock extractor to structured format with model field keys"
```

---

## Task 4: Update Documents Router (Structured Storage + DI + Label Mapping)

**Files:**
- Modify: `api/routers/documents.py`
- Modify: `tests/api/test_documents.py`

- [ ] **Step 1: Update the documents router**

Rewrite `api/routers/documents.py`:

```python
"""Document management endpoints."""
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import DocumentModel
from api.models.document import (
    DocumentResponse,
    DocumentListResponse,
    ExtractedField,
    ExtractionResult,
)
from api.models.enums import FormType
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel
from api.routers._helpers import get_client_or_404
from api.services.ocr.protocol import OCRExtractor
from api.services.ocr.field_mapping import get_display_label

router = APIRouter(prefix="/api", tags=["documents"])

UPLOAD_DIR = Path("uploads")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


def _get_ocr_extractor() -> OCRExtractor:
    """Select extractor based on config. Default: mock for dev/test."""
    if os.getenv("OCR_EXTRACTOR", "mock") == "claude":
        import anthropic
        from api.services.ocr.claude_extractor import ClaudeVisionExtractor
        return ClaudeVisionExtractor(anthropic.Anthropic())
    from api.services.ocr.mock_extractor import MockOCRExtractor
    return MockOCRExtractor()


_ocr = _get_ocr_extractor()


def _sanitize_filename(filename: str) -> str:
    """Remove path separators and dangerous characters from a filename."""
    name = os.path.basename(filename)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "upload"


@router.get("/clients/{client_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    client_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    base = select(DocumentModel).where(
        DocumentModel.client_id == client_id,
        DocumentModel.org_id == user.org_id,
    )
    count_q = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    paginated = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(paginated)
    docs = result.scalars().all()
    return DocumentListResponse(items=docs, total=total, page=page, page_size=page_size)


@router.post(
    "/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    client_id: int,
    form_type: FormType = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{file.content_type}' not allowed. Accepted: PDF, PNG, JPEG, TIFF.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    # Save file first so extractor can read it
    safe_name = _sanitize_filename(file.filename or "upload")

    # Run extraction
    extraction = await _ocr.extract("", form_type)

    # Store as structured JSON dict (model-ready)
    extracted_data = json.dumps(extraction.structured_data)
    flags = json.dumps(extraction.flags)
    confidence = extraction.overall_confidence

    has_flags = extraction.has_flags
    doc_status = "review" if (has_flags or confidence < 0.90) else "verified"

    doc = DocumentModel(
        client_id=client_id,
        form_type=form_type,
        title=f"{form_type} ({safe_name})",
        status=doc_status,
        confidence=confidence,
        extracted_data=extracted_data,
        flags=flags,
        org_id=user.org_id,
        created_by=user.id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    doc_dir = UPLOAD_DIR / str(doc.id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / safe_name
    file_path.write_bytes(content)

    doc.file_path = str(file_path)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/documents/{doc_id}/approve", response_model=DocumentResponse)
async def approve_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(require_role("admin", "supervisor", "preparer")),
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "approved"
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/documents/{doc_id}/fields", response_model=list[ExtractedField])
async def get_document_fields(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        select(DocumentModel).where(
            DocumentModel.id == doc_id,
            DocumentModel.org_id == user.org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        raw = json.loads(doc.extracted_data)
    except (json.JSONDecodeError, TypeError):
        raw = {}

    # Handle both structured dict format (new) and list format (legacy)
    if isinstance(raw, dict):
        fields = []
        for key, value in raw.items():
            label = get_display_label(doc.form_type, key)
            fields.append(ExtractedField(
                name=key, value=str(value), confidence=doc.confidence,
                label=label,
            ))
        return fields
    elif isinstance(raw, list):
        # Legacy format: list of ExtractedField dicts
        return [ExtractedField(**f) for f in raw]
    return []
```

- [ ] **Step 2: Update document tests**

Rewrite `tests/api/test_documents.py`:

```python
"""Tests for document management endpoints."""
import pytest


@pytest.mark.asyncio
async def test_upload_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake-pdf", "application/pdf")},
    )
    assert resp.status_code == 201
    assert resp.json()["form_type"] == "W-2"


@pytest.mark.asyncio
async def test_upload_document_1099int(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "1099-INT"},
        files={"file": ("1099int.pdf", b"fake-pdf", "application/pdf")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["form_type"] == "1099-INT"
    assert body["confidence"] < 1.0


@pytest.mark.asyncio
async def test_list_documents(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    resp = await client.get(f"/api/clients/{cid}/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_documents_empty(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.get(f"/api/clients/{cid}/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}")
    assert resp.status_code == 200
    assert resp.json()["id"] == did


@pytest.mark.asyncio
async def test_get_document_not_found(client):
    resp = await client.get("/api/documents/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_document(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.patch(f"/api/documents/{did}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_get_fields_structured(client):
    """Verify fields endpoint returns structured keys with display labels."""
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}/fields")
    assert resp.status_code == 200
    fields = resp.json()
    assert len(fields) >= 3
    # Verify structured key names
    names = [f["name"] for f in fields]
    assert "box1_wages" in names
    assert "employer_name" in names
    # Verify display labels populated
    wages_field = next(f for f in fields if f["name"] == "box1_wages")
    assert wages_field["label"] == "Box 1 — Wages, salaries, tips"


@pytest.mark.asyncio
async def test_get_fields_1099int_has_flags(client):
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "1099-INT"},
        files={"file": ("1099int.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}/fields")
    assert resp.status_code == 200
    fields = resp.json()
    assert len(fields) >= 2


@pytest.mark.asyncio
async def test_upload_to_nonexistent_client(client):
    resp = await client.post(
        "/api/clients/9999/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extracted_data_is_structured_dict(client):
    """Verify extracted_data stored as structured JSON dict, not display field list."""
    import json
    c = await client.post("/api/clients", json={"name": "Test", "tax_year": 2024})
    cid = c.json()["id"]
    doc = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake", "application/pdf")},
    )
    did = doc.json()["id"]
    resp = await client.get(f"/api/documents/{did}")
    data = json.loads(resp.json()["extracted_data"])
    assert isinstance(data, dict)
    assert "box1_wages" in data
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/api/test_documents.py -v`
Expected: All 12 tests PASS

- [ ] **Step 4: Run full API test suite for regressions**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/documents.py tests/api/test_documents.py
git commit -m "feat(extraction): update documents router — structured storage, DI, label mapping"
```

---

## Task 5: Update Assembler for Backward Compatibility

**Files:**
- Modify: `api/tax_engine/assembler.py`

- [ ] **Step 1: Update assembler to handle both formats**

The assembler's `json.loads(doc.extracted_data)` currently expects a dict. With the old format it was a list. Add format detection:

In `api/tax_engine/assembler.py`, replace the `data = json.loads(...)` block (around line 59) with:

```python
            raw = json.loads(doc.extracted_data) if doc.extracted_data else {}

            # Handle both structured dict (new) and list of ExtractedField dicts (legacy)
            if isinstance(raw, list):
                # Legacy format: convert [{name: "box1_wages", value: "112400"}, ...] to dict
                data = {}
                for item in raw:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        data[item["name"]] = item["value"]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
```

- [ ] **Step 2: Run assembler tests**

Run: `python -m pytest tests/api/tax_engine/test_assembler.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add api/tax_engine/assembler.py
git commit -m "fix(assembler): handle both structured dict and legacy list formats"
```

---

## Task 6: Claude Vision Extractor

**Files:**
- Create: `api/services/ocr/claude_extractor.py`
- Create: `tests/api/services/ocr/test_claude_extractor.py`
- Modify: `requirements-api.txt`

- [ ] **Step 1: Add anthropic dependency**

Append to `requirements-api.txt`:

```
# Document extraction
anthropic>=0.40
```

- [ ] **Step 2: Write failing tests with mocked Anthropic client**

Create `tests/api/services/ocr/test_claude_extractor.py`:

```python
"""Tests for Claude Vision extractor with mocked Anthropic client."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.ocr.claude_extractor import ClaudeVisionExtractor


def _make_claude_response(fields_json: dict) -> MagicMock:
    """Create a mock Claude API response."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps({"fields": fields_json})
    response.content = [content_block]
    return response


def _mock_client(fields_json: dict) -> MagicMock:
    """Create a mock Anthropic client that returns the given fields."""
    client = MagicMock()
    client.messages.create.return_value = _make_claude_response(fields_json)
    return client


class TestClaudeVisionExtractor:
    @pytest.mark.asyncio
    async def test_w2_extraction(self, tmp_path):
        fields = {
            "box1_wages": {"value": "85000.00", "confidence": 0.99},
            "employer_name": {"value": "ACME CORP", "confidence": 0.97},
            "employer_ein": {"value": "12-3456789", "confidence": 0.95},
        }
        client = _mock_client(fields)
        extractor = ClaudeVisionExtractor(client)

        pdf_file = tmp_path / "w2.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        result = await extractor.extract(str(pdf_file), "W-2")
        assert len(result.fields) == 3
        assert result.structured_data["box1_wages"] == "85000.00"
        assert result.overall_confidence == 0.95
        assert result.has_flags is False

    @pytest.mark.asyncio
    async def test_low_confidence_flagged(self, tmp_path):
        fields = {
            "box1_interest": {"value": "3847.00", "confidence": 0.95},
            "payer": {"value": "CHASE", "confidence": 0.72},
        }
        client = _mock_client(fields)
        extractor = ClaudeVisionExtractor(client)

        pdf_file = tmp_path / "1099.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        result = await extractor.extract(str(pdf_file), "1099-INT")
        assert result.has_flags is True
        flagged = [f for f in result.fields if f.flagged]
        assert len(flagged) == 1
        assert flagged[0].name == "payer"

    @pytest.mark.asyncio
    async def test_image_file_detected(self, tmp_path):
        fields = {"box1_wages": {"value": "50000.00", "confidence": 0.90}}
        client = _mock_client(fields)
        extractor = ClaudeVisionExtractor(client)

        img_file = tmp_path / "w2.png"
        img_file.write_bytes(b"\x89PNG fake image")

        result = await extractor.extract(str(img_file), "W-2")
        # Verify the API was called with image type
        call_args = client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        media_block = content[0]
        assert media_block["type"] == "image"

    @pytest.mark.asyncio
    async def test_pdf_file_detected(self, tmp_path):
        fields = {"box1_wages": {"value": "50000.00", "confidence": 0.90}}
        client = _mock_client(fields)
        extractor = ClaudeVisionExtractor(client)

        pdf_file = tmp_path / "w2.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        result = await extractor.extract(str(pdf_file), "W-2")
        call_args = client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        media_block = content[0]
        assert media_block["type"] == "document"

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, tmp_path):
        """Claude returns garbage — should return empty result with flag."""
        client = MagicMock()
        response = MagicMock()
        content_block = MagicMock()
        content_block.text = "This is not valid JSON at all"
        response.content = [content_block]
        client.messages.create.return_value = response

        extractor = ClaudeVisionExtractor(client)
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        result = await extractor.extract(str(pdf_file), "W-2")
        assert len(result.fields) == 0
        assert result.has_flags is True
        assert any("failed" in f.lower() or "manual" in f.lower() for f in result.flags)

    @pytest.mark.asyncio
    async def test_correct_prompt_selected(self, tmp_path):
        fields = {"payer": {"value": "CHASE", "confidence": 0.95}}
        client = _mock_client(fields)
        extractor = ClaudeVisionExtractor(client)

        pdf_file = tmp_path / "form.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        await extractor.extract(str(pdf_file), "1099-INT")
        call_args = client.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "1099-INT" in prompt_text
        assert "box1_interest" in prompt_text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/api/services/ocr/test_claude_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement claude_extractor.py**

Create `api/services/ocr/claude_extractor.py`:

```python
"""Claude Vision extractor — sends PDFs/images to Claude API for structured extraction."""
import base64
import json
import mimetypes
from pathlib import Path

from api.models.document import ExtractionResult, ExtractedField
from api.services.ocr.prompts import get_prompt

CONFIDENCE_FLAG_THRESHOLD = 0.90
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Map file extensions to media types and Claude content block types
_MEDIA_TYPES = {
    ".pdf": ("application/pdf", "document"),
    ".png": ("image/png", "image"),
    ".jpg": ("image/jpeg", "image"),
    ".jpeg": ("image/jpeg", "image"),
    ".tiff": ("image/tiff", "image"),
    ".tif": ("image/tiff", "image"),
}


class ClaudeVisionExtractor:
    """Extracts tax form data using Claude Vision API."""

    def __init__(self, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def extract(self, file_path: str, form_type: str) -> ExtractionResult:
        """Extract structured data from a tax document."""
        path = Path(file_path)
        file_bytes = path.read_bytes()
        b64_data = base64.standard_b64encode(file_bytes).decode("utf-8")

        # Determine media type and content block type
        suffix = path.suffix.lower()
        media_type, block_type = _MEDIA_TYPES.get(suffix, ("application/pdf", "document"))

        prompt = get_prompt(form_type)

        # Build the API request
        media_block = {
            "type": block_type,
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        }
        text_block = {"type": "text", "text": prompt}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [media_block, text_block],
                }],
            )
        except Exception:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — API error. Manual entry required."],
            )

        # Parse response
        raw_text = response.content[0].text if response.content else ""
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> ExtractionResult:
        """Parse Claude's JSON response into ExtractionResult."""
        # Try to extract JSON from the response (handle markdown fences)
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — invalid response. Manual entry required."],
            )

        fields_data = parsed.get("fields", {})
        if not isinstance(fields_data, dict):
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — unexpected format. Manual entry required."],
            )

        fields: list[ExtractedField] = []
        min_confidence = 1.0
        has_flags = False
        flag_messages: list[str] = []

        for key, info in fields_data.items():
            if isinstance(info, dict):
                value = str(info.get("value", ""))
                confidence = float(info.get("confidence", 0.0))
            else:
                value = str(info)
                confidence = 0.5

            flagged = confidence < CONFIDENCE_FLAG_THRESHOLD
            flag_reason = ""
            if flagged:
                has_flags = True
                flag_reason = f"Low confidence ({confidence:.0%})"
                flag_messages.append(f"{key}: {confidence:.0%} confidence")

            min_confidence = min(min_confidence, confidence)
            fields.append(ExtractedField(
                name=key, value=value, confidence=confidence,
                flagged=flagged, flag_reason=flag_reason,
            ))

        overall = min_confidence if fields else 0.0
        return ExtractionResult(
            fields=fields, overall_confidence=overall,
            has_flags=has_flags, flags=flag_messages,
        )
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/services/ocr/test_claude_extractor.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/services/ocr/claude_extractor.py tests/api/services/ocr/test_claude_extractor.py requirements-api.txt
git commit -m "feat(extraction): add ClaudeVisionExtractor with form-specific prompts"
```

---

## Task 7: Integration Test — End-to-End Upload → Assembler

**Files:**
- Create: `tests/api/test_extraction_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/api/test_extraction_integration.py`:

```python
"""Integration test: upload document → structured extraction → assembler builds TaxReturn."""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.base import Base
from api.db.models import ClientModel, DocumentModel
from api.auth.models import OrganizationModel, UserModel
from api.tax_engine.assembler import DocumentAssembler


@pytest.fixture
async def db_with_extracted_doc():
    """Set up DB with a client and an approved W-2 document in structured format."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        org = OrganizationModel(name="Test CPA", slug="test-cpa", plan="professional")
        session.add(org)
        await session.flush()
        user = UserModel(org_id=org.id, auth0_sub="dev|test", email="t@t.com", name="Test", role="admin")
        session.add(user)
        await session.flush()
        client = ClientModel(org_id=org.id, created_by=user.id, name="John Doe",
                             filing_status="single", tax_year=2024)
        session.add(client)
        await session.flush()

        # Structured extracted_data (as the new pipeline produces)
        structured_data = {
            "employer_name": "ACME CORPORATION",
            "employer_ein": "12-3456789",
            "box1_wages": "112400.00",
            "box2_fed_withheld": "18750.00",
            "box3_ss_wages": "112400.00",
            "box5_medicare_wages": "112400.00",
        }
        doc = DocumentModel(
            org_id=org.id, created_by=user.id, client_id=client.id,
            form_type="W-2", title="W-2 (w2.pdf)",
            status="approved", confidence=0.95,
            extracted_data=json.dumps(structured_data),
        )
        session.add(doc)
        await session.commit()
        yield session, client.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_assembler_reads_structured_data(db_with_extracted_doc):
    """Verify DocumentAssembler can build a TaxReturn from structured extracted_data."""
    session, client_id = db_with_extracted_doc
    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)

    assert len(tr.w2s) == 1
    w2 = tr.w2s[0]
    assert w2.employer_name == "ACME CORPORATION"
    assert w2.employer_ein == "12-3456789"
    assert str(w2.box1_wages) == "112400.00"
    assert str(w2.box2_fed_withheld) == "18750.00"


@pytest.mark.asyncio
async def test_assembler_handles_legacy_list_format(db_with_extracted_doc):
    """Verify assembler still works with old list-of-dicts format."""
    session, client_id = db_with_extracted_doc

    # Overwrite with legacy format
    result = await session.execute(
        select(DocumentModel).where(DocumentModel.client_id == client_id))
    doc = result.scalar_one()
    doc.extracted_data = json.dumps([
        {"name": "employer_name", "value": "LEGACY CORP"},
        {"name": "employer_ein", "value": "99-8888888"},
        {"name": "box1_wages", "value": "50000.00"},
    ])
    await session.commit()

    assembler = DocumentAssembler()
    tr = await assembler.assemble(client_id, session)
    assert len(tr.w2s) == 1
    assert tr.w2s[0].employer_name == "LEGACY CORP"


@pytest.mark.asyncio
async def test_full_pipeline_upload_to_computation(client):
    """Upload → extract → approve → compute draft — end-to-end via API."""
    # Create client
    c = await client.post("/api/clients", json={"name": "Test User", "filing_status": "single", "tax_year": 2024})
    cid = c.json()["id"]

    # Upload W-2
    doc_resp = await client.post(
        f"/api/clients/{cid}/documents",
        data={"form_type": "W-2"},
        files={"file": ("w2.pdf", b"fake-pdf", "application/pdf")},
    )
    assert doc_resp.status_code == 201
    did = doc_resp.json()["id"]

    # Verify structured data stored
    detail = await client.get(f"/api/documents/{did}")
    data = json.loads(detail.json()["extracted_data"])
    assert isinstance(data, dict)
    assert "box1_wages" in data

    # Approve
    await client.patch(f"/api/documents/{did}/approve")

    # Generate draft — should use engine with assembled data
    draft_resp = await client.post(f"/api/clients/{cid}/returns/draft")
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert draft["total_income"] > 0  # Should have income from the mock W-2
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/api/test_extraction_integration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Run full suite**

Run: `python -m pytest tests/api/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_extraction_integration.py
git commit -m "test(extraction): add end-to-end integration tests — upload to computation"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest tests/api/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no regressions in tax engine tests**

Run: `python -m pytest tests/api/tax_engine/ -v`
Expected: All ~100+ tests PASS

- [ ] **Step 3: Final commit**

```bash
git add -A
git status
# Only commit if there are uncommitted changes
git commit -m "feat(extraction): Phase 2 complete — Claude Vision extraction pipeline"
```
