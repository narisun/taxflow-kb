"""
tests/test_layer3.py

Layer 3 test suite — IRS Publications PDF pipeline.

Test classes
────────────
  TestModels              — 5 tests: Pydantic model construction and validation
  TestPDFParserHelpers    — 7 tests: token counting, heading detection, chunking
  TestParsePublicationPDF — 4 tests: parse_publication_pdf() edge cases (no real PDF)
  TestV31Structural       — 6 tests: V3.1 structural gate logic
  TestV32Coverage         — 4 tests: V3.2 in-memory coverage gate
  TestV33Retrieval        — 4 tests: V3.3 in-memory retrieval gate (mock embeddings)

No real PDFs, no OpenAI API key, no PostgreSQL connection required.
All embedding calls are replaced with deterministic mock vectors.
"""
from __future__ import annotations

import math
import pathlib
import pytest
from unittest.mock import patch, MagicMock


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_vec(seed: int, dim: int = 1536) -> list[float]:
    """Return a unit-norm deterministic float vector for testing."""
    import random
    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _make_chunk(
    chunk_index : int = 0,
    pub_id      : str = "p17-2025",
    pub_number  : str = "17",
    tax_year    : int = 2025,
    text        : str = "This is a sample chunk about income tax deductions.",
    embedding   : list[float] | None = None,
    page_start  : int = 1,
    token_count : int | None = None,
) -> "PublicationChunk":
    from tax_brain.publications.models import PublicationChunk
    return PublicationChunk(
        chunk_id    = f"{pub_id}::{chunk_index:04d}",
        pub_id      = pub_id,
        pub_number  = pub_number,
        tax_year    = tax_year,
        chunk_index = chunk_index,
        text        = text,
        # Default to 150 tokens so V3.2-D avg-token check passes in unit tests.
        token_count = token_count if token_count is not None else 150,
        page_start  = page_start,
        embedding   = embedding,
    )


