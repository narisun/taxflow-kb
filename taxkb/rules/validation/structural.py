"""
taxkb/rules/validation/structural.py

V1.1 — Structural Integrity Check (Days 1–2)

Validates that the CSV parsed cleanly:
  ✓ Row count matches IRS expected count (from release memo)
  ✓ No null required fields
  ✓ All rule expressions parse to a valid AST
  ✓ No duplicate rule_ids within a tax year + schema version
  ✓ All rule_type and severity values are in the allowed set

Pass thresholds (configurable):
  - AST parse success : >= 98%  (FAIL below)
  - Null field rows   : 0       (FAIL if any)
  - Duplicate IDs     : 0       (FAIL if any)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from taxkb.models import MeFRule, ParseResult, ValidationReport
from taxkb.rules.ast_parser import parse_expression
from taxkb.models import ASTNodeType

logger = logging.getLogger(__name__)

# ── Configurable thresholds ───────────────────────────────────────────────────
AST_PARSE_THRESHOLD = 0.98   # Minimum fraction of rules that must parse cleanly
MAX_NULL_ROWS       = 0      # Maximum tolerated null-field rows
MAX_DUPLICATES      = 0      # Maximum tolerated duplicate rule_ids


@dataclass
class StructuralCheckConfig:
    """Override defaults per environment."""
    expected_row_count : int | None = None   # From IRS release memo; None = skip check
    ast_threshold      : float = AST_PARSE_THRESHOLD
    max_null_rows      : int   = MAX_NULL_ROWS
    max_duplicates     : int   = MAX_DUPLICATES


def run(
    rules        : list[MeFRule],
    parse_result : ParseResult,
    config       : StructuralCheckConfig | None = None,
) -> ValidationReport:
    """
    Run V1.1 structural integrity check.

    Args:
        rules        : Parsed MeFRule list from CSVParser.parse()
        parse_result : ParseResult summary from the same parse run
        config       : Optional threshold overrides

    Returns:
        ValidationReport  — check .passed and .failures for gate decision
    """
    cfg      = config or StructuralCheckConfig()
    failures : list[dict] = []
    warnings : list[dict] = []
    notes    : list[str]  = []

    # ── Check 1: Row count vs. expected ───────────────────────────────────
    if cfg.expected_row_count is not None:
        if parse_result.total_rows != cfg.expected_row_count:
            failures.append({
                "check"   : "ROW_COUNT",
                "expected": cfg.expected_row_count,
                "actual"  : parse_result.total_rows,
                "detail"  : (
                    f"Expected {cfg.expected_row_count} rows per IRS release memo, "
                    f"parsed {parse_result.total_rows}. "
                    f"Diff = {parse_result.total_rows - cfg.expected_row_count:+d}"
                ),
            })
            logger.error("V1.1 ROW_COUNT FAIL: expected=%d actual=%d",
                         cfg.expected_row_count, parse_result.total_rows)
        else:
            notes.append(f"ROW_COUNT OK: {parse_result.total_rows} rows match release memo.")

    # ── Check 2: Null required fields ─────────────────────────────────────
    if parse_result.null_field_rows > cfg.max_null_rows:
        failures.append({
            "check"  : "NULL_FIELDS",
            "count"  : parse_result.null_field_rows,
            "detail" : f"{parse_result.null_field_rows} rows had null required fields.",
            "rows"   : [f["row"] for f in parse_result.failed_rules[:20]],
        })
    else:
        notes.append("NULL_FIELDS OK: zero null required fields.")

    # ── Check 3: Duplicate rule_ids ────────────────────────────────────────
    if len(parse_result.duplicate_ids) > cfg.max_duplicates:
        failures.append({
            "check"    : "DUPLICATE_RULE_IDS",
            "count"    : len(parse_result.duplicate_ids),
            "rule_ids" : parse_result.duplicate_ids[:20],
            "detail"   : (
                f"{len(parse_result.duplicate_ids)} duplicate rule_ids found. "
                "Check CSV merge logic."
            ),
        })
    else:
        notes.append("DUPLICATE_IDS OK: zero duplicates.")

    # ── Check 4: AST parse success rate ───────────────────────────────────
    ast_failures: list[dict] = []
    total_parsed = 0

    for rule in rules:
        if rule.parse_success is False or rule.expression_ast is None:
            # Not yet parsed — run the AST parser now and update the rule
            try:
                ast_node = parse_expression(rule.rule_expression)
                if ast_node.node_type == ASTNodeType.PARSE_ERROR:
                    ast_failures.append({
                        "rule_id"   : rule.rule_id,
                        "expression": rule.rule_expression[:120],
                        "reason"    : ast_node.value,
                    })
                    rule.parse_success   = False
                    rule.parse_error_msg = str(ast_node.value)
                else:
                    rule.expression_ast = ast_node.to_dict()
                    rule.parse_success  = True
            except Exception as exc:
                ast_failures.append({
                    "rule_id"   : rule.rule_id,
                    "expression": rule.rule_expression[:120],
                    "reason"    : str(exc),
                })
                rule.parse_success   = False
                rule.parse_error_msg = str(exc)

        total_parsed += 1

    parse_success_count = sum(1 for r in rules if r.parse_success)
    ast_rate = parse_success_count / total_parsed if total_parsed else 0.0

    if ast_rate < cfg.ast_threshold:
        failures.append({
            "check"        : "AST_PARSE_RATE",
            "rate"         : round(ast_rate, 4),
            "threshold"    : cfg.ast_threshold,
            "failed_count" : len(ast_failures),
            "sample_errors": ast_failures[:10],
            "detail"       : (
                f"AST parse success rate {ast_rate*100:.1f}% is below "
                f"threshold {cfg.ast_threshold*100:.0f}%. "
                f"{len(ast_failures)} expressions failed to parse."
            ),
        })
    else:
        notes.append(
            f"AST_PARSE OK: {parse_success_count}/{total_parsed} "
            f"({ast_rate*100:.1f}%) parsed successfully."
        )
        if ast_failures:
            warnings.append({
                "check"   : "AST_PARSE_PARTIAL",
                "count"   : len(ast_failures),
                "detail"  : "Some rules failed AST parse but rate is above threshold.",
                "failures": ast_failures[:5],
            })

    # ── Check 5: Enum value validity ──────────────────────────────────────
    invalid_enums: list[dict] = []
    valid_rule_types  = {"MATH", "REJECT", "ALERT", "DATABASE"}
    valid_severities  = {"ERROR", "WARNING", "INFO"}

    for rule in rules:
        bad = []
        if rule.rule_type.value not in valid_rule_types:
            bad.append(f"rule_type='{rule.rule_type.value}'")
        if rule.severity.value not in valid_severities:
            bad.append(f"severity='{rule.severity.value}'")
        if bad:
            invalid_enums.append({"rule_id": rule.rule_id, "issues": bad})

    if invalid_enums:
        failures.append({
            "check"  : "INVALID_ENUM_VALUES",
            "count"  : len(invalid_enums),
            "detail" : "Rules with unrecognised rule_type or severity values.",
            "rows"   : invalid_enums[:10],
        })
    else:
        notes.append("ENUM_VALUES OK: all rule_type and severity values are valid.")

    # ── Build report ──────────────────────────────────────────────────────
    total_checks = 5  # one per check above
    passed_checks = total_checks - len({f["check"] for f in failures})

    report = ValidationReport(
        step          = "V1.1-STRUCTURAL",
        passed        = len(failures) == 0,
        total_checked = total_parsed,
        total_passed  = parse_success_count,
        total_failed  = total_parsed - parse_success_count,
        failures      = failures,
        warnings      = warnings,
        notes         = notes,
    )

    logger.info(report.summary_line())
    if not report.passed:
        logger.error(
            "V1.1 FAILED with %d failure(s). Must resolve before proceeding to Layer 2.",
            len(failures),
        )
    return report
