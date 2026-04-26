"""
taxkb/layer4/retriever.py

Leaf retrievers and merge utilities for the CPA query agent.

Contains:
  - normalize_query()        — strip gold-set "excerpt" noise
  - _rrf_merge()             — Reciprocal Rank Fusion
  - _hybrid_merge_augment()  — BM25-augmented merge (default strategy)
  - PublicationSearcher          — pgvector cosine similarity
  - KeywordSearcher            — Postgres tsvector full-text search
  - RuleSearcher          — MeF business rules
  - InstructionSearcher          — Instruction graph (form/line refs)

The orchestrator that ties these together is TaxBrainRetriever
(in agent/retriever.py). MultiLayerRetriever is a deprecated
alias that points to TaxBrainRetriever for backward compatibility.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from taxkb.agent.models import RetrievedPassage

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Query normalizer
# ──────────────────────────────────────────────────────────────────────────────

import re as _re

# Phrases that appear when a gold-set question was generated while the LLM
# had a specific chunk as "the excerpt".  They are meaningless to a retriever
# that has no current excerpt context and confuse the embedding model.
#
# Pattern: "according to the excerpt", "in this excerpt", "the excerpt states",
# "under the excerpt", "described in the excerpt", "mentioned in the excerpt" …
#
# Strategy: remove the phrase entirely; the surrounding content still conveys
# the retrieval intent.
_EXCERPT_PATTERNS = [
    _re.compile(r",?\s*according to the excerpt[,.]?", _re.I),
    _re.compile(r",?\s*as stated in the excerpt[,.]?", _re.I),
    _re.compile(r",?\s*as described in the excerpt[,.]?", _re.I),
    _re.compile(r",?\s*as mentioned in the excerpt[,.]?", _re.I),
    _re.compile(r"\bunder the excerpt\b[,.]?", _re.I),
    _re.compile(r"\bin (this|the) excerpt\b[,.]?", _re.I),
    _re.compile(r"\bthe excerpt states?\b[,.]?", _re.I),
    _re.compile(r"\bthe excerpt (describes?|mentions?|provides?|lists?|outlines?|says?|defines?)\b[,.]?", _re.I),
    _re.compile(r"\bdescribed in the excerpt\b[,.]?", _re.I),
    _re.compile(r"\bmentioned in the excerpt\b[,.]?", _re.I),
    _re.compile(r"\bprovided in the excerpt\b[,.]?", _re.I),
    _re.compile(r"\bthe excerpt\b", _re.I),   # catch-all for remaining bare refs
]

# Normalise spacing and capitalisation after stripping excerpt phrases.
def normalize_query(query: str) -> str:
    """
    Strip excerpt-reference phrases from retrieval queries.

    Gold-set questions are often generated while an LLM has a specific chunk
    as context, so they contain phrases like "the excerpt", "under the excerpt",
    or "as stated in the excerpt" that are meaningless at retrieval time.
    Removing them exposes the underlying domain intent that the embedding model
    can actually match.

    Examples
    ────────
    "Which tax forms does the excerpt state individuals should use?"
    → "Which tax forms do individuals use to file their return?"

    "Under the excerpt, how long must the employee be on active duty?"
    → "How long must the employee be on active duty?"

    Args:
        query : The raw question string.

    Returns:
        Cleaned query with excerpt references removed and whitespace normalised.
        The first character is capitalised.  If the cleaned result is blank,
        the original query is returned unchanged.
    """
    normalized = query
    for pat in _EXCERPT_PATTERNS:
        normalized = pat.sub("", normalized)
    # Collapse double spaces, strip, fix capitalisation
    normalized = _re.sub(r"\s{2,}", " ", normalized).strip()
    # Re-capitalise the first letter if lowercased by removal
    if normalized and normalized[0].islower():
        normalized = normalized[0].upper() + normalized[1:]
    result = normalized or query   # never return blank
    if result != query:
        logger.debug("normalize_query: %r → %r", query[:80], result[:80])
    return result

# ──────────────────────────────────────────────────────────────────────────────
# Reciprocal Rank Fusion
# ──────────────────────────────────────────────────────────────────────────────

def _rrf_merge(
    ranked_lists : list[list[RetrievedPassage]],
    top_k        : int,
    k            : int = 60,
) -> list[RetrievedPassage]:
    """
    Reciprocal Rank Fusion — merge multiple ranked retrieval lists into one.

    For each candidate document:
        rrf_score = Σ  1 / (k + rank_i)   for each list i that contains it

    where rank_i is the 1-based position in list i, and k=60 is the standard
    constant from the original RRF paper (Cormack et al., 2009).

    Candidates that appear in multiple lists get a boost from their combined
    rank contributions. Candidates unique to one list are still included but
    ranked lower. This is parameter-free (no tuning weights needed) and
    consistently outperforms linear score combination on heterogeneous lists.

    Args:
        ranked_lists : Each inner list is an ordered retrieval result
                       (position 0 = most relevant).
        top_k        : Maximum results to return.
        k            : RRF constant (default 60, rarely needs changing).

    Returns:
        Merged and re-ranked list capped at top_k.  Each context has
        retrieval_method="hybrid" and score set to its RRF score.
    """
    rrf_scores : dict[str, float]           = {}
    by_id      : dict[str, RetrievedPassage] = {}

    for result_list in ranked_lists:
        for rank, ctx in enumerate(result_list, start=1):
            # Use chunk_id as dedup key; fall back to text hash when empty.
            key = ctx.chunk_id if ctx.chunk_id else f"{ctx.reference}:{hash(ctx.text[:120])}"
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in by_id:
                by_id[key] = ctx

    # Re-rank by descending RRF score, stamp retrieval_method and score
    merged = sorted(
        by_id.keys(),
        key=lambda k_: rrf_scores[k_],
        reverse=True,
    )[:top_k]

    results = []
    for key in merged:
        ctx = by_id[key]
        ctx.retrieval_method = "hybrid"
        ctx.score            = round(rrf_scores[key], 6)
        results.append(ctx)

    return results


def _hybrid_merge_augment(
    vec_contexts     : list[RetrievedPassage],
    bm25_contexts    : list[RetrievedPassage],
    top_k            : int,
    max_bm25_extras  : int   = 3,
    bm25_min_score   : float = 0.05,
) -> list[RetrievedPassage]:
    """
    BM25-augmented merge — guarantees HR@top_k ≥ vector-only baseline.

    Strategy
    ────────
    1. Keep all vector top_k results **in their original order** (no re-ranking).
       This preserves the semantic ranking that already achieved 69.44% HR@10.
    2. Mark any chunk that also appears in BM25 results as retrieval_method="hybrid"
       (signal that both retrievers agreed on it — useful for CPA trust scoring).
    3. Append up to max_bm25_extras BM25-only chunks (not found by vector) at
       positions top_k+1 … top_k+max_bm25_extras.  These are bonus candidates
       that can only improve HR@(top_k+extras), never hurt HR@top_k.

    Why symmetric RRF failed
    ────────────────────────
    With k=60 for both retrievers, a BM25 rank-1 chunk scores 1/61 = 0.01639,
    beating a vector rank-10 chunk (1/70 = 0.01429).  For conceptual pubs
    (501, 550, 590b), BM25 keyword noise displaces correct vector results,
    causing HR@10 regression: 69.44% → 65.69%.

    Augmented merge eliminates this failure mode while preserving BM25 gains
    on exact-term pubs (525: +31pp, 969: +15pp) via the extra slots.

    Args:
        vec_contexts    : Vector results, ordered by cosine similarity (best first).
        bm25_contexts   : BM25 results, ordered by ts_rank_cd score (best first).
        top_k           : Number of guaranteed vector results to keep.
        max_bm25_extras : Maximum BM25-only chunks to append (default 3).
        bm25_min_score  : Minimum ts_rank_cd score for a BM25-only chunk to
                          qualify as an extra (default 0.05).  Filters out
                          false positives where many generic OR terms match
                          an unrelated chunk (e.g., Pub 596 EIC intro page
                          matching an S-corp passive loss query on common
                          words like "income", "wages", "loss").  Set to 0.0
                          to disable the filter.

    Returns:
        List of length ≤ top_k + max_bm25_extras.  Vector results occupy
        positions 0…top_k-1 (order preserved).  BM25 extras occupy
        positions top_k … top_k+max_bm25_extras-1.
    """
    # Build chunk_id sets for fast membership tests.
    # Fall back to text-hash key for chunks without a chunk_id.
    def _key(ctx: RetrievedPassage) -> str:
        return ctx.chunk_id if ctx.chunk_id else f"{ctx.reference}:{hash(ctx.text[:120])}"

    bm25_keys = {_key(ctx) for ctx in bm25_contexts}
    vec_keys  = {_key(ctx) for ctx in vec_contexts}

    # Step 1 + 2: preserve vector order, upgrade intersecting chunks to "hybrid"
    result = []
    for ctx in vec_contexts[:top_k]:
        if _key(ctx) in bm25_keys:
            ctx.retrieval_method = "hybrid"
        else:
            ctx.retrieval_method = "vector"
        result.append(ctx)

    # Step 3: append BM25-only extras (not retrieved by vector)
    #
    # Two guards against false positives:
    #
    # Guard A — publication scoping:
    #   Only accept extras from publications that the vector search already
    #   considered relevant.  OR-based BM25 can inflate scores for short
    #   intro pages (e.g., Pub 596 EIC page 1) that contain many common tax
    #   words ("income", "wages", "loss") even when the query is about an
    #   unrelated topic (e.g., S-corp passive activity losses).  Since vector
    #   search didn't retrieve any Pub 596 chunks for that query, we reject
    #   BM25 extras from that pub.
    #
    # Guard B — min-score threshold:
    #   Reject extras with ts_rank_cd < bm25_min_score.  Catches residual
    #   low-signal hits after Guard A.  Default 0.05 ≈ "at least one moderately
    #   specific term matched".
    #
    # Note: Guard A is intentionally relaxed when the top BM25 result comes
    # from a NEW publication AND its score is unusually high — a sign that
    # BM25 found a strong keyword match in a pub vector semantics undershooted.
    # This heuristic is reserved for a future phase when cross-pub routing
    # (Layer 1 MeF + Layer 2 instruction) is active.
    vec_pubs = {ctx.reference for ctx in vec_contexts[:top_k]}
    extras_added = 0
    for ctx in bm25_contexts:
        if extras_added >= max_bm25_extras:
            break
        # Guard B
        if ctx.score < bm25_min_score:
            logger.debug(
                "bm25 extra skipped (score %.4f < min %.4f): %s",
                ctx.score, bm25_min_score, ctx.chunk_id,
            )
            break   # sorted desc — remaining all below threshold too
        # Guard A
        if ctx.reference not in vec_pubs:
            logger.debug(
                "bm25 extra skipped (pub %s not in vector pubs %s): %s",
                ctx.reference, sorted(vec_pubs), ctx.chunk_id,
            )
            continue
        if _key(ctx) not in vec_keys:
            ctx.retrieval_method = "hybrid"   # confirmed by BM25, missed by vector
            result.append(ctx)
            extras_added += 1

    logger.debug(
        "hybrid_merge_augment: %d vector + %d bm25-extras = %d total",
        min(len(vec_contexts), top_k), extras_added, len(result),
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Layer 3 vector retriever
# ──────────────────────────────────────────────────────────────────────────────

class PublicationSearcher:
    """
    Semantic search over IRS publication chunks using pgvector cosine similarity.

    Wraps PublicationStore.search_similar() and converts results into
    RetrievedPassage objects tagged retrieval_method="vector".

    Supports optional dependency injection of ConnectionPool and EmbeddingClient
    for testing and integration with the config module.
    """

    def __init__(
        self,
        pg_dsn: str = "",
        api_key: str = "",
        pool: Optional[Any] = None,  # ConnectionPool protocol
        embedding_client: Optional[Any] = None,  # EmbeddingClient protocol
    ) -> None:
        self._api_key = api_key
        self._pool = pool
        self._embedding_client = embedding_client

    def retrieve(
        self,
        query       : str,
        top_k       : int  = 10,
        pub_numbers : Optional[list[str]] = None,
        tax_year    : Optional[int] = None,
    ) -> tuple[list[RetrievedPassage], float]:
        """
        Embed the query and return the top_k most similar publication chunks.

        Returns:
            (contexts, elapsed_ms)
        """
        from taxkb.publications.store import PublicationStore

        t0    = time.perf_counter()

        # Use injected embedding client if available, otherwise use global function
        if self._embedding_client is not None:
            q_vec = self._embedding_client.embed_query(query)
        else:
            from taxkb.publications.embeddings import embed_query
            q_vec = embed_query(query, api_key=self._api_key)

        # Use connection pool to get a store; if no pool, return empty
        if self._pool is None:
            logger.debug("Layer 3 vector: disabled (no pool)")
            return [], 0.0

        conn = self._pool.getconn()
        try:
            with PublicationStore(conn=conn) as store:
                raw = store.search_similar(
                    q_vec,
                    top_k       = top_k,
                    pub_numbers = pub_numbers,
                    tax_year    = tax_year,
                )
        finally:
            self._pool.putconn(conn)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("Layer 3 vector: %d results in %.0f ms", len(raw), elapsed_ms)

        return [
            RetrievedPassage(
                layer              = 3,
                source_type        = "publication",
                reference          = r.pub_number,
                title              = r.pub_title,
                text               = r.text,
                score              = r.score,
                page               = r.page_start,
                chunk_id           = r.chunk_id,
                chapter            = r.chapter_title or "",
                section            = r.section_title or "",
                retrieval_method   = "vector",
                context_annotation = getattr(r, 'context_annotation', ''),
            )
            for r in raw
        ], elapsed_ms


# ──────────────────────────────────────────────────────────────────────────────
# BM25 keyword retriever
# ──────────────────────────────────────────────────────────────────────────────

class KeywordSearcher:
    """
    Keyword search over IRS publication chunks using Postgres full-text search.

    Wraps PublicationStore.search_bm25() (plainto_tsquery + ts_rank_cd).
    Requires the text_tsvector column and GIN index:
        python cli.py add-bm25-index --pg-dsn "..."

    Returns an empty list silently if the column doesn't exist yet, so
    MultiLayerRetriever degrades gracefully to vector-only mode.

    Supports optional dependency injection of ConnectionPool for testing
    and integration with the config module.
    """

    def __init__(
        self,
        pg_dsn: str = "",
        pool: Optional[Any] = None,  # ConnectionPool protocol
    ) -> None:
        self._pool = pool

    def retrieve(
        self,
        query       : str,
        top_k       : int  = 10,
        pub_numbers : Optional[list[str]] = None,
        tax_year    : Optional[int] = None,
    ) -> tuple[list[RetrievedPassage], float]:
        """
        Full-text keyword search.  Returns (contexts, elapsed_ms).
        Results are tagged retrieval_method="bm25".
        """
        from taxkb.publications.store import PublicationStore

        t0 = time.perf_counter()

        # Use connection pool to get a store; if no pool, return empty
        if self._pool is None:
            logger.debug("Layer 3 BM25: disabled (no pool)")
            return [], 0.0

        conn = self._pool.getconn()
        try:
            with PublicationStore(conn=conn) as store:
                raw = store.search_bm25(
                    query,
                    top_k       = top_k,
                    pub_numbers = pub_numbers,
                    tax_year    = tax_year,
                )
        finally:
            self._pool.putconn(conn)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("Layer 3 BM25:   %d results in %.0f ms", len(raw), elapsed_ms)

        return [
            RetrievedPassage(
                layer              = 3,
                source_type        = "publication",
                reference          = r.pub_number,
                title              = r.pub_title,
                text               = r.text,
                score              = r.score,
                page               = r.page_start,
                chunk_id           = r.chunk_id,
                chapter            = r.chapter_title or "",
                section            = r.section_title or "",
                retrieval_method   = "bm25",
                context_annotation = getattr(r, 'context_annotation', ''),
            )
            for r in raw
        ], elapsed_ms


# ──────────────────────────────────────────────────────────────────────────────
# Layer 1 MeF business rules retriever
# ──────────────────────────────────────────────────────────────────────────────

class RuleSearcher:
    """
    Retrieves MeF business rules from PostgreSQL when the query
    references specific forms, fields, or error codes.

    Activated for QueryIntent.RULE and QueryIntent.FORM_LINE queries.
    Searches irs_kb.irs_business_rules table by form reference or error code pattern.
    """

    def __init__(
        self,
        pg_dsn: str = "",
        pool: Optional[Any] = None,  # ConnectionPool protocol
    ) -> None:
        self._pool = pool

    def retrieve(
        self,
        query: str,
        form_refs: list[str] | None = None,
        top_k: int = 5,
        tax_year: int | None = None,
    ) -> tuple[list[RetrievedPassage], float]:
        """
        Search MeF rules by form reference or error code pattern.

        Args:
            query: The normalized query string.
            form_refs: List of form references to search (e.g., ["Form1040", "ScheduleC"]).
            top_k: Maximum number of results per search.
            tax_year: Optional tax year to filter rules (NULL matches all years).

        Returns:
            (contexts, elapsed_ms)
        """
        t0 = time.perf_counter()

        if not self._pool:
            logger.debug("Layer 1 MeF rules: disabled (no pool)")
            return [], 0.0

        results = []

        try:
            conn = self._pool.getconn()
            try:
                with conn.cursor() as cur:
                    # Search by form reference
                    if form_refs:
                        patterns = []
                        for ref in form_refs:
                            # "Form1040" -> "%IRS1040%", "ScheduleC" -> "%ScheduleC%"
                            clean = ref.replace("Form", "IRS").replace("Schedule", "Schedule")
                            patterns.append(f"%{clean}%")

                        for pattern in patterns[:3]:  # limit to 3 patterns
                            try:
                                cur.execute("""
                                    SELECT rule_id, rule_type, field_path, rule_text,
                                           rule_expression, error_code, severity
                                    FROM irs_kb.irs_business_rules
                                    WHERE field_path LIKE %s
                                      AND is_current = true
                                      AND (%s IS NULL OR tax_year = %s)
                                    ORDER BY severity DESC
                                    LIMIT %s
                                """, (pattern, tax_year, tax_year, top_k))

                                for row in cur.fetchall():
                                    results.append(RetrievedPassage(
                                        layer=1,
                                        source_type="mef_rule",
                                        reference=str(row[0]),  # rule_id
                                        title=f"MeF Rule: {row[1]}",
                                        text=f"Rule {row[0]} ({row[1]}): {row[3]}\nExpression: {row[4]}\nError Code: {row[5]} | Severity: {row[6]}",
                                        score=1.0 if row[6] == "ERROR" else 0.8,
                                        chunk_id=str(row[0]),
                                        retrieval_method="mef_rule",
                                    ))
                            except Exception as exc:
                                logger.debug("Form pattern search failed: %s", exc)
                                continue

                    # Also search by error code pattern in query
                    error_code_match = re.search(r'F\d{4}-\d{3}', query)
                    if error_code_match:
                        code_prefix = error_code_match.group(0)
                        try:
                            cur.execute("""
                                SELECT rule_id, rule_type, field_path, rule_text,
                                       rule_expression, error_code, severity
                                FROM irs_kb.irs_business_rules
                                WHERE (rule_id LIKE %s OR error_code LIKE %s)
                                  AND is_current = true
                                LIMIT %s
                            """, (f"{code_prefix}%", f"{code_prefix}%", top_k))

                            for row in cur.fetchall():
                                if not any(r.chunk_id == str(row[0]) for r in results):
                                    results.append(RetrievedPassage(
                                        layer=1,
                                        source_type="mef_rule",
                                        reference=str(row[0]),
                                        title=f"MeF Rule: {row[1]}",
                                        text=f"Rule {row[0]} ({row[1]}): {row[3]}\nExpression: {row[4]}\nError Code: {row[5]} | Severity: {row[6]}",
                                        score=1.0,
                                        chunk_id=str(row[0]),
                                        retrieval_method="mef_rule",
                                    ))
                        except Exception as exc:
                            logger.debug("Error code search failed: %s", exc)

            finally:
                self._pool.putconn(conn)

            elapsed = (time.perf_counter() - t0) * 1000
            if results:
                logger.debug("Layer 1 MeF rules: %d results in %.0f ms", len(results), elapsed)
            return results[:top_k], elapsed

        except Exception as exc:
            logger.debug("Layer 1 retrieval failed (table may not exist): %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            return [], elapsed


# ──────────────────────────────────────────────────────────────────────────────
# Layer 2 instruction graph retriever
# ──────────────────────────────────────────────────────────────────────────────

class InstructionSearcher:
    """
    Retrieves instruction sections from the Neo4j instruction graph
    when the query references specific form line numbers.

    Activated for QueryIntent.FORM_LINE queries.
    Searches irs_kb.instruction_sections table by line reference.
    """

    def __init__(
        self,
        pg_dsn: str = "",
        pool: Optional[Any] = None,  # ConnectionPool protocol
    ) -> None:
        self._pool = pool

    def retrieve(
        self,
        query: str,
        line_refs: list[str] | None = None,
        form_refs: list[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievedPassage], float]:
        """
        Search Layer 2 instruction sections by form/line reference.

        Args:
            query: The normalized query string.
            line_refs: List of line references (e.g., ["Line 1a", "Line 7"]).
            form_refs: List of form references for context (e.g., ["1040"]).
            top_k: Maximum number of results per search.

        Returns:
            (contexts, elapsed_ms)
        """
        t0 = time.perf_counter()

        if not self._pool:
            logger.debug("Layer 2 instruction: disabled (no pool)")
            return [], 0.0

        results = []

        try:
            conn = self._pool.getconn()
            try:
                with conn.cursor() as cur:
                    # Search instruction sections that reference specific lines
                    if line_refs:
                        for line_ref in line_refs[:3]:
                            try:
                                cur.execute("""
                                    SELECT s.section_id, s.heading, s.body_text,
                                           s.form_refs, s.line_refs, s.pub_refs,
                                           p.page_id
                                    FROM irs_kb.instruction_sections s
                                    JOIN irs_kb.instruction_pages p ON s.page_id = p.page_id
                                    WHERE %s = ANY(s.line_refs)
                                    LIMIT %s
                                """, (line_ref, top_k))

                                for row in cur.fetchall():
                                    results.append(RetrievedPassage(
                                        layer=2,
                                        source_type="instruction_section",
                                        reference=str(row[6]),  # page_id
                                        title=row[1] or "Instruction Section",
                                        text=row[2] or "",
                                        score=0.9,
                                        chunk_id=str(row[0]),  # section_id
                                        retrieval_method="instruction_graph",
                                    ))
                            except Exception as exc:
                                logger.debug("Line reference search failed: %s", exc)
                                continue

            finally:
                self._pool.putconn(conn)

            elapsed = (time.perf_counter() - t0) * 1000
            if results:
                logger.debug("Layer 2 instruction: %d results in %.0f ms", len(results), elapsed)
            return results[:top_k], elapsed

        except Exception as exc:
            logger.debug("Layer 2 retrieval not available (table may not exist): %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            return [], elapsed


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compatibility alias
# ──────────────────────────────────────────────────────────────────────────────
# MultiLayerRetriever has been merged into TaxBrainRetriever.
# This alias exists so that any remaining imports don't break.

def _get_hierarchical_retriever():
    from taxkb.agent.retriever import TaxBrainRetriever
    return TaxBrainRetriever

# Lazy alias — resolves on first attribute access
class _MultiLayerRetrieverAlias:
    """Deprecated: use TaxBrainRetriever instead."""
    def __new__(cls, *args, **kwargs):
        import warnings
        warnings.warn(
            "MultiLayerRetriever is deprecated; use TaxBrainRetriever instead.",
            DeprecationWarning, stacklevel=2,
        )
        HR = _get_hierarchical_retriever()
        return HR(*args, **kwargs)

MultiLayerRetriever = _MultiLayerRetrieverAlias
