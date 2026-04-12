"""
tax_brain/layer5/gold_set_patcher.py

Patches an existing gold set in-place by expanding each entry's gold_chunk_ids
to include adjacent chunks (±window positions in page/chunk_index order).

This retrofits the "adjacent chunk" improvement onto an already-generated gold
set WITHOUT re-calling the LLM, saving API cost and time.

Usage (via CLI):
  python cli.py patch-gold-set \
    --gold-set data/eval/gold_set_full.json \
    --pg-dsn "postgresql://..." \
    --window 1          # ±1 adjacent chunk (default)
    --out data/eval/gold_set_full_patched.json   # or omit to overwrite in-place
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def patch_adjacent_chunks(
    gold_set,               # GoldSet instance
    store,                  # PublicationStore (connected)
    window    : int = 1,    # how many neighbours on each side to include
) -> tuple[int, int]:
    """
    For each GoldSetEntry, look up the primary chunk's neighbours in the DB
    and append them to gold_chunk_ids (without duplicates).

    Returns (n_entries_patched, n_already_had_adjacent).
    """
    # Build a per-pub ordered chunk list cache to avoid N queries
    _pub_chunk_cache: dict[str, list[str]] = {}

    def _get_ordered_chunk_ids(pub_number: str) -> list[str]:
        if pub_number in _pub_chunk_cache:
            return _pub_chunk_cache[pub_number]
        with store._cursor() as cur:
            cur.execute(
                """
                SELECT c.chunk_id
                FROM irs_kb.publication_chunks c
                WHERE c.pub_number = %s
                  AND c.embedding IS NOT NULL
                ORDER BY c.page_start, c.chunk_index
                """,
                (pub_number,),
            )
            ids = [str(row[0]) for row in cur.fetchall()]
        _pub_chunk_cache[pub_number] = ids
        return ids

    n_patched = 0
    n_already = 0

    for entry in gold_set.entries:
        if not entry.gold_chunk_ids:
            continue

        primary_id = entry.gold_chunk_ids[0]

        # If already has >1 chunk ID, it was generated with the new generator
        if len(entry.gold_chunk_ids) > 1:
            n_already += 1
            continue

        # Look up this chunk's position in the ordered list
        ordered = _get_ordered_chunk_ids(entry.expected_pub)
        if not ordered:
            logger.warning("No chunks found for pub %s", entry.expected_pub)
            continue

        try:
            idx = ordered.index(primary_id)
        except ValueError:
            logger.warning(
                "Primary chunk %s not found in ordered list for pub %s",
                primary_id, entry.expected_pub,
            )
            continue

        # Collect neighbours within the window
        adjacent: list[str] = []
        for offset in range(-window, window + 1):
            if offset == 0:
                continue
            nb_idx = idx + offset
            if 0 <= nb_idx < len(ordered):
                adjacent.append(ordered[nb_idx])

        # Update entry's gold_chunk_ids = [primary] + adjacent (no duplicates)
        existing = set(entry.gold_chunk_ids)
        new_ids  = entry.gold_chunk_ids.copy()
        for cid in adjacent:
            if cid not in existing:
                new_ids.append(cid)
                existing.add(cid)

        entry.gold_chunk_ids = new_ids
        n_patched += 1

    logger.info(
        "Patched %d entries with adjacent chunk IDs (window=±%d); "
        "%d entries already had multiple IDs.",
        n_patched, window, n_already,
    )
    return n_patched, n_already
