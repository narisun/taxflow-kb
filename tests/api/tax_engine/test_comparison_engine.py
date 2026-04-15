"""Tests for year-over-year comparison engine."""
from decimal import Decimal
import pytest

from api.tax_engine.comparison.engine import ComparisonEngine
from api.tax_engine.models.tax_return import TaxResult, FormResult, LineTrace


def _make_result(tax_year: int, lines: dict[str, Decimal]) -> TaxResult:
    """Helper: create a TaxResult with specified 1040 lines."""
    line_traces = {}
    for line, value in lines.items():
        line_traces[line] = LineTrace(form="1040", line=line, label=f"Line {line}",
                                      value=value, formula="test")
    return TaxResult(
        tax_year=tax_year, filing_status="S",
        form_results={"1040": FormResult(form_name="1040", lines=line_traces, total=Decimal("0"))},
    )


class TestComparisonEngine:
    def test_basic_comparison(self):
        current = _make_result(2024, {"1a": Decimal("90000"), "9": Decimal("90000"),
                                       "11": Decimal("90000"), "15": Decimal("75400"),
                                       "24": Decimal("12000"), "33": Decimal("15000"),
                                       "35a": Decimal("3000")})
        prior = _make_result(2023, {"1a": Decimal("80000"), "9": Decimal("80000"),
                                     "11": Decimal("80000"), "15": Decimal("65400"),
                                     "24": Decimal("10000"), "33": Decimal("14000"),
                                     "35a": Decimal("4000")})
        engine = ComparisonEngine()
        report = engine.compare(current, prior, client_id=1)

        assert report.current_year == 2024
        assert report.prior_year == 2023
        assert len(report.sections) == 4

        # Income section
        wages_row = report.sections[0].rows[0]
        assert wages_row.label == "Wages, salaries, tips"
        assert wages_row.current == Decimal("90000")
        assert wages_row.prior == Decimal("80000")
        assert wages_row.change == Decimal("10000")
        assert wages_row.pct_change == 12.5

    def test_decreased_values(self):
        current = _make_result(2024, {"9": Decimal("50000"), "24": Decimal("5000")})
        prior = _make_result(2023, {"9": Decimal("80000"), "24": Decimal("10000")})
        report = ComparisonEngine().compare(current, prior, client_id=1)

        total_income = next(r for r in report.sections[0].rows if r.line == "9")
        assert total_income.change == Decimal("-30000")
        assert total_income.pct_change == -37.5

    def test_prior_zero_pct_change(self):
        current = _make_result(2024, {"2b": Decimal("5000")})
        prior = _make_result(2023, {"2b": Decimal("0")})
        report = ComparisonEngine().compare(current, prior, client_id=1)

        interest = next(r for r in report.sections[0].rows if r.line == "2b")
        assert interest.pct_change == 100.0

    def test_both_zero(self):
        current = _make_result(2024, {})
        prior = _make_result(2023, {})
        report = ComparisonEngine().compare(current, prior, client_id=1)

        for section in report.sections:
            for row in section.rows:
                assert row.change == Decimal("0")
                assert row.pct_change == 0.0

    def test_summary_refund_change(self):
        current = _make_result(2024, {"35a": Decimal("3000")})
        prior = _make_result(2023, {"35a": Decimal("5000")})
        report = ComparisonEngine().compare(current, prior, client_id=1)

        assert report.summary.current == Decimal("3000")
        assert report.summary.prior == Decimal("5000")
        assert report.summary.change == Decimal("-2000")

    def test_summary_owed_vs_refund(self):
        current = _make_result(2024, {"37": Decimal("1000")})  # owed
        prior = _make_result(2023, {"35a": Decimal("2000")})   # refund
        report = ComparisonEngine().compare(current, prior, client_id=1)

        assert report.summary.current == Decimal("-1000")  # owed shown as negative
        assert report.summary.prior == Decimal("2000")
        assert report.summary.change == Decimal("-3000")

    def test_four_sections(self):
        current = _make_result(2024, {})
        prior = _make_result(2023, {})
        report = ComparisonEngine().compare(current, prior, client_id=1)

        section_titles = [s.title for s in report.sections]
        assert section_titles == ["Income", "Deductions", "Tax", "Payments"]
