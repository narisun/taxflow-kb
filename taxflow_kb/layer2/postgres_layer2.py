"""
taxflow_kb/layer2/postgres_layer2.py

Ingests Layer 2 instruction data into PostgreSQL (irs_kb schema).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from taxflow_kb.layer2.models_layer2 import Layer2ParseResult

logger = logging.getLogger(__name__)

_SCHEMA = "irs_kb"


class PostgresLayer2Ingestion:
    """
    Writes instruction page and section data into PostgreSQL.

    Args:
        conn : psycopg2 connection (autocommit=False).
    """

    def __init__(self, conn: Any):
        self._conn = conn

    # ── Public API ─────────────────────────────────────────────────────────────

    def ensure_schema(self, sql_path: str = "schema/postgres_layer2.sql") -> None:
        """Run the Layer 2 DDL file to create tables if they don't exist."""
        from pathlib import Path
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self._conn.cursor() as cur:
            cur.execute(sql)
        self._conn.commit()
        logger.info("Layer 2 PostgreSQL schema ensured from %s", sql_path)

    def ingest(
        self,
        result      : Layer2ParseResult,
        source_path : str = "",
        explains_count  : int = 0,
        form_refs_count : int = 0,
    ) -> None:
        """
        Upsert an InstructionPage and all its InstructionSections.

        Args:
            result         : Parsed Layer2ParseResult.
            source_path    : File path of the HTML source (for audit log).
            explains_count : Number of EXPLAINS relationships created in Neo4j.
            form_refs_count: Number of REFERENCES_FORM relationships created.
        """
        page = result.page

        with self._conn.cursor() as cur:
            # ── Upsert InstructionPage ────────────────────────────────────────
            cur.execute(
                f"""
                INSERT INTO {_SCHEMA}.instruction_pages
                    (page_id, form_type, tax_year, title, source_url,
                     html_hash, section_count, line_section_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (page_id) DO UPDATE SET
                    html_hash          = EXCLUDED.html_hash,
                    section_count      = EXCLUDED.section_count,
                    line_section_count = EXCLUDED.line_section_count,
                    ingested_at        = NOW()
                """,
                (page.page_id, page.form_type, page.tax_year, page.title,
                 page.source_url, page.html_hash,
                 page.section_count, page.line_section_count),
            )

            # ── Upsert InstructionSections ────────────────────────────────────
            for sec in result.sections:
                cur.execute(
                    f"""
                    INSERT INTO {_SCHEMA}.instruction_sections
                        (section_id, page_id, heading, section_type, level,
                         sequence, anchor, line_reference, field_names,
                         text_content, cross_refs)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (section_id) DO UPDATE SET
                        heading       = EXCLUDED.heading,
                        text_content  = EXCLUDED.text_content,
                        field_names   = EXCLUDED.field_names,
                        cross_refs    = EXCLUDED.cross_refs,
                        ingested_at   = NOW()
                    """,
                    (sec.section_id, sec.page_id, sec.heading,
                     sec.section_type.value, sec.level, sec.sequence,
                     sec.anchor, sec.line_reference,
                     sec.field_names, sec.text_content, sec.cross_refs),
                )

            # ── Write ingestion log ───────────────────────────────────────────
            cur.execute(
                f"""
                INSERT INTO {_SCHEMA}.instruction_ingestion_log
                    (page_id, html_hash, source_path, section_count,
                     explains_count, form_refs_count,
                     parse_success, errors, warnings)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (page.page_id, page.html_hash, source_path,
                 page.section_count, explains_count, form_refs_count,
                 result.parse_success, result.errors, result.warnings),
            )

        self._conn.commit()
        logger.info(
            "PostgreSQL Layer 2 ingest: page=%s sections=%d",
            page.page_id, len(result.sections),
        )

    def save_validation(
        self,
        step          : str,
        passed        : bool,
        total_checked : int,
        total_passed  : int,
        total_failed  : int,
        failures      : list[dict],
        notes         : list[str],
        page_id       : str | None = None,
    ) -> None:
        """Persist a Layer 2 validation gate result."""
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_SCHEMA}.layer2_validation_runs
                    (step, page_id, passed, total_checked, total_passed,
                     total_failed, failures, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (step, page_id, passed, total_checked,
                 total_passed, total_failed,
                 json.dumps(failures), notes),
            )
        self._conn.commit()

    def get_field_names_in_sections(self) -> list[str]:
        """Return all unique field names that appear in at least one section."""
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT unnest(field_names) AS fn
                FROM {_SCHEMA}.instruction_sections
                ORDER BY 1
                """
            )
            return [row[0] for row in cur.fetchall()]
