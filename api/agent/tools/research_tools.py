"""Research tools — thin async wrappers around taxkb retriever components.

Each tool bridges the async API layer to taxkb's sync psycopg2 calls
via asyncio.to_thread(). Tools are registered into a ToolRegistry by
build_research_tool_registry().
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

from api.agent.research_session import ResearchSession
from api.agent.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_MAX_PASSAGES = 8
_MAX_TEXT_LEN = 500


# ── Lazy singletons for taxkb components ─────────────────────────────────

@lru_cache(maxsize=1)
def _get_retriever() -> Any:
    from taxkb.factories import create_retriever
    return create_retriever()


@lru_cache(maxsize=1)
def _get_ontology() -> Any:
    from taxkb.publications.ontology import get_ontology
    return get_ontology()


def _get_instruction_searcher(session: ResearchSession) -> Any:
    from taxkb.agent.search import InstructionSearcher
    return InstructionSearcher(pool=session.taxkb_pool)


def _get_rule_searcher(session: ResearchSession) -> Any:
    from taxkb.agent.search import RuleSearcher
    return RuleSearcher(pool=session.taxkb_pool)


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _pub_title(pub_number: str) -> str:
    try:
        from taxkb.publications.models import PUB_TITLES
        return PUB_TITLES.get(pub_number, f"Publication {pub_number}")
    except Exception:
        return f"Publication {pub_number}"


def _expand(query: str) -> str:
    """Run query expansion, swallowing errors."""
    try:
        from taxkb.agent.query_expander import expand_query
        return expand_query(query)
    except Exception:
        return query


# ── Tool handlers ─────────────────────────────────────────────────────────────

async def find_relevant_publications(
    session: ResearchSession, *, query: str, tax_year: int = 2025,
) -> dict:
    """Stage 1: Navigate summary chunks to find relevant publications."""
    try:
        retriever = _get_retriever()
        expanded = await asyncio.to_thread(_expand, query)

        nav_pubs, nav_sections, ms = await asyncio.to_thread(
            retriever._navigate, expanded, tax_year,
        )
    except Exception as exc:
        logger.warning("find_relevant_publications failed: %s", exc)
        return {
            "publications": [], "sections": [],
            "kb_unavailable": True,
            "suggestion": "The IRS knowledge base is not available. Answer the question using your own tax knowledge and clearly note it is not verified against the KB.",
        }

    publications = [
        {"pub_number": pn, "title": _pub_title(pn)}
        for pn in nav_pubs
    ]
    sections = [
        {"pub_number": pn, "chapter": ch}
        for pn, ch in nav_sections
    ]

    suggestion = ""
    if publications:
        top_pubs = [p["pub_number"] for p in publications[:3]]
        suggestion = (
            f"Found {len(publications)} relevant publications. "
            f"Use search_publication_details with pub_numbers={top_pubs} to get specific rules."
        )
    else:
        suggestion = (
            "No publications found in the knowledge base. "
            "Answer using your own tax knowledge and clearly note it is not verified against the KB."
        )

    return {
        "publications": publications,
        "sections": sections,
        "suggestion": suggestion,
        "search_time_ms": round(ms),
    }


async def search_publication_details(
    session: ResearchSession, *, query: str,
    pub_numbers: list[str], tax_year: int = 2025,
) -> dict:
    """Stage 2: Drill into specific publications for detailed passages."""
    try:
        retriever = _get_retriever()
        expanded = await asyncio.to_thread(_expand, query)

        contexts, ms = await asyncio.to_thread(
            retriever._search,
            query=expanded, top_k=_MAX_PASSAGES,
            pub_filter=pub_numbers, tax_year=tax_year,
        )
    except Exception as exc:
        logger.warning("search_publication_details failed: %s", exc)
        return {
            "passages": [], "total_found": 0,
            "kb_unavailable": True,
            "suggestion": "The IRS knowledge base is not available. Answer using your own tax knowledge.",
        }

    passages = [
        {
            "text": _truncate(ctx.text),
            "pub_number": ctx.reference,
            "pub_title": ctx.title,
            "chapter": ctx.chapter,
            "section": ctx.section,
            "page": ctx.page,
            "score": round(ctx.score, 3),
        }
        for ctx in contexts[:_MAX_PASSAGES]
    ]

    return {
        "passages": passages,
        "total_found": len(contexts),
        "search_time_ms": round(ms),
    }


async def find_cross_references(
    session: ResearchSession, *, topic: str,
    already_found_pubs: list[str] | None = None,
) -> dict:
    """Find related publications via the topic ontology."""
    try:
        ontology = _get_ontology()
        already = set(already_found_pubs or [])

        matched_topics = await asyncio.to_thread(ontology.find_by_query, topic)

        related = []
        seen = set()
        for t in matched_topics[:5]:
            pub_numbers = await asyncio.to_thread(
                ontology.get_pub_numbers_for_topic, t.topic_id,
            )
            for pn in pub_numbers:
                if pn not in already and pn not in seen:
                    seen.add(pn)
                    related.append({
                        "pub_number": pn,
                        "title": _pub_title(pn),
                        "topic": t.label if hasattr(t, "label") else t.topic_id,
                    })
    except Exception as exc:
        logger.warning("find_cross_references failed: %s", exc)
        return {"related_publications": [], "suggestion": "Cross-reference lookup unavailable."}

    suggestion = ""
    if related:
        new_pubs = [r["pub_number"] for r in related[:3]]
        suggestion = (
            f"Found {len(related)} related publications. "
            f"Use search_publication_details with pub_numbers={new_pubs} for additional detail."
        )
    else:
        suggestion = "No additional cross-references found for this topic."

    return {"related_publications": related, "suggestion": suggestion}


async def search_form_instructions(
    session: ResearchSession, *, query: str,
    form_number: str | None = None, line_reference: str | None = None,
) -> dict:
    """Search IRS form instructions for line-by-line guidance."""
    try:
        searcher = _get_instruction_searcher(session)

        form_refs = [form_number] if form_number else []
        line_refs = [line_reference] if line_reference else []

        contexts, ms = await asyncio.to_thread(
            searcher.retrieve, query,
            form_refs=form_refs, line_refs=line_refs, top_k=5,
        )
    except Exception as exc:
        logger.warning("search_form_instructions failed: %s", exc)
        return {"instructions": [], "kb_unavailable": True,
                "suggestion": "Form instruction lookup unavailable. Answer using your own knowledge."}

    instructions = [
        {
            "form_type": ctx.reference,
            "line_reference": ctx.section,
            "text": _truncate(ctx.text),
            "chapter": ctx.chapter,
        }
        for ctx in contexts
    ]

    return {"instructions": instructions, "search_time_ms": round(ms)}


async def search_mef_rules(
    session: ResearchSession, *, query: str,
    form_refs: list[str] | None = None, tax_year: int = 2025,
) -> dict:
    """Search MeF validation rules for e-file requirements."""
    try:
        searcher = _get_rule_searcher(session)

        contexts, ms = await asyncio.to_thread(
            searcher.retrieve, query,
            form_refs=form_refs or [], top_k=5, tax_year=tax_year,
        )
    except Exception as exc:
        logger.warning("search_mef_rules failed: %s", exc)
        return {"rules": [], "kb_unavailable": True,
                "suggestion": "MeF rule lookup unavailable. Answer using your own knowledge."}

    rules = [
        {
            "rule_id": ctx.chunk_id,
            "text": _truncate(ctx.text),
            "reference": ctx.reference,
            "severity": ctx.section,
        }
        for ctx in contexts
    ]

    return {"rules": rules, "search_time_ms": round(ms)}


async def compare_tax_years(
    session: ResearchSession, *, query: str,
    years: list[int], pub_filter: list[str] | None = None,
) -> dict:
    """Compare rules across multiple tax years."""
    try:
        retriever = _get_retriever()

        contexts, ms, metadata = await asyncio.to_thread(
            retriever._retrieve_cross_year,
            query, top_k=8, pub_filter=pub_filter, comparison_years=years,
        )
    except Exception as exc:
        logger.warning("compare_tax_years failed: %s", exc)
        return {"passages": [], "years": years, "kb_unavailable": True,
                "suggestion": "Year comparison unavailable. Answer using your own knowledge."}

    passages = [
        {
            "text": _truncate(ctx.text),
            "pub_number": ctx.reference,
            "chapter": ctx.chapter,
            "page": ctx.page,
            "score": round(ctx.score, 3),
        }
        for ctx in contexts[:_MAX_PASSAGES]
    ]

    return {
        "passages": passages,
        "years": years,
        "search_time_ms": round(ms),
    }


# ── Registry builder ──────────────────────────────────────────────────────────

def build_research_tool_registry() -> ToolRegistry:
    """Create a ToolRegistry with all 6 research tools."""
    registry = ToolRegistry()

    registry.register(
        name="find_relevant_publications",
        description=(
            "Stage 1: Navigate the IRS knowledge base to identify which publications "
            "are relevant to a question. Returns publication names and key sections. "
            "Use this FIRST before drilling into specific publications."
        ),
        handler=find_relevant_publications,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query about a tax topic."},
                "tax_year": {"type": "integer", "description": "Tax year to search. Default 2025."},
            },
            "required": ["query"],
        },
    )

    registry.register(
        name="search_publication_details",
        description=(
            "Stage 2: Deep search within specific IRS publications for detailed rules, "
            "limits, thresholds, and procedures. Use AFTER find_relevant_publications "
            "has identified which publications to search. Returns specific passages with citations."
        ),
        handler=search_publication_details,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query — be specific with IRC sections, dollar amounts, or form numbers when known."},
                "pub_numbers": {"type": "array", "items": {"type": "string"}, "description": "Publication numbers to search (e.g., ['590a', '17'])."},
                "tax_year": {"type": "integer", "description": "Tax year to search. Default 2025."},
            },
            "required": ["query", "pub_numbers"],
        },
    )

    registry.register(
        name="find_cross_references",
        description=(
            "Find related IRS publications that the initial search might have missed, "
            "using the topic ontology. Use after an initial search when the topic might "
            "span multiple publications. Example: Roth conversions touch both Pub 590a "
            "(conversion process) and Pub 590b (distribution rules after conversion)."
        ),
        handler=find_cross_references,
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Tax topic to find cross-references for."},
                "already_found_pubs": {"type": "array", "items": {"type": "string"}, "description": "Publication numbers already found — these will be excluded from results."},
            },
            "required": ["topic"],
        },
    )

    registry.register(
        name="search_form_instructions",
        description=(
            "Search IRS form instructions for specific line-by-line guidance. "
            "Use when the question is about how to fill out a specific form line "
            "or what data goes on a specific schedule line."
        ),
        handler=search_form_instructions,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question about a form or line."},
                "form_number": {"type": "string", "description": "Form number (e.g., '1040', 'Schedule C')."},
                "line_reference": {"type": "string", "description": "Line reference (e.g., '1a', '31', 'Part II')."},
            },
            "required": ["query"],
        },
    )

    registry.register(
        name="search_mef_rules",
        description=(
            "Search MeF (Modernized e-File) validation rules. Use when the question "
            "involves e-filing requirements, rejection codes, or attachment rules."
        ),
        handler=search_mef_rules,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question about e-file rules or error codes."},
                "form_refs": {"type": "array", "items": {"type": "string"}, "description": "Form references to filter by."},
                "tax_year": {"type": "integer", "description": "Tax year. Default 2025."},
            },
            "required": ["query"],
        },
    )

    registry.register(
        name="compare_tax_years",
        description=(
            "Compare tax rules, limits, or thresholds across multiple tax years. "
            "Use for questions like 'How did the standard deduction change from 2024 to 2025?'"
        ),
        handler=compare_tax_years,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to compare across years."},
                "years": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "description": "Tax years to compare (e.g., [2024, 2025])."},
                "pub_filter": {"type": "array", "items": {"type": "string"}, "description": "Optional: restrict to specific publication numbers."},
            },
            "required": ["query", "years"],
        },
    )

    return registry
