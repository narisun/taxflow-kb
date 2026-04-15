# Phase 2: Document Extraction Pipeline — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Replace MockOCRExtractor with Claude Vision extraction, structured data storage, form-specific prompts, field mapping for CPA review UI

---

## 1. Overview

Replace the mock document extraction with real Claude Vision-powered extraction. When a CPA uploads a tax document (PDF or image), the system sends it to Claude's vision API with a form-specific prompt, receives structured JSON matching our Pydantic tax model fields, and stores it for the DocumentAssembler (Phase 1) to consume directly.

### Design Principles

- **Single extraction backend** — Claude Vision handles fillable PDFs, text PDFs, and scanned images equally. No local PDF libraries needed yet.
- **Structured-first storage** — `extracted_data` stores model-ready JSON (`{"box1_wages": "112400"}`), not display-oriented fields. Display labels derived from a mapping.
- **Graceful degradation** — Low-confidence fields are included with flags. Documents with any low-confidence field go to "review" status for CPA correction.
- **Testability** — Anthropic client injected via constructor. Mock extractor updated to match new structured format for dev/test.
- **Backward compatible** — `OCRExtractor` protocol unchanged. Swap is config-driven.

---

## 2. Directory Structure

```
api/services/ocr/
├── protocol.py              # OCRExtractor protocol (unchanged)
├── mock_extractor.py         # Updated: returns structured format
├── claude_extractor.py       # NEW: Claude Vision extraction
├── prompts.py                # NEW: form-specific extraction prompts
└── field_mapping.py          # NEW: structured key → display label mapping
```

---

## 3. Components

### 3.1 `claude_extractor.py` — ClaudeVisionExtractor

```python
class ClaudeVisionExtractor:
    """Extracts tax form data using Claude Vision API."""

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    async def extract(self, file_path: str, form_type: str) -> ExtractionResult:
        """
        1. Read file bytes from file_path
        2. Determine media type (PDF → application/pdf, else image/*)
        3. Base64-encode the file content
        4. Get the form-specific prompt from prompts.py
        5. Call Claude API: messages.create() with vision content
        6. Parse the JSON response into structured fields
        7. Compute per-field confidence from Claude's self-assessment
        8. Build and return ExtractionResult
        """
```

**Claude API call structure:**

```python
response = self.client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "document",       # For PDFs
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    }],
)
```

For image files (PNG, JPEG, TIFF), use `"type": "image"` instead of `"type": "document"`.

**Response parsing:**

Claude is prompted to return JSON in this exact format:

```json
{
  "fields": {
    "box1_wages": {"value": "112400.00", "confidence": 0.99},
    "box2_fed_withheld": {"value": "18750.00", "confidence": 0.99},
    "employer_name": {"value": "ACME CORPORATION", "confidence": 0.97},
    "employer_ein": {"value": "12-3456789", "confidence": 0.95}
  }
}
```

The extractor converts this to:
- `extracted_data` JSON: `{"box1_wages": "112400.00", "employer_name": "ACME CORPORATION", ...}` (values only, for assembler)
- `ExtractionResult.fields`: list of `ExtractedField` with name, value, confidence, and flag info
- `overall_confidence`: minimum confidence across all fields
- `has_flags`: true if any field confidence < 0.90

### 3.2 `prompts.py` — Form-Specific Extraction Prompts

One prompt function per form type. Each prompt:
- Identifies the form type and lists exact fields to extract
- Specifies JSON keys matching our Pydantic model field names
- Instructs Claude to return numeric values without `$` or `,` formatting
- Asks Claude to self-assess confidence per field (0.0 to 1.0)
- Includes a fallback for unreadable fields

**Supported form types and their fields:**

