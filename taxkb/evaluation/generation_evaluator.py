"""
taxkb/layer5/generation_evaluator.py

LLM-as-judge evaluation for the TaxFlow answer synthesis pipeline.

For each gold set entry we:
  1. Run the full TaxBrainAgent to get an answer.
  2. Ask GPT-5.4 to score the answer against the ground truth using
     a structured 5-dimension tax rubric.
  3. Aggregate scores and produce a report with pass/fail gate thresholds.

Tax-domain rubric dimensions
─────────────────────────────
  faithfulness       — Does every claim trace back to the provided IRS excerpts?
  answer_correctness — Is the final answer factually correct vs ground truth?
  citation_accuracy  — Are IRS pub numbers / chapters / pages correctly cited?
  temporal_accuracy  — Are tax-year-specific values (limits, rates) correct?
  safe_abstention    — Does the model abstain correctly when knowledge is absent?

Each dimension is scored 0–4:
  0  Completely wrong or absent
  1  Mostly wrong / major gaps
  2  Partially correct
  3  Mostly correct / minor issues
  4  Fully correct

Overall score = mean of the five dimensions (0.0 – 4.0).
Gate threshold : overall ≥ 3.0  AND  faithfulness ≥ 3  AND  citation_accuracy ≥ 3
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Rubric prompt ─────────────────────────────────────────────────────────────

_JUDGE_SYSTEM = """\
You are an expert CPA and AI evaluator. You assess the quality of answers
produced by an AI tax research assistant against gold-standard CPA-verified
answers.

Score ONLY on the five dimensions defined below. Return ONLY valid JSON.
"""

_JUDGE_USER = """\
=== QUESTION ===
{question}

=== GROUND TRUTH (CPA-verified) ===
{ground_truth}

=== AI ANSWER TO EVALUATE ===
{answer}

=== IRS PUBLICATION EXCERPTS PROVIDED TO THE AI ===
{context_snippets}

Score the AI answer on EACH of the five dimensions using integer 0–4:

  faithfulness       : Every factual claim is directly supported by the provided excerpts.
                       Do not penalise for omitting facts — only penalise for adding unsupported ones.
                       0=makes up facts  4=all claims fully grounded
  answer_correctness : The answer matches the ground truth in all key facts and figures.
                       0=completely wrong  4=fully correct
  citation_accuracy  : The AI correctly references IRS publication numbers and [N] source labels
                       from the provided excerpts. Do NOT penalise for missing page numbers —
                       page numbers are not reliably available in the system.
                       Score based on: correct pub numbers cited, correct [N] labels used,
                       no fabricated source references.
                       0=no citations or completely wrong pub numbers
                       2=correct pub numbers but wrong or missing [N] labels
                       3=correct pub numbers and mostly correct source labels
                       4=all pub numbers and source labels precise and correct
  temporal_accuracy  : Tax-year-specific amounts, rates, and limits match the ground truth.
                       0=wrong year or values  4=correct year and values
  safe_abstention    : If the excerpts lacked enough info, the AI said "INSUFFICIENT CONTEXT".
                       Score 4 if excerpts WERE sufficient (no abstention needed).
                       Score 4 if the AI correctly stated "INSUFFICIENT CONTEXT".
                       Score 1 if the AI partially answered instead of abstaining clearly.
                       Score 0 if the AI fabricated an answer when it should have abstained.

