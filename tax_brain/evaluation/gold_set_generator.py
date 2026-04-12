"""
tax_brain/layer5/gold_set_generator.py

Generates gold set Q&A pairs from ingested IRS publication chunks.

Strategy:
  1. Sample representative chunks from each publication (spread across pages
     and sections — not just from page 1).
  2. For each chunk, call GPT-4o to draft 1–2 CPA-realistic Q&A pairs grounded
     entirely in that chunk's text.
  3. Filter out low-quality drafts (too short, no specific answer, duplicates).
  4. Return GoldSetEntry objects tagged as created_by="generated" so a CPA
     knows to review them before they are treated as authoritative.

The generator deliberately uses GPT-4o (not gpt-4o-mini) because the quality
of the seed Q&A pairs directly determines the reliability of all downstream
evaluation metrics.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from tax_brain.evaluation.models import GoldSetEntry, GoldSet

logger = logging.getLogger(__name__)

# ── Sampling parameters ───────────────────────────────────────────────────────

# How many chunks to sample per publication when generating a gold set.
# Larger sample = more diverse Q&A pairs but more API cost.
DEFAULT_CHUNKS_PER_PUB = 15

# Chunks shorter than this are skipped (headers, TOC lines, stubs).
MIN_CHUNK_CHARS = 200

# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior CPA creating evaluation questions for an IRS tax knowledge base.
Your job is to read an excerpt from an IRS publication and write realistic Q&A pairs
that could be used to test whether an AI tax assistant retrieves and answers correctly.

Rules:
1. Each question must be answerable SOLELY from the provided excerpt — no outside knowledge.
2. The ground truth answer must be specific and verifiable (amounts, percentages, limits,
   conditions). Avoid vague answers like "it depends" or "see the publication."
3. Write as a CPA would ask, using precise tax terminology.
4. Vary difficulty: some questions should be direct lookups (simple), others should require
   synthesizing two or three facts from within the excerpt (medium or complex).
5. Return ONLY valid JSON — no markdown, no preamble, no explanation.
"""

_USER_PROMPT = """\
IRS Publication {pub_number} — {pub_title}
Page: {page}
Chapter: {chapter}
Section: {section}

Excerpt:
\"\"\"
{text}
\"\"\"

Generate {n_pairs} question-answer pair(s) from this excerpt at difficulty level: {difficulty}

Difficulty guidance:
  simple  — direct factual lookup of a single number, limit, or condition from the excerpt
  medium  — requires combining 2–3 related facts or conditions stated in the excerpt
  complex — requires multi-step reasoning, applying a rule to a specific scenario, or
            understanding an exception or edge case described in the excerpt

The "difficulty" field in your response MUST be exactly "{difficulty}".

Return a JSON array (even if n=1):
[
  {{
    "question": "...",
    "ground_truth": "...",
    "difficulty": "{difficulty}",
    "topic_tags": ["tag1", "tag2"]
  }}
]
"""

# Difficulty levels rotated across chunks so every publication gets even coverage
_DIFFICULTY_CYCLE = ["simple", "medium", "complex"]

# ── Chunk sampling from the DB ────────────────────────────────────────────────

@dataclass
class SampledChunk:
    chunk_id          : str
    pub_number        : str
    pub_title         : str
    text              : str
    page_start        : int
    chapter_title     : str
    section_title     : str
    token_count       : int
    # Adjacent chunk IDs (from the same pub, ordered by page/chunk_index).
    # Used to expand gold_chunk_ids so the retrieval metric isn't too strict.
    adjacent_chunk_ids: list[str] = None

    def __post_init__(self):
        if self.adjacent_chunk_ids is None:
            self.adjacent_chunk_ids = []


