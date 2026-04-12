"""
tax_brain/validation/spot_check.py

V1.2 — Domain Expert Spot-Check (Days 3–5)

Generates a stratified sample of 50 rules for tax domain expert review.
The expert verifies each rule's parsed expression matches the IRS instruction PDF.

Workflow:
  1. Call generate_sample() → produces a CSV/JSON file for expert review
  2. Expert annotates each row: correct=True/False, notes="..."
  3. Call score_review(annotated_path) → produces ValidationReport

Categories for stratified sampling:
  - income_limits       : IRADeduction, StudentLoanInterest, etc.
  - contribution_caps   : 401k, HSA limits
  - required_attachments: Form 8960, 6251, ScheduleA, etc.
  - math_validation     : Sums, totals, arithmetic checks
  - cross_form_refs     : Rules referencing multiple forms
"""
from __future__ import annotations

import csv
import json
import logging
import random
from pathlib import Path
from typing import Optional

from tax_brain.models import MeFRule, ValidationReport

logger = logging.getLogger(__name__)

# ── Sampling configuration ────────────────────────────────────────────────────

SAMPLE_SIZE_PER_CATEGORY = 10
PASS_THRESHOLD            = 0.95  # >= 95% of sampled rules must be correct

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "income_limits": [
        "phase-out", "phaseout", "limit", "threshold", "deduction limit",
        "IRADeduction", "StudentLoan", "ChildTaxCredit", "AOTC",
    ],
    "contribution_caps": [
        "401k", "HSA", "IRA contribution", "contribution limit",
        "cannot exceed", "annual limit",
    ],
    "required_attachments": [
        "must be attached", "required when", "must be present",
        "requires Schedule", "requires Form",
    ],
    "math_validation": [
        "must equal", "= [", "sum of", "SUM(", "total must",
        "must reconcile",
    ],
    "cross_form_refs": [
        "Form 8960", "Schedule D", "Schedule A", "Schedule E",
        "1099", "W-2", "SUM([IRS",
    ],
}


def _classify_rule(rule: MeFRule) -> str:
    """Assign one category label to a rule based on keyword matching."""
    combined = (rule.rule_text + " " + rule.rule_expression).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in combined for kw in keywords):
            return category
    return "other"


def generate_sample(
    rules          : list[MeFRule],
    output_path    : str | Path,
    sample_per_cat : int = SAMPLE_SIZE_PER_CATEGORY,
    seed           : int = 42,
) -> dict[str, int]:
    """
    Generate a stratified sample for expert review.
    Writes two files:
      {output_path}.csv  — for spreadsheet review
      {output_path}.json — machine-readable annotated input

    Returns: category → count mapping of sampled rules.
    """
    random.seed(seed)
    output_path = Path(output_path)

    # Bucket rules by category
    buckets: dict[str, list[MeFRule]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    buckets["other"] = []
    for rule in rules:
        cat = _classify_rule(rule)
        buckets.setdefault(cat, []).append(rule)

    # Sample from each category
    sampled: list[tuple[str, MeFRule]] = []
    category_counts: dict[str, int] = {}
    for cat, bucket in buckets.items():
        n = min(sample_per_cat, len(bucket))
        chosen = random.sample(bucket, n)
        for rule in chosen:
            sampled.append((cat, rule))
        category_counts[cat] = n
        logger.info("Category '%s': %d rules sampled from %d available", cat, n, len(bucket))

    # Write CSV for expert annotation
    csv_path = output_path.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "sample_id", "category", "rule_id", "form_family", "severity",
            "field_path", "rule_text", "rule_expression",
            "expert_correct",   # Expert fills: TRUE / FALSE
            "expert_notes",     # Expert fills: explanation if incorrect
        ])
        writer.writeheader()
        for idx, (cat, rule) in enumerate(sampled, start=1):
            writer.writerow({
                "sample_id"       : idx,
                "category"        : cat,
                "rule_id"         : rule.rule_id,
                "form_family"     : rule.form_family,
                "severity"        : rule.severity.value,
                "field_path"      : rule.field_path,
                "rule_text"       : rule.rule_text,
                "rule_expression" : rule.rule_expression,
                "expert_correct"  : "",
                "expert_notes"    : "",
            })

    # Write JSON for programmatic scoring
    json_path = output_path.with_suffix(".json")
    json_data = [
        {
            "sample_id"      : idx,
            "category"       : cat,
            "rule_id"        : rule.rule_id,
            "rule_expression": rule.rule_expression,
            "expert_correct" : None,
            "expert_notes"   : "",
        }
        for idx, (cat, rule) in enumerate(sampled, start=1)
    ]
    json_path.write_text(json.dumps(json_data, indent=2))

    logger.info(
        "Spot-check sample written: %d rules to %s and %s",
        len(sampled), csv_path.name, json_path.name,
    )
    return category_counts


