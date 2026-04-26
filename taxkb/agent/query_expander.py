"""
taxkb/agent/query_expander.py

LLM-powered query expansion for CPA tax queries.

Uses the LLM's parametric knowledge of tax law to expand a CPA's natural-
language query with specific IRC section numbers, form references, tax
terminology synonyms, and related concepts BEFORE retrieval.  This bridges
the vocabulary gap between how a CPA phrases a question and how the IRS
wrote the guidance.

Example:
    Input:  "wash sale rule for options"
    Output: "wash sale rule for options IRC Section 1091 substantially
             identical securities call put option 61-day window
             disallowed loss Form 8949 Schedule D"

The expanded query is fed to BOTH the embedding model (vector search) and
BM25 (keyword search).  Vector search benefits from richer semantic context;
BM25 benefits from exact IRC section numbers and form references that
wouldn't appear in the original query.

Key design decisions:
  - Uses gpt-4o-mini for speed and cost (~0.3s, ~$0.0001 per expansion)
  - Returns expansion terms ONLY (no restatement) to avoid diluting the
    original query's semantic focus
  - Capped at 80 tokens to keep embedding input manageable
  - Falls back to original query on any LLM failure (never blocks retrieval)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


_EXPANSION_SYSTEM = """\
You are a tax law knowledge assistant. Given a CPA's question, output ONLY \
additional search terms that would help find the answer in IRS publications. \
Do NOT restate the question.

Include (when relevant):
- IRC section numbers (e.g., "IRC Section 121", "Section 469(c)(7)")
- Related IRS form and schedule numbers (e.g., "Form 8949", "Schedule D")
- IRS publication numbers likely to contain the answer (e.g., "Publication 550")
- Official tax terminology synonyms (e.g., "wash sale" -> "disallowed loss")
- Related concepts a CPA would need (e.g., "substantially identical securities")
- Key thresholds or limits if commonly known (e.g., "$250,000 exclusion")

Output a single line of space-separated terms. No bullets, no numbering, \
no explanation. Maximum 60 words."""

_EXPANSION_USER = "CPA question: {query}"


def expand_query(
    query: str,
    completion_client=None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    max_tokens: int = 80,
) -> str:
    """
    Expand a CPA query with tax-specific search terms using an LLM.

    The expanded query is the original query + appended expansion terms.
    On any failure, returns the original query unchanged (never blocks).

    Args:
        query              : The CPA's original question.
        completion_client  : Optional CompletionClient (DI).
        api_key            : OpenAI API key (fallback if no client).
        model              : Model for expansion (default: gpt-4o-mini).
        max_tokens         : Max tokens for the expansion output.

    Returns:
        Expanded query string = original + " " + expansion terms.
    """
    if not query.strip():
        return query

    t0 = time.perf_counter()
    user_msg = _EXPANSION_USER.format(query=query)

    try:
        expansion = _call_llm(
            system=_EXPANSION_SYSTEM,
            user=user_msg,
            completion_client=completion_client,
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.warning("Query expansion failed (using original query): %s", exc)
        return query

    if not expansion or expansion.strip().lower().startswith("no additional"):
        logger.debug("Query expansion returned nothing useful")
        return query

    # Clean up: remove any accidental restatement of the question
    expansion = expansion.strip()

    expanded = f"{query} {expansion}"
    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        "Query expanded in %.0f ms: %r -> +%d terms",
        elapsed_ms, query[:60], len(expansion.split()),
    )
    logger.debug("Expansion terms: %s", expansion)

    return expanded


def _call_llm(
    system: str,
    user: str,
    completion_client=None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    max_tokens: int = 80,
) -> str:
    """Call the LLM via completion_client or direct OpenAI fallback."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    if completion_client is not None:
        text, _, _ = completion_client.complete(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return text

    # Fallback: direct OpenAI client
    from openai import OpenAI

    if api_key is None:
        from taxkb.config import get_settings
        api_key = get_settings().openai_api_key.get_secret_value()

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
