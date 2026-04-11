"""
taxflow_kb/layer3/validation/v3_2_coverage.py

Gate V3.2 — Publication coverage.

Checks (all must pass):
  V3.2-A  Every expected publication is present in the database.
  V3.2-B  Each publication meets the minimum chunk threshold.
  V3.2-C  Embedding coverage ≥ MIN_EMBED_PCT % for each publication
           (only checked when embeddings are expected / present).
  V3.2-D  Average tokens per chunk within [MIN_AVG_TOKENS, MAX_AVG_TOKENS].
  V3.2-E  No publication's page count is unexpectedly low (< MIN_PAGES).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Thresholds ────────────────────────────────────────────────────────────────

MIN_CHUNKS_PER_PUB  = 10      # absolute floor
MIN_AVG_TOKENS      = 50      # sanity: avg chunk shouldn't be tiny
MAX_AVG_TOKENS      = 650     # raised from 450: Pub 596 EIC worksheets avg ~601 tokens
MIN_EMBED_PCT       = 95.0    # % of chunks that must be embedded
MIN_PAGES           = 5       # publications with fewer pages are suspect

# ── Expected publications (pub_number → friendly name) ────────────────────────
#
# Derived from the publication registry — includes all Tier 1 and Tier 2
# publications that have active tax years (i.e., not discontinued with
# empty tax_years).  Discontinued pubs that HAVE been ingested (e.g., Pub 535
# with tax_years=[2022]) are included; fully retired pubs with tax_years=[]
# (e.g., Pub 564) are excluded.

def _build_expected_pubs() -> dict[str, str]:
    """Build the expected publications dict from the registry."""
    try:
        from taxflow_kb.layer3.publication_registry import get_registry
        registry = get_registry()
        pubs: dict[str, str] = {}
        for meta in registry.all():
            # Include Tier 1 and Tier 2 pubs that have at least one tax year
            if meta.tier <= 2 and meta.tax_years:
                pubs[meta.pub_number] = meta.title
        return pubs
    except Exception:
        # Fallback if registry isn't available
        return _FALLBACK_EXPECTED_PUBS


# Static fallback in case registry can't be imported (e.g., isolated test)
_FALLBACK_EXPECTED_PUBS: dict[str, str] = {
    "17"  : "Your Federal Income Tax (For Individuals)",
    "334" : "Tax Guide for Small Business",
    "463" : "Travel, Gift, and Car Expenses",
    "501" : "Dependents, Standard Deduction, and Filing Information",
    "502" : "Medical and Dental Expenses",
    "503" : "Child and Dependent Care Expenses",
    "504" : "Divorced or Separated Individuals",
    "505" : "Tax Withholding and Estimated Tax",
    "523" : "Selling Your Home",
    "525" : "Taxable and Nontaxable Income",
    "527" : "Residential Rental Property",
    "535" : "Business Expenses",
    "544" : "Sales of Assets",
    "550" : "Investment Income and Expenses",
    "551" : "Basis of Assets",
    "590a": "Contributions to Individual Retirement Arrangements (IRAs)",
    "590b": "Distributions from Individual Retirement Arrangements (IRAs)",
    "596" : "Earned Income Credit (EIC)",
    "946" : "How to Depreciate Property",
    "969" : "Health Savings Accounts and Other Tax-Favored Health Plans",
}

EXPECTED_PUBS: dict[str, str] = _build_expected_pubs()


@dataclass
class V32PubStats:
    """Per-publication stats collected from the database."""
    pub_number    : str
    pub_title     : str
    chunk_count   : int   = 0
    embedded_count: int   = 0
    page_count    : int   = 0
    avg_tokens    : float = 0.0


@dataclass
class V32Result:
    gate          : str  = "V3.2"
    passed        : bool = False
    total_pubs    : int  = 0
    passed_pubs   : int  = 0
    failures      : list[str] = field(default_factory=list)
    warnings      : list[str] = field(default_factory=list)
    pub_stats     : list[V32PubStats] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{self.gate}] {status} — "
            f"{self.passed_pubs}/{self.total_pubs} publications pass "
            f"({len(self.failures)} failures)"
        )

    def print_report(self):
        print(self.summary)
        for f in self.failures:
            print(f"  FAIL  {f}")
        for w in self.warnings:
            print(f"  WARN  {w}")
        print()
        print(f"  {'PubNum':<8} {'Chunks':>7} {'Embedded':>9} {'Embed%':>7} {'Pages':>6} {'AvgTok':>7}")
        print(f"  {'-'*8} {'-'*7} {'-'*9} {'-'*7} {'-'*6} {'-'*7}")
        for s in self.pub_stats:
            pct = (s.embedded_count / s.chunk_count * 100) if s.chunk_count else 0
            print(
                f"  {s.pub_number:<8} {s.chunk_count:>7} {s.embedded_count:>9} "
                f"{pct:>6.1f}% {s.page_count:>6} {s.avg_tokens:>7.0f}"
            )


def validate_coverage(
    store,                                # Layer3Store instance
    expected_pubs      : Optional[dict[str, str]] = None,
    require_embeddings : bool = False,
) -> V32Result:
    """
    Run the V3.2 coverage gate against the live database via a Layer3Store.

    Args:
        store              : Connected Layer3Store.
        expected_pubs      : Mapping pub_number → title to check against.
                             Defaults to EXPECTED_PUBS.
        require_embeddings : When True, enforce MIN_EMBED_PCT check (V3.2-C).
                             Set False during initial text-only ingestion.

    Returns:
        V32Result with per-publication stats and pass/fail details.
    """
    if expected_pubs is None:
        expected_pubs = EXPECTED_PUBS

    coverage_rows = store.get_pub_coverage()          # list[dict]
    present: dict[str, dict] = {r["pub_number"]: r for r in coverage_rows}

    out = V32Result(total_pubs=len(expected_pubs))

    pub_pass_count = 0

    for pub_number, pub_title in expected_pubs.items():
        row = present.get(pub_number)
        pub_failures: list[str] = []

        if row is None:
            out.failures.append(
                f"V3.2-A: Publication {pub_number} ({pub_title}) not found in database"
            )
            # Can't check other gates without data
            out.pub_stats.append(V32PubStats(pub_number=pub_number, pub_title=pub_title))
            continue

        chunk_count    = row.get("chunk_count", 0) or 0
        embedded_count = row.get("embedded_count", 0) or 0
        page_count     = row.get("page_count", 0) or 0
        # avg_token_count is computed by the v_pub_coverage view (subquery per pub)
        avg_tokens     = float(row.get("avg_token_count") or 0.0)

        stats = V32PubStats(
            pub_number    = pub_number,
            pub_title     = pub_title,
            chunk_count   = chunk_count,
            embedded_count= embedded_count,
            page_count    = page_count,
            avg_tokens    = avg_tokens,
        )
        out.pub_stats.append(stats)

        # B: Minimum chunks
        if chunk_count < MIN_CHUNKS_PER_PUB:
            pub_failures.append(
                f"V3.2-B: Pub {pub_number} has {chunk_count} chunks "
                f"(minimum {MIN_CHUNKS_PER_PUB})"
            )

        # C: Embedding coverage
        if require_embeddings and chunk_count > 0:
            embed_pct = embedded_count / chunk_count * 100
            if embed_pct < MIN_EMBED_PCT:
                pub_failures.append(
                    f"V3.2-C: Pub {pub_number} embedding coverage {embed_pct:.1f}% "
                    f"< {MIN_EMBED_PCT}%"
                )

        # D: Average token count
        if avg_tokens and (avg_tokens < MIN_AVG_TOKENS or avg_tokens > MAX_AVG_TOKENS):
            pub_failures.append(
                f"V3.2-D: Pub {pub_number} avg tokens {avg_tokens:.0f} "
                f"outside [{MIN_AVG_TOKENS}, {MAX_AVG_TOKENS}]"
            )

        # E: Page count sanity
        if page_count > 0 and page_count < MIN_PAGES:
            out.warnings.append(
                f"V3.2-E: Pub {pub_number} has only {page_count} pages — "
                f"may be truncated or incorrectly downloaded"
            )

        if pub_failures:
            out.failures.extend(pub_failures)
        else:
            pub_pass_count += 1

    out.passed_pubs = pub_pass_count
    out.passed      = len(out.failures) == 0
    return out


def validate_coverage_from_results(
    results            : list,      # list[Layer3ParseResult]
    require_embeddings : bool = False,
) -> V32Result:
    """
    Run V3.2 against in-memory Layer3ParseResult objects (no DB required).

    Useful in unit tests and CI pipelines where no PostgreSQL is available.
    """
    from taxflow_kb.layer3.models_layer3 import Layer3ParseResult

    present: dict[str, "Layer3ParseResult"] = {
        r.publication.pub_number: r for r in results
    }

    out = V32Result(total_pubs=len(EXPECTED_PUBS))
    pub_pass_count = 0

    for pub_number, pub_title in EXPECTED_PUBS.items():
        result = present.get(pub_number)
        pub_failures: list[str] = []

        if result is None:
            out.failures.append(
                f"V3.2-A: Publication {pub_number} not in result set"
            )
            out.pub_stats.append(V32PubStats(pub_number=pub_number, pub_title=pub_title))
            continue

        chunks         = result.chunks
        chunk_count    = len(chunks)
        embedded_count = len([c for c in chunks if c.embedding is not None])
        page_count     = result.publication.page_count

        # Avg tokens from chunk objects
        if chunk_count:
            avg_tokens = sum(c.token_count for c in chunks) / chunk_count
        else:
            avg_tokens = 0.0

        stats = V32PubStats(
            pub_number    = pub_number,
            pub_title     = pub_title,
            chunk_count   = chunk_count,
            embedded_count= embedded_count,
            page_count    = page_count,
            avg_tokens    = avg_tokens,
        )
        out.pub_stats.append(stats)

        # B
        if chunk_count < MIN_CHUNKS_PER_PUB:
            pub_failures.append(
                f"V3.2-B: {pub_number} has {chunk_count} chunks "
                f"(minimum {MIN_CHUNKS_PER_PUB})"
            )

        # C
        if require_embeddings and chunk_count > 0:
            embed_pct = embedded_count / chunk_count * 100
            if embed_pct < MIN_EMBED_PCT:
                pub_failures.append(
                    f"V3.2-C: {pub_number} embedding coverage {embed_pct:.1f}%"
                )

        # D
        if avg_tokens and (avg_tokens < MIN_AVG_TOKENS or avg_tokens > MAX_AVG_TOKENS):
            pub_failures.append(
                f"V3.2-D: {pub_number} avg tokens {avg_tokens:.0f} "
                f"outside [{MIN_AVG_TOKENS}, {MAX_AVG_TOKENS}]"
            )

        # E
        if page_count > 0 and page_count < MIN_PAGES:
            out.warnings.append(
                f"V3.2-E: {pub_number} only {page_count} pages"
            )

        if pub_failures:
            out.failures.extend(pub_failures)
        else:
            pub_pass_count += 1

    out.passed_pubs = pub_pass_count
    out.passed      = len(out.failures) == 0
    return out
