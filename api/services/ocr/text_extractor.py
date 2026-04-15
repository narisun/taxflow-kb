"""Tier 2: Text layer extraction for readable/programmatic PDFs using pdfplumber.

Extracts ALL data from PDFs with embedded text. Uses pdfplumber's table
extraction to read cell-by-cell data with label+value pairs.

Design principle: NEVER miss a field. All known IRS fields are mapped by name.
Any data that doesn't match a known field is captured in 'other_fields' as
a semicolon-separated key=value string.
"""
import io
import re
from decimal import Decimal, InvalidOperation

import pdfplumber
from pypdf import PdfReader

from api.models.document import ExtractionResult, ExtractedField

# ── Regex patterns ───────────────────────────────────────────────────────────

_CURRENCY_RE = re.compile(
    r"""(?x)
    (?:
        \$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)
        |
        (\d{1,3}(?:,\d{3})+(?:\.\d{2})?)
        |
        (\d+\.\d{2})
    )
    """
)
_EIN_RE = re.compile(r"\b(\d{2}-\d{7})\b")
_SSN_RE = re.compile(r"\b(\d{3}-\d{2}-\d{4})\b")


def _parse_currency(s: str) -> str:
    if not s:
        return ""
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return f"{Decimal(s):.2f}"
    except (InvalidOperation, ValueError):
        return ""


def _extract_number(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    result = _parse_currency(s)
    if result:
        return result
    m = _CURRENCY_RE.search(s)
    if m:
        return _parse_currency(m.group(1) or m.group(2) or m.group(3) or "")
    m = re.search(r"\b(\d{4,})\b", s)
    if m:
        return _parse_currency(m.group(1))
    return ""


# ── Format detection ─────────────────────────────────────────────────────────

def detect_pdf_format(file_bytes: bytes) -> str:
    if not file_bytes[:5].startswith(b"%PDF"):
        if file_bytes[:8] == b"\x89PNG\r\n\x1a\n" or file_bytes[:2] == b"\xff\xd8":
            return "image"
        return "not_pdf"
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        fields = reader.get_form_text_fields() or {}
        if len(fields) >= 2:
            return "acroform"
    except Exception:
        pass
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:3]:
                text = (page.extract_text() or "").strip()
                if len(text) > 20:
                    return "text"
    except Exception:
        pass
    return "scanned"


# ── Form classification ──────────────────────────────────────────────────────

def _classify_form(text: str, filename_hint: str = "") -> str:
    fname = filename_hint.lower()
    text_lower = text.lower()
    if "w2" in fname or "w-2" in fname:
        return "W-2"
    if "1099-int" in fname or "1099int" in fname:
        return "1099-INT"
    if "1099-div" in fname or "1099div" in fname:
        return "1099-DIV"
    if "1099-b" in fname or "1099b" in fname:
        return "1099-B"
    if "1099-nec" in fname or "1099nec" in fname:
        return "1099-NEC"
    if "1098" in fname:
        return "1098"
    if "k-1" in fname or "k1" in fname:
        return "K-1"
    if "wage and tax statement" in text_lower or "w-2" in text_lower:
        return "W-2"
    if "interest income" in text_lower and "1099" in text_lower:
        return "1099-INT"
    if "dividends and distributions" in text_lower or "1099-div" in text_lower:
        return "1099-DIV"
    if "proceeds from broker" in text_lower or "1099-b" in text_lower:
        return "1099-B"
    if "nonemployee compensation" in text_lower or "1099-nec" in text_lower:
        return "1099-NEC"
    if "mortgage interest" in text_lower and "1098" in text_lower:
        return "1098"
    if "schedule k-1" in text_lower or "share of income" in text_lower:
        return "K-1"
    return "Other"


# ── Generic table cell parser ────────────────────────────────────────────────

def _parse_table_cells(tables: list) -> list[tuple[str, str]]:
    """Parse all table cells into (label, value) pairs.

    Each cell may contain "label\\nvalue" or just "label" (empty value).
    Returns ALL pairs — nothing is discarded.
    """
    pairs = []
    for table in tables:
        for row in table:
            for cell in row:
                if not cell or not cell.strip():
                    continue
                lines = cell.strip().split("\n")
                label = lines[0].strip()
                value = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                pairs.append((label, value))
    return pairs


# ── W-2 complete field mapping ───────────────────────────────────────────────

