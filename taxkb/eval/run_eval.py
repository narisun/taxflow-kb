#!/usr/bin/env python3
"""
Tax Brain — Evaluation Harness

Runs the golden-set questions through the TaxBrainAgent and scores both
retrieval quality and answer quality (via LLM-as-judge).

Metrics produced
────────────────
RETRIEVAL:
  • pub_precision   — fraction of retrieved pubs that are expected
  • pub_recall      — fraction of expected pubs that appear in results
  • context_count   — how many chunks came back
  • retrieval_ms    — wall-clock time

ANSWER (LLM-as-judge, 1-5 scale):
  • correctness     — does the answer match the ground truth?
  • completeness    — does it cover all key facts?
  • hallucination   — does it invent facts not in sources? (5=no hallucinations)
  • citation_quality — does it reference appropriate IRS sources?

Outputs:
  taxkb/eval/results/<timestamp>/scores.json     — per-question scores
  taxkb/eval/results/<timestamp>/summary.json    — aggregate metrics
  taxkb/eval/results/<timestamp>/report.txt      — human-readable report

Usage (run from project root):
  python taxkb/eval/run_eval.py                 # full eval
  python taxkb/eval/run_eval.py --no-synth      # retrieval only
  python taxkb/eval/run_eval.py --no-judge      # retrieve + synthesize, skip LLM judge
  python taxkb/eval/run_eval.py --golden taxkb/eval/golden_set.json
  python taxkb/eval/run_eval.py -t IND-01       # run single question by ID
  python taxkb/eval/run_eval.py --category "I." # run a category
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Setup path ──────────────────────────────────────────────────────────────
# Two levels up: taxkb/eval/run_eval.py → project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from taxkb.factories import create_agent
from taxkb.agent.agent import TaxBrainAgent
from taxkb.agent.models import QueryResult

# ═══════════════════════════════════════════════════════════════════════════
# LLM-as-Judge
# ═══════════════════════════════════════════════════════════════════════════

JUDGE_SYSTEM_PROMPT = """\
You are an expert tax evaluator. You will be given:
1. A CPA's question about U.S. tax law
2. The GROUND TRUTH answer (the correct answer)
3. The CANDIDATE answer produced by an AI system
4. The list of IRS sources the AI retrieved

Score the candidate answer on four dimensions (1-5 scale).

SCORING RUBRIC:

CORRECTNESS (does the answer match the ground truth?):
  5 = Perfectly matches all substantive claims in the ground truth
  4 = Mostly correct with minor omissions or imprecisions
  3 = Partially correct — gets the main idea but misses key details or numbers
  2 = Mostly incorrect — some relevant content but wrong conclusions
  1 = Completely wrong, contradicts the ground truth, or says "I don't know"

COMPLETENESS (does it cover all key facts from the ground truth?):
  5 = Covers every key fact and threshold from the ground truth
  4 = Covers most key facts, misses one minor point
  3 = Covers about half of the key facts
  2 = Covers only one or two key facts
  1 = Misses all key facts or is empty

HALLUCINATION (does it invent facts NOT supported by the retrieved sources?):
  5 = No fabricated facts — everything stated is grounded in sources or correct law
  4 = One minor unsupported claim that doesn't affect the conclusion
  3 = Contains a few unsupported claims
  2 = Significant fabricated details that could mislead a CPA
  1 = Mostly fabricated or confidently wrong

CITATION_QUALITY (does it reference appropriate IRS publications?):
  5 = Cites specific, correct IRS publications/forms matching the ground truth path
  4 = Cites relevant publications but missing specificity (chapter/section)
  3 = Cites some relevant sources but also irrelevant ones
  2 = Vague or mostly irrelevant citations
  1 = No citations or completely wrong sources

Respond ONLY with valid JSON (no markdown fences):
{"correctness": <int>, "completeness": <int>, "hallucination": <int>, "citation_quality": <int>, "reasoning": "<brief explanation>"}
"""

JUDGE_USER_TEMPLATE = """\
QUESTION:
{question}

