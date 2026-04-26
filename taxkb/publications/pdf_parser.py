"""
taxkb/layer3/pdf_parser.py

Extracts and chunks text from IRS publication PDFs.

Strategy
────────
1. Use pdfplumber to extract text page by page with layout awareness.
2. Strip recurring page headers / footers (detected by similarity across pages).
3. Detect chapter and section headings by font size and capitalization patterns.
4. Split extracted text into paragraph-aware chunks:
     · Target  : ~400 tokens per chunk (cl100k_base, same as text-embedding-3-small)
     · Overlap : ~50 tokens carried forward from the previous chunk
     · Hard max: 512 tokens (never exceed the model's context window)
5. Annotate each chunk with:
     · chapter_title / section_title (from nearest preceding heading)
     · page_start / page_end
     · form_refs  (e.g. "Form1040", "ScheduleA")
     · line_refs  (e.g. "1a", "12", "27a")
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports — fail gracefully so tests can import the module even without
# pdfplumber / tiktoken installed.
try:
    import pdfplumber                           # type: ignore
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

try:
    import tiktoken                             # type: ignore
    _ENC = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN_AVAILABLE = True
except Exception:
    # ImportError if tiktoken not installed; OSError/requests errors if the
    # encoding file cannot be downloaded (e.g. restricted network in CI).
    # Fall back to the 4-chars-per-token heuristic in both cases.
    _TIKTOKEN_AVAILABLE = False
    _ENC = None

from taxkb.publications.models import (
    Layer3ParseResult, Publication, PublicationChunk, PUB_TITLES,
)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_TOKENS     = 400    # target chunk size
OVERLAP_TOKENS = 50     # tokens carried from previous chunk
HARD_MAX       = 512    # absolute ceiling

# Cross-reference extraction (reused from Layer 2 patterns)
_FORM_RE  = re.compile(r"\bForm\s+([\w\-]+\d[\w\-]*)", re.I)
_SCHED_RE = re.compile(r"\bSchedule\s+([A-Z0-9\-]+)", re.I)
_LINE_RE  = re.compile(r"\blines?\s+(\d+[a-z]?)", re.I)
_PUB_RE   = re.compile(r"\bPub(?:lication)?\.\s*(\d+[\w\-]*)", re.I)

# Heading detection: ALL CAPS words, or "Chapter N", or "Part N"
_CHAPTER_RE = re.compile(
    r"^(?:chapter|part)\s+\d+|^[A-Z][A-Z\s\-]{8,}$", re.M | re.I
)

# IRS page header / footer patterns to strip
_HEADER_FOOTER_RE = re.compile(
    r"Publication\s+\d+\s*\(\d{4}\)|"
    r"Page\s+\d+\s+of\s+\d+|"
    r"Chapter\s+\d+\s+\w[\w\s]{0,30}Page\s+\d+|"
    r"^\d+\s*$|"            # lone page numbers
    # IRS TOC lines: "47 Chapter 5 Wages, Salaries, and Other Earnings"
    # or "92 Chapter 10 Standard Deduction" — page-number-prefixed TOC entries
    r"^\d+\s+(?:Chapter|Part)\s+\d+",
    re.I | re.M,
)

# Strip trailing standalone page numbers from heading text, e.g.
# "Chapter 5 Wages, Salaries, and Other Earnings 47" → strip " 47"
_TRAILING_PAGENUM_RE = re.compile(r"\s+\d{1,4}\s*$")


# ── Token utilities ────────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base (same encoder as text-embedding-3-small)."""
    if _TIKTOKEN_AVAILABLE and _ENC is not None:
        return len(_ENC.encode(text))
    # Rough fallback: ~4 chars per token
    return max(1, len(text) // 4)


def _encode(text: str) -> list[int]:
    if _TIKTOKEN_AVAILABLE and _ENC is not None:
        return _ENC.encode(text)
    return list(text.encode())   # bytes as ints (fallback)


def _decode(tokens: list[int]) -> str:
    if _TIKTOKEN_AVAILABLE and _ENC is not None:
        return _ENC.decode(tokens)
    return bytes(tokens).decode(errors="replace")


# ── Page-header chapter detection ──────────────────────────────────────────────

# IRS publications have page headers like:
#   "Publication 334 (2025) Chapter 1 Filing and Paying Business Taxes 7"
#   "6 Chapter 1 Filing and Paying Business Taxes Publication 334 (2025)"
# We extract the chapter map BEFORE stripping these headers.

_HEADER_CH_RE_1 = re.compile(
    r"Publication\s+\d+\s*\(\d{4}\)\s+Chapter\s+(\d+)\s+([\w\s\(\)&,\-/\']+?)(?:\s+\d+\s*$)",
    re.I | re.M,
)
_HEADER_CH_RE_2 = re.compile(
    r"^\d+\s+Chapter\s+(\d+)\s+([\w\s\(\)&,\-/\']+?)\s+Publication\s+\d+",
    re.I | re.M,
)


def _extract_chapter_map(pdf_path: Path) -> dict[int, tuple[int, str]]:
    """
    Scan the raw text of every page for chapter references in page headers.

    Returns a dict of page_number → (chapter_number, chapter_title).
    Multiple pages may map to the same chapter (one entry per page).
    """
    page_chapter: dict[int, tuple[int, str]] = {}
    if not _PDFPLUMBER_AVAILABLE:
        return page_chapter

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                raw = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                lines = raw.split("\n")
                # Check first/last 3 lines for header/footer chapter references
                check_lines = lines[:3] + lines[-3:]
                for line in check_lines:
                    for regex in (_HEADER_CH_RE_1, _HEADER_CH_RE_2):
                        m = regex.search(line)
                        if m:
                            ch_num = int(m.group(1))
                            ch_title = m.group(2).strip()
                            # Remove trailing page numbers from title
                            ch_title = _TRAILING_PAGENUM_RE.sub("", ch_title).strip()
                            page_chapter[page.page_number] = (ch_num, ch_title)
                            break
                    else:
                        continue
                    break  # found a match for this page
    except Exception as exc:
        logger.warning("Chapter map extraction failed: %s", exc)

    return page_chapter


def _build_chapter_ranges(
    page_chapter: dict[int, tuple[int, str]],
) -> list[tuple[int, int, str]]:
    """
    Convert per-page chapter map to chapter ranges: (start_page, end_page, title).
    """
    if not page_chapter:
        return []

    # Group by chapter number
    ch_pages: dict[int, tuple[str, int, int]] = {}  # ch_num → (title, min_page, max_page)
    for page, (ch_num, ch_title) in page_chapter.items():
        if ch_num not in ch_pages:
            ch_pages[ch_num] = (ch_title, page, page)
        else:
            old = ch_pages[ch_num]
            ch_pages[ch_num] = (old[0], min(old[1], page), max(old[2], page))

    # Sort by chapter number and return as ranges
    ranges = []
    sorted_chapters = sorted(ch_pages.keys())
    for ch_num in sorted_chapters:
        title, first_page, last_page = ch_pages[ch_num]
        label = f"Chapter {ch_num}. {title}"
        ranges.append((first_page, last_page, label))

    return ranges


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_pages(pdf_path: Path) -> list[dict]:
    """
    Return a list of dicts: {page_num, text} for every page in the PDF.
    Strips IRS page headers/footers and leading/trailing whitespace.
    """
    if not _PDFPLUMBER_AVAILABLE:
        raise ImportError(
            "pdfplumber is required for PDF parsing. "
            "Install it with: pip install pdfplumber --break-system-packages"
        )

    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            # Strip IRS headers/footers
            cleaned = _HEADER_FOOTER_RE.sub("", raw)
            # Collapse runs of 3+ blank lines to 2
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            if cleaned:
                pages.append({"page_num": i, "text": cleaned})
    return pages


# ── Heading detection ──────────────────────────────────────────────────────────

def _detect_heading(line: str) -> tuple[Optional[str], Optional[str]]:
    """
    Return (chapter, section) if the line looks like a heading, else (None, None).

    Heuristics:
    · "Chapter N Title" or "Part N Title" → chapter
    · Short ALL-CAPS line (≤ 60 chars) → chapter
    · Title-cased line ≤ 60 chars ending without punctuation → section

    Trailing page numbers (e.g. "Chapter 5 Income 47") are stripped.
    Lines beginning with a page number followed by "Chapter/Part" are TOC
    artefacts and are rejected entirely (handled by _HEADER_FOOTER_RE upstream,
    but guarded here too).
    """
    line = line.strip()
    if not line or len(line) > 120:
        return None, None

    # Reject IRS TOC lines: "47 Chapter 5 …" or "92 Chapter 10 …"
    if re.match(r"^\d+\s+(?:Chapter|Part)\s+\d+", line, re.I):
        return None, None

    ch_m = re.match(r"^(Chapter|Part)\s+\d+[\.\s]+(.+)", line, re.I)
    if ch_m:
        # Strip trailing page numbers: "Chapter 5 Wages … 47" → "Chapter 5 Wages …"
        clean = _TRAILING_PAGENUM_RE.sub("", line).strip()
        return clean, None

    if line.isupper() and 5 < len(line) <= 60:
        return line, None

    if (line.istitle() or (line[0].isupper() and line[-1] not in ".?!,;:")) \
            and 5 < len(line) <= 60 and " " in line:
        # Strip leading/trailing page numbers from TOC-style section labels
        clean = re.sub(r"^\d+\s+", "", line)           # "92 Standard Deduction" → "Standard Deduction"
        clean = _TRAILING_PAGENUM_RE.sub("", clean).strip()
        if 5 < len(clean) <= 60 and " " in clean:
            return None, clean

    return None, None


# ── Paragraph splitting ────────────────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    """Split page text into paragraphs on blank lines."""
    raw_paras = re.split(r"\n{2,}", text)
    paras = []
    for p in raw_paras:
        p = p.replace("\n", " ").strip()
        if p and len(p) > 10:   # drop very short fragments
            paras.append(p)
    return paras


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk_paragraphs(
    paragraphs : list[str],
    max_tokens : int = MAX_TOKENS,
    overlap    : int = OVERLAP_TOKENS,
    hard_max   : int = HARD_MAX,
) -> list[str]:
    """
    Group paragraphs into chunks of ≤ max_tokens with overlap carried forward.

    If a single paragraph exceeds hard_max tokens it is split at sentence
    boundaries.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def _flush():
        nonlocal current, current_tokens
        if current:
            chunks.append(" ".join(current))
        current = []
        current_tokens = 0

    def _overlap_seed(paras: list[str]) -> list[str]:
        """Return the tail of paras that fits within `overlap` tokens."""
        seed: list[str] = []
        budget = overlap
        for p in reversed(paras):
            t = _count_tokens(p)
            if t <= budget:
                seed.insert(0, p)
                budget -= t
            else:
                break
        return seed

    for para in paragraphs:
        para_tok = _count_tokens(para)

        # If a single paragraph exceeds hard_max, split on sentences
        if para_tok > hard_max:
            _flush()
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf: list[str] = []
            buf_tok = 0
            for sent in sentences:
                st = _count_tokens(sent)
                if buf_tok + st > max_tokens and buf:
                    chunks.append(" ".join(buf))
                    seed = _overlap_seed(buf)
                    buf = seed + [sent]
                    buf_tok = _count_tokens(" ".join(buf))
                else:
                    buf.append(sent)
                    buf_tok += st
            if buf:
                chunks.append(" ".join(buf))
            continue

        if current_tokens + para_tok > max_tokens and current:
            _flush()
            # Start new chunk with overlap from previous
            seed = _overlap_seed(chunks[-1].split(". ") if chunks else [])
            current = seed
            current_tokens = _count_tokens(" ".join(current))

        current.append(para)
        current_tokens += para_tok

    _flush()
    return chunks


# ── Cross-reference extraction ─────────────────────────────────────────────────

def _extract_refs(text: str) -> tuple[list[str], list[str]]:
    """Return (form_refs, line_refs) extracted from chunk text."""
    form_refs: list[str] = []
    for m in _FORM_RE.finditer(text):
        form_refs.append(f"Form{m.group(1)}")
    for m in _SCHED_RE.finditer(text):
        form_refs.append(f"Schedule{m.group(1)}")
    form_refs = list(dict.fromkeys(form_refs))

    line_refs = [m.group(1).lower() for m in _LINE_RE.finditer(text)]
    line_refs = list(dict.fromkeys(line_refs))

    return form_refs, line_refs


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_publication_pdf(
    pdf_path   : str | Path,
    pub_number : str,
    tax_year   : int,
    max_tokens : int = MAX_TOKENS,
    overlap    : int = OVERLAP_TOKENS,
) -> Layer3ParseResult:
    """
    Parse an IRS publication PDF into text chunks ready for embedding.

    Args:
        pdf_path   : Path to the PDF file.
        pub_number : Publication number string, e.g. "17", "550", "590a".
        tax_year   : Tax year the publication covers.
        max_tokens : Target tokens per chunk (default 400).
        overlap    : Overlap tokens carried to the next chunk (default 50).

    Returns:
        Layer3ParseResult with Publication metadata + list[PublicationChunk].
    """
    path = Path(pdf_path)
    errors: list[str]   = []
    warnings: list[str] = []

    pub_id    = f"p{pub_number}-{tax_year}"
    pub_title = PUB_TITLES.get(pub_number, f"IRS Publication {pub_number}")

    if not path.exists():
        return Layer3ParseResult(
            publication=Publication(
                pub_id=pub_id, pub_number=pub_number,
                pub_title=pub_title, tax_year=tax_year,
            ),
            chunks=[],
            parse_success=False,
            errors=[f"File not found: {pdf_path}"],
        )

    if not _PDFPLUMBER_AVAILABLE:
        return Layer3ParseResult(
            publication=Publication(
                pub_id=pub_id, pub_number=pub_number,
                pub_title=pub_title, tax_year=tax_year,
                source_path=str(path),
            ),
            chunks=[],
            parse_success=False,
            errors=["pdfplumber not installed — run: pip install pdfplumber"],
        )

    # PDF hash for dedup
    pdf_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    # Extract text per page
    try:
        pages = _extract_pages(path)
    except Exception as exc:
        return Layer3ParseResult(
            publication=Publication(
                pub_id=pub_id, pub_number=pub_number,
                pub_title=pub_title, tax_year=tax_year,
                source_path=str(path), pdf_hash=pdf_hash,
            ),
            chunks=[],
            parse_success=False,
            errors=[f"PDF extraction failed: {exc}"],
        )

    page_count = max((p["page_num"] for p in pages), default=0)
    logger.info("Extracted %d pages from %s", page_count, path.name)

    # ── Extract chapter map from page headers (pre-strip) ────────────────
    page_chapter_map = _extract_chapter_map(path)
    chapter_ranges = _build_chapter_ranges(page_chapter_map)
    if chapter_ranges:
        logger.info(
            "Detected %d chapters from page headers: %s",
            len(chapter_ranges),
            ", ".join(label for _, _, label in chapter_ranges),
        )

    def _chapter_for_page(page_num: int) -> str:
        """Look up the chapter title for a page number from header-derived map."""
        for start_p, end_p, label in chapter_ranges:
            if start_p <= page_num <= end_p:
                return label
        return ""

    # Walk pages, detect headings, build chunks
    chunks:          list[PublicationChunk] = []
    chunk_index      = 0
    current_chapter  = ""
    current_section  = ""

    # Each entry is (paragraph_text, page_num) so sub-chunks inherit
    # the correct starting page even when heading detection misses headings.
    para_buffer: list[tuple[str, int]] = []

    def _flush_buffer():
        nonlocal chunk_index
        if not para_buffer:
            return
        texts     = [p for p, _ in para_buffer]
        page_nums = [n for _, n in para_buffer]
        text_chunks = _chunk_paragraphs(texts, max_tokens, overlap)

        # Map each output chunk back to its starting paragraph index so we can
        # assign the correct page_start.  We do this by matching the first
        # ~40 characters of each chunk against the flattened paragraph list.
        para_offsets: list[int] = []  # cumulative char offset of each para
        flat = ""
        for t in texts:
            para_offsets.append(len(flat))
            flat += t + " "

        def _chunk_page(chunk_text: str) -> int:
            """Return the page number of the paragraph where this chunk begins."""
            prefix = chunk_text[:40].strip()
            pos = flat.find(prefix)
            if pos < 0:
                return page_nums[0]
            # Find which paragraph contains this offset
            for i, offset in enumerate(reversed(para_offsets)):
                idx = len(para_offsets) - 1 - i
                if offset <= pos:
                    return page_nums[idx]
            return page_nums[0]

        p_end = page_nums[-1]
        for tc in text_chunks:
            if not tc.strip():
                continue
            p_start = _chunk_page(tc)
            form_refs, line_refs = _extract_refs(tc)
            # Use page-header chapter map as fallback when heading
            # detection didn't find a chapter title
            effective_chapter = current_chapter or _chapter_for_page(p_start)
            chunks.append(PublicationChunk(
                chunk_id      = f"{pub_id}::{chunk_index:04d}",
                pub_id        = pub_id,
                pub_number    = pub_number,
                tax_year      = tax_year,
                chunk_index   = chunk_index,
                chapter_title = effective_chapter,
                section_title = current_section,
                page_start    = p_start,
                page_end      = p_end,
                text          = tc,
                token_count   = _count_tokens(tc),
                form_refs     = form_refs,
                line_refs     = line_refs,
            ))
            chunk_index += 1
        para_buffer.clear()

    for page in pages:
        page_num = page["page_num"]
        paragraphs = _split_paragraphs(page["text"])

        for para in paragraphs:
            ch, sec = _detect_heading(para)
            if ch:
                _flush_buffer()
                current_chapter = ch
                current_section = ""
            elif sec:
                _flush_buffer()
                current_section = sec
            else:
                para_buffer.append((para, page_num))

    _flush_buffer()   # flush anything remaining

    if not chunks:
        errors.append("No text chunks extracted — PDF may be scanned/image-only.")

    publication = Publication(
        pub_id      = pub_id,
        pub_number  = pub_number,
        pub_title   = pub_title,
        tax_year    = tax_year,
        source_path = str(path),
        pdf_hash    = pdf_hash,
        page_count  = page_count,
        chunk_count = len(chunks),
    )

    logger.info(
        "Parsed %s: %d chunks, avg %.0f tokens/chunk",
        pub_id, len(chunks),
        sum(c.token_count for c in chunks) / max(len(chunks), 1),
    )

    return Layer3ParseResult(
        publication   = publication,
        chunks        = chunks,
        parse_success = len(errors) == 0,
        errors        = errors,
        warnings      = warnings,
    )
