"""
taxflow_kb/layer5/retrieval_evaluator.py

Retrieval-quality evaluation for the TaxFlow knowledge base.

Runs every entry in a GoldSet through the Layer 3 retriever and measures
how well the system finds the exact chunks that contain the correct answer.

Metrics
-------
Hit Rate @ k   (HR@k)   : fraction of questions where a gold chunk appears in the top-k results.
MRR            (MRR)    : Mean Reciprocal Rank — measures how highly the first correct chunk ranks.
Recall @ k     (Rec@k)  : fraction of all gold chunks recovered within the top-k.
Publication Accuracy    : fraction of questions where the primary expected pub is in top-k.

All metrics are computed globally and broken down by difficulty, publication, and tax year.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Per-question result ───────────────────────────────────────────────────────

@dataclass
class RetrievalEvalResult:
    """Retrieval evaluation outcome for a single gold set entry."""
    entry_id      : str
    question      : str
    expected_pub  : str
    difficulty    : str
    gold_chunk_ids: list[str]

    # Populated during evaluation
    retrieved_chunk_ids: list[str]   = field(default_factory=list)
    retrieved_pub_numbers: list[str] = field(default_factory=list)
    retrieval_ms  : float            = 0.0
    error         : Optional[str]    = None

    # Computed metrics
    hit            : bool            = False   # any gold chunk in top-k (strict)
    first_hit_rank : Optional[int]   = None    # 1-based rank of first gold chunk hit
    reciprocal_rank: float           = 0.0    # 1 / first_hit_rank  (0 if miss)
    recall         : float           = 0.0    # fraction of gold chunks recovered
    pub_hit        : bool            = False   # expected pub appears in results

    def compute(self, top_k: int) -> None:
        """
        Compute hit/MRR/recall from retrieved vs gold chunk IDs.

        gold_chunk_ids should include the primary chunk AND any adjacent chunks
        (±1 from generator).  This prevents penalising the retriever when it
        finds an equally valid neighbouring chunk.
        """
        gold  = set(self.gold_chunk_ids)
        found = self.retrieved_chunk_ids  # ordered by rank (1-based = index+1)

        # Hit @ k — match against full gold set (primary + adjacent)
        hits_in_top_k = [cid for cid in found[:top_k] if cid in gold]
        self.hit = len(hits_in_top_k) > 0

        # MRR — rank of first hit within the gold set
        for rank, cid in enumerate(found[:top_k], 1):
            if cid in gold:
                self.first_hit_rank  = rank
                self.reciprocal_rank = 1.0 / rank
                break

        # Recall — primary chunk only (not adjacent) for a conservative measure
        primary_gold = {self.gold_chunk_ids[0]} if self.gold_chunk_ids else set()
        if primary_gold:
            recovered   = sum(1 for cid in found[:top_k] if cid in primary_gold)
            self.recall = recovered / len(primary_gold)

        # Publication hit
        self.pub_hit = self.expected_pub in self.retrieved_pub_numbers[:top_k]


# ── Aggregate report ──────────────────────────────────────────────────────────

@dataclass
class RetrievalReport:
    """Aggregate retrieval evaluation metrics."""

    top_k          : int
    total          : int     = 0
    errors         : int     = 0

    # Core metrics
    hit_count      : int     = 0
    mrr_sum        : float   = 0.0
    recall_sum     : float   = 0.0
    pub_hit_count  : int     = 0

    # Sliced metrics: {label: (hit_count, total, mrr_sum, recall_sum)}
    by_difficulty  : dict    = field(default_factory=dict)
    by_pub         : dict    = field(default_factory=dict)

    # Raw results for downstream use
    results        : list[RetrievalEvalResult] = field(default_factory=list)

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def hit_rate(self) -> float:
        return self.hit_count / self.total if self.total else 0.0

    @property
    def mrr(self) -> float:
        return self.mrr_sum / self.total if self.total else 0.0

    @property
    def recall(self) -> float:
        return self.recall_sum / self.total if self.total else 0.0

    @property
    def pub_accuracy(self) -> float:
        return self.pub_hit_count / self.total if self.total else 0.0

    # ── Accumulation ─────────────────────────────────────────────────────────

    def _slice_key(self, store: dict, key: str) -> list:
        return store.setdefault(key, [0, 0, 0.0, 0.0])  # [hits, total, mrr, recall]

    def add(self, result: RetrievalEvalResult) -> None:
        self.results.append(result)
        self.total += 1

        if result.error:
            self.errors += 1
            return

        self.hit_count     += int(result.hit)
        self.mrr_sum       += result.reciprocal_rank
        self.recall_sum    += result.recall
        self.pub_hit_count += int(result.pub_hit)

        for store, key in [
            (self.by_difficulty, result.difficulty),
            (self.by_pub,        result.expected_pub),
        ]:
            bucket = self._slice_key(store, key)
            bucket[0] += int(result.hit)
            bucket[1] += 1
            bucket[2] += result.reciprocal_rank
            bucket[3] += result.recall

    # ── Reporting ─────────────────────────────────────────────────────────────

    def _slice_rows(self, store: dict) -> list[str]:
        rows = []
        for k in sorted(store):
            h, t, m, r = store[k]
            hr  = h / t if t else 0.0
            mrr = m / t if t else 0.0
            rec = r / t if t else 0.0
            rows.append(f"    {k:<20} n={t:3d}  HR={hr:.2%}  MRR={mrr:.3f}  Rec={rec:.2%}")
        return rows

    def print_report(self) -> None:
        # Note on Hit Rate interpretation:
        #   With an expanded gold set (primary chunk + adjacent ±1), HR reflects
        #   whether the retriever found the answer REGION, not just the exact chunk.
        #   This is the meaningful production metric.
        #   Recall uses only the primary chunk for a conservative lower bound.
        lines = [
            "",
            "══════════════════════════════════════════════════════════════",
            f"  Layer 5 — Retrieval Evaluation  (top_k={self.top_k})",
            "══════════════════════════════════════════════════════════════",
            f"  Questions evaluated : {self.total}   (errors: {self.errors})",
            f"  Hit Rate @ {self.top_k:<2}       : {self.hit_rate:.2%}  "
            f"  ← primary + adjacent chunks",
            f"  MRR                 : {self.mrr:.3f}",
            f"  Recall @ {self.top_k:<2}         : {self.recall:.2%}  "
            f"  ← primary chunk only (strict)",
            f"  Publication Accuracy: {self.pub_accuracy:.2%}",
            "",
            "  ── By difficulty ──────────────────────────────────────────",
            *self._slice_rows(self.by_difficulty),
            "",
            "  ── By publication ─────────────────────────────────────────",
            *self._slice_rows(self.by_pub),
            "══════════════════════════════════════════════════════════════",
        ]
        print("\n".join(lines))

    def to_dict(self) -> dict:
        return {
            "top_k"          : self.top_k,
            "total"          : self.total,
            "errors"         : self.errors,
            "hit_rate"       : round(self.hit_rate,  4),
            "mrr"            : round(self.mrr,       4),
            "recall"         : round(self.recall,    4),
            "pub_accuracy"   : round(self.pub_accuracy, 4),
            "by_difficulty"  : {
                k: {"hit_rate": round(v[0]/v[1], 4) if v[1] else 0,
                    "mrr":      round(v[2]/v[1], 4) if v[1] else 0,
                    "recall":   round(v[3]/v[1], 4) if v[1] else 0,
                    "n":        v[1]}
                for k, v in self.by_difficulty.items()
            },
            "by_pub": {
                k: {"hit_rate": round(v[0]/v[1], 4) if v[1] else 0,
                    "mrr":      round(v[2]/v[1], 4) if v[1] else 0,
                    "recall":   round(v[3]/v[1], 4) if v[1] else 0,
                    "n":        v[1]}
                for k, v in self.by_pub.items()
            },
        }


# ── Main evaluator ────────────────────────────────────────────────────────────

def evaluate_retrieval(
    gold_set,                        # GoldSet instance
    retriever,                       # HierarchicalRetriever (already constructed)
    top_k           : int  = 5,
    pub_filter      : Optional[list[str]] = None,
    difficulty      : Optional[str] = None,
    verified_only   : bool = False,
    rate_limit_delay: float = 0.0,
) -> RetrievalReport:
    """
    Run retrieval on every gold set entry and compute recall/MRR metrics.

    Args:
        gold_set        : GoldSet (or filtered list of GoldSetEntry).
        retriever       : Connected HierarchicalRetriever.
        top_k           : Number of results to retrieve per question.
        pub_filter      : Restrict evaluation to specific publications.
        difficulty      : Restrict to "simple" | "medium" | "complex".
        verified_only   : Only run on CPA-verified gold entries.
        rate_limit_delay: Optional pause between calls.

    Returns:
        RetrievalReport with HR@k, MRR, Recall@k, and per-slice breakdowns.
    """
    # Filter entries
    entries = gold_set.filter(
        pub        = pub_filter[0] if pub_filter and len(pub_filter) == 1 else None,
        difficulty = difficulty,
        verified_only = verified_only,
    )
    # Multi-pub filter (gold_set.filter supports only single pub, apply manually)
    if pub_filter and len(pub_filter) > 1:
        entries = [e for e in entries if e.expected_pub in pub_filter]

    logger.info(
        "Retrieval eval: %d entries, top_k=%d", len(entries), top_k
    )

    report = RetrievalReport(top_k=top_k)

    # Warmup — avoid IVFFlat cold-start penalty on first real probe
    try:
        retriever.retrieve("tax filing requirements", top_k=1)
    except Exception:
        pass

    for i, entry in enumerate(entries):
        result = RetrievalEvalResult(
            entry_id       = entry.id,
            question       = entry.question,
            expected_pub   = entry.expected_pub,
            difficulty     = entry.difficulty,
            gold_chunk_ids = entry.gold_chunk_ids,
        )

        try:
            t0 = time.perf_counter()
            # HierarchicalRetriever returns 3-tuple (contexts, ms, metadata)
            ret = retriever.retrieve(
                entry.question,
                top_k = top_k,
            )
            contexts, retrieval_ms = ret[0], ret[1]
            result.retrieval_ms = retrieval_ms

            # Extract chunk IDs and pub numbers from returned contexts
            result.retrieved_chunk_ids    = [c.chunk_id  for c in contexts]
            result.retrieved_pub_numbers  = [c.reference for c in contexts]   # reference = pub_number

            result.compute(top_k=top_k)

        except Exception as exc:
            logger.error("Retrieval failed for entry %s: %s", entry.id, exc)
            result.error = str(exc)

        report.add(result)

        if (i + 1) % 10 == 0:
            logger.info(
                "  … %d/%d evaluated  HR=%.2f  MRR=%.3f",
                i + 1, len(entries), report.hit_rate, report.mrr,
            )

        if rate_limit_delay:
            time.sleep(rate_limit_delay)

    logger.info(
        "Retrieval eval complete: HR@%d=%.2f  MRR=%.3f  Rec=%.2f",
        top_k, report.hit_rate, report.mrr, report.recall,
    )
    return report