Return this exact JSON schema (no markdown, no extra keys):
{{
  "faithfulness"       : <int 0-4>,
  "answer_correctness" : <int 0-4>,
  "citation_accuracy"  : <int 0-4>,
  "temporal_accuracy"  : <int 0-4>,
  "safe_abstention"    : <int 0-4>,
  "reasoning"          : "<one-sentence justification for any dimension scored below 3>"
}}
"""

# ── Per-question result ───────────────────────────────────────────────────────

@dataclass
class GenerationEvalResult:
    """Evaluation outcome for a single gold set entry."""
    entry_id      : str
    question      : str
    expected_pub  : str
    difficulty    : str
    ground_truth  : str

    # Populated after agent run
    ai_answer     : str  = ""
    retrieval_ms  : float = 0.0
    synthesis_ms  : float = 0.0
    agent_error   : Optional[str] = None

    # Populated after judge run
    faithfulness       : Optional[int] = None
    answer_correctness : Optional[int] = None
    citation_accuracy  : Optional[int] = None
    temporal_accuracy  : Optional[int] = None
    safe_abstention    : Optional[int] = None
    reasoning          : str = ""
    judge_error        : Optional[str] = None
    judge_ms           : float = 0.0

    @property
    def overall_score(self) -> Optional[float]:
        dims = [self.faithfulness, self.answer_correctness,
                self.citation_accuracy, self.temporal_accuracy, self.safe_abstention]
        if any(d is None for d in dims):
            return None
        return sum(dims) / len(dims)

    @property
    def passes_gate(self) -> bool:
        """True if this answer meets the minimum quality threshold."""
        if self.overall_score is None:
            return False
        return (
            self.overall_score       >= 3.0
            and self.faithfulness    >= 3
            and self.citation_accuracy >= 3
        )

    def to_dict(self) -> dict:
        return {
            "entry_id"          : self.entry_id,
            "question"          : self.question,
            "expected_pub"      : self.expected_pub,
            "difficulty"        : self.difficulty,
            "overall_score"     : self.overall_score,
            "passes_gate"       : self.passes_gate,
            "faithfulness"      : self.faithfulness,
            "answer_correctness": self.answer_correctness,
            "citation_accuracy" : self.citation_accuracy,
            "temporal_accuracy" : self.temporal_accuracy,
            "safe_abstention"   : self.safe_abstention,
            "reasoning"         : self.reasoning,
            "ai_answer"         : self.ai_answer[:800] if self.ai_answer else "",
            "agent_error"       : self.agent_error,
            "judge_error"       : self.judge_error,
        }


# ── Aggregate report ──────────────────────────────────────────────────────────

@dataclass
class GenerationReport:
    """Aggregate generation-quality evaluation."""

    total         : int   = 0
    agent_errors  : int   = 0
    judge_errors  : int   = 0
    pass_count    : int   = 0

    # Dimension sum accumulators
    _faith_sum    : float = field(default=0.0, repr=False)
    _corr_sum     : float = field(default=0.0, repr=False)
    _cit_sum      : float = field(default=0.0, repr=False)
    _temp_sum     : float = field(default=0.0, repr=False)
    _abst_sum     : float = field(default=0.0, repr=False)
    _scored       : int   = field(default=0,   repr=False)

    by_difficulty : dict  = field(default_factory=dict)
    by_pub        : dict  = field(default_factory=dict)

    results       : list[GenerationEvalResult] = field(default_factory=list)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total if self.total else 0.0

    def _avg(self, total: float) -> float:
        return total / self._scored if self._scored else 0.0

    @property
    def avg_faithfulness(self)       -> float: return self._avg(self._faith_sum)
    @property
    def avg_answer_correctness(self) -> float: return self._avg(self._corr_sum)
    @property
    def avg_citation_accuracy(self)  -> float: return self._avg(self._cit_sum)
    @property
    def avg_temporal_accuracy(self)  -> float: return self._avg(self._temp_sum)
    @property
    def avg_safe_abstention(self)    -> float: return self._avg(self._abst_sum)

    @property
    def avg_overall(self) -> float:
        return self._avg(
            self._faith_sum + self._corr_sum + self._cit_sum +
            self._temp_sum  + self._abst_sum
        ) / 5 if self._scored else 0.0

    # ── Accumulation ─────────────────────────────────────────────────────────

    def add(self, result: GenerationEvalResult) -> None:
        self.results.append(result)
        self.total += 1

        if result.agent_error:
            self.agent_errors += 1
            return
        if result.judge_error:
            self.judge_errors += 1
            return

        if result.overall_score is not None:
            self._faith_sum += result.faithfulness
            self._corr_sum  += result.answer_correctness
            self._cit_sum   += result.citation_accuracy
            self._temp_sum  += result.temporal_accuracy
            self._abst_sum  += result.safe_abstention
            self._scored    += 1
            self.pass_count += int(result.passes_gate)

        # Slice by difficulty
        diff = result.difficulty
        bucket = self.by_difficulty.setdefault(diff, {"pass": 0, "total": 0, "score_sum": 0.0})
        bucket["total"] += 1
        if result.passes_gate:
            bucket["pass"] += 1
        if result.overall_score is not None:
            bucket["score_sum"] += result.overall_score

        # Slice by pub
        pub = result.expected_pub
        pbucket = self.by_pub.setdefault(pub, {"pass": 0, "total": 0, "score_sum": 0.0})
        pbucket["total"] += 1
        if result.passes_gate:
            pbucket["pass"] += 1
        if result.overall_score is not None:
            pbucket["score_sum"] += result.overall_score

    # ── Reporting ─────────────────────────────────────────────────────────────

    def print_report(self) -> None:
        gate = "PASS ✓" if self.pass_rate >= 0.75 else "FAIL ✗"
        lines = [
            "",
            "══════════════════════════════════════════════════════════════",
            f"  Layer 5 — Generation Quality (LLM-as-Judge)",
            "══════════════════════════════════════════════════════════════",
            f"  Questions evaluated : {self.total}  "
            f"(agent errors: {self.agent_errors}, judge errors: {self.judge_errors})",
            f"  Gate (pass rate ≥75%): {gate}",
            f"  Pass rate           : {self.pass_rate:.1%}  ({self.pass_count}/{self.total})",
            f"  Overall score       : {self.avg_overall:.2f} / 4.0",
            "",
            "  Dimension averages (max 4.0):",
            f"    Faithfulness       : {self.avg_faithfulness:.2f}",
            f"    Answer Correctness : {self.avg_answer_correctness:.2f}",
            f"    Citation Accuracy  : {self.avg_citation_accuracy:.2f}",
            f"    Temporal Accuracy  : {self.avg_temporal_accuracy:.2f}",
            f"    Safe Abstention    : {self.avg_safe_abstention:.2f}",
        ]

        if self.by_difficulty:
            lines += ["", "  ── By difficulty ──────────────────────────────────────────"]
            for k in sorted(self.by_difficulty):
                b = self.by_difficulty[k]
                pr  = b["pass"] / b["total"] if b["total"] else 0.0
                avg = b["score_sum"] / b["total"] if b["total"] else 0.0
                lines.append(f"    {k:<20} n={b['total']:3d}  pass={pr:.1%}  avg={avg:.2f}")

        if self.by_pub:
            lines += ["", "  ── By publication ─────────────────────────────────────────"]
            for k in sorted(self.by_pub):
                b = self.by_pub[k]
                pr  = b["pass"] / b["total"] if b["total"] else 0.0
                avg = b["score_sum"] / b["total"] if b["total"] else 0.0
                lines.append(f"    Pub {k:<17} n={b['total']:3d}  pass={pr:.1%}  avg={avg:.2f}")

        lines.append("══════════════════════════════════════════════════════════════")
        print("\n".join(lines))

    def to_dict(self) -> dict:
        return {
            "total"              : self.total,
            "agent_errors"       : self.agent_errors,
            "judge_errors"       : self.judge_errors,
            "pass_rate"          : round(self.pass_rate, 4),
            "pass_count"         : self.pass_count,
            "avg_overall"        : round(self.avg_overall, 4),
            "avg_faithfulness"   : round(self.avg_faithfulness, 4),
            "avg_answer_correctness": round(self.avg_answer_correctness, 4),
            "avg_citation_accuracy" : round(self.avg_citation_accuracy,  4),
            "avg_temporal_accuracy" : round(self.avg_temporal_accuracy,  4),
            "avg_safe_abstention"   : round(self.avg_safe_abstention,    4),
            "by_difficulty"      : self.by_difficulty,
            "by_pub"             : self.by_pub,
        }


# ── LLM judge call ────────────────────────────────────────────────────────────

def _call_judge(
    result  : GenerationEvalResult,
    contexts: list,       # list of RetrievedPassage
    api_key : str,
    model   : str,
) -> None:
    """Call GPT-5.4 to score result.ai_answer; writes scores into result in-place."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    context_snippets = "\n".join(
        f"[{i+1}] {c.citation}\n{c.text[:500]}"
        for i, c in enumerate(contexts[:5])
    )

    prompt = _JUDGE_USER.format(
        question         = result.question,
        ground_truth     = result.ground_truth,
        answer           = result.ai_answer[:2000],
        context_snippets = context_snippets[:3000],
    )

    # GPT-5.x and o-series models use max_completion_tokens; older models use max_tokens.
    _NEW_TOKEN_PARAM_PREFIXES = ("gpt-5", "o1", "o3", "o4")
    token_kwarg = (
        {"max_completion_tokens": 512}
        if any(model.startswith(p) for p in _NEW_TOKEN_PARAM_PREFIXES)
        else {"max_tokens": 512}
    )

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model           = model,
            messages        = [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature     = 0.0,
            response_format = {"type": "json_object"},
            **token_kwarg,
        )
        raw = response.choices[0].message.content or "{}"
    except Exception as exc:
        result.judge_error = str(exc)
        return
    finally:
        result.judge_ms = (time.perf_counter() - t0) * 1000

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        result.judge_error = f"JSON parse error: {exc}"
        return

    def _int_score(key: str) -> Optional[int]:
        v = data.get(key)
        try:
            v = int(v)
            return max(0, min(4, v))
        except (TypeError, ValueError):
            return None

    result.faithfulness       = _int_score("faithfulness")
    result.answer_correctness = _int_score("answer_correctness")
    result.citation_accuracy  = _int_score("citation_accuracy")
    result.temporal_accuracy  = _int_score("temporal_accuracy")
    result.safe_abstention    = _int_score("safe_abstention")
    result.reasoning          = str(data.get("reasoning", ""))


