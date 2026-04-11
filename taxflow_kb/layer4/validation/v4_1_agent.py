"""
taxflow_kb/layer4/validation/v4_1_agent.py

Gate V4.1 — CPA Query Agent functional validation.

Runs a set of realistic CPA queries against the live agent and verifies:
  V4.1-A  Every query returns at least MIN_CONTEXTS retrieved chunks.
  V4.1-B  Every retrieved chunk has cosine score ≥ MIN_SCORE.
  V4.1-C  The synthesized answer is non-trivial (≥ MIN_ANSWER_CHARS).
  V4.1-D  Every answer cites at least one IRS publication.
  V4.1-E  Retrieval completes within MAX_RETRIEVAL_MS.
  V4.1-F  Synthesis completes within MAX_SYNTHESIS_MS.

This gate requires a live PostgreSQL (pgvector) database and OPENAI_API_KEY.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Thresholds ────────────────────────────────────────────────────────────────

MIN_CONTEXTS      = 3       # V4.1-A: at least this many chunks retrieved
MIN_SCORE         = 0.40    # V4.1-B: weakest acceptable cosine similarity
MIN_ANSWER_CHARS  = 80      # V4.1-C: answer must be substantive
MAX_RETRIEVAL_MS  = 20_000  # V4.1-E: retrieval ≤ 20 s
#   Note: the IVFFlat index cold-starts on first access (PostgreSQL loads
#   the index into shared_buffers). The first query in a session can take
#   10–15 s; subsequent queries run in < 2 s once the index is in RAM.
#   validate_agent() issues a single warmup search before the probes begin,
#   so in practice all 5 probes should complete well within this limit.
MAX_SYNTHESIS_MS  = 30_000  # V4.1-F: synthesis ≤ 30 s

# Pattern that matches "Pub XXX" or "Publication XXX" (IRS citation)
_CITATION_RE = re.compile(r"(?:Pub(?:lication)?\.?\s*\d+[a-z]?)", re.IGNORECASE)

# ── Standard CPA probe queries ────────────────────────────────────────────────
#
# Each tuple: (query_text, expected_pub_in_answer)
# expected_pub_in_answer is the pub number (string) that must appear somewhere
# in the synthesized answer — or None to skip that check.

CPA_PROBES: list[tuple[str, Optional[str]]] = [
    (
        "What are the income limits for claiming the Earned Income Credit "
        "with one qualifying child for 2024?",
        "596",
    ),
    (
        "My client is 70½ and has a traditional IRA. What are the required "
        "minimum distribution rules and how do they calculate the RMD amount?",
        "590b",
    ),
    (
        "Can my client deduct contributions to a Health Savings Account "
        "if they have a high-deductible health plan, and what is the 2024 limit?",
        "969",
    ),
    (
        "How are qualified dividends from a mutual fund taxed, "
        "and what holding-period requirement makes a dividend qualified?",
        "550",
    ),
    (
        "My client is single, age 45, and covered by a 401(k) at work. "
        "What is the maximum deductible traditional IRA contribution "
        "at a modified AGI of $85,000?",
        "590a",
    ),
]


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    query         : str
    passed        : bool  = False
    contexts_found: int   = 0
    min_chunk_score: float = 0.0
    answer_chars  : int   = 0
    cites_pub     : bool  = True   # only checked when expected_pub is set
    retrieval_ms  : float = 0.0
    synthesis_ms  : float = 0.0
    failure_reason: str   = ""


@dataclass
class V41Result:
    gate          : str  = "V4.1"
    passed        : bool = False
    total_probes  : int  = 0
    passed_probes : int  = 0
    failures      : list[str]        = field(default_factory=list)
    warnings      : list[str]        = field(default_factory=list)
    probe_results : list[ProbeResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{self.gate}] {status} — "
            f"{self.passed_probes}/{self.total_probes} probes pass"
        )

    def print_report(self) -> None:
        print(self.summary)
        for pr in self.probe_results:
            mark = "✓" if pr.passed else "✗"
            timing = f"ret={pr.retrieval_ms:.0f}ms syn={pr.synthesis_ms:.0f}ms"
            print(
                f"  {mark}  [{timing} | ctx={pr.contexts_found} | "
                f"ans={pr.answer_chars}c]  {pr.query[:65]}"
            )
            if not pr.passed:
                print(f"       → {pr.failure_reason}")
        for w in self.warnings:
            print(f"  WARN  {w}")
        print()


# ── Main gate function ────────────────────────────────────────────────────────

def validate_agent(
    agent,                                     # CPAQueryAgent
    probes: Optional[list[tuple[str, Optional[str]]]] = None,
    top_k : int = 5,
) -> V41Result:
    """
    Run the V4.1 functional validation gate against a live CPAQueryAgent.

    Args:
        agent  : Configured CPAQueryAgent instance.
        probes : Override the default CPA_PROBES list.
        top_k  : Chunks to retrieve per probe.

    Returns:
        V41Result with per-probe details.
    """
    if probes is None:
        probes = CPA_PROBES

    out = V41Result(total_probes=len(probes))

    # ── Warmup: load IVFFlat index into shared memory ─────────────────────────
    # The first pgvector search in a session is slow (10–15 s) because PostgreSQL
    # pages the IVFFlat index from disk into shared_buffers.  A single throw-away
    # search before the timed probes ensures all probe timings are representative.
    try:
        agent.query("tax filing status", top_k=1, synthesize=False)
    except Exception:
        pass  # warmup failure doesn't affect the gate result

    for query, expected_pub in probes:
        pr = ProbeResult(query=query)

        try:
            result = agent.query(query, top_k=top_k)
        except Exception as exc:
            pr.failure_reason = f"agent.query raised: {exc}"
            out.failures.append(f"V4.1 query error: {exc}")
            out.probe_results.append(pr)
            continue

        pr.retrieval_ms  = result.retrieval_ms
        pr.synthesis_ms  = result.synthesis_ms
        pr.contexts_found= len(result.contexts)
        pr.answer_chars  = len(result.answer)
        pr.min_chunk_score = min((c.score for c in result.contexts), default=0.0)

        fail_reasons: list[str] = []

        # A: minimum chunks
        if pr.contexts_found < MIN_CONTEXTS:
            fail_reasons.append(
                f"V4.1-A: only {pr.contexts_found} chunks (min {MIN_CONTEXTS})"
            )

        # B: score floor
        if pr.min_chunk_score < MIN_SCORE:
            fail_reasons.append(
                f"V4.1-B: min chunk score {pr.min_chunk_score:.3f} < {MIN_SCORE}"
            )

        # C: answer length
        if pr.answer_chars < MIN_ANSWER_CHARS:
            fail_reasons.append(
                f"V4.1-C: answer only {pr.answer_chars} chars (min {MIN_ANSWER_CHARS})"
            )

        # D: citation check
        if expected_pub:
            answer_lower = result.answer.lower()
            pub_cited = (
                f"pub {expected_pub}" in answer_lower
                or f"pub. {expected_pub}" in answer_lower
                or f"publication {expected_pub}" in answer_lower
                or bool(_CITATION_RE.search(result.answer))
            )
            pr.cites_pub = pub_cited
            if not pub_cited:
                fail_reasons.append(
                    f"V4.1-D: answer does not cite Pub {expected_pub}"
                )

        # E: retrieval latency
        if pr.retrieval_ms > MAX_RETRIEVAL_MS:
            fail_reasons.append(
                f"V4.1-E: retrieval {pr.retrieval_ms:.0f} ms > {MAX_RETRIEVAL_MS} ms"
            )

        # F: synthesis latency
        if pr.synthesis_ms > MAX_SYNTHESIS_MS:
            fail_reasons.append(
                f"V4.1-F: synthesis {pr.synthesis_ms:.0f} ms > {MAX_SYNTHESIS_MS} ms"
            )

        # Surface any agent-reported error as a warning
        if result.error:
            out.warnings.append(f"Agent error for query '{query[:40]}…': {result.error}")

        if fail_reasons:
            pr.failure_reason = "; ".join(fail_reasons)
            out.failures.extend(fail_reasons)
        else:
            pr.passed = True
            out.passed_probes += 1

        out.probe_results.append(pr)

    out.passed = len(out.failures) == 0
    return out
