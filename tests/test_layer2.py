"""
tests/test_layer2.py

Layer 2 test suite — IRS HTML Instruction Graph.

Test classes
────────────
  TestHTMLParser         — 10 tests: parse result structure, section types,
                            line references, field mapping, cross-references
  TestLayer2Structural   —  6 tests: V2.1 gate checks
  TestLinkCoverage       —  5 tests: V2.2 FormLine coverage gate
"""
from __future__ import annotations

import pathlib
import pytest

# ── Locate sample HTML ────────────────────────────────────────────────────────

SAMPLE_HTML = pathlib.Path(__file__).parent.parent / \
    "data" / "instructions" / "i1040gi_2024_synthetic.html"


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def parse_result():
    from taxflow_kb.layer2.html_parser import parse_instruction_html
    return parse_instruction_html(SAMPLE_HTML, form_type="1040", tax_year=2024)


@pytest.fixture(scope="module")
def line_sections(parse_result):
    return parse_result.line_sections()


# ══════════════════════════════════════════════════════════════════════════════
# TestHTMLParser
# ══════════════════════════════════════════════════════════════════════════════

class TestHTMLParser:

    def test_parse_succeeds(self, parse_result):
        """Parser should complete without errors on the synthetic HTML."""
        assert parse_result.parse_success, \
            f"Parse failed: {parse_result.errors}"

    def test_page_metadata(self, parse_result):
        """InstructionPage should carry correct form_type and tax_year."""
        page = parse_result.page
        assert page.form_type == "1040"
        assert page.tax_year  == 2024
        assert page.html_hash != ""
        assert "1040" in page.title

    def test_minimum_sections_extracted(self, parse_result):
        """Should extract at least 10 h2/h3 sections from the HTML."""
        assert len(parse_result.sections) >= 10, \
            f"Only {len(parse_result.sections)} sections found"

    def test_section_types_assigned(self, parse_result):
        """Every section must have a non-null SectionType."""
        from taxflow_kb.layer2.models_layer2 import SectionType
        types = {s.section_type for s in parse_result.sections}
        assert len(types) >= 3, f"Expected several section types, got: {types}"
        # At minimum WHATS_NEW, LINE_INSTRUCTION, and GENERAL/FILING_INFO present
        assert SectionType.WHATS_NEW        in types
        assert SectionType.LINE_INSTRUCTION in types

    def test_line_sections_extracted(self, parse_result):
        """Should find at least 10 sections with a line_reference."""
        n = len(parse_result.line_sections())
        assert n >= 10, f"Only {n} line sections found"

    def test_key_line_refs_present(self, parse_result):
        """Critical Form 1040 lines must be represented in the parsed output."""
        refs = {s.line_reference for s in parse_result.line_sections()}
        for expected in ("1a", "2b", "3b", "9", "11", "12", "15", "24", "35a"):
            assert expected in refs, f"Line reference '{expected}' not found"

    def test_field_mapping_populated(self, line_sections):
        """Line sections should map to at least one FormLine field name."""
        mapped = [s for s in line_sections if s.field_names]
        rate = len(mapped) / len(line_sections) if line_sections else 0
        assert rate >= 0.70, \
            f"Only {len(mapped)}/{len(line_sections)} line sections have field mappings"

    def test_wages_field_mapped(self, parse_result):
        """Line 1a section must map to WagesSalariesTipsAmt."""
        line1a = next(
            (s for s in parse_result.sections if s.line_reference == "1a"), None
        )
        assert line1a is not None, "Line 1a section not found"
        assert "WagesSalariesTipsAmt" in line1a.field_names

    def test_cross_refs_extracted(self, parse_result):
        """Sections should extract cross-references to forms and publications."""
        all_refs = [ref for s in parse_result.sections for ref in s.cross_refs]
        assert len(all_refs) >= 5, \
            f"Only {len(all_refs)} cross-references extracted (expected ≥5)"

    def test_schedule_b_cross_ref(self, parse_result):
        """The interest/dividend sections should reference Schedule B."""
        interest_sec = next(
            (s for s in parse_result.sections if s.line_reference == "2b"), None
        )
        assert interest_sec is not None, "Line 2b section not found"
        refs_lower = [r.lower() for r in interest_sec.cross_refs]
        has_sched_b = any("scheduleb" in r for r in refs_lower)
        assert has_sched_b, \
            f"Expected ScheduleB reference in Line 2b section; got {interest_sec.cross_refs}"

    def test_text_content_not_empty(self, parse_result):
        """No h3 (level 2) section should have empty text_content.

        h2 (level 1) sections are container headings whose paragraph text lives
        inside their h3 children, so they are intentionally excluded here.
        """
        empty = [s.section_id for s in parse_result.sections
                 if s.level > 1 and not s.text_content.strip()]
        assert len(empty) == 0, f"Empty text in h3 sections: {empty[:5]}"

    def test_anchor_ids_present(self, parse_result):
        """Most h3 sections should carry HTML anchor ids."""
        h3_secs = [s for s in parse_result.sections if s.level == 2]
        with_anchor = [s for s in h3_secs if s.anchor]
        rate = len(with_anchor) / len(h3_secs) if h3_secs else 0
        assert rate >= 0.70, \
            f"Only {len(with_anchor)}/{len(h3_secs)} h3 sections have anchors"