# ── Main evaluator ────────────────────────────────────────────────────────────

def evaluate_generation(
    gold_set         ,          # GoldSet instance
    agent            ,          # TaxBrainAgent (already constructed)
    api_key          : str,
    judge_model      : str  = "gpt-5.4",
    agent_top_k      : int  = 10,
    pub_filter       : Optional[list[str]] = None,
    difficulty       : Optional[str]       = None,
    verified_only    : bool  = False,
    rate_limit_delay : float = 1.0,
    sample           : Optional[int]       = None,
    sample_seed      : int   = 42,
) -> GenerationReport:
    """
    Run the full agent pipeline for each gold set entry and judge the output.

    Args:
        gold_set        : GoldSet to evaluate.
        agent           : Initialized TaxBrainAgent.
        api_key         : OpenAI API key (for the judge).
        judge_model     : Model to use for judging (gpt-5.4 recommended).
        agent_top_k     : top_k chunks for the agent's retriever.
        pub_filter      : Restrict to specific publications.
        difficulty      : Restrict by difficulty tier.
        verified_only   : Only evaluate CPA-verified gold entries.
        rate_limit_delay: Seconds to pause between judge calls.
        sample          : If set, randomly sample this many entries (for quick
                          spot-checks before running the full gold set).
        sample_seed     : Random seed for reproducible sampling (default 42).

    Returns:
        GenerationReport with per-dimension averages and pass/fail breakdowns.
    """
    import random as _random

    entries = gold_set.filter(
        pub          = pub_filter[0] if pub_filter and len(pub_filter) == 1 else None,
        difficulty   = difficulty,
        verified_only= verified_only,
    )
    if pub_filter and len(pub_filter) > 1:
        entries = [e for e in entries if e.expected_pub in pub_filter]

    # Optional random sample for fast iteration
    if sample is not None and sample < len(entries):
        rng = _random.Random(sample_seed)
        entries = rng.sample(entries, sample)
        logger.info(
            "Generation eval (SAMPLE %d/%d): judge_model=%s",
            len(entries), len(gold_set.entries), judge_model,
        )
    else:
        logger.info(
            "Generation eval: %d entries, judge_model=%s", len(entries), judge_model
        )

    # Warmup the agent's retriever to avoid IVFFlat cold-start penalty
    try:
        agent.query("filing status overview", top_k=1, synthesize=False)
    except Exception:
        pass

    report = GenerationReport()

    for i, entry in enumerate(entries):
        result = GenerationEvalResult(
            entry_id     = entry.id,
            question     = entry.question,
            expected_pub = entry.expected_pub,
            difficulty   = entry.difficulty,
            ground_truth = entry.ground_truth,
        )

        # Step 1 — run the agent
        try:
            query_result = agent.query(
                question  = entry.question,
                top_k     = agent_top_k,
                synthesize= True,
            )
            if query_result.error:
                result.agent_error = query_result.error
            else:
                result.ai_answer    = query_result.answer
                result.retrieval_ms = query_result.retrieval_ms
                result.synthesis_ms = query_result.synthesis_ms
        except Exception as exc:
            logger.error("Agent failed for entry %s: %s", entry.id, exc)
            result.agent_error = str(exc)

        # Step 2 — judge the answer (skip if agent failed)
        if not result.agent_error:
            contexts = getattr(query_result, "contexts", [])
            _call_judge(result, contexts, api_key, judge_model)

        report.add(result)

        if (i + 1) % 5 == 0:
            logger.info(
                "  … %d/%d judged  pass_rate=%.1f%%  avg_overall=%.2f",
                i + 1, len(entries),
                report.pass_rate * 100, report.avg_overall,
            )

        if rate_limit_delay:
            time.sleep(rate_limit_delay)

    logger.info(
        "Generation eval complete: pass_rate=%.1f%%  avg=%.2f",
        report.pass_rate * 100, report.avg_overall,
    )
    return report
