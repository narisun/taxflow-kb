"""Cascading extractor — tries extraction tiers in order of cost/speed.

Tier 1: AcroForm field extraction (pypdf) — fillable PDFs, free, instant
Tier 2: Text layer extraction (pdfplumber) — readable PDFs, free, instant
Tier 3: Claude Vision API — scanned/image PDFs, API cost, slower

For each tier, if meaningful fields are extracted, stop. Otherwise try next tier.
"""
import io
import logging
import re

from pypdf import PdfReader

from api.models.document import ExtractionResult, ExtractedField
from api.services.ocr.text_extractor import TextLayerExtractor, detect_pdf_format, _classify_form

logger = logging.getLogger(__name__)

# ── AcroForm field name → structured key mapping (per form type) ─────────
# pypdf returns fields like "f2_09[0]" → "85000.00". These maps translate
# the positional field names to our canonical keys.

_ACROFORM_W2_MAP: list[tuple[str, str, str]] = [
    # (pypdf field pattern, our field key, type)
    (r"f2_01", "employee_ssn", "text"),
    (r"f2_02", "employer_ein", "text"),
    (r"f2_03", "employer_name", "text"),
    (r"f2_04", "control_number", "text"),
    (r"f2_05", "employee_first_name", "text"),
    (r"f2_06", "employee_last_name", "text"),
    (r"f2_07", "employee_suffix", "text"),
    (r"f2_08", "employee_address", "text"),
    (r"f2_09", "box1_wages", "number"),
    (r"f2_10", "box2_fed_withheld", "number"),
    (r"f2_11", "box3_ss_wages", "number"),
    (r"f2_12", "box4_ss_withheld", "number"),
    (r"f2_13", "box5_medicare_wages", "number"),
    (r"f2_14", "box6_medicare_withheld", "number"),
    (r"f2_15", "box7_ss_tips", "number"),
    (r"f2_16", "box8_allocated_tips", "number"),
    (r"f2_17", "box9", "number"),
    (r"f2_18", "box10_dependent_care", "number"),
    (r"f2_19", "box11_nonqualified_plans", "number"),
    (r"f2_20", "box12a_code", "text"),
    (r"f2_21", "box12a_amount", "number"),
    (r"f2_22", "box12b_code", "text"),
    (r"f2_23", "box12b_amount", "number"),
    (r"f2_24", "box12c_code", "text"),
    (r"f2_25", "box12c_amount", "number"),
    (r"f2_26", "box12d_code", "text"),
    (r"f2_27", "box12d_amount", "number"),
    (r"f2_28", "box14_other", "text"),
    (r"f2_29", "box15_state", "text"),
    (r"f2_30", "box15_state_ein", "text"),
    (r"f2_31", "box15b_state", "text"),
    (r"f2_32", "box15b_state_ein", "text"),
    (r"f2_33", "box16_state_wages", "number"),
    (r"f2_34", "box16b_state_wages", "number"),
    (r"f2_35", "box17_state_withheld", "number"),
    (r"f2_36", "box17b_state_withheld", "number"),
]