GROUND TRUTH:
{ground_truth}

KEY FACTS TO CHECK:
{key_facts}

EXPECTED IRS SOURCES:
{expected_pubs}

CANDIDATE ANSWER:
{candidate_answer}

RETRIEVED SOURCES:
{retrieved_sources}

Score the candidate answer. Respond with JSON only.
"""


def judge_answer(
    question: str,
    ground_truth: str,
    key_facts: list[str],
    expected_pubs: list[str],
    candidate_answer: str,
    retrieved_sources: list[str],
    api_key: str,
    model: str = "gpt-4o",
) -> dict:
    """Call the LLM judge and return scores dict."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    user_msg = JUDGE_USER_TEMPLATE.format(
        question=question,
        ground_truth=ground_truth,
        key_facts=", ".join(key_facts),
        expected_pubs=", ".join(f"Pub {p}" for p in expected_pubs),
        candidate_answer=candidate_answer or "(NO ANSWER GENERATED)",
        retrieved_sources="\n".join(f"  - {s}" for s in retrieved_sources) or "(none)",
    )

    t0 = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=500,
    )
    judge_ms = (time.time() - t0) * 1000

    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        scores = json.loads(raw)
    except json.JSONDecodeError:
        scores = {
            "correctness": 0, "completeness": 0,
            "hallucination": 0, "citation_quality": 0,
            "reasoning": f"Judge parse error: {raw[:200]}",
        }

    scores["judge_ms"] = round(judge_ms)
    scores["judge_model"] = model
    scores["judge_tokens"] = response.usage.total_tokens if response.usage else 0
    return scores


# ═══════════════════════════════════════════════════════════════════════════
# Retrieval Scoring
# ═══════════════════════════════════════════════════════════════════════════