# Maps IRS label patterns → our field name. Order matters — first match wins.
_W2_FIELD_MAP: list[tuple[str, str, str]] = [
    # (regex_pattern, field_name, value_type: "ein"|"ssn"|"text"|"number"|"state_id")
    (r"^a\s+employee.s?\s+social\s+security", "employee_ssn", "ssn"),
    (r"^b\s+employer\s+identification", "employer_ein", "ein"),
    (r"^c\s+employer.s?\s+name", "employer_name_address", "text"),
    (r"^d\s+control\s+number", "control_number", "text"),
    (r"^e\s+employee.s?\s+first\s+name", "employee_name_address", "text"),
    (r"^1\s+wages|^wages.*compensation", "box1_wages", "number"),
    (r"^2\s+federal|federal\s+income\s+tax\s+withheld", "box2_fed_withheld", "number"),
    (r"^3\s+social\s+security\s+wages", "box3_ss_wages", "number"),
    (r"^4\s+social\s+security\s+tax", "box4_ss_withheld", "number"),
    (r"^5\s+medicare\s+wages", "box5_medicare_wages", "number"),
    (r"^6\s+medicare\s+tax", "box6_medicare_withheld", "number"),
    (r"^7\s+social\s+security\s+tips", "box7_ss_tips", "number"),
    (r"^8\s+allocated\s+tips", "box8_allocated_tips", "number"),
    (r"^9\b", "box9", "number"),
    (r"^10\s+dependent\s+care", "box10_dependent_care", "number"),
    (r"^11\s+nonqualified", "box11_nonqualified_plans", "number"),
    (r"^12a\b", "box12a", "text"),
    (r"^12b\b", "box12b", "text"),
    (r"^12c\b", "box12c", "text"),
    (r"^12d\b", "box12d", "text"),
    (r"^13\s+statutory|^13\b.*employee\s+plan", "box13_statutory", "text"),
    (r"^14a\s+other|^14a\b", "box14a_other", "text"),
    (r"^14b\b", "box14b_other", "text"),
    (r"^15\s+state\s+employer|^15\s+state\b", "box15_state_id", "state_id"),
    (r"^16\s+state\s+wages", "box16_state_wages", "number"),
    (r"^17\s+state\s+income\s+tax", "box17_state_withheld", "number"),
    (r"^18\s+local\s+wages", "box18_local_wages", "number"),
    (r"^19\s+local\s+income\s+tax", "box19_local_tax", "number"),
    (r"^20\s+locality\s+name", "box20_locality_name", "text"),
]

# Labels to skip (form metadata, not data)
_SKIP_LABELS = {
    "22222", "OMB No. 1545-0029", "Form", "Copy 1", "Copy 2", "Copy B",
    "Copy C", "Copy D", "Department of the Treasury",
    "Wage and Tax Statement", "Internal Revenue Service",
    "W-2", "Co", "de", "Code",
}


