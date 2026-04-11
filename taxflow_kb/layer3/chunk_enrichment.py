"""
taxflow_kb/layer3/chunk_enrichment.py

Pre-embedding chunk text enrichment using a registry pattern.

Each publication can register a custom enrichment function that prepends
semantic context to chunks before embedding. Publications without a
registered enricher use a generic summary approach.

Problem: Pub 596 (EITC), 525 (Income), and other IRS publications contain
lookup tables and worksheets with dollar amounts, phaseout ranges, and Form
line references. The semantic gap between a natural-language question and a
raw table chunk is large — embeddings fail to match them because the surface
forms are so different.

Solution: Prepend a short natural-language summary line to worksheet / table
chunks so the embedding vector captures the semantic intent of the chunk.
The original text is preserved after the summary — only the embedding input
is changed (the stored `text` column is not modified).

Registry pattern replaces the previous if/elif branching, making it
extensible without modifying existing code (Open/Closed Principle).

Usage:
    from taxflow_kb.layer3.chunk_enrichment import enrich_for_embedding
    enriched_text = enrich_for_embedding(chunk, pub_number="596")
    # use enriched_text as the input to the embedding API
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Type for enrichment functions
EnricherFn = Callable[[str, Optional[dict]], str]
# signature: (text, metadata_dict_with_chapter_section_etc) -> enriched_text


class EnrichmentRegistry:
    """Registry of per-publication chunk enrichment functions."""

    _enrichers: dict[str, EnricherFn] = {}

    @classmethod
    def register(cls, pub_number: str) -> Callable[[EnricherFn], EnricherFn]:
        """Decorator to register an enrichment function for a publication."""
        def decorator(fn: EnricherFn) -> EnricherFn:
            cls._enrichers[pub_number] = fn
            return fn
        return decorator

    @classmethod
    def get(cls, pub_number: str) -> Optional[EnricherFn]:
        """Retrieve the enrichment function for a publication."""
        return cls._enrichers.get(pub_number)

    @classmethod
    def enrich(cls, text: str, pub_number: str, metadata: Optional[dict] = None) -> str:
        """
        Enrich chunk text for embedding. Falls back to generic enrichment.

        Args:
            text: The chunk text to enrich.
            pub_number: IRS publication number.
            metadata: Optional dict with chapter_title, section_title, page_start,
                     form_refs, line_refs, etc.

        Returns:
            Enriched text ready for embedding.
        """
        enricher = cls.get(pub_number)
        if enricher:
            return enricher(text, metadata)
        return _generic_enrichment(text, pub_number, metadata)


def enrich_for_embedding(chunk, pub_number: str) -> str:
    """
    Return the text to use as the embedding input for a chunk.

    Public API — backward compatible with the previous implementation.
    Delegates to the registry. Extracts metadata from chunk object
    for enrichment functions that need chapter/section context.

    Args:
        chunk      : PublicationChunk (must have .text attribute).
        pub_number : IRS publication number string (e.g. "596").

    Returns:
        String to pass to the embedding API.
    """
    text = chunk.text or ""
    metadata = {
        "chapter_title": getattr(chunk, "chapter_title", ""),
        "section_title": getattr(chunk, "section_title", ""),
        "page_start": getattr(chunk, "page_start", 0),
        "form_refs": getattr(chunk, "form_refs", []),
        "line_refs": getattr(chunk, "line_refs", []),
    }
    return EnrichmentRegistry.enrich(text, pub_number, metadata)


# ── Pub 596 — Earned Income Credit ────────────────────────────────────────────

# Patterns that identify worksheet/table chunks in Pub 596
_596_WORKSHEET_SIGNALS = [
    r"Worksheet\s+\d",
    r"Step\s+\d",
    r"earned income limit",
    r"investment income",
    r"phaseout",
    r"AGI limit",
    r"\$[\d,]+\s+\$[\d,]+",          # dollar table cells
    r"Form\s+1040.*line\s+\d+",
    r"Schedule\s+[A-Z].*line\s+\d+",
    r"qualifying child(?:ren)?",
    r"no qualifying child",
    r"three or more",
    r"married filing jointly",
    r"single.*head of household",
]
_596_WS_RE = re.compile(
    "|".join(_596_WORKSHEET_SIGNALS), re.IGNORECASE
)

_596_INCOME_TABLE_RE = re.compile(
    r"\$\s*[\d,]{4,}",   # at least one 4-digit dollar figure
    re.IGNORECASE,
)


@EnrichmentRegistry.register("596")
def _enrich_596(text: str, metadata: Optional[dict] = None) -> str:
    """
    Prepend a semantic summary to Pub 596 worksheet/table chunks.

    Detects chunks that contain EIC income tables, phaseout thresholds, or
    worksheet steps and prepends a plain-English descriptor so the embedding
    space aligns with natural-language CPA queries.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict (unused in this enricher).

    Returns:
        Enriched text with summary prepended, or original text if no patterns match.
    """
    if not _596_WS_RE.search(text):
        return text

    # Build a contextual summary from signals found in the text
    parts: list[str] = ["[EIC Reference]"]

    if re.search(r"Worksheet", text, re.I):
        ws_match = re.search(r"Worksheet\s+(\d+[A-Z]?)", text, re.I)
        label = ws_match.group(0) if ws_match else "Worksheet"
        parts.append(f"Earned income credit {label} — step-by-step calculation.")

    if re.search(r"phaseout|phase-out", text, re.I):
        parts.append(
            "Contains EIC phaseout thresholds and income ranges for phase-out computation."
        )

    if re.search(r"investment income", text, re.I):
        parts.append("Investment income limit for earned income credit eligibility.")

    if re.search(r"AGI limit|adjusted gross income limit", text, re.I):
        parts.append("AGI and earned income limits for EIC qualification.")

    dollar_matches = _596_INCOME_TABLE_RE.findall(text)
    if len(dollar_matches) >= 3:
        parts.append(
            "Income table with earned income credit dollar thresholds by filing status "
            "and number of qualifying children."
        )

    if re.search(r"married filing jointly", text, re.I):
        parts.append("Includes married filing jointly (MFJ) limits.")

    if re.search(r"no qualifying child", text, re.I):
        parts.append("Includes limits for taxpayers with no qualifying children.")

    if re.search(r"three or more|3 or more", text, re.I):
        parts.append("Includes limits for three or more qualifying children.")

    summary = " ".join(parts)
    return f"{summary}\n\n{text}"


# ── Pub 525 — Taxable and Nontaxable Income ───────────────────────────────────

# Topic keywords that help identify the subject of a Pub 525 chunk
_525_TOPIC_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"incentive stock option|ISO|qualifying disposition", re.I),
     "Incentive stock options (ISO), qualifying and disqualifying dispositions, "
     "AMT treatment, holding period requirements."),
    (re.compile(r"nonqualified|non-qualified|NQSO|nonstatutory", re.I),
     "Nonqualified stock options (NQSO), ordinary income recognition, W-2 reporting."),
    (re.compile(r"unemployment compensation|unemployment benefit", re.I),
     "Unemployment compensation, taxability, repayment rules, Form 1099-G."),
    (re.compile(r"fringe benefit|de minimis|working condition", re.I),
     "Employee fringe benefits, de minimis exclusions, working condition fringe benefits."),
    (re.compile(r"alimony|divorce|separation instrument", re.I),
     "Alimony and separate maintenance payments, TCJA post-2018 rules, taxability by agreement date."),
    (re.compile(r"differential wage|military", re.I),
     "Differential wage payments to military reservists, employer reporting requirements."),
    (re.compile(r"life insurance|employer.*life|group-term", re.I),
     "Group-term life insurance, employer-provided life insurance income inclusion."),
    (re.compile(r"accident.*health|disability.*income|sick pay", re.I),
     "Accident and health benefits, disability income, sick pay taxability."),
    (re.compile(r"scholarship|fellowship|educational", re.I),
     "Scholarships, fellowships, educational assistance taxability exclusions."),
    (re.compile(r"cancellation.*debt|forgiveness.*debt|COD", re.I),
     "Cancellation of debt income, Form 1099-C, insolvency exclusion."),
    (re.compile(r"gambling|lottery|prize|award", re.I),
     "Gambling winnings, lottery prizes, awards, Form W-2G reporting."),
    (re.compile(r"social security|SSA|SSDI|railroad retirement", re.I),
     "Social Security benefits taxability, lump-sum elections, railroad retirement."),
    (re.compile(r"rental income|royalt", re.I),
     "Rental income, royalties, passive activity rules."),
    (re.compile(r"bartering|barter", re.I),
     "Bartering income, fair market value, Form 1099-B reporting."),
]


@EnrichmentRegistry.register("525")
def _enrich_525(text: str, metadata: Optional[dict] = None) -> str:
    """
    Prepend a topic label to Pub 525 chunks so semantically similar questions
    land on the right chunk even across diverse income categories.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict (unused in this enricher).

    Returns:
        Enriched text with topic prepended, or original text if no topics match.
    """
    matched_topics: list[str] = []
    for pattern, description in _525_TOPIC_MAP:
        if pattern.search(text):
            matched_topics.append(description)

    if not matched_topics:
        return text

    topic_line = " | ".join(matched_topics)
    return f"[Pub 525 — Taxable Income] Topic: {topic_line}\n\n{text}"


# ── Pub 969 — Health Savings Accounts ────────────────────────────────────────

# Patterns that identify HSA limit tables and contribution rules in Pub 969
_969_SIGNALS = [
    r"HDHP|high.*deductible",
    r"HSA.*limit|contribution.*limit",
    r"catch-up|catch up contribution",
    r"\$\d+,\d+\s*(?:per|for)",      # dollar amounts with per/for context
    r"family coverage|individual coverage|self-only",
    r"minimum deductible|maximum out-of-pocket",
    r"eligible expense|qualified medical",
]
_969_RE = re.compile("|".join(_969_SIGNALS), re.IGNORECASE)


@EnrichmentRegistry.register("969")
def _enrich_969(text: str, metadata: Optional[dict] = None) -> str:
    """
    Enrich Pub 969 (HSA) chunks with threshold context.

    Detects HDHP limit tables, contribution limits, catch-up amounts,
    and coverage level distinctions to help embeddings match HSA-related queries.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict with chapter/section context.

    Returns:
        Enriched text with HSA context prepended, or original text if no signals found.
    """
    if not _969_RE.search(text):
        return text

    parts: list[str] = ["[HSA Reference]"]

    if re.search(r"contribution.*limit|limit.*contribution", text, re.I):
        parts.append("HSA annual contribution limits by coverage level (self-only, family).")

    if re.search(r"catch-up|catch up contribution", text, re.I):
        parts.append("HSA catch-up contributions for individuals age 55 and older.")

    if re.search(r"HDHP|high.*deductible", text, re.I):
        parts.append("High-deductible health plan (HDHP) eligibility and requirements.")

    if re.search(r"minimum deductible|maximum out-of-pocket", text, re.I):
        parts.append("HDHP minimum deductible and maximum out-of-pocket limits.")

    if re.search(r"eligible expense|qualified medical", text, re.I):
        parts.append("Qualified medical expenses eligible for HSA distributions.")

    if re.search(r"family coverage|self-only|individual coverage", text, re.I):
        parts.append("Coverage level distinctions: self-only vs. family coverage.")

    if len(parts) > 1:
        summary = " ".join(parts)
        return f"{summary}\n\n{text}"
    return text


# ── Pub 590-B — Distributions from IRAs ──────────────────────────────────────

# Patterns that identify RMD tables and distribution rules in Pub 590-B
_590b_SIGNALS = [
    r"RMD|required minimum distribution",
    r"distribution.*table|table.*distribution|life expectancy",
    r"age\s+7[0-9]|over\s+70|age\s+72",
    r"IRA withdrawal|IRA distribution",
    r"uniform lifetime table|single life expectancy",
    r"beneficiary|inherited IRA",
]
_590b_RE = re.compile("|".join(_590b_SIGNALS), re.IGNORECASE)


@EnrichmentRegistry.register("590b")
def _enrich_590b(text: str, metadata: Optional[dict] = None) -> str:
    """
    Enrich Pub 590-B (IRA Distributions) chunks with RMD/table context.

    Detects life expectancy tables, RMD worksheets, distribution rules,
    and beneficiary rules to align embeddings with distribution planning queries.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict with chapter/section context.

    Returns:
        Enriched text with RMD/distribution context prepended, or original text if no signals.
    """
    if not _590b_RE.search(text):
        return text

    parts: list[str] = ["[IRA Distributions Reference]"]

    if re.search(r"RMD|required minimum distribution", text, re.I):
        parts.append("Required minimum distribution (RMD) rules, calculations, and timing.")

    if re.search(r"distribution.*table|table.*distribution|life expectancy|uniform lifetime", text, re.I):
        parts.append("Life expectancy tables and uniform lifetime table for RMD calculations.")

    if re.search(r"age\s+7[0-9]|over\s+70|age\s+72", text, re.I):
        parts.append("Age thresholds for RMD commencement (age 72 under current law).")

    if re.search(r"beneficiary|inherited IRA", text, re.I):
        parts.append("Beneficiary distribution rules and inherited IRA requirements.")

    if re.search(r"IRA withdrawal|IRA distribution|distribution options", text, re.I):
        parts.append("IRA withdrawal and distribution options for account owners.")

    if len(parts) > 1:
        summary = " ".join(parts)
        return f"{summary}\n\n{text}"
    return text


# ── Pub 550 — Investment Income and Expenses ─────────────────────────────────

# Patterns that identify investment terminology and thresholds in Pub 550
_550_SIGNALS = [
    r"wash sale|wash-sale",
    r"holding period|holding.*period",
    r"capital gain|capital loss|long-term|short-term",
    r"dividend|distribution|interest income",
    r"bond|stock|mutual fund|investment",
    r"basis|cost basis|adjusted basis",
]
_550_RE = re.compile("|".join(_550_SIGNALS), re.IGNORECASE)


@EnrichmentRegistry.register("550")
def _enrich_550(text: str, metadata: Optional[dict] = None) -> str:
    """
    Enrich Pub 550 (Investment Income) chunks with investment terminology context.

    Detects wash sale rules, holding period distinctions, capital gain rate tables,
    and investment income rules to help embeddings match investment tax queries.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict with chapter/section context.

    Returns:
        Enriched text with investment context prepended, or original text if no signals.
    """
    if not _550_RE.search(text):
        return text

    parts: list[str] = ["[Investment Income Reference]"]

    if re.search(r"wash sale|wash-sale", text, re.I):
        parts.append("Wash sale rule, disallowed loss deferral, and identification requirements.")

    if re.search(r"holding period|holding.*period", text, re.I):
        parts.append("Holding period rules for long-term vs. short-term capital gains classification.")

    if re.search(r"capital gain|capital loss|long-term|short-term", text, re.I):
        parts.append("Capital gain and loss treatment, net capital loss limitations, and tax rates.")

    if re.search(r"dividend|distribution", text, re.I):
        parts.append("Qualified dividend income, dividend distributions, and dividend tax rates.")

    if re.search(r"interest income|bond", text, re.I):
        parts.append("Interest income taxation, original issue discount, and bond rules.")

    if re.search(r"basis|cost basis|adjusted basis", text, re.I):
        parts.append("Cost basis calculations, basis adjustments, and average cost method.")

    if len(parts) > 1:
        summary = " ".join(parts)
        return f"{summary}\n\n{text}"
    return text


# ── Pub 17 — Your Federal Income Tax ─────────────────────────────────────────

# Patterns that identify tax rate tables and filing requirements in Pub 17
_17_SIGNALS = [
    r"tax rate|tax bracket|tax schedule",
    r"standard deduction|itemized deduction",
    r"filing requirement|filing status",
    r"personal exemption|dependent|qualifying",
    r"Form\s+1040|Schedule",
    r"Single|Married.*Filing.*Jointly|Head.*Household",
]
_17_RE = re.compile("|".join(_17_SIGNALS), re.IGNORECASE)


@EnrichmentRegistry.register("17")
def _enrich_17(text: str, metadata: Optional[dict] = None) -> str:
    """
    Enrich Pub 17 (Your Federal Income Tax) chunks with tax-specific context.

    Detects tax rate schedule tables, standard deduction amounts, filing requirement
    thresholds, and filing status rules to align embeddings with basic tax queries.

    Args:
        text: The chunk text to enrich.
        metadata: Optional dict with chapter/section context.

    Returns:
        Enriched text with tax context prepended, or original text if no signals.
    """
    if not _17_RE.search(text):
        return text

    parts: list[str] = ["[Federal Income Tax Reference]"]

    if re.search(r"tax rate|tax bracket|tax schedule", text, re.I):
        parts.append("Federal income tax rates, tax brackets, and tax rate schedules by filing status.")

    if re.search(r"standard deduction|itemized deduction", text, re.I):
        parts.append("Standard deduction amounts and itemized deduction rules.")

    if re.search(r"filing requirement|filing threshold|must file", text, re.I):
        parts.append("Filing requirement thresholds and who must file income tax returns.")

    if re.search(r"filing status|Single|Married.*Filing|Head.*Household", text, re.I):
        parts.append("Filing status categories and tax treatment by filing status.")

    if re.search(r"personal exemption|dependent|qualifying.*dependent", text, re.I):
        parts.append("Dependent qualifications and related tax benefits (dependent credits, etc.).")

    if re.search(r"Form\s+1040|Schedule\s+[A-Z]", text, re.I):
        parts.append("Form 1040 line references and related schedule instructions.")

    if len(parts) > 1:
        summary = " ".join(parts)
        return f"{summary}\n\n{text}"
    return text


# ── Pub 334 — Tax Guide for Small Business ────────────────────────────────────

_334_SIGNALS = [
    r"self-employment tax", r"schedule\s+c", r"schedule\s+se",
    r"estimated tax", r"sole proprietor", r"net profit",
    r"business income", r"business expense", r"record\s*keeping",
    r"\$[\d,]{4,}", r"quarterly", r"1099-NEC", r"independent contractor",
]
_334_RE = re.compile("|".join(_334_SIGNALS), re.I)


@EnrichmentRegistry.register("334")
def _enrich_334(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 334 (Small Business Tax Guide) chunks."""
    if not _334_RE.search(text):
        return text
    parts: list[str] = ["[Small Business Tax Reference]"]
    if re.search(r"self-employment tax|schedule\s+se|15\.3%", text, re.I):
        parts.append("Self-employment tax calculation and Schedule SE.")
    if re.search(r"estimated tax|quarterly|1040-ES", text, re.I):
        parts.append("Quarterly estimated tax payments for self-employed.")
    if re.search(r"schedule\s+c|net profit|business income", text, re.I):
        parts.append("Schedule C business income and profit calculation.")
    if re.search(r"record\s*keeping|receipt|documentation", text, re.I):
        parts.append("Business record-keeping requirements and documentation.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 505 — Tax Withholding and Estimated Tax ──────────────────────────────

_505_SIGNALS = [
    r"withholding", r"estimated tax", r"form\s+w-4",
    r"form\s+1040-ES", r"safe harbor", r"underpayment penalty",
    r"quarterly.*payment", r"annualized income",
]
_505_RE = re.compile("|".join(_505_SIGNALS), re.I)


@EnrichmentRegistry.register("505")
def _enrich_505(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 505 (Tax Withholding and Estimated Tax) chunks."""
    if not _505_RE.search(text):
        return text
    parts: list[str] = ["[Withholding & Estimated Tax Reference]"]
    if re.search(r"form\s+w-4|withholding allowance|withholding rate", text, re.I):
        parts.append("W-4 withholding configuration and rates.")
    if re.search(r"estimated tax.*payment|1040-ES|quarterly", text, re.I):
        parts.append("Quarterly estimated tax payment rules and deadlines.")
    if re.search(r"safe harbor|underpayment|penalty", text, re.I):
        parts.append("Safe harbor rules and underpayment penalties.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 527 — Residential Rental Property ─────────────────────────────────────

_527_SIGNALS = [
    r"rental income", r"rental expense", r"rental property",
    r"schedule\s+e", r"depreciation", r"passive.*(?:activity|loss)",
    r"fair rental", r"personal use", r"real estate professional",
    r"\$[\d,]{4,}", r"MACRS", r"27\.5.year",
]
_527_RE = re.compile("|".join(_527_SIGNALS), re.I)


@EnrichmentRegistry.register("527")
def _enrich_527(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 527 (Residential Rental Property) chunks."""
    if not _527_RE.search(text):
        return text
    parts: list[str] = ["[Rental Property Reference]"]
    if re.search(r"rental income|gross rental|fair rental", text, re.I):
        parts.append("Rental income reporting and fair rental value.")
    if re.search(r"rental expense|deductible.*expense|operating expense", text, re.I):
        parts.append("Deductible rental property expenses.")
    if re.search(r"depreciation|MACRS|27\.5|recovery period", text, re.I):
        parts.append("Rental property depreciation under MACRS (27.5-year).")
    if re.search(r"passive.*(?:activity|loss)|real estate professional", text, re.I):
        parts.append("Passive activity loss limitations for rental property.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 544 — Sales of Assets ─────────────────────────────────────────────────

_544_SIGNALS = [
    r"capital gain", r"capital loss", r"holding period",
    r"short-term", r"long-term", r"section 1231",
    r"section 1245", r"section 1250", r"recapture",
    r"adjusted basis", r"net capital", r"wash sale",
    r"like-kind exchange", r"installment sale",
]
_544_RE = re.compile("|".join(_544_SIGNALS), re.I)


@EnrichmentRegistry.register("544")
def _enrich_544(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 544 (Sales of Assets) chunks."""
    if not _544_RE.search(text):
        return text
    parts: list[str] = ["[Capital Gains & Asset Sales Reference]"]
    if re.search(r"holding period|short-term|long-term", text, re.I):
        parts.append("Holding period rules for short-term vs long-term gains.")
    if re.search(r"section 1231|business property", text, re.I):
        parts.append("Section 1231 gains and losses from business property.")
    if re.search(r"section 124[05]|recapture|depreciation recapture", text, re.I):
        parts.append("Depreciation recapture rules (Sections 1245/1250).")
    if re.search(r"wash sale|substantially identical", text, re.I):
        parts.append("Wash sale rule for securities losses.")
    if re.search(r"like-kind|section 1031|exchange", text, re.I):
        parts.append("Like-kind exchange (Section 1031) rules.")
    if re.search(r"installment sale|installment method", text, re.I):
        parts.append("Installment sale method for reporting gains.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 946 — How to Depreciate Property ──────────────────────────────────────

_946_SIGNALS = [
    r"depreciation", r"MACRS", r"section 179",
    r"bonus depreciation", r"recovery period", r"depreciable",
    r"convention", r"straight.line", r"declining balance",
    r"form\s+4562", r"listed property", r"class life",
]
_946_RE = re.compile("|".join(_946_SIGNALS), re.I)


@EnrichmentRegistry.register("946")
def _enrich_946(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 946 (How to Depreciate Property) chunks."""
    if not _946_RE.search(text):
        return text
    parts: list[str] = ["[Depreciation Reference]"]
    if re.search(r"MACRS|recovery period|class life", text, re.I):
        parts.append("MACRS depreciation system, recovery periods, and class lives.")
    if re.search(r"section 179|expensing|immediate deduction", text, re.I):
        parts.append("Section 179 expensing election and dollar limits.")
    if re.search(r"bonus depreciation|100%|first.year", text, re.I):
        parts.append("Bonus depreciation (first-year) rules and phase-down.")
    if re.search(r"convention|half.year|mid.month|mid.quarter", text, re.I):
        parts.append("Depreciation conventions (half-year, mid-month, mid-quarter).")
    if re.search(r"listed property|automobile|vehicle", text, re.I):
        parts.append("Listed property and vehicle depreciation limits.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 463 — Travel, Entertainment, Gift, and Car Expenses ──────────────────

_463_SIGNALS = [
    r"travel expense", r"transportation", r"business travel",
    r"per diem", r"standard mileage", r"actual expense",
    r"entertainment", r"business meal", r"gift",
    r"form\s+2106", r"\$[\d,]{2,}", r"50%.*meal",
    r"accountable plan", r"temporary.*assignment",
]
_463_RE = re.compile("|".join(_463_SIGNALS), re.I)


@EnrichmentRegistry.register("463")
def _enrich_463(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 463 (Travel, Entertainment, Gift, and Car Expenses) chunks."""
    if not _463_RE.search(text):
        return text
    parts: list[str] = ["[Travel & Business Expense Reference]"]
    if re.search(r"standard mileage|mileage rate|cents per mile", text, re.I):
        parts.append("Standard mileage rate for business vehicle use.")
    if re.search(r"per diem|daily.*allowance|federal rate", text, re.I):
        parts.append("Per diem rates and daily travel allowances.")
    if re.search(r"travel expense|business travel|away from home", text, re.I):
        parts.append("Business travel expense rules and deductibility.")
    if re.search(r"meal|50%.*deduct|entertainment", text, re.I):
        parts.append("Meal and entertainment expense limitations.")
    if re.search(r"gift|business gift|\$25", text, re.I):
        parts.append("Business gift deduction rules and limits.")
    if re.search(r"accountable plan|reimbursement|substantiation", text, re.I):
        parts.append("Accountable plan and expense substantiation requirements.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 502 — Medical and Dental Expenses ────────────────────────────────────

_502_SIGNALS = [
    r"medical expense", r"dental expense", r"health insurance",
    r"schedule\s+a", r"itemized deduction", r"7\.5%",
    r"prescription", r"health care", r"long-term care",
    r"medical savings", r"\$[\d,]{2,}",
    r"AGI|adjusted gross income",
]
_502_RE = re.compile("|".join(_502_SIGNALS), re.I)


@EnrichmentRegistry.register("502")
def _enrich_502(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 502 (Medical and Dental Expenses) chunks."""
    if not _502_RE.search(text):
        return text
    parts: list[str] = ["[Medical & Dental Expense Reference]"]
    if re.search(r"7\.5%|AGI.*threshold|adjusted gross income", text, re.I):
        parts.append("Medical expense AGI threshold (7.5%) for deductibility.")
    if re.search(r"health insurance|premium|marketplace", text, re.I):
        parts.append("Health insurance premium deductibility rules.")
    if re.search(r"prescription|medicine|drug", text, re.I):
        parts.append("Deductible prescription and medication expenses.")
    if re.search(r"long-term care|nursing|assisted living", text, re.I):
        parts.append("Long-term care and nursing expense deductions.")
    if re.search(r"dental|orthodontic|vision|eyeglasses", text, re.I):
        parts.append("Dental, vision, and orthodontic expense rules.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 503 — Child and Dependent Care Expenses ─────────────────────────────

_503_SIGNALS = [
    r"child care", r"dependent care", r"day care",
    r"form\s+2441", r"credit.*care", r"care provider",
    r"earned income", r"qualifying person", r"household",
    r"\$[\d,]{3,}", r"employer.*benefit", r"cafeteria plan",
]
_503_RE = re.compile("|".join(_503_SIGNALS), re.I)


@EnrichmentRegistry.register("503")
def _enrich_503(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 503 (Child and Dependent Care Expenses) chunks."""
    if not _503_RE.search(text):
        return text
    parts: list[str] = ["[Child & Dependent Care Reference]"]
    if re.search(r"credit.*care|child.*tax credit|form\s+2441", text, re.I):
        parts.append("Child and dependent care credit calculation (Form 2441).")
    if re.search(r"qualifying person|qualifying child|dependent", text, re.I):
        parts.append("Qualifying person rules for child/dependent care credit.")
    if re.search(r"care provider|day care|babysitter|nanny", text, re.I):
        parts.append("Care provider identification and expense documentation.")
    if re.search(r"employer.*benefit|dependent care.*benefit|cafeteria", text, re.I):
        parts.append("Employer-provided dependent care benefits and exclusion.")
    if re.search(r"earned income|work.*related|employment", text, re.I):
        parts.append("Earned income requirement for care expense eligibility.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Pub 504 — Divorced or Separated Individuals ─────────────────────────────

_504_SIGNALS = [
    r"divorce", r"separated", r"alimony", r"child support",
    r"filing status", r"head of household", r"exemption",
    r"property settlement", r"community property",
    r"form\s+8332", r"qualifying child", r"custodial parent",
]
_504_RE = re.compile("|".join(_504_SIGNALS), re.I)


@EnrichmentRegistry.register("504")
def _enrich_504(text: str, metadata: Optional[dict] = None) -> str:
    """Enrich Pub 504 (Divorced or Separated Individuals) chunks."""
    if not _504_RE.search(text):
        return text
    parts: list[str] = ["[Divorce & Separation Tax Reference]"]
    if re.search(r"alimony|spousal support|maintenance", text, re.I):
        parts.append("Alimony and spousal support tax treatment.")
    if re.search(r"child support|custody|custodial parent", text, re.I):
        parts.append("Child support and custody-related tax rules.")
    if re.search(r"filing status|head of household|married filing", text, re.I):
        parts.append("Filing status determination for divorced/separated individuals.")
    if re.search(r"property.*(?:settlement|transfer|division)|community property", text, re.I):
        parts.append("Property settlement and transfer rules in divorce.")
    if re.search(r"form\s+8332|exemption|release.*claim", text, re.I):
        parts.append("Form 8332 release of exemption claim for dependents.")
    if len(parts) > 1:
        return " ".join(parts) + "\n\n" + text
    return text


# ── Generic Enrichment Fallback ──────────────────────────────────────────────

def _generic_enrichment(text: str, pub_number: str, metadata: Optional[dict] = None) -> str:
    """
    Generic enrichment for publications without a specific enricher.

    Prepends chapter/section context from metadata to help the embedding
    model associate the chunk with its structural position in the publication.

    Args:
        text: The chunk text to enrich.
        pub_number: IRS publication number.
        metadata: Optional dict with chapter_title, section_title, form_refs, etc.

    Returns:
        Enriched text with publication context prepended, or original text if no metadata.
    """
    parts: list[str] = []
    if metadata:
        chapter = metadata.get("chapter_title", "")
        section = metadata.get("section_title", "")
        if chapter:
            parts.append(f"[IRS Pub {pub_number}] {chapter}")
        if section:
            parts.append(section)
        forms = metadata.get("form_refs", [])
        if forms:
            parts.append(f"Related forms: {', '.join(forms)}")

    if parts:
        header = " | ".join(parts)
        return f"{header}\n\n{text}"
    return text
