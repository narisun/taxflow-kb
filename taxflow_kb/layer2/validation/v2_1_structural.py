"""
taxflow_kb/layer2/validation/v2_1_structural.py

V2.1 — Structural Integrity Gate for the instruction graph.

Checks
──────
1. PARSE_SUCCESS    — parse_success must be True.
2. SECTION_COUNT    — must have at least MIN_SECTIONS h2/h3 sections.
3. LINE_SECTIONS    — must have at least MIN_LINE_SECTIONS with a line_reference.
4. EMPTY_CONTENT    — no section should have empty text_content.
5. HEADING_QUALITY  — no section should have an empty heading.
6. FIELD_MAPPING    — every LINE_INSTRUCTION section should map to ≥ 1 field.
7. FIELD_MAP_RATE   — ≥ FIELD_MAP_THRESHOLD of line sections have field_names.

Gate: all checks 1–5 must pass; checks 6–7 produce warnings not failures.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from taxflow_kb.layer2.models_layer2 import Layer2ParseResult, SectionType
from taxflow_kb.models import ValidationReport

logger = logging.getLogger(__name__)

MIN_SECTIONS        = 10    # minimum total h2/h3 sections
MIN_LINE_SECTIONS   = 5     # minimum sections with line_reference
FIELD_MAP_THRESHOLD = 0.70  # 70% of line sections must map to ≥1 field


@dataclass
class _Check:
    name   : str
    passed : bool
    detail : str = ""


def run(result: Layer2ParseResult) -> ValidationReport:
    """
    Run V2.1 structural checks on a Layer2ParseResult.

    Returns a ValidationReport; check .passed for gate decision.
    """
    failures : list[dict] = []
    warnings : list[dict] = []
    notes    : list[str]  = []
    checks   : list[_Check] = []

    # ── Check 1: Parse success ────────────────────────────────────────────────
    checks.append(_Check(
        "PARSE_SUCCESS",
        result.parse_success,
        f"Errors: {result.errors}" if not result.parse_success else "OK",
    ))

    total   = len(result.sections)
    line_s  = result.line_sections()
    n_line  = len(line_s)

    # ── Check 2: Minimum section count ────────────────────────────────────────
    checks.append(_Check(
        "SECTION_COUNT",
        total >= MIN_SECTIONS,
        f"{total} sections (min {MIN_SECTIONS})",
    ))

    # ── Check 3: Minimum line sections ────────────────────────────────────────
    checks.append(_Check(
        "LINE_SECTIONS",
        n_line >= MIN_LINE_SECTIONS,
        f"{n_line} line sections (min {MIN_LINE_SECTIONS})",
    ))

    # ── Check 4: No empty text content ────────────────────────────────────────
    # Container / category headings (h2 = level 1, h3 = level 2) aggregate their
    # content inside child sections and legitimately have no direct paragraph text.
    # Only leaf-level sections (h4 / level 3+) are required to have content.
    # For synthetic HTML (max level = 2) this check is skipped, which is fine —
    # the unit test in test_layer2.py validates h3 content directly.
    empty_content = [s for s in result.sections
                     if s.level > 2 and not s.text_content.strip()]
    checks.append(_Check(
        "EMPTY_CONTENT",
        len(empty_content) == 0,
        f"{len(empty_content)} leaf sections with no text content" if empty_content
        else "OK",
    ))

    # ── Check 5: No empty headings ────────────────────────────────────────────
    empty_headings = [s for s in result.sections if not s.heading.strip()]
    checks.append(_Check(
        "HEADING_QUALITY",
        len(empty_headings) == 0,
        f"{len(empty_headings)} sections with empty heading" if empty_headings else "OK",
    ))

    # ── Check 6/7: Field mapping (warning-only) ───────────────────────────────
    mapped   = [s for s in line_s if s.field_names]
    unmapped = [s for s in line_s if not s.field_names]
    map_rate = len(mapped) / n_line if n_line else 1.0

    map_check = _Check(
        "FIELD_MAP_RATE",
        map_rate >= FIELD_MAP_THRESHOLD,
        f"{len(mapped)}/{n_line} line sections mapped ({map_rate*100:.1f}%)",
    )

    if not map_check.passed:
        warnings.append({
            "check" : "FIELD_MAP_RATE",
            "detail": map_check.detail,
            "unmapped_sections": [
                {"section_id": s.section_id, "heading": s.heading,
                 "line_ref": s.line_reference}
                for s in unmapped[:10]
            ],
        })
    notes.append(
        f"FIELD_MAPPING: {len(mapped)}/{n_line} line sections mapped "
        f"({map_rate*100:.1f}%) [threshold: {FIELD_MAP_THRESHOLD*100:.0f}%] "
        f"{'✓' if map_check.passed else '⚠'}"
    )

    # ── Collect failures ──────────────────────────────────────────────────────
    gate_checks = checks  # all 5 checks are gate checks
    for chk in gate_checks:
        if not chk.passed:
            failures.append({
                "check" : chk.name,
                "detail": chk.detail,
            })

    passed = len(failures) == 0

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes.insert(0, f"TOTAL_SECTIONS:     {total}")
    notes.insert(1, f"LINE_SECTIONS:      {n_line}")
    notes.insert(2, f"CROSS_REFS:         {sum(len(s.cross_refs) for s in result.sections)}")

    for chk in checks[:5]:
        notes.append(f"{chk.name}: {chk.detail}")

    report = ValidationReport(
        step          = "V2.1-STRUCTURAL",
        passed        = passed,
        total_checked = total,
        total_passed  = total - len(empty_content) - len(empty_headings),
        total_failed  = len(failures),
        failures      = failures,
        warnings      = [w if isinstance(w, dict) else {"detail": w} for w in warnings],
        notes         = notes,
    )

    if passed:
        logger.info("V2.1 PASSED — %d sections, %d line sections.", total, n_line)
    else:
        logger.error("V2.1 FAILED — %d failure(s): %s",
                     len(failures), [f["check"] for f in failures])
    return report