| Form Type | JSON Keys to Extract |
|-----------|---------------------|
| W-2 | `employer_name`, `employer_ein`, `box1_wages`, `box2_fed_withheld`, `box3_ss_wages`, `box4_ss_withheld`, `box5_medicare_wages`, `box6_medicare_withheld`, `box15_state`, `box16_state_wages`, `box17_state_withheld` |
| 1099-INT | `payer`, `box1_interest`, `box4_fed_withheld` |
| 1099-DIV | `payer`, `box1a_ordinary_dividends`, `box1b_qualified_dividends`, `box2a_capital_gain_distributions` |
| 1099-B | `payer`, `short_term_proceeds`, `short_term_cost_basis`, `long_term_proceeds`, `long_term_cost_basis` |
| 1099-NEC | `payer`, `nec_compensation`, `fed_tax_withheld` |
| 1098 | `lender`, `box1_interest`, `box10_property_taxes` |
| K-1 | `entity_name`, `entity_ein`, `entity_type`, `box1_ordinary_income`, `box2_rental_income`, `box4a_guaranteed_payments`, `box14a_se_earnings`, `box20z_section_199a_qbi` |

**Prompt template structure:**

```python
def get_prompt(form_type: str) -> str:
    """Return the extraction prompt for the given form type."""
```

Each prompt follows this pattern:

```
You are extracting data from a US tax form ({form_type}).

Extract the following fields and return them as JSON. Use these exact keys:
{field_list_with_descriptions}

Rules:
- Return numeric values as plain numbers without $ signs or commas (e.g., "112400.00" not "$112,400.00")
- EINs should be in XX-XXXXXXX format
- For each field, assess your confidence from 0.0 to 1.0
- If a field is not present on the form, omit it from the response
- If a field is partially illegible, include your best guess and set confidence below 0.8

Return ONLY valid JSON in this format:
{
  "fields": {
    "field_key": {"value": "extracted_value", "confidence": 0.95},
    ...
  }
}
```

A `get_prompt("unknown")` fallback returns a generic prompt asking Claude to identify the form type and extract whatever fields it can find.

### 3.3 `field_mapping.py` — Display Label Mapping

Simple dict-of-dicts mapping `(form_type, field_key)` → human-readable label:

```python
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
        "box16_state_wages": "Box 16 — State wages",
        "box17_state_withheld": "Box 17 — State income tax",
    },
    "1099-INT": {
        "payer": "Payer Name",
        "box1_interest": "Box 1 — Interest income",
        "box4_fed_withheld": "Box 4 — Federal income tax withheld",
    },
    # ... etc for all form types
}

def get_display_label(form_type: str, field_key: str) -> str:
    """Return human-readable label for a structured field key."""
    return FIELD_LABELS.get(form_type, {}).get(field_key, field_key)
```

### 3.4 Updated `mock_extractor.py`

The mock extractor is updated to return structured data matching the new format. Same hardcoded values, but using model field names as keys instead of display labels:

```python
# Before: ExtractedField(name="Box 1 — Wages", value="$112,400.00", confidence=0.99)
# After:  ExtractedField(name="box1_wages", value="112400.00", confidence=0.99)
```

This keeps dev/test working without API calls. Existing tests updated to match.

---

## 4. Modifications to Existing Files

### 4.1 `api/models/document.py`

`ExtractedField` updated — `name` now holds the structured field key. Add a `display_label` computed property or optional field:

```python
class ExtractedField(BaseModel):
    name: str                   # Structured key: "box1_wages"
    value: str                  # Clean value: "112400.00"
    confidence: float
    flagged: bool = False
    flag_reason: str = ""
    label: str = ""             # Display label: "Box 1 — Wages" (populated by router)
```

### 4.2 `api/routers/documents.py`

**Upload endpoint changes:**
- Extractor selected via config/DI (mock vs claude)
- `extracted_data` stored as structured JSON dict (`{"box1_wages": "112400.00", ...}`) instead of a list of display fields
- Confidence and flags derived from extraction result (unchanged logic)

**Fields endpoint changes:**
- When returning fields for the UI, use `field_mapping.get_display_label()` to populate the `label` field on each `ExtractedField`

