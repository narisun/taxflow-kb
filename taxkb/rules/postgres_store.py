"""
taxkb/rules/postgres_store.py

Mirrors MeF rules into PostgreSQL (irs_kb schema).
PostgreSQL serves as the relational store for the irs-forms-mcp tool layer
and provides SQL-accessible validation queries.

Requires psycopg2:  pip install psycopg2-binary
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import psycopg2.extras

from taxkb.models import (
    MeFRule, ParseResult, RuleVersionDiff, ValidationReport,
    TestReturnCase, TestReturnResult, ChangeType,
)

logger = logging.getLogger(__name__)


class RuleStore:
    """
    Mirrors MeF rules and all validation artefacts to PostgreSQL.

    Usage:
        conn = psycopg2.connect("postgresql://user:pass@localhost:5432/taxflow")
        pg = RuleStore(conn)
        pg.ensure_schema()
        pg.ingest_rules(rules, parse_result)
        pg.close()
    """

    def __init__(self, conn: Any) -> None:
        """Accept an existing database connection.

        The caller is responsible for connection lifecycle (close/return to pool).
        Use factories.create_pool() + pool.getconn() to obtain a connection.
        """
        self._conn = conn
        self._conn.autocommit = False
        logger.info("PostgreSQL connection established.")

    def close(self) -> None:
        """Release the connection reference.

        Does NOT close the underlying connection -- the pool or caller
        that provided it is responsible for its lifecycle.
        """
        self._conn = None

    # ──────────────────────────────────────────────────────────────────────
    # Schema setup
    # ──────────────────────────────────────────────────────────────────────

    def ensure_schema(self, schema_file: Optional[str] = None) -> None:
        """
        Run the DDL schema file to create tables if they don't exist.
        Defaults to ``taxkb/schema/postgres_schema.sql``.
        """
        if schema_file is None:
            schema_file = str(
                Path(__file__).parent.parent / "schema" / "postgres_schema.sql"
            )
        ddl = Path(schema_file).read_text()
        with self._conn.cursor() as cur:
            cur.execute(ddl)
        self._conn.commit()
        logger.info("PostgreSQL schema applied from %s", schema_file)

    # ──────────────────────────────────────────────────────────────────────
    # Rule ingestion
    # ──────────────────────────────────────────────────────────────────────

    def ingest_rules(
        self,
        rules: list[MeFRule],
        parse_result: ParseResult,
        source_file: str = "",
        file_hash: str = "",
    ) -> int:
        """
        Upsert all rules and log the ingestion run.
        Returns the number of rows upserted.

        Args:
            rules: List of MeFRule objects to ingest.
            parse_result: ParseResult metadata about the ingestion.
            source_file: Source CSV file path. If empty, constructs from parse_result metadata.
            file_hash: Hash of the source file. If empty, will be empty in the log.
        """
        # Construct source_file if not provided
        if not source_file:
            source_file = f"data/sample/mef_{rules[0].form_family if rules else 'UNKNOWN'}_{parse_result.tax_year}_v{parse_result.schema_version}.csv"

        with self._conn.cursor() as cur:
            # Log the ingestion run
            cur.execute(
                """
                INSERT INTO irs_kb.csv_ingestion_log
                    (tax_year, schema_version, form_family, file_path, file_hash,
                     total_rows, parse_success, parse_failed, null_field_rows,
                     duplicate_ids, failed_detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_hash) DO NOTHING
                """,
                (
                    parse_result.tax_year,
                    parse_result.schema_version,
                    rules[0].form_family if rules else "UNKNOWN",
                    source_file,
                    file_hash,
                    parse_result.total_rows,
                    parse_result.parse_success,
                    parse_result.parse_failed,
                    parse_result.null_field_rows,
                    parse_result.duplicate_ids,
                    json.dumps(parse_result.failed_rules),
                ),
            )

            # Upsert rules
            upserted = 0
            for rule in rules:
                cur.execute(
                    """
                    INSERT INTO irs_kb.irs_business_rules
                        (rule_id, tax_year, schema_version, rule_type, form_family,
                         field_path, rule_text, rule_expression, expression_ast,
                         error_code, severity, parse_success, parse_error_msg, is_current)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                    ON CONFLICT (rule_id, tax_year, schema_version)
                    DO UPDATE SET
                        rule_type       = EXCLUDED.rule_type,
                        rule_text       = EXCLUDED.rule_text,
                        rule_expression = EXCLUDED.rule_expression,
                        expression_ast  = EXCLUDED.expression_ast,
                        parse_success   = EXCLUDED.parse_success,
                        parse_error_msg = EXCLUDED.parse_error_msg,
                        is_current      = true
                    """,
                    (
                        rule.rule_id,
                        rule.tax_year,
                        rule.schema_version,
                        rule.rule_type.value,
                        rule.form_family,
                        rule.field_path,
                        rule.rule_text,
                        rule.rule_expression,
                        json.dumps(rule.expression_ast) if rule.expression_ast else None,
                        rule.error_code,
                        rule.severity.value,
                        rule.parse_success,
                        rule.parse_error_msg,
                    ),
                )
                upserted += 1

        self._conn.commit()
        logger.info("PostgreSQL: upserted %d rules", upserted)
        return upserted

    def mark_superseded(self, rule_id: str, tax_year: int, new_version: str) -> None:
        """Mark all prior schema versions of a rule as not current."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE irs_kb.irs_business_rules
                SET is_current = false
                WHERE rule_id = %s AND tax_year = %s AND schema_version <> %s
                """,
                (rule_id, tax_year, new_version),
            )
        self._conn.commit()

    def record_version_diff(self, diff: RuleVersionDiff) -> None:
        """Append a version change record to rule_version_history."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO irs_kb.rule_version_history
                    (rule_id, tax_year, old_version, new_version, change_type,
                     changed_fields, old_expression, new_expression)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    diff.rule_id,
                    diff.tax_year,
                    diff.old_version,
                    diff.new_version,
                    diff.change_type.value,
                    diff.changed_fields,
                    diff.old_expression,
                    diff.new_expression,
                ),
            )
        self._conn.commit()

    # ──────────────────────────────────────────────────────────────────────
    # Validation run storage
    # ──────────────────────────────────────────────────────────────────────

    def save_validation_report(
        self,
        report: ValidationReport,
        tax_year: int,
        schema_version: Optional[str] = None,
        run_by: str = "cli",
    ) -> int:
        """Persist a ValidationReport. Returns the new run ID."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO irs_kb.validation_runs
                    (step, tax_year, schema_version, passed,
                     total_checked, total_passed, total_failed, pass_rate,
                     failures, warnings, notes, run_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    report.step,
                    tax_year,
                    schema_version,
                    report.passed,
                    report.total_checked,
                    report.total_passed,
                    report.total_failed,
                    report.pass_rate,
                    json.dumps(report.failures),
                    json.dumps(report.warnings),
                    report.notes,
                    run_by,
                ),
            )
            run_id = cur.fetchone()[0]
        self._conn.commit()
        logger.info("Validation run %d saved for step %s", run_id, report.step)
        return run_id

    # ──────────────────────────────────────────────────────────────────────
    # Test return management
    # ──────────────────────────────────────────────────────────────────────

    def save_test_case(self, case: TestReturnCase) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO irs_kb.test_return_cases
                    (case_id, description, tax_year, expected_outcome,
                     expected_errors, return_data, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id) DO UPDATE SET
                    description      = EXCLUDED.description,
                    expected_outcome = EXCLUDED.expected_outcome,
                    expected_errors  = EXCLUDED.expected_errors,
                    return_data      = EXCLUDED.return_data
                """,
                (
                    case.case_id,
                    case.description,
                    case.tax_year,
                    case.expected_outcome.value,
                    case.expected_errors,
                    json.dumps(case.return_data),
                    "SYNTHETIC",
                ),
            )
        self._conn.commit()

    def save_test_result(
        self,
        result: TestReturnResult,
        run_id: Optional[int] = None,
        tax_year: Optional[int] = None,
        default_tax_year: Optional[int] = None,
    ) -> None:
        """
        Save a test return result to the database.

        Args:
            result: TestReturnResult object with actual outcome and fired rules.
            run_id: Optional validation run ID to associate this result with.
            tax_year: Tax year for this test result.
            default_tax_year: Fallback tax year when *tax_year* is None.
                The caller should pass ``get_settings().default_tax_year``
                rather than having the store reach into config itself.
        """
        if tax_year is None:
            tax_year = default_tax_year

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO irs_kb.test_return_results
                    (validation_run_id, case_id, tax_year, actual_outcome,
                     fired_rules, fired_errors, outcome_match, error_code_match, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    result.case_id,
                    tax_year,
                    result.actual_outcome.value,
                    result.fired_rules,
                    result.fired_errors,
                    result.outcome_match,
                    result.error_code_match,
                    result.notes,
                ),
            )
        self._conn.commit()

    # ──────────────────────────────────────────────────────────────────────
    # Query helpers (used by MCP tool layer)
    # ──────────────────────────────────────────────────────────────────────

    def get_rules_for_field(
        self,
        field_path: str,
        tax_year: int,
        severity: Optional[str] = None,
    ) -> list[dict]:
        """Return all current rules governing a specific field path."""
        query = """
            SELECT rule_id, rule_type, severity, error_code,
                   rule_text, rule_expression, expression_ast
            FROM irs_kb.v_current_rules
            WHERE field_path = %s AND tax_year = %s
        """
        params: list = [field_path, tax_year]
        if severity:
            query += " AND severity = %s"
            params.append(severity)
        query += " ORDER BY severity, rule_id"

        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def get_rules_for_form(self, form_family: str, tax_year: int) -> list[dict]:
        """Return all current rules for a form family."""
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT rule_id, field_path, rule_type, severity,
                       error_code, rule_text, rule_expression
                FROM irs_kb.v_current_rules
                WHERE form_family = %s AND tax_year = %s
                ORDER BY severity DESC, rule_id
                """,
                (form_family, tax_year),
            )
            return [dict(r) for r in cur.fetchall()]
