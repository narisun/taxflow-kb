"""
taxkb/agent/compressor.py

Query-focused context compression for the CPA query agent.

After reranking, this module takes the top-N chunks and runs a fast
extraction pass using gpt-4o-mini. For each publication group, the
compressor asks the LLM to extract ONLY the facts relevant to the
specific query — stripping away irrelevant boilerplate, unrelated
subsections, and noise.

The compressed output replaces the raw chunk text, producing a much
cleaner context for the final synthesis model.

This is the "query-focused summarization" technique proven to improve
RAG answer quality by 20-30% (Nature 2025, FG-RAG 2025).
"""
from __future__ import annotations

import logging
import time
from itertools import groupby
from typing import Optional

from taxkb.agent.models import RetrievedPassage
from taxkb.adapters import OpenAICompletionClient

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are a precise tax fact extractor. Given a CPA's question and IRS publication \
excerpts, extract ONLY the facts from these excerpts that are directly relevant \
to answering the question.

RULES:
1. Extract specific dollar amounts, percentages, thresholds, limits, dates, and rules.
2. Preserve the exact numbers — never round or approximate.
3. CRITICAL: For every dollar amount or threshold, you MUST preserve:
   - WHO it applies to (Single, MFJ, HOH, etc.)
   - WHAT it is (phase-out threshold, income limit, deduction amount, credit amount, etc.)
   - WHAT HAPPENS at that threshold (reduces by X, disqualifies, etc.)
   Do NOT just list numbers — always include the filing status and the consequence.
4. Include the tax year each fact applies to.
5. Include form numbers, schedule references, and section references.
6. If an excerpt is not relevant to the question, skip it entirely.
7. Keep each extracted fact as a concise but COMPLETE sentence.
8. Prefix each fact with [N] matching the excerpt it came from.

Output format: One fact per line, each prefixed with [N]. If no relevant facts, \
output "NO_RELEVANT_FACTS".

GOOD example (preserves filing status + threshold + consequence):
[1] For tax year 2025, the senior deduction is $6,000 per qualifying individual age 65+.
[1] Single filers: phase-out begins at $150,000 MAGI; deduction reduces by 10% per $10,000 over.
[1] MFJ filers: phase-out begins at $300,000 MAGI; deduction reduces by 10% per $20,000 over.
[3] Married filing jointly couples can each claim $6,000, for a maximum of $12,000.

