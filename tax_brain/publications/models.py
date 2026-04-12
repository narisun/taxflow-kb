"""
tax_brain/publications/models.py

Pydantic v2 models for the IRS Publications Layer (Layer 3).
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from tax_brain.publications.ontology import ChunkType


# ── Publication metadata ───────────────────────────────────────────────────────

def _get_pub_titles() -> dict[str, str]:
    """Load publication titles from the registry, falling back to hardcoded defaults."""
    try:
        from tax_brain.publications.registry import get_pub_titles
        return get_pub_titles()
    except ImportError:
        # Fallback if registry not available
        return {
            "17"  : "Your Federal Income Tax (For Individuals)",
            "501" : "Dependents, Standard Deduction, and Filing Information",
            "525" : "Taxable and Nontaxable Income",
            "550" : "Investment Income and Expenses",
            "590a": "Contributions to Individual Retirement Arrangements (IRAs)",
            "590b": "Distributions from Individual Retirement Arrangements (IRAs)",
            "596" : "Earned Income Credit (EIC)",
            "969" : "Health Savings Accounts and Other Tax-Favored Health Plans",
        }


# Backward-compatible module-level access
PUB_TITLES: dict[str, str] = _get_pub_titles()


class Publication(BaseModel):
    """Registry entry for one IRS publication PDF."""
    pub_id      : str                    # "p17-2025"
    pub_number  : str                    # "17", "550", "590a"
    pub_title   : str
    tax_year    : int
    source_path : str   = ""
    pdf_hash    : str   = ""
    page_count  : int   = 0
    chunk_count : int   = 0


# ── Chunk (text + optional embedding) ─────────────────────────────────────────

class PublicationChunk(BaseModel):
    """
    One passage extracted from a publication PDF.

    Three-tier hierarchy via chunk_type:
      PUB_SUMMARY     — Tier 1: one per publication, summarizes scope & key topics
      SECTION_SUMMARY  — Tier 2: one per major section, summarizes rules & thresholds
      DETAIL           — Tier 3: existing ~400-token chunks (default)

    The topic_ids field links chunks to the cross-publication topic ontology,
    enabling topic-based routing and cross-publication retrieval.
    """
    chunk_id      : str                  # "p17-2025::0042"
    pub_id        : str
    pub_number    : str
    tax_year      : int
    chunk_index   : int
    chapter_title : str  = ""
    section_title : str  = ""
    page_start    : int  = 0
    page_end      : int  = 0
    text          : str
    token_count   : int  = 0
    form_refs     : list[str] = Field(default_factory=list)
    line_refs     : list[str] = Field(default_factory=list)
    # Three-tier hierarchy
    chunk_type    : ChunkType = ChunkType.DETAIL
    # Cross-publication topic ontology links
    topic_ids     : list[str] = Field(default_factory=list)
    # LLM-generated contextual annotation (set at ingestion time)
    context_annotation : str = ""
    # Populated after embedding step
    embedding     : Optional[list[float]] = None


# ── Parse result ───────────────────────────────────────────────────────────────

class Layer3ParseResult(BaseModel):
    """Output of parsing one publication PDF into chunks."""
    publication   : Publication
    chunks        : list[PublicationChunk]
    parse_success : bool
    errors        : list[str] = Field(default_factory=list)
    warnings      : list[str] = Field(default_factory=list)

    def embedded_chunks(self) -> list[PublicationChunk]:
        return [c for c in self.chunks if c.embedding is not None]


# ── Retrieval result ───────────────────────────────────────────────────────────

class RetrievalResult(BaseModel):
    """One chunk returned by a semantic search query."""
    chunk_id      : str
    pub_number    : str
    pub_title     : str
    chapter_title : str
    section_title : str
    page_start    : int
    text          : str
    score         : float             # cosine similarity (0–1, higher = more similar)
    form_refs     : list[str] = Field(default_factory=list)
    line_refs     : list[str] = Field(default_factory=list)
    context_annotation : str = ""     # LLM-generated context (if available)
