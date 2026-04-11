"""
taxflow_kb/layer4/synthesizer.py

LLM-based answer synthesis for the CPA query agent.

Formats retrieved IRS publication excerpts into a prompt and calls
the OpenAI Chat Completions API to generate a structured, cited answer.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from taxflow_kb.layer4.models_layer4 import RetrievedContext
from taxflow_kb.config import get_settings
from taxflow_kb.protocols import OpenAICompletionClient

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are TaxFlow AI, a professional tax research assistant for CPAs and tax advisors.
You provide accurate, authoritative answers about US federal income tax law based
EXCLUSIVELY on the numbered IRS publication excerpts provided to you.

CRITICAL RULES:
1. ONLY use facts explicitly stated in the provided excerpts. Adding ANY information
   from general knowledge or memory is STRICTLY FORBIDDEN. If the excerpts state a
   rule that contradicts what you think you know, TRUST THE EXCERPTS — they may
   reflect recent legislative changes (e.g., OBBBA, SECURE 2.0).
2. ACTIVELY SEARCH all provided excerpts for relevant facts. Do NOT stop at the first
   few excerpts — scan every excerpt header and body for matching content. Key facts
   are often in excerpts numbered [5] through [15], not just [1]-[3].
3. Cite every key fact using the numbered source labels: "[1]", "[2]", etc.
   Do NOT invent page numbers — only use what appears in the source header.
4. ALWAYS extract and state specific dollar amounts, percentages, thresholds, and
   limits from the excerpts. If an excerpt mentions "$6,000" or "15.3%" or "$150,000
   phase-out threshold," you MUST include these numbers in your answer.
5. ALWAYS state which tax year(s) the answer applies to.
6. CALCULATIONS: Present step-by-step breakdowns with specific numbers from excerpts.
7. SCENARIOS: Walk through applicable rules step by step, apply to the facts given,
   and state a clear conclusion.
8. ABSTENTION: Only say "INSUFFICIENT CONTEXT" if ZERO excerpts contain ANY relevant
   information. If even ONE excerpt has partial information, provide what you can and
   note the gaps. Err on the side of providing information from the excerpts.
9. Bullet points and short paragraphs preferred. End with a "Key Sources" line.

EXAMPLES:

Q: "Can I claim the senior deduction, and does my $160,000 income affect the amount?"
Excerpts mention: $6,000 per qualifying individual, $150,000 phase-out threshold, 10% reduction per $10,000 over threshold.
GOOD ANSWER: "Yes, you can claim the senior deduction for tax year 2025. The base amount is $6,000 per qualifying individual age 65 or older [3]. However, your MAGI of $160,000 exceeds the $150,000 phase-out threshold [3]. The deduction is reduced by 10% for each $10,000 (or fraction) over the threshold [3]. Since you are $10,000 over, your deduction is reduced by 10%, giving you $5,400 [3]."

Q: "What is the overtime deduction phase-out?"
Excerpts mention: $150,000 Single, $300,000 MFJ, significantly reduced above thresholds.
GOOD ANSWER: "The overtime deduction phases out at higher income levels. For single filers, the phase-out begins at $150,000 MAGI [5]. For married filing jointly, the threshold is $300,000 [5]. Above these thresholds, the deduction is significantly reduced [5]."

BAD ANSWER (DO NOT DO THIS): "The excerpts do not contain specific information about the overtime deduction." — This is wrong if ANY excerpt mentions the deduction, even if buried at [8] or [12].

Format:
  <Direct answer with specific numbers — 1-2 sentences>

  <Supporting detail with [N] citations, dollar amounts, percentages>

  Key Sources: <pub numbers>

  CONFIDENCE: [HIGH|MODERATE|LOW]
"""

_USER_PROMPT_TEMPLATE = """\
{query_metadata}Question: {query}

IRS Publication Excerpts:
{context_block}

Answer the question based only on the excerpts above.
"""