def _extract_w2_from_table(tables: list, text: str) -> list[ExtractedField]:
    """Extract ALL W-2 data from table cells — known fields + unknown catch-all."""
    fields = []
    other_pairs = []
    cells = _parse_table_cells(tables)
    matched_labels = set()

    for label, value in cells:
        # Skip form metadata
        if label in _SKIP_LABELS or any(label.startswith(s) for s in ("W-2", "Copy", "Department")):
            continue

        # Try to match against known W-2 fields
        matched = False
        for pattern, field_name, value_type in _W2_FIELD_MAP:
            if re.search(pattern, label, re.IGNORECASE):
                if field_name in matched_labels:
                    continue  # Already matched this field
                matched_labels.add(field_name)
                matched = True

                if value_type == "ein":
                    m = _EIN_RE.search(value or label)
                    if m:
                        fields.append(ExtractedField(
                            name=field_name, value=m.group(1), confidence=0.98))
                    elif value:
                        fields.append(ExtractedField(
                            name=field_name, value=value, confidence=0.90))

                elif value_type == "ssn":
                    m = _SSN_RE.search(value or label)
                    if m:
                        fields.append(ExtractedField(
                            name=field_name, value=m.group(1), confidence=0.98))
                    elif value:
                        fields.append(ExtractedField(
                            name=field_name, value=value, confidence=0.90))

                elif value_type == "number":
                    num = _extract_number(value)
                    if num:
                        fields.append(ExtractedField(
                            name=field_name, value=num, confidence=0.99))
                    # Omit if empty — but record it was seen

                elif value_type == "state_id":
                    if value:
                        # Extract state abbreviation and ID number
                        m = re.match(r"([A-Z]{2})\s*(.*)", value)
                        if m:
                            fields.append(ExtractedField(
                                name="box15_state", value=m.group(1), confidence=0.98))
                            if m.group(2).strip():
                                fields.append(ExtractedField(
                                    name="box15_state_ein", value=m.group(2).strip(), confidence=0.95))
                        else:
                            fields.append(ExtractedField(
                                name=field_name, value=value, confidence=0.90))

                elif value_type == "text":
                    if value:
                        # For employer name+address, split on comma
                        if field_name == "employer_name_address":
                            parts = value.split(",")
                            fields.append(ExtractedField(
                                name="employer_name", value=parts[0].strip(), confidence=0.95))
                            if len(parts) > 1:
                                fields.append(ExtractedField(
                                    name="employer_address", value=",".join(parts[1:]).strip(), confidence=0.90))
                        elif field_name == "employee_name_address":
                            # First line is name, rest is address
                            name_lines = value.split("\n")
                            fields.append(ExtractedField(
                                name="employee_name", value=name_lines[0].strip(), confidence=0.95))
                            if len(name_lines) > 1:
                                addr = "\n".join(name_lines[1:]).strip()
                                # Filter out the "f Employee's address" label
                                addr = re.sub(r"f\s+employee.s?\s+address.*", "", addr, flags=re.IGNORECASE).strip()
                                if addr:
                                    fields.append(ExtractedField(
                                        name="employee_address", value=addr, confidence=0.90))
                        else:
                            # Clean up garbled text (OCR artifacts)
                            clean = re.sub(r"\s{2,}", " ", value).strip()
                            clean = re.sub(r"\n", " ", clean).strip()
                            # Skip noise values from table rendering artifacts
                            if (len(clean) > 2
                                    and clean.lower() not in ("co", "de", "code", "co de", "co\nde",
                                                              "employee plan sick pay")):
                                fields.append(ExtractedField(
                                    name=field_name, value=clean, confidence=0.90))
                break

        # If not matched to any known field, capture as "other"
        if not matched and value and label:
            # Skip pure metadata/noise
            clean_label = re.sub(r"\s+", " ", label).strip()
            clean_value = re.sub(r"\s+", " ", value).strip()
            if (clean_value.lower() not in ("co", "de", "code", "employee plan sick pay")
                    and len(clean_value) > 0
                    and clean_label not in _SKIP_LABELS):
                other_pairs.append(f"{clean_label}={clean_value}")

    # Capture any unmatched data in other_fields
    if other_pairs:
        fields.append(ExtractedField(
            name="other_fields", value="; ".join(other_pairs), confidence=0.80,
            flagged=True, flag_reason="Unrecognized fields captured for review"))

    return fields


# ── 1099-INT extraction ──────────────────────────────────────────────────────

_1099INT_FIELD_MAP = [
    (r"payer.s?\s+name|payer\s*:", "payer", "text"),
    (r"1\s+interest\s+income|interest\s+income", "box1_interest", "number"),
    (r"2\s+early\s+withdrawal", "box2_early_withdrawal_penalty", "number"),
    (r"3\s+interest\s+on.*savings", "box3_savings_bond_interest", "number"),
    (r"4\s+federal.*withheld|federal.*tax.*withheld", "box4_fed_withheld", "number"),
    (r"5\s+investment\s+expenses", "box5_investment_expenses", "number"),
    (r"6\s+foreign\s+tax", "box6_foreign_tax", "number"),
    (r"8\s+tax.exempt\s+interest", "box8_tax_exempt_interest", "number"),
    (r"9\s+specified\s+private", "box9_private_activity", "number"),
    (r"10\s+market\s+discount", "box10_market_discount", "number"),
    (r"11\s+bond\s+premium", "box11_bond_premium", "number"),
]


def _extract_1099_int(text: str, tables: list) -> list[ExtractedField]:
    return _generic_table_extract(tables, text, _1099INT_FIELD_MAP)


# ── 1099-DIV extraction ──────────────────────────────────────────────────────

