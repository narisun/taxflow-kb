"""
tax_brain/publications/validation/structural.py

Gate V3.1 — Structural integrity of parsed publication chunks.

Checks (all must pass):
  V3.1-A  At least MIN_CHUNKS chunks produced per publication.
  V3.1-B  No chunk has empty or whitespace-only text.
  V3.1-C  All token_count values are positive.
  V3.1-D  chunk_index values are unique within a publication.
  V3.1-E  page_start ≥ 1 for all chunks (IRS PDFs are 1-indexed).
  V3.1-F  chunk_id follows the expected format "p<pub>-<year>::<NNNN>".
  V3.1-G  form_refs and line_refs contain no duplicate entries.
  V3.1-H  Embedding dimension is correct (1536) whenever present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from tax_brain.publications.models import Layer3ParseResult, PublicationChunk

MIN_CHUNKS    = 10       # minimum acceptable chunks per publication
EMBEDDING_DIM = 1536
_CHUNK_ID_RE  = re.compile(r"^p[\w]+-\d{4}::\d{4}$")


@dataclass
class V31Result:
    gate        : str  = "V3.1"
    pub_id      : str  = ""
    passed      : bool = False
    total_chunks: int  = 0
    failures    : list[str] = field(default_factory=list)
    warnings    : list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{self.gate}] {status} — {self.pub_id} "
            f"({self.total_chunks} chunks, {len(self.failures)} failures)"
        )

    def print_report(self):
        print(self.summary)
        for f in self.failures:
            print(f"  FAIL  {f}")
        for w in self.warnings:
            print(f"  WARN  {w}")


def validate_structural(result: Layer3ParseResult) -> V31Result:
    """
    Run the V3.1 structural gate against a Layer3ParseResult.

    Args:
        result: The output of parse_publication_pdf().

    Returns:
        V31Result with passed=True only if all checks pass.
    """
    pub_id = result.publication.pub_id
    chunks = result.chunks
    out    = V31Result(pub_id=pub_id, total_chunks=len(chunks))

    # A: Minimum chunk count
    if len(chunks) < MIN_CHUNKS:
        out.failures.append(
            f"V3.1-A: Only {len(chunks)} chunks produced "
            f"(minimum {MIN_CHUNKS})"
        )

    # B: No empty text
    empty_text = [c.chunk_id for c in chunks if not c.text.strip()]
    if empty_text:
        out.failures.append(
            f"V3.1-B: {len(empty_text)} chunks have empty text: "
            f"{empty_text[:5]}"
        )

    # C: Positive token counts
    bad_tokens = [c.chunk_id for c in chunks if c.token_count <= 0]
    if bad_tokens:
        out.failures.append(
            f"V3.1-C: {len(bad_tokens)} chunks have non-positive token_count: "
            f"{bad_tokens[:5]}"
        )

    # D: Unique chunk_index values
    seen_idx: set[int] = set()
    dup_idx: list[int] = []
    for c in chunks:
        if c.chunk_index in seen_idx:
            dup_idx.append(c.chunk_index)
        seen_idx.add(c.chunk_index)
    if dup_idx:
        out.failures.append(
            f"V3.1-D: Duplicate chunk_index values: {dup_idx[:10]}"
        )

    # E: page_start ≥ 1
    bad_pages = [c.chunk_id for c in chunks if c.page_start < 1]
    if bad_pages:
        out.failures.append(
            f"V3.1-E: {len(bad_pages)} chunks have page_start < 1: "
            f"{bad_pages[:5]}"
        )

    # F: chunk_id format
    bad_ids = [c.chunk_id for c in chunks if not _CHUNK_ID_RE.match(c.chunk_id)]
    if bad_ids:
        out.failures.append(
            f"V3.1-F: {len(bad_ids)} chunks have malformed chunk_id: "
            f"{bad_ids[:5]}"
        )

    # G: No duplicate refs within a chunk
    dup_refs: list[str] = []
    for c in chunks:
        if len(c.form_refs) != len(set(c.form_refs)):
            dup_refs.append(f"{c.chunk_id}:form_refs")
        if len(c.line_refs) != len(set(c.line_refs)):
            dup_refs.append(f"{c.chunk_id}:line_refs")
    if dup_refs:
        out.warnings.append(
            f"V3.1-G: {len(dup_refs)} chunks have duplicate refs: "
            f"{dup_refs[:5]}"
        )

    # H: Embedding dimension (only for embedded chunks)
    embedded = [c for c in chunks if c.embedding is not None]
    bad_dim  = [c.chunk_id for c in embedded if len(c.embedding) != EMBEDDING_DIM]
    if bad_dim:
        out.failures.append(
            f"V3.1-H: {len(bad_dim)} chunks have wrong embedding dimension "
            f"(expected {EMBEDDING_DIM}): {bad_dim[:5]}"
        )
    elif embedded:
        out.warnings.append(
            f"V3.1-H: {len(embedded)}/{len(chunks)} chunks are embedded "
            f"— dimension OK."
        )

    # Parse result errors propagate as failures
    for err in result.errors:
        out.failures.append(f"ParseError: {err}")

    out.passed = len(out.failures) == 0
    return out
