#!/usr/bin/env python3
"""
End-to-end test script for Tax Brain.

Runs targeted queries against the live Postgres database and validates
that hierarchical retrieval, scoped scenario retrieval, cross-year
comparison, and ontology routing all work as expected.

Test cases are calibrated against the actual ingested data:
  - 25 pubs, 5161 chunks (all embedded)
  - Summary chunks on: 334, 502-505, 523, 527, 535, 544, 551, 946
  - Years: 2022 (Pub 535), 2024 (Pubs 334, 925), 2025 (most pubs)

Usage:
    python taxkb/scripts/e2e_test_taxkb.py              # full synthesis
    python taxkb/scripts/e2e_test_taxkb.py --no-synth   # retrieval only (no OpenAI calls)
    python taxkb/scripts/e2e_test_taxkb.py -v            # verbose (print context details)
    python taxkb/scripts/e2e_test_taxkb.py -t "rental"   # run single test by name
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

# ── Setup path ───────────────────────────────────────────────────────────────
sys.path.insert(0, ".")

from taxkb.factories import create_agent
from taxkb.agent.agent import TaxBrainAgent
from taxkb.agent.models import QueryResult


@dataclass
class TestCase:
    """A single end-to-end test case."""
    name: str
    question: str
    # What we're testing — the assertion mode
    # "hierarchical" | "flat" | "flat_fallback" | "scoped_multi_pub" | "cross_year_comparison"
    # Use a list to accept any of several valid modes
    accept_modes: list[str]
    # At least one of these pubs should appear in contexts (flexible matching)
    accept_pubs: list[str]
    min_contexts: int = 1           # minimum contexts (relaxed default)
    tax_year: int | None = None     # explicit tax_year override
    pub_filter: list[str] | None = None
    # If True, we expect 0 contexts (e.g. querying a year with no data)
    expect_empty: bool = False


# ══════════════════════════════════════════════════════════════════════════════
# Test Cases — calibrated against actual DB contents
# ══════════════════════════════════════════════════════════════════════════════

# Pubs WITH summary chunks (hierarchical navigation possible):
#   334, 502, 503, 504, 505, 523, 527, 535, 544, 551, 946
#
# Pubs WITHOUT summaries (will fall back to flat):
#   17, 463, 501, 525, 526, 550, 560, 587, 590a, 590b, 596, 925, 936, 969

TESTS: list[TestCase] = [

    # ─── GROUP 1: HIERARCHICAL RETRIEVAL ─────────────────────────────────────
    # These target pubs that HAVE summary chunks, so hierarchical should engage.

    TestCase(
        name="1a. Depreciation rules (hierarchical - Pub 946 has summaries)",
        question="What are the MACRS depreciation rules and recovery periods for business property?",
        accept_modes=["hierarchical"],
        accept_pubs=["946"],
        min_contexts=3,
    ),
    TestCase(
        name="1b. Rental income expenses (hierarchical - Pub 527 has summaries)",
        question="What expenses can I deduct for rental property income?",
        accept_modes=["hierarchical"],
        accept_pubs=["527"],
        min_contexts=3,
    ),
    TestCase(
        name="1c. Capital gains on sale of property (hierarchical - Pub 544 has summaries)",
        question="How are gains and losses reported on the sale of business property?",
        accept_modes=["hierarchical"],
        accept_pubs=["544"],
        min_contexts=3,
    ),
    TestCase(
        name="1d. Business expenses (hierarchical - Pub 535 has summaries)",
        question="What business expenses are deductible for tax purposes?",
        accept_modes=["hierarchical"],
        accept_pubs=["535", "334", "527"],  # 535 is 2022-only; 334/527 cover business expenses for 2025
        min_contexts=3,
    ),
    TestCase(
        name="1e. Self-employment tax (hierarchical - Pub 334 has summaries)",
        question="How is self-employment tax calculated and what is the rate?",
        accept_modes=["hierarchical"],
        accept_pubs=["334"],
        min_contexts=3,
    ),

    # ─── GROUP 2: FLAT FALLBACK ──────────────────────────────────────────────
    # These target pubs WITHOUT summary chunks — hierarchical should fall back
    # to flat mode but still return relevant contexts.

    TestCase(
        name="2a. EIC income limits (flat fallback - Pub 596, no summaries)",
        question="What is the earned income credit income limit for a taxpayer with one qualifying child?",
        accept_modes=["flat", "flat_fallback", "hierarchical"],
        accept_pubs=["596", "17", "503", "504", "505"],  # vector search may pick adjacent pubs
        min_contexts=2,
    ),
    TestCase(
        name="2b. IRA contribution rules (flat fallback - Pubs 590a/590b, no summaries)",
        question="What are the IRA contribution limits and deduction rules?",
        accept_modes=["flat", "flat_fallback", "hierarchical"],
        accept_pubs=["590a", "590b", "503", "505", "560"],  # retirement/tax credit pubs
        min_contexts=2,
    ),
    TestCase(
        name="2c. Retirement plan limits (flat fallback - Pub 560, no summaries)",
        question="What are the contribution limits for SEP and SIMPLE retirement plans?",
        accept_modes=["flat", "flat_fallback", "hierarchical"],
        accept_pubs=["560", "590a", "590b", "334", "505"],  # retirement-related pubs
        min_contexts=2,
    ),

    # ─── GROUP 3: SCOPED MULTI-PUB SCENARIO ──────────────────────────────────
    # Complex questions spanning multiple pubs. Should trigger ontology routing.
    # Scoped mode requires the classifier to detect "scenario" intent AND
    # ontology to find multiple pub groups. If it falls to hierarchical that's
    # still acceptable for now.

    TestCase(
        name="3a. Rental depreciation + sale (scenario — Pubs 527, 946, 544)",
        question="My client bought a rental property for $300,000. How do I calculate the annual depreciation, and what tax rules apply when they eventually sell it at a gain?",
        accept_modes=["scoped_multi_pub", "hierarchical"],
        accept_pubs=["527", "946", "544"],
        min_contexts=3,
    ),
    TestCase(
        name="3b. Self-employment + business expenses (scenario — Pubs 334, 535)",
        question="My client is a freelance contractor who had $150,000 in revenue. How do I calculate the self-employment tax and what business expenses can offset the income?",
        accept_modes=["scoped_multi_pub", "hierarchical"],
        accept_pubs=["334", "535"],
        min_contexts=3,
    ),

    # ─── GROUP 4: CROSS-YEAR COMPARISON ──────────────────────────────────────
    # Uses years that actually exist in the DB: 2024 and 2025.
    # Pub 334 has data for both 2024 (195 chunks) and 2025 (209 chunks).

    TestCase(
        name="4a. SE tax rate changes 2024 vs 2025 (cross-year — Pub 334)",
        question="How did the self-employment tax rules change between 2024 and 2025?",
        accept_modes=["cross_year_comparison"],
        accept_pubs=["334"],
        min_contexts=2,
    ),

    # ─── GROUP 5: PUB-SCOPED RETRIEVAL ───────────────────────────────────────
    # Explicit pub_filter narrows to a single publication.

    TestCase(
        name="5a. Scoped to Pub 527 only (rental)",
        question="What are the passive activity rules for rental income?",
        accept_modes=["hierarchical", "flat", "flat_fallback"],
        accept_pubs=["527"],
        min_contexts=2,
        pub_filter=["527"],
    ),
    TestCase(
        name="5b. Scoped to Pub 550 only (investment income)",
        question="How is interest and dividend income reported?",
        accept_modes=["flat", "flat_fallback", "hierarchical"],
        accept_pubs=["550"],
        min_contexts=2,
        pub_filter=["550"],
    ),

    # ─── GROUP 6: YEAR-SPECIFIC RETRIEVAL ────────────────────────────────────
    # Verify default year (2025) and explicit year pinning.

    TestCase(
        name="6a. Default year = 2025 (no year mentioned)",
        question="What are the MACRS recovery period classifications for depreciable assets?",
        accept_modes=["hierarchical", "flat", "flat_fallback"],
        accept_pubs=["946"],
        min_contexts=2,
    ),
    TestCase(
        name="6b. Explicit year 2024 — Pub 334 has 2024 data",
        question="What was the self-employment tax rate in 2024?",
        accept_modes=["hierarchical", "flat", "flat_fallback"],
        accept_pubs=["334"],
        min_contexts=1,
    ),
    TestCase(
        name="6c. Year with no data (2023) — should return empty",
        question="What were the tax rules in 2023?",
        accept_modes=["flat", "flat_fallback", "hierarchical"],
        accept_pubs=[],  # no pubs expected
        min_contexts=0,
        expect_empty=True,
    ),
]


# ── Runner ───────────────────────────────────────────────────────────────────

def run_test(agent: TaxBrainAgent, tc: TestCase, synthesize: bool) -> tuple[bool, str, QueryResult | None]:
    """Run a single test. Returns (passed, message, result)."""
    try:
        result = agent.query(
            question=tc.question,
            pub_filter=tc.pub_filter,
            tax_year=tc.tax_year,
            synthesize=synthesize,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"EXCEPTION: {e}", None

    issues: list[str] = []

    # Check retrieval mode
    if tc.accept_modes and result.retrieval_mode not in tc.accept_modes:
        issues.append(
            f"mode: expected one of {tc.accept_modes}, got '{result.retrieval_mode}'"
        )

    # Check empty expectation
    if tc.expect_empty:
        if len(result.contexts) > 0:
            issues.append(
                f"expected empty results but got {len(result.contexts)} contexts"
            )
        # Don't check pubs/min_contexts for expected-empty tests
        if issues:
            return False, "; ".join(issues), result
        return True, "OK (empty as expected)", result

    # Check minimum contexts
    if len(result.contexts) < tc.min_contexts:
        issues.append(
            f"contexts: expected >={tc.min_contexts}, got {len(result.contexts)}"
        )

    # Check expected pubs appear in contexts
    if tc.accept_pubs:
        found_pubs = {ctx.reference for ctx in result.contexts}
        matched_pubs = [p for p in tc.accept_pubs if p in found_pubs]
        if not matched_pubs:
            issues.append(
                f"pubs: expected at least one of {tc.accept_pubs}, "
                f"found {sorted(found_pubs)}"
            )

    # Check no error (unless we expected empty)
    if result.error:
        issues.append(f"error: {result.error}")

    if issues:
        return False, "; ".join(issues), result
    return True, "OK", result


def main():
    parser = argparse.ArgumentParser(description="Tax Brain end-to-end test")
    parser.add_argument("--no-synth", action="store_true",
                        help="Skip LLM synthesis (retrieval only)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print full reports for each query")
    parser.add_argument("--test", "-t", type=str, default=None,
                        help="Run only tests matching this substring")
    args = parser.parse_args()

    synthesize = not args.no_synth

    print("=" * 72)
    print("  TAX BRAIN — End-to-End Validation")
    print(f"  Synthesis: {'ON' if synthesize else 'OFF (retrieval only)'}")
    print("=" * 72)

    # Build agent
    print("\nInitializing TaxBrainAgent...")
    t0 = time.time()
    agent = create_agent()
    print(f"  Agent ready in {time.time() - t0:.1f}s\n")

    # Filter tests
    tests = TESTS
    if args.test:
        tests = [t for t in TESTS if args.test.lower() in t.name.lower()]
        if not tests:
            print(f"No tests matching '{args.test}'")
            sys.exit(1)

    passed = 0
    failed = 0
    total_retrieval_ms = 0.0

    for i, tc in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {tc.name}")
        print(f"  Q: {tc.question[:80]}{'...' if len(tc.question) > 80 else ''}")

        ok, msg, result = run_test(agent, tc, synthesize)

        if ok:
            passed += 1
            if result and result.contexts:
                found_pubs = sorted({ctx.reference for ctx in result.contexts})
                print(f"  ✓ PASS — mode={result.retrieval_mode}, "
                      f"{len(result.contexts)} contexts, "
                      f"{result.retrieval_ms:.0f}ms, pubs={found_pubs}")
            else:
                print(f"  ✓ PASS — {msg}")
            if result and result.nav_pubs:
                print(f"    nav_pubs: {result.nav_pubs}")
            if result and result.ontology_pubs:
                print(f"    ontology_pubs: {result.ontology_pubs}")
        else:
            failed += 1
            print(f"  ✗ FAIL — {msg}")

        if result and result.retrieval_ms:
            total_retrieval_ms += result.retrieval_ms

        if args.verbose and result and result.contexts:
            print(f"    --- Contexts ({len(result.contexts)}) ---")
            for j, ctx in enumerate(result.contexts[:5], 1):
                print(f"    [{j}] Pub {ctx.reference} | {ctx.chunk_type} | "
                      f"score={ctx.score:.3f} | {ctx.section or ctx.chapter or 'no section'}")
                print(f"        {ctx.text[:120]}...")
            if len(result.contexts) > 5:
                print(f"    ... and {len(result.contexts) - 5} more")

        print()

    # Summary
    print("=" * 72)
    total = passed + failed
    if failed == 0:
        print(f"  ALL {total} TESTS PASSED ✓")
    else:
        print(f"  {passed}/{total} passed, {failed} FAILED ✗")
    print(f"  Total retrieval time: {total_retrieval_ms:.0f}ms "
          f"(avg {total_retrieval_ms / max(total, 1):.0f}ms/query)")
    print("=" * 72)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