def _sample_chunks_for_pub(
    store,
    pub_number        : str,
    n                 : int,
    min_token_count   : int = 80,
    seed              : int = 42,
    adjacent_window   : int = 1,   # how many neighbors on each side to tag as gold
) -> list[SampledChunk]:
    """
    Sample n representative chunks from a single publication.

    Uses stratified sampling: divides the publication's pages into n buckets
    and picks one chunk from each bucket, so we get coverage across the whole
    document rather than clustering in a single section.

    Also populates adjacent_chunk_ids with the chunk_ids immediately before and
    after each sampled chunk, so the retrieval evaluator can use a soft match
    (finding an adjacent chunk counts as a hit, since the answer content often
    spans chunk boundaries).
    """
    with store._cursor() as cur:
        # Fetch ALL chunks for this pub ordered by page/chunk_index.
        # We need the full ordered list so we can look up neighbours.
        cur.execute(
            """
            SELECT c.chunk_id, c.pub_number, p.pub_title,
                   c.text, c.page_start, c.chapter_title, c.section_title,
                   c.token_count
            FROM irs_kb.publication_chunks c
            JOIN irs_kb.publications p ON p.pub_id = c.pub_id
            WHERE c.pub_number = %s
              AND c.token_count >= %s
              AND c.embedding IS NOT NULL
            ORDER BY c.page_start, c.chunk_index
            """,
            (pub_number, min_token_count),
        )
        rows = cur.fetchall()

    if not rows:
        logger.warning("No eligible chunks found for pub %s", pub_number)
        return []

    # Build a lookup: chunk_id → row index in the ordered list
    all_chunk_ids = [str(r[0]) for r in rows]
    id_to_idx     = {cid: i for i, cid in enumerate(all_chunk_ids)}

    # Stratified sample: divide into n buckets, pick one from each
    rng    = random.Random(seed)
    bucket_size = max(1, len(rows) // n)
    sampled: list[SampledChunk] = []

    for bucket_start in range(0, len(rows), bucket_size):
        bucket = rows[bucket_start : bucket_start + bucket_size]
        row    = rng.choice(bucket)

        sampled_id  = str(row[0])
        sampled_idx = id_to_idx[sampled_id]

        # Collect adjacent chunk IDs within the window (excluding the sampled chunk itself)
        adj_ids: list[str] = []
        for offset in range(-adjacent_window, adjacent_window + 1):
            nb_idx = sampled_idx + offset
            if offset != 0 and 0 <= nb_idx < len(all_chunk_ids):
                adj_ids.append(all_chunk_ids[nb_idx])

        sampled.append(SampledChunk(
            chunk_id          = sampled_id,
            pub_number        = row[1],
            pub_title         = row[2],
            text              = row[3],
            page_start        = row[4] or 0,
            chapter_title     = row[5] or "",
            section_title     = row[6] or "",
            token_count       = row[7] or 0,
            adjacent_chunk_ids= adj_ids,
        ))
        if len(sampled) >= n:
            break

    logger.debug(
        "Sampled %d/%d chunks for pub %s (from %d eligible)",
        len(sampled), n, pub_number, len(rows),
    )
    return sampled


# ── LLM Q&A generation ────────────────────────────────────────────────────────

def _generate_pairs_for_chunk(
    chunk             : SampledChunk,
    api_key           : str,
    model             : str,
    n_pairs           : int,
    tax_year          : int,
    target_difficulty : str = "medium",
) -> list[GoldSetEntry]:
    """Call the LLM to draft Q&A pairs for one chunk, return GoldSetEntries."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = _USER_PROMPT.format(
        pub_number = chunk.pub_number,
        pub_title  = chunk.pub_title,
        page       = chunk.page_start or "unknown",
        chapter    = chunk.chapter_title or "—",
        section    = chunk.section_title or "—",
        difficulty = target_difficulty,
        text       = chunk.text.strip()[:2000],  # cap to ~500 tokens
        n_pairs    = n_pairs,
    )

    # GPT-5.x and o-series models use max_completion_tokens; older models use max_tokens.
    _NEW_TOKEN_PARAM_PREFIXES = ("gpt-5", "o1", "o3", "o4")
    token_kwarg = (
        {"max_completion_tokens": 1024}
        if any(model.startswith(p) for p in _NEW_TOKEN_PARAM_PREFIXES)
        else {"max_tokens": 1024}
    )

    try:
        response = client.chat.completions.create(
            model       = model,
            messages    = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature = 0.4,   # some creativity, mostly grounded
            **token_kwarg,
            # NOTE: response_format="json_object" omitted — GPT-5.x sometimes returns
            # the array unwrapped (not valid json_object mode) and some model versions
            # don't support the parameter. We parse raw text instead.
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error("LLM call failed for chunk %s: %s", chunk.chunk_id, exc)
        return []

    logger.info("Raw LLM response for chunk %s (first 300 chars): %s",
                chunk.chunk_id, raw[:300].replace("\n", " "))

    if not raw.strip():
        logger.warning("Empty response for chunk %s", chunk.chunk_id)
        return []

    # ── Robust JSON extraction ────────────────────────────────────────────────
    # GPT-5.x may return:
    #   (a) A bare JSON array:  [{"question":..., "ground_truth":...}, ...]
    #   (b) A JSON object with a list value:  {"pairs": [...]}
    #   (c) A single JSON object (when n_pairs=1):  {"question":..., "ground_truth":...}
    #   (d) Markdown-fenced JSON:  ```json\n[...]\n```

    # Strip markdown code fences if present
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # Try to find the first JSON array or object using bracket search
    def _extract_json(text: str):
        """Try to parse the first complete JSON structure from text."""
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            if start == -1:
                continue
            # Walk to find matching close bracket
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i+1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break  # try next structure type
        return None

    parsed = _extract_json(stripped)
    if parsed is None:
        logger.warning("Could not extract JSON from response for chunk %s. Raw: %r",
                       chunk.chunk_id, raw[:200])
        return []

    # Normalise to list of items
    if isinstance(parsed, dict):
        # Case (b): object with a list value
        items_list = None
        for key in ("pairs", "questions", "qa_pairs", "items", "results",
                    "question_answer_pairs", "qa", "answers"):
            if key in parsed and isinstance(parsed[key], list):
                items_list = parsed[key]
                break
        if items_list is None:
            # Case (c): single Q&A object — wrap in list
            if "question" in parsed and "ground_truth" in parsed:
                items_list = [parsed]
            else:
                # Try first list value
                for v in parsed.values():
                    if isinstance(v, list):
                        items_list = v
                        break
        if items_list is None:
            logger.warning("Cannot normalise JSON dict for chunk %s. Keys: %s",
                           chunk.chunk_id, list(parsed.keys()))
            return []
        parsed = items_list
    elif not isinstance(parsed, list):
        logger.warning("Unexpected JSON type %s for chunk %s", type(parsed), chunk.chunk_id)
        return []

    logger.info("Parsed %d item(s) from LLM for chunk %s", len(parsed), chunk.chunk_id)

    entries: list[GoldSetEntry] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        question     = str(item.get("question", "")).strip()
        ground_truth = str(item.get("ground_truth", "")).strip()
        difficulty   = str(item.get("difficulty", "simple")).strip()
        topic_tags   = item.get("topic_tags", [])

        # Quality filters
        if len(question) < 20:
            logger.debug("Skipping short question (%d chars): %r", len(question), question[:60])
            continue
        if len(ground_truth) < 20:
            logger.debug("Skipping short answer (%d chars): %r", len(ground_truth), ground_truth[:60])
            continue
        if difficulty not in ("simple", "medium", "complex"):
            difficulty = target_difficulty  # honour the target we requested

        entries.append(GoldSetEntry(
            question       = question,
            ground_truth   = ground_truth,
            expected_pub   = chunk.pub_number,
            # Primary gold chunk + adjacent chunks (within ±1 positions).
            # Retrieval counts as a hit if ANY of these IDs is in top-k.
            gold_chunk_ids = [chunk.chunk_id] + chunk.adjacent_chunk_ids,
            tax_year       = tax_year,
            difficulty     = difficulty,
            topic_tags     = topic_tags if isinstance(topic_tags, list) else [],
            created_by     = "generated",
        ))

    logger.info("Accepted %d/%d entries for chunk %s", len(entries), len(parsed), chunk.chunk_id)
    return entries


# ── Main generator ────────────────────────────────────────────────────────────

def generate_gold_set(
    store            ,                  # PublicationStore (context manager not needed; pass connected)
    api_key          : str,
    pub_numbers      : Optional[list[str]] = None,
    chunks_per_pub   : int  = DEFAULT_CHUNKS_PER_PUB,
    pairs_per_chunk  : int  = 1,
    tax_year         : int  = 2025,
    model            : str  = "gpt-5.4",  # use highest-quality model for gold set
    existing         : Optional[GoldSet] = None,
    rate_limit_delay : float = 0.5,       # seconds between API calls
) -> GoldSet:
    """
    Generate a gold set by sampling chunks from the DB and drafting Q&A pairs.

    Args:
        store           : Connected PublicationStore (psycopg2 connection open).
        api_key         : OpenAI API key.
        pub_numbers     : Publications to sample from. Defaults to all ingested.
        chunks_per_pub  : Chunks to sample per publication.
        pairs_per_chunk : Q&A pairs to request per chunk (1 recommended to stay grounded).
        tax_year        : Tax year to tag entries with.
        model           : OpenAI model for generation (gpt-4o recommended).
        existing        : If provided, new entries are appended to this GoldSet.
        rate_limit_delay: Pause between API calls to avoid 429 errors.

    Returns:
        GoldSet with generated (unverified) entries.
    """
    # Resolve which publications to generate for
    if pub_numbers is None:
        with store._cursor() as cur:
            cur.execute("SELECT pub_number FROM irs_kb.publications ORDER BY pub_number")
            pub_numbers = [row[0] for row in cur.fetchall()]
    logger.info(
        "Generating gold set: pubs=%s, chunks_per_pub=%d, pairs_per_chunk=%d",
        pub_numbers, chunks_per_pub, pairs_per_chunk,
    )

    gold_set = existing or GoldSet()
    total_generated = 0

    for pub_number in pub_numbers:
        logger.info("  → Pub %s …", pub_number)
        chunks = _sample_chunks_for_pub(store, pub_number, n=chunks_per_pub)

        for chunk_idx, chunk in enumerate(chunks):
            # Cycle difficulties evenly: simple → medium → complex → simple → …
            # This guarantees all three tiers appear regardless of LLM preference.
            target_diff = _DIFFICULTY_CYCLE[chunk_idx % len(_DIFFICULTY_CYCLE)]

            entries = _generate_pairs_for_chunk(
                chunk, api_key, model,
                n_pairs           = pairs_per_chunk,
                tax_year          = tax_year,
                target_difficulty = target_diff,
            )
            gold_set.entries.extend(entries)
            total_generated += len(entries)

            if rate_limit_delay:
                time.sleep(rate_limit_delay)

        logger.info(
            "  ✓ Pub %s: %d entries generated so far", pub_number, total_generated
        )

    logger.info(
        "Gold set generation complete: %d entries across %d publications",
        total_generated, len(pub_numbers),
    )
    return gold_set
