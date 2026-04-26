"""
taxkb/cli/instructions_commands.py

Layer 2 command handlers: cmd_ingest_instructions, cmd_validate_instructions
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("taxflow.cli")


def cmd_ingest_instructions(args) -> int:
    from taxkb.instructions.html_parser import parse_instruction_html

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
        from taxkb.instructions.neo4j_store import InstructionGraphStore
        driver = GraphDatabase.driver(
            args.neo4j_uri,
            auth=(args.neo4j_user, args.neo4j_password),
        )
        ingestion = InstructionGraphStore(driver)
        neo4j_stats = ingestion.ingest(result)
        driver.close()
        logger.info("Neo4j: %s", neo4j_stats)

    if args.pg_dsn:
        import psycopg2
        from taxkb.instructions.postgres_store import InstructionStore
        conn = psycopg2.connect(args.pg_dsn)
        pg   = InstructionStore(conn)
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
    from taxkb.instructions.html_parser import parse_instruction_html
    from taxkb.instructions.validation import structural as v2_structural, link_coverage

    logger.info("Parsing HTML for validation: %s", args.html)
    result = parse_instruction_html(
        args.html, form_type=args.form_type, tax_year=args.tax_year,
    )

    overall_pass = True
    step = args.step.lower()

    if step in ("all", "v2.1"):
        r = v2_structural.run(result)
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
        r = link_coverage.run(result)
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