def score_retrieval(
    result: QueryResult,
    expected_pubs: list[str],
) -> dict:
    """Score retrieval quality for a single question."""
    retrieved_pubs = list(dict.fromkeys(
        ctx.reference for ctx in result.contexts
    ))

    # Normalize pub numbers for comparison
    norm = lambda p: p.lower().strip()
    expected_set = {norm(p) for p in expected_pubs}
    retrieved_set = {norm(p) for p in retrieved_pubs}

    # Also check nav_pubs and ontology_pubs
    all_touched_pubs = retrieved_set | {norm(p) for p in result.nav_pubs} | {norm(p) for p in result.ontology_pubs}

    true_pos = expected_set & retrieved_set
    pub_precision = len(true_pos) / len(retrieved_set) if retrieved_set else 0.0
    pub_recall = len(true_pos) / len(expected_set) if expected_set else 0.0

    # Broader recall: did we at least *navigate* to the right pub?
    nav_recall = len(expected_set & all_touched_pubs) / len(expected_set) if expected_set else 0.0

    return {
        "retrieved_pubs": retrieved_pubs,
        "expected_pubs": expected_pubs,
        "pub_precision": round(pub_precision, 3),
        "pub_recall": round(pub_recall, 3),
        "nav_recall": round(nav_recall, 3),
        "context_count": len(result.contexts),
        "retrieval_ms": round(result.retrieval_ms),
        "retrieval_mode": result.retrieval_mode,
        "nav_pubs": result.nav_pubs,
        "ontology_pubs": result.ontology_pubs,
        "query_intent": result.query_intent,
        "detected_tax_year": result.detected_tax_year,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Key-Fact Heuristic (fast pre-check before LLM judge)
# ═══════════════════════════════════════════════════════════════════════════

def check_key_facts(answer: str, key_facts: list[str]) -> dict:
    """Check which key facts appear in the answer (case-insensitive substring match)."""
    if not answer:
        return {"facts_found": 0, "facts_total": len(key_facts), "fact_ratio": 0.0, "missing": key_facts}
    answer_lower = answer.lower()
    found = []
    missing = []
    for fact in key_facts:
        if fact.lower() in answer_lower:
            found.append(fact)
        else:
            missing.append(fact)
    total = len(key_facts)
    return {
        "facts_found": len(found),
        "facts_total": total,
        "fact_ratio": round(len(found) / total, 3) if total else 0.0,
        "missing": missing,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main Runner
# ═══════════════════════════════════════════════════════════════════════════

def load_golden_set(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def run_eval(
    golden_set: list[dict],
    agent: TaxBrainAgent,
    synthesize: bool = True,
    run_judge: bool = True,
    judge_model: str = "gpt-4o",
    api_key: str = "",
    verbose: bool = False,
) -> list[dict]:
    """Run evaluation on all golden-set questions. Returns list of per-question results."""
    results = []
    total = len(golden_set)

    for i, item in enumerate(golden_set, 1):
        qid = item["id"]
        question = item["question"]
        ground_truth = item["ground_truth"]
        expected_pubs = item.get("expected_pubs", [])
        key_facts = item.get("key_facts", [])

        print(f"\n[{i}/{total}] {qid}: {question[:70]}...")

        # ── Run query ──────────────────────────────────────────────────
        t0 = time.time()
        try:
            result = agent.query(question, synthesize=synthesize)
        except Exception as exc:
            print(f"  ✗ ERROR: {exc}")
            results.append({
                "id": qid,
                "category": item.get("category", ""),
                "question": question,
                "error": str(exc),
            })
            continue
        query_ms = (time.time() - t0) * 1000

        # ── Retrieval scores ───────────────────────────────────────────
        retrieval_scores = score_retrieval(result, expected_pubs)

        # ── Key-fact heuristic ─────────────────────────────────────────
        fact_check = check_key_facts(result.answer, key_facts)

        # ── LLM-as-judge ──────────────────────────────────────────────
        judge_scores = {}
        if synthesize and run_judge and result.answer:
            try:
                judge_scores = judge_answer(
                    question=question,
                    ground_truth=ground_truth,
                    key_facts=key_facts,
                    expected_pubs=expected_pubs,
                    candidate_answer=result.answer,
                    retrieved_sources=result.sources,
                    api_key=api_key,
                    model=judge_model,
                )
            except Exception as exc:
                print(f"  ⚠ Judge error: {exc}")
                judge_scores = {"error": str(exc)}

        # ── Build result record ────────────────────────────────────────
        record = {
            "id": qid,
            "category": item.get("category", ""),
            "question": question,
            "ground_truth": ground_truth,
            "candidate_answer": result.answer,
            "retrieval": retrieval_scores,
            "fact_check": fact_check,
            "judge": judge_scores,
            "query_ms": round(query_ms),
            "synthesis_ms": round(result.synthesis_ms),
            "model_used": result.model_used,
            "tokens": result.total_tokens,
        }
        results.append(record)

        # ── Print progress ─────────────────────────────────────────────
        pub_ok = "✓" if retrieval_scores["pub_recall"] > 0 else "✗"
        fact_ok = f"{fact_check['facts_found']}/{fact_check['facts_total']}"
        judge_str = ""
        if judge_scores and "correctness" in judge_scores:
            judge_str = (
                f"  judge: C={judge_scores['correctness']} "
                f"F={judge_scores['completeness']} "
                f"H={judge_scores['hallucination']} "
                f"S={judge_scores['citation_quality']}"
            )

        print(
            f"  {pub_ok} pubs: {retrieval_scores['retrieved_pubs']}  "
            f"(recall={retrieval_scores['pub_recall']:.0%}, "
            f"nav_recall={retrieval_scores['nav_recall']:.0%})  "
            f"facts={fact_ok}  {retrieval_scores['retrieval_ms']}ms"
            f"{judge_str}"
        )

        if verbose and result.answer:
            print(f"  Answer: {result.answer[:200]}...")

    return results


def compute_summary(results: list[dict]) -> dict:
    """Compute aggregate metrics from per-question results."""
    valid = [r for r in results if "error" not in r]
    n = len(valid)
    if n == 0:
        return {"error": "No valid results"}

    # Retrieval aggregates
    pub_recalls = [r["retrieval"]["pub_recall"] for r in valid]
    nav_recalls = [r["retrieval"]["nav_recall"] for r in valid]
    pub_precisions = [r["retrieval"]["pub_precision"] for r in valid]
    context_counts = [r["retrieval"]["context_count"] for r in valid]
    retrieval_times = [r["retrieval"]["retrieval_ms"] for r in valid]

    # Fact-check aggregates
    fact_ratios = [r["fact_check"]["fact_ratio"] for r in valid]

    # Judge aggregates
    judged = [r for r in valid if r.get("judge") and "correctness" in r["judge"]]
    judge_agg = {}
    if judged:
        for dim in ["correctness", "completeness", "hallucination", "citation_quality"]:
            vals = [r["judge"][dim] for r in judged]
            judge_agg[dim] = {
                "mean": round(sum(vals) / len(vals), 2),
                "min": min(vals),
                "max": max(vals),
            }
        judge_agg["n_judged"] = len(judged)
        judge_agg["total_judge_tokens"] = sum(r["judge"].get("judge_tokens", 0) for r in judged)

    # Category breakdown
    categories: dict[str, list] = {}
    for r in valid:
        cat = r.get("category", "unknown")
        categories.setdefault(cat, []).append(r)

    cat_summary = {}
    for cat, items in categories.items():
        cat_judged = [r for r in items if r.get("judge") and "correctness" in r["judge"]]
        cat_summary[cat] = {
            "count": len(items),
            "avg_pub_recall": round(sum(r["retrieval"]["pub_recall"] for r in items) / len(items), 3),
            "avg_nav_recall": round(sum(r["retrieval"]["nav_recall"] for r in items) / len(items), 3),
            "avg_fact_ratio": round(sum(r["fact_check"]["fact_ratio"] for r in items) / len(items), 3),
        }
        if cat_judged:
            cat_summary[cat]["avg_correctness"] = round(
                sum(r["judge"]["correctness"] for r in cat_judged) / len(cat_judged), 2
            )

    # Coverage analysis: which expected pubs are never retrieved?
    all_expected = set()
    all_retrieved = set()
    for r in valid:
        all_expected.update(r["retrieval"]["expected_pubs"])
        all_retrieved.update(r["retrieval"]["retrieved_pubs"])
    missing_pubs = sorted(all_expected - all_retrieved)

    summary = {
        "total_questions": len(results),
        "valid_questions": n,
        "errors": len(results) - n,
        "retrieval": {
            "avg_pub_recall": round(sum(pub_recalls) / n, 3),
            "avg_nav_recall": round(sum(nav_recalls) / n, 3),
            "avg_pub_precision": round(sum(pub_precisions) / n, 3),
            "avg_context_count": round(sum(context_counts) / n, 1),
            "avg_retrieval_ms": round(sum(retrieval_times) / n),
            "total_retrieval_ms": sum(retrieval_times),
            "missing_pubs": missing_pubs,
        },
        "fact_check": {
            "avg_fact_ratio": round(sum(fact_ratios) / n, 3),
        },
        "judge": judge_agg,
        "by_category": cat_summary,
    }
    return summary


def format_report(summary: dict, results: list[dict]) -> str:
    """Generate a human-readable report."""
    lines = []
    w = 76
    lines.append("=" * w)
    lines.append("  TAX BRAIN — Evaluation Report")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * w)

    lines.append(f"\n  Questions: {summary['total_questions']} total, "
                 f"{summary['valid_questions']} valid, {summary['errors']} errors\n")

    # ── Retrieval ──────────────────────────────────────────────────────
    ret = summary["retrieval"]
    lines.append("─" * w)
    lines.append("  RETRIEVAL METRICS")
    lines.append("─" * w)
    lines.append(f"  Pub Recall (direct):     {ret['avg_pub_recall']:.1%}")
    lines.append(f"  Pub Recall (nav+onto):   {ret['avg_nav_recall']:.1%}")
    lines.append(f"  Pub Precision:           {ret['avg_pub_precision']:.1%}")
    lines.append(f"  Avg Contexts:            {ret['avg_context_count']}")
    lines.append(f"  Avg Retrieval Time:      {ret['avg_retrieval_ms']}ms")
    if ret["missing_pubs"]:
        lines.append(f"  Missing Pubs (never retrieved): {', '.join(ret['missing_pubs'])}")
    lines.append("")

    # ── Fact Check ─────────────────────────────────────────────────────
    lines.append("─" * w)
    lines.append("  FACT CHECK (heuristic)")
    lines.append("─" * w)
    lines.append(f"  Avg Key-Fact Ratio:      {summary['fact_check']['avg_fact_ratio']:.1%}")
    lines.append("")

    # ── Judge ──────────────────────────────────────────────────────────
    if summary["judge"]:
        j = summary["judge"]
        lines.append("─" * w)
        lines.append(f"  LLM-AS-JUDGE ({j.get('n_judged', 0)} questions judged)")
        lines.append("─" * w)
        for dim in ["correctness", "completeness", "hallucination", "citation_quality"]:
            if dim in j:
                d = j[dim]
                lines.append(f"  {dim:<22s}  mean={d['mean']:.1f}  min={d['min']}  max={d['max']}")
        if "total_judge_tokens" in j:
            lines.append(f"  Total judge tokens:      {j['total_judge_tokens']}")
        lines.append("")

    # ── Category Breakdown ─────────────────────────────────────────────
    lines.append("─" * w)
    lines.append("  BY CATEGORY")
    lines.append("─" * w)
    for cat, cs in summary.get("by_category", {}).items():
        line = f"  {cat[:50]:<52s} n={cs['count']}  recall={cs['avg_pub_recall']:.0%}  facts={cs['avg_fact_ratio']:.0%}"
        if "avg_correctness" in cs:
            line += f"  correct={cs['avg_correctness']:.1f}"
        lines.append(line)
    lines.append("")

    # ── Per-Question Detail ────────────────────────────────────────────
    lines.append("─" * w)
    lines.append("  PER-QUESTION DETAIL")
    lines.append("─" * w)
    for r in results:
        qid = r["id"]
        if "error" in r and "retrieval" not in r:
            lines.append(f"  {qid:<8s} ERROR: {r['error'][:60]}")
            continue

        ret = r["retrieval"]
        fc = r["fact_check"]
        status = "✓" if ret["pub_recall"] > 0 else "✗"
        line = (f"  {status} {qid:<8s} "
                f"recall={ret['pub_recall']:.0%}  "
                f"nav={ret['nav_recall']:.0%}  "
                f"facts={fc['facts_found']}/{fc['facts_total']}  "
                f"pubs={ret['retrieved_pubs']}")

        if r.get("judge") and "correctness" in r["judge"]:
            j = r["judge"]
            line += f"  C={j['correctness']} F={j['completeness']} H={j['hallucination']} S={j['citation_quality']}"
        lines.append(line)

        # Show missing facts
        if fc.get("missing"):
            lines.append(f"           missing: {', '.join(fc['missing'][:5])}")

    lines.append("")
    lines.append("=" * w)

    # ── Content Gap Analysis ───────────────────────────────────────────
    # Find questions with 0 recall to identify KB gaps
    gaps = [r for r in results if "retrieval" in r and r["retrieval"]["pub_recall"] == 0]
    if gaps:
        lines.append("")
        lines.append("─" * w)
        lines.append("  CONTENT GAP ANALYSIS")
        lines.append("  Questions where no expected pub was retrieved — likely missing from KB")
        lines.append("─" * w)
        needed_pubs: dict[str, list[str]] = {}
        for r in gaps:
            for p in r["retrieval"]["expected_pubs"]:
                needed_pubs.setdefault(p, []).append(r["id"])
        for pub, qids in sorted(needed_pubs.items()):
            lines.append(f"  Pub {pub:<8s} needed by: {', '.join(qids)}")
        lines.append("")
        lines.append(f"  → {len(needed_pubs)} publications need to be ingested or updated")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Tax Brain Evaluation Harness")
    parser.add_argument(
        "--golden",
        default=str(Path(__file__).resolve().parent / "golden_set.json"),
        help="Path to golden set JSON (default: taxkb/eval/golden_set.json)",
    )
    parser.add_argument("--no-synth", action="store_true",
                        help="Retrieval only (no synthesis)")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM-as-judge scoring")
    parser.add_argument("--judge-model", default="gpt-4o",
                        help="Model for LLM-as-judge (default: gpt-4o)")
    parser.add_argument("-t", "--test-id", nargs="+",
                        help="Run one or more questions by ID (e.g. -t IND-01 TIP-14)")
    parser.add_argument("--category",
                        help="Run only questions in matching category (substring)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print answer snippets")
    parser.add_argument("--output-dir",
                        help="Custom output directory (default: timestamped)")

    args = parser.parse_args()

    # ── Load golden set ────────────────────────────────────────────────
    golden = load_golden_set(args.golden)
    print(f"Loaded {len(golden)} questions from {args.golden}")

    # Filter
    if args.test_id:
        test_ids = set(args.test_id)
        golden = [q for q in golden if q["id"] in test_ids]
        if not golden:
            print(f"No questions found with IDs: {args.test_id}")
            sys.exit(1)
    elif args.category:
        golden = [q for q in golden if args.category.lower() in q.get("category", "").lower()]
        if not golden:
            print(f"No questions found in category matching '{args.category}'")
            sys.exit(1)

    print(f"Running {len(golden)} questions")

    # ── Setup ──────────────────────────────────────────────────────────
    synthesize = not args.no_synth
    run_judge = synthesize and not args.no_judge
    from taxkb.config import get_settings
    api_key = get_settings().openai_api_key.get_secret_value()

    mode_label = "FULL (retrieval + synthesis + judge)"
    if not synthesize:
        mode_label = "RETRIEVAL ONLY"
    elif not run_judge:
        mode_label = "RETRIEVAL + SYNTHESIS (no judge)"

    print(f"\n{'=' * 76}")
    print(f"  TAX BRAIN — Evaluation Harness")
    print(f"  Mode: {mode_label}")
    print(f"  Judge model: {args.judge_model}" if run_judge else "")
    print(f"{'=' * 76}")

    print("\nInitializing TaxBrainAgent...")
    t0 = time.time()
    agent = create_agent()
    print(f"  Agent ready in {time.time() - t0:.1f}s\n")

    # ── Run ────────────────────────────────────────────────────────────
    results = run_eval(
        golden_set=golden,
        agent=agent,
        synthesize=synthesize,
        run_judge=run_judge,
        judge_model=args.judge_model,
        api_key=api_key,
        verbose=args.verbose,
    )

    # ── Aggregate ──────────────────────────────────────────────────────
    summary = compute_summary(results)

    # ── Output ─────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_results = Path(__file__).resolve().parent / "results" / timestamp
    out_dir = Path(args.output_dir) if args.output_dir else default_results
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save scores
    scores_path = out_dir / "scores.json"
    with open(scores_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save summary
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Generate and save report
    report = format_report(summary, results)
    report_path = out_dir / "report.txt"
    with open(report_path, "w") as f:
        f.write(report)

    # Print report
    print(f"\n{report}")

    print(f"\nResults saved to: {out_dir}/")
    print(f"  scores.json   — per-question detail")
    print(f"  summary.json  — aggregate metrics")
    print(f"  report.txt    — this report")


if __name__ == "__main__":
    main()
