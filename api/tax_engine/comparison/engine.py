"""ComparisonEngine — compares two TaxResult objects line by line."""
from decimal import Decimal

from api.tax_engine.comparison.models import ComparisonRow, ComparisonSection, ComparisonReport
from api.tax_engine.models.tax_return import TaxResult


_SECTIONS = [
    ("Income", [
        ("1a", "Wages, salaries, tips"),
        ("2b", "Taxable interest"),
        ("3b", "Ordinary dividends"),
        ("7", "Capital gain/loss"),
        ("8", "Other income"),
        ("9", "Total income"),
        ("10", "Adjustments to income"),
        ("11", "Adjusted gross income"),
    ]),
    ("Deductions", [
        ("12", "Deduction (standard/itemized)"),
        ("13a", "QBI deduction"),
        ("15", "Taxable income"),
    ]),
    ("Tax", [
        ("16", "Tax"),
        ("23", "Other taxes"),
        ("24", "Total tax"),
    ]),
    ("Payments", [
        ("25", "Federal tax withheld"),
        ("26", "Estimated tax payments"),
        ("33", "Total payments"),
    ]),
]


def _get_1040_line(result: TaxResult, line: str) -> Decimal:
    """Extract a Form 1040 line value from TaxResult."""
    f1040 = result.form_results.get("1040")
    if f1040 and line in f1040.lines:
        return f1040.lines[line].value
    return Decimal("0")


def _calc_pct(change: Decimal, prior: Decimal) -> float:
    """Calculate percentage change, handling zero prior."""
    if prior != Decimal("0"):
        return round(float(change / abs(prior) * 100), 1)
    return 100.0 if change != Decimal("0") else 0.0


def _make_row(label: str, line: str, current: Decimal, prior: Decimal) -> ComparisonRow:
    change = current - prior
    return ComparisonRow(
        label=label, line=line, current=current, prior=prior,
        change=change, pct_change=_calc_pct(change, prior),
    )


class ComparisonEngine:
    def compare(self, current: TaxResult, prior: TaxResult, client_id: int) -> ComparisonReport:
        """Compare two TaxResults and return a structured report."""
        sections: list[ComparisonSection] = []

        for title, lines in _SECTIONS:
            rows = []
            for line, label in lines:
                cur_val = _get_1040_line(current, line)
                pri_val = _get_1040_line(prior, line)
                rows.append(_make_row(label, line, cur_val, pri_val))
            sections.append(ComparisonSection(title=title, rows=rows))

        # Summary: refund/owed (check 35a first, then 37)
        cur_refund = _get_1040_line(current, "35a")
        pri_refund = _get_1040_line(prior, "35a")
        if cur_refund == Decimal("0"):
            cur_refund = -_get_1040_line(current, "37")
        if pri_refund == Decimal("0"):
            pri_refund = -_get_1040_line(prior, "37")

        summary = _make_row("Refund / (Amount owed)", "35a/37", cur_refund, pri_refund)

        return ComparisonReport(
            current_year=current.tax_year,
            prior_year=prior.tax_year,
            client_id=client_id,
            sections=sections,
            summary=summary,
        )
