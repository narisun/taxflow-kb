#!/usr/bin/env python3
"""
cli.py — TaxFlow AI Knowledge Base CLI (Layers 1–3)

Layer 1 commands  (MeF business rules CSV → Neo4j + PostgreSQL)
  ingest            Parse MeF CSV and load into databases
  validate          Run validation steps V1.1 / V1.3 / all
  sample            Generate expert spot-check sample
  score             Score an annotated spot-check file
  diff              Regression test between two CSV versions

Layer 2 commands  (IRS HTML instructions → instruction graph)
  ingest-instructions    Parse HTML file and load into Neo4j + PostgreSQL
  validate-instructions  Run V2.1 (structural) and V2.2 (link coverage) gates

Layer 3 commands  (IRS Publication PDFs → pgvector semantic search)
  ingest-publications    Parse PDF(s), embed with OpenAI, load into PostgreSQL
  validate-publications  Run V3.1 (structural), V3.2 (coverage), V3.3 (retrieval)
  add-hierarchy-columns  One-time migration: add chunk_type + topic_ids columns
  search                 Semantic similarity search over ingested publications

Usage examples:
  # Layer 1
  python cli.py ingest --csv data/sample/mef_1040_2024_v5_2.csv
  python cli.py validate --step all --csv data/sample/mef_1040_2024_v5_2.csv

  # Layer 2
  python cli.py ingest-instructions \\
    --html data/instructions/i1040gi_2024_synthetic.html \\
    --form-type 1040 --tax-year 2024
  python cli.py validate-instructions \\
    --html data/instructions/i1040gi_2024_synthetic.html \\
    --form-type 1040 --tax-year 2024

  # Layer 3
  python cli.py ingest-publications \\
    --pdf data/publications/p17.pdf --pub-number 17 --tax-year 2025 \\
    --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
  python cli.py validate-publications \\
    --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" \\
    --step v3.1
  python cli.py search "What is the standard deduction for a single filer?" \\
    --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow" --top-k 5
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("taxflow.cli")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_and_ast(csv_path: str):
    """Parse CSV and run AST parser on all rules. Returns (rules, parse_result)."""
    from taxflow_kb.ingestion.csv_parser import CSVParser
    from taxflow_kb.ingestion.ast_parser import parse_expression
    from taxflow_kb.models import ASTNodeType

    logger.info("Parsing CSV: %s", csv_path)
    parser = CSVParser(csv_path)
    rules, parse_result = parser.parse()

    logger.info("Running AST parser on %d rules…", len(rules))
    for rule in rules:
        ast_node = parse_expression(rule.rule_expression)
        if ast_node.node_type == ASTNodeType.PARSE_ERROR:
            rule.parse_success   = False
            rule.parse_error_msg = str(ast_node.value)
        else:
            rule.expression_ast = ast_node.to_dict()
            rule.parse_success  = True

    return rules, parse_result


def _print_report(report) -> None:
    """Pretty-print a ValidationReport."""
    status = "✓ PASS" if report.passed else "✗ FAIL"
    print(f"\n{'='*60}")
    print(f"  {report.step}  —  {status}")
    print(f"  {report.pass_rate*100:.1f}% passed "
          f"({report.total_passed}/{report.total_checked})")
    print(f"{'='*60}")
    for note in report.notes:
        print(f"  {note}")
    if report.warnings:
        print(f"\n  Warnings ({len(report.warnings)}):")
        for w in report.warnings[:5]:
            print(f"    ⚠  {json.dumps(w)[:120]}")
    if report.failures:
        print(f"\n  Failures ({len(report.failures)}):")
        for f in report.failures[:10]:
            print(f"    ✗  {json.dumps(f)[:160]}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Layer 1 command handlers
# ──────────────────────────────────────────────────────────────────────────────

def cmd_ingest(args) -> int:
    rules, parse_result = _parse_and_ast(args.csv)
    logger.info("Parse result: %d/%d rows, %d duplicates",
                parse_result.parse_success, parse_result.total_rows,
                len(parse_result.duplicate_ids))

    if args.neo4j_uri:
        from taxflow_kb.ingestion.neo4j_ingestion import Neo4jIngestion
        logger.info("Loading into Neo4j: %s", args.neo4j_uri)
        ingestor = Neo4jIngestion(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        counts = ingestor.ingest(rules)
        ingestor.close()
        logger.info("Neo4j: %s", counts)

    if args.pg_dsn:
        from taxflow_kb.ingestion.postgres_ingestion import PostgresIngestion
        logger.info("Loading into PostgreSQL…")
        pg = PostgresIngestion(args.pg_dsn)
        if args.init_schema:
            pg.ensure_schema()
        pg.ingest_rules(rules, parse_result)
        pg.close()
        logger.info("PostgreSQL: ingestion complete")

    logger.info("Ingest done. %d rules loaded.", len(rules))
    return 0


def cmd_validate(args) -> int:
    rules, parse_result = _parse_and_ast(args.csv)
    step = args.step.lower()
    overall_passed = True

    if step in ("all", "v1.1"):
        from taxflow_kb.validation import v1_1_structural
        from taxflow_kb.validation.v1_1_structural import StructuralCheckConfig
        cfg = StructuralCheckConfig(
            expected_row_count=args.expected_rows,
        )
        report = v1_1_structural.run(rules, parse_result, cfg)
        _print_report(report)
        overall_passed = overall_passed and report.passed

    if step in ("all", "v1.3"):
        from taxflow_kb.validation import v1_3_test_replay
        from taxflow_kb.validation.v1_3_test_replay import build_synthetic_test_cases
        test_cases = build_synthetic_test_cases()
        report, _ = v1_3_test_replay.run(rules, test_cases)
        _print_report(report)
        overall_passed = overall_passed and report.passed

    if not overall_passed:
        logger.error("One or more validation steps FAILED. Do not proceed to Layer 2.")
        return 1
    logger.info("All validation steps PASSED.")
    return 0


def cmd_sample(args) -> int:
    rules, _ = _parse_and_ast(args.csv)
    from taxflow_kb.validation import v1_2_spot_check
    counts = v1_2_spot_check.generate_sample(rules, args.out)
    print("\nSpot-check sample generated:")
    for cat, n in sorted(counts.items()):
        print(f"  {cat:25s}: {n} rules")
    print(f"\nFiles: {args.out}.csv  and  {args.out}.json")
    print("Next: have the tax domain expert annotate the CSV, then run:")
    print(f"  python cli.py score --annotated {args.out}.json")
    return 0


def cmd_score(args) -> int:
    from taxflow_kb.validation import v1_2_spot_check
    report = v1_2_spot_check.score_review(args.annotated)
    _print_report(report)
    return 0 if report.passed else 1


def cmd_diff(args) -> int:
    old_rules, _ = _parse_and_ast(args.old)
    new_rules, _ = _parse_and_ast(args.new)
    from taxflow_kb.validation import v1_4_regression
    from taxflow_kb.validation.v1_3_test_replay import build_synthetic_test_cases
    test_cases = build_synthetic_test_cases()
    diffs, report = v1_4_regression.run(
        old_rules, new_rules, test_cases,
        report_dir=args.report_dir,
    )
    _print_report(report)
    from taxflow_kb.models import ChangeType
    for ct in (ChangeType.ADDED, ChangeType.REMOVED, ChangeType.MODIFIED):
        group = [d for d in diffs if d.change_type == ct]
        if group:
            print(f"{ct.value} ({len(group)}):")
            for d in group[:10]:
                print(f"  {d.rule_id}  →  {', '.join(d.changed_fields) or 'n/a'}")
    return 0 if report.passed else 1


# ──────────────────────────────────────────────────────────────────────────────
# Layer 2 command handlers
# ──────────────────────────────────────────────────────────────────────────────

def cmd_ingest_instructions(args) -> int:
    from taxflow_kb.layer2.html_parser import parse_instruction_html

    logger.info("Layer 2 — parsing HTML: %s", args.html)
    result = parse_instruction_html(
        args.html,
        form_type  = args.form_type,
        tax_year   = args.tax_year,
        source_url = getattr(args, "source_url", ""),
    )

    if not result.parse_success:
        logger.error("Parse failed: %s", result.errors)
        return 1

    logger.info("Parsed: %d sections (%d with line references)",
                len(result.sections), len(result.line_sections()))
    for w in result.warnings:
        logger.warning("  %s", w)

    neo4j_stats: dict = {}
    if args.neo4j_uri:
        from neo4j import GraphDatabase
        from taxflow_kb.layer2.neo4j_layer2 import Neo4jLayer2Ingestion
        driver = GraphDatabase.driver(
            args.neo4j_uri,
            auth=(args.neo4j_user, args.neo4j_password),
        )
        ingestion = Neo4jLayer2Ingestion(driver)
        neo4j_stats = ingestion.ingest(result)
        driver.close()
        logger.info("Neo4j: %s", neo4j_stats)

    if args.pg_dsn:
        import psycopg2
        from taxflow_kb.layer2.postgres_layer2 import PostgresLayer2Ingestion
        conn = psycopg2.connect(args.pg_dsn)
        pg   = PostgresLayer2Ingestion(conn)
        if getattr(args, "init_schema", False):
            pg.ensure_schema()
        pg.ingest(
            result,
            source_path     = args.html,
            explains_count  = neo4j_stats.get("explains_created", 0),
            form_refs_count = neo4j_stats.get("form_refs_created", 0),
        )
        conn.close()
        logger.info("PostgreSQL: Layer 2 data written.")

    logger.info("Layer 2 ingest complete.")
    return 0


def cmd_validate_instructions(args) -> int:
    from taxflow_kb.layer2.html_parser import parse_instruction_html
    from taxflow_kb.layer2.validation import v2_1_structural, v2_2_link_coverage

    logger.info("Parsing HTML for validation: %s", args.html)
    result = parse_instruction_html(
        args.html, form_type=args.form_type, tax_year=args.tax_year,
    )

    overall_pass = True
    step = args.step.lower()

    if step in ("all", "v2.1"):
        r = v2_1_structural.run(result)
        status = "PASS ✓" if r.passed else "FAIL ✗"
        print(f"\n{'='*60}")
        print(f"  V2.1-STRUCTURAL  —  {status}")
        print(f"{'='*60}")
        for note in r.notes:
            print(f"  {note}")
        if r.failures:
            print(f"\n  Failures ({len(r.failures)}):")
            for f in r.failures:
                print(f"    ✗  {json.dumps(f)[:160]}")
        if r.warnings:
            print(f"\n  Warnings ({len(r.warnings)}):")
            for w in r.warnings[:5]:
                print(f"    ⚠  {json.dumps(w)[:120]}")
        print()
        if not r.passed:
            overall_pass = False

    if step in ("all", "v2.2"):
        r = v2_2_link_coverage.run(result)
        status = "PASS ✓" if r.passed else "FAIL ✗"
        print(f"\n{'='*60}")
        print(f"  V2.2-LINK-COVERAGE  —  {status}")
        print(f"  {r.pass_rate*100:.1f}% fields covered "
              f"({r.total_passed}/{r.total_checked})")
        print(f"{'='*60}")
        for note in r.notes:
            print(f"  {note}")
        if r.failures:
            print(f"\n  Failures ({len(r.failures)}):")
            for f in r.failures[:10]:
                print(f"    ✗  {json.dumps(f)[:160]}")
        print()
        if not r.passed:
            overall_pass = False

    return 0 if overall_pass else 1


# ──────────────────────────────────────────────────────────────────────────────
# Layer 3 command handlers
# ──────────────────────────────────────────────────────────────────────────────

def cmd_ingest_publications(args) -> int:
    """
    Parse one or more IRS publication PDFs, embed with OpenAI, and load into
    PostgreSQL (pgvector).
    """
    import os
    from taxflow_kb.layer3.pdf_parser    import parse_publication_pdf
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key and not args.skip_embedding:
        logger.error(
            "OPENAI_API_KEY is not set. Pass --api-key or set the env var, "
            "or use --skip-embedding to ingest text only."
        )
        return 1

    pdf_paths   = args.pdf        # list[str]
    pub_numbers = args.pub_number # list[str]
    tax_year    = args.tax_year

    if len(pdf_paths) != len(pub_numbers):
        logger.error(
            "--pdf and --pub-number must be provided the same number of times "
            "(got %d and %d)", len(pdf_paths), len(pub_numbers)
        )
        return 1

    dsn = args.pg_dsn
    if not dsn:
        logger.error("--pg-dsn is required for Layer 3 ingestion.")
        return 1

    overall_ok = True

    with Layer3Store(dsn=dsn) as store:
        if args.init_schema:
            schema_path = Path(__file__).parent / "schema" / "postgres_layer3.sql"
            store.apply_schema(str(schema_path))
            logger.info("Layer 3 schema applied.")

        for pdf_path, pub_number in zip(pdf_paths, pub_numbers):
            logger.info("Processing pub %s from %s …", pub_number, pdf_path)
            result = parse_publication_pdf(pdf_path, pub_number, tax_year)

            if not result.parse_success:
                logger.error("Parse failed for pub %s: %s", pub_number, result.errors)
                overall_ok = False
                continue

            logger.info(
                "  Parsed: %d chunks, avg %.0f tokens/chunk",
                len(result.chunks),
                sum(c.token_count for c in result.chunks) / max(len(result.chunks), 1),
            )

            summary = store.ingest(
                result,
                embed_api_key      = api_key,
                skip_embedding     = args.skip_embedding,
                generate_summaries = not args.no_summaries,
            )
            logger.info("  Ingest summary: %s", summary)

        if args.build_index:
            try:
                store.create_ivfflat_index()
            except Exception as exc:
                logger.warning("Could not build IVFFlat index: %s", exc)

    return 0 if overall_ok else 1


def cmd_validate_publications(args) -> int:
    """Run V3.1 / V3.2 / V3.3 gates against the live database or parsed PDFs."""
    import os
    from taxflow_kb.layer3.pdf_parser import parse_publication_pdf

    step = args.step.lower()
    overall_pass = True

    # ── V3.1 — parse PDFs and check structural integrity ─────────────────────
    if step in ("all", "v3.1"):
        from taxflow_kb.layer3.validation.v3_1_structural import validate_structural

        if not args.pdf:
            if step == "v3.1":
                logger.error("V3.1 requires --pdf (one or more PDF paths).")
                return 1
            else:
                # Running --step all without PDFs: skip V3.1, continue with V3.2/V3.3
                logger.warning(
                    "V3.1 skipped — no --pdf arguments provided. "
                    "Pass --pdf/--pub-number to run the structural gate."
                )
        else:
            pub_numbers = args.pub_number
            if len(args.pdf) != len(pub_numbers):
                logger.error("--pdf and --pub-number count must match for V3.1.")
                return 1

            for pdf_path, pub_number in zip(args.pdf, pub_numbers):
                result = parse_publication_pdf(pdf_path, pub_number, args.tax_year)
                v = validate_structural(result)
                v.print_report()
                if not v.passed:
                    overall_pass = False

    # ── V3.2 — database coverage check ───────────────────────────────────────
    if step in ("all", "v3.2"):
        from taxflow_kb.layer3.validation.v3_2_coverage import validate_coverage
        from taxflow_kb.layer3.postgres_layer3 import Layer3Store

        if not args.pg_dsn:
            logger.error("V3.2 requires --pg-dsn.")
            return 1

        with Layer3Store(dsn=args.pg_dsn) as store:
            v = validate_coverage(
                store,
                require_embeddings=args.require_embeddings,
            )
        v.print_report()
        if not v.passed:
            overall_pass = False

    # ── V3.3 — retrieval quality probes ──────────────────────────────────────
    if step in ("all", "v3.3"):
        from taxflow_kb.layer3.validation.v3_3_retrieval import validate_retrieval
        from taxflow_kb.layer3.postgres_layer3 import Layer3Store

        if not args.pg_dsn:
            logger.error("V3.3 requires --pg-dsn.")
            return 1

        api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("V3.3 requires OPENAI_API_KEY or --api-key.")
            return 1

        with Layer3Store(dsn=args.pg_dsn) as store:
            v = validate_retrieval(store, api_key=api_key)
        v.print_report()
        if not v.passed:
            overall_pass = False

    return 0 if overall_pass else 1


def cmd_build_index(args) -> int:
    """Create (or force-rebuild) the IVFFlat ANN index on the embedding column."""
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    force = getattr(args, "force", False)
    logger.info(
        "Building IVFFlat index (lists=%d, force=%s) …", args.lists, force
    )
    with Layer3Store(dsn=args.pg_dsn) as store:
        try:
            store.create_ivfflat_index(lists=args.lists, force=force)
        except Exception as exc:
            logger.error("Index creation failed: %s", exc)
            return 1

    logger.info("IVFFlat index ready — cosine ANN search is now fast.")
    return 0


def cmd_add_bm25_index(args) -> int:
    """
    One-time migration: add the text_tsvector generated column and GIN index
    to irs_kb.publication_chunks.

    This enables BM25 keyword search alongside pgvector cosine search.
    HierarchicalRetriever automatically switches to hybrid mode once the
    column exists.  Safe to run multiple times (idempotent).

    After running this command you can test BM25 directly:
        python cli.py search "Form 8889 HSA contribution limit" \\
          --pg-dsn "..." --mode bm25
    """
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    logger.info("Adding BM25 index to publication_chunks …")
    with Layer3Store(dsn=args.pg_dsn) as store:
        try:
            store.add_bm25_index()
        except Exception as exc:
            logger.error("BM25 migration failed: %s", exc)
            return 1

    print("\n✓ BM25 index ready.")
    print("  text_tsvector column  : GENERATED ALWAYS AS to_tsvector('english', text) STORED")
    print("  GIN index             : idx_chunks_fts")
    print("\nHybrid retrieval (vector + BM25 + RRF) is now active for all queries.")
    print("Test with:")
    print(f'  python cli.py search "Form 8889 HSA limit" --pg-dsn "..." --mode bm25')
    print(f'  python cli.py search "Form 8889 HSA limit" --pg-dsn "..." --mode hybrid')
    return 0


def cmd_add_hierarchy_columns(args) -> int:
    """
    One-time migration: add chunk_type and topic_ids columns plus supporting
    indexes to irs_kb.publication_chunks.

    This enables the three-tier hierarchy (pub_summary → section_summary →
    detail) and cross-publication topic ontology.  Safe to run multiple times
    (idempotent).
    """
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    logger.info("Adding hierarchy columns to publication_chunks …")
    with Layer3Store(dsn=args.pg_dsn) as store:
        try:
            store.add_hierarchy_columns()
        except Exception as exc:
            logger.error("Hierarchy migration failed: %s", exc)
            return 1

    print("\n✓ Hierarchy columns ready.")
    print("  chunk_type  : TEXT DEFAULT 'detail' (pub_summary | section_summary | detail)")
    print("  topic_ids   : TEXT[] DEFAULT '{}'")
    print("  Indexes     : idx_chunks_chunk_type, idx_chunks_pub_type, idx_chunks_topic_ids")
    print("\nRe-ingest publications to generate anchor chunks:")
    print('  python cli.py ingest-publications --pdf data/publications/p17.pdf \\')
    print('    --pub-number 17 --pg-dsn "..." --init-schema')
    return 0


def cmd_search(args) -> int:
    """Similarity / keyword / hybrid search over ingested IRS publications."""
    import os
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store

    mode = getattr(args, "mode", "hybrid").lower()
    if mode not in ("vector", "bm25", "hybrid"):
        logger.error("--mode must be one of: vector, bm25, hybrid")
        return 1

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key and mode in ("vector", "hybrid"):
        logger.error(
            "OPENAI_API_KEY is required for vector and hybrid modes. "
            "Pass --api-key or set the env var.  Use --mode bm25 for keyword-only."
        )
        return 1

    if not args.pg_dsn:
        logger.error("--pg-dsn is required for search.")
        return 1

    pub_nums = getattr(args, "pub_number", None) or None
    raw_tax_year = getattr(args, "tax_year", None)

    # Always pin to a single year to avoid cross-year duplicates.
    # --tax-year 0 is a hidden developer escape hatch (not in --help).
    if raw_tax_year == 0:
        tax_year = None        # developer-only: no year filter
    elif raw_tax_year is not None:
        tax_year = raw_tax_year
    else:
        from taxflow_kb.config import get_settings
        tax_year = get_settings().default_tax_year
        logger.debug("No --tax-year specified; defaulting to %d", tax_year)

    year_label = str(tax_year) if tax_year else "ALL (debug)"
    print(f"\nMode: {mode.upper()}  |  Query: {args.query!r}  |  Year: {year_label}")

    if mode == "hybrid":
        # Use HierarchicalRetriever (navigate → vector + BM25 → ontology augment)
        merge_strategy = getattr(args, "merge_strategy", "augment") or "augment"
        from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever
        retriever = HierarchicalRetriever(
            pg_dsn         = args.pg_dsn,
            api_key        = api_key,
            enable_bm25    = True,
            merge_strategy = merge_strategy,
        )
        contexts, elapsed_ms, _meta = retriever.retrieve(
            args.query,
            top_k      = args.top_k,
            pub_filter = pub_nums,
            tax_year   = tax_year,
        )
        print(f"Retrieved {len(contexts)} chunks in {elapsed_ms:.0f} ms  [merge={merge_strategy}]\n{'─'*70}")
        for i, ctx in enumerate(contexts, 1):
            print(f"[{i}] Pub {ctx.reference} — {ctx.title}  [{ctx.retrieval_method}]")
            if ctx.chapter:
                print(f"    Chapter: {ctx.chapter}")
            if ctx.section:
                print(f"    Section: {ctx.section}")
            score_label = "RRF" if merge_strategy == "rrf" else "score"
            print(f"    Page: {ctx.page}  |  {score_label}: {ctx.score:.6f}")
            snippet = ctx.text[:300].replace("\n", " ")
            if len(ctx.text) > 300:
                snippet += "…"
            print(f"    {snippet}")
            print(f"{'─'*70}")
        return 0

    # Vector or BM25 mode — use Layer3Store directly
    with Layer3Store(dsn=args.pg_dsn) as store:
        if mode == "bm25":
            results = store.search_bm25(
                args.query,
                top_k       = args.top_k,
                pub_numbers = pub_nums,
                tax_year    = tax_year,
            )
        else:
            from taxflow_kb.layer3.embeddings import embed_query
            q_vec   = embed_query(args.query, api_key=api_key)
            results = store.search_similar(
                q_vec,
                top_k       = args.top_k,
                pub_numbers = pub_nums,
                tax_year    = tax_year,
            )

    if not results:
        print(f"No results found for mode={mode}.")
        return 0

    print(f"\nRetrieved {len(results)} chunks  [mode={mode}]\n{'─'*70}")
    for i, r in enumerate(results, 1):
        print(f"[{i}] Pub {r.pub_number} — {r.pub_title}")
        if r.chapter_title:
            print(f"    Chapter: {r.chapter_title}")
        if r.section_title:
            print(f"    Section: {r.section_title}")
        print(f"    Page: {r.page_start}  |  Score: {r.score:.4f}")
        snippet = r.text[:300].replace("\n", " ")
        if len(r.text) > 300:
            snippet += "…"
        print(f"    {snippet}")
        print(f"{'─'*70}")

    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Layer 5 command handlers — Evaluation infrastructure
# ──────────────────────────────────────────────────────────────────────────────

def cmd_generate_gold_set(args) -> int:
    """
    Sample chunks from the DB and use GPT-4o to draft Q&A pairs.
    Saves an unverified gold set JSON that a CPA should review.
    """
    import os
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store
    from taxflow_kb.layer5.gold_set_generator import generate_gold_set
    from taxflow_kb.layer5.models_layer5 import GoldSet

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1
    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    pub_numbers = getattr(args, "pub", None) or None
    out_path    = args.out

    # Load existing gold set if --append is set
    existing = None
    if getattr(args, "append", False) and Path(out_path).exists():
        existing = GoldSet.load(out_path)
        logger.info("Appending to existing gold set (%d entries)", existing.total)

    with Layer3Store(dsn=args.pg_dsn) as store:
        gold_set = generate_gold_set(
            store           = store,
            api_key         = api_key,
            pub_numbers     = pub_numbers,
            chunks_per_pub  = args.chunks_per_pub,
            pairs_per_chunk = args.pairs_per_chunk,
            tax_year        = args.tax_year,
            model           = args.model,
            existing        = existing,
        )

    gold_set.save(out_path)
    print(f"\n{gold_set.summary()}")
    print(f"\n✓ Gold set saved to: {out_path}")
    print(
        f"\nNext step: review and verify the entries.\n"
        f"  python cli.py review-gold-set --gold-set {out_path}\n"
        f"\nMark entries as verified with:\n"
        f"  python cli.py verify-gold-set --gold-set {out_path} "
        f"--verifier \"Your Name\""
    )
    return 0


def cmd_review_gold_set(args) -> int:
    """Print a summary and sample entries from a gold set file."""
    from taxflow_kb.layer5.models_layer5 import GoldSet

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\n{gold_set.summary()}")

    n_sample = min(args.sample, gold_set.total)
    if n_sample == 0:
        return 0

    import random
    sample = random.sample(gold_set.entries, n_sample)

    pub_filter = getattr(args, "pub", None)
    diff_filter = getattr(args, "difficulty", None)
    entries = gold_set.filter(pub=pub_filter, difficulty=diff_filter)

    print(f"\n{'─'*72}")
    print(f"Showing {min(n_sample, len(entries))} entry/entries "
          f"({'all' if not pub_filter and not diff_filter else 'filtered'}):\n")

    for e in entries[:n_sample]:
        status = "✓ verified" if e.is_verified else "⚠ unverified"
        print(f"[{e.short_id}] {status} | {e.expected_pub} | {e.difficulty} | "
              f"tags: {', '.join(e.topic_tags) or 'none'}")
        print(f"  Q: {e.question}")
        print(f"  A: {e.ground_truth[:200]}{'…' if len(e.ground_truth) > 200 else ''}")
        if e.notes:
            print(f"  Note: {e.notes}")
        print()

    unverified = gold_set.total - gold_set.verified_count
    if unverified:
        print(f"⚠  {unverified} entries still need CPA verification.\n"
              f"   Run: python cli.py verify-gold-set --gold-set {args.gold_set} "
              f"--verifier \"Your Name\"")
    return 0


def cmd_evaluate_generation(args) -> int:
    """
    Evaluate answer quality using an LLM-as-judge rubric.

    Runs the full CPAQueryAgent on each gold set entry, then calls GPT-5.4
    to score the answer on 5 tax-domain dimensions (faithfulness, correctness,
    citation accuracy, temporal accuracy, safe abstention).
    """
    import json as _json
    import os
    from taxflow_kb.layer4.agent import CPAQueryAgent
    from taxflow_kb.layer5.models_layer5 import GoldSet
    from taxflow_kb.layer5.generation_evaluator import evaluate_generation

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1
    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1
    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\nLoaded: {gold_set.summary()}\n")

    agent = CPAQueryAgent(
        pg_dsn  = args.pg_dsn,
        api_key = api_key,
        model   = args.model,
    )

    pub_filter = getattr(args, "pub", []) or []
    sample = getattr(args, "sample", None)
    report = evaluate_generation(
        gold_set          = gold_set,
        agent             = agent,
        api_key           = api_key,
        judge_model       = args.judge_model,
        agent_top_k       = args.top_k,
        pub_filter        = pub_filter if pub_filter else None,
        difficulty        = getattr(args, "difficulty", None),
        verified_only     = getattr(args, "verified_only", False),
        rate_limit_delay  = args.rate_limit_delay,
        sample            = sample,
        sample_seed       = getattr(args, "sample_seed", 42),
    )

    report.print_report()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            _json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport saved → {args.out}")

    if args.out_results:
        out_path = Path(args.out_results)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            for r in report.results:
                f.write(_json.dumps(r.to_dict()) + "\n")
        print(f"Per-question results → {args.out_results}")

    # Gate: pass rate < 75% is a red flag
    if report.pass_rate < 0.75:
        logger.warning(
            "Generation pass rate %.1f%% is below the 75%% target.", report.pass_rate * 100
        )
        return 1
    return 0


def cmd_patch_gold_set(args) -> int:
    """
    Expand gold_chunk_ids with adjacent chunk IDs (±window) without re-calling the LLM.
    Reads an existing gold set, looks up each chunk's neighbours in the DB,
    and writes the patched result.
    """
    from taxflow_kb.layer3.postgres_layer3 import Layer3Store
    from taxflow_kb.layer5.models_layer5 import GoldSet
    from taxflow_kb.layer5.gold_set_patcher import patch_adjacent_chunks

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1
    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\nLoaded: {gold_set.summary()}\n")

    with Layer3Store(dsn=args.pg_dsn) as store:
        n_patched, n_already = patch_adjacent_chunks(
            gold_set = gold_set,
            store    = store,
            window   = args.window,
        )

    out_path = args.out or args.gold_set   # default: overwrite in-place
    gold_set.save(out_path)

    print(f"Patched  : {n_patched} entries (added ±{args.window} adjacent chunk IDs)")
    print(f"Skipped  : {n_already} entries (already had multiple IDs)")
    print(f"Total    : {gold_set.total} entries")
    print(f"Saved to : {out_path}")

    # Show before/after gold_chunk_ids count distribution
    counts = {}
    for e in gold_set.entries:
        n = len(e.gold_chunk_ids)
        counts[n] = counts.get(n, 0) + 1
    print("\nGold chunk IDs per entry:")
    for k in sorted(counts):
        print(f"  {k} chunk(s): {counts[k]} entries")
    return 0


def cmd_filter_gold_set(args) -> int:
    """
    Remove questions from a gold set that are unfair for RAG evaluation.

    Filtered out:
    - Questions referencing SPECIFIC NAMED EXAMPLES ("In Example 9…", "Cameron and Jordan…")
      that require finding the exact chunk containing that specific illustration.
    - Questions about specific worksheet line numbers that only make sense with an exact chunk.
    - Questions where the gold_chunk_ids list is empty (no retrieval anchor).

    These questions are valid for testing a system with exact-match search but not
    for semantic RAG evaluation because the retriever has no reliable way to find
    one specific example among hundreds of similar chunks.
    """
    import re
    from taxflow_kb.layer5.models_layer5 import GoldSet

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    n_before = gold_set.total

    # Patterns that indicate a question references a specific named example/scenario
    SPECIFIC_PATTERNS = [
        r"\bExample \d+\b",          # "Example 9", "Example 12"
        r"\bexample \d+\b",
        r"In the .{3,40} example",   # "In the Cameron and Jordan example"
        r"In Example",
        r"in example",
        r"line \d+ of (the|this|your)",   # "line 1 of the EIC Worksheet"
        r"on line \d+",
        r"enter on line",
        r"what amount .{0,30}(enter|enters)",
        r"what .{0,20}(amount|figure|number).{0,20}(appears?|goes?|falls?)\b",
    ]
    COMPILED = [re.compile(p) for p in SPECIFIC_PATTERNS]

    kept   = []
    removed = []
    for entry in gold_set.entries:
        q = entry.question
        if any(pat.search(q) for pat in COMPILED):
            removed.append(entry)
        else:
            kept.append(entry)

    gold_set.entries = kept
    out_path = args.out or args.gold_set
    gold_set.save(out_path)

    print(f"\nFiltered gold set:")
    print(f"  Before : {n_before} entries")
    print(f"  Removed: {len(removed)} specific-example questions")
    print(f"  Kept   : {len(kept)} entries")
    print(f"  Saved  : {out_path}")

    if args.show_removed:
        print("\nRemoved questions:")
        for e in removed:
            print(f"  [{e.expected_pub}] {e.question[:120]}")
    return 0


def cmd_validate_gold_set(args) -> int:
    """Run V5.1 gold set quality gate."""
    from taxflow_kb.layer5.models_layer5 import GoldSet
    from taxflow_kb.layer5.validation.v5_1_gold_set import validate_gold_set

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\nLoaded: {gold_set.summary()}\n")

    result = validate_gold_set(gold_set)
    result.print_report()
    return 0 if result.passed else 1


def cmd_verify_gold_set(args) -> int:
    """
    Interactively mark gold set entries as CPA-verified.

    Prints each unverified entry and asks for a PASS / EDIT / SKIP decision.
    PASS marks the entry verified. EDIT opens an inline editor to correct the
    ground truth before verifying. SKIP leaves it unverified.
    """
    from taxflow_kb.layer5.models_layer5 import GoldSet

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    verifier = args.verifier
    print(f"\nLoaded {gold_set.total} entries ({gold_set.verified_count} already verified).")
    print(f"Verifying as: {verifier}\n")

    unverified = [e for e in gold_set.entries if not e.is_verified]
    if not unverified:
        print("All entries are already verified.")
        return 0

    # Apply pub/difficulty filter if requested
    pub_filter  = getattr(args, "pub",  None)
    diff_filter = getattr(args, "difficulty", None)
    if pub_filter:
        unverified = [e for e in unverified if e.expected_pub == pub_filter]
    if diff_filter:
        unverified = [e for e in unverified if e.difficulty == diff_filter]

    if not unverified:
        print("No unverified entries match the given filter.")
        return 0

    verified_count = 0
    for i, entry in enumerate(unverified):
        print(f"\n{'═'*72}")
        print(f"Entry {i+1}/{len(unverified)}  [{entry.short_id}]  Pub {entry.expected_pub}  {entry.difficulty}")
        print(f"Tags: {', '.join(entry.topic_tags) or 'none'}")
        print(f"\nQ: {entry.question}")
        print(f"\nA: {entry.ground_truth}")
        print(f"\n[P]ass  [E]dit ground truth  [S]kip  [Q]uit", end="  > ")

        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nInterrupted.")
            break

        if choice in ("q", "quit"):
            break
        elif choice in ("s", "skip", ""):
            print("  → skipped")
            continue
        elif choice in ("e", "edit"):
            print(f"  Current: {entry.ground_truth}")
            print("  New ground truth (press Enter to keep current):")
            new_gt = input("  > ").strip()
            if new_gt:
                entry.ground_truth = new_gt
            note = input("  Optional note (CPA comment): ").strip()
            entry.mark_verified(verifier, note=note or None)
            verified_count += 1
            print(f"  ✓ Verified (edited)")
        elif choice in ("p", "pass"):
            note = input("  Optional note (Enter to skip): ").strip()
            entry.mark_verified(verifier, note=note or None)
            verified_count += 1
            print(f"  ✓ Verified")

    gold_set.save(args.gold_set)
    print(f"\nSaved. Verified {verified_count} entries in this session.")
    print(f"Total verified: {gold_set.verified_count}/{gold_set.total}")
    return 0


def cmd_re_embed(args) -> int:
    """
    Re-embed one or more publications with the current (or specified) embedding
    model, optionally applying chunk enrichment for publications with tabular
    or worksheet-heavy content (Pub 596, Pub 525).

    Steps:
      1. Load chunk text for the requested pub(s) from the database.
      2. Optionally apply chunk_enrichment.enrich_for_embedding() to each chunk
         so that the embedding input includes a natural-language summary header.
      3. Call the OpenAI Embeddings API using the configured model.
      4. Write the new vectors back to the publication_chunks table.
      5. Rebuild the IVFFlat index to pick up the new vectors.

    Example:
        python cli.py re-embed \\
          --pub 596 --pub 525 \\
          --pg-dsn "postgresql://taxflow:taxflow_dev@localhost:5432/taxflow"
    """
    import os
    from taxflow_kb.layer3.postgres_layer3  import Layer3Store
    from taxflow_kb.layer3.embeddings       import embed_chunks, EMBEDDING_MODEL
    from taxflow_kb.layer3.chunk_enrichment import enrich_for_embedding

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1

    pub_numbers = args.pub   # list[str]
    if not pub_numbers:
        logger.error("At least one --pub <number> is required.")
        return 1

    model    = getattr(args, "model", EMBEDDING_MODEL) or EMBEDDING_MODEL
    enrich   = not args.no_enrich
    rebuild  = not args.no_index

    overall_ok = True

    with Layer3Store(dsn=args.pg_dsn) as store:
        for pub_number in pub_numbers:
            logger.info(
                "Re-embedding Pub %s  model=%s  enrichment=%s",
                pub_number, model, enrich,
            )

            chunks = store.load_chunks_for_pub(pub_number)
            if not chunks:
                logger.warning("No chunks found for Pub %s — skipping.", pub_number)
                continue

            # Apply optional chunk enrichment: swap chunk.text for an
            # enriched version ONLY for the embedding step; the stored text
            # in the DB is not modified.
            if enrich:
                enriched_count = 0
                for c in chunks:
                    enriched = enrich_for_embedding(c, pub_number)
                    if enriched != c.text:
                        c.text = enriched    # embedding input only
                        enriched_count += 1
                logger.info(
                    "  Enriched %d/%d chunks for Pub %s",
                    enriched_count, len(chunks), pub_number,
                )

            # Embed (force=True since all chunks already have vectors from
            # the previous model — we want to replace them).
            try:
                embed_chunks(chunks, api_key=api_key, model=model, force=True)
            except Exception as exc:
                logger.error("Embedding failed for Pub %s: %s", pub_number, exc)
                overall_ok = False
                continue

            # Write new vectors back to the DB.
            updated = store.upsert_embeddings(chunks)
            logger.info(
                "  Updated %d embedding vectors for Pub %s.", updated, pub_number
            )
            store.finalize_embedding(pub_number, updated)

        # Rebuild the IVFFlat ANN index after all pubs are re-embedded.
        # MUST use force=True to drop the stale index first — IVFFlat stores
        # k-means centroids computed at build time.  After switching embedding
        # models the old centroids route queries into wrong cluster partitions,
        # collapsing HR to near-zero.  force=True drops then recreates.
        if rebuild:
            logger.info("Force-rebuilding IVFFlat index (dropping stale index first) …")
            try:
                store.create_ivfflat_index(force=True)
                logger.info("Index rebuilt.")
            except Exception as exc:
                logger.warning("Could not rebuild index: %s", exc)

    return 0 if overall_ok else 1


def cmd_evaluate_retrieval(args) -> int:
    """
    Evaluate retriever quality against a gold set.

    Computes Hit Rate @ k, MRR, Recall @ k, and Publication Accuracy,
    broken down by difficulty and publication.
    """
    import json as _json
    import os
    from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever
    from taxflow_kb.layer5.models_layer5 import GoldSet
    from taxflow_kb.layer5.retrieval_evaluator import evaluate_retrieval

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1
    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1
    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\nLoaded: {gold_set.summary()}\n")

    merge_strategy = getattr(args, "merge_strategy", "augment") or "augment"
    no_bm25 = getattr(args, "no_bm25", False)
    retriever = HierarchicalRetriever(
        pg_dsn         = args.pg_dsn,
        api_key        = api_key,
        enable_bm25    = not no_bm25,
        merge_strategy = merge_strategy,
    )
    pub_filter = getattr(args, "pub", []) or []
    report = evaluate_retrieval(
        gold_set       = gold_set,
        retriever      = retriever,
        top_k          = args.top_k,
        pub_filter     = pub_filter if pub_filter else None,
        difficulty     = getattr(args, "difficulty", None),
        verified_only  = getattr(args, "verified_only", False),
    )

    report.print_report()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            _json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport saved → {args.out}")

    # Gate: HR@k < 0.50 is a red flag
    hr = report.hit_rate
    if hr < 0.50:
        logger.warning(
            "Hit Rate %.2f%% is below the 50%% target — consider re-embedding "
            "or increasing chunk overlap.", hr * 100
        )
        return 1
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Coverage report
# ──────────────────────────────────────────────────────────────────────────────

def cmd_coverage(args) -> int:
    """Print multi-year publication coverage report."""
    from taxflow_kb.layer3.publication_registry import get_registry

    reg = get_registry()
    gaps_only = getattr(args, "gaps_only", False)
    years = getattr(args, "years", []) or []

    if gaps_only:
        gaps = reg.coverage_gaps(years or None)
        if not gaps:
            print("No coverage gaps found.")
            return 0
        print("Publications with coverage gaps:")
        for pn, missing in sorted(gaps.items()):
            meta = reg.get(pn)
            title = meta.short_title if meta else "?"
            print(f"  Pub {pn} ({title}): missing {', '.join(str(y) for y in missing)}")
        return 0

    print(reg.coverage_summary())
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Layer 4 command handlers
# ──────────────────────────────────────────────────────────────────────────────

def cmd_ask(args) -> int:
    """Answer a CPA tax question using the full retrieval + synthesis pipeline."""
    import os
    from taxflow_kb.layer4.agent import CPAQueryAgent

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required. Pass --api-key or set the env var.")
        return 1

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    pub_filter = getattr(args, "pub", None) or None

    agent = CPAQueryAgent(
        pg_dsn  = args.pg_dsn,
        api_key = api_key,
        model   = getattr(args, "model", "gpt-4o-mini"),
    )

    synthesize = not getattr(args, "no_synthesize", False)

    # Agent always defaults to current year when None is passed;
    # cross-year comparison queries are handled automatically via
    # separate per-year retrievals inside the agent.
    ask_tax_year = getattr(args, "tax_year", None) or None

    result = agent.query(
        args.question,
        top_k      = args.top_k,
        pub_filter = pub_filter,
        tax_year   = ask_tax_year,
        synthesize = synthesize,
    )

    show_chunks = getattr(args, "show_chunks", False)
    result.print_report(show_contexts=show_chunks)

    if getattr(args, "json_out", False):
        import json
        out = {
            "query"   : result.query,
            "answer"  : result.answer,
            "sources" : result.sources,
            "contexts": [
                {
                    "pub"    : c.reference,
                    "title"  : c.title,
                    "page"   : c.page,
                    "score"  : round(c.score, 4),
                    "chapter": c.chapter,
                    "section": c.section,
                    "text"   : c.text[:500],
                }
                for c in result.contexts
            ],
            "stats": {
                "retrieval_ms"     : round(result.retrieval_ms),
                "synthesis_ms"     : round(result.synthesis_ms),
                "model"            : result.model_used,
                "prompt_tokens"    : result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
        }
        print(json.dumps(out, indent=2))

    return 1 if result.error else 0


def cmd_validate_agent(args) -> int:
    """Run V4.1 CPA agent functional validation (5 real queries)."""
    import os
    from taxflow_kb.layer4.agent import CPAQueryAgent
    from taxflow_kb.layer4.validation.v4_1_agent import validate_agent

    api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    agent = CPAQueryAgent(
        pg_dsn  = args.pg_dsn,
        api_key = api_key,
        model   = getattr(args, "model", "gpt-4o-mini"),
    )

    v = validate_agent(agent, top_k=args.top_k)
    v.print_report()
    return 0 if v.passed else 1


# ──────────────────────────────────────────────────────────────────────────────
# IRS Publication Download
# ──────────────────────────────────────────────────────────────────────────────

def cmd_download_publications(args) -> int:
    """Download IRS publication PDFs from IRS.gov."""
    from taxflow_kb.ingestion.irs_download import IRSDownloader

    dl = IRSDownloader(
        output_dir=getattr(args, "output_dir", None),
        force=args.force,
    )

    mode = args.mode
    years = None
    if args.years:
        years = [int(y.strip()) for y in args.years.split(",")]

    if mode == "single":
        if not args.pub_number:
            logger.error("--pub-number is required for single download mode.")
            return 1
        tax_year = args.tax_year
        result = dl.download_publication(args.pub_number, tax_year)
        print(result)
        return 0 if result.success else 1

    elif mode == "tier":
        tier = args.tier or 2
        results = dl.download_tier(tier, years)
    elif mode == "missing":
        results = dl.download_missing(years)
    elif mode == "all":
        results = dl.download_all_registered(years)
    elif mode == "status":
        status = dl.get_status()
        print(f"\n{'='*60}")
        print(f"  IRS Publication Download Status")
        print(f"{'='*60}")
        print(f"  Registered publications: {status['total_registered']}")
        print(f"  Tax years: {status['years']}")
        print(f"  Downloaded: {status['downloaded']}")
        print(f"  Missing:    {status['missing']}")
        for tier_num, tier_data in sorted(status['tiers'].items()):
            print(f"\n  Tier {tier_num}: {tier_data['publications']} publications")
            print(f"    Downloaded: {tier_data['downloaded']}")
            print(f"    Missing:    {tier_data['missing']}")
        if status['missing_details'] and len(status['missing_details']) <= 30:
            print(f"\n  Missing files:")
            for f in status['missing_details']:
                print(f"    - {f}")
        print()
        return 0
    else:
        logger.error("Unknown mode: %s", mode)
        return 1

    # Print summary for batch modes
    ok = sum(1 for r in results if r.success and not r.skipped)
    skip = sum(1 for r in results if r.skipped)
    fail = sum(1 for r in results if not r.success)
    print(f"\nDownload complete: {ok} new, {skip} skipped, {fail} failed")
    if fail:
        for r in results:
            if not r.success:
                print(f"  FAILED: p{r.pub_number}_{r.tax_year} -- {r.error}")
    return 1 if fail else 0


# ──────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
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
                       help="Apply schema/postgres_layer3.sql before ingesting")
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

    # ── Layer 4: validate-agent ───────────────────────────────────────────────
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
