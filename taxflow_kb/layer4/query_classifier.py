"""
taxflow_kb/layer4/query_classifier.py

Query intent classification and metadata extraction for CPA queries.

Classifies queries into intent types that determine retrieval strategy:
  - LOOKUP     : Specific threshold/limit questions ("What is the 2025 standard deduction?")
  - SCENARIO   : Multi-step fact patterns ("Client sold rental property after...")
  - FORM_LINE  : Form/schedule line number questions ("What goes on Schedule C line 31?")
  - RULE       : MeF validation rule questions ("What triggers Form 8960?")
  - COMPARISON : Year-over-year or option comparison ("Standard vs itemized for 2025?")
  - GENERAL    : General guidance questions (default)

Also extracts structured metadata:
  - tax_year   : Detected tax year from the query (e.g., 2025, 2024)
  - form_refs  : Referenced forms/schedules
  - pub_refs   : Referenced publication numbers
  - topic_tags : Detected tax topics for publication routing
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Enums and Models
# ──────────────────────────────────────────────────────────────────────────────


class QueryIntent(str, Enum):
    """Query intent classification."""
    LOOKUP = "lookup"
    SCENARIO = "scenario"
    FORM_LINE = "form_line"
    RULE = "rule"
    COMPARISON = "comparison"
    GENERAL = "general"


@dataclass
class QueryMetadata:
    """Structured metadata extracted from a CPA query."""
    original_query: str
    normalized_query: str = ""
    intent: QueryIntent = QueryIntent.GENERAL
    tax_year: Optional[int] = None
    comparison_years: list[int] = field(default_factory=list)  # multi-year comparison
    form_refs: list[str] = field(default_factory=list)
    pub_refs: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    confidence: float = 0.5  # 0-1, how confident we are in the classification


# ──────────────────────────────────────────────────────────────────────────────
# Topic-to-keyword mappings (case-insensitive matching)
# ──────────────────────────────────────────────────────────────────────────────

TOPIC_PATTERNS = [
    ("earned-income-credit", [
        r"earned income credit", r"\bEIC\b", r"\bEITC\b"
    ]),
    ("hsa", [
        r"\bHSA\b", r"health savings", r"\bHDHP\b"
    ]),
    ("ira", [
        r"\bIRA\b", r"individual retirement", r"traditional IRA", r"\bRoth\b"
    ]),
    ("retirement", [
        r"retirement account", r"retirement plan", r"401\(k\)", r"\b403\(b\)\b"
    ]),
    ("investments", [
        r"capital gain", r"investment income", r"dividend", r"\bstock\b"
    ]),
    ("capital-gains", [
        r"capital gain", r"long-term gain", r"short-term gain"
    ]),
    ("depreciation", [
        r"depreciation", r"section 179", r"\bMACRS\b", r"bonus depreciation"
    ]),
    ("business-property", [
        r"business property", r"fixed assets", r"property equipment"
    ]),
    ("rental-property", [
        r"rental property", r"rental income", r"landlord"
    ]),
    ("home-sale", [
        r"home sale", r"selling.*home", r"section 121", r"primary residence"
    ]),
    ("self-employment", [
        r"self-employed", r"self-employment", r"\bSchedule C\b", r"sole proprietor"
    ]),
    ("business", [
        r"\bbusiness\b", r"trade or business", r"small business"
    ]),
    ("estimated-tax", [
        r"estimated tax", r"quarterly payment", r"safe harbor"
    ]),
    ("deductions", [
        r"standard deduction", r"itemized", r"\bSchedule A\b"
    ]),
    ("dependents", [
        r"dependent", r"qualifying child", r"qualifying relative"
    ]),
    ("filing-status", [
        r"filing status", r"married filing", r"head of household", r"\bsingle\b"
    ]),
    ("rmd", [
        r"\bRMD\b", r"required minimum", r"life expectancy"
    ]),
    ("retirement-distributions", [
        r"retirement distribution", r"distribution rules"
    ]),
    ("contribution-limits", [
        r"contribution limit", r"deduction limit", r"phase-out"
    ]),
    ("mortgage-interest", [
        r"mortgage interest", r"home mortgage", r"\bpoints\b"
    ]),
    ("charitable-contributions", [
        r"charitable", r"donation", r"\bForm 8283\b"
    ]),
    ("medical-expenses", [
        r"medical expense", r"dental"
    ]),
    ("education", [
        r"education credit", r"\bAOTC\b", r"lifetime learning", r"\b529\b"
    ]),
    ("alimony-divorce", [
        r"alimony", r"divorce", r"separation"
    ]),
    ("gambling", [
        r"gambling", r"lottery", r"prize"
    ]),
    ("foreign-income", [
        r"foreign tax", r"foreign income", r"FBAR"
    ]),
    ("amt", [
        r"\bAMT\b", r"alternative minimum"
    ]),
    ("health-plans", [
        r"health plan", r"HSA", r"HDHP"
    ]),
]


# ──────────────────────────────────────────────────────────────────────────────
# Query Classifier
# ──────────────────────────────────────────────────────────────────────────────


def _extract_tax_year(query: str, default_tax_year: int = 2025) -> Optional[int]:
    """
    Extract tax year from query text.

    Matches patterns like:
    - "2025", "2024", "tax year 2023"
    - "for 2025", "in 2024"
    - "this year" → default_tax_year
    - "last year" → default_tax_year - 1

    Args:
        query: The query string to analyze
        default_tax_year: Year to use for "this year" references

    Returns:
        Detected tax year as int, or None if no year found
    """
    query_lower = query.lower()

    # Check for "this year" first (highest priority)
    if re.search(r"\bthis year\b", query_lower):
        return default_tax_year

    # Check for "last year"
    if re.search(r"\blast year\b", query_lower):
        return default_tax_year - 1

    # Check for "next year"
    if re.search(r"\bnext year\b", query_lower):
        return default_tax_year + 1

    # Check for explicit year references like "2025", "for 2024", "tax year 2023"
    # Use word boundaries to avoid matching form numbers like "1040"

    # Find ALL year mentions first
    all_year_matches = re.findall(r"\b([12]\d{3})\b", query)
    plausible_years = [int(y) for y in all_year_matches if 1950 <= int(y) <= 2050]

    if not plausible_years:
        return None

    if len(plausible_years) == 1:
        return plausible_years[0]

    # Multiple years: prefer the "action" year (the year the user is asking
    # about) over the "event" year (when something happened in the past).
    #
    # E.g. "financed a vehicle in 2024, can I claim the deduction in 2025?"
    #   → 2025 is the action year (claim/deduct), 2024 is the event year.
    #
    # Look for years near action verbs (claim, deduct, file, report, owe).
    ACTION_YEAR_PATTERN = re.compile(
        r"(?:claim|deduct(?:ion)?|file|report|owe|pay(?:ing)?|"
        r"tax(?:es)?|returns?)\b.*?\b([12]\d{3})\b",
        re.IGNORECASE,
    )
    action_match = ACTION_YEAR_PATTERN.search(query)
    if action_match:
        action_year = int(action_match.group(1))
        if 1950 <= action_year <= 2050:
            return action_year

    # Also check "tax year YYYY" pattern (highest confidence)
    tax_year_match = re.search(r"tax year\s+([12]\d{3})\b", query, re.IGNORECASE)
    if tax_year_match:
        return int(tax_year_match.group(1))

    # Fallback: prefer the LATER year — users typically ask about upcoming
    # or current tax implications, referencing past events as context.
    return max(plausible_years)


def _extract_comparison_years(query: str) -> list[int]:
    """
    Extract multiple tax years from cross-year comparison queries.

    Only returns years when the query contains explicit comparison language.
    A query that merely mentions two years (e.g. "financed in 2024, deduct
    in 2025") is NOT a comparison — it's a single-year question with temporal
    context.

    Detects patterns like:
    - "from 2023 to 2025"
    - "between 2023 and 2025"
    - "2023 vs 2024"
    - "changed from 2023 to 2025"
    - "2023 compared to 2025"
    - "difference between 2023 and 2025"
    - "how did X change from 2023 to 2024"

    Returns:
        Sorted list of distinct plausible years (1950-2050).
        Empty list if fewer than 2 distinct years or no comparison language.
    """
    query_lower = query.lower()

    # ── Require explicit comparison language ──────────────────────────
    # Without these indicators, multiple years in a query are typically
    # "event year" + "tax year", not a cross-year comparison.
    COMPARISON_INDICATORS = [
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\bcompare[ds]?\b",               # "compare", "compared to", "compares"
        r"\bcomparison\b",
        r"\bdifference\s+between\b",
        r"\bchanged?\s+(?:from|between|since)\b",
        r"\bbetween\s+\d{4}\s+and\s+\d{4}\b",
        r"\bfrom\s+\d{4}\s+to\s+\d{4}\b",
    ]

    has_comparison = any(
        re.search(pattern, query_lower) for pattern in COMPARISON_INDICATORS
    )
    if not has_comparison:
        return []

    # Find all 4-digit years in the query
    all_years = [int(m) for m in re.findall(r"\b([12]\d{3})\b", query)]
    # Filter to plausible tax years and deduplicate
    plausible = sorted(set(y for y in all_years if 1950 <= y <= 2050))
    return plausible if len(plausible) >= 2 else []


def _extract_forms(query: str) -> list[str]:
    """
    Extract form and schedule references from query.

    Matches patterns like:
    - "Form 1040", "Form 1040-SR", "Form 8889"
    - "Schedule C", "Schedule A", "Schedule D"

    Returns a normalized list like ["Form1040", "ScheduleC"]

    Args:
        query: The query string to analyze

    Returns:
        List of normalized form references
    """
    forms = []

    # Match "Form XXXX" or "Form XXXX-XX" patterns
    form_matches = re.finditer(
        r"Form\s+(\d{4}(?:-[A-Z]{1,2})?)",
        query,
        re.IGNORECASE
    )
    for match in form_matches:
        form_num = match.group(1).replace("-", "")
        forms.append(f"Form{form_num}")

    # Match "Schedule X" patterns
    schedule_matches = re.finditer(
        r"Schedule\s+([A-Z])",
        query,
        re.IGNORECASE
    )
    for match in schedule_matches:
        forms.append(f"Schedule{match.group(1)}")

    return list(set(forms))  # Remove duplicates


def _extract_publications(query: str) -> list[str]:
    """
    Extract publication references from query.

    Matches patterns like:
    - "Pub 596", "Publication 17", "Pub. 590-A"

    Normalizes to pub number only: "596", "17", "590a"

    Args:
        query: The query string to analyze

    Returns:
        List of normalized publication numbers
    """
    pubs = []

    # Match "Pub 596", "Publication 17", "Pub. 590-A", etc.
    pub_matches = re.finditer(
        r"(?:Pub(?:lication)?\.?\s+)?(\d{1,3}(?:[a-z])?)",
        query,
        re.IGNORECASE
    )
    for match in pub_matches:
        pub_num = match.group(1).lower()
        if pub_num.isdigit() or (len(pub_num) > 1 and pub_num[-1] in "ab"):
            pubs.append(pub_num)

    return list(set(pubs))  # Remove duplicates


def _extract_topics(query: str) -> list[str]:
    """
    Extract topic tags based on keyword matching.

    Uses the TOPIC_PATTERNS mapping to identify tax topics mentioned
    in the query. Matching is case-insensitive.

    Args:
        query: The query string to analyze

    Returns:
        List of matched topic tags (may include duplicates from overlapping patterns)
    """
    topics = []
    query_lower = query.lower()

    for topic, patterns in TOPIC_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                topics.append(topic)
                break  # Only add topic once even if multiple patterns match

    return list(set(topics))  # Remove duplicates


def _classify_intent(query: str) -> tuple[QueryIntent, float]:
    """
    Classify query intent based on linguistic patterns.

    Returns intent and confidence score (0-1).

    Classification rules:
    - FORM_LINE: Contains form/line references
    - RULE: Contains validation/error language
    - LOOKUP: Contains threshold/limit language
    - SCENARIO: Contains client scenario language
    - COMPARISON: Contains comparison language
    - GENERAL: Default fallback

    Args:
        query: The query string to analyze

    Returns:
        Tuple of (QueryIntent, confidence_score)
    """
    query_lower = query.lower()

    # FORM_LINE: "Schedule C line", "Form 1040 line", "where do I report", "which line"
    if re.search(
        r"(?:Schedule|Form|line|where|which)\s+(?:line|form|do i report|goes on|belongs)",
        query_lower
    ) or re.search(r"line\s+\d+", query_lower):
        return QueryIntent.FORM_LINE, 0.95

    # RULE: "what triggers", "when is ... required", "must attach", "rejection", "error code"
    if re.search(
        r"what triggers|when.*required|must attach|rejection|error code|F1040-",
        query_lower
    ):
        return QueryIntent.RULE, 0.90

    # COMPARISON: "vs", "versus", "compared to", "difference between", "standard or itemized"
    if re.search(
        r"\bvs\b|\bversus\b|compared to|difference between|standard or itemized",
        query_lower
    ):
        return QueryIntent.COMPARISON, 0.85

    # LOOKUP: "what is the", "how much", "what are the limits", "standard deduction", "contribution limit"
    if re.search(
        r"what is the|what\'s|how much|what are the|limits?|standard deduction|contribution limit|"
        r"phase-out|income limit|\$\d|threshold|what\'s required|is.*required",
        query_lower
    ):
        return QueryIntent.LOOKUP, 0.80

    # SCENARIO: "my client", "a taxpayer", "the client", conditional language ("if...then")
    if re.search(
        r"my client|a taxpayer|the client|if\s.*then|client\s+(?:sold|purchased|has|received)",
        query_lower
    ):
        return QueryIntent.SCENARIO, 0.85

    # GENERAL: default
    return QueryIntent.GENERAL, 0.50


def classify_query(query: str, default_tax_year: int = 2025) -> QueryMetadata:
    """
    Classify a CPA query and extract structured metadata.

    This is a pre-retrieval step that works alongside normalize_query().
    It extracts:
    - Intent classification (LOOKUP, SCENARIO, FORM_LINE, RULE, COMPARISON, GENERAL)
    - Tax year (if mentioned or inferred)
    - Form and schedule references
    - Publication references
    - Topic tags for publication routing

    Args:
        query: The raw CPA query string
        default_tax_year: Year to use for "this year" references (default: 2025)

    Returns:
        QueryMetadata object with extracted information

    Examples
    ────────
    >>> result = classify_query("What is the 2025 standard deduction?")
    >>> result.intent
    <QueryIntent.LOOKUP: 'lookup'>
    >>> result.tax_year
    2025
    >>> result.topic_tags
    ['standard-deduction', 'deductions']

    >>> result = classify_query("My client sold a rental property in 2024. What are the tax implications?")
    >>> result.intent
    <QueryIntent.SCENARIO: 'scenario'>
    >>> result.tax_year
    2024
    >>> result.topic_tags
    ['rental-property', 'capital-gains']
    """
    intent, confidence = _classify_intent(query)

    comparison_years = _extract_comparison_years(query)

    metadata = QueryMetadata(
        original_query=query,
        normalized_query="",  # Will be filled by caller if needed
        intent=intent,
        tax_year=_extract_tax_year(query, default_tax_year),
        comparison_years=comparison_years,
        form_refs=_extract_forms(query),
        pub_refs=_extract_publications(query),
        topic_tags=_extract_topics(query),
        confidence=confidence,
    )

    logger.debug(
        "classify_query: intent=%s (confidence=%.2f), tax_year=%s, topics=%s",
        intent.value,
        confidence,
        metadata.tax_year,
        metadata.topic_tags,
    )

    return metadata


def suggest_pub_filter(metadata: QueryMetadata) -> list[str] | None:
    """
    Suggest publication number filters based on query metadata.

    Uses the topic tags extracted from the query to find relevant publications
    via the publication registry's find_by_topic() method. If multiple topics
    are present, they are combined and deduplicated.

    Args:
        metadata: QueryMetadata object from classify_query()

    Returns:
        List of 1-3 pub numbers if confident topics are found, None otherwise.
        Returns None if we cannot confidently narrow the publication scope
        (e.g., very general query, no topic matches).

    Examples
    ────────
    >>> metadata = classify_query("What is the 2025 standard deduction?")
    >>> suggest_pub_filter(metadata)
    ['501', '17']  # Publications related to deductions

    >>> metadata = classify_query("General tax question")
    >>> suggest_pub_filter(metadata)
    None  # Too general, no specific publications
    """
    if not metadata.topic_tags:
        return None

    # If explicit pub refs were found, use those
    if metadata.pub_refs:
        return metadata.pub_refs

    # Only suggest a filter if we have reasonable confidence
    if metadata.confidence < 0.6:
        return None

    # Import here to avoid circular dependency
    try:
        from taxflow_kb.layer3.publication_registry import get_registry
    except ImportError:
        logger.warning("Cannot import publication_registry; skipping pub filter suggestion")
        return None

    registry = get_registry()
    pub_candidates = set()

    # For each topic tag, find matching publications
    for topic in metadata.topic_tags:
        matching_pubs = registry.find_by_topic(topic)
        for pub_meta in matching_pubs:
            pub_candidates.add(pub_meta.pub_number)

    if not pub_candidates:
        return None

    # Year-aware filtering: if the query specifies a tax year, only suggest
    # publications that are available for that year.  Pubs with empty
    # tax_years (fully discontinued) are always excluded.
    target_year = metadata.tax_year
    if target_year is not None:
        year_filtered = []
        for pn in pub_candidates:
            pub_meta = registry.get(pn)
            if pub_meta and pub_meta.tax_years and target_year in pub_meta.tax_years:
                year_filtered.append(pn)
        if year_filtered:
            pub_candidates = set(year_filtered)
        # If nothing matches the target year, fall back to unfiltered
        # (retrieval will still apply tax_year at the DB level)

    # Return top 1-3 pubs (sorted for consistency)
    sorted_pubs = sorted(pub_candidates, key=lambda x: int(x.rstrip("ab")))
    return sorted_pubs[:3] if len(sorted_pubs) > 3 else sorted_pubs or None


# ──────────────────────────────────────────────────────────────────────────────
# Testing and Examples
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Configure logging for test output
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    test_queries = [
        # LOOKUP queries
        "What is the 2025 standard deduction?",
        "How much can I contribute to my IRA in 2024?",
        "What are the income limits for the earned income credit?",

        # SCENARIO queries
        "My client sold a rental property in 2024. What are the tax implications?",
        "A taxpayer received a $50,000 inheritance. Is this taxable?",
        "The client has investment income from dividends and capital gains. How should they file?",

        # FORM_LINE queries
        "Where do I report rental income on the tax return?",
        "What goes on Schedule C line 31?",
        "Which line on Form 1040 reports mortgage interest?",

        # RULE queries
        "What triggers the need to file Form 8960?",
        "When is Form 5471 required for foreign corporations?",
        "What error codes might appear for estimated tax violations?",

        # COMPARISON queries
        "Should my client use standard or itemized deduction for 2025?",
        "What is the difference between a traditional and Roth IRA?",
        "Traditional vs Solo 401(k) - which is better?",

        # GENERAL queries
        "Tell me about tax planning.",
        "What is federal income tax?",
    ]

    print("=" * 80)
    print("QUERY CLASSIFIER TEST SUITE")
    print("=" * 80)

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Test {i}] {query}")
        print("-" * 80)

        metadata = classify_query(query)

        print(f"Intent:        {metadata.intent.value} (confidence: {metadata.confidence:.2f})")
        print(f"Tax Year:      {metadata.tax_year}")
        print(f"Forms:         {metadata.form_refs if metadata.form_refs else '(none)'}")
        print(f"Publications:  {metadata.pub_refs if metadata.pub_refs else '(none)'}")
        print(f"Topics:        {metadata.topic_tags if metadata.topic_tags else '(none)'}")

        pub_filter = suggest_pub_filter(metadata)
        print(f"Suggested Pubs: {pub_filter if pub_filter else '(none - too general)'}")

    print("\n" + "=" * 80)
    print("Tests completed")
    print("=" * 80)
