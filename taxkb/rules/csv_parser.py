"""
taxkb/ingestion/csv_parser.py

Parses an IRS MeF business rules CSV into a list of MeFRule objects.
Handles encoding quirks, multi-line values, and schema validation.
"""
from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
from typing import Iterator

from taxkb.models import MeFRule, ParseResult, RuleType, Severity

logger = logging.getLogger(__name__)

# Required columns — any CSV missing these is rejected immediately.
REQUIRED_COLUMNS = {
    "RULE_ID", "RULE_TYPE", "FORM_FAMILY", "FIELD_PATH",
    "RULE_TEXT", "RULE_EXPRESSION", "ERROR_CODE", "SEVERITY",
    "TAX_YEAR", "SCHEMA_VERSION",
}

# Column aliases — IRS has used slightly different header names across versions.
COLUMN_ALIASES: dict[str, str] = {
    "RULEID"          : "RULE_ID",
    "RULE ID"         : "RULE_ID",
    "RULETYPE"        : "RULE_TYPE",
    "FORMFAMILY"      : "FORM_FAMILY",
    "FORM_NAME"       : "FORM_FAMILY",
    "FIELDPATH"       : "FIELD_PATH",
    "XPATH"           : "FIELD_PATH",
    "RULETEXT"        : "RULE_TEXT",
    "DESCRIPTION"     : "RULE_TEXT",
    "RULEEXPRESSION"  : "RULE_EXPRESSION",
    "EXPRESSION"      : "RULE_EXPRESSION",
    "ERRORCODE"       : "ERROR_CODE",
    "ERR_CODE"        : "ERROR_CODE",
    "TAXYEAR"         : "TAX_YEAR",
    "TAX_YR"          : "TAX_YEAR",
    "SCHEMAVERSION"   : "SCHEMA_VERSION",
    "SCHEMA_VER"      : "SCHEMA_VERSION",
    "VERSION"         : "SCHEMA_VERSION",
}


def _normalize_header(raw: str) -> str:
    """Strip whitespace, uppercase, then apply alias map."""
    cleaned = raw.strip().upper().replace("-", "_").replace(" ", "_")
    return COLUMN_ALIASES.get(cleaned, cleaned)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


class CSVParser:
    """
    Parses an IRS MeF business rules CSV file.

    Usage:
        parser = CSVParser("data/sample/mef_1040_2024_v5_2.csv")
        rules, result = parser.parse()
    """

    def __init__(self, csv_path: str | Path):
        self.path = Path(csv_path)
        if not self.path.exists():
            raise FileNotFoundError(f"CSV not found: {self.path}")
        self.file_hash = _sha256(self.path)

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def parse(self) -> tuple[list[MeFRule], ParseResult]:
        """
        Parse the CSV file.

        Returns:
            (rules, result)  — rules is the list of MeFRule objects;
                               result carries the ParseResult summary.
        Raises:
            ValueError if required columns are missing.
        """
        rules: list[MeFRule] = []
        failed: list[dict]   = []
        null_field_rows       = 0
        seen_ids: dict[str, int] = {}   # unique_key → row_number

        with self.path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)

            # Normalise headers
            if reader.fieldnames is None:
                raise ValueError("CSV appears empty — no header row found.")
            reader.fieldnames = [_normalize_header(f) for f in reader.fieldnames]

            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise ValueError(
                    f"CSV is missing required columns: {sorted(missing)}\n"
                    f"Found columns: {reader.fieldnames}"
                )

            for row_num, raw_row in enumerate(reader, start=2):  # 1-indexed, row 1 = header
                row = {k: (v.strip() if v else "") for k, v in raw_row.items()}

                # ── Null-field check ──────────────────────────────────────
                null_fields = [
                    col for col in ("RULE_ID", "ERROR_CODE", "SEVERITY", "FIELD_PATH")
                    if not row.get(col)
                ]
                if null_fields:
                    null_field_rows += 1
                    failed.append({
                        "row": row_num,
                        "rule_id": row.get("RULE_ID", ""),
                        "error": f"Null required fields: {null_fields}",
                    })
                    logger.warning("Row %d: null required fields %s", row_num, null_fields)
                    continue

                # ── Build MeFRule ─────────────────────────────────────────
                try:
                    rule = MeFRule(
                        rule_id         = row["RULE_ID"],
                        rule_type       = RuleType(row["RULE_TYPE"]),
                        form_family     = row["FORM_FAMILY"],
                        field_path      = row["FIELD_PATH"],
                        rule_text       = row["RULE_TEXT"],
                        rule_expression = row["RULE_EXPRESSION"],
                        error_code      = row["ERROR_CODE"],
                        severity        = Severity(row["SEVERITY"]),
                        tax_year        = int(row["TAX_YEAR"]),
                        schema_version  = row["SCHEMA_VERSION"],
                    )
                except Exception as exc:
                    failed.append({
                        "row": row_num,
                        "rule_id": row.get("RULE_ID", ""),
                        "error": str(exc),
                    })
                    logger.warning("Row %d parse error: %s", row_num, exc)
                    continue

                # ── Duplicate check ───────────────────────────────────────
                key = rule.unique_key
                if key in seen_ids:
                    logger.warning(
                        "Duplicate rule_id '%s' at rows %d and %d",
                        rule.rule_id, seen_ids[key], row_num,
                    )
                seen_ids[key] = row_num

                rules.append(rule)

        # Duplicates: keys that appeared more than once
        id_counts: dict[str, int] = {}
        for r in rules:
            id_counts[r.unique_key] = id_counts.get(r.unique_key, 0) + 1
        duplicates = [k for k, cnt in id_counts.items() if cnt > 1]

        result = ParseResult(
            schema_version  = rules[0].schema_version if rules else "unknown",
            tax_year        = rules[0].tax_year        if rules else 0,
            total_rows      = len(rules) + len(failed),
            parse_success   = len(rules),
            parse_failed    = len(failed),
            null_field_rows = null_field_rows,
            duplicate_ids   = duplicates,
            failed_rules    = failed,
        )

        logger.info(
            "CSV parse complete: %d/%d rows succeeded, %d failed, %d duplicates",
            result.parse_success, result.total_rows,
            result.parse_failed, len(duplicates),
        )
        return rules, result

    def iter_rules(self) -> Iterator[MeFRule]:
        """Streaming iterator — lower memory for very large CSV files."""
        rules, _ = self.parse()
        yield from rules

    @property
    def content_hash(self) -> str:
        return self.file_hash
