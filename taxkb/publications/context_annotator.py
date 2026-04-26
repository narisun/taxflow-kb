"""
taxkb/layer3/context_annotator.py

LLM-based contextual chunk annotation (Anthropic's "Contextual Retrieval" technique).

At ingestion time, generates a concise context sentence for each chunk that
explains what the chunk covers, which publication/section it belongs to, and
what key facts it contains. This annotation is:

  1. Prepended to the chunk text BEFORE embedding → better vector search
  2. Stored in a dedicated column → available to synthesis model at query time

The annotation gives each chunk the "situational awareness" it needs for both
retrieval and synthesis. A raw chunk saying "Section 3(d)(2) provides that..."
becomes: "This chunk from IRS Pub 1-A (OBBBA Guide) discusses the vehicle
interest deduction phase-out thresholds for Single ($150,000) and Joint
($300,000) filers under the One Big Beautiful Bill Act."

This technique has been shown to improve retrieval quality by 20-67% and
reduce retrieval failures by 50% (Anthropic Contextual Retrieval, 2024).

Usage:
    from taxkb.publications.context_annotator import annotate_chunks
    annotated = annotate_chunks(chunks, pub_title="Your Federal Income Tax")
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from taxkb.config import get_settings
from taxkb.publications.models import PublicationChunk

logger = logging.getLogger(__name__)

# ── Annotation prompt ────────────────────────────────────────────────────────

_ANNOTATION_SYSTEM = """\
You are a tax document analyst. You will be given a chunk of text from an IRS \
publication, along with the publication title, chapter, and section.

Your task: Write a SINGLE concise context sentence (30-60 words) that:
1. Names the IRS publication number and title
2. Identifies the specific tax topic covered
3. Mentions any specific dollar amounts, thresholds, percentages, or limits
4. Identifies the tax year if mentioned
5. Notes if this is an OBBBA (One Big Beautiful Bill Act) provision or change

Write ONLY the context sentence, nothing else. Do not repeat the chunk text.

GOOD examples:
- "This chunk from IRS Pub 501 (Dependents, Standard Deduction) covers the 2025 standard deduction amounts: $15,000 for Single, $30,000 for MFJ, and $22,500 for HOH, including the OBBBA increase."
- "This chunk from IRS Pub 1-A (OBBBA Tax Guide) describes the overtime income deduction phase-out: begins at $150,000 MAGI for Single filers and $300,000 for MFJ, with the deduction capped at $12,500/$25,000."
- "This chunk from IRS Pub 17 (Your Federal Income Tax) explains the SALT deduction cap increase to $40,000 under OBBBA, with phase-out beginning at $500,000 MAGI."
- "This chunk from IRS Pub 596 (Earned Income Credit) contains the EIC income limit table for 2025: $18,591 with no children to $59,899 with 3+ children for Single filers."

BAD examples (too vague — NEVER do this):
- "This chunk discusses tax deductions."
- "This chunk from an IRS publication covers income thresholds."
"""

_ANNOTATION_USER_TEMPLATE = """\
Publication: IRS Pub {pub_number} — {pub_title}
Tax Year: {tax_year}
Chapter: {chapter}
Section: {section}

