"""
cli/rules_commands.py

Layer 1 command handlers: cmd_ingest, cmd_validate, cmd_sample, cmd_score, cmd_diff
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("taxflow.cli")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_and_ast(csv_path: str):
    """Parse CSV and run AST parser on all rules. Returns (rules, parse_result)."""
    from tax_brain.rules.csv_parser import CSVParser
    from tax_brain.rules.ast_parser import parse_expression
    from tax_brain.models import ASTNodeType

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
        from tax_brain.rules.neo4j_store import RuleGraphStore
        logger.info("Loading into Neo4j: %s", args.neo4j_uri)
        ingestor = RuleGraphStore(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        counts = ingestor.ingest(rules)
        ingestor.close()
        logger.info("Neo4j: %s", counts)

    if args.pg_dsn:
        from tax_brain.rules.postgres_store import RuleStore
        logger.info("Loading into PostgreSQL…")
        pg = RuleStore(args.pg_dsn)
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
        from tax_brain.rules.validation import structural as v1_structural
        from tax_brain.rules.validation.structural import StructuralCheckConfig
        cfg = StructuralCheckConfig(
            expected_row_count=args.expected_rows,
        )
        report = v1_structural.run(rules, parse_result, cfg)
        _print_report(report)
        overall_passed = overall_passed and report.passed

    if step in ("all", "v1.3"):
        from tax_brain.rules.validation import test_replay as v1_test_replay
        from tax_brain.rules.validation.test_replay import build_synthetic_test_cases
        test_cases = build_synthetic_test_cases()
        report, _ = v1_test_replay.run(rules, test_cases)
        _print_report(report)
        overall_passed = overall_passed and report.passed

    if not overall_passed:
        logger.error("One or more validation steps FAILED. Do not proceed to Layer 2.")
        return 1
    logger.info("All validation steps PASSED.")
    return 0


def cmd_sample(args) -> int:
    rules, _ = _parse_and_ast(args.csv)
    from tax_brain.rules.validation import spot_check
    counts = spot_check.generate_sample(rules, args.out)
    print("\nSpot-check sample generated:")
    for cat, n in sorted(counts.items()):
        print(f"  {cat:25s}: {n} rules")
    print(f"\nFiles: {args.out}.csv  and  {args.out}.json")
    print("Next: have the tax domain expert annotate the CSV, then run:")
    print(f"  python cli.py score --annotated {args.out}.json")
    return 0


def cmd_score(args) -> int:
    from tax_brain.rules.validation import spot_check
    report = spot_check.score_review(args.annotated)
    _print_report(report)
    return 0 if report.passed else 1


def cmd_diff(args) -> int:
    old_rules, _ = _parse_and_ast(args.old)
    new_rules, _ = _parse_and_ast(args.new)
    from tax_brain.rules.validation import regression
    from tax_brain.rules.validation.test_replay import build_synthetic_test_cases
    test_cases = build_synthetic_test_cases()
    diffs, report = regression.run(
        old_rules, new_rules, test_cases,
        report_dir=args.report_dir,
    )
    _print_report(report)
    from tax_brain.models import ChangeType
    for ct in (ChangeType.ADDED, ChangeType.REMOVED, ChangeType.MODIFIED):
        group = [d for d in diffs if d.change_type == ct]
        if group:
            print(f"{ct.value} ({len(group)}):")
            for d in group[:10]:
                print(f"  {d.rule_id}  →  {', '.join(d.changed_fields) or 'n/a'}")
    return 0 if report.passed else 1
