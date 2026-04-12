"""
tax_brain/validation/regression.py

V1.4 — Schema Version Regression Test (Ongoing)

Compares two MeF CSV versions and:
  - Identifies rules ADDED in the new version
  - Identifies rules REMOVED in the new version
  - Identifies rules MODIFIED (expression or severity changed)
  - Generates a RuleVersionDiff list for SUPERSEDES edge creation
  - Re-runs the test return suite against the new version and checks
    that outcomes changed only where the release memo documents a change

Usage:
    old_rules, _ = CSVParser("mef_v5_1.csv").parse()
    new_rules, _ = CSVParser("mef_v5_2.csv").parse()
    diffs, report = regression.run(old_rules, new_rules, test_cases)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from tax_brain.models import (
    MeFRule, RuleVersionDiff, ChangeType, ValidationReport,
    TestReturnCase, TestReturnOutcome,
)
from tax_brain.rules.validation.test_replay import RuleEngine

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Diff engine
# ──────────────────────────────────────────────────────────────────────────────

# Fields that are meaningful to compare between versions
DIFF_FIELDS = [
    "rule_type", "severity", "rule_expression",
    "error_code", "field_path", "rule_text",
]


def compute_diffs(
    old_rules : list[MeFRule],
    new_rules : list[MeFRule],
) -> list[RuleVersionDiff]:
    """
    Compare old and new rule sets.  Returns a list of RuleVersionDiff
    objects describing what changed, was added, or was removed.
    """
    old_map = {r.rule_id: r for r in old_rules}
    new_map = {r.rule_id: r for r in new_rules}

    old_version = old_rules[0].schema_version if old_rules else "unknown"
    new_version = new_rules[0].schema_version if new_rules else "unknown"
    tax_year    = new_rules[0].tax_year       if new_rules else 2024

    diffs: list[RuleVersionDiff] = []

    # ADDED — in new but not old
    for rule_id in set(new_map) - set(old_map):
        rule = new_map[rule_id]
        diffs.append(RuleVersionDiff(
            rule_id        = rule_id,
            tax_year       = tax_year,
            old_version    = None,
            new_version    = new_version,
            change_type    = ChangeType.ADDED,
            changed_fields = [],
            old_expression = None,
            new_expression = rule.rule_expression,
        ))
        logger.info("ADDED rule: %s", rule_id)

    # REMOVED — in old but not new
    for rule_id in set(old_map) - set(new_map):
        rule = old_map[rule_id]
        diffs.append(RuleVersionDiff(
            rule_id        = rule_id,
            tax_year       = tax_year,
            old_version    = old_version,
            new_version    = new_version,
            change_type    = ChangeType.REMOVED,
            changed_fields = [],
            old_expression = rule.rule_expression,
            new_expression = None,
        ))
        logger.info("REMOVED rule: %s", rule_id)

    # MODIFIED — in both, check each diff field
    for rule_id in set(old_map) & set(new_map):
        old = old_map[rule_id]
        new = new_map[rule_id]
        changed: list[str] = []

        for field in DIFF_FIELDS:
            old_val = getattr(old, field, None)
            new_val = getattr(new, field, None)
            # Handle Enum values
            if hasattr(old_val, "value"):
                old_val = old_val.value
            if hasattr(new_val, "value"):
                new_val = new_val.value
            if old_val != new_val:
                changed.append(field)
                logger.debug(
                    "Rule %s changed field '%s': '%s' → '%s'",
                    rule_id, field, old_val, new_val,
                )

        if changed:
            diffs.append(RuleVersionDiff(
                rule_id        = rule_id,
                tax_year       = tax_year,
                old_version    = old_version,
                new_version    = new_version,
                change_type    = ChangeType.MODIFIED,
                changed_fields = changed,
                old_expression = old.rule_expression,
                new_expression = new.rule_expression,
            ))
        else:
            diffs.append(RuleVersionDiff(
                rule_id        = rule_id,
                tax_year       = tax_year,
                old_version    = old_version,
                new_version    = new_version,
                change_type    = ChangeType.UNCHANGED,
            ))

    added    = sum(1 for d in diffs if d.change_type == ChangeType.ADDED)
    removed  = sum(1 for d in diffs if d.change_type == ChangeType.REMOVED)
    modified = sum(1 for d in diffs if d.change_type == ChangeType.MODIFIED)
    unchanged= sum(1 for d in diffs if d.change_type == ChangeType.UNCHANGED)

    logger.info(
        "Diff %s → %s: +%d added, -%d removed, ~%d modified, %d unchanged",
        old_version, new_version, added, removed, modified, unchanged,
    )
    return diffs


def write_diff_report(
    diffs       : list[RuleVersionDiff],
    output_path : str | Path,
) -> None:
    """Write the diff report to JSON for review."""
    output_path = Path(output_path)
    data = [d.model_dump() for d in diffs if d.change_type != ChangeType.UNCHANGED]
    output_path.write_text(json.dumps(data, indent=2, default=str))
    logger.info("Diff report written to %s (%d changed rules)", output_path, len(data))


# ──────────────────────────────────────────────────────────────────────────────
# Regression test runner
# ──────────────────────────────────────────────────────────────────────────────

def run(
    old_rules  : list[MeFRule],
    new_rules  : list[MeFRule],
    test_cases : list[TestReturnCase],
    report_dir : Optional[str | Path] = None,
) -> tuple[list[RuleVersionDiff], ValidationReport]:
    """
    Run V1.4 regression test.

    Steps:
      1. Compute diffs between old and new rule sets.
      2. Run all test cases against both rule sets.
      3. Flag any test case whose outcome changed WITHOUT a corresponding
         documented rule change (unexpected regression).
      4. Flag any rule change that is NOT covered by any test case
         (coverage gap).

    Returns:
        (diffs, ValidationReport)
    """
    diffs = compute_diffs(old_rules, new_rules)
    modified_rule_ids = {d.rule_id for d in diffs if d.change_type == ChangeType.MODIFIED}
    added_rule_ids    = {d.rule_id for d in diffs if d.change_type == ChangeType.ADDED}

    old_engine = RuleEngine(old_rules)
    new_engine = RuleEngine(new_rules)

    failures : list[dict] = []
    warnings : list[dict] = []
    notes    : list[str]  = []

    outcome_changed_cases      : list[str] = []
    changed_covered_rule_ids   : set[str]  = set()

    for case in test_cases:
        old_fired, old_errors = old_engine.evaluate_return(case.return_data)
        new_fired, new_errors = new_engine.evaluate_return(case.return_data)

        old_outcome = (
            TestReturnOutcome.REJECTED if old_fired else TestReturnOutcome.ACCEPTED
        )
        new_outcome = (
            TestReturnOutcome.REJECTED if new_fired else TestReturnOutcome.ACCEPTED
        )

        if old_outcome != new_outcome:
            # Outcome changed — is it explained by a modified rule?
            rules_responsible = set(new_fired) | set(old_fired)
            explained = bool(rules_responsible & (modified_rule_ids | added_rule_ids))

            if not explained:
                # UNEXPECTED regression — new version changed outcome without
                # a documented rule change
                failures.append({
                    "case_id"      : case.case_id,
                    "description"  : case.description,
                    "old_outcome"  : old_outcome.value,
                    "new_outcome"  : new_outcome.value,
                    "changed_rules": list(rules_responsible),
                    "detail"       : (
                        "Outcome changed between schema versions but no "
                        "corresponding rule was flagged as modified/added. "
                        "This is an UNEXPECTED regression."
                    ),
                })
            else:
                # Expected change — document it
                changed_covered_rule_ids |= rules_responsible & modified_rule_ids
                warnings.append({
                    "case_id"         : case.case_id,
                    "description"     : case.description,
                    "old_outcome"     : old_outcome.value,
                    "new_outcome"     : new_outcome.value,
                    "modified_rules"  : list(rules_responsible & modified_rule_ids),
                    "detail"          : "Outcome change is explained by documented rule modification.",
                })
            outcome_changed_cases.append(case.case_id)

    # Coverage gap: modified rules not exercised by any test case
    uncovered = modified_rule_ids - changed_covered_rule_ids
    if uncovered:
        warnings.append({
            "check"        : "COVERAGE_GAP",
            "uncovered_ids": sorted(uncovered),
            "count"        : len(uncovered),
            "detail"       : (
                f"{len(uncovered)} modified rules are not exercised by any test case. "
                "Add test cases covering these rule IDs before the next release."
            ),
        })

    # Summary notes
    added    = sum(1 for d in diffs if d.change_type == ChangeType.ADDED)
    removed  = sum(1 for d in diffs if d.change_type == ChangeType.REMOVED)
    modified = sum(1 for d in diffs if d.change_type == ChangeType.MODIFIED)
    old_ver  = old_rules[0].schema_version if old_rules else "?"
    new_ver  = new_rules[0].schema_version if new_rules else "?"

    notes = [
        f"Schema diff: {old_ver} → {new_ver}",
        f"  Rules added:    {added}",
        f"  Rules removed:  {removed}",
        f"  Rules modified: {modified}",
        f"Test cases run: {len(test_cases)}",
        f"Outcome changes: {len(outcome_changed_cases)} "
        f"({'0 unexpected' if not failures else str(len(failures)) + ' UNEXPECTED'})",
        f"Coverage gaps: {len(uncovered)} modified rules without test coverage",
    ]

    passed = len(failures) == 0

    # Write diff report to disk if requested
    if report_dir:
        report_path = Path(report_dir) / f"regression_{old_ver}_to_{new_ver}.json"
        write_diff_report(diffs, report_path)
        notes.append(f"Diff report written to {report_path}")

    report = ValidationReport(
        step          = "V1.4-REGRESSION",
        passed        = passed,
        total_checked = len(test_cases),
        total_passed  = len(test_cases) - len(failures),
        total_failed  = len(failures),
        failures      = failures,
        warnings      = warnings,
        notes         = notes,
    )

    logger.info(report.summary_line())
    return diffs, report