Chunk text:
{text}
"""


def annotate_chunks(
    chunks: list[PublicationChunk],
    pub_title: str = "",
    api_key: Optional[str] = None,
    completion_client=None,
    model: Optional[str] = None,
    batch_size: int = 20,
) -> list[PublicationChunk]:
    """
    Generate LLM context annotations for a batch of chunks.

    For each chunk, calls a fast LLM to produce a context sentence that is
    stored in `chunk.context_annotation`. This annotation will be:
    - Prepended to chunk text before embedding (in enrich_for_embedding)
    - Available to the synthesis model at query time

    Args:
        chunks         : List of PublicationChunk objects to annotate.
        pub_title      : Human-readable publication title (e.g., "Your Federal Income Tax").
        api_key        : OpenAI API key (uses env/config if not provided).
        completion_client : Optional pre-built OpenAICompletionClient.
        model          : Model to use for annotation (default: gpt-4o-mini — fast & cheap).
        batch_size     : Number of chunks per batch call (uses multi-message batching).

    Returns:
        Same list of chunks with `context_annotation` field populated.
    """
    settings = get_settings()
    model = model or "gpt-4o-mini"  # Fast model — annotation doesn't need gpt-4o

    if not chunks:
        return chunks

    t0 = time.perf_counter()
    annotated_count = 0
    skipped_count = 0

    # Skip chunks that already have annotations
    pending = [c for c in chunks if not getattr(c, "context_annotation", None)]
    if not pending:
        logger.info("All %d chunks already annotated — skipping.", len(chunks))
        return chunks

    logger.info(
        "Annotating %d chunks with %s for Pub %s (%s)…",
        len(pending), model, pending[0].pub_number, pub_title,
    )

    # Process in batches to respect rate limits
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]

        for chunk in batch:
            # Build the user prompt with full context
            user_msg = _ANNOTATION_USER_TEMPLATE.format(
                pub_number=chunk.pub_number,
                pub_title=pub_title or f"Publication {chunk.pub_number}",
                tax_year=chunk.tax_year,
                chapter=chunk.chapter_title or "(unknown chapter)",
                section=chunk.section_title or "(unknown section)",
                text=chunk.text[:1500],  # Cap text to avoid token bloat
            )

            try:
                if completion_client:
                    annotation, _, _ = completion_client.complete(
                        model=model,
                        messages=[
                            {"role": "system", "content": _ANNOTATION_SYSTEM},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.0,
                        max_tokens=150,
                    )
                else:
                    from openai import OpenAI
                    from taxkb.config import get_settings
                    resolved_key = api_key or get_settings().openai_api_key.get_secret_value()
                    client = OpenAI(api_key=resolved_key)
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": _ANNOTATION_SYSTEM},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.0,
                        max_tokens=150,
                    )
                    annotation = response.choices[0].message.content or ""

                # Store annotation on the chunk object
                chunk.context_annotation = annotation.strip()
                annotated_count += 1

            except Exception as exc:
                logger.warning(
                    "Annotation failed for chunk %s: %s — using fallback",
                    chunk.chunk_id, exc,
                )
                # Fallback: generate a rule-based annotation
                chunk.context_annotation = _fallback_annotation(chunk, pub_title)
                skipped_count += 1

        logger.info(
            "  Annotated %d/%d chunks…",
            annotated_count + skipped_count, len(pending),
        )

    elapsed = time.perf_counter() - t0
    logger.info(
        "Annotation complete: %d LLM-annotated, %d fallback, %.1f seconds",
        annotated_count, skipped_count, elapsed,
    )

    return chunks


def _fallback_annotation(chunk: PublicationChunk, pub_title: str = "") -> str:
    """
    Generate a rule-based annotation when LLM annotation fails.

    Uses available metadata to construct a reasonable context sentence.
    Not as good as LLM annotation but much better than nothing.
    """
    parts = [f"This chunk from IRS Pub {chunk.pub_number}"]
    if pub_title:
        parts[0] += f" ({pub_title})"

    if chunk.chapter_title:
        parts.append(f"chapter '{chunk.chapter_title}'")
    if chunk.section_title:
        parts.append(f"section '{chunk.section_title}'")

    parts.append(f"for tax year {chunk.tax_year}")

    # Check for OBBBA content
    text_lower = chunk.text.lower()
    if "obbba" in text_lower or "one big beautiful" in text_lower:
        parts.append("— covers OBBBA (One Big Beautiful Bill Act) provisions")

    # Check for key tax entities
    import re
    dollars = re.findall(r"\$[\d,]+(?:\.\d+)?", chunk.text)
    if dollars:
        parts.append(f"— mentions amounts: {', '.join(dollars[:5])}")

    return " ".join(parts) + "."


def annotate_single_chunk(
    chunk: PublicationChunk,
    pub_title: str = "",
    completion_client=None,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Annotate a single chunk (for use during incremental updates).

    Returns the annotation string (does not modify the chunk object).
    """
    user_msg = _ANNOTATION_USER_TEMPLATE.format(
        pub_number=chunk.pub_number,
        pub_title=pub_title or f"Publication {chunk.pub_number}",
        tax_year=chunk.tax_year,
        chapter=chunk.chapter_title or "(unknown chapter)",
        section=chunk.section_title or "(unknown section)",
        text=chunk.text[:1500],
    )

    try:
        if completion_client:
            annotation, _, _ = completion_client.complete(
                model=model,
                messages=[
                    {"role": "system", "content": _ANNOTATION_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=150,
            )
            return annotation.strip()
    except Exception:
        pass

    return _fallback_annotation(chunk, pub_title)
