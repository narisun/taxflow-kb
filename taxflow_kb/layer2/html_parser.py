"""
taxflow_kb/layer2/html_parser.py

Parses IRS instruction HTML pages into a structured Layer2ParseResult.

Uses only the Python standard library (html.parser) — no BeautifulSoup required.

Parsing strategy
────────────────
Handles two HTML structures produced by IRS.gov:

  Synthetic / simple HTML (h2 / h3 only)
  ───────────────────────────────────────
  · h2  → level-1 major section (What's New, Line Instructions …)
  · h3  → level-2 line / subsection

  Real IRS publication HTML (irs.gov/instructions)
  ──────────────────────────────────────────────────
  · h2.role-major-section → level-1 major section
  · h2 with other classes  → navigation chrome; skipped
  · h2.role-taxtable       → Tax Table; entire section skipped
  · h3.role-subsect / h3.worksheet → level-2 category heading
  · h4.role-hd1  → level-3 PRIMARY line instruction ("Line 1a", "Lines 4a, 4b, 4c")
  · h4.role-hd2  → sub-item inside the current hd1; its <p> content merges in
  · h4.role-hd3  → deep sub-item; also merges into the current hd1
  · other h4     → ignored

For every heading, the parser:
  1. Classifies SectionType (WHATS_NEW, LINE_INSTRUCTION, FILING_INFO …)
  2. Extracts a line_reference ("1a", "4b", "12" …) by regex
  3. Maps line_reference → list[field_name] via LINE_TO_FIELDS
  4. Collects cross-references from paragraph text
  5. Returns a Layer2ParseResult
"""
from __future__ import annotations

