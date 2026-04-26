"""
taxkb/evaluation/validation/gold_set.py

V5.1 Gold Set Quality Gate

Validates that a generated gold set meets minimum quality standards before
it is used in downstream retrieval and generation evaluations.

Gate criteria
─────────────
V5.1-A  Minimum size    : at least MIN_ENTRIES total entries
V5.1-B  Publication coverage : all expected pubs appear at least once
V5.1-C  Difficulty spread    : all three difficulty tiers present
V5.1-D  Question length      : median question length ≥ 30 chars
V5.1-E  Answer length        : median answer length ≥ 50 chars
V5.1-F  No duplicates        : no two entries share the same question (after strip/lower)

All 6 checks must pass for the gate to succeed.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────

MIN_ENTRIES      = 40     # lower bound across all pubs combined
MIN_PER_PUB      = 3     # each expected pub must have at least this many entries
EXPECTED_PUBS    = {"17", "501", "525", "550", "590a", "590b", "596", "969"}
REQUIRED_DIFFS   = {"simple", "medium", "complex"}
MIN_MEDIAN_Q_LEN = 30
MIN_MEDIAN_A_LEN = 50


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class V51Check:
    code   : str
    name   : str
    passed : bool
    detail : str

@dataclass
class V51Result:
    checks : list[V51Check]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def print_report(self) -> None:
        lines = [
            "",
            "══════════════════════════════════════════════════════════════",
            "  V5.1 — Gold Set Quality Gate",
            "══════════════════════════════════════════════════════════════",
        ]
        for c in self.checks:
            icon = "✓ PASS" if c.passed else "✗ FAIL"
            lines.append(f"  {icon}  {c.code}  {c.name}")
            lines.append(f"         {c.detail}")
        overall = "PASS" if self.passed else "FAIL"
        lines.append("")
        lines.append(f"  Overall: {overall}  ({sum(c.passed for c in self.checks)}/{len(self.checks)} checks pass)")
        lines.append("══════════════════════════════════════════════════════════════")
        print("\n".join(lines))


# ── Gate implementation ────────────────────────────────────────────────────────

def validate_gold_set(gold_set) -> V51Result:
    """
    Run all V5.1 checks against a GoldSet instance.

    Args:
        gold_set: GoldSet with .entries list of GoldSetEntry.

    Returns:
        V51Result with per-check pass/fail details.
    """
    entries = gold_set.entries
    n = len(entries)
    checks: list[V51Check] = []

    # V5.1-A: Minimum entry count
    checks.append(V51Check(
        code   = "V5.1-A",
        name   = "Minimum size",
        passed = n >= MIN_ENTRIES,
        detail = f"{n} entries (min {MIN_ENTRIES})",
    ))

    # V5.1-B: Publication coverage
    pub_counts = gold_set.by_pub
    missing = [p for p in EXPECTED_PUBS if pub_counts.get(p, 0) < MIN_PER_PUB]
    checks.append(V51Check(
        code   = "V5.1-B",
        name   = "Publication coverage",
        passed = len(missing) == 0,
        detail = (
            f"All {len(EXPECTED_PUBS)} pubs present (≥{MIN_PER_PUB} each)"
            if not missing else
            f"Missing/thin pubs: {sorted(missing)}"
        ),
    ))

    # V5.1-C: Difficulty spread
    diff_counts = gold_set.by_difficulty
    missing_diff = [d for d in REQUIRED_DIFFS if diff_counts.get(d, 0) == 0]
    checks.append(V51Check(
        code   = "V5.1-C",
        name   = "Difficulty spread",
        passed = len(missing_diff) == 0,
        detail = (
            f"All difficulties present: {dict(diff_counts)}"
            if not missing_diff else
            f"Missing difficulty tiers: {missing_diff}"
        ),
    ))

    # V5.1-D: Question length
    q_lens = [len(e.question) for e in entries] if entries else [0]
    median_q = statistics.median(q_lens)
    checks.append(V51Check(
        code   = "V5.1-D",
        name   = "Question length",
        passed = median_q >= MIN_MEDIAN_Q_LEN,
        detail = f"Median question length = {median_q:.0f} chars (min {MIN_MEDIAN_Q_LEN})",
    ))

    # V5.1-E: Answer length
    a_lens = [len(e.ground_truth) for e in entries] if entries else [0]
    median_a = statistics.median(a_lens)
    checks.append(V51Check(
        code   = "V5.1-E",
        name   = "Answer length",
        passed = median_a >= MIN_MEDIAN_A_LEN,
        detail = f"Median answer length = {median_a:.0f} chars (min {MIN_MEDIAN_A_LEN})",
    ))

    # V5.1-F: No duplicate questions
    normalized = [e.question.strip().lower() for e in entries]
    n_unique = len(set(normalized))
    duplicates = n - n_unique
    checks.append(V51Check(
        code   = "V5.1-F",
        name   = "No duplicate questions",
        passed = duplicates == 0,
        detail = (
            f"{n_unique} unique questions, no duplicates"
            if duplicates == 0 else
            f"{duplicates} duplicate question(s) found"
        ),
    ))

    result = V51Result(checks=checks)

    if result.passed:
        logger.info("V5.1 PASS — gold set meets all quality criteria (%d entries)", n)
    else:
        failed = [c.code for c in checks if not c.passed]
        logger.warning("V5.1 FAIL — failed checks: %s", failed)

    return result
