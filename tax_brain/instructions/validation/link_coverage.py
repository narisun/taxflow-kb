"""
tax_brain/instructions/validation/link_coverage.py

V2.2 — FormLine Link Coverage Gate.

Measures what percentage of the FormLine field names used in Layer 1 rules
are "explained" by at least one Layer 2 instruction section.

Gate: ≥ COVERAGE_THRESHOLD of Layer 1 fields must have an instruction section.

This gate operates purely in-memory against the parsed Layer2ParseResult and
the list of Layer 1 rule field paths — no database connection needed.
"""
from __future__ import annotations

import logging

from tax_brain.instructions.html_parser import LINE_TO_FIELDS
from tax_brain.instructions.models import Layer2ParseResult
from tax_brain.models import ValidationReport

logger = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 0.70   # 70% of known Layer 1 fields must be covered


def _all_layer1_fields() -> set[str]:
    """
    Return the complete set of short field names referenced across all
    line-to-field mappings.  This represents every FormLine that Layer 1
    rules reference and that Layer 2 should explain.
    """
    fields: set[str] = set()
    for field_list in LINE_TO_FIELDS.values():
        fields.update(field_list)
    return fields


def run(result: Layer2ParseResult) -> ValidationReport:
    """
    Run V2.2: verify that instruction sections cover Layer 1 FormLine fields.

    Args:
        result : The parsed Layer2ParseResult (no DB needed).

    Returns:
        ValidationReport — check .passed for gate decision.
    """
    failures : list[dict] = []
    warnings : list[dict] = []
    notes    : list[str]  = []

    # All field names that Layer 1 rules reference (from LINE_TO_FIELDS)
    l1_fields = _all_layer1_fields()

    # All field names covered by at least one instruction section
    covered: set[str] = set()
    for sec in result.sections:
        covered.update(sec.field_names)

    # Intersection: which L1 fields does Layer 2 explain?
    covered_l1 = l1_fields & covered
    missing     = l1_fields - covered

    total     = len(l1_fields)
    n_covered = len(covered_l1)
    rate      = n_covered / total if total else 1.0
    passed    = rate >= COVERAGE_THRESHOLD

    if not passed:
        failures.append({
            "check"  : "FORMLINE_COVERAGE",
            "rate"   : round(rate, 4),
            "threshold": COVERAGE_THRESHOLD,
            "missing_fields": sorted(missing),
            "detail" : (
                f"Only {n_covered}/{total} Layer 1 fields have instruction "
                f"sections ({rate*100:.1f}% < {COVERAGE_THRESHOLD*100:.0f}% threshold)."
            ),
        })
    else:
        notes.append(
            f"FORMLINE_COVERAGE: {n_covered}/{total} fields covered "
            f"({rate*100:.1f}%) [threshold: {COVERAGE_THRESHOLD*100:.0f}%] ✓ PASS"
        )

    if missing:
        warnings.append({
            "check"  : "UNCOVERED_FIELDS",
            "detail" : f"{len(missing)} fields lack an instruction section.",
            "fields" : sorted(missing),
        })

    notes += [
        f"Total Layer 1 fields:    {total}",
        f"Covered by Layer 2:      {n_covered}",
        f"Not yet covered:         {len(missing)}",
        f"Extra fields in Layer 2: {len(covered - l1_fields)} "
        "(fields in HTML but not in Layer 1 rules)",
    ]

    report = ValidationReport(
        step          = "V2.2-LINK-COVERAGE",
        passed        = passed,
        total_checked = total,
        total_passed  = n_covered,
        total_failed  = len(missing),
        failures      = failures,
        warnings      = warnings,
        notes         = notes,
    )

    if passed:
        logger.info("V2.2 PASSED — %d/%d fields covered (%.1f%%)",
                    n_covered, total, rate * 100)
    else:
        logger.error("V2.2 FAILED — coverage %.1f%% below %.0f%% threshold. "
                     "Missing: %s", rate * 100, COVERAGE_THRESHOLD * 100,
                     sorted(missing)[:10])
    return report
