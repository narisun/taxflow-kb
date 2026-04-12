"""
cli/evaluation_commands.py

Layer 5 command handlers: cmd_generate_gold_set, cmd_review_gold_set,
cmd_filter_gold_set, cmd_patch_gold_set, cmd_validate_gold_set,
cmd_verify_gold_set, cmd_eval_retrieval, cmd_eval_generation
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("taxflow.cli")


def cmd_generate_gold_set(args) -> int:
    """
    Sample chunks from the DB and use GPT-4o to draft Q&A pairs.
    Saves an unverified gold set JSON that a CPA should review.
    """
    import os
    from tax_brain.publications.store import PublicationStore
    from tax_brain.evaluation.gold_set_generator import generate_gold_set
    from tax_brain.evaluation.models import GoldSet

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

    with PublicationStore(dsn=args.pg_dsn) as store:
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
    from tax_brain.evaluation.models import GoldSet

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
    """
    import json as _json
    import os
    from tax_brain.factories import create_agent
    from tax_brain.config import get_settings
    from tax_brain.evaluation.models import GoldSet
    from tax_brain.evaluation.generation_evaluator import evaluate_generation

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

    settings = get_settings()
    settings.pg_dsn = args.pg_dsn
    settings.synthesis_model = args.model
    agent = create_agent(settings=settings, api_key=api_key)

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
    Expand gold_chunk_ids with adjacent chunk IDs (+-window) without re-calling the LLM.
    """
    from tax_brain.publications.store import PublicationStore
    from tax_brain.evaluation.models import GoldSet
    from tax_brain.evaluation.gold_set_patcher import patch_adjacent_chunks

    if not Path(args.gold_set).exists():
        logger.error("Gold set file not found: %s", args.gold_set)
        return 1
    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    gold_set = GoldSet.load(args.gold_set)
    print(f"\nLoaded: {gold_set.summary()}\n")

    with PublicationStore(dsn=args.pg_dsn) as store:
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
    """
    import re
    from tax_brain.evaluation.models import GoldSet

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
    from tax_brain.evaluation.models import GoldSet
    from tax_brain.evaluation.validation.gold_set import validate_gold_set

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
    """
    from tax_brain.evaluation.models import GoldSet

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


def cmd_evaluate_retrieval(args) -> int:
    """
    Evaluate retriever quality against a gold set.
    """
    import json as _json
    import os
    from tax_brain.agent.retriever import TaxBrainRetriever
    from tax_brain.evaluation.models import GoldSet
    from tax_brain.evaluation.retrieval_evaluator import evaluate_retrieval

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
    retriever = TaxBrainRetriever(
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