def score_review(
    annotated_path : str | Path,
    threshold      : float = PASS_THRESHOLD,
) -> ValidationReport:
    """
    Score the expert-annotated review file.

    Args:
        annotated_path : Path to the annotated .json or .csv file
        threshold      : Minimum fraction that must be marked correct to pass

    Returns:
        ValidationReport with pass/fail and per-category breakdown
    """
    annotated_path = Path(annotated_path)
    if annotated_path.suffix == ".json":
        records = json.loads(annotated_path.read_text())
    elif annotated_path.suffix == ".csv":
        with annotated_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            records = list(reader)
    else:
        raise ValueError(f"Unsupported format: {annotated_path.suffix}")

    total_reviewed  = 0
    total_correct   = 0
    failures: list[dict] = []
    by_category: dict[str, dict] = {}

    for rec in records:
        expert_val = rec.get("expert_correct", "")
        if expert_val == "" or expert_val is None:
            continue  # Skip un-annotated rows (expert not done yet)

        total_reviewed += 1
        cat = rec.get("category", "unknown")
        by_category.setdefault(cat, {"correct": 0, "total": 0})
        by_category[cat]["total"] += 1

        is_correct = str(expert_val).strip().upper() in ("TRUE", "1", "YES", "Y", "CORRECT")
        if is_correct:
            total_correct += 1
            by_category[cat]["correct"] += 1
        else:
            failures.append({
                "sample_id"      : rec.get("sample_id"),
                "rule_id"        : rec.get("rule_id"),
                "category"       : cat,
                "rule_expression": rec.get("rule_expression", "")[:120],
                "expert_notes"   : rec.get("expert_notes", ""),
            })

    if total_reviewed == 0:
        return ValidationReport(
            step="V1.2-SPOT-CHECK",
            passed=False,
            total_checked=0,
            total_passed=0,
            total_failed=0,
            failures=[{"detail": "No annotated rows found. Expert has not completed the review."}],
            notes=["Run generate_sample() and have the tax domain expert annotate the output file."],
        )

    pass_rate = total_correct / total_reviewed
    passed    = pass_rate >= threshold

    # Per-category breakdown as notes
    cat_notes = [
        f"  {cat}: {v['correct']}/{v['total']} correct ({v['correct']/v['total']*100:.0f}%)"
        for cat, v in sorted(by_category.items())
    ]

    # Detect systematic failures (entire category wrong)
    systematic: list[str] = []
    for cat, v in by_category.items():
        if v["total"] >= 3 and v["correct"] / v["total"] < 0.5:
            systematic.append(
                f"SYSTEMATIC ERROR in '{cat}': only {v['correct']}/{v['total']} correct. "
                "Likely an AST parser logic bug — fix and re-run full extraction."
            )

    report = ValidationReport(
        step          = "V1.2-SPOT-CHECK",
        passed        = passed,
        total_checked = total_reviewed,
        total_passed  = total_correct,
        total_failed  = total_reviewed - total_correct,
        failures      = failures,
        warnings      = [{"systematic": s} for s in systematic],
        notes         = [
            f"Overall: {total_correct}/{total_reviewed} correct ({pass_rate*100:.1f}%)",
            f"Threshold: {threshold*100:.0f}%",
            "By category:",
            *cat_notes,
        ],
    )

    logger.info(report.summary_line())
    if systematic:
        logger.error("SYSTEMATIC FAILURES detected: %s", "; ".join(systematic))
    return report