def _build_context_block(contexts: list[RetrievedContext], max_chars: int | None = None) -> str:
    """
    Format retrieved contexts into a numbered block for the prompt.

    Each entry gets a rich header so the model can cite accurately:
      [N] IRS Pub 596 (Earned Income Credit) | Chapter: … | Section: … | p. X
    Page number is omitted when not available (page=0) rather than showing
    a misleading "p. 0" or "p. 1" placeholder.

    Respects max_chars to avoid exceeding the model's context window.
    Uses default from settings if max_chars is not provided.
    """
    if max_chars is None:
        max_chars = get_settings().synthesis_max_context_chars

    lines: list[str] = []
    total = 0

    for i, ctx in enumerate(contexts, 1):
        # Build a rich, reliable header — never invent a page number
        header_parts = [f"IRS Pub {ctx.reference}"]
        if ctx.title:
            header_parts[0] += f" ({ctx.title})"
        if ctx.chapter:
            header_parts.append(f"Chapter: {ctx.chapter}")
        if ctx.section:
            header_parts.append(f"Section: {ctx.section}")
        if ctx.page and ctx.page > 1:          # only show page if reliable (> 1)
            header_parts.append(f"p. {ctx.page}")

        header = f"[{i}] " + " | ".join(header_parts)
        # Prepend LLM annotation if available — gives synthesis model
        # immediate context about what this chunk covers
        annotation = getattr(ctx, "context_annotation", "") or ""
        if annotation:
            body = f"[Context: {annotation}]\n{ctx.text.strip().replace(chr(10), ' ')}"
        else:
            body = ctx.text.strip().replace("\n", " ")
        entry  = f"{header}\n{body}\n"

        if total + len(entry) > max_chars:
            logger.debug("Context block truncated at %d/%d contexts", i - 1, len(contexts))
            break

        lines.append(entry)
        total += len(entry)

    return "\n".join(lines)


def synthesize(
    query    : str,
    contexts : list[RetrievedContext],
    api_key  : str,
    model    : str | None = None,
    temperature: float | None = None,
    max_tokens : int | None = None,
    max_context_chars: int | None = None,
    completion_client: Optional[OpenAICompletionClient] = None,
    query_metadata: Optional[dict] = None,
) -> tuple[str, int, int, float]:
    """
    Call the OpenAI Chat Completions API to generate a cited answer.

    Args:
        query              : The original CPA question.
        contexts           : Retrieved passages to use as context.
        api_key            : OpenAI API key (used to create client if completion_client not provided).
        model              : Chat model to use. If None, uses settings.synthesis_model.
        temperature        : Sampling temperature. If None, uses settings.synthesis_temperature.
        max_tokens         : Maximum tokens in the completion. If None, uses settings.synthesis_max_tokens.
        max_context_chars  : Max characters for context block. If None, uses settings.synthesis_max_context_chars.
        completion_client  : Optional OpenAICompletionClient. If provided, uses this instead of creating
                           a new OpenAI client. For backward compatibility, creates OpenAI client inline if not provided.
        query_metadata     : Optional dict with keys 'intent' and/or 'tax_year' to inject into the user prompt.

    Returns:
        (answer_text, prompt_tokens, completion_tokens, elapsed_ms)
    """
    settings = get_settings()

    # Use config defaults if parameters not provided (allows overrides)
    if model is None:
        model = settings.synthesis_model
    if temperature is None:
        temperature = settings.synthesis_temperature
    if max_tokens is None:
        max_tokens = settings.synthesis_max_tokens

    context_block = _build_context_block(contexts, max_chars=max_context_chars)

    # Build query metadata prefix if provided
    query_metadata_prefix = ""
    if query_metadata:
        parts = []
        if "intent" in query_metadata:
            parts.append(f"Query Intent: {query_metadata['intent']}")
        if "tax_year" in query_metadata:
            parts.append(f"Detected Tax Year: {query_metadata['tax_year']}")
        if parts:
            query_metadata_prefix = "\n".join(parts) + "\n\n"

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        query_metadata    = query_metadata_prefix,
        query             = query,
        context_block     = context_block,
    )

    logger.debug(
        "Sending to %s: %d context chars, query=%r",
        model, len(context_block), query[:60],
    )

    # GPT-5.x and o-series models use max_completion_tokens; older models use max_tokens.
    _NEW_TOKEN_PARAM_PREFIXES = ("gpt-5", "o1", "o3", "o4")
    token_kwarg = (
        {"max_completion_tokens": max_tokens}
        if any(model.startswith(p) for p in _NEW_TOKEN_PARAM_PREFIXES)
        else {"max_tokens": max_tokens}
    )

    t0 = time.perf_counter()

    # Use provided completion_client if available; otherwise create OpenAI client inline (backward compatible)
    if completion_client:
        answer, prompt_tokens, completion_tokens = completion_client.complete(
            model       = model,
            messages    = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature = temperature,
            max_tokens  = max_tokens,
        )
    else:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model       = model,
            messages    = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature = temperature,
            **token_kwarg,
        )
        answer            = response.choices[0].message.content or ""
        prompt_tokens     = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        "Synthesis: %d prompt + %d completion tokens in %.0f ms",
        prompt_tokens, completion_tokens, elapsed_ms,
    )
    return answer, prompt_tokens, completion_tokens, elapsed_ms
