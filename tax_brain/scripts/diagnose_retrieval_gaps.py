#!/usr/bin/env python3
"""
Diagnose why ingested publications aren't being retrieved.

Checks each stage of the TaxBrainRetriever pipeline for a set of
"problem" pubs that are in the DB but not appearing in retrieval results.

Stages tested:
  1. DB presence — are chunks actually in the DB for this pub?
  2. Summary coverage — does the pub have PUB_SUMMARY / SECTION_SUMMARY chunks?
  3. Vector similarity — does a targeted query find chunks from this pub?
  4. Navigate stage — does the summary-level search route to this pub?
  5. Drill stage — do detail chunks from this pub appear after drilling?
  6. Full pipeline — does the complete TaxBrainRetriever return this pub?

Usage:
    python scripts/diagnose_retrieval_gaps.py
    python scripts/diagnose_retrieval_gaps.py --pub 535
    python scripts/diagnose_retrieval_gaps.py --query "What business expenses are deductible?"
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import psycopg2
import psycopg2.extras

sys.path.insert(0, ".")

from tax_brain.config import get_settings
from tax_brain.publications.store import PublicationStore
from tax_brain.adapters import OpenAIEmbeddingClient


# ── Problem pubs: in DB but not retrieved in eval ──────────────────────────
PROBLEM_PUBS = {
    "535": [
        "What business expenses are deductible for tax purposes?",
        "What types of business expenses can I deduct on my Schedule C?",
        "Do I still have to amortize my research costs over 5 years?",
    ],
    "550": [
        "How are my dividends taxed?",
        "How is interest and dividend income reported?",
    ],
    "587": [
        "How much home office expense can I deduct?",
    ],
    "590a": [
        "Can I contribute to a traditional IRA, and is it deductible?",
        "What is the 2026 contribution limit for Trump Accounts?",
    ],
    "590b": [
        "What is my required minimum distribution (RMD) for this year?",
        "Can I convert my traditional IRA to a Roth IRA?",
    ],
    "596": [
        "What are the income limits for the 2025 Earned Income Credit?",
        "Can my college student be a qualifying child for EITC purposes?",
    ],
    "560": [
        "Can I contribute to a SEP IRA, and how much?",
        "What is the advantage of a SIMPLE IRA plan over a regular IRA?",
    ],
    "501": [
        "Can I still claim my child as a dependent if they are not a student?",
    ],
}


def diagnose_pub(pub: str, queries: list[str], conn, embed_client, settings):
    """Run full diagnostic on a single publication."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"\n{'='*76}")
    print(f"  PUB {pub} — DIAGNOSTIC")
    print(f"{'='*76}")

    # ── Stage 1: DB Presence ──────────────────────────────────────────
    cur.execute("""
        SELECT chunk_type, tax_year, COUNT(*) as cnt,
               AVG(LENGTH(text)) as avg_len
        FROM irs_kb.publication_chunks
        WHERE pub_number = %s
        GROUP BY chunk_type, tax_year
        ORDER BY chunk_type, tax_year
    """, (pub,))
    rows = cur.fetchall()
    total_chunks = sum(r["cnt"] for r in rows)
    print(f"\n  Stage 1 — DB Presence: {total_chunks} total chunks")
    if not rows:
        print(f"  ⚠ PUB {pub} HAS NO CHUNKS IN DB!")
        return
    for r in rows:
        print(f"    {r['chunk_type']:<20s}  year={r['tax_year']}  count={r['cnt']}  avg_len={r['avg_len']:.0f}")

    # ── Stage 2: Summary Coverage ─────────────────────────────────────
    cur.execute("""
        SELECT chunk_type, COUNT(*) as cnt, tax_year
        FROM irs_kb.publication_chunks
        WHERE pub_number = %s
          AND chunk_type IN ('PUB_SUMMARY', 'SECTION_SUMMARY')
        GROUP BY chunk_type, tax_year
        ORDER BY chunk_type, tax_year
    """, (pub,))
    summaries = cur.fetchall()
    has_summaries = len(summaries) > 0
    print(f"\n  Stage 2 — Summary Coverage: {'YES' if has_summaries else 'NO'}")
    if has_summaries:
        for r in summaries:
            print(f"    {r['chunk_type']:<20s}  year={r['tax_year']}  count={r['cnt']}")
    else:
        print(f"  ⚠ NO SUMMARY CHUNKS — hierarchical navigate will NOT route to this pub")
        print(f"    Retriever will only find this pub via flat/BM25 search")

    # ── Stage 3: Embedding Coverage ───────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as embedded
        FROM irs_kb.publication_chunks
        WHERE pub_number = %s
    """, (pub,))
    emb = cur.fetchone()
    embedded_pct = (emb["embedded"] / emb["total"] * 100) if emb["total"] else 0
    print(f"\n  Stage 3 — Embedding Coverage: {emb['embedded']}/{emb['total']} ({embedded_pct:.0f}%)")
    if embedded_pct < 100:
        print(f"  ⚠ {emb['total'] - emb['embedded']} chunks have NO embedding!")

    # ── Stage 4: Vector Similarity (direct query) ─────────────────────
    print(f"\n  Stage 4 — Vector Similarity (targeted queries)")
    for q in queries:
        print(f"\n    Query: \"{q[:70]}...\"")
        try:
            q_emb = embed_client.embed_query(q)
            emb_str = "[" + ",".join(f"{x:.8f}" for x in q_emb) + "]"

            # Search ALL pubs — see where this pub ranks
            cur.execute("""
                SELECT pub_number, chunk_type, section_title,
                       1 - (embedding <=> %s::vector) as similarity,
                       LEFT(text, 100) as snippet
                FROM irs_kb.publication_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 20
            """, (emb_str, emb_str))
            top_results = cur.fetchall()

            # Find our pub in results
            pub_ranks = [i+1 for i, r in enumerate(top_results) if r["pub_number"] == pub]
            other_pubs = list(dict.fromkeys(r["pub_number"] for r in top_results[:5]))

            if pub_ranks:
                print(f"    ✓ Pub {pub} found at rank(s): {pub_ranks}")
                for rank in pub_ranks[:3]:
                    r = top_results[rank-1]
                    print(f"      rank {rank}: sim={r['similarity']:.4f} type={r['chunk_type']} "
                          f"section=\"{(r['section_title'] or '')[:40]}\"")
            else:
                print(f"    ✗ Pub {pub} NOT in top 20")
                print(f"    Top 5 pubs: {other_pubs}")
                # Check similarity for the best match from this pub
                cur.execute("""
                    SELECT 1 - (embedding <=> %s::vector) as similarity,
                           chunk_type, section_title, LEFT(text, 80) as snippet
                    FROM irs_kb.publication_chunks
                    WHERE pub_number = %s AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT 3
                """, (emb_str, pub, emb_str))
                pub_best = cur.fetchall()
                if pub_best:
                    print(f"    Best match from Pub {pub}:")
                    for r in pub_best:
                        print(f"      sim={r['similarity']:.4f} type={r['chunk_type']} "
                              f"section=\"{(r['section_title'] or '')[:40]}\"")
                        print(f"      \"{r['snippet']}...\"")

            # Also search with pub filter
            cur.execute("""
                SELECT chunk_type, section_title,
                       1 - (embedding <=> %s::vector) as similarity,
                       LEFT(text, 100) as snippet
                FROM irs_kb.publication_chunks
                WHERE pub_number = %s AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 5
            """, (emb_str, pub, emb_str))
            filtered = cur.fetchall()
            if filtered:
                best_sim = filtered[0]["similarity"]
                print(f"    Pub-filtered best sim: {best_sim:.4f} ({filtered[0]['chunk_type']})")

        except Exception as exc:
            print(f"    ERROR: {exc}")

    # ── Stage 5: Navigate stage simulation ────────────────────────────
    if has_summaries:
        print(f"\n  Stage 5 — Navigate Stage (summary search)")
        for q in queries[:2]:
            try:
                q_emb = embed_client.embed_query(q)
                emb_str = "[" + ",".join(f"{x:.8f}" for x in q_emb) + "]"

                cur.execute("""
                    SELECT pub_number, chunk_type, section_title,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM irs_kb.publication_chunks
                    WHERE embedding IS NOT NULL
                      AND chunk_type IN ('PUB_SUMMARY', 'SECTION_SUMMARY')
                    ORDER BY embedding <=> %s::vector
                    LIMIT 10
                """, (emb_str, emb_str))
                nav_results = cur.fetchall()
                nav_pubs = list(dict.fromkeys(r["pub_number"] for r in nav_results))
                pub_in_nav = pub in nav_pubs

                print(f"    Query: \"{q[:50]}...\"")
                print(f"    Nav pubs (top 10 summaries): {nav_pubs}")
                print(f"    Pub {pub} in nav: {'✓ YES' if pub_in_nav else '✗ NO'}")
                if pub_in_nav:
                    rank = nav_pubs.index(pub) + 1
                    print(f"    Rank: {rank}")
            except Exception as exc:
                print(f"    ERROR: {exc}")
    else:
        print(f"\n  Stage 5 — SKIPPED (no summary chunks)")

    # ── Stage 6: Full pipeline test ───────────────────────────────────
    print(f"\n  Stage 6 — Full Pipeline (TaxBrainRetriever)")
    try:
        from tax_brain.factories import create_agent
        agent = create_agent()
        for q in queries[:2]:
            result = agent.query(q, synthesize=False)
            retrieved_pubs = list(dict.fromkeys(ctx.reference for ctx in result.contexts))
            pub_found = pub in retrieved_pubs
            print(f"    Query: \"{q[:50]}...\"")
            print(f"    Mode: {result.retrieval_mode}  Contexts: {len(result.contexts)}")
            print(f"    Retrieved pubs: {retrieved_pubs}")
            print(f"    Nav pubs: {result.nav_pubs}")
            print(f"    Ontology pubs: {result.ontology_pubs}")
            print(f"    Pub {pub}: {'✓ FOUND' if pub_found else '✗ MISSING'}")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Diagnose retrieval gaps")
    parser.add_argument("--pub", help="Diagnose a single pub")
    parser.add_argument("--query", help="Test a specific query against all pubs")
    args = parser.parse_args()

    settings = get_settings()
    conn = psycopg2.connect(settings.pg_dsn)
    embed_client = OpenAIEmbeddingClient(api_key=os.environ.get("OPENAI_API_KEY", ""))

    if args.pub:
        queries = PROBLEM_PUBS.get(args.pub, [f"Information from Publication {args.pub}"])
        diagnose_pub(args.pub, queries, conn, embed_client, settings)
    elif args.query:
        # Test one query against all problem pubs
        for pub in PROBLEM_PUBS:
            diagnose_pub(pub, [args.query], conn, embed_client, settings)
    else:
        # Run all problem pubs
        for pub, queries in PROBLEM_PUBS.items():
            diagnose_pub(pub, queries, conn, embed_client, settings)

    conn.close()
    print(f"\n{'='*76}")
    print("  DIAGNOSIS COMPLETE")
    print(f"{'='*76}")


if __name__ == "__main__":
    main()
