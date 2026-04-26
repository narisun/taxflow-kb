#!/usr/bin/env python3
"""
taxkb/scripts/ingest_all_pubs.py

Master ingestion script — downloads, parses, embeds, and ingests ALL
publications needed by the golden-set evaluation.

Three phases:
  Phase 1: Download all missing PDFs from IRS.gov
  Phase 2: Ingest all publications (parse → chunk → embed → store)
  Phase 3: Generate summary chunks for pubs that lack them

Usage:
    # Full pipeline (download + ingest + summaries)
    python taxkb/taxkb/scripts/ingest_all_pubs.py

    # Download only (no DB required)
    python taxkb/taxkb/scripts/ingest_all_pubs.py --download-only

    # Ingest only (skip download, assumes PDFs already present)
    python taxkb/taxkb/scripts/ingest_all_pubs.py --ingest-only

    # Dry run — show what would be done
    python taxkb/taxkb/scripts/ingest_all_pubs.py --dry-run

    # Skip embeddings (text-only, no OpenAI cost)
    python taxkb/taxkb/scripts/ingest_all_pubs.py --skip-embedding

    # Ingest specific pubs only
    python taxkb/taxkb/scripts/ingest_all_pubs.py --pubs 17 535 560 541

    # Force re-ingest even if already in DB
    python taxkb/taxkb/scripts/ingest_all_pubs.py --force

Environment:
    PG_DSN          PostgreSQL DSN (or use --pg-dsn flag)
    OPENAI_API_KEY  OpenAI API key (or use --api-key flag)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import psycopg2

# ── Setup path ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from taxkb.publications.registry import get_registry, PublicationMeta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── IRS URL patterns ────────────────────────────────────────────────────────
# Publications: https://www.irs.gov/pub/irs-pdf/p{number}.pdf
# Form instructions: https://www.irs.gov/pub/irs-pdf/i{number}.pdf
# Forms: https://www.irs.gov/pub/irs-pdf/f{number}.pdf
# Prior-year pubs: https://www.irs.gov/pub/irs-prior/p{number}--{year}.pdf

# Map pub_numbers to their IRS PDF URL patterns.
# Most are publications (p-prefix), some are form instructions (i-prefix).
FORM_INSTRUCTION_PUBS = {
    # These "pubs" are actually form instructions on the IRS website
    "1040":   "i1040gi",    # Instructions for Form 1040 (general instructions bundle)
    "1099":   "i1099gi",    # General Instructions for 1099-series
    "W-2":    "iw2w3",      # Instructions for W-2 and W-3
    "6765":   "i6765",      # Instructions for Form 6765
    "8812":   "i1040s8",    # Instructions for Schedule 8812 (renamed to "s8" in 2025)
    "8962":   "i8962",      # Instructions for Form 8962
    "8995-A": "i8995a",     # Instructions for Form 8995-A
    # Schedule 1-A: the form is at f1040s1a.pdf; instructions are in the 1040 bundle.
    # We download the form itself which contains enough context for chunking.
    "1-A":    "f1040s1a",   # Schedule 1-A form (Additional Deductions incl. tips/overtime)
}

# Discontinued publications — use the last available year from irs-prior
DISCONTINUED_PUB_URLS = {
    # Pub 536 discontinued after 2023; use 2023 version
    "536": "https://www.irs.gov/pub/irs-prior/p536--2023.pdf",
}

# Some pubs have non-standard IRS PDF names
CUSTOM_PDF_NAMES = {
    "15-B":  "p15b",        # Pub 15-B uses "p15b" not "p15-b"
    "590a":  "p590a",       # Already handled correctly
    "590b":  "p590b",       # Already handled correctly
}

# Pubs that don't have downloadable PDFs (handled by other layers)
# NOTE: MeF was removed from SKIP_DOWNLOAD — a synthetic PDF (pMeF_2025.pdf)
# with business rule crosswalk content is now in data/publications/.
SKIP_DOWNLOAD = set()

# Trump Account (Form 4547) is a new OBBBA form — may not be on IRS.gov yet.
# We'll create a synthetic placeholder if download fails.
OBBBA_NEW_FORMS = {"4547"}


def build_irs_url(pub_number: str, tax_year: int) -> str:
    """Build the IRS.gov PDF download URL for a publication."""
    # Check for discontinued pubs with fixed URLs
    if pub_number in DISCONTINUED_PUB_URLS:
        return DISCONTINUED_PUB_URLS[pub_number]

    if pub_number in FORM_INSTRUCTION_PUBS:
        pdf_name = FORM_INSTRUCTION_PUBS[pub_number]
        if tax_year == 2025:
            return f"https://www.irs.gov/pub/irs-pdf/{pdf_name}.pdf"
        else:
            return f"https://www.irs.gov/pub/irs-prior/{pdf_name}--{tax_year}.pdf"

    # Standard publication
    pdf_name = CUSTOM_PDF_NAMES.get(pub_number, f"p{pub_number}")
    if tax_year == 2025:
        return f"https://www.irs.gov/pub/irs-pdf/{pdf_name}.pdf"
    else:
        return f"https://www.irs.gov/pub/irs-prior/{pdf_name}--{tax_year}.pdf"


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF from IRS.gov. Returns True on success."""
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    if dest.exists():
        logger.info("  ✓ Already downloaded: %s", dest.name)
        return True

    logger.info("  ↓ Downloading %s ...", url)
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TaxFlowAI/1.0)"
        })
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        logger.info("  ✓ Downloaded: %s (%d KB)", dest.name, len(data) // 1024)
        time.sleep(1.0)  # polite delay
        return True
    except (HTTPError, URLError, OSError) as e:
        logger.warning("  ✗ Download failed: %s — %s", url, e)
        return False


def get_pdf_path(pub_number: str, tax_year: int, data_dir: Path) -> Path:
    """Get the expected local path for a publication PDF."""
    # For discontinued pubs with fixed URLs, the file is still stored with
    # the registered tax_year suffix.
    return data_dir / f"p{pub_number}_{tax_year}.pdf"


# Also check if the 1040 instructions PDF was already downloaded under a
# different pub_number (since 1040 and 1-A share the same instructions bundle).
def _find_existing_pdf(pub_number: str, tax_year: int, data_dir: Path) -> Path | None:
    """Try to find an existing PDF for a pub, checking alternate names."""
    primary = get_pdf_path(pub_number, tax_year, data_dir)
    if primary.exists():
        return primary

    # Check non-year-suffixed version (e.g., p17.pdf)
    alt = data_dir / f"p{pub_number}.pdf"
    if alt.exists():
        return alt

    return None


def phase1_download(pubs_to_process: list[tuple[str, int]], data_dir: Path, dry_run: bool) -> dict:
    """Phase 1: Download all missing PDFs from IRS.gov."""
    print("\n" + "=" * 72)
    print("  PHASE 1: DOWNLOAD MISSING PDFs")
    print("=" * 72)

    results = {"downloaded": 0, "skipped": 0, "failed": 0, "skip_no_pdf": 0}

    for pub_number, tax_year in pubs_to_process:
        if pub_number in SKIP_DOWNLOAD:
            logger.info("  → Skipping %s (no downloadable PDF)", pub_number)
            results["skip_no_pdf"] += 1
            continue

        dest = get_pdf_path(pub_number, tax_year, data_dir)
        url = build_irs_url(pub_number, tax_year)

        if dest.exists():
            results["skipped"] += 1
            continue

        if dry_run:
            logger.info("  [DRY RUN] Would download: %s → %s", url, dest.name)
            continue

        if download_pdf(url, dest):
            results["downloaded"] += 1
        else:
            # For new OBBBA forms, create a placeholder
            if pub_number in OBBBA_NEW_FORMS:
                logger.info("  → Creating placeholder for new OBBBA form %s", pub_number)
                _create_placeholder_pdf(pub_number, tax_year, dest)
                results["downloaded"] += 1
            else:
                results["failed"] += 1

    print(f"\n  Downloaded: {results['downloaded']}, "
          f"Already had: {results['skipped']}, "
          f"Failed: {results['failed']}, "
          f"No PDF: {results['skip_no_pdf']}")
    return results


def _create_placeholder_pdf(pub_number: str, tax_year: int, dest: Path):
    """Create a minimal text file as a placeholder for forms not yet on IRS.gov."""
    registry = get_registry()
    meta = registry.get(pub_number)
    title = meta.title if meta else f"IRS Form/Publication {pub_number}"
    description = meta.description if meta else ""
    tags = ", ".join(meta.topic_tags) if meta else ""

    # Write as a plain text file (our parser handles text extraction)
    text = f"""IRS {title}
Tax Year {tax_year}

{description}

This is a placeholder for {pub_number} which may not yet be published on IRS.gov.
The content should be updated once the official form/instructions are released.

Topics: {tags}

Related forms: {', '.join(meta.related_forms) if meta else 'N/A'}
"""
    # Actually we need a valid PDF for the parser. Let's skip placeholders
    # and just note them as missing.
    logger.warning("  ⚠ Cannot create placeholder PDF for %s — needs manual download", pub_number)


def phase2_ingest(
    pubs_to_process: list[tuple[str, int]],
    data_dir: Path,
    pg_dsn: str,
    api_key: str,
    skip_embedding: bool,
    force: bool,
    dry_run: bool,
) -> dict:
    """Phase 2: Ingest all publications into PostgreSQL.

    Uses the high-level PublicationStore.ingest() pipeline which handles:
      parse_result → anchor chunks → embed → upsert → finalize
    """
    print("\n" + "=" * 72)
    print("  PHASE 2: INGEST PUBLICATIONS")
    print("=" * 72)

    results = {"ingested": 0, "skipped": 0, "failed": 0, "no_pdf": 0}

    if dry_run:
        for pub_number, tax_year in pubs_to_process:
            pdf_path = get_pdf_path(pub_number, tax_year, data_dir)
            exists = pdf_path.exists()
            logger.info("  [DRY RUN] %s year=%d — PDF %s",
                        pub_number, tax_year,
                        f"exists ({pdf_path.stat().st_size // 1024} KB)" if exists else "MISSING")
        return results

    # Import ingestion pipeline
    from taxkb.publications.pdf_parser import parse_publication_pdf
    from taxkb.publications.store import PublicationStore

    # Init schema once
    schema_path = str(PROJECT_ROOT / "schema" / "postgres_layer3.sql")
    _schema_conn = psycopg2.connect(pg_dsn)
    try:
        with PublicationStore(conn=_schema_conn) as store:
            store.apply_schema(schema_path)
            logger.info("  Schema initialized")

            # Check what's already ingested
            existing_pubs = set()
            if not force:
                try:
                    with _schema_conn.cursor() as cur:
                        cur.execute(
                            "SELECT DISTINCT pub_number || '::' || tax_year "
                            "FROM irs_kb.publications"
                        )
                        existing_pubs = {row[0] for row in cur.fetchall()}
                except Exception:
                    pass  # table may not exist yet
    finally:
        _schema_conn.close()

    for pub_number, tax_year in pubs_to_process:
        pub_key = f"{pub_number}::{tax_year}"

        if pub_number in SKIP_DOWNLOAD:
            logger.info("  → Skipping %s (no PDF — handled by other layers)", pub_number)
            results["no_pdf"] += 1
            continue

        pdf_path = _find_existing_pdf(pub_number, tax_year, data_dir)

        if pdf_path is None:
            logger.warning("  ✗ No PDF for %s year=%d — skipping", pub_number, tax_year)
            results["no_pdf"] += 1
            continue

        if not force and pub_key in existing_pubs:
            logger.info("  ✓ Already ingested: %s year=%d", pub_number, tax_year)
            results["skipped"] += 1
            continue

        logger.info("  → Ingesting %s year=%d from %s ...",
                    pub_number, tax_year, pdf_path.name)
        t0 = time.time()

        try:
            # Step 1: Parse PDF
            parse_result = parse_publication_pdf(
                pdf_path=str(pdf_path),
                pub_number=pub_number,
                tax_year=tax_year,
            )

            if not parse_result.parse_success:
                logger.error("  ✗ Parse failed for %s: %s",
                            pub_number, parse_result.errors)
                results["failed"] += 1
                continue

            logger.info("    Parsed: %d chunks from %d pages",
                        len(parse_result.chunks),
                        parse_result.publication.page_count)

            # Step 2: Use the high-level store.ingest() pipeline
            # This handles: anchor generation → upsert pub → upsert chunks →
            #               embed → upsert embeddings → finalize
            _ingest_conn = psycopg2.connect(pg_dsn)
            try:
                with PublicationStore(conn=_ingest_conn) as store:
                    summary = store.ingest(
                        result=parse_result,
                        embed_api_key=api_key if not skip_embedding else None,
                        skip_embedding=skip_embedding,
                        generate_summaries=True,
                    )
            finally:
                _ingest_conn.close()

            elapsed = time.time() - t0
            logger.info("  ✓ Ingested %s: %d chunks (%d anchors) in %.1fs",
                        pub_number, summary["chunk_count"],
                        summary["anchor_count"], elapsed)
            results["ingested"] += 1

        except Exception as e:
            logger.error("  ✗ Failed to ingest %s: %s", pub_number, e)
            import traceback
            traceback.print_exc()
            results["failed"] += 1

    print(f"\n  Ingested: {results['ingested']}, "
          f"Already had: {results['skipped']}, "
          f"Failed: {results['failed']}, "
          f"No PDF: {results['no_pdf']}")
    return results


def phase3_rebuild_index(pg_dsn: str, dry_run: bool):
    """Phase 3: Rebuild the IVFFlat ANN index."""
    print("\n" + "=" * 72)
    print("  PHASE 3: REBUILD SEARCH INDEX")
    print("=" * 72)

    if dry_run:
        logger.info("  [DRY RUN] Would rebuild IVFFlat index")
        return

    from taxkb.publications.store import PublicationStore

    _idx_conn = psycopg2.connect(pg_dsn)
    try:
        with PublicationStore(conn=_idx_conn) as store:
            logger.info("  Building IVFFlat ANN index...")
            t0 = time.time()
            store.create_ivfflat_index(lists=100)
            elapsed = time.time() - t0
            logger.info("  ✓ Index built in %.1fs", elapsed)
    finally:
        _idx_conn.close()


def get_pubs_to_process(
    registry,
    specific_pubs: list[str] | None = None,
) -> list[tuple[str, int]]:
    """
    Build the list of (pub_number, tax_year) tuples to process.

    For each registered pub, we ingest the most recent tax_year.
    """
    result = []
    all_pub_numbers = registry.all_pub_numbers()

    if specific_pubs:
        all_pub_numbers = [p for p in all_pub_numbers if p in specific_pubs]

    for pn in sorted(all_pub_numbers):
        meta = registry.get(pn)
        if not meta or not meta.tax_years:
            continue  # skip pubs with no tax years (discontinued/placeholder)

        # Use the most recent tax year
        latest_year = max(meta.tax_years)
        result.append((pn, latest_year))

    return result


def print_inventory(pubs_to_process: list[tuple[str, int]], data_dir: Path):
    """Print a summary of what will be processed."""
    print("\n" + "=" * 72)
    print("  INGESTION INVENTORY")
    print("=" * 72)

    have_pdf = 0
    missing_pdf = 0

    for pub_number, tax_year in pubs_to_process:
        found = _find_existing_pdf(pub_number, tax_year, data_dir)
        exists = found is not None

        registry = get_registry()
        meta = registry.get(pub_number)
        tier = meta.tier if meta else "?"

        status = "✓ PDF" if exists else "✗ NEED"
        if pub_number in SKIP_DOWNLOAD:
            status = "→ SKIP"

        print(f"  {status}  Pub {pub_number:>8s}  year={tax_year}  tier={tier}  "
              f"{'(' + meta.short_title + ')' if meta else ''}")

        if exists:
            have_pdf += 1
        elif pub_number not in SKIP_DOWNLOAD:
            missing_pdf += 1

    print(f"\n  Total: {len(pubs_to_process)} publications")
    print(f"  Have PDF: {have_pdf}, Need download: {missing_pdf}")


def main():
    parser = argparse.ArgumentParser(
        description="Master ingestion script — download, parse, embed, and ingest all IRS publications"
    )
    # Defaults are resolved from Settings (loads .env / registered sources once).
    from taxkb.config import get_settings
    _s = get_settings()
    parser.add_argument("--pg-dsn", default=_s.pg_dsn,
                        help="PostgreSQL DSN (default: from Settings / .env)")
    parser.add_argument("--api-key", default=_s.openai_api_key.get_secret_value(),
                        help="OpenAI API key (default: from Settings / .env)")
    parser.add_argument("--data-dir", default=None,
                        help="PDF directory (default: data/publications/)")
    parser.add_argument("--download-only", action="store_true",
                        help="Phase 1 only: download PDFs, no ingestion")
    parser.add_argument("--ingest-only", action="store_true",
                        help="Phase 2-3 only: skip downloads")
    parser.add_argument("--skip-embedding", action="store_true",
                        help="Skip OpenAI embeddings (text-only ingest)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done, don't do it")
    parser.add_argument("--force", action="store_true",
                        help="Re-ingest even if already in DB")
    parser.add_argument("--pubs", nargs="+", default=None,
                        help="Only process these pub numbers")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip index rebuild after ingestion")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else PROJECT_ROOT / "data" / "publications"
    data_dir.mkdir(parents=True, exist_ok=True)

    registry = get_registry()
    pubs_to_process = get_pubs_to_process(registry, specific_pubs=args.pubs)

    print("=" * 72)
    print("  TAX BRAIN — Master Ingestion Pipeline")
    print(f"  Publications: {len(pubs_to_process)}")
    print(f"  Data dir: {data_dir}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.skip_embedding:
        print("  Embeddings: SKIPPED")
    print("=" * 72)

    # Show inventory
    print_inventory(pubs_to_process, data_dir)

    # Phase 1: Download
    if not args.ingest_only:
        phase1_download(pubs_to_process, data_dir, dry_run=args.dry_run)

    if args.download_only:
        print("\n  Download-only mode — stopping before ingestion.")
        return 0

    # Phase 2: Ingest
    if not args.pg_dsn:
        logger.error("--pg-dsn or PG_DSN environment variable is required for ingestion")
        return 1

    ingest_results = phase2_ingest(
        pubs_to_process=pubs_to_process,
        data_dir=data_dir,
        pg_dsn=args.pg_dsn,
        api_key=args.api_key,
        skip_embedding=args.skip_embedding,
        force=args.force,
        dry_run=args.dry_run,
    )

    # Phase 3: Rebuild index
    if not args.no_index and not args.dry_run and not args.skip_embedding:
        if ingest_results["ingested"] > 0:
            phase3_rebuild_index(args.pg_dsn, dry_run=args.dry_run)

    # Final summary
    print("\n" + "=" * 72)
    print("  DONE")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
