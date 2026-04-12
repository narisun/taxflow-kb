"""
tax_brain/instructions/neo4j_store.py

Ingests Layer 2 instruction graph into Neo4j.

New nodes
──────────
  InstructionPage   — one per HTML file (form + tax year)
  InstructionSection — one per h2/h3 section

New relationships
─────────────────
  (:InstructionPage)   -[:HAS_SECTION {sequence}]->  (:InstructionSection)
  (:InstructionSection)-[:HAS_SUBSECTION {sequence}]->(:InstructionSection)
  (:InstructionSection)-[:EXPLAINS]->                 (:FormLine)
  (:InstructionSection)-[:SEE_ALSO]->                 (:InstructionSection)
  (:InstructionSection)-[:REFERENCES_FORM]->          (:Form)

All writes use MERGE (upsert) — safe to re-run.
"""
from __future__ import annotations

import logging
from typing import Any

from tax_brain.instructions.models import (
    InstructionPage, InstructionSection, Layer2ParseResult,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Cypher statements
# ──────────────────────────────────────────────────────────────────────────────

_MERGE_PAGE = """
MERGE (p:InstructionPage {page_id: $page_id})
SET   p.form_type          = $form_type,
      p.tax_year           = $tax_year,
      p.title              = $title,
      p.source_url         = $source_url,
      p.html_hash          = $html_hash,
      p.section_count      = $section_count,
      p.line_section_count = $line_section_count
"""

_MERGE_SECTION = """
MERGE (s:InstructionSection {section_id: $section_id})
SET   s.page_id       = $page_id,
      s.heading       = $heading,
      s.section_type  = $section_type,
      s.level         = $level,
      s.sequence      = $sequence,
      s.anchor        = $anchor,
      s.line_reference= $line_reference,
      s.field_names   = $field_names,
      s.text_content  = $text_content,
      s.cross_refs    = $cross_refs
"""

_MERGE_HAS_SECTION = """
MATCH (p:InstructionPage    {page_id:    $page_id})
MATCH (s:InstructionSection {section_id: $section_id})
MERGE (p)-[:HAS_SECTION {sequence: $sequence}]->(s)
"""

_MERGE_EXPLAINS = """
MATCH  (s:InstructionSection {section_id: $section_id})
MATCH  (fl:FormLine {form_type: $form_type, short_field: $short_field, tax_year: $tax_year})
MERGE  (s)-[:EXPLAINS {line_reference: $line_reference}]->(fl)
"""

_MERGE_REFERENCES_FORM = """
MATCH  (s:InstructionSection {section_id: $section_id})
MATCH  (f:Form               {form_type:  $ref_form_type, tax_year: $tax_year})
MERGE  (s)-[:REFERENCES_FORM]->(f)
"""

# ──────────────────────────────────────────────────────────────────────────────
# Known form-type aliases (cross-ref text → Neo4j form_type)
# ──────────────────────────────────────────────────────────────────────────────

_FORM_ALIAS: dict[str, str] = {
    "FormScheduleA" : "ScheduleA",
    "ScheduleA"     : "ScheduleA",
    "FormScheduleB" : "ScheduleB",
    "ScheduleB"     : "ScheduleB",
    "FormScheduleC" : "ScheduleC",
    "ScheduleC"     : "ScheduleC",
    "FormScheduleD" : "ScheduleD",
    "ScheduleD"     : "ScheduleD",
    "FormScheduleE" : "ScheduleE",
    "ScheduleE"     : "ScheduleE",
    "FormScheduleSE": "ScheduleSE",
    "ScheduleSE"    : "ScheduleSE",
    "Form6251"      : "IRS6251",
    "Form8960"      : "IRS8960",
    "Form8812"      : "IRS8812",
    "Form1116"      : "IRS1116",
    "Form8889"      : "Form8889",   # HSA — may not be seeded yet
    "Form8995"      : "Form8995",
    "Form5329"      : "Form5329",
    "Form8919"      : "Form8919",
    "Form8606"      : "Form8606",
}


def _to_form_type(ref: str) -> str | None:
    """Map a cross-reference string to a Neo4j form_type value, or None."""
    return _FORM_ALIAS.get(ref)


# ──────────────────────────────────────────────────────────────────────────────
# Ingestion class
# ──────────────────────────────────────────────────────────────────────────────

class InstructionGraphStore:
    """
    Ingests an instruction-graph parse result into Neo4j.

    Args:
        driver : neo4j.GraphDatabase driver instance (bolt connection).
        database: Neo4j database name (default "neo4j").
    """

    def __init__(self, driver: Any, database: str = "neo4j"):
        self._driver   = driver
        self._database = database

    def _run(self, cypher: str, **params) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(cypher, **params)

    # ── Public API ─────────────────────────────────────────────────────────────

    def ingest(self, result: Layer2ParseResult) -> dict[str, int]:
        """
        Ingest a Layer2ParseResult.

        Returns a stats dict:
          pages_upserted, sections_upserted, explains_created,
          form_refs_created, skipped_explains, skipped_form_refs
        """
        if not result.parse_success:
            logger.error("Skipping ingest — parse_success=False for %s",
                         result.page.page_id)
            return {"pages_upserted": 0, "sections_upserted": 0,
                    "explains_created": 0, "form_refs_created": 0}

        stats = {
            "pages_upserted"  : 0,
            "sections_upserted": 0,
            "explains_created": 0,
            "form_refs_created": 0,
            "skipped_explains": 0,
            "skipped_form_refs": 0,
        }

        page = result.page
        self._upsert_page(page)
        stats["pages_upserted"] = 1

        for sec in result.sections:
            self._upsert_section(sec)
            self._link_page_to_section(page.page_id, sec)
            stats["sections_upserted"] += 1

            # EXPLAINS → FormLine
            for field in sec.field_names:
                ok = self._link_explains(sec, page, field)
                if ok:
                    stats["explains_created"] += 1
                else:
                    stats["skipped_explains"] += 1

            # REFERENCES_FORM → Form
            for ref in sec.cross_refs:
                form_type = _to_form_type(ref)
                if form_type:
                    ok = self._link_form_ref(sec, page, form_type)
                    if ok:
                        stats["form_refs_created"] += 1
                    else:
                        stats["skipped_form_refs"] += 1

        logger.info(
            "Layer 2 ingest complete: %s — pages=%d sections=%d "
            "explains=%d form_refs=%d",
            page.page_id,
            stats["pages_upserted"],
            stats["sections_upserted"],
            stats["explains_created"],
            stats["form_refs_created"],
        )
        return stats

    # ── Private helpers ────────────────────────────────────────────────────────

    def _upsert_page(self, page: InstructionPage) -> None:
        self._run(
            _MERGE_PAGE,
            page_id           = page.page_id,
            form_type         = page.form_type,
            tax_year          = page.tax_year,
            title             = page.title,
            source_url        = page.source_url,
            html_hash         = page.html_hash,
            section_count     = page.section_count,
            line_section_count= page.line_section_count,
        )

    def _upsert_section(self, sec: InstructionSection) -> None:
        self._run(
            _MERGE_SECTION,
            section_id    = sec.section_id,
            page_id       = sec.page_id,
            heading       = sec.heading,
            section_type  = sec.section_type.value,
            level         = sec.level,
            sequence      = sec.sequence,
            anchor        = sec.anchor or "",
            line_reference= sec.line_reference or "",
            field_names   = sec.field_names,
            text_content  = sec.text_content,
            cross_refs    = sec.cross_refs,
        )

    def _link_page_to_section(
        self, page_id: str, sec: InstructionSection
    ) -> None:
        self._run(
            _MERGE_HAS_SECTION,
            page_id    = page_id,
            section_id = sec.section_id,
            sequence   = sec.sequence,
        )

    def _link_explains(
        self, sec: InstructionSection,
        page: InstructionPage, field: str,
    ) -> bool:
        """Create EXPLAINS relationship to FormLine. Returns True on success."""
        try:
            self._run(
                _MERGE_EXPLAINS,
                section_id     = sec.section_id,
                form_type      = page.form_type,
                short_field    = field,
                tax_year       = page.tax_year,
                line_reference = sec.line_reference or "",
            )
            return True
        except Exception as exc:
            logger.debug("EXPLAINS skipped %s→%s: %s", sec.section_id, field, exc)
            return False

    def _link_form_ref(
        self, sec: InstructionSection,
        page: InstructionPage, ref_form_type: str,
    ) -> bool:
        """Create REFERENCES_FORM relationship to Form node. Returns True on success."""
        try:
            self._run(
                _MERGE_REFERENCES_FORM,
                section_id    = sec.section_id,
                ref_form_type = ref_form_type,
                tax_year      = page.tax_year,
            )
            return True
        except Exception as exc:
            logger.debug("REFERENCES_FORM skipped %s→%s: %s",
                         sec.section_id, ref_form_type, exc)
            return False
