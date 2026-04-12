"""
cli/publications_commands.py

Layer 3 command handlers: cmd_ingest_publications, cmd_validate_publications,
cmd_search, cmd_build_index, cmd_add_bm25_index, cmd_add_hierarchy_columns,
cmd_re_embed, cmd_download_publications, cmd_coverage
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("taxflow.cli")


def cmd_ingest_publications(args) -> int:
    """
    Parse one or more IRS publication PDFs, embed with OpenAI, and load into
    PostgreSQL (pgvector).
    """
    import os
    from tax_brain.publications.pdf_parser    import parse_publication_pdf
    from tax_brain.publications.store import PublicationStore

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

    with PublicationStore(dsn=dsn) as store:
        if args.init_schema:
            schema_path = Path(__file__).resolve().parent.parent / "schema" / "postgres_layer3.sql"
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
    from tax_brain.publications.pdf_parser import parse_publication_pdf

    step = args.step.lower()
    overall_pass = True

    # -- V3.1 -- parse PDFs and check structural integrity
    if step in ("all", "v3.1"):
        from tax_brain.publications.validation.structural import validate_structural

        if not args.pdf:
            if step == "v3.1":
                logger.error("V3.1 requires --pdf (one or more PDF paths).")
                return 1
            else:
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

    # -- V3.2 -- database coverage check
    if step in ("all", "v3.2"):
        from tax_brain.publications.validation.coverage import validate_coverage
        from tax_brain.publications.store import PublicationStore

        if not args.pg_dsn:
            logger.error("V3.2 requires --pg-dsn.")
            return 1

        with PublicationStore(dsn=args.pg_dsn) as store:
            v = validate_coverage(
                store,
                require_embeddings=args.require_embeddings,
            )
        v.print_report()
        if not v.passed:
            overall_pass = False

    # -- V3.3 -- retrieval quality probes
    if step in ("all", "v3.3"):
        from tax_brain.publications.validation.retrieval import validate_retrieval
        from tax_brain.publications.store import PublicationStore

        if not args.pg_dsn:
            logger.error("V3.3 requires --pg-dsn.")
            return 1

        api_key = getattr(args, "api_key", None) or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("V3.3 requires OPENAI_API_KEY or --api-key.")
            return 1

        with PublicationStore(dsn=args.pg_dsn) as store:
            v = validate_retrieval(store, api_key=api_key)
        v.print_report()
        if not v.passed:
            overall_pass = False

    return 0 if overall_pass else 1


def cmd_build_index(args) -> int:
    """Create (or force-rebuild) the IVFFlat ANN index on the embedding column."""
    from tax_brain.publications.store import PublicationStore

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    force = getattr(args, "force", False)
    logger.info(
        "Building IVFFlat index (lists=%d, force=%s) …", args.lists, force
    )
    with PublicationStore(dsn=args.pg_dsn) as store:
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
    """
    from tax_brain.publications.store import PublicationStore

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    logger.info("Adding BM25 index to publication_chunks …")
    with PublicationStore(dsn=args.pg_dsn) as store:
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
    """
    from tax_brain.publications.store import PublicationStore

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    logger.info("Adding hierarchy columns to publication_chunks …")
    with PublicationStore(dsn=args.pg_dsn) as store:
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
    from tax_brain.publications.store import PublicationStore

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
        from tax_brain.config import get_settings
        tax_year = get_settings().default_tax_year
        logger.debug("No --tax-year specified; defaulting to %d", tax_year)

    year_label = str(tax_year) if tax_year else "ALL (debug)"
    print(f"\nMode: {mode.upper()}  |  Query: {args.query!r}  |  Year: {year_label}")

    if mode == "hybrid":
        # Use TaxBrainRetriever (navigate -> vector + BM25 -> ontology augment)
        merge_strategy = getattr(args, "merge_strategy", "augment") or "augment"
        from tax_brain.agent.retriever import TaxBrainRetriever
        retriever = TaxBrainRetriever(
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

    # Vector or BM25 mode — use PublicationStore directly
    with PublicationStore(dsn=args.pg_dsn) as store:
        if mode == "bm25":
            results = store.search_bm25(
                args.query,
                top_k       = args.top_k,
                pub_numbers = pub_nums,
                tax_year    = tax_year,
            )
        else:
            from tax_brain.publications.embeddings import embed_query
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


def cmd_re_embed(args) -> int:
    """
    Re-embed one or more publications with the current (or specified) embedding
    model, optionally applying chunk enrichment.
    """
    import os
    from tax_brain.publications.store  import PublicationStore
    from tax_brain.publications.embeddings       import embed_chunks, EMBEDDING_MODEL
    from tax_brain.publications.chunk_enrichment import enrich_for_embedding

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

    with PublicationStore(dsn=args.pg_dsn) as store:
        for pub_number in pub_numbers:
            logger.info(
                "Re-embedding Pub %s  model=%s  enrichment=%s",
                pub_number, model, enrich,
            )

            chunks = store.load_chunks_for_pub(pub_number)
            if not chunks:
                logger.warning("No chunks found for Pub %s — skipping.", pub_number)
                continue

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

            try:
                embed_chunks(chunks, api_key=api_key, model=model, force=True)
            except Exception as exc:
                logger.error("Embedding failed for Pub %s: %s", pub_number, exc)
                overall_ok = False
                continue

            updated = store.upsert_embeddings(chunks)
            logger.info(
                "  Updated %d embedding vectors for Pub %s.", updated, pub_number
            )
            store.finalize_embedding(pub_number, updated)

        if rebuild:
            logger.info("Force-rebuilding IVFFlat index (dropping stale index first) …")
            try:
                store.create_ivfflat_index(force=True)
                logger.info("Index rebuilt.")
            except Exception as exc:
                logger.warning("Could not rebuild index: %s", exc)

    return 0 if overall_ok else 1


def cmd_download_publications(args) -> int:
    """Download IRS publication PDFs from IRS.gov."""
    from tax_brain.rules.irs_download import IRSDownloader

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


def cmd_coverage(args) -> int:
    """Print multi-year publication coverage report."""
    from tax_brain.publications.registry import get_registry

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