def _make_result(
    pub_number  : str = "17",
    tax_year    : int = 2025,
    num_chunks  : int = 15,
    add_embeddings: bool = False,
) -> "Layer3ParseResult":
    from tax_brain.publications.models import Layer3ParseResult, Publication
    pub_id = f"p{pub_number}-{tax_year}"
    chunks = [
        _make_chunk(
            chunk_index = i,
            pub_id      = pub_id,
            pub_number  = pub_number,
            tax_year    = tax_year,
            text        = f"Chunk {i}: information about IRS Publication {pub_number} on tax topics.",
            embedding   = _make_vec(i) if add_embeddings else None,
            page_start  = max(1, i + 1),
        )
        for i in range(num_chunks)
    ]
    pub = Publication(
        pub_id      = pub_id,
        pub_number  = pub_number,
        pub_title   = f"IRS Publication {pub_number}",
        tax_year    = tax_year,
        page_count  = num_chunks + 5,
        chunk_count = num_chunks,
    )
    return Layer3ParseResult(
        publication  = pub,
        chunks       = chunks,
        parse_success= True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TestModels
# ══════════════════════════════════════════════════════════════════════════════

class TestModels:

    def test_publication_chunk_defaults(self):
        """PublicationChunk should have sensible defaults."""
        from tax_brain.publications.models import PublicationChunk
        c = PublicationChunk(
            chunk_id    = "p17-2025::0000",
            pub_id      = "p17-2025",
            pub_number  = "17",
            tax_year    = 2025,
            chunk_index = 0,
            text        = "Hello",
        )
        assert c.chapter_title == ""
        assert c.section_title == ""
        assert c.embedding is None
        assert c.form_refs == []
        assert c.line_refs == []

    def test_publication_defaults(self):
        from tax_brain.publications.models import Publication
        pub = Publication(
            pub_id    = "p17-2025",
            pub_number= "17",
            pub_title = "Your Federal Income Tax",
            tax_year  = 2025,
        )
        assert pub.pdf_hash   == ""
        assert pub.page_count == 0
        assert pub.chunk_count== 0

    def test_layer3_parse_result_embedded_chunks(self):
        """embedded_chunks() should only return chunks with embeddings."""
        result = _make_result(num_chunks=5)
        result.chunks[0].embedding = _make_vec(0)
        result.chunks[2].embedding = _make_vec(2)
        assert len(result.embedded_chunks()) == 2

    def test_pub_titles_populated(self):
        from tax_brain.publications.models import PUB_TITLES
        assert "17"   in PUB_TITLES
        assert "590a" in PUB_TITLES
        assert "969"  in PUB_TITLES

    def test_retrieval_result_construction(self):
        from tax_brain.publications.models import RetrievalResult
        rr = RetrievalResult(
            chunk_id      = "p17-2025::0001",
            pub_number    = "17",
            pub_title     = "Your Federal Income Tax",
            chapter_title = "Introduction",
            section_title = "Filing Requirements",
            page_start    = 5,
            text          = "Sample text about filing requirements.",
            score         = 0.87,
        )
        assert rr.score == pytest.approx(0.87)
        assert rr.form_refs == []


# ══════════════════════════════════════════════════════════════════════════════
# TestPDFParserHelpers
# ══════════════════════════════════════════════════════════════════════════════

class TestPDFParserHelpers:

    def test_count_tokens_fallback(self):
        """Token count fallback (4 chars/token) should return positive int."""
        from tax_brain.publications.pdf_parser import _count_tokens
        result = _count_tokens("Hello, world!")
        assert result > 0

    def test_count_tokens_non_empty_text(self):
        """100-word text should produce at least 80 tokens."""
        from tax_brain.publications.pdf_parser import _count_tokens
        text = " ".join(["word"] * 100)
        assert _count_tokens(text) >= 80

    def test_detect_heading_chapter(self):
        """Lines starting with 'Chapter N' should be detected as chapter headings."""
        from tax_brain.publications.pdf_parser import _detect_heading
        ch, sec = _detect_heading("Chapter 1. Filing Information")
        assert ch is not None
        assert sec is None

    def test_detect_heading_all_caps(self):
        """Short all-caps lines should be chapter headings."""
        from tax_brain.publications.pdf_parser import _detect_heading
        ch, sec = _detect_heading("FILING STATUS")
        assert ch is not None

    def test_detect_heading_title_case_section(self):
        """Short title-cased lines without punctuation should be section headings."""
        from tax_brain.publications.pdf_parser import _detect_heading
        ch, sec = _detect_heading("Standard Deduction Amount")
        # May be detected as section or not — it must not be a chapter
        assert ch is None

    def test_detect_heading_long_line_not_heading(self):
        """Lines longer than 120 chars should not be headings."""
        from tax_brain.publications.pdf_parser import _detect_heading
        long_line = "This is a very long line of text that goes on and on " * 5
        ch, sec = _detect_heading(long_line)
        assert ch is None
        assert sec is None

    def test_chunk_paragraphs_respects_max_tokens(self):
        """Chunks should not exceed HARD_MAX tokens."""
        from tax_brain.publications.pdf_parser import _chunk_paragraphs, _count_tokens, HARD_MAX
        # Create paragraphs that together exceed a single chunk
        paras = ["This is a tax paragraph with some real content here. " * 10] * 20
        chunks = _chunk_paragraphs(paras, max_tokens=100, overlap=10, hard_max=150)
        assert len(chunks) > 1
        for c in chunks:
            assert _count_tokens(c) <= HARD_MAX, \
                f"Chunk exceeded HARD_MAX: {_count_tokens(c)} tokens"

    def test_split_paragraphs_on_blank_lines(self):
        """Paragraphs should split on double newlines."""
        from tax_brain.publications.pdf_parser import _split_paragraphs
        text = "First paragraph text.\n\nSecond paragraph text.\n\nThird paragraph text."
        paras = _split_paragraphs(text)
        assert len(paras) == 3

    def test_extract_refs_finds_form(self):
        """Form references should be extracted from chunk text."""
        from tax_brain.publications.pdf_parser import _extract_refs
        text = "Enter the amount from Form 1040, line 11. See Schedule A for details."
        form_refs, line_refs = _extract_refs(text)
        assert "Form1040" in form_refs
        assert "ScheduleA" in form_refs

    def test_extract_refs_finds_line(self):
        """Line references should be extracted from chunk text."""
        from tax_brain.publications.pdf_parser import _extract_refs
        text = "Enter the total on line 12."
        form_refs, line_refs = _extract_refs(text)
        assert "12" in line_refs


# ══════════════════════════════════════════════════════════════════════════════
# TestParsePublicationPDF
# ══════════════════════════════════════════════════════════════════════════════

class TestParsePublicationPDF:

    def test_missing_file_returns_graceful_failure(self):
        """parse_publication_pdf should return parse_success=False for missing files."""
        from tax_brain.publications.pdf_parser import parse_publication_pdf
        result = parse_publication_pdf("/nonexistent/path/pub17.pdf", "17", 2025)
        assert result.parse_success is False
        assert result.chunks == []
        assert any("not found" in e.lower() or "File not found" in e for e in result.errors)

    def test_pub_id_format(self):
        """pub_id should follow the pattern p{pub_number}-{tax_year}."""
        from tax_brain.publications.pdf_parser import parse_publication_pdf
        result = parse_publication_pdf("/nonexistent/pub.pdf", "550", 2024)
        assert result.publication.pub_id == "p550-2024"

    def test_pub_title_from_registry(self):
        """pub_title should be looked up from PUB_TITLES."""
        from tax_brain.publications.pdf_parser import parse_publication_pdf
        result = parse_publication_pdf("/nonexistent/pub.pdf", "17", 2025)
        assert "Federal Income Tax" in result.publication.pub_title

    def test_unknown_pub_number_uses_fallback_title(self):
        """Unknown pub numbers should produce a generic title."""
        from tax_brain.publications.pdf_parser import parse_publication_pdf
        result = parse_publication_pdf("/nonexistent/pub.pdf", "9999", 2025)
        assert "9999" in result.publication.pub_title


# ══════════════════════════════════════════════════════════════════════════════
# TestV31Structural
# ══════════════════════════════════════════════════════════════════════════════

class TestV31Structural:

    def test_passes_with_valid_result(self):
        """A well-formed Layer3ParseResult should pass V3.1."""
        from tax_brain.publications.validation.structural import validate_structural
        result = _make_result(num_chunks=20)
        v = validate_structural(result)
        assert v.passed, f"V3.1 failures: {v.failures}"

    def test_fails_on_too_few_chunks(self):
        """V3.1-A should fail when fewer than MIN_CHUNKS chunks are present."""
        from tax_brain.publications.validation.structural import validate_structural, MIN_CHUNKS
        result = _make_result(num_chunks=max(1, MIN_CHUNKS - 1))
        v = validate_structural(result)
        assert not v.passed
        assert any("V3.1-A" in f for f in v.failures)

    def test_fails_on_empty_text(self):
        """V3.1-B should fail when any chunk has empty text."""
        from tax_brain.publications.validation.structural import validate_structural
        result = _make_result(num_chunks=15)
        result.chunks[3].text = "   "
        v = validate_structural(result)
        assert not v.passed
        assert any("V3.1-B" in f for f in v.failures)

    def test_fails_on_zero_token_count(self):
        """V3.1-C should fail when token_count is 0."""
        from tax_brain.publications.validation.structural import validate_structural
        result = _make_result(num_chunks=15)
        result.chunks[0].token_count = 0
        v = validate_structural(result)
        assert not v.passed
        assert any("V3.1-C" in f for f in v.failures)

    def test_fails_on_duplicate_chunk_index(self):
        """V3.1-D should fail when chunk_index values repeat."""
        from tax_brain.publications.validation.structural import validate_structural
        result = _make_result(num_chunks=15)
        result.chunks[5].chunk_index = 0   # duplicate of index 0
        v = validate_structural(result)
        assert not v.passed
        assert any("V3.1-D" in f for f in v.failures)

    def test_fails_on_wrong_embedding_dimension(self):
        """V3.1-H should fail when embedding dimension is not 1536."""
        from tax_brain.publications.validation.structural import validate_structural
        result = _make_result(num_chunks=15)
        result.chunks[0].embedding = [0.1, 0.2, 0.3]  # wrong dimension
        v = validate_structural(result)
        assert not v.passed
        assert any("V3.1-H" in f for f in v.failures)


# ══════════════════════════════════════════════════════════════════════════════
# TestV32Coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestV32Coverage:

    def test_passes_when_all_pubs_present(self):
        """V3.2 should pass when every expected pub is in the result list."""
        from tax_brain.publications.validation.coverage import (
            validate_coverage_from_results, EXPECTED_PUBS,
        )
        results = [_make_result(pub_number=pn, num_chunks=15) for pn in EXPECTED_PUBS]
        v = validate_coverage_from_results(results)
        assert v.passed, f"V3.2 failures: {v.failures}"

    def test_fails_when_pub_missing(self):
        """V3.2-A should fail when an expected pub is absent."""
        from tax_brain.publications.validation.coverage import validate_coverage_from_results
        results = [_make_result(pub_number="17", num_chunks=15)]  # only pub 17
        v = validate_coverage_from_results(results)
        assert not v.passed
        assert any("V3.2-A" in f for f in v.failures)

    def test_fails_on_insufficient_chunks(self):
        """V3.2-B should fail when a pub has too few chunks."""
        from tax_brain.publications.validation.coverage import (
            validate_coverage_from_results, EXPECTED_PUBS, MIN_CHUNKS_PER_PUB,
        )
        results = []
        for pn in EXPECTED_PUBS:
            n = max(1, MIN_CHUNKS_PER_PUB - 1) if pn == "17" else 15
            results.append(_make_result(pub_number=pn, num_chunks=n))
        v = validate_coverage_from_results(results)
        assert not v.passed
        assert any("V3.2-B" in f for f in v.failures)

    def test_embedding_check_passes_at_100_pct(self):
        """V3.2-C should pass when all chunks are embedded."""
        from tax_brain.publications.validation.coverage import (
            validate_coverage_from_results, EXPECTED_PUBS,
        )
        results = [
            _make_result(pub_number=pn, num_chunks=15, add_embeddings=True)
            for pn in EXPECTED_PUBS
        ]
        v = validate_coverage_from_results(results, require_embeddings=True)
        assert v.passed, f"V3.2 failures: {v.failures}"


# ══════════════════════════════════════════════════════════════════════════════
# TestV33Retrieval
# ══════════════════════════════════════════════════════════════════════════════

class TestV33Retrieval:
    """
    V3.3 tests use mock embeddings:
    · Each probe query is mapped to a deterministic vector (seed = hash of query).
    · Each chunk's embedding has the correct publication's vector set as high-similarity.
    """

    def _build_probe_chunks(self, probes, num_extra=5):
        """
        Build a set of chunks where each probe's expected pub has one chunk
        whose embedding is very similar to the probe's query embedding.
        """
        from tax_brain.publications.validation.retrieval import RetrievalProbe

        chunks = []
        for i, probe in enumerate(probes):
            # "perfect" chunk: same vector as the query will produce
            seed = hash(probe.query) % (2 ** 31)
            vec  = _make_vec(seed)
            text = probe.must_contain or f"IRS guidance for publication {probe.expected_pub}"
            chunks.append(_make_chunk(
                chunk_index = i,
                pub_id      = f"p{probe.expected_pub}-2025",
                pub_number  = probe.expected_pub,
                text        = f"{text} additional context about this tax topic.",
                embedding   = vec,
                page_start  = i + 1,
            ))
        # Add noise chunks from a different pub
        for j in range(num_extra):
            chunks.append(_make_chunk(
                chunk_index = len(probes) + j,
                pub_id      = "p999-2025",
                pub_number  = "999",
                text        = f"Unrelated content chunk {j}.",
                embedding   = _make_vec(9999 + j),
                page_start  = j + 1,
            ))
        return chunks

    def _mock_embed_query(self, query: str, api_key=None, model=None) -> list[float]:
        """Return the same deterministic vector the probe chunks were built with."""
        seed = hash(query) % (2 ** 31)
        return _make_vec(seed)

    def test_passes_with_perfect_embeddings(self):
        """V3.3 should pass when each probe's exact vector is in the chunk set."""
        from tax_brain.publications.validation.retrieval import (
            validate_retrieval_from_chunks, PROBES,
        )
        chunks = self._build_probe_chunks(PROBES)
        with patch(
            "tax_brain.publications.embeddings.embed_query",
            side_effect=self._mock_embed_query,
        ):
            v = validate_retrieval_from_chunks(chunks, probes=PROBES)
        assert v.passed, (
            f"V3.3 failures: {v.failures}\n"
            + "\n".join(
                f"  probe={pr.probe.query[:40]} top1={pr.top1_pub} "
                f"score={pr.top1_score:.3f} reason={pr.failure_reason}"
                for pr in v.probe_results if not pr.passed
            )
        )

    def test_fails_when_wrong_pub_returned(self):
        """V3.3 should fail when the top result comes from the wrong publication."""
        from tax_brain.publications.validation.retrieval import (
            validate_retrieval_from_chunks, RetrievalProbe,
        )
        # Single probe; only chunk is from a different pub
        probe = RetrievalProbe(
            query        = "What is the standard deduction?",
            expected_pub = "501",
            min_score    = 0.5,
        )
        seed  = hash(probe.query) % (2 ** 31)
        wrong_chunk = _make_chunk(
            pub_number  = "17",   # wrong pub
            embedding   = _make_vec(seed),  # same vector → will be top-1
            text        = "Standard deduction information.",
        )
        with patch(
            "tax_brain.publications.embeddings.embed_query",
            side_effect=self._mock_embed_query,
        ):
            v = validate_retrieval_from_chunks([wrong_chunk], probes=[probe])
        assert not v.passed

    def test_fails_on_low_score(self):
        """V3.3 should fail when cosine score is below probe's min_score."""
        from tax_brain.publications.validation.retrieval import (
            validate_retrieval_from_chunks, RetrievalProbe,
        )
        probe = RetrievalProbe(
            query        = "IRA contribution limits for 2025",
            expected_pub = "590a",
            min_score    = 0.999,   # impossibly high
        )
        seed = hash(probe.query) % (2 ** 31)
        chunk = _make_chunk(
            pub_number  = "590a",
            embedding   = _make_vec(seed),
            text        = "IRA contribution limits.",
        )
        with patch(
            "tax_brain.publications.embeddings.embed_query",
            side_effect=self._mock_embed_query,
        ):
            v = validate_retrieval_from_chunks([chunk], probes=[probe])
        # Score will be 1.0 because same seed → actually passes
        # Use a different seed for chunk to get a genuinely low score
        chunk.embedding = _make_vec(seed + 1)
        with patch(
            "tax_brain.publications.embeddings.embed_query",
            side_effect=self._mock_embed_query,
        ):
            v = validate_retrieval_from_chunks([chunk], probes=[probe])
        assert not v.passed

    def test_no_embedded_chunks_fails(self):
        """V3.3 should fail gracefully when no embedded chunks are available."""
        from tax_brain.publications.validation.retrieval import (
            validate_retrieval_from_chunks, RetrievalProbe,
        )
        probe  = RetrievalProbe(query="Any tax question", expected_pub="17")
        chunk  = _make_chunk(pub_number="17")   # no embedding
        with patch(
            "tax_brain.publications.embeddings.embed_query",
            side_effect=self._mock_embed_query,
        ):
            v = validate_retrieval_from_chunks([chunk], probes=[probe])
        assert not v.passed
        assert len(v.failures) > 0
