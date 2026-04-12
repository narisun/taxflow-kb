"""
tax_brain/layer4/reranker.py

Query-aware chunk reranking for the CPA query agent.

After initial retrieval returns 30-50 chunks, this module re-scores each
chunk for relevance to the specific query, producing a tighter, higher-
precision set of chunks for synthesis.

Scoring strategy (no external API calls):
  1. Original vector/BM25 score (normalized)
  2. Query term overlap — how many query keywords appear in the chunk text
  3. Numeric entity match — chunks containing specific numbers/thresholds
     that the query asks about get boosted
  4. Pub priority — chunks from nav_pubs (directly matched by Navigate)
     rank higher than ontology_pubs (indirectly matched)
  5. Chunk type priority — detail > section_summary > pub_summary when
     detail chunks from the same pub exist

The composite score determines chunk ordering for synthesis.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Optional

from tax_brain.agent.models import RetrievedPassage

logger = logging.getLogger(__name__)

# ── Stop words to exclude from query term matching ─────────────────────────
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "about", "also", "and", "but", "or", "if", "because",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "its", "it", "my", "me", "i", "we", "our", "you", "your",
    "he", "she", "they", "them", "his", "her", "their",
})

# ── Tax-specific high-value terms that should boost relevance ──────────────
_TAX_ENTITIES = re.compile(
    r"""
    \$[\d,]+(?:\.\d{2})?          |  # Dollar amounts ($6,000, $150,000.00)
    \b\d{1,3}(?:,\d{3})+\b       |  # Large numbers (150,000)
    \b\d+(?:\.\d+)?%\b            |  # Percentages (15.3%, 50%)
    \bForm\s+\d[\w-]*\b           |  # Form references (Form 4562, Form W-2)
    \bSchedule\s+[A-Z][\w-]*\b   |  # Schedule references
    \bSection\s+\d+[A-Za-z]?\b   |  # IRC section references
    \bPub(?:lication)?\s+\d+\b      # Publication references
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _tokenize_query(query: str) -> list[str]:
    """Extract meaningful terms from the query for matching."""
    words = re.findall(r"[a-z0-9$%]+", query.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric values from text (dollar amounts, percentages, etc)."""
    # Dollar amounts
    dollars = set(re.findall(r"\$[\d,]+", text))
    # Percentages
    pcts = set(re.findall(r"\b\d+(?:\.\d+)?%", text))
    # Plain large numbers (1,000+)
    nums = set(re.findall(r"\b\d{1,3}(?:,\d{3})+\b", text))
    return dollars | pcts | nums


def rerank_chunks(
    query: str,
    chunks: list[RetrievedPassage],
    nav_pubs: list[str] | None = None,
    ontology_pubs: list[str] | None = None,
    max_chunks: int = 15,
    query_metadata: dict | None = None,
) -> list[RetrievedPassage]:
    """
    Re-score and re-order retrieved chunks for maximum synthesis quality.

    Args:
        query          : The original CPA query.
        chunks         : Retrieved chunks from the pipeline.
        nav_pubs       : Publications identified by Navigate (highest priority).
        ontology_pubs  : Publications added by ontology augment (secondary priority).
        max_chunks     : Maximum number of chunks to return.
        query_metadata : Optional dict with 'intent', 'tax_year', etc.

    Returns:
        Re-ordered list of chunks, capped at max_chunks, with the most
        relevant chunks first.
    """
    if not chunks:
        return []

    nav_set = set(nav_pubs or [])
    onto_set = set(ontology_pubs or [])
    query_terms = _tokenize_query(query)
    query_numbers = _extract_numbers(query)
    query_lower = query.lower()

    # Track which pubs have detail chunks (to demote summaries when details exist)
    pubs_with_details: set[str] = set()
    for c in chunks:
        if c.chunk_type == "detail":
            pubs_with_details.add(c.reference)

    scored: list[tuple[float, int, RetrievedPassage]] = []

    for idx, chunk in enumerate(chunks):
        text_lower = chunk.text.lower()

        # ── Component 1: Normalized original score (0-1) ──
        base_score = min(chunk.score, 1.0)

        # ── Component 2: Query term overlap (0-1) ──
        if query_terms:
            matched = sum(1 for t in query_terms if t in text_lower)
            term_score = matched / len(query_terms)
        else:
            term_score = 0.0

        # ── Component 3: Numeric entity match (0-1) ──
        if query_numbers:
            chunk_numbers = _extract_numbers(chunk.text)
            num_overlap = len(query_numbers & chunk_numbers)
            num_score = min(num_overlap / len(query_numbers), 1.0)
        else:
            # Boost chunks containing specific numbers/dollar amounts
            # (likely contains thresholds the user needs)
            entities = _TAX_ENTITIES.findall(chunk.text)
            num_score = min(len(entities) / 10.0, 0.5)

        # ── Component 4: Publication priority (0-1) ──
        if chunk.reference in nav_set:
            pub_score = 1.0
        elif chunk.reference in onto_set:
            pub_score = 0.6
        else:
            pub_score = 0.3

        # ── Component 5: Chunk type priority ──
        if chunk.chunk_type == "detail":
            type_score = 1.0
        elif chunk.chunk_type == "section_summary":
            # Demote section summaries if detail chunks from same pub exist
            type_score = 0.4 if chunk.reference in pubs_with_details else 0.8
        else:  # pub_summary
            type_score = 0.2 if chunk.reference in pubs_with_details else 0.6

        # ── Component 6: Section/chapter title match ──
        title_score = 0.0
        for field in [chunk.chapter, chunk.section]:
            if field:
                field_lower = field.lower()
                title_matches = sum(1 for t in query_terms if t in field_lower)
                if query_terms:
                    title_score = max(title_score, title_matches / len(query_terms))

        # ── Composite score (weighted) ──
        composite = (
            0.15 * base_score     +   # Original retrieval relevance
            0.30 * term_score     +   # Query keyword coverage
            0.15 * num_score      +   # Numeric/threshold entity match
            0.15 * pub_score      +   # Publication priority
            0.10 * type_score     +   # Chunk type appropriateness
            0.15 * title_score        # Section/chapter title relevance
        )

        scored.append((composite, idx, chunk))

    # Sort by composite score descending, break ties by original order
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Ensure pub diversity: don't let one pub dominate all top slots
    result: list[RetrievedPassage] = []
    pub_counts: Counter[str] = Counter()
    max_per_pub = max(3, max_chunks // 3)

    for composite, idx, chunk in scored:
        if len(result) >= max_chunks:
            break
        if pub_counts[chunk.reference] >= max_per_pub:
            continue
        result.append(chunk)
        pub_counts[chunk.reference] += 1

    # If we couldn't fill max_chunks due to diversity limits, add remaining
    if len(result) < max_chunks:
        result_ids = {id(c) for c in result}
        for composite, idx, chunk in scored:
            if len(result) >= max_chunks:
                break
            if id(chunk) not in result_ids:
                result.append(chunk)
                result_ids.add(id(chunk))

    logger.info(
        "Reranked %d→%d chunks, top pubs: %s",
        len(chunks), len(result),
        ", ".join(f"{p}({c})" for p, c in pub_counts.most_common(5)),
    )

    return result


def apply_positional_optimization(chunks: list[RetrievedPassage]) -> list[RetrievedPassage]:
    """
    Reorder chunks to combat the 'lost-in-the-middle' phenomenon.

    LLMs attend most strongly to content at the beginning and end of the
    context window. This function interleaves chunks so that the highest-
    ranked ones appear at positions 1, 2, N, N-1, N-2, etc.

    The input must already be sorted by relevance (most relevant first).

    Pattern for 10 chunks ranked 1-10:
      Position: [1, 3, 5, 7, 9, 10, 8, 6, 4, 2]
      → Top items at start AND end, weakest in the middle.
    """
    if len(chunks) <= 3:
        return chunks

    # Split into first-half (odd positions) and second-half (even positions)
    first_half = chunks[::2]     # indices 0, 2, 4, ... → positions 1, 3, 5, ...
    second_half = chunks[1::2]   # indices 1, 3, 5, ... → positions 2, 4, 6, ...

    # Reverse second_half so higher-ranked items go to the end
    second_half.reverse()

    return first_half + second_half