# ══════════════════════════════════════════════════════════════════════════════
# TestLayer2Structural (V2.1)
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer2Structural:

    @pytest.fixture(scope="class")
    def v21_report(self, parse_result):
        from taxflow_kb.layer2.validation import v2_1_structural
        return v2_1_structural.run(parse_result)

    def test_v21_passes_on_synthetic_html(self, v21_report):
        """V2.1 structural gate must pass on the synthetic sample."""
        assert v21_report.passed, \
            f"V2.1 failed: {v21_report.failures}"

    def test_v21_step_name(self, v21_report):
        """Report must carry the correct step identifier."""
        assert v21_report.step == "V2.1-STRUCTURAL"

    def test_v21_total_checked_matches_sections(self, parse_result, v21_report):
        """total_checked should equal the number of sections parsed."""
        assert v21_report.total_checked == len(parse_result.sections)

    def test_v21_no_failures_on_good_html(self, v21_report):
        """Good HTML should produce zero failures."""
        assert v21_report.failures == []

    def test_v21_notes_populated(self, v21_report):
        """Report must include informational notes."""
        assert len(v21_report.notes) >= 3

    def test_v21_fails_on_empty_result(self):
        """V2.1 should fail when given a parse result with no sections."""
        from taxflow_kb.layer2.models_layer2 import (
            InstructionPage, Layer2ParseResult,
        )
        from taxflow_kb.layer2.validation import v2_1_structural

        empty_page = InstructionPage(
            page_id="test-empty", form_type="1040", tax_year=2024,
            title="Empty", source_url="", html_hash="abc",
        )
        empty_result = Layer2ParseResult(
            page=empty_page, sections=[], parse_success=True,
        )
        report = v2_1_structural.run(empty_result)
        assert not report.passed
        check_names = [f["check"] for f in report.failures]
        assert "SECTION_COUNT" in check_names
        assert "LINE_SECTIONS" in check_names


# ══════════════════════════════════════════════════════════════════════════════
# TestLinkCoverage (V2.2)
# ══════════════════════════════════════════════════════════════════════════════

class TestLinkCoverage:

    @pytest.fixture(scope="class")
    def v22_report(self, parse_result):
        from taxflow_kb.layer2.validation import v2_2_link_coverage
        return v2_2_link_coverage.run(parse_result)

    def test_v22_passes_on_synthetic_html(self, v22_report):
        """V2.2 link coverage gate must pass on the synthetic sample."""
        assert v22_report.passed, \
            f"V2.2 failed: {v22_report.failures}"

    def test_v22_step_name(self, v22_report):
        """Report must carry the correct step identifier."""
        assert v22_report.step == "V2.2-LINK-COVERAGE"

    def test_v22_coverage_rate_above_threshold(self, v22_report):
        """Coverage rate must be ≥ 70%."""
        total   = v22_report.total_checked
        covered = v22_report.total_passed
        rate    = covered / total if total else 0
        assert rate >= 0.70, \
            f"Coverage {covered}/{total} = {rate*100:.1f}% below 70%"

    def test_v22_wages_field_covered(self, parse_result):
        """WagesSalariesTipsAmt must be covered by at least one section."""
        covered = {f for s in parse_result.sections for f in s.field_names}
        assert "WagesSalariesTipsAmt" in covered

    def test_v22_agi_field_covered(self, parse_result):
        """AdjustedGrossIncomeAmt must be covered by at least one section."""
        covered = {f for s in parse_result.sections for f in s.field_names}
        assert "AdjustedGrossIncomeAmt" in covered
