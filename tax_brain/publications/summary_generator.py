"""
tax_brain/layer3/summary_generator.py

Generates Tier 1 (publication summary) and Tier 2 (section summary) anchor
chunks from detail chunks parsed out of IRS publication PDFs.

These anchor chunks serve as navigation points in the hierarchical retrieval
architecture. They are embedded alongside detail chunks but carry a different
chunk_type, enabling two-stage retrieval:

  Stage 1: Search summaries → identify relevant pub + section
  Stage 2: Search detail chunks within those sections → get specific answers

Summary generation strategies:
  1. EXTRACTIVE (no LLM needed)  — default
     Builds summaries from chapter titles, section titles, first paragraphs,
     and key terms extracted from the detail chunks.

  2. LLM-ENHANCED (optional, future)
     Sends section chunks to an LLM for a concise summary. Better quality
     but requires API calls and adds latency during ingestion.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

from tax_brain.publications.models import PublicationChunk
from tax_brain.publications.ontology import ChunkType, get_ontology

logger = logging.getLogger(__name__)


# ── Token counter (shared with pdf_parser) ───────────────────────────────────

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN = True
except Exception:
    _ENC = None
    _TIKTOKEN = False


def _count_tokens(text: str) -> int:
    if _TIKTOKEN and _ENC is not None:
        return len(_ENC.encode(text))
    return max(1, len(text) // 4)


# ── Key term extraction ──────────────────────────────────────────────────────

# Patterns that indicate dollar thresholds, percentages, or limits
_THRESHOLD_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?|"                    # "$250,000", "$7.25"
    r"\d+(?:\.\d+)?%|"                         # "7.5%", "15.3%"
    r"(?:limit|maximum|minimum|threshold|cap|ceiling|floor)"
    r"\s+(?:is|of|for)?\s*\$?[\d,]+",          # "limit is $6,500"
    re.I,
)

_FORM_RE = re.compile(r"\bForm\s+([\w\-]+\d[\w\-]*)", re.I)
_SCHED_RE = re.compile(r"\bSchedule\s+([A-Z0-9\-]+)", re.I)


def _extract_key_terms(chunks: list[PublicationChunk]) -> list[str]:
    """Extract dollar thresholds, form references, and key limits from chunks."""
    terms: list[str] = []
    seen: set[str] = set()

    for chunk in chunks:
        # Dollar thresholds and percentages
        for match in _THRESHOLD_RE.finditer(chunk.text):
            term = match.group().strip()
            if term not in seen and len(term) > 2:
                seen.add(term)
                terms.append(term)

        # Form references
        for ref in chunk.form_refs:
            if ref not in seen:
                seen.add(ref)
                terms.append(ref)

    return terms[:20]  # Cap to avoid overly long summaries


# ── Chapter inference from page ranges ──────────────────────────────────────

def _infer_chapters_from_pages(
    detail_chunks: list[PublicationChunk],
) -> dict[str, list[PublicationChunk]]:
    """
    Infer chapter groupings when the PDF parser didn't detect chapter titles.

    IRS publications include "Chapter N Title" in page headers/footers.  The
    pdf_parser strips these as boilerplate, leaving chapter_title empty.  We
    reconstruct chapter boundaries by scanning chunk text for residual
    "Chapter N" references and grouping chunks by their page_start.

    Falls back to page-range heuristic: splits chunks into roughly equal
    groups of ~30 chunks each, labelled by page range.
    """
    if not detail_chunks:
        return {}

    # Strategy 1: Look for "Chapter N Title" in chunk text near page transitions
    _CH_IN_TEXT = re.compile(
        r"(?:^|\n)\s*(?:\d+\s+)?Chapter\s+(\d+)[\.\s]+([\w\s\(\)&,\-/\']+?)(?:\s+Publication|\s*$)",
        re.I | re.M,
    )

    # Build a page → chapter map from residual chapter references in chunk text
    page_chapter: dict[int, tuple[int, str]] = {}  # page_num → (ch_num, ch_title)
    for chunk in detail_chunks:
        for m in _CH_IN_TEXT.finditer(chunk.text):
            ch_num = int(m.group(1))
            ch_title = m.group(2).strip()
            # Deduplicate: keep the first (lowest page) occurrence per chapter
            page = chunk.page_start
            if ch_num not in {v[0] for v in page_chapter.values() if v[0] == ch_num}:
                page_chapter[page] = (ch_num, ch_title)
            elif page not in page_chapter:
                page_chapter[page] = (ch_num, ch_title)

    if len(page_chapter) >= 2:
        # We found chapter references — assign each chunk to its chapter by page
        sorted_pages = sorted(page_chapter.keys())
        chapter_ranges: list[tuple[int, int, str]] = []  # (start_page, end_page, title)
        for i, start_page in enumerate(sorted_pages):
            ch_num, ch_title = page_chapter[start_page]
            end_page = sorted_pages[i + 1] - 1 if i + 1 < len(sorted_pages) else 9999
            label = f"Chapter {ch_num}. {ch_title}"
            chapter_ranges.append((start_page, end_page, label))

        groups: dict[str, list[PublicationChunk]] = defaultdict(list)
        for chunk in detail_chunks:
            assigned = False
            for start_p, end_p, label in chapter_ranges:
                if start_p <= chunk.page_start <= end_p:
                    groups[label].append(chunk)
                    assigned = True
                    break
            if not assigned:
                # Chunks before chapter 1 → "Introduction"
                groups["Introduction"].append(chunk)

        if len(groups) >= 2:
            logger.info(
                "Inferred %d chapters from page-header references", len(groups),
            )
            return dict(groups)

    # Strategy 2: Simple page-range split (~30 chunks per group)
    if len(detail_chunks) > 30:
        GROUP_SIZE = max(20, len(detail_chunks) // 6)
        groups = defaultdict(list)
        for i, chunk in enumerate(detail_chunks):
            group_idx = i // GROUP_SIZE
            p_start = detail_chunks[group_idx * GROUP_SIZE].page_start
            p_end = detail_chunks[min((group_idx + 1) * GROUP_SIZE - 1, len(detail_chunks) - 1)].page_end
            label = f"Pages {p_start}–{p_end}"
            groups[label].append(chunk)

        logger.info(
            "Split %d chunks into %d page-range groups (fallback)",
            len(detail_chunks), len(groups),
        )
        return dict(groups)

    # Small publication — single group
    return {"(General)": list(detail_chunks)}


# ── Tier 1: Publication summary ──────────────────────────────────────────────

def generate_pub_summary(
    pub_number: str,
    pub_title: str,
    tax_year: int,
    detail_chunks: list[PublicationChunk],
    max_tokens: int = 500,
) -> PublicationChunk:
    """
    Generate a Tier 1 publication summary anchor chunk.

    The summary answers: "What does this publication cover, and when should
    a CPA consult it?" It's built extractively from:
      - Publication title and metadata
      - Chapter/section titles (table of contents)
      - Key terms and thresholds found in the content
      - Topic ontology mapping
    """
    pub_id = f"p{pub_number}-{tax_year}"

    # Collect unique chapter and section titles in order
    chapters: list[str] = []
    sections_by_chapter: dict[str, list[str]] = defaultdict(list)
    seen_chapters: set[str] = set()
    seen_sections: set[str] = set()

    for chunk in detail_chunks:
        if chunk.chapter_title and chunk.chapter_title not in seen_chapters:
            seen_chapters.add(chunk.chapter_title)
            chapters.append(chunk.chapter_title)
        if chunk.section_title and chunk.section_title not in seen_sections:
            seen_sections.add(chunk.section_title)
            ch = chunk.chapter_title or "(General)"
            sections_by_chapter[ch].append(chunk.section_title)

    # Build the Table of Contents
    toc_lines: list[str] = []
    for ch in chapters:
        toc_lines.append(f"  - {ch}")
        for sec in sections_by_chapter.get(ch, [])[:5]:  # Cap sections per chapter
            toc_lines.append(f"    - {sec}")
    toc_text = "\n".join(toc_lines) if toc_lines else "(No chapter structure detected)"

    # Extract key terms
    key_terms = _extract_key_terms(detail_chunks)
    terms_text = ", ".join(key_terms[:15]) if key_terms else "(none detected)"

    # Get forms referenced
    all_forms: set[str] = set()
    for chunk in detail_chunks:
        all_forms.update(chunk.form_refs)
    forms_text = ", ".join(sorted(all_forms)[:10]) if all_forms else "(none)"

    # Look up topic ontology for this publication
    ontology = get_ontology()
    related_topics: list[str] = []
    for topic in ontology._topics.values():
        for ps in topic.pub_sections:
            if ps.pub_number == pub_number:
                related_topics.append(topic.display_name)
                break

    topics_text = ", ".join(related_topics[:10]) if related_topics else "(unmapped)"

    # Get publication description from registry
    try:
        from tax_brain.publications.registry import get_registry
        reg = get_registry()
        meta = reg.get(pub_number)
        description = meta.description if meta else ""
        category = meta.category if meta else ""
    except ImportError:
        description = ""
        category = ""

    # Assemble the summary
    summary_parts = [
        f"[PUBLICATION SUMMARY] IRS Publication {pub_number}: {pub_title} "
        f"(Tax Year {tax_year})",
        "",
        f"Category: {category}" if category else "",
        f"Description: {description}" if description else "",
        "",
        "This publication covers the following topics:",
        toc_text,
        "",
        f"Related tax topics: {topics_text}",
        f"Key forms and schedules: {forms_text}",
        f"Key thresholds and limits: {terms_text}",
        "",
        f"Consult this publication for guidance on: "
        f"{', '.join(related_topics[:5]) if related_topics else pub_title}.",
    ]

    summary_text = "\n".join(line for line in summary_parts if line is not None)

    # Truncate if needed
    while _count_tokens(summary_text) > max_tokens and summary_parts:
        summary_parts.pop(-2)  # Remove from before the last line
        summary_text = "\n".join(line for line in summary_parts if line is not None)

    # Map to topic IDs
    topic_ids = []
    for topic in ontology._topics.values():
        for ps in topic.pub_sections:
            if ps.pub_number == pub_number and ps.relevance == "primary":
                topic_ids.append(topic.topic_id)
                break

    return PublicationChunk(
        chunk_id=f"{pub_id}::summary",
        pub_id=pub_id,
        pub_number=pub_number,
        tax_year=tax_year,
        chunk_index=-1,  # Summaries sort before detail chunks
        chapter_title="(Publication Summary)",
        section_title="",
        page_start=1,
        page_end=detail_chunks[-1].page_end if detail_chunks else 1,
        text=summary_text,
        token_count=_count_tokens(summary_text),
        form_refs=sorted(all_forms)[:10],
        line_refs=[],
        chunk_type=ChunkType.PUB_SUMMARY,
        topic_ids=topic_ids,
    )


# ── Tier 2: Section summaries ───────────────────────────────────────────────

def generate_section_summaries(
    pub_number: str,
    pub_title: str,
    tax_year: int,
    detail_chunks: list[PublicationChunk],
    max_tokens_per_summary: int = 350,
) -> list[PublicationChunk]:
    """
    Generate Tier 2 section summary anchor chunks.

    Creates one summary per unique chapter_title found in the detail chunks.
    Each summary answers: "What rules and guidance does this section contain?"

    Built extractively from:
      - Chapter/section title
      - First paragraph of the chapter (usually an overview)
      - Key thresholds and form references within the section
      - Sub-section titles
    """
    pub_id = f"p{pub_number}-{tax_year}"
    ontology = get_ontology()

    # Group chunks by chapter — use detected chapter_title if available,
    # otherwise infer chapters from page-header residuals or page ranges
    chunks_by_chapter: dict[str, list[PublicationChunk]] = defaultdict(list)
    has_chapters = any(c.chapter_title for c in detail_chunks)

    if has_chapters:
        for chunk in detail_chunks:
            key = chunk.chapter_title or "(General)"
            chunks_by_chapter[key].append(chunk)
    else:
        # PDF parser didn't detect headings — infer from page headers
        chunks_by_chapter = defaultdict(list, _infer_chapters_from_pages(detail_chunks))

    summaries: list[PublicationChunk] = []
    summary_index = 0

    for chapter_title, chapter_chunks in chunks_by_chapter.items():
        if chapter_title == "(General)" and len(chapter_chunks) < 3:
            continue  # Skip tiny general sections

        # Sub-sections within this chapter
        sub_sections: list[str] = []
        seen: set[str] = set()
        for c in chapter_chunks:
            if c.section_title and c.section_title not in seen:
                seen.add(c.section_title)
                sub_sections.append(c.section_title)

        # First meaningful paragraph (skip very short intro lines)
        first_para = ""
        for c in chapter_chunks[:3]:
            if len(c.text) > 100:
                # Take first ~150 words
                words = c.text.split()
                first_para = " ".join(words[:150])
                if len(words) > 150:
                    first_para += "..."
                break

        # Key terms and forms in this section
        key_terms = _extract_key_terms(chapter_chunks)
        all_forms: set[str] = set()
        for c in chapter_chunks:
            all_forms.update(c.form_refs)

        # Find matching topic IDs
        topic_ids: list[str] = []
        for topic in ontology._topics.values():
            for ps in topic.pub_sections:
                if ps.pub_number == pub_number and (
                    ps.chapter.lower() in chapter_title.lower()
                    or chapter_title.lower() in ps.chapter.lower()
                    or (not ps.chapter and ps.relevance == "primary")
                ):
                    if topic.topic_id not in topic_ids:
                        topic_ids.append(topic.topic_id)

        # Assemble section summary
        sub_sec_text = ""
        if sub_sections:
            sub_sec_text = "\nKey sections: " + ", ".join(sub_sections[:8])

        forms_text = ", ".join(sorted(all_forms)[:8]) if all_forms else ""
        terms_text = ", ".join(key_terms[:10]) if key_terms else ""

        summary_parts = [
            f"[SECTION SUMMARY] IRS Pub {pub_number} — {chapter_title}",
            "",
        ]
        if first_para:
            summary_parts.append(first_para)
            summary_parts.append("")
        if sub_sec_text:
            summary_parts.append(sub_sec_text)
        if forms_text:
            summary_parts.append(f"Forms referenced: {forms_text}")
        if terms_text:
            summary_parts.append(f"Key thresholds/limits: {terms_text}")

        summary_text = "\n".join(summary_parts)

        # Truncate if needed
        while _count_tokens(summary_text) > max_tokens_per_summary and len(summary_parts) > 2:
            summary_parts.pop(-1)
            summary_text = "\n".join(summary_parts)

        page_start = chapter_chunks[0].page_start if chapter_chunks else 0
        page_end = chapter_chunks[-1].page_end if chapter_chunks else 0

        summaries.append(PublicationChunk(
            chunk_id=f"{pub_id}::section_summary::{summary_index:04d}",
            pub_id=pub_id,
            pub_number=pub_number,
            tax_year=tax_year,
            chunk_index=-(summary_index + 2),  # Negative indices for summaries
            chapter_title=chapter_title,
            section_title="(Section Summary)",
            page_start=page_start,
            page_end=page_end,
            text=summary_text,
            token_count=_count_tokens(summary_text),
            form_refs=sorted(all_forms)[:8],
            line_refs=[],
            chunk_type=ChunkType.SECTION_SUMMARY,
            topic_ids=topic_ids,
        ))
        summary_index += 1

    logger.info(
        "Generated %d section summaries for Pub %s (%d)",
        len(summaries), pub_number, tax_year,
    )
    return summaries


# ── Combined: generate all anchor chunks for a publication ───────────────────

def generate_anchor_chunks(
    pub_number: str,
    pub_title: str,
    tax_year: int,
    detail_chunks: list[PublicationChunk],
) -> list[PublicationChunk]:
    """
    Generate all anchor chunks (Tier 1 pub summary + Tier 2 section summaries)
    for a single publication.

    Returns:
        List of anchor chunks ready to be embedded and stored alongside
        the detail chunks.
    """
    anchors: list[PublicationChunk] = []

    # Tier 1: Publication summary
    pub_summary = generate_pub_summary(
        pub_number=pub_number,
        pub_title=pub_title,
        tax_year=tax_year,
        detail_chunks=detail_chunks,
    )
    anchors.append(pub_summary)

    # Tier 2: Section summaries
    section_summaries = generate_section_summaries(
        pub_number=pub_number,
        pub_title=pub_title,
        tax_year=tax_year,
        detail_chunks=detail_chunks,
    )
    anchors.extend(section_summaries)

    logger.info(
        "Pub %s (%d): 1 pub summary + %d section summaries = %d anchor chunks",
        pub_number, tax_year, len(section_summaries), len(anchors),
    )
    return anchors
