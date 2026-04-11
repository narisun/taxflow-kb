#!/usr/bin/env python3
"""
Dry-run ingestion of the 8 Tier-1 gap publications.

Runs the full pipeline EXCEPT the database write and embedding steps:
  PDF parse → chunking → anchor summary generation → enrichment validation

Produces a detailed report of what would be ingested.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taxflow_kb.layer3.pdf_parser import parse_publication_pdf
from taxflow_kb.layer3.summary_generator import generate_anchor_chunks
from taxflow_kb.layer3.chunk_enrichment import enrich_for_embedding
from taxflow_kb.layer3.topic_ontology import ChunkType, get_ontology
from taxflow_kb.layer3.publication_registry import get_registry

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "publications"

# The 8 Tier-1 gap publications — use latest tax year available
TIER1_PUBS = [
    ("334", 2025),
    ("505", 2025),
    ("523", 2025),
    ("527", 2025),
    ("535", 2022),  # Discontinued — only 2022 available
    ("544", 2025),
    ("551", 2025),
    ("946", 2025),
]


def main():
    registry = get_registry()
    ontology = get_ontology()
    results = []
    total_detail = 0
    total_anchor = 0
    total_enriched = 0
    overall_ok = True

    print("=" * 72)
    print("  TAX BRAIN — Tier-1 Gap Publication Dry-Run Ingestion")
    print("=" * 72)
    print()

    for pub_number, tax_year in TIER1_PUBS:
        pdf_name = f"p{pub_number}_{tax_year}.pdf"
        pdf_path = DATA_DIR / pdf_name
        meta = registry.get(pub_number)
        title = meta.title if meta else f"Publication {pub_number}"

        print(f"── Pub {pub_number} ({title}) ──")

        if not pdf_path.exists():
            print(f"  ✗ PDF not found: {pdf_path}")
            overall_ok = False
            results.append({
                "pub_number": pub_number,
                "tax_year": tax_year,
                "status": "MISSING",
                "detail_chunks": 0,
                "anchor_chunks": 0,
            })
            print()
            continue

        t0 = time.monotonic()

        # ── Step 1: Parse PDF ────────────────────────────────────────────
        result = parse_publication_pdf(str(pdf_path), pub_number, tax_year)
        t_parse = time.monotonic() - t0

        if not result.parse_success:
            print(f"  ✗ Parse failed: {result.errors}")
            overall_ok = False
            results.append({
                "pub_number": pub_number,
                "tax_year": tax_year,
                "status": "PARSE_FAIL",
                "errors": result.errors,
                "detail_chunks": 0,
                "anchor_chunks": 0,
            })
            print()
            continue

        detail_chunks = list(result.chunks)
        n_detail = len(detail_chunks)
        total_detail += n_detail
        avg_tokens = sum(c.token_count for c in detail_chunks) / max(n_detail, 1)
        pages = result.publication.page_count

        print(f"  Parsed: {pages} pages → {n_detail} detail chunks "
              f"(avg {avg_tokens:.0f} tok/chunk) [{t_parse:.1f}s]")

        # ── Step 2: Generate anchor chunks ───────────────────────────────
        t1 = time.monotonic()
        try:
            anchors = generate_anchor_chunks(
                pub_number=pub_number,
                pub_title=title,
                tax_year=tax_year,
                detail_chunks=detail_chunks,
            )
        except Exception as exc:
            print(f"  ✗ Summary generation failed: {exc}")
            anchors = []

        t_summary = time.monotonic() - t1
        n_anchor = len(anchors)
        total_anchor += n_anchor

        pub_summaries = [a for a in anchors if a.chunk_type == ChunkType.PUB_SUMMARY]
        sec_summaries = [a for a in anchors if a.chunk_type == ChunkType.SECTION_SUMMARY]

        print(f"  Anchors: {n_anchor} "
              f"(1 pub summary + {len(sec_summaries)} section summaries) "
              f"[{t_summary:.1f}s]")

        # Show pub summary snippet
        if pub_summaries:
            ps = pub_summaries[0]
            snippet = ps.text[:200].replace("\n", " ")
            print(f"    Pub summary: {snippet}…")
            if ps.topic_ids:
                print(f"    Topic IDs: {ps.topic_ids}")

        # Show section summary titles
        if sec_summaries:
            chapter_names = [s.chapter_title for s in sec_summaries]
            print(f"    Sections: {', '.join(chapter_names[:8])}"
                  + ("…" if len(chapter_names) > 8 else ""))

        # ── Step 3: Enrichment test ──────────────────────────────────────
        enriched_count = 0
        sample_detail = detail_chunks[:min(20, n_detail)]
        for chunk in sample_detail:
            enriched = enrich_for_embedding(chunk, pub_number=pub_number)
            if enriched != chunk.text:
                enriched_count += 1
        total_enriched += enriched_count

        pct = enriched_count / len(sample_detail) * 100 if sample_detail else 0
        print(f"  Enrichment: {enriched_count}/{len(sample_detail)} sampled chunks "
              f"enriched ({pct:.0f}%)")

        # ── Step 4: Ontology coverage ────────────────────────────────────
        topics = [t for t in ontology._topics.values()
                  if any(ps.pub_number == pub_number for ps in t.pub_sections)]
        topic_names = [t.display_name for t in topics]
        print(f"  Ontology: mapped to {len(topics)} topics"
              + (f" ({', '.join(topic_names[:5])})" if topic_names else ""))

        results.append({
            "pub_number": pub_number,
            "tax_year": tax_year,
            "title": title,
            "status": "OK",
            "pages": pages,
            "detail_chunks": n_detail,
            "anchor_chunks": n_anchor,
            "section_summaries": len(sec_summaries),
            "enrichment_rate": f"{pct:.0f}%",
            "ontology_topics": len(topics),
            "avg_tokens": round(avg_tokens),
        })
        print()

    # ── Summary report ───────────────────────────────────────────────────
    print("=" * 72)
    print("  DRY-RUN SUMMARY")
    print("=" * 72)
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = len(results) - ok_count
    print(f"  Publications: {ok_count} OK, {fail_count} failed")
    print(f"  Detail chunks: {total_detail}")
    print(f"  Anchor chunks: {total_anchor}")
    print(f"  Total chunks (detail + anchor): {total_detail + total_anchor}")
    print(f"  Enrichment hits (sampled): {total_enriched}")
    print()

    if overall_ok:
        print("  ✓ ALL 8 TIER-1 PUBLICATIONS READY FOR INGESTION")
    else:
        print("  ✗ SOME PUBLICATIONS FAILED — see details above")

    # Save JSON report
    report_path = Path(__file__).resolve().parent.parent / "data" / "dryrun_tier1_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_detail_chunks": total_detail,
            "total_anchor_chunks": total_anchor,
            "total_chunks": total_detail + total_anchor,
            "publications": results,
        }, f, indent=2)
    print(f"\n  Report saved to: {report_path}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