BAD example (loses critical context — NEVER do this):
[1] The income thresholds mentioned include $150,000 and $300,000.
"""


def compress_contexts(
    query: str,
    chunks: list[RetrievedPassage],
    api_key: str,
    completion_client: Optional[OpenAICompletionClient] = None,
    model: Optional[str] = None,
    query_metadata: Optional[dict] = None,
) -> list[RetrievedPassage]:
    """
    Run query-focused extraction on retrieved chunks, grouped by publication.

    For each publication group, sends the chunks + query to a fast LLM and
    replaces chunk text with extracted relevant facts. If compression
    can't extract facts for a pub group, the original chunks are kept
    (never dropped — the retriever already filtered for relevance).

    Args:
        query              : The CPA question.
        chunks             : Reranked chunks to compress.
        api_key            : OpenAI API key.
        completion_client  : Optional pre-built client.
        model              : Compression model (default: settings.compression_model).
        query_metadata     : Optional dict with intent/tax_year info.

    Returns:
        List of RetrievedPassage with compressed text. May be shorter than
        input if some chunks had no relevant facts.
    """
    model = model or "gpt-4o-mini"

    if not chunks:
        return []

    # Safety guardrail: don't compress when chunk count is low.
    # With fewer than 8 chunks, there's not enough noise to justify
    # the risk of losing critical details during compression.
    MIN_CHUNKS_FOR_COMPRESSION = 8
    if len(chunks) < MIN_CHUNKS_FOR_COMPRESSION:
        logger.info(
            "Skipping compression: only %d chunks (minimum %d)",
            len(chunks), MIN_CHUNKS_FOR_COMPRESSION,
        )
        return chunks

    t0 = time.perf_counter()

    # Group chunks by publication for batched extraction
    # Sort by reference first so groupby works correctly
    sorted_chunks = sorted(chunks, key=lambda c: c.reference)
    pub_groups: list[tuple[str, list[tuple[int, RetrievedPassage]]]] = []

    for pub_ref, group_iter in groupby(sorted_chunks, key=lambda c: c.reference):
        # Track original indices for citation numbering
        group_chunks = []
        for c in group_iter:
            orig_idx = chunks.index(c) + 1  # 1-based for [N] citations
            group_chunks.append((orig_idx, c))
        pub_groups.append((pub_ref, group_chunks))

    # Process each publication group
    compressed_results: list[RetrievedPassage] = []

    for pub_ref, indexed_chunks in pub_groups:
        if len(indexed_chunks) == 1:
            # Single chunk per pub — no compression needed, just pass through
            compressed_results.append(indexed_chunks[0][1])
            continue

        # Build the extraction prompt for this pub group
        excerpt_block_parts = []
        for orig_idx, chunk in indexed_chunks:
            header_parts = [f"IRS Pub {chunk.reference}"]
            if chunk.title:
                header_parts[0] += f" ({chunk.title})"
            if chunk.section:
                header_parts.append(f"Section: {chunk.section}")
            header = f"[{orig_idx}] " + " | ".join(header_parts)
            body = chunk.text.strip().replace("\n", " ")
            excerpt_block_parts.append(f"{header}\n{body}")

        excerpt_block = "\n\n".join(excerpt_block_parts)

        # Add query metadata if available
        meta_prefix = ""
        if query_metadata:
            parts = []
            if "intent" in query_metadata:
                parts.append(f"Query Intent: {query_metadata['intent']}")
            if "tax_year" in query_metadata:
                parts.append(f"Tax Year: {query_metadata['tax_year']}")
            if parts:
                meta_prefix = " | ".join(parts) + "\n"

        user_content = (
            f"{meta_prefix}Question: {query}\n\n"
            f"Excerpts from IRS Pub {pub_ref}:\n{excerpt_block}\n\n"
            f"Extract only the facts relevant to answering the question above."
        )

        try:
            if completion_client:
                extracted, _, _ = completion_client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": _EXTRACTION_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.0,
                    max_tokens=900,
                )
            else:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _EXTRACTION_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.0,
                    max_tokens=900,
                )
                extracted = response.choices[0].message.content or ""

            if "NO_RELEVANT_FACTS" in extracted:
                # NEVER drop a pub group — the retriever already filtered for
                # relevance. If compression can't extract facts, keep the
                # original chunks so the synthesis model can try.
                logger.debug(
                    "Compression: Pub %s — no extracted facts, keeping originals",
                    pub_ref,
                )
                for _, chunk in indexed_chunks:
                    compressed_results.append(chunk)
                continue

            # Create a single compressed context for this pub group
            # Use the highest-scoring chunk as the template
            best_chunk = max(indexed_chunks, key=lambda x: x[1].score)
            compressed_ctx = RetrievedPassage(
                layer=best_chunk[1].layer,
                source_type=best_chunk[1].source_type,
                reference=pub_ref,
                title=best_chunk[1].title,
                text=extracted.strip(),
                score=best_chunk[1].score,
                page=best_chunk[1].page,
                chunk_id=best_chunk[1].chunk_id,
                chapter=best_chunk[1].chapter,
                section="(compressed extract)",
                retrieval_method="compressed",
                chunk_type=best_chunk[1].chunk_type,
            )
            compressed_results.append(compressed_ctx)

        except Exception as exc:
            logger.warning(
                "Compression failed for Pub %s: %s — using uncompressed",
                pub_ref, exc,
            )
            # Fall back to uncompressed chunks
            for _, chunk in indexed_chunks:
                compressed_results.append(chunk)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "Context compression: %d chunks → %d compressed entries in %.0f ms",
        len(chunks), len(compressed_results), elapsed_ms,
    )

    # Re-sort by score so best pub group comes first
    compressed_results.sort(key=lambda c: c.score, reverse=True)

    return compressed_results