**Dependency injection:**
```python
def get_ocr_extractor() -> OCRExtractor:
    if os.getenv("OCR_EXTRACTOR", "mock") == "claude":
        import anthropic
        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
        from api.services.ocr.claude_extractor import ClaudeVisionExtractor
        return ClaudeVisionExtractor(client)
    from api.services.ocr.mock_extractor import MockOCRExtractor
    return MockOCRExtractor()
```

### 4.3 `api/tax_engine/assembler.py`

Minor update — the assembler currently expects `extracted_data` to be a dict of field→value pairs. With the new structured format, this already works. The only change: ensure the assembler handles the case where `extracted_data` is stored as a JSON dict (new format) vs a JSON list (old format, for backward compatibility during migration).

### 4.4 `requirements-api.txt`

Add: `anthropic>=0.40`

---

## 5. Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OCR_EXTRACTOR` | `"mock"` | `"mock"` or `"claude"` |
| `ANTHROPIC_API_KEY` | (none) | Required when `OCR_EXTRACTOR=claude` |
| `CLAUDE_EXTRACTION_MODEL` | `"claude-sonnet-4-20250514"` | Model for vision extraction |

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Claude API unreachable | Raise HTTP 503, document not created |
| Claude returns invalid JSON | Retry once with stricter prompt. If still invalid, store empty extracted_data, set status="review", add flag "Extraction failed — manual entry required" |
| File too large for Claude context | Raise HTTP 413 (already handled by MAX_FILE_SIZE check) |
| Unknown form type | Use generic prompt, store whatever Claude extracts, set status="review" |
| Claude returns fields not in our model | Ignore extra fields (Pydantic ignores unknown fields by default) |
| ANTHROPIC_API_KEY missing when OCR_EXTRACTOR=claude | Raise startup error with clear message |

---

## 7. Testing Strategy

### Unit Tests

- `test_claude_extractor.py` — Mock the Anthropic client, verify:
  - Correct prompt selected per form type
  - Response parsed into ExtractionResult correctly
  - Low-confidence fields flagged
  - Invalid JSON response handled gracefully
  - PDF vs image media type detection

- `test_prompts.py` — Verify:
  - Each form type has a prompt
  - Each prompt references the correct field keys
  - Unknown form type returns fallback prompt

- `test_field_mapping.py` — Verify:
  - All form types have label mappings
  - All field keys in prompts have corresponding labels
  - Unknown keys return the key itself as fallback

- `test_mock_extractor.py` — Verify:
  - Mock returns structured format (not display format)
  - All supported form types return valid data
  - Returned field names match Pydantic model field names

### Integration Tests

- `test_documents.py` (updated) — Verify:
  - Upload → structured extracted_data stored correctly
  - Fields endpoint returns display labels
  - Approve flow unchanged
  - Assembler can build TaxReturn from new extraction format

---

## 8. Scope Summary

| Component | Change Type | Description |
|-----------|------------|-------------|
| `claude_extractor.py` | New | Claude Vision extraction with structured output |
| `prompts.py` | New | 7 form-specific prompts + generic fallback |
| `field_mapping.py` | New | Structured key → display label dict |
| `mock_extractor.py` | Modified | Returns structured format |
| `documents.py` router | Modified | DI for extractor, structured storage, label mapping |
| `document.py` models | Modified | ExtractedField gains `label` field |
| `assembler.py` | Modified | Handle both old list and new dict formats |
| `requirements-api.txt` | Modified | Add `anthropic>=0.40` |
| Test files | 4 new + 1 updated | Extractor, prompts, mapping, mock, integration |

### Out of Scope (Phase 3+)

- Local PDF libraries (pdfplumber, pypdf) for AcroForm/text extraction
- Multi-page document handling
- Batch/bulk extraction
- OCR preprocessing (rotation, deskewing)
- PDF form generation / output
- Advisory engine
