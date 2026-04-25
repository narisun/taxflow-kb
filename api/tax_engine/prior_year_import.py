"""Build a TaxReturnDraft from extracted prior-year 1040 line items."""
from __future__ import annotations

from api.models.tax_return import ReturnLine, TaxReturnDraft

# Form 1040 lines we extract from prior-year PDFs.
# Maps extracted field key → (line_number, label, section).
_LINE_MAP: dict[str, tuple[str, str, str]] = {
    "line_1a": ("1a", "Wages, salaries, tips", "income"),
    "line_2b": ("2b", "Taxable interest", "income"),
    "line_3b": ("3b", "Qualified dividends", "income"),
    "line_7": ("7", "Capital gain or loss", "income"),
    "line_8": ("8", "Other income", "income"),
    "line_9": ("9", "Total income", "income"),
    "line_12": ("12", "Deductions", "deductions"),
    "line_13a": ("13a", "QBI deduction", "deductions"),
    "line_15": ("15", "Taxable income", "deductions"),
    "line_16": ("16", "Tax", "tax_credits"),
    "line_24": ("24", "Total tax", "tax_credits"),
    "line_25a": ("25a", "W-2 withholding", "payments"),
    "line_25b": ("25b", "1099 withholding", "payments"),
    "line_25c": ("25c", "Other withholding", "payments"),
    "line_26": ("26", "Estimated tax payments", "payments"),
    "line_33": ("33", "Total payments", "payments"),
    "line_35a": ("35a", "Refund", "payments"),
    "line_37": ("37", "Amount owed", "payments"),
}


def _parse_dollar(value: str | int | float | None) -> float:
    """Parse a dollar value from OCR output. Handles commas, $, negatives."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def build_draft_from_lines(
    client_id: str,
    tax_year: int,
    extracted: dict[str, str | int | float | None],
    filing_status: str = "S",
) -> TaxReturnDraft:
    """Convert extracted 1040 field dict into a TaxReturnDraft."""
    lines: list[ReturnLine] = []
    for field_key, (line_num, label, section) in _LINE_MAP.items():
        raw = extracted.get(field_key)
        val = _parse_dollar(raw)
        if val != 0.0 or field_key in ("line_9", "line_15", "line_24", "line_33"):
            lines.append(ReturnLine(
                number=line_num, label=label, value=val, section=section,
            ))

    total_income = _parse_dollar(extracted.get("line_9"))
    total_deductions = _parse_dollar(extracted.get("line_12")) + _parse_dollar(extracted.get("line_13a"))
    taxable_income = _parse_dollar(extracted.get("line_15"))
    total_tax = _parse_dollar(extracted.get("line_24"))
    total_payments = _parse_dollar(extracted.get("line_33"))
    refund = _parse_dollar(extracted.get("line_35a"))
    owed = _parse_dollar(extracted.get("line_37"))
    refund_or_owed = refund if refund > 0 else -owed

    effective_rate = round(total_tax / total_income * 100, 1) if total_income > 0 else 0.0

    return TaxReturnDraft(
        client_id=client_id,
        tax_year=tax_year,
        filing_status=filing_status,
        lines=lines,
        total_income=total_income,
        total_deductions=total_deductions,
        taxable_income=taxable_income,
        total_tax=total_tax,
        total_payments=total_payments,
        refund_or_owed=refund_or_owed,
        effective_rate=effective_rate,
    )
