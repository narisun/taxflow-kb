"""
taxkb/instructions/models.py

Pydantic v2 models for Layer 2 — IRS HTML Instruction Graph entities.

Graph additions:
  Nodes:   InstructionPage, InstructionSection
  Edges:   HAS_SECTION, HAS_SUBSECTION, EXPLAINS (→ FormLine), SEE_ALSO,
           REFERENCES_FORM (→ Form)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SectionType(str, Enum):
    WHATS_NEW       = "WHATS_NEW"
    REMINDER        = "REMINDER"
    FILING_INFO     = "FILING_INFO"
    LINE_INSTRUCTION= "LINE_INSTRUCTION"
    SCHEDULE_REQ    = "SCHEDULE_REQ"
    PREPARER        = "PREPARER"
    SIGNATURE       = "SIGNATURE"
    GENERAL         = "GENERAL"


# ──────────────────────────────────────────────────────────────────────────────
# Instruction page metadata
# ──────────────────────────────────────────────────────────────────────────────

class InstructionPage(BaseModel):
    """Represents one IRS HTML instruction publication (e.g. i1040gi for TY 2024)."""
    page_id           : str           # "i1040gi-2024"
    form_type         : str           # "1040"
    tax_year          : int           # 2024
    title             : str           # "2024 Instructions for Form 1040 and 1040-SR"
    source_url        : str           # canonical IRS URL or file path for synthetic
    html_hash         : str           # SHA-256 of raw HTML (for change detection)
    section_count     : int = 0
    line_section_count: int = 0       # sections with a line_reference

    def page_label(self) -> str:
        return f"{self.form_type} Instructions {self.tax_year}"


# ──────────────────────────────────────────────────────────────────────────────
# Instruction section
# ──────────────────────────────────────────────────────────────────────────────

class InstructionSection(BaseModel):
    """
    One <h2> or <h3> section within an instruction page.

    line_reference  — the raw line label extracted from the heading, e.g. "1a",
                      "2b", "12".  None for general sections.
    field_names     — short field names from FormLine that this section explains,
                      e.g. ["WagesSalariesTipsAmt"].  Populated by the field map.
    cross_refs      — form types or publication numbers mentioned in the text,
                      e.g. ["ScheduleB", "IRS8960", "Publication 550"].
    anchor          — the HTML id= attribute value, used as stable identifier.
    """
    section_id      : str                        # "i1040gi-2024::line1a"
    page_id         : str                        # parent page
    heading         : str                        # raw heading text
    section_type    : SectionType
    level           : int                        # 1 = h2, 2 = h3
    sequence        : int                        # document order
    anchor          : Optional[str] = None       # HTML id attribute
    line_reference  : Optional[str] = None       # "1a", "2b", "12", etc.
    field_names     : list[str]     = Field(default_factory=list)
    text_content    : str           = ""         # concatenated paragraph text
    cross_refs      : list[str]     = Field(default_factory=list)  # form/pub refs


# ──────────────────────────────────────────────────────────────────────────────
# Parse result
# ──────────────────────────────────────────────────────────────────────────────

class Layer2ParseResult(BaseModel):
    """Output of the HTML parser for one instruction page."""
    page          : InstructionPage
    sections      : list[InstructionSection]
    parse_success : bool
    errors        : list[str] = Field(default_factory=list)
    warnings      : list[str] = Field(default_factory=list)

    def line_sections(self) -> list[InstructionSection]:
        return [s for s in self.sections if s.line_reference is not None]

    def sections_by_type(self, st: SectionType) -> list[InstructionSection]:
        return [s for s in self.sections if s.section_type == st]