import hashlib
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from taxflow_kb.layer2.models_layer2 import (
    InstructionPage, InstructionSection, Layer2ParseResult, SectionType,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Line → FormLine field name mapping  (Form 1040 / TY 2024–2025)
# ──────────────────────────────────────────────────────────────────────────────

LINE_TO_FIELDS: dict[str, list[str]] = {
    "1a" : ["WagesSalariesTipsAmt"],
    "1z" : ["WagesSalariesTipsAmt"],
    "2a" : [],                                  # tax-exempt interest (not in Layer 1 rules)
    "2b" : ["TaxableInterestAmt"],
    "3a" : ["QualifiedDividendsAmt"],
    "3b" : ["OrdinaryDividendsAmt"],
    "4a" : [],
    "4b" : ["IRADistributionsAmt"],
    "5a" : [],
    "5b" : ["PensionsAnnuitiesAmt"],
    "6a" : [],
    "6b" : ["SocialSecurityBenefitsAmt"],
    # Line 8 on Form 1040 = "Additional income from Schedule 1, line 10".
    # The Schedule 1 instruction section is headed "Lines 8a Through 8z" (role-hd1)
    # so we map "8a" (the first ref the parser extracts) to the same fields as "8".
    "8"  : ["OtherIncomeAmt", "SupplementalIncomeOrLossAmt",
             "SelfEmploymentNetProfitAmt"],
    "8a" : ["OtherIncomeAmt", "SupplementalIncomeOrLossAmt",
             "SelfEmploymentNetProfitAmt"],
    # Capital gains — real IRS 2025 uses "Line 7a"; keep plain "7" for synthetic
    "7"  : ["CapitalGainOrLossAmt"],
    "7a" : ["CapitalGainOrLossAmt"],
    "8"  : ["OtherIncomeAmt", "SupplementalIncomeOrLossAmt",
             "SelfEmploymentNetProfitAmt"],
    "9"  : ["TotalIncomeAmt"],
    "10" : ["EducatorExpensesAmt", "StudentLoanInterestDeductionAmt",
             "HealthSavingsAccountDedAmt", "SelfEmployedHealthInsDedAmt",
             "SEPSIMPLEQualifiedPlansAmt", "SelfEmploymentTaxDeductionAmt",
             "AlimonyPaidAmt"],
    "11" : ["AdjustedGrossIncomeAmt"],
    "12" : ["StandardDeductionAmt", "DeductionsAmt", "ItemizedOrStandardCd",
             "StateLocalTaxDeductionAmt"],
    # Real IRS 2025 splits line 12 into 12a–12e
    "12a": ["StandardDeductionAmt"],
    "12b": ["DeductionsAmt"],
    "12c": ["ItemizedOrStandardCd"],
    "12d": ["StateLocalTaxDeductionAmt"],
    "12e": ["StandardDeductionAmt", "DeductionsAmt", "ItemizedOrStandardCd",
             "StateLocalTaxDeductionAmt"],
    "13" : ["QualifiedBusinessIncomeDedAmt"],
    "13a": ["QualifiedBusinessIncomeDedAmt"],
    "13b": ["QualifiedBusinessIncomeDedAmt"],
    "15" : ["TaxableIncomeAmt"],
    "16" : ["IncomeTaxAmt"],
    "17" : ["AlternativeMinimumTaxAmt", "NetInvestmentIncomeTaxAmt",
             "AdditionalMedicareTaxAmt"],
    "19" : ["ChildTaxCreditAmt"],
    "24" : ["TotalTaxAmt"],
    "25" : ["FederalIncomeTaxWithheldAmt"],    # "Line 25 Federal Income Tax Withheld"
    "25a": ["FederalIncomeTaxWithheldAmt"],
    "26" : ["EstimatedTaxPaymentsAmt"],
    # EIC — real IRS 2025 heading is "Lines 27a, 27b, and 27c" (role-step-section)
    # so "27a" is the first extracted ref.  Keep plain "27" for synthetic HTML.
    "27" : ["EarnedIncomeCreditAmt"],
    "27a": ["EarnedIncomeCreditAmt"],
    "28" : ["AdditionalChildTaxCreditAmt"],
    "33" : ["TotalPaymentsAmt"],
    "35a": ["RefundAmt"],
    "36" : ["AmountAppliedToNextYrAmt"],
    "37" : [],
}

# ──────────────────────────────────────────────────────────────────────────────
# Section classification helpers
# ──────────────────────────────────────────────────────────────────────────────

_WHATS_NEW_RE  = re.compile(r"what'?s?\s+new", re.I)
_REMINDER_RE   = re.compile(r"^reminder", re.I)
_FILING_RE     = re.compile(r"filing\s+(information|status|requirements?)", re.I)
_LINE_RE       = re.compile(r"^Lines?\s+\d", re.I)
_SCHED_REQ_RE  = re.compile(r"schedule\s+[a-z0-9]+\s+(requirement|attachment)", re.I)
_PREPARER_RE   = re.compile(r"paid\s+preparer", re.I)
_SIGNATURE_RE  = re.compile(r"sign(ature|s?\s+your\s+return)", re.I)

# Cross-reference patterns
_FORM_REF_RE   = re.compile(r"\bForm\s+([\w\-]+\d[\w\-]*)", re.I)
_SCHED_REF_RE  = re.compile(r"\bSchedule\s+([A-Z0-9]+)", re.I)
_PUB_REF_RE    = re.compile(r"\bPub(?:lication)?\.\s*(\d+[\w\-]*)", re.I)


def _classify_section(heading: str, level: int, h2_text: str) -> SectionType:
    """Classify a section based on heading text and the current h2 context."""
    if _WHATS_NEW_RE.search(h2_text) or _WHATS_NEW_RE.search(heading):
        return SectionType.WHATS_NEW
    if _REMINDER_RE.search(h2_text) or _REMINDER_RE.search(heading):
        return SectionType.REMINDER
    if _PREPARER_RE.search(h2_text) or _PREPARER_RE.search(heading):
        return SectionType.PREPARER
    if _SIGNATURE_RE.search(h2_text) or _SIGNATURE_RE.search(heading):
        return SectionType.SIGNATURE
    if _SCHED_REQ_RE.search(heading):
        return SectionType.SCHEDULE_REQ
    if _LINE_RE.match(heading):
        return SectionType.LINE_INSTRUCTION
    if "line instruction" in h2_text.lower():
        return SectionType.LINE_INSTRUCTION
    if _FILING_RE.search(h2_text) or _FILING_RE.search(heading):
        return SectionType.FILING_INFO
    return SectionType.GENERAL


def _extract_line_ref(heading: str) -> Optional[str]:
    """Return the canonical line reference from a heading string.

    Handles three forms:
      · "Line 1a"                  → "1a"
      · "Lines 2a–2b"              → "2b" (prefer end of range when mapped)
      · "Lines 4a, 4b, and 4c"    → first ref that has a LINE_TO_FIELDS mapping

    Returns None if no line number is found.
    """
    # Must have "Line" or "Lines" prefix
    prefix = re.search(r'Lines?\s+', heading, re.I)
    if not prefix:
        return None

    rest = heading[prefix.end():]

    # Check for a range with an em-dash or hyphen: "2a–2b"
    range_m = re.match(r'(\d+[a-z]?)\s*[–\-]\s*(\d+[a-z]?)', rest)
    if range_m:
        first = range_m.group(1).lower()
        last  = range_m.group(2).lower()
        # Prefer the end of the range when it has a field mapping
        if LINE_TO_FIELDS.get(last):
            return last
        return first

    # Collect all number+optional-letter tokens (e.g. "4a", "4b", "4c" from "4a, 4b, and 4c")
    refs = [r.lower() for r in re.findall(r'\d+[a-z]?', rest)]
    if not refs:
        return None

    # Return the first ref that has a non-empty field mapping; else return the first
    for ref in refs:
        if LINE_TO_FIELDS.get(ref):
            return ref
    return refs[0]


def _extract_cross_refs(text: str) -> list[str]:
    """Extract form, schedule, and publication references from paragraph text."""
    refs: list[str] = []
    for m in _FORM_REF_RE.finditer(text):
        refs.append(f"Form{m.group(1)}")
    for m in _SCHED_REF_RE.finditer(text):
        refs.append(f"Schedule{m.group(1)}")
    for m in _PUB_REF_RE.finditer(text):
        refs.append(f"Publication{m.group(1)}")
    return list(dict.fromkeys(refs))   # deduplicate, preserve order


# ──────────────────────────────────────────────────────────────────────────────
# HTML parser state machine
# ──────────────────────────────────────────────────────────────────────────────

# h2 classes that flag non-content navigation elements — skip silently
_H2_SKIP_CLASSES = ("visually-hidden", "accordion-title", "subtitle")
# h2 class that marks a large non-instruction section — skip the entire section
_H2_SKIP_SECTION_CLASSES = ("role-taxtable",)


class _IRSHTMLParser(HTMLParser):
    """
    Stateful HTML parser that walks h2/h3/h4 headings and accumulates <p> text.

    For the real IRS HTML format:
      · h4.role-hd1 is the primary line instruction level (level 3)
      · h4.role-hd2 / h4.role-hd3 are sub-items; their <p> content is merged
        into the enclosing hd1 section rather than creating new sections
      · Non-content h2 elements (navigation chrome, Tax Table) are skipped

    For the synthetic / simplified HTML format (h2 / h3 only):
      · h2 → level 1,  h3 → level 2  (unchanged behaviour)
    """

    def __init__(self):
        super().__init__()
        self._sections     : list[dict] = []
        self._cur          : Optional[dict] = None
        self._in_heading   : Optional[str]  = None   # "h2"|"h3"|"h4"
        self._in_para      : bool           = False
        self._buf          : list[str]      = []
        self._h2_text      : str            = ""     # current major section heading
        self._in_hd1       : bool           = False  # inside an h4.role-hd1 section
        self._skip_section : bool           = False  # skip until next major h2
        self._skip_tags    : set[str]       = {"script", "style", "nav", "head"}
        self._skipping     : int            = 0      # nesting depth inside skip tags

    # ── Tag open ──────────────────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs):
        if tag in self._skip_tags:
            self._skipping += 1
            return
        if self._skipping:
            return

        attr_dict = dict(attrs)
        cls       = attr_dict.get("class", "")

        # ── h2 ───────────────────────────────────────────────────────────────
        if tag == "h2":
            # Silent navigation chrome — ignore, don't touch state
            if any(kw in cls for kw in _H2_SKIP_CLASSES):
                return

            # Large non-instruction block (Tax Table) — skip the whole section
            if any(kw in cls for kw in _H2_SKIP_SECTION_CLASSES):
                self._flush()
                self._cur          = None
                self._skip_section = True
                return

            # Has a class but NOT a content section class — ignore silently
            # (e.g. promo banners inside <div class="field ..."><h2>…</h2>)
            if cls and "role-major-section" not in cls:
                return

            # Valid content h2 (role-major-section OR no class = synthetic)
            self._skip_section = False
            self._in_hd1       = False
            self._flush()
            self._in_heading   = "h2"
            self._buf          = []
            self._cur          = {
                "level"  : 1,
                "anchor" : attr_dict.get("id"),
                "heading": "",
                "texts"  : [],
            }

        # ── h3 ───────────────────────────────────────────────────────────────
        elif tag == "h3":
            if self._skip_section:
                return
            self._in_hd1     = False
            self._flush()
            self._in_heading = "h3"
            self._buf        = []
            self._cur        = {
                "level"  : 2,
                "anchor" : attr_dict.get("id"),
                "heading": "",
                "texts"  : [],
            }

        # ── h4 ───────────────────────────────────────────────────────────────
        elif tag == "h4":
            if self._skip_section:
                return

            if "role-hd1" in cls or "role-step-section" in cls:
                # Primary line instruction heading — new level-3 section.
                # role-step-section is used by IRS for complex multi-step sections
                # such as "Lines 27a, 27b, and 27c — Earned Income Credit (EIC)".
                self._flush()
                self._in_hd1     = True
                self._in_heading = "h4"
                self._buf        = []
                self._cur        = {
                    "level"  : 3,
                    "anchor" : attr_dict.get("id"),
                    "heading": "",
                    "texts"  : [],
                }

            elif "role-hd2" in cls or "role-hd3" in cls:
                # Sub-item within the current hd1 — do NOT flush; just silence
                # the heading capture (paragraph text will still flow in via <p>)
                if self._in_hd1:
                    self._in_heading = None
                    self._buf        = []
                # If there's no parent hd1, ignore this h4 entirely

            # role-intro, role-step-section, worksheet sub-h4, etc. → ignore

        # ── Inline anchor with a "name" attribute (IRS convention) ───────────
        elif tag == "a":
            name = attr_dict.get("name")
            if name and self._in_heading and self._cur:
                if not self._cur.get("anchor"):
                    self._cur["anchor"] = name

        # ── Paragraph ─────────────────────────────────────────────────────────
        elif tag == "p":
            if self._skip_section:
                return
            self._in_para = True
            self._buf     = []

        # Transparent inline elements — content captured by enclosing handler
        # (span, strong, em, b, i, etc.)

    # ── Tag close ─────────────────────────────────────────────────────────────

    def handle_endtag(self, tag: str):
        if tag in self._skip_tags:
            self._skipping = max(0, self._skipping - 1)
            return
        if self._skipping:
            return

        if tag in ("h2", "h3", "h4") and self._in_heading == tag:
            heading_text         = " ".join(self._buf).strip()
            if self._cur:
                self._cur["heading"] = heading_text
            if tag == "h2":
                self._h2_text    = heading_text
            self._in_heading     = None
            self._buf            = []

        elif tag == "p" and self._in_para:
            text = " ".join(self._buf).strip()
            if text and self._cur:
                self._cur["texts"].append(text)
            self._in_para = False
            self._buf     = []

    # ── Character data ────────────────────────────────────────────────────────

    def handle_data(self, data: str):
        if self._skipping:
            return
        if self._in_heading or self._in_para:
            chunk = data.replace("\n", " ").replace("\r", "")
            if chunk.strip():
                self._buf.append(chunk)

    # ── Flush ─────────────────────────────────────────────────────────────────

    def _flush(self):
        """Commit the current section (if it has a heading) to the list."""
        if self._cur and self._cur.get("heading"):
            self._cur["h2_context"] = self._h2_text
            self._sections.append(self._cur)
        self._cur = None

    def finish(self) -> list[dict]:
        self._flush()
        return self._sections


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def parse_instruction_html(
    html_path  : str | Path,
    form_type  : str = "1040",
    tax_year   : int = 2024,
    source_url : str = "",
) -> Layer2ParseResult:
    """
    Parse an IRS instruction HTML file into a Layer2ParseResult.

    Works with both synthetic (h2/h3) and real IRS publication (h2/h3/h4) HTML.

    Args:
        html_path  : Path to the HTML file.
        form_type  : IRS form number string, e.g. "1040".
        tax_year   : Tax year integer.
        source_url : Canonical URL of the page (optional metadata).

    Returns:
        Layer2ParseResult with InstructionPage + list[InstructionSection].
    """
    path = Path(html_path)
    errors:   list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return Layer2ParseResult(
            page=InstructionPage(
                page_id=f"i{form_type.lower()}gi-{tax_year}",
                form_type=form_type, tax_year=tax_year,
                title="", source_url=source_url, html_hash="",
            ),
            sections=[],
            parse_success=False,
            errors=[f"File not found: {html_path}"],
        )

    raw_html  = path.read_text(encoding="utf-8")
    html_hash = hashlib.sha256(raw_html.encode()).hexdigest()

    # Extract page title
    title_m = re.search(r"<title>([^<]+)</title>", raw_html, re.I)
    title   = (title_m.group(1).strip() if title_m
                else f"Form {form_type} Instructions {tax_year}")

    page_id = f"i{form_type.lower()}gi-{tax_year}"

    # Run the state-machine parser
    parser = _IRSHTMLParser()
    try:
        parser.feed(raw_html)
    except Exception as exc:
        errors.append(f"HTML parse error: {exc}")

    raw_sections = parser.finish()

    if not raw_sections:
        errors.append("No content sections found — check document structure.")
        return Layer2ParseResult(
            page=InstructionPage(
                page_id=page_id, form_type=form_type, tax_year=tax_year,
                title=title, source_url=source_url, html_hash=html_hash,
            ),
            sections=[],
            parse_success=False,
            errors=errors,
        )

    # Build InstructionSection objects
    sections: list[InstructionSection] = []
    sequence = 0

    for raw in raw_sections:
        heading    = raw["heading"]
        level      = raw["level"]
        anchor     = raw.get("anchor")
        h2_context = raw.get("h2_context", "")
        texts      = raw.get("texts", [])

        if not heading:
            warnings.append(f"Empty heading at sequence {sequence} — skipped.")
            continue

        sec_type   = _classify_section(heading, level, h2_context)
        line_ref   = _extract_line_ref(heading)

        field_names  = LINE_TO_FIELDS.get(line_ref, []) if line_ref else []
        text_content = " ".join(texts).strip()
        cross_refs   = _extract_cross_refs(text_content)

        section_id = f"{page_id}::{anchor or heading[:40].replace(' ', '_')}"

        sections.append(InstructionSection(
            section_id    = section_id,
            page_id       = page_id,
            heading       = heading,
            section_type  = sec_type,
            level         = level,
            sequence      = sequence,
            anchor        = anchor,
            line_reference= line_ref,
            field_names   = field_names,
            text_content  = text_content,
            cross_refs    = cross_refs,
        ))
        sequence += 1

    line_sections = [s for s in sections if s.line_reference is not None]

    if not line_sections:
        warnings.append("No line-instruction sections found — FormLine linkage will be empty.")

    page = InstructionPage(
        page_id            = page_id,
        form_type          = form_type,
        tax_year           = tax_year,
        title              = title,
        source_url         = source_url or str(path),
        html_hash          = html_hash,
        section_count      = len(sections),
        line_section_count = len(line_sections),
    )

    logger.info(
        "Parsed %s: %d sections, %d with line references",
        page_id, len(sections), len(line_sections),
    )

    return Layer2ParseResult(
        page          = page,
        sections      = sections,
        parse_success = len(errors) == 0,
        errors        = errors,
        warnings      = warnings,
    )
