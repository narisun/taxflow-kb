#!/usr/bin/env python3
"""
taxkb/cli/main.py — TaxFlow AI Knowledge Base CLI entry point.

Argparse setup, dispatch dict, and main() function.
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("taxflow.cli")


def main() -> int:
    # Print active config (secrets masked) so users know what env was loaded.
    from taxkb.config import print_settings_banner
    print_settings_banner()

    parser = argparse.ArgumentParser(
        description="TaxFlow AI — IRS Knowledge Base CLI (Layers 1–4)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Layer 1:  ingest · validate · sample · score · diff\n"
            "Layer 2:  ingest-instructions · validate-instructions\n"
            "Layer 3:  ingest-publications · validate-publications · build-index · search\n"
            "Layer 4:  ask · validate-agent\n"
            "Data:     download-publications"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── Layer 1: ingest ───────────────────────────────────────────────────────
    p_ingest = sub.add_parser("ingest", help="Parse MeF CSV and load into databases")
    p_ingest.add_argument("--csv",            required=True, help="Path to MeF CSV file")
    p_ingest.add_argument("--neo4j-uri",      default=None,  help="Neo4j bolt URI")
    p_ingest.add_argument("--neo4j-user",     default="neo4j")
    p_ingest.add_argument("--neo4j-password", default="password")
    p_ingest.add_argument("--pg-dsn",         default=None,  help="PostgreSQL DSN")
    p_ingest.add_argument("--init-schema",    action="store_true",
                          help="Run DDL schema before ingesting")

    # ── Layer 1: validate ─────────────────────────────────────────────────────
    p_val = sub.add_parser("validate", help="Run Layer 1 validation gates")
    p_val.add_argument("--csv",           required=True)
    p_val.add_argument("--step",          default="all",
                       choices=["all", "v1.1", "v1.3"],
                       help="Which gate to run (default: all)")
    p_val.add_argument("--expected-rows", type=int, default=None,
                       help="Expected row count from IRS release memo")

    # ── Layer 1: sample ───────────────────────────────────────────────────────
    p_sample = sub.add_parser("sample", help="Generate expert spot-check sample")
    p_sample.add_argument("--csv", required=True)
    p_sample.add_argument("--out", default="reports/spot_check",
                          help="Output file path (without extension)")

    # ── Layer 1: score ────────────────────────────────────────────────────────
    p_score = sub.add_parser("score", help="Score annotated spot-check file")
    p_score.add_argument("--annotated", required=True,
                         help="Path to annotated .json or .csv file")

    # ── Layer 1: diff ─────────────────────────────────────────────────────────
    p_diff = sub.add_parser("diff", help="Regression test between two CSV versions")
    p_diff.add_argument("--old",        required=True, help="Old CSV version path")
    p_diff.add_argument("--new",        required=True, help="New CSV version path")
    p_diff.add_argument("--report-dir", default="reports/",
                        help="Directory to write diff report JSON")

    # ── Layer 2: ingest-instructions ──────────────────────────────────────────
    p_l2i = sub.add_parser("ingest-instructions",
                            help="Parse IRS instruction HTML and load into databases")
    p_l2i.add_argument("--html",            required=True,
                       help="Path to IRS instruction HTML file")
    p_l2i.add_argument("--form-type",       default="1040",
                       help="Form type identifier, e.g. 1040 (default: 1040)")
    p_l2i.add_argument("--tax-year",        type=int, default=2024,
                       help="Tax year, e.g. 2024 (default: 2024)")
    p_l2i.add_argument("--source-url",      default="",
                       help="Canonical IRS URL (optional metadata)")
    p_l2i.add_argument("--neo4j-uri",       default=None, help="Neo4j bolt URI")
    p_l2i.add_argument("--neo4j-user",      default="neo4j")
    p_l2i.add_argument("--neo4j-password",  default="password")
    p_l2i.add_argument("--pg-dsn",          default=None, help="PostgreSQL DSN")
    p_l2i.add_argument("--init-schema",     action="store_true",
                       help="Run Layer 2 DDL before ingesting")

    # ── Layer 2: validate-instructions ────────────────────────────────────────
    p_l2v = sub.add_parser("validate-instructions",
                            help="Run V2.1 (structural) and V2.2 (link coverage) gates")
    p_l2v.add_argument("--html",      required=True,
                       help="Path to IRS instruction HTML file")
    p_l2v.add_argument("--form-type", default="1040")
    p_l2v.add_argument("--tax-year",  type=int, default=2024)
    p_l2v.add_argument("--step",      default="all",
                       choices=["all", "v2.1", "v2.2"],
                       help="Which gate to run (default: all)")

    # ── Layer 3: ingest-publications ──────────────────────────────────────────
    p_l3i = sub.add_parser(
        "ingest-publications",
        help="Parse IRS publication PDF(s), embed, and load into PostgreSQL/pgvector",
    )
    p_l3i.add_argument("--pdf",            required=True, action="append",
                       dest="pdf",
                       help="Path to IRS publication PDF (repeat for multiple)")
    p_l3i.add_argument("--pub-number",     required=True, action="append",
                       dest="pub_number",
                       help="Publication number matching the --pdf (repeat for multiple)")
    p_l3i.add_argument("--tax-year",       type=int, default=2025,
                       help="Tax year the publication covers (default: 2025)")
    p_l3i.add_argument("--pg-dsn",         required=True,
                       help="PostgreSQL DSN, e.g. postgresql://taxflow:pw@localhost/taxflow")
    p_l3i.add_argument("--api-key",        default=None,
                       help="OpenAI API key (default: OPENAI_API_KEY env var)")
    p_l3i.add_argument("--skip-embedding", action="store_true",
                       help="Ingest text only; skip embedding step")
    p_l3i.add_argument("--init-schema",    action="store_true",
                       help="Apply taxkb/schema/postgres_layer3.sql before ingesting")
    p_l3i.add_argument("--build-index",    action="store_true",
                       help="Build IVFFlat ANN index after ingestion")
    p_l3i.add_argument("--no-summaries",   action="store_true",
                       help="Skip Tier-1/2 anchor chunk generation (detail-only mode)")

    # ── Layer 3: validate-publications ────────────────────────────────────────
    p_l3v = sub.add_parser(
        "validate-publications",
        help="Run V3.1 (structural), V3.2 (coverage), V3.3 (retrieval) gates",
    )
    p_l3v.add_argument("--step",              default="all",
                       choices=["all", "v3.1", "v3.2", "v3.3"],
                       help="Which gate(s) to run (default: all)")
    p_l3v.add_argument("--pg-dsn",            default=None,
                       help="PostgreSQL DSN (required for V3.2 and V3.3)")
    p_l3v.add_argument("--pdf",               action="append", default=[],
                       dest="pdf",
                       help="PDF path(s) for V3.1 structural check")
    p_l3v.add_argument("--pub-number",        action="append", default=[],
                       dest="pub_number",
                       help="Publication number(s) matching --pdf for V3.1")
    p_l3v.add_argument("--tax-year",          type=int, default=2025)
    p_l3v.add_argument("--api-key",           default=None,
                       help="OpenAI API key for V3.3 probe embedding")
    p_l3v.add_argument("--require-embeddings",action="store_true",
                       help="Enforce V3.2-C embedding coverage check")

    # ── Layer 3: build-index ──────────────────────────────────────────────────
    p_bidx = sub.add_parser(
        "build-index",
        help="Build IVFFlat ANN index for fast cosine search (run once after ingest)",
    )
    p_bidx.add_argument("--pg-dsn",  required=True, help="PostgreSQL DSN")
    p_bidx.add_argument("--lists",   type=int, default=100,
                        help="IVFFlat lists parameter (default: 100, good for ≤1M chunks)")
    p_bidx.add_argument("--force",   action="store_true",
                        help="Drop the existing index before rebuilding. REQUIRED after "
                             "re-embedding with a different model — stale IVFFlat centroids "
                             "will route all queries to wrong cluster partitions.")

    # ── Layer 3: add-bm25-index ───────────────────────────────────────────────
    p_bm25 = sub.add_parser(
        "add-bm25-index",
        help="One-time migration: add tsvector column + GIN index for BM25 keyword search",
    )
    p_bm25.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")

    # ── Layer 3: add-hierarchy-columns ────────────────────────────────────────
    p_hier = sub.add_parser(
        "add-hierarchy-columns",
        help="One-time migration: add chunk_type + topic_ids columns and indexes "
             "for three-tier hierarchy",
    )
    p_hier.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")

    # ── Layer 3: search ───────────────────────────────────────────────────────
    p_search = sub.add_parser(
        "search",
        help="Search ingested IRS publications (vector | bm25 | hybrid)",
    )
    p_search.add_argument("query",
                          help="Natural-language or keyword query string")
    p_search.add_argument("--pg-dsn",     required=True,
                          help="PostgreSQL DSN")
    p_search.add_argument("--api-key",    default=None,
                          help="OpenAI API key (required for vector/hybrid modes)")
    p_search.add_argument("--top-k",      type=int, default=5,
                          help="Number of results to return (default: 5)")
    p_search.add_argument("--pub-number", action="append", default=[],
                          dest="pub_number",
                          help="Restrict search to these publication numbers")
    p_search.add_argument("--tax-year",   type=int, default=None,
                          help="Tax year to search (default: current year from settings)")
    p_search.add_argument("--mode",       default="hybrid",
                          choices=["vector", "bm25", "hybrid"],
                          help="Retrieval mode: vector (cosine), bm25 (keyword), "
                               "hybrid (default). Requires add-bm25-index for bm25/hybrid.")
    p_search.add_argument("--merge-strategy", default="augment", dest="merge_strategy",
                          choices=["augment", "rrf"],
                          help="Hybrid merge strategy: 'augment' (default, preserves vector "
                               "ranking + appends BM25 extras) or 'rrf' (Reciprocal Rank Fusion).")

    # ── Layer 5: generate-gold-set ────────────────────────────────────────────
    p_gen = sub.add_parser(
        "generate-gold-set",
        help="Sample pub chunks from DB and draft Q&A pairs with GPT-4o",
    )
    p_gen.add_argument("--pg-dsn",          required=True, help="PostgreSQL DSN")
    p_gen.add_argument("--out",             default="data/eval/gold_set.json",
                       help="Output JSON path (default: data/eval/gold_set.json)")
    p_gen.add_argument("--pub",             action="append", default=[], dest="pub",
                       help="Pub number(s) to generate for (default: all ingested)")
    p_gen.add_argument("--chunks-per-pub",  type=int, default=15,
                       help="Chunks to sample per publication (default: 15)")
    p_gen.add_argument("--pairs-per-chunk", type=int, default=1,
                       help="Q&A pairs to generate per chunk (default: 1)")
    p_gen.add_argument("--tax-year",        type=int, default=2025)
    p_gen.add_argument("--model",           default="gpt-5.4",
                       help="OpenAI model for generation (default: gpt-5.4)")
    p_gen.add_argument("--api-key",         default=None)
    p_gen.add_argument("--append",          action="store_true",
                       help="Append to existing gold set instead of overwriting")

    # ── Layer 5: review-gold-set ──────────────────────────────────────────────
    p_rev = sub.add_parser(
        "review-gold-set",
        help="Print summary and sample entries from a gold set file",
    )
    p_rev.add_argument("--gold-set",    required=True, dest="gold_set",
                       help="Path to gold set JSON file")
    p_rev.add_argument("--sample",      type=int, default=5,
                       help="Number of entries to display (default: 5)")
    p_rev.add_argument("--pub",         default=None,
                       help="Filter by publication number")
    p_rev.add_argument("--difficulty",  default=None,
                       choices=["simple", "medium", "complex"],
                       help="Filter by difficulty level")

    # ── Layer 5: filter-gold-set ─────────────────────────────────────────────
    p_filt = sub.add_parser(
        "filter-gold-set",
        help="Remove specific-example questions that are unfair for semantic RAG evaluation",
    )
    p_filt.add_argument("--gold-set",     required=True, dest="gold_set")
    p_filt.add_argument("--out",          default=None,
                        help="Output path (default: overwrite input)")
    p_filt.add_argument("--show-removed", action="store_true",
                        help="Print removed questions to stdout")

    # ── Layer 5: patch-gold-set ───────────────────────────────────────────────
    p_patch = sub.add_parser(
        "patch-gold-set",
        help="Expand gold_chunk_ids with adjacent chunks (±window) — no LLM calls needed",
    )
    p_patch.add_argument("--gold-set",  required=True, dest="gold_set",
                         help="Path to existing gold set JSON")
    p_patch.add_argument("--pg-dsn",   required=True,
                         help="PostgreSQL DSN")
    p_patch.add_argument("--window",   type=int, default=1,
                         help="Neighbour window on each side (default: 1 = ±1 chunk)")
    p_patch.add_argument("--out",      default=None,
                         help="Output path (default: overwrite input file)")

    # ── Layer 5: validate-gold-set ────────────────────────────────────────────
    p_val_gs = sub.add_parser(
        "validate-gold-set",
        help="Run V5.1 quality gate on a gold set file (size, coverage, diversity)",
    )
    p_val_gs.add_argument("--gold-set", required=True, dest="gold_set",
                          help="Path to gold set JSON file")

    # ── Layer 5: verify-gold-set ──────────────────────────────────────────────
    p_verify = sub.add_parser(
        "verify-gold-set",
        help="Interactively CPA-verify entries in a gold set file",
    )
    p_verify.add_argument("--gold-set",   required=True, dest="gold_set")
    p_verify.add_argument("--verifier",   required=True,
                          help="CPA name to record as verifier (e.g. 'Jane CPA')")
    p_verify.add_argument("--pub",        default=None,
                          help="Only verify entries for this publication")
    p_verify.add_argument("--difficulty", default=None,
                          choices=["simple", "medium", "complex"])

    # ── Layer 5: evaluate-retrieval ───────────────────────────────────────────
    p_eval_ret = sub.add_parser(
        "evaluate-retrieval",
        help="Run HR@k / MRR / Recall evaluation of the retriever against a gold set",
    )
    p_eval_ret.add_argument("--gold-set",        required=True, dest="gold_set",
                            help="Path to gold set JSON file")
    p_eval_ret.add_argument("--pg-dsn",          required=True,
                            help="PostgreSQL DSN")
    p_eval_ret.add_argument("--api-key",         default=None,
                            help="OpenAI API key (needed for embedding queries)")
    p_eval_ret.add_argument("--top-k",           type=int, default=10,
                            help="Number of chunks to retrieve per question (default: 10)")
    p_eval_ret.add_argument("--pub",             action="append", default=[],
                            help="Restrict evaluation to these pub number(s)")
    p_eval_ret.add_argument("--difficulty",      default=None,
                            choices=["simple", "medium", "complex"])
    p_eval_ret.add_argument("--verified-only",   action="store_true",
                            help="Evaluate only CPA-verified entries")
    p_eval_ret.add_argument("--merge-strategy",  default="augment", dest="merge_strategy",
                            choices=["augment", "rrf"],
                            help="Hybrid merge strategy: 'augment' (default, safe) or 'rrf' (may regress)")
    p_eval_ret.add_argument("--no-bm25",         action="store_true", dest="no_bm25",
                            help="Disable BM25; run pure vector-only (useful for establishing baseline)")
    p_eval_ret.add_argument("--out",             default=None,
                            help="Write JSON report to this path (optional)")

    # ── Layer 5: evaluate-generation ─────────────────────────────────────────
    p_eval_gen = sub.add_parser(
        "evaluate-generation",
        help="Run LLM-as-judge generation quality evaluation against a gold set",
    )
    p_eval_gen.add_argument("--gold-set",        required=True, dest="gold_set",
                            help="Path to gold set JSON file")
    p_eval_gen.add_argument("--pg-dsn",          required=True,
                            help="PostgreSQL DSN")
    p_eval_gen.add_argument("--api-key",         default=None,
                            help="OpenAI API key")
    p_eval_gen.add_argument("--model",           default="gpt-5.4-mini",
                            help="Agent synthesis model (default: gpt-5.4-mini)")
    p_eval_gen.add_argument("--judge-model",     default="gpt-5.4",
                            help="Judge model (default: gpt-5.4)")
    p_eval_gen.add_argument("--top-k",           type=int, default=10)
    p_eval_gen.add_argument("--pub",             action="append", default=[])
    p_eval_gen.add_argument("--difficulty",      default=None,
                            choices=["simple", "medium", "complex"])
    p_eval_gen.add_argument("--verified-only",   action="store_true")
    p_eval_gen.add_argument("--out",             default=None,
                            help="Write JSON report to this path (optional)")
    p_eval_gen.add_argument("--out-results",     default=None,
                            help="Write per-question results JSONL to this path")
    p_eval_gen.add_argument("--rate-limit-delay",type=float, default=1.0,
                            help="Seconds between judge API calls (default: 1.0)")
    p_eval_gen.add_argument("--sample",          type=int,   default=None,
                            help="Evaluate a random sample of N entries instead of "
                                 "the full gold set (for quick iteration checks)")
    p_eval_gen.add_argument("--sample-seed",     type=int,   default=42,
                            dest="sample_seed",
                            help="Random seed for --sample (default: 42)")

    # ── Layer 3: re-embed ────────────────────────────────────────────────────
    p_re_embed = sub.add_parser(
        "re-embed",
        help="Re-embed one or more publications with the current model "
             "(text-embedding-3-large), optionally enriching tabular chunks",
    )
    p_re_embed.add_argument("--pub",        action="append", default=[],
                            required=True,
                            help="Publication number to re-embed (repeat for multiple, "
                                 "e.g. --pub 596 --pub 525)")
    p_re_embed.add_argument("--pg-dsn",     required=True,
                            help="PostgreSQL DSN")
    p_re_embed.add_argument("--api-key",    default=None,
                            help="OpenAI API key (default: OPENAI_API_KEY env var)")
    p_re_embed.add_argument("--model",      default=None,
                            help="Embedding model override (default: text-embedding-3-large)")
    p_re_embed.add_argument("--no-enrich",  action="store_true", dest="no_enrich",
                            help="Skip chunk enrichment (embed raw text only)")
    p_re_embed.add_argument("--no-index",   action="store_true", dest="no_index",
                            help="Skip IVFFlat index rebuild after re-embedding")

    # ── Layer 4: ask ──────────────────────────────────────────────────────────
    p_ask = sub.add_parser(
        "ask",
        help="Answer a CPA tax question using the full retrieval + synthesis pipeline",
    )
    p_ask.add_argument("question",
                       help="Natural-language CPA question (quote it)")
    p_ask.add_argument("--pg-dsn",        required=True,
                       help="PostgreSQL DSN")
    p_ask.add_argument("--api-key",       default=None,
                       help="OpenAI API key (default: OPENAI_API_KEY env var)")
    p_ask.add_argument("--model",         default="gpt-5.4-mini",
                       help="OpenAI chat model for synthesis (default: gpt-5.4-mini)")
    p_ask.add_argument("--top-k",         type=int, default=5,
                       help="Number of publication chunks to retrieve (default: 5)")
    p_ask.add_argument("--pub",           action="append", default=[],
                       dest="pub",
                       help="Restrict search to this publication number (repeat for multiple)")
    p_ask.add_argument("--tax-year",      type=int, default=None,
                       help="Tax year to search (default: current year from settings)")
    p_ask.add_argument("--no-synthesize", action="store_true", dest="no_synthesize",
                       help="Return retrieved chunks only — skip LLM synthesis")
    p_ask.add_argument("--show-chunks",   action="store_true", dest="show_chunks",
                       help="Print the first 200 chars of each retrieved chunk")
    p_ask.add_argument("--json",          action="store_true", dest="json_out",
                       help="Output full result as JSON (in addition to pretty print)")

    # ── Download IRS publications ───────────────────────────────────────────────
    p_dl = sub.add_parser(
        "download-publications",
        help="Download IRS publication PDFs from IRS.gov",
    )
    p_dl.add_argument(
        "--mode", default="status",
        choices=["status", "single", "tier", "missing", "all"],
        help=(
            "Download mode: status (show what's downloaded), "
            "single (one pub), tier (all pubs in a tier), "
            "missing (only what's not on disk), all (everything)"
        ),
    )
    p_dl.add_argument("--pub-number", default=None,
                       help="Publication number for single mode (e.g., 523)")
    p_dl.add_argument("--tax-year", type=int, default=None,
                       help="Tax year for single mode (default: current year)")
    p_dl.add_argument("--tier", type=int, default=None, choices=[1, 2, 3],
                       help="Tier for tier mode (1=current, 2=Tier-1 additions, 3=Tier-2)")
    p_dl.add_argument("--years", default=None,
                       help="Comma-separated tax years (e.g., 2023,2024,2025)")
    p_dl.add_argument("--output-dir", default=None,
                       help="Output directory (default: data/publications/)")
    p_dl.add_argument("--force", action="store_true",
                       help="Re-download even if file exists")

    # ── Layer 4: validate-agent ──────────────────────────────────────────────
    p_l4v = sub.add_parser(
        "validate-agent",
        help="Run V4.1 CPA agent functional validation (5 standard CPA queries)",
    )
    p_l4v.add_argument("--pg-dsn",  required=True, help="PostgreSQL DSN")
    p_l4v.add_argument("--api-key", default=None,
                       help="OpenAI API key (default: OPENAI_API_KEY env var)")
    p_l4v.add_argument("--model",   default="gpt-5.4-mini",
                       help="OpenAI chat model for synthesis (default: gpt-5.4-mini)")
    p_l4v.add_argument("--top-k",   type=int, default=5,
                       help="Chunks to retrieve per probe (default: 5)")

    # ── Coverage report ──────────────────────────────────────────────────────
    p_cov = sub.add_parser(
        "coverage",
        help="Print multi-year publication coverage report",
    )
    p_cov.add_argument("--year", type=int, action="append", default=[],
                       dest="years",
                       help="Check coverage for specific year(s); repeat for multiple")
    p_cov.add_argument("--gaps-only", action="store_true", dest="gaps_only",
                       help="Show only publications with coverage gaps")

    # ── Dispatch ──────────────────────────────────────────────────────────────
    args = parser.parse_args()

    from taxkb.cli.rules_commands import cmd_ingest, cmd_validate, cmd_sample, cmd_score, cmd_diff
    from taxkb.cli.instructions_commands import cmd_ingest_instructions, cmd_validate_instructions
    from taxkb.cli.publications_commands import (
        cmd_ingest_publications, cmd_validate_publications,
        cmd_build_index, cmd_add_bm25_index, cmd_add_hierarchy_columns,
        cmd_search, cmd_re_embed, cmd_download_publications, cmd_coverage,
    )
    from taxkb.cli.agent_commands import cmd_ask, cmd_validate_agent
    from taxkb.cli.evaluation_commands import (
        cmd_generate_gold_set, cmd_review_gold_set, cmd_filter_gold_set,
        cmd_patch_gold_set, cmd_validate_gold_set, cmd_verify_gold_set,
        cmd_evaluate_retrieval, cmd_evaluate_generation,
    )

    dispatch = {
        "ingest"                : cmd_ingest,
        "validate"              : cmd_validate,
        "sample"                : cmd_sample,
        "score"                 : cmd_score,
        "diff"                  : cmd_diff,
        "ingest-instructions"   : cmd_ingest_instructions,
        "validate-instructions" : cmd_validate_instructions,
        "ingest-publications"   : cmd_ingest_publications,
        "validate-publications" : cmd_validate_publications,
        "build-index"           : cmd_build_index,
        "add-bm25-index"        : cmd_add_bm25_index,
        "add-hierarchy-columns" : cmd_add_hierarchy_columns,
        "re-embed"              : cmd_re_embed,
        "search"                : cmd_search,
        "coverage"              : cmd_coverage,
        "ask"                   : cmd_ask,
        "validate-agent"        : cmd_validate_agent,
        "download-publications" : cmd_download_publications,
        # Layer 5
        "generate-gold-set"     : cmd_generate_gold_set,
        "filter-gold-set"       : cmd_filter_gold_set,
        "patch-gold-set"        : cmd_patch_gold_set,
        "validate-gold-set"     : cmd_validate_gold_set,
        "verify-gold-set"       : cmd_verify_gold_set,
        "review-gold-set"       : cmd_review_gold_set,
        "evaluate-retrieval"    : cmd_evaluate_retrieval,
        "evaluate-generation"   : cmd_evaluate_generation,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