def _extract_acroform(file_bytes: bytes, form_type: str) -> list[ExtractedField]:
    """Tier 1: Extract data from fillable PDF AcroForm fields."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        raw_fields = reader.get_form_text_fields() or {}
    except Exception:
        return []

    if not raw_fields:
        return []

    # Auto-detect form type from field values if needed
    if form_type in ("Other", ""):
        all_text = " ".join(str(v) for v in raw_fields.values() if v)
        form_type = _classify_form(all_text)

    if form_type == "W-2":
        return _map_acroform_w2(raw_fields)

    # For other form types, return all non-empty fields as-is
    fields = []
    for key, value in sorted(raw_fields.items()):
        if value and str(value).strip():
            fields.append(ExtractedField(
                name=key, value=str(value).strip(), confidence=0.95,
            ))
    return fields


def _map_acroform_w2(raw_fields: dict) -> list[ExtractedField]:
    """Map W-2 AcroForm field names to our canonical keys."""
    fields = []
    mapped_keys = set()

    for pdf_key, value in raw_fields.items():
        if not value or not str(value).strip():
            continue
        value = str(value).strip()
        # Strip the [0] index suffix
        clean_key = re.sub(r"\[\d+\]$", "", pdf_key)

        matched = False
        for pattern, field_name, vtype in _ACROFORM_W2_MAP:
            if field_name in mapped_keys:
                continue
            if re.fullmatch(pattern, clean_key):
                mapped_keys.add(field_name)
                matched = True
                if vtype == "number":
                    clean_val = value.replace(",", "").replace("$", "")
                    fields.append(ExtractedField(
                        name=field_name, value=clean_val, confidence=0.99,
                    ))
                else:
                    fields.append(ExtractedField(
                        name=field_name, value=value, confidence=0.98,
                    ))
                break

        if not matched:
            fields.append(ExtractedField(
                name=clean_key, value=value, confidence=0.90,
            ))

    # Combine first/last name into employee_name for display
    first = next((f.value for f in fields if f.name == "employee_first_name"), "")
    last = next((f.value for f in fields if f.name == "employee_last_name"), "")
    if first or last:
        fields.append(ExtractedField(
            name="employee_name", value=f"{first} {last}".strip(), confidence=0.98,
        ))

    return fields


class CascadingExtractor:
    """Format-aware extractor that selects the best method for each document."""

    def __init__(self, vision_extractor=None):
        """
        Args:
            vision_extractor: Optional Claude Vision extractor for Tier 3.
                If None, Tier 3 is skipped (mock mode).
        """
        self.text_extractor = TextLayerExtractor()
        self.vision_extractor = vision_extractor

    async def extract(self, file_bytes: bytes, form_type: str) -> ExtractionResult:
        """Extract data using the best available method for this document.

        Strategy:
        1. Detect format (acroform, text, scanned, image)
        2. For acroform → try AcroForm extraction first (Tier 1)
        3. For text/acroform → try text layer extraction (Tier 2)
        4. If nothing works → fall through to Vision (Tier 3)
        """
        fmt = detect_pdf_format(file_bytes)
        logger.info(f"Document format detected: {fmt} (form_type={form_type})")

        # Tier 1: AcroForm extraction for fillable PDFs
        if fmt == "acroform":
            acro_fields = _extract_acroform(file_bytes, form_type)
            if acro_fields:
                logger.info(f"Tier 1 (AcroForm): extracted {len(acro_fields)} fields")
                min_conf = min(f.confidence for f in acro_fields)
                has_flags = any(f.flagged for f in acro_fields)
                flag_msgs = [f.flag_reason for f in acro_fields if f.flagged and f.flag_reason]
                return ExtractionResult(
                    fields=acro_fields, overall_confidence=min_conf,
                    has_flags=has_flags, flags=flag_msgs,
                )
            logger.info("Tier 1: no AcroForm fields found, trying text layer")

        # Tier 2: Text layer extraction
        if fmt in ("text", "acroform"):
            result = await self.text_extractor.extract(file_bytes, form_type)
            if result.fields:
                logger.info(f"Tier 2 (text layer): extracted {len(result.fields)} fields")
                return result
            logger.info("Tier 2: no fields extracted, falling through to Vision")

        # Fall through to Vision (Tier 3) if available
        if self.vision_extractor:
            logger.info("Tier 3 (Claude Vision): sending to API")
            return await self.vision_extractor.extract(file_bytes, form_type)

        # No Vision extractor configured — return what we have
        if fmt in ("scanned", "image"):
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Scanned/image document — Vision extraction not configured. "
                       "Set OCR_EXTRACTOR=claude to enable."],
            )

        return ExtractionResult(
            fields=[], overall_confidence=0.0, has_flags=True,
            flags=["Could not extract data from this document"],
        )