_1099DIV_FIELD_MAP = [
    (r"payer.s?\s+name|payer\s*:", "payer", "text"),
    (r"1a\s+(?:total\s+)?ordinary\s+dividends", "box1a_ordinary_dividends", "number"),
    (r"1b\s+qualified\s+dividends", "box1b_qualified_dividends", "number"),
    (r"2a\s+.*capital\s+gain", "box2a_capital_gain_distributions", "number"),
    (r"2b\s+.*28%\s+rate", "box2b_28pct_rate_gain", "number"),
    (r"2c\s+.*1250", "box2c_section_1250", "number"),
    (r"2d\s+.*collectibles", "box2d_collectibles_gain", "number"),
    (r"3\s+nondividend\s+distributions", "box3_nondividend", "number"),
    (r"4\s+federal.*withheld", "box4_fed_withheld", "number"),
    (r"5\s+section\s+199a", "box5_section_199a", "number"),
    (r"6\s+investment\s+expenses", "box6_investment_expenses", "number"),
    (r"7\s+foreign\s+tax", "box7_foreign_tax_paid", "number"),
]


def _extract_1099_div(text: str, tables: list) -> list[ExtractedField]:
    return _generic_table_extract(tables, text, _1099DIV_FIELD_MAP)


# ── 1099-NEC extraction ─────────────────────────────────────────────────────

_1099NEC_FIELD_MAP = [
    (r"payer.s?\s+name|payer\s*:", "payer", "text"),
    (r"1\s+nonemployee\s+compensation|nonemployee\s+compensation", "nec_compensation", "number"),
    (r"2\s+.*direct\s+sales", "box2_direct_sales", "text"),
    (r"4\s+federal.*withheld", "fed_tax_withheld", "number"),
    (r"5\s+state\s+tax", "box5_state_tax", "number"),
    (r"6\s+state.*income", "box6_state_income", "number"),
    (r"7\s+state", "box7_state", "text"),
]


def _extract_1099_nec(text: str, tables: list) -> list[ExtractedField]:
    return _generic_table_extract(tables, text, _1099NEC_FIELD_MAP)


# ── 1098 extraction ──────────────────────────────────────────────────────────

_1098_FIELD_MAP = [
    (r"recipient.s?\s+name|lender\s*:", "lender", "text"),
    (r"1\s+mortgage\s+interest|mortgage\s+interest\s+received", "box1_interest", "number"),
    (r"2\s+outstanding\s+mortgage", "box2_outstanding_principal", "number"),
    (r"3\s+mortgage\s+origination", "box3_origination_date", "text"),
    (r"4\s+refund\s+of\s+overpaid", "box4_refund_overpaid", "number"),
    (r"5\s+mortgage\s+insurance", "box5_mortgage_insurance", "number"),
    (r"6\s+points\s+paid", "box6_points_paid", "number"),
    (r"7\s+.*property\s+address|property\s+address", "box7_property_address", "text"),
    (r"10\s+property\s+tax|property\s+tax", "box10_property_taxes", "number"),
    (r"11\s+mortgage\s+acquisition", "box11_acquisition_date", "text"),
]


def _extract_1098(text: str, tables: list) -> list[ExtractedField]:
    return _generic_table_extract(tables, text, _1098_FIELD_MAP)


# ── 1099-B extraction ────────────────────────────────────────────────────────

_1099B_FIELD_MAP = [
    (r"payer.s?\s+name|broker.s?\s+name|payer\s*:", "payer", "text"),
    (r"1d\s+proceeds|proceeds", "short_term_proceeds", "number"),
    (r"1e\s+cost.*basis|cost.*basis", "short_term_cost_basis", "number"),
    (r"1g\s+adjustments|adjustments", "adjustments", "number"),
    (r"2\s+.*short.term|short.term", "short_term_indicator", "text"),
    (r"4\s+federal.*withheld", "box4_fed_withheld", "number"),
    (r"5\s+.*wash\s+sale|wash\s+sale", "box5_wash_sale", "number"),
]


def _extract_1099_b(text: str, tables: list) -> list[ExtractedField]:
    return _generic_table_extract(tables, text, _1099B_FIELD_MAP)


# ── Generic table extraction ─────────────────────────────────────────────────

def _generic_table_extract(
    tables: list, text: str, field_map: list[tuple[str, str, str]]
) -> list[ExtractedField]:
    """Generic extraction using a field map. Captures unknown fields too."""
    fields = []
    other_pairs = []
    cells = _parse_table_cells(tables) if tables else []
    matched_names = set()

    # If no tables, try text-based extraction
    if not cells:
        cells = [(line, "") for line in text.split("\n") if line.strip()]

    for label, value in cells:
        if label in _SKIP_LABELS:
            continue

        matched = False
        for pattern, field_name, value_type in field_map:
            if field_name in matched_names:
                continue
            if re.search(pattern, label, re.IGNORECASE):
                matched_names.add(field_name)
                matched = True
                if value_type == "number":
                    num = _extract_number(value)
                    if num:
                        fields.append(ExtractedField(name=field_name, value=num, confidence=0.98))
                elif value_type == "ein":
                    m = _EIN_RE.search(value or label)
                    if m:
                        fields.append(ExtractedField(name=field_name, value=m.group(1), confidence=0.98))
                elif value_type == "ssn":
                    m = _SSN_RE.search(value or label)
                    if m:
                        fields.append(ExtractedField(name=field_name, value=m.group(1), confidence=0.98))
                elif value_type == "text" and value:
                    fields.append(ExtractedField(name=field_name, value=value.strip(), confidence=0.95))
                break

        if not matched and value and label and len(value) > 0:
            clean_label = re.sub(r"\s+", " ", label).strip()[:50]
            clean_value = re.sub(r"\s+", " ", value).strip()[:100]
            if clean_value.lower() not in ("co", "de", "code"):
                other_pairs.append(f"{clean_label}={clean_value}")

    if other_pairs:
        fields.append(ExtractedField(
            name="other_fields", value="; ".join(other_pairs), confidence=0.80,
            flagged=True, flag_reason="Unrecognized fields captured for review"))

    return fields


# ── Main extractor class ─────────────────────────────────────────────────────

class TextLayerExtractor:
    """Extracts ALL data from PDFs with embedded text using pdfplumber."""

    async def extract(self, file_bytes: bytes, form_type: str) -> ExtractionResult:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages_text = []
                all_tables = []
                for page in pdf.pages[:10]:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(text)
                    tables = page.extract_tables()
                    if tables:
                        all_tables.extend(tables)
                full_text = "\n".join(pages_text)
        except Exception:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Failed to read PDF text layer"],
            )

        if not full_text or len(full_text.strip()) < 20:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["No text layer found — document may be scanned"],
            )

        detected_type = form_type
        if form_type in ("Other", "1099", ""):
            detected_type = _classify_form(full_text)

        fields = self._extract_form(detected_type, full_text, all_tables)

        if not fields:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=[f"Text layer found but no fields extracted for '{detected_type}'"],
            )

        min_conf = min(f.confidence for f in fields)
        has_flags = any(f.flagged for f in fields)
        flag_msgs = [f.flag_reason for f in fields if f.flagged and f.flag_reason]

        return ExtractionResult(
            fields=fields, overall_confidence=min_conf,
            has_flags=has_flags, flags=flag_msgs,
        )

    def _extract_form(self, form_type: str, text: str, tables: list) -> list[ExtractedField]:
        if form_type == "W-2":
            return _extract_w2_from_table(tables, text) if tables else []
        elif form_type == "1099-INT":
            return _extract_1099_int(text, tables)
        elif form_type == "1099-DIV":
            return _extract_1099_div(text, tables)
        elif form_type == "1099-NEC":
            return _extract_1099_nec(text, tables)
        elif form_type == "1098":
            return _extract_1098(text, tables)
        elif form_type == "1099-B":
            return _extract_1099_b(text, tables)
        # For unknown forms, do a generic dump of all table cells
        return self._extract_generic(text, tables)

    def _extract_generic(self, text: str, tables: list) -> list[ExtractedField]:
        """Extract all data from an unknown form type as key=value pairs."""
        cells = _parse_table_cells(tables) if tables else []
        pairs = []
        for label, value in cells:
            if value and label not in _SKIP_LABELS:
                clean_label = re.sub(r"\s+", " ", label).strip()[:50]
                clean_value = re.sub(r"\s+", " ", value).strip()[:100]
                if clean_value.lower() not in ("co", "de", "code"):
                    pairs.append(f"{clean_label}={clean_value}")
        if pairs:
            return [ExtractedField(
                name="other_fields", value="; ".join(pairs), confidence=0.70,
                flagged=True, flag_reason="Unknown form — all fields captured for manual review")]
        return []
