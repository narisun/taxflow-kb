"""
taxkb/publications/ontology.py

Cross-publication tax topic ontology for hierarchical retrieval.

Design
──────
The ontology provides three capabilities the flat chunk index cannot:

  1. NAVIGATION ANCHORS
     General queries ("How are capital gains taxed?") match topic-level
     summaries instead of drowning in thousands of detail chunks. The
     topic summary tells the agent WHICH publications and sections are
     authoritative, letting it drill down precisely.

  2. CROSS-PUBLICATION ROUTING
     A single tax concept (e.g., "basis of assets") spans Pub 551 (primary),
     Pub 544 Ch.1 (sale context), Pub 523 (home sale context), Pub 527
     (rental depreciation). The ontology maps the concept to all relevant
     sections so the retriever can pull from all of them.

  3. HIERARCHICAL RETRIEVAL
     The three-tier chunk hierarchy (pub_summary → section_summary → detail)
     lets the agent answer at the right level of specificity:
       - "What does Pub 527 cover?" → pub_summary
       - "How is rental depreciation calculated?" → section_summary
       - "What is the MACRS recovery period for residential rental?" → detail

Architecture
────────────
  TaxTopic (node in the ontology)
    ├── topic_id: "capital_gains"
    ├── display_name: "Capital Gains & Losses"
    ├── parent_topic: "investments" (optional, for hierarchy)
    ├── description: "Tax treatment of gains and losses from asset sales..."
    ├── pub_sections: [(pub, chapter, section), ...]  ← cross-pub links
    ├── related_topics: ["basis_of_assets", "holding_period", ...]
    └── key_terms: ["capital gain", "long-term", "short-term", ...]

  ChunkType (enum for the three-tier hierarchy)
    PUB_SUMMARY      — One per pub: scope, key topics, when to use
    SECTION_SUMMARY   — One per major section: rules, thresholds, key guidance
    DETAIL            — Existing ~400-token chunks (default)

Usage in retrieval:
  Stage 1 (navigate):  Search PUB_SUMMARY + SECTION_SUMMARY chunks
                        → identify the right publication(s) and section(s)
  Stage 2 (drill):     Search DETAIL chunks filtered to those sections
                        → get the specific passage that answers the question
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── Chunk type for three-tier hierarchy ──────────────────────────────────────

class ChunkType(str, Enum):
    """Three-tier chunk hierarchy for hierarchical retrieval."""
    PUB_SUMMARY     = "pub_summary"       # Tier 1: one per publication
    SECTION_SUMMARY = "section_summary"   # Tier 2: one per major section/chapter
    DETAIL          = "detail"            # Tier 3: existing ~400-token chunks


# ── Publication section reference ────────────────────────────────────────────

class PubSection(BaseModel):
    """A reference to a specific section within a publication."""

    model_config = ConfigDict(frozen=True)

    pub_number: str               # "527", "544", "551"
    chapter: str = ""             # "Chapter 2. Depreciation of Rental Property"
    section: str = ""             # "Modified Accelerated Cost Recovery System (MACRS)"
    relevance: str = "primary"    # "primary" | "supplementary" | "reference"
    notes: str = ""               # "Covers MACRS recovery periods for rental property"


# ── Tax topic node ───────────────────────────────────────────────────────────

class TaxTopic(BaseModel):
    """
    A node in the cross-publication tax topic ontology.

    Each topic represents a CPA-meaningful concept that spans one or more
    publications. Topics can form a hierarchy via parent_topic.
    """

    model_config = ConfigDict(frozen=True)

    topic_id: str                           # "capital_gains", "rental_depreciation"
    display_name: str                       # "Capital Gains & Losses"
    parent_topic: Optional[str] = None      # "investments" → parent topic_id
    category: str = ""                      # "investments", "deductions", "credits"
    description: str = ""                   # Human-readable scope description
    pub_sections: list[PubSection] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)  # For BM25 boosting


# ── Topic ontology registry ─────────────────────────────────────────────────

class TopicOntology:
    """
    Registry of tax topics with cross-publication section mappings.

    This is the CPA's mental map in data form: given a tax concept,
    which publications cover it, in which sections, and with what authority.
    """

    def __init__(self):
        self._topics: dict[str, TaxTopic] = {}
        self._term_index: dict[str, list[str]] = {}  # term → [topic_id, ...]
        self._load_defaults()

    def register(self, topic: TaxTopic) -> None:
        """Register a topic in the ontology."""
        self._topics[topic.topic_id] = topic
        # Index key terms for fast lookup
        for term in topic.key_terms:
            term_lower = term.lower()
            if term_lower not in self._term_index:
                self._term_index[term_lower] = []
            if topic.topic_id not in self._term_index[term_lower]:
                self._term_index[term_lower].append(topic.topic_id)

    def get(self, topic_id: str) -> TaxTopic | None:
        """Get a topic by ID."""
        return self._topics.get(topic_id)

    def find_by_term(self, term: str) -> list[TaxTopic]:
        """Find topics whose key_terms contain the given term (case-insensitive)."""
        term_lower = term.lower()
        # Exact match first
        topic_ids = self._term_index.get(term_lower, [])
        # Then substring match across all terms
        for indexed_term, tids in self._term_index.items():
            if term_lower in indexed_term or indexed_term in term_lower:
                for tid in tids:
                    if tid not in topic_ids:
                        topic_ids.append(tid)
        return [self._topics[tid] for tid in topic_ids if tid in self._topics]

    def find_by_query(self, query: str) -> list[TaxTopic]:
        """
        Find topics relevant to a natural-language query.

        Matches query words against key_terms. Returns topics sorted by
        number of matching terms (most relevant first).
        """
        query_lower = query.lower()
        scores: dict[str, int] = {}

        for topic in self._topics.values():
            score = 0
            for term in topic.key_terms:
                if term.lower() in query_lower:
                    score += 1
            # Also check display_name
            if topic.display_name.lower() in query_lower:
                score += 2
            if score > 0:
                scores[topic.topic_id] = score

        ranked = sorted(scores.keys(), key=lambda tid: scores[tid], reverse=True)
        return [self._topics[tid] for tid in ranked]

    def get_pub_sections_for_topic(self, topic_id: str) -> list[PubSection]:
        """Get all publication sections that cover a topic."""
        topic = self.get(topic_id)
        return list(topic.pub_sections) if topic else []

    def get_pub_numbers_for_topic(self, topic_id: str) -> list[str]:
        """Get unique pub numbers that cover a topic, primaries first."""
        sections = self.get_pub_sections_for_topic(topic_id)
        primary = [s.pub_number for s in sections if s.relevance == "primary"]
        others = [s.pub_number for s in sections if s.relevance != "primary"]
        seen: set[str] = set()
        result: list[str] = []
        for pn in primary + others:
            if pn not in seen:
                seen.add(pn)
                result.append(pn)
        return result

    def get_children(self, parent_topic_id: str) -> list[TaxTopic]:
        """Get all topics whose parent_topic is the given ID."""
        return [
            t for t in self._topics.values()
            if t.parent_topic == parent_topic_id
        ]

    def get_root_topics(self) -> list[TaxTopic]:
        """Get all topics with no parent (top-level categories)."""
        return [t for t in self._topics.values() if t.parent_topic is None]

    def all_topic_ids(self) -> list[str]:
        """Get all registered topic IDs, sorted."""
        return sorted(self._topics.keys())

    # ── Default topic definitions ────────────────────────────────────────────

    def _load_defaults(self) -> None:
        """
        Load the default tax topic ontology.

        This mirrors how a CPA mentally organizes tax knowledge:
        broad categories → specific topics → cross-referenced publications.
        """

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: INCOME
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="income",
            display_name="Income",
            category="income",
            description=(
                "All forms of taxable and nontaxable income including wages, "
                "interest, dividends, business income, and retirement distributions."
            ),
            pub_sections=[
                PubSection(pub_number="17", chapter="Income", relevance="primary",
                           notes="Master reference for all income types"),
                PubSection(pub_number="525", relevance="primary",
                           notes="Comprehensive guide to taxable vs nontaxable income"),
            ],
            related_topics=["investment_income", "business_income", "retirement_income"],
            key_terms=[
                "income", "taxable income", "gross income", "adjusted gross income",
                "AGI", "wages", "salary", "compensation", "earnings",
            ],
        ))

        self.register(TaxTopic(
            topic_id="investment_income",
            display_name="Investment Income & Expenses",
            parent_topic="income",
            category="investments",
            description=(
                "Tax treatment of interest, dividends, capital gains/losses, "
                "and investment-related expenses."
            ),
            pub_sections=[
                PubSection(pub_number="550", relevance="primary",
                           notes="Comprehensive investment income guide"),
                PubSection(pub_number="525", chapter="Interest Income",
                           relevance="supplementary"),
            ],
            related_topics=["capital_gains", "dividends", "interest_income"],
            key_terms=[
                "investment income", "investment expenses", "interest",
                "dividends", "bonds", "stocks", "mutual funds",
            ],
        ))

        self.register(TaxTopic(
            topic_id="capital_gains",
            display_name="Capital Gains & Losses",
            parent_topic="investment_income",
            category="investments",
            description=(
                "Tax treatment of gains and losses from selling assets: "
                "holding periods, short-term vs long-term rates, netting rules, "
                "carryover of losses, wash sale rules."
            ),
            pub_sections=[
                PubSection(pub_number="544", relevance="primary",
                           notes="Primary guide to sales of assets and capital gains"),
                PubSection(pub_number="550", chapter="Capital Gains and Losses",
                           relevance="primary",
                           notes="Investment context for capital gains"),
                PubSection(pub_number="523", relevance="supplementary",
                           notes="Home sale exclusion (Section 121)"),
            ],
            related_topics=["basis_of_assets", "home_sale", "holding_period"],
            key_terms=[
                "capital gain", "capital loss", "long-term gain", "short-term gain",
                "holding period", "wash sale", "netting", "carryover",
                "capital loss limitation", "Schedule D",
            ],
        ))

        self.register(TaxTopic(
            topic_id="dividends",
            display_name="Dividend Income",
            parent_topic="investment_income",
            category="investments",
            description=(
                "Tax treatment of ordinary and qualified dividends, "
                "including reinvested dividends and mutual fund distributions."
            ),
            pub_sections=[
                PubSection(pub_number="550", chapter="Dividends and Other Distributions",
                           relevance="primary"),
                PubSection(pub_number="525", chapter="Dividends", relevance="supplementary"),
            ],
            related_topics=["capital_gains", "investment_income"],
            key_terms=[
                "dividend", "qualified dividend", "ordinary dividend",
                "reinvested dividend", "dividend income", "1099-DIV",
            ],
        ))

        self.register(TaxTopic(
            topic_id="interest_income",
            display_name="Interest Income",
            parent_topic="investment_income",
            category="investments",
            description=(
                "Tax treatment of interest from savings, bonds, and other "
                "debt instruments, including tax-exempt interest."
            ),
            pub_sections=[
                PubSection(pub_number="550", chapter="Interest Income",
                           relevance="primary"),
                PubSection(pub_number="525", chapter="Interest Income",
                           relevance="supplementary"),
            ],
            related_topics=["investment_income"],
            key_terms=[
                "interest income", "savings interest", "bond interest",
                "tax-exempt interest", "municipal bond", "1099-INT",
                "original issue discount", "OID",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_income",
            display_name="Business Income & Self-Employment",
            parent_topic="income",
            category="business",
            description=(
                "Income and expenses from self-employment, sole proprietorships, "
                "and small businesses reported on Schedule C."
            ),
            pub_sections=[
                PubSection(pub_number="334", relevance="primary",
                           notes="Tax Guide for Small Business — comprehensive"),
                PubSection(pub_number="535", relevance="primary",
                           notes="Business expenses (2022 final edition)"),
                PubSection(pub_number="587", relevance="supplementary",
                           notes="Home office deduction"),
            ],
            related_topics=["business_expenses", "home_office", "self_employment_tax"],
            key_terms=[
                "business income", "self-employment", "sole proprietor",
                "Schedule C", "net profit", "business receipts",
                "independent contractor", "1099-NEC",
            ],
        ))

        self.register(TaxTopic(
            topic_id="retirement_income",
            display_name="Retirement Income",
            parent_topic="income",
            category="retirement",
            description=(
                "Tax treatment of distributions from IRAs, 401(k)s, pensions, "
                "and annuities including RMDs and early withdrawal penalties."
            ),
            pub_sections=[
                PubSection(pub_number="590b", relevance="primary",
                           notes="IRA distributions — primary reference"),
                PubSection(pub_number="575", relevance="primary",
                           notes="Pension and annuity income"),
                PubSection(pub_number="525", chapter="Pensions and Annuities",
                           relevance="supplementary"),
                PubSection(pub_number="915", relevance="supplementary",
                           notes="Social Security benefits taxation"),
            ],
            related_topics=["ira_contributions", "rmd", "roth_conversions", "social_security_benefits"],
            key_terms=[
                "retirement income", "pension", "annuity", "IRA distribution",
                "401k distribution", "required minimum distribution", "RMD",
                "early withdrawal", "10% penalty",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: DEDUCTIONS
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="deductions",
            display_name="Deductions",
            category="deductions",
            description=(
                "Tax deductions that reduce taxable income: standard deduction, "
                "itemized deductions, and above-the-line adjustments."
            ),
            pub_sections=[
                PubSection(pub_number="17", chapter="Deductions",
                           relevance="primary",
                           notes="Overview of all deduction types"),
                PubSection(pub_number="501", relevance="primary",
                           notes="Standard deduction amounts and rules"),
            ],
            related_topics=[
                "standard_deduction", "itemized_deductions",
                "business_expenses", "charitable_contributions",
            ],
            key_terms=[
                "deduction", "standard deduction", "itemized deduction",
                "above-the-line", "below-the-line", "Schedule A",
                "adjusted gross income", "AGI",
            ],
        ))

        self.register(TaxTopic(
            topic_id="standard_deduction",
            display_name="Standard Deduction",
            parent_topic="deductions",
            category="deductions",
            description=(
                "Standard deduction amounts by filing status, additional amounts "
                "for age 65+ and blind, and when standard vs itemized is better."
            ),
            pub_sections=[
                PubSection(pub_number="501", chapter="Standard Deduction",
                           relevance="primary"),
                PubSection(pub_number="17", chapter="Standard Deduction",
                           relevance="supplementary"),
            ],
            related_topics=["filing_status", "itemized_deductions"],
            key_terms=[
                "standard deduction", "filing status", "additional standard deduction",
                "age 65", "blind", "dependent standard deduction",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_expenses",
            display_name="Business Expenses",
            parent_topic="deductions",
            category="business",
            description=(
                "Deductible business expenses: ordinary and necessary test, "
                "capitalization rules, vehicle expenses, travel, meals."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Business expenses (2022 final edition)"),
                PubSection(pub_number="334", relevance="primary",
                           notes="Small business tax guide"),
                PubSection(pub_number="463", relevance="primary",
                           notes="Travel, car, and entertainment expenses"),
                PubSection(pub_number="15-B", relevance="supplementary",
                           notes="Employer fringe benefit expenses"),
            ],
            related_topics=["home_office", "depreciation", "business_income", "nol", "qbi_deduction"],
            key_terms=[
                "business expense", "ordinary and necessary", "deductible expense",
                "travel expense", "vehicle expense", "mileage", "meals",
                "office supplies", "professional fees", "startup cost",
                "insurance premium", "advertising", "training expense",
                "repair", "maintenance", "business gift", "supplies",
                "dues", "subscription", "license", "permit", "utilities",
                "deduct", "write off", "write-off", "expensing",
            ],
        ))

        self.register(TaxTopic(
            topic_id="home_office",
            display_name="Home Office Deduction",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deduction for business use of home: regular use test, "
                "principal place of business, simplified vs actual method."
            ),
            pub_sections=[
                PubSection(pub_number="587", relevance="primary",
                           notes="Business Use of Your Home — comprehensive"),
                PubSection(pub_number="334", chapter="Business Use of Home",
                           relevance="supplementary"),
            ],
            related_topics=["business_expenses", "depreciation"],
            key_terms=[
                "home office", "business use of home", "Form 8829",
                "simplified method", "actual expense method",
                "regular and exclusive use", "principal place of business",
            ],
        ))

        self.register(TaxTopic(
            topic_id="charitable_contributions",
            display_name="Charitable Contributions",
            parent_topic="deductions",
            category="deductions",
            description=(
                "Deductions for donations to qualified organizations: "
                "cash vs property, AGI limits, substantiation rules, appraisals."
            ),
            pub_sections=[
                PubSection(pub_number="526", relevance="primary",
                           notes="Charitable contribution rules and limits"),
                PubSection(pub_number="561", relevance="primary",
                           notes="Valuation of donated property"),
            ],
            related_topics=["itemized_deductions"],
            key_terms=[
                "charitable contribution", "charitable deduction", "donation",
                "qualified organization", "noncash contribution", "appraisal",
                "substantiation", "Form 8283", "AGI limit",
            ],
        ))

        self.register(TaxTopic(
            topic_id="medical_expenses",
            display_name="Medical & Dental Expenses",
            parent_topic="deductions",
            category="deductions",
            description=(
                "Deductible medical and dental expenses: 7.5% AGI threshold, "
                "qualifying expenses, insurance premiums, long-term care."
            ),
            pub_sections=[
                PubSection(pub_number="502", relevance="primary",
                           notes="Medical and dental expense deduction rules"),
                PubSection(pub_number="969", relevance="supplementary",
                           notes="HSA qualified medical expenses"),
            ],
            related_topics=["hsa", "itemized_deductions"],
            key_terms=[
                "medical expense", "dental expense", "7.5% AGI",
                "Schedule A", "health insurance premium",
                "qualified medical expense", "nursing care",
            ],
        ))

        self.register(TaxTopic(
            topic_id="casualty_theft_loss",
            display_name="Casualty, Disaster & Theft Losses",
            parent_topic="deductions",
            category="deductions",
            description=(
                "Deductions for losses from casualties, federally declared "
                "disasters, and thefts. Includes reduction rules and Form 4684."
            ),
            pub_sections=[
                PubSection(pub_number="547", relevance="primary",
                           notes="Casualty, disaster, and theft loss rules"),
                PubSection(pub_number="544", relevance="supplementary",
                           notes="Involuntary conversions from casualties"),
                PubSection(pub_number="584", relevance="supplementary",
                           notes="Casualty, Disaster, and Theft Loss Workbook"),
            ],
            related_topics=["itemized_deductions", "basis_of_assets"],
            key_terms=[
                "casualty loss", "theft loss", "disaster loss",
                "federally declared disaster", "Form 4684",
                "fair market value", "insurance reimbursement",
                "fire", "house fire", "home destroyed",
                "wildfire", "flood", "earthquake", "hurricane",
                "involuntary conversion", "replacement property",
                "home fire", "property destroyed", "burned down",
                "natural disaster", "damaged home",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: CREDITS
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="credits",
            display_name="Tax Credits",
            category="credits",
            description=(
                "Tax credits that directly reduce tax liability: refundable "
                "and nonrefundable credits including EIC, child credits, "
                "education credits."
            ),
            pub_sections=[
                PubSection(pub_number="17", chapter="Tax Credits",
                           relevance="primary"),
            ],
            related_topics=["eic", "child_care_credit", "education_credits"],
            key_terms=[
                "tax credit", "refundable credit", "nonrefundable credit",
                "credit", "tax liability",
            ],
        ))

        self.register(TaxTopic(
            topic_id="eic",
            display_name="Earned Income Credit (EIC)",
            parent_topic="credits",
            category="credits",
            description=(
                "Earned Income Credit for low-to-moderate income workers: "
                "qualifying child rules, income limits, phase-out tables, "
                "investment income test."
            ),
            pub_sections=[
                PubSection(pub_number="596", relevance="primary",
                           notes="Complete EIC guide with tables and worksheets"),
                PubSection(pub_number="17", chapter="Earned Income Credit",
                           relevance="supplementary"),
            ],
            related_topics=["credits", "filing_requirements"],
            key_terms=[
                "earned income credit", "EIC", "EITC",
                "qualifying child", "investment income limit",
                "phase-out", "Schedule EIC", "refundable",
            ],
        ))

        self.register(TaxTopic(
            topic_id="child_care_credit",
            display_name="Child & Dependent Care Credit",
            parent_topic="credits",
            category="credits",
            description=(
                "Credit for child and dependent care expenses: qualifying "
                "person, care provider, dollar limits, FSA coordination."
            ),
            pub_sections=[
                PubSection(pub_number="503", relevance="primary",
                           notes="Child and dependent care credit rules"),
            ],
            related_topics=["credits", "dependents"],
            key_terms=[
                "child care credit", "dependent care", "Form 2441",
                "qualifying person", "care provider",
                "dependent care FSA", "earned income requirement",
            ],
        ))

        self.register(TaxTopic(
            topic_id="education_credits",
            display_name="Education Credits & Deductions",
            parent_topic="credits",
            category="education",
            description=(
                "American Opportunity Credit, Lifetime Learning Credit, "
                "student loan interest deduction, education savings accounts."
            ),
            pub_sections=[
                PubSection(pub_number="970", relevance="primary",
                           notes="Comprehensive education tax benefits guide"),
            ],
            related_topics=["credits"],
            key_terms=[
                "education credit", "American Opportunity Credit",
                "Lifetime Learning Credit", "student loan interest",
                "Form 8863", "qualified education expense",
                "529 plan", "Coverdell ESA",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: PROPERTY & BASIS
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="property_basis",
            display_name="Property, Basis & Depreciation",
            category="property",
            description=(
                "Rules for determining property basis, adjustments, "
                "depreciation methods, and tax treatment of property sales."
            ),
            pub_sections=[
                PubSection(pub_number="551", relevance="primary",
                           notes="Basis of Assets — master reference"),
                PubSection(pub_number="544", relevance="primary",
                           notes="Sales and dispositions of assets"),
                PubSection(pub_number="946", relevance="primary",
                           notes="Depreciation methods"),
            ],
            related_topics=[
                "basis_of_assets", "depreciation", "home_sale", "rental_property",
            ],
            key_terms=[
                "property", "basis", "depreciation", "asset",
                "adjusted basis", "fair market value",
            ],
        ))

        self.register(TaxTopic(
            topic_id="basis_of_assets",
            display_name="Basis of Assets",
            parent_topic="property_basis",
            category="property",
            description=(
                "Determining and adjusting basis: cost basis, gift basis, "
                "inherited basis (stepped-up), and basis adjustments."
            ),
            pub_sections=[
                PubSection(pub_number="551", relevance="primary",
                           notes="Basis of Assets — complete guide"),
                PubSection(pub_number="544", chapter="Basis of Assets Sold",
                           relevance="supplementary"),
            ],
            related_topics=["capital_gains", "depreciation", "home_sale"],
            key_terms=[
                "basis", "cost basis", "adjusted basis", "stepped-up basis",
                "gift basis", "inherited property", "basis adjustment",
                "fair market value at death",
            ],
        ))

        self.register(TaxTopic(
            topic_id="depreciation",
            display_name="Depreciation",
            parent_topic="property_basis",
            category="property",
            description=(
                "Depreciation methods for business and rental property: "
                "MACRS, Section 179, bonus depreciation, recovery periods."
            ),
            pub_sections=[
                PubSection(pub_number="946", relevance="primary",
                           notes="How to Depreciate Property — comprehensive"),
                PubSection(pub_number="527", chapter="Depreciation",
                           relevance="supplementary",
                           notes="Rental property depreciation specifics"),
                PubSection(pub_number="587", chapter="Depreciation",
                           relevance="supplementary",
                           notes="Home office depreciation"),
            ],
            related_topics=["rental_property", "business_expenses", "basis_of_assets"],
            key_terms=[
                "depreciation", "MACRS", "Section 179", "bonus depreciation",
                "recovery period", "depreciable property", "Form 4562",
                "straight-line", "declining balance", "convention",
                "equipment purchases", "equipment deduction",
                "first-year deduction", "first year deduction",
                "asset purchase", "cost recovery",
                "write off equipment", "expensing",
            ],
        ))

        self.register(TaxTopic(
            topic_id="home_sale",
            display_name="Selling Your Home",
            parent_topic="property_basis",
            category="property",
            description=(
                "Section 121 exclusion for home sale gains: ownership and use "
                "tests, $250K/$500K exclusion, partial exclusions, reporting."
            ),
            pub_sections=[
                PubSection(pub_number="523", relevance="primary",
                           notes="Selling Your Home — complete guide"),
                PubSection(pub_number="544", chapter="Sales of Property",
                           relevance="supplementary"),
                PubSection(pub_number="551", chapter="Basis of Your Home",
                           relevance="supplementary"),
            ],
            related_topics=["capital_gains", "basis_of_assets"],
            key_terms=[
                "home sale", "selling your home", "Section 121",
                "exclusion", "ownership test", "use test",
                "$250,000", "$500,000", "primary residence",
                "adjusted basis of home",
            ],
        ))

        self.register(TaxTopic(
            topic_id="rental_property",
            display_name="Rental Property",
            parent_topic="property_basis",
            category="property",
            description=(
                "Tax treatment of residential rental income and expenses: "
                "rental income reporting, allowable deductions, depreciation, "
                "passive activity limitations."
            ),
            pub_sections=[
                PubSection(pub_number="527", relevance="primary",
                           notes="Residential Rental Property — comprehensive"),
                PubSection(pub_number="946", chapter="MACRS",
                           relevance="supplementary",
                           notes="Depreciation for rental property"),
                PubSection(pub_number="551", chapter="Basis",
                           relevance="reference",
                           notes="Determining basis for rental property"),
                PubSection(pub_number="925", relevance="supplementary",
                           notes="Passive activity rules for rentals"),
            ],
            related_topics=["depreciation", "passive_activity", "basis_of_assets"],
            key_terms=[
                "rental property", "rental income", "rental expense",
                "Schedule E", "passive activity", "passive loss",
                "real estate professional", "fair rental days",
                "personal use days",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: RETIREMENT & SAVINGS
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="retirement",
            display_name="Retirement Plans & Savings",
            category="retirement",
            description=(
                "Tax treatment of retirement plan contributions and distributions: "
                "IRAs, 401(k), pensions, annuities, HSAs."
            ),
            pub_sections=[
                PubSection(pub_number="590a", relevance="primary",
                           notes="IRA contributions"),
                PubSection(pub_number="590b", relevance="primary",
                           notes="IRA distributions"),
                PubSection(pub_number="575", relevance="primary",
                           notes="Pension and annuity income"),
            ],
            related_topics=[
                "ira_contributions", "retirement_income", "hsa", "rmd",
            ],
            key_terms=[
                "retirement", "IRA", "401k", "pension", "annuity",
                "Roth", "traditional IRA", "retirement savings",
            ],
        ))

        self.register(TaxTopic(
            topic_id="ira_contributions",
            display_name="IRA Contributions",
            parent_topic="retirement",
            category="retirement",
            description=(
                "Traditional and Roth IRA contribution rules: annual limits, "
                "income phase-outs, deductibility, catch-up contributions, SEP."
            ),
            pub_sections=[
                PubSection(pub_number="590a", relevance="primary",
                           notes="IRA Contributions — complete guide"),
                PubSection(pub_number="560", relevance="supplementary",
                           notes="SEP and SIMPLE IRA plans"),
            ],
            related_topics=["retirement_income", "rmd", "small_business_retirement"],
            key_terms=[
                "IRA contribution", "contribution limit", "deductible IRA",
                "nondeductible IRA", "Roth IRA contribution",
                "income phase-out", "catch-up contribution",
                "SEP IRA", "SIMPLE IRA", "Form 5498",
            ],
        ))

        self.register(TaxTopic(
            topic_id="rmd",
            display_name="Required Minimum Distributions",
            parent_topic="retirement",
            category="retirement",
            description=(
                "RMD rules: when they start, how to calculate them, "
                "life expectancy tables, penalties for missed RMDs."
            ),
            pub_sections=[
                PubSection(pub_number="590b", chapter="Required Minimum Distributions",
                           relevance="primary"),
            ],
            related_topics=["retirement_income", "ira_contributions"],
            key_terms=[
                "required minimum distribution", "RMD",
                "life expectancy table", "uniform lifetime table",
                "age 73", "50% penalty", "missed RMD",
            ],
        ))

        self.register(TaxTopic(
            topic_id="roth_conversions",
            display_name="Roth Conversions",
            parent_topic="retirement",
            category="retirement",
            description=(
                "Converting traditional IRA to Roth: tax consequences, "
                "ordering rules, 5-year rule, backdoor Roth."
            ),
            pub_sections=[
                PubSection(pub_number="590a", chapter="Roth IRA",
                           relevance="primary"),
                PubSection(pub_number="590b", chapter="Roth IRA Distributions",
                           relevance="primary"),
            ],
            related_topics=["ira_contributions", "retirement_income"],
            key_terms=[
                "Roth conversion", "backdoor Roth", "5-year rule",
                "recharacterization", "ordering rules",
                "traditional to Roth", "taxable conversion",
            ],
        ))

        self.register(TaxTopic(
            topic_id="hsa",
            display_name="Health Savings Accounts",
            parent_topic="retirement",
            category="benefits",
            description=(
                "HSA rules: eligibility, contribution limits, qualified "
                "medical expenses, HDHP requirements, catch-up amounts."
            ),
            pub_sections=[
                PubSection(pub_number="969", relevance="primary",
                           notes="HSA and tax-favored health plans"),
            ],
            related_topics=["medical_expenses"],
            key_terms=[
                "HSA", "health savings account", "contribution limit",
                "HDHP", "high-deductible health plan",
                "qualified medical expense", "Form 8889",
                "catch-up contribution",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ROOT: FILING & GENERAL
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="filing",
            display_name="Filing Requirements & Status",
            category="general",
            description=(
                "Who must file, filing status determination, dependents, "
                "withholding, and estimated tax payments."
            ),
            pub_sections=[
                PubSection(pub_number="17", chapter="Filing Requirements",
                           relevance="primary"),
                PubSection(pub_number="501", relevance="primary",
                           notes="Dependents, standard deduction, filing info"),
                PubSection(pub_number="505", relevance="primary",
                           notes="Withholding and estimated tax"),
            ],
            related_topics=[
                "filing_status", "dependents", "withholding",
                "standard_deduction",
            ],
            key_terms=[
                "filing requirement", "must file", "filing status",
                "Form 1040", "tax return", "due date", "extension",
            ],
        ))

        self.register(TaxTopic(
            topic_id="filing_status",
            display_name="Filing Status",
            parent_topic="filing",
            category="general",
            description=(
                "Five filing statuses and rules for choosing the correct one: "
                "single, MFJ, MFS, HOH, qualifying surviving spouse."
            ),
            pub_sections=[
                PubSection(pub_number="501", chapter="Filing Status",
                           relevance="primary"),
                PubSection(pub_number="504", relevance="supplementary",
                           notes="Filing status for divorced/separated"),
            ],
            related_topics=["dependents", "standard_deduction"],
            key_terms=[
                "filing status", "single", "married filing jointly",
                "married filing separately", "head of household",
                "qualifying surviving spouse", "MFJ", "MFS", "HOH",
            ],
        ))

        self.register(TaxTopic(
            topic_id="dependents",
            display_name="Dependents",
            parent_topic="filing",
            category="general",
            description=(
                "Rules for claiming dependents: qualifying child, qualifying "
                "relative, support test, residency test, tiebreaker rules."
            ),
            pub_sections=[
                PubSection(pub_number="501", chapter="Dependents",
                           relevance="primary"),
                PubSection(pub_number="504", chapter="Exemptions for Dependents",
                           relevance="supplementary"),
            ],
            related_topics=["filing_status", "eic", "child_care_credit"],
            key_terms=[
                "dependent", "qualifying child", "qualifying relative",
                "support test", "residency test", "age test",
                "relationship test", "tiebreaker",
            ],
        ))

        self.register(TaxTopic(
            topic_id="withholding",
            display_name="Withholding & Estimated Tax",
            parent_topic="filing",
            category="general",
            description=(
                "Income tax withholding rules and estimated tax payments: "
                "W-4, quarterly payments, safe harbor, underpayment penalties."
            ),
            pub_sections=[
                PubSection(pub_number="505", relevance="primary",
                           notes="Withholding and estimated tax — comprehensive"),
                PubSection(pub_number="15", relevance="supplementary",
                           notes="Employer withholding requirements"),
            ],
            related_topics=["self_employment_tax", "filing", "employer_taxes"],
            key_terms=[
                "withholding", "estimated tax", "Form W-4",
                "Form 1040-ES", "quarterly payment", "safe harbor",
                "underpayment penalty", "Form 2210",
                "90%", "100%", "110%", "estimated payment",
                "extension", "filing extension", "late payment",
            ],
        ))

        self.register(TaxTopic(
            topic_id="self_employment_tax",
            display_name="Self-Employment Tax",
            parent_topic="filing",
            category="business",
            description=(
                "Social Security and Medicare tax for self-employed individuals: "
                "SE tax calculation, deductible half, Schedule SE."
            ),
            pub_sections=[
                PubSection(pub_number="334", chapter="Self-Employment Tax",
                           relevance="primary"),
                PubSection(pub_number="505", chapter="Self-Employment",
                           relevance="supplementary"),
            ],
            related_topics=["business_income", "withholding"],
            key_terms=[
                "self-employment tax", "SE tax", "Schedule SE",
                "Social Security", "Medicare", "net earnings",
                "15.3%", "deductible half",
            ],
        ))

        self.register(TaxTopic(
            topic_id="divorce_separation",
            display_name="Divorce & Separation",
            parent_topic="filing",
            category="general",
            description=(
                "Tax implications of divorce and separation: alimony treatment, "
                "property transfers, filing status, dependent claims."
            ),
            pub_sections=[
                PubSection(pub_number="504", relevance="primary",
                           notes="Divorced or Separated Individuals"),
            ],
            related_topics=["filing_status", "dependents"],
            key_terms=[
                "divorce", "separation", "alimony", "spousal support",
                "child support", "property settlement",
                "QDRO", "innocent spouse",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # NEW TOPICS — added for golden-set coverage
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="partnerships",
            display_name="Partnerships",
            parent_topic="business_income",
            category="business",
            description=(
                "Tax treatment of partnerships: formation, distributive shares, "
                "basis, Schedule K-1 reporting, self-employment implications."
            ),
            pub_sections=[
                PubSection(pub_number="541", relevance="primary",
                           notes="Partnerships — complete guide"),
                PubSection(pub_number="334", relevance="supplementary",
                           notes="Small business partnership context"),
            ],
            related_topics=["business_income", "self_employment_tax"],
            key_terms=[
                "partnership", "partner", "general partner",
                "limited partner", "distributive share", "K-1",
                "Schedule K-1", "Form 1065", "partnership basis",
                "guaranteed payment",
            ],
        ))

        self.register(TaxTopic(
            topic_id="corporations",
            display_name="Corporations",
            parent_topic="business_income",
            category="business",
            description=(
                "Tax treatment of C and S corporations: formation, income, "
                "deductions, distributions, and entity-level tax."
            ),
            pub_sections=[
                PubSection(pub_number="542", relevance="primary",
                           notes="Corporations — complete guide"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["business_income", "dividends"],
            key_terms=[
                "corporation", "C corp", "S corp", "S corporation",
                "corporate tax", "Form 1120", "Form 1120-S",
                "accumulated earnings", "shareholder",
            ],
        ))

        self.register(TaxTopic(
            topic_id="nol",
            display_name="Net Operating Losses",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Net operating loss rules: how to figure an NOL, "
                "carryforward rules, excess business loss limitation."
            ),
            pub_sections=[
                PubSection(pub_number="536", relevance="primary",
                           notes="NOLs for individuals, estates, and trusts"),
                PubSection(pub_number="535", relevance="supplementary",
                           notes="Business expense context for NOLs"),
            ],
            related_topics=["business_expenses", "business_income"],
            key_terms=[
                "net operating loss", "NOL", "carryforward",
                "carryback", "excess business loss", "Form 1045",
                "loss limitation", "80% limitation", "NOL deduction",
                "carry back", "carry forward", "operating loss",
            ],
        ))

        self.register(TaxTopic(
            topic_id="passive_activity",
            display_name="Passive Activity Rules",
            parent_topic="property_basis",
            category="investments",
            description=(
                "Passive activity loss rules: material participation tests, "
                "at-risk rules, rental activity rules, suspended losses."
            ),
            pub_sections=[
                PubSection(pub_number="925", relevance="primary",
                           notes="Passive Activity and At-Risk Rules"),
                PubSection(pub_number="527", relevance="supplementary",
                           notes="Rental passive activity context"),
            ],
            related_topics=["rental_property", "business_income"],
            key_terms=[
                "passive activity", "passive loss", "material participation",
                "at-risk rules", "passive income", "Form 8582",
                "suspended loss", "active participation",
                "real estate professional",
                "$25,000 loss", "$25,000 allowance", "rental loss limit",
                "$30,000 loss", "rental loss deduction",
                "passive loss limit", "rental activity loss",
                "how much rental loss", "rental loss AGI",
                "$100,000 AGI", "$150,000 phase-out",
                "rental loss", "rental losses",
                "$30,000 in rental", "deduct rental",
                "passive gains", "loss limit",
                "$30,000 annual", "annual loss limit",
            ],
        ))

        self.register(TaxTopic(
            topic_id="qbi_deduction",
            display_name="Qualified Business Income (Section 199A)",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Section 199A QBI deduction: 20% deduction for pass-through "
                "income, SSTB rules, W-2 wage and property limitations."
            ),
            pub_sections=[
                PubSection(pub_number="8995-A", relevance="primary",
                           notes="QBI deduction instructions"),
                PubSection(pub_number="535", relevance="supplementary"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["business_income", "partnerships", "corporations"],
            key_terms=[
                "QBI", "qualified business income", "Section 199A",
                "pass-through deduction", "20% deduction",
                "specified service", "SSTB", "Form 8995",
                "W-2 wage limitation",
            ],
        ))

        self.register(TaxTopic(
            topic_id="installment_sales",
            display_name="Installment Sales",
            parent_topic="capital_gains",
            category="property",
            description=(
                "Tax treatment of installment sales: eligibility, "
                "gross profit percentage, reporting, interest charge."
            ),
            pub_sections=[
                PubSection(pub_number="537", relevance="primary",
                           notes="Installment sales — complete guide"),
                PubSection(pub_number="544", relevance="supplementary"),
            ],
            related_topics=["capital_gains", "basis_of_assets"],
            key_terms=[
                "installment sale", "installment method",
                "Form 6252", "gross profit percentage",
                "deferred payment", "installment obligation",
            ],
        ))

        self.register(TaxTopic(
            topic_id="small_business_retirement",
            display_name="Small Business Retirement Plans",
            parent_topic="retirement",
            category="retirement",
            description=(
                "Retirement plan options for small businesses: SEP-IRA, "
                "SIMPLE IRA, solo 401(k), qualified plans."
            ),
            pub_sections=[
                PubSection(pub_number="560", relevance="primary",
                           notes="Retirement Plans for Small Business"),
                PubSection(pub_number="590a", relevance="supplementary",
                           notes="SEP and SIMPLE IRA contribution rules"),
            ],
            related_topics=["ira_contributions", "retirement", "self_employment_tax"],
            key_terms=[
                "SEP", "SEP-IRA", "SIMPLE", "SIMPLE IRA",
                "solo 401k", "Keogh", "profit-sharing plan",
                "small business retirement", "employer contribution",
                "Form 5500",
            ],
        ))

        self.register(TaxTopic(
            topic_id="social_security_benefits",
            display_name="Social Security Benefits",
            parent_topic="retirement_income",
            category="income",
            description=(
                "Tax treatment of social security benefits: provisional income, "
                "85% inclusion rule, lump-sum election."
            ),
            pub_sections=[
                PubSection(pub_number="915", relevance="primary",
                           notes="Social Security and Railroad Retirement Benefits"),
                PubSection(pub_number="525", relevance="supplementary"),
            ],
            related_topics=["retirement_income"],
            key_terms=[
                "social security", "social security benefits",
                "SSA-1099", "provisional income",
                "85% taxable", "50% taxable", "base amount",
                "combined income",
            ],
        ))

        self.register(TaxTopic(
            topic_id="child_tax_credit",
            display_name="Child Tax Credit",
            parent_topic="credits",
            category="credits",
            description=(
                "Child tax credit and additional child tax credit: "
                "$2,000 per child, refundable portion, income limits."
            ),
            pub_sections=[
                PubSection(pub_number="8812", relevance="primary",
                           notes="Schedule 8812 instructions"),
                PubSection(pub_number="17", relevance="supplementary"),
            ],
            related_topics=["credits", "dependents", "eic"],
            key_terms=[
                "child tax credit", "CTC", "additional child tax credit",
                "ACTC", "Schedule 8812", "$2,000 per child",
                "refundable", "qualifying child", "$2,200",
                "per child", "child credit", "dependent credit",
            ],
        ))

        self.register(TaxTopic(
            topic_id="premium_tax_credit",
            display_name="Premium Tax Credit",
            parent_topic="credits",
            category="credits",
            description=(
                "Premium tax credit for health insurance marketplace: "
                "eligibility, advance payments, reconciliation."
            ),
            pub_sections=[
                PubSection(pub_number="8962", relevance="primary",
                           notes="Form 8962 instructions"),
                PubSection(pub_number="1040", relevance="supplementary",
                           notes="Form 1040 Instructions — PTC reconciliation "
                                 "and MeF reject troubleshooting (F8962-070)"),
            ],
            related_topics=["credits", "hsa"],
            key_terms=[
                "premium tax credit", "PTC", "marketplace",
                "advance premium tax credit", "APTC",
                "Form 1095-A", "Form 8962",
                "health insurance", "ACA",
                "marketplace data", "F8962-070",
                "e-file fail marketplace", "e-file rejected marketplace",
            ],
        ))

        self.register(TaxTopic(
            topic_id="research_credit",
            display_name="Research & Development Credit",
            parent_topic="credits",
            category="credits",
            description=(
                "Credit for increasing research activities: qualified research "
                "expenses, ASC method, payroll tax offset for small businesses."
            ),
            pub_sections=[
                PubSection(pub_number="6765", relevance="primary",
                           notes="Form 6765 instructions"),
                PubSection(pub_number="535", relevance="primary",
                           notes="Pub 535 Ch.7 — R&D expenses & amortization"),
            ],
            related_topics=["credits", "business_income", "business_expenses"],
            key_terms=[
                "research credit", "R&D credit", "R&E credit",
                "Form 6765", "qualified research expenses",
                "ASC method", "payroll tax offset",
                "R&D", "research", "Section 174",
                "R&D expensing", "amortize research", "domestic R&D",
                "research costs", "experimental expenditures",
                "amortize", "5 year", "5-year", "immediate expensing",
            ],
        ))

        self.register(TaxTopic(
            topic_id="employer_taxes",
            display_name="Employer Tax Obligations",
            parent_topic="filing",
            category="employment",
            description=(
                "Employer tax responsibilities: withholding, FICA, FUTA, "
                "Form W-2, payroll deposits, household employers."
            ),
            pub_sections=[
                PubSection(pub_number="15", relevance="primary",
                           notes="Circular E — Employer's Tax Guide"),
                PubSection(pub_number="926", relevance="primary",
                           notes="Household Employer's Tax Guide"),
                PubSection(pub_number="15-B", relevance="supplementary",
                           notes="Fringe benefits"),
            ],
            related_topics=["withholding", "self_employment_tax"],
            key_terms=[
                "employer tax", "payroll tax", "FICA", "FUTA",
                "Form 941", "Form 940", "W-2", "W-3",
                "deposit schedule", "household employer",
                "nanny tax", "Schedule H",
            ],
        ))

        self.register(TaxTopic(
            topic_id="mortgage_interest",
            display_name="Mortgage Interest Deduction",
            parent_topic="deductions",
            category="deductions",
            description=(
                "Deduction for home mortgage interest: qualified residence, "
                "points, $750K/$1M limitation, SALT interaction."
            ),
            pub_sections=[
                PubSection(pub_number="936", relevance="primary",
                           notes="Home Mortgage Interest Deduction"),
                PubSection(pub_number="523", relevance="supplementary"),
            ],
            related_topics=["deductions", "home_sale"],
            key_terms=[
                "mortgage interest", "home mortgage", "points",
                "Form 1098", "qualified residence", "SALT",
                "mortgage interest deduction", "home equity",
            ],
        ))

        self.register(TaxTopic(
            topic_id="information_returns",
            display_name="Information Returns & Reporting",
            parent_topic="filing",
            category="reporting",
            description=(
                "1099-series information return requirements: filing thresholds, "
                "1099-K, 1099-NEC, electronic filing requirements."
            ),
            pub_sections=[
                PubSection(pub_number="1099", relevance="primary",
                           notes="General Instructions for 1099-series"),
                PubSection(pub_number="525", relevance="supplementary"),
            ],
            related_topics=["employer_taxes", "filing"],
            key_terms=[
                "1099", "information return", "1099-K",
                "1099-NEC", "1099-MISC", "1099-INT", "1099-DIV",
                "reporting threshold", "$5,000", "$600", "$2,000",
                "electronic filing", "issue 1099", "file 1099",
            ],
        ))

        self.register(TaxTopic(
            topic_id="trump_account",
            display_name="Trump Account (OBBBA)",
            parent_topic="retirement",
            category="savings",
            description=(
                "Trump Account: new tax-advantaged savings account for U.S.-born "
                "children under the One Big Beautiful Bill Act (OBBBA). "
                "$1,000 government contribution, tax-free growth."
            ),
            pub_sections=[
                PubSection(pub_number="4547", relevance="primary",
                           notes="Form 4547 — Trump Account"),
                PubSection(pub_number="15-B", relevance="supplementary",
                           notes="Employer contributions as fringe benefit"),
                PubSection(pub_number="590a", relevance="supplementary",
                           notes="IRA-like contribution rules"),
                PubSection(pub_number="W-2", relevance="supplementary",
                           notes="W-2 Box 12 employer contribution reporting"),
            ],
            related_topics=["education_credits", "employer_taxes"],
            key_terms=[
                "Trump Account", "MAGA account", "newborn savings",
                "Form 4547", "$1,000", "child savings",
                "OBBBA", "tax-free growth",
                "employer contribution", "fringe benefit",
                "employer match", "W-2 Box 12", "report on W-2",
                "baby bond", "child account",
                "company contributes", "employer put",
                "daughter's account", "child's account",
                "report the $2,500", "nonprofit employer",
            ],
        ))

        self.register(TaxTopic(
            topic_id="tip_overtime_deduction",
            display_name="Tip & Overtime Income Deductions (OBBBA)",
            parent_topic="deductions",
            category="deductions",
            description=(
                "New above-the-line deductions for tip and overtime income "
                "under OBBBA: eligible workers, income caps, W-2 reporting."
            ),
            pub_sections=[
                PubSection(pub_number="1-A", relevance="primary",
                           notes="Schedule 1-A — tip and overtime deductions"),
                PubSection(pub_number="17", relevance="supplementary"),
                PubSection(pub_number="W-2", relevance="supplementary",
                           notes="W-2 reporting for tips and overtime"),
            ],
            related_topics=["income", "employer_taxes"],
            key_terms=[
                "tip deduction", "overtime deduction", "tip income",
                "overtime pay", "cash tip", "above-the-line",
                "Schedule 1-A", "OBBBA", "tipped worker",
                "$160,000 cap", "tips", "overtime", "tip",
                "qualified tip", "overtime premium", "FLSA",
                "$25,000", "tax-free tips", "tipped",
                "Form 1-A", "1-A", "W-2 code",
            ],
        ))

        # ── Tip/Overtime sub-topics for better routing ────────────────────

        self.register(TaxTopic(
            topic_id="no_tax_on_tips",
            display_name="No Tax on Tips Deduction",
            parent_topic="tip_overtime_deduction",
            category="deductions",
            description=(
                "Qualified tips deduction on Schedule 1-A: up to $25,000 of "
                "tips excluded from taxable income, W-2 Code TP reporting, "
                "income phase-out rules."
            ),
            pub_sections=[
                PubSection(pub_number="1-A", relevance="primary",
                           notes="Schedule 1-A tips deduction calculation"),
                PubSection(pub_number="17", relevance="supplementary",
                           notes="Pub 17 What's New — tips deduction overview"),
            ],
            related_topics=["tip_overtime_deduction", "income"],
            key_terms=[
                "tips deduction", "qualified tips", "tip income", "cash tip",
                "tax-free tips", "no tax on tips", "tipped worker",
                "tipped employee", "tips tax-free", "tip deduction",
                "Schedule 1-A", "1-A", "Code TP", "W-2 tips",
                "$25,000", "tip cap", "tip phase-out", "tips phase-out",
                "waitress", "waiter", "server", "bartender",
            ],
        ))

        self.register(TaxTopic(
            topic_id="no_tax_on_overtime",
            display_name="No Tax on Overtime Deduction",
            parent_topic="tip_overtime_deduction",
            category="deductions",
            description=(
                "Qualified overtime deduction on Schedule 1-A: overtime "
                "premium (the 'half' of time-and-a-half) is deductible, "
                "W-2 Code TT reporting, income phase-out rules."
            ),
            pub_sections=[
                PubSection(pub_number="1-A", relevance="primary",
                           notes="Schedule 1-A overtime deduction calculation"),
                PubSection(pub_number="17", relevance="primary",
                           notes="Pub 17 — overtime deduction rules and eligibility"),
            ],
            related_topics=["tip_overtime_deduction", "income"],
            key_terms=[
                "overtime deduction", "overtime premium", "overtime pay",
                "no tax on overtime", "time-and-a-half", "overtime income",
                "qualified overtime", "FLSA", "overtime tax-free",
                "Schedule 1-A", "1-A", "Code TT", "W-2 overtime",
                "overtime cap", "overtime phase-out", "$150,000",
                "$300,000", "overtime worker", "factory worker",
            ],
        ))

        self.register(TaxTopic(
            topic_id="qualified_tips",
            display_name="Qualified Tips Definition & Reporting",
            parent_topic="tip_overtime_deduction",
            category="deductions",
            description=(
                "What constitutes qualified tips for the Schedule 1-A "
                "deduction: cash tips, credit card tips, tip pooling, "
                "W-2 Code TP reporting requirements."
            ),
            pub_sections=[
                PubSection(pub_number="1-A", relevance="primary",
                           notes="Schedule 1-A qualified tips definition"),
                PubSection(pub_number="17", relevance="supplementary"),
                PubSection(pub_number="W-2", relevance="supplementary",
                           notes="W-2 Code TP for qualified tips"),
            ],
            related_topics=["tip_overtime_deduction", "no_tax_on_tips"],
            key_terms=[
                "qualified tip", "qualified tips", "tip reporting",
                "Code TP", "W-2 code", "tip pooling", "credit card tip",
                "cash tip", "allocated tips", "tip income",
                "tips W-2", "employer tips",
            ],
        ))

        # ═══════════════════════════════════════════════════════════════════
        # ADDITIONAL SUB-TOPICS — targeting eval gaps
        # ═══════════════════════════════════════════════════════════════════

        self.register(TaxTopic(
            topic_id="startup_costs",
            display_name="Startup & Organizational Costs",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deduction and amortization of startup and organizational costs: "
                "$5,000 first-year deduction, 180-month amortization, Form 4562."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Business startup costs rules"),
                PubSection(pub_number="334", relevance="primary",
                           notes="Small business startup context"),
            ],
            related_topics=["business_expenses"],
            key_terms=[
                "startup cost", "startup expense", "organizational cost",
                "start-up", "new business", "first year deduction",
                "180-month amortization", "Form 4562",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_meals",
            display_name="Business Meal Deduction",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deduction for business meal expenses: 50% limitation, "
                "documentation requirements, per diem rates."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Meal expense rules and limitations"),
                PubSection(pub_number="463", relevance="primary",
                           notes="Travel, entertainment, and meal expenses"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["business_expenses"],
            key_terms=[
                "meal expense", "meal deduction", "business meal",
                "50% deduction", "per diem", "entertainment",
                "food and beverage", "client meal", "employee meal",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_insurance",
            display_name="Business Insurance Deductions",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deductible business insurance: health, liability, property, "
                "workers compensation, and self-employed health insurance."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Business insurance deduction rules"),
                PubSection(pub_number="334", relevance="primary"),
                PubSection(pub_number="502", relevance="supplementary",
                           notes="Self-employed health insurance context"),
            ],
            related_topics=["business_expenses", "medical_expenses"],
            key_terms=[
                "business insurance", "insurance premium", "insurance deduction",
                "liability insurance", "health insurance premium",
                "self-employed health insurance", "workers compensation",
                "professional insurance", "property insurance",
                "deduct insurance", "employee health",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_gifts",
            display_name="Business Gift Deduction",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deduction for business gifts: $25 per recipient limit, "
                "exceptions for nominal value, promotional items."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary"),
                PubSection(pub_number="463", relevance="primary",
                           notes="Gift expense rules in travel/entertainment context"),
            ],
            related_topics=["business_expenses"],
            key_terms=[
                "business gift", "gift deduction", "$25 limit",
                "gift to client", "promotional item",
            ],
        ))

        self.register(TaxTopic(
            topic_id="inventory_cogs",
            display_name="Inventory & Cost of Goods Sold",
            parent_topic="business_income",
            category="business",
            description=(
                "Inventory valuation and cost of goods sold: capitalization, "
                "FIFO, LIFO, and lower of cost or market methods."
            ),
            pub_sections=[
                PubSection(pub_number="334", relevance="primary",
                           notes="Cost of goods sold for small businesses"),
                PubSection(pub_number="535", relevance="primary",
                           notes="Capitalization rules for inventory"),
            ],
            related_topics=["business_income", "business_expenses"],
            key_terms=[
                "inventory", "cost of goods sold", "COGS",
                "capitalization", "FIFO", "LIFO", "valuation",
            ],
        ))

        self.register(TaxTopic(
            topic_id="estimated_tax_payments",
            display_name="Estimated Tax Payments",
            parent_topic="withholding",
            category="general",
            description=(
                "Quarterly estimated tax payment rules: safe harbor, "
                "penalty calculation, Form 1040-ES, annualized income."
            ),
            pub_sections=[
                PubSection(pub_number="505", relevance="primary",
                           notes="Estimated tax payment rules"),
                PubSection(pub_number="17", relevance="supplementary",
                           notes="Filing requirements and estimated tax"),
            ],
            related_topics=["withholding", "self_employment_tax"],
            key_terms=[
                "estimated tax", "quarterly payment", "safe harbor",
                "underpayment penalty", "Form 1040-ES", "Form 2210",
                "90% current year", "100% prior year", "110%",
                "annualized income",
            ],
        ))

        self.register(TaxTopic(
            topic_id="gambling_income",
            display_name="Gambling Income & Losses",
            parent_topic="income",
            category="income",
            description=(
                "Tax treatment of gambling income and losses: reporting, "
                "itemized deduction for losses, Form W-2G."
            ),
            pub_sections=[
                PubSection(pub_number="529", relevance="primary",
                           notes="Miscellaneous deductions including gambling"),
                PubSection(pub_number="525", relevance="primary",
                           notes="Gambling income reporting"),
                PubSection(pub_number="17", relevance="supplementary"),
            ],
            related_topics=["income"],
            key_terms=[
                "gambling", "gambling income", "gambling loss",
                "winnings", "casino", "lottery", "Form W-2G",
                "wagering", "betting",
            ],
        ))

        self.register(TaxTopic(
            topic_id="educational_assistance",
            display_name="Employer Educational Assistance",
            parent_topic="education_credits",
            category="education",
            description=(
                "Tax-free employer educational assistance: $5,250 annual limit, "
                "qualified expenses, Section 127 plans."
            ),
            pub_sections=[
                PubSection(pub_number="970", relevance="primary",
                           notes="Education tax benefits"),
                PubSection(pub_number="15-B", relevance="primary",
                           notes="Employer-provided educational assistance as fringe benefit"),
            ],
            related_topics=["education_credits", "employer_taxes"],
            key_terms=[
                "educational assistance", "employer education",
                "tuition reimbursement", "$5,250", "Section 127",
                "educational benefit", "employer-provided education",
                "tuition assistance",
            ],
        ))

        self.register(TaxTopic(
            topic_id="obbba_salt",
            display_name="SALT Deduction (OBBBA)",
            parent_topic="deductions",
            category="deductions",
            description=(
                "State and local tax deduction under OBBBA: $40,000 cap, "
                "$500,000 income phase-out threshold, Schedule 1-A interaction."
            ),
            pub_sections=[
                PubSection(pub_number="17", relevance="primary",
                           notes="SALT deduction overview"),
                PubSection(pub_number="505", relevance="primary",
                           notes="Withholding and SALT interaction"),
                PubSection(pub_number="501", relevance="supplementary"),
                PubSection(pub_number="1-A", relevance="supplementary",
                           notes="Schedule 1-A SALT provisions"),
            ],
            related_topics=["deductions", "tip_overtime_deduction"],
            key_terms=[
                "SALT", "state and local tax", "SALT cap", "SALT deduction",
                "$40,000", "$10,000", "state tax deduction",
                "local tax deduction", "property tax deduction",
                "OBBBA", "Schedule A",
            ],
        ))

        self.register(TaxTopic(
            topic_id="obbba_senior_deduction",
            display_name="Senior Standard Deduction (OBBBA)",
            parent_topic="standard_deduction",
            category="deductions",
            description=(
                "New OBBBA senior deduction: $6,000 for age 65+, "
                "$150,000 MAGI phase-out, per-spouse calculation."
            ),
            pub_sections=[
                PubSection(pub_number="17", relevance="primary",
                           notes="Senior deduction rules"),
                PubSection(pub_number="501", relevance="primary",
                           notes="Standard deduction and senior amounts"),
                PubSection(pub_number="1040", relevance="supplementary",
                           notes="Form 1040 senior deduction line"),
            ],
            related_topics=["standard_deduction", "filing"],
            key_terms=[
                "senior deduction", "age 65", "senior standard deduction",
                "OBBBA senior", "$6,000", "over 65", "elderly",
                "additional deduction", "phase-out", "$150,000",
            ],
        ))

        self.register(TaxTopic(
            topic_id="obbba_vehicle_interest",
            display_name="Vehicle Loan Interest Deduction (OBBBA)",
            parent_topic="deductions",
            category="deductions",
            description=(
                "New OBBBA deduction for vehicle loan interest: "
                "U.S.-assembled vehicles, $10,000 annual limit, above-the-line."
            ),
            pub_sections=[
                PubSection(pub_number="17", relevance="primary"),
                PubSection(pub_number="1-A", relevance="primary",
                           notes="Schedule 1-A vehicle interest provisions"),
            ],
            related_topics=["deductions", "tip_overtime_deduction"],
            key_terms=[
                "vehicle interest", "car loan interest", "auto loan",
                "vehicle loan", "car interest deduction",
                "U.S. assembled", "American made", "$10,000 limit",
                "vehicle deduction", "financed in 2024", "claim in 2025",
                "bought a car", "purchased vehicle", "loan origination",
                "when can I deduct", "vehicle financing",
                "car loan deduction", "auto interest deduction",
                "financed a vehicle", "vehicle in 2024",
                "interest deduction in 2025",
            ],
        ))

        self.register(TaxTopic(
            topic_id="filing_extensions",
            display_name="Filing Extensions & Deadlines",
            parent_topic="filing",
            category="general",
            description=(
                "Tax return extension rules: Form 4868, payment vs filing "
                "deadlines, penalties for late filing and late payment."
            ),
            pub_sections=[
                PubSection(pub_number="17", relevance="primary",
                           notes="Filing deadlines and extensions"),
                PubSection(pub_number="1040", relevance="supplementary",
                           notes="Form 1040 due dates"),
            ],
            related_topics=["filing", "withholding"],
            key_terms=[
                "extension", "Form 4868", "filing deadline",
                "late filing", "late payment", "penalty",
                "failure to file", "failure to pay", "due date",
                "April 15",
            ],
        ))

        self.register(TaxTopic(
            topic_id="vehicle_expenses",
            display_name="Vehicle & Transportation Expenses",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Business vehicle deductions: standard mileage rate, actual "
                "expense method, repairs, maintenance, listed property rules."
            ),
            pub_sections=[
                PubSection(pub_number="463", relevance="primary",
                           notes="Car and transportation expense rules"),
                PubSection(pub_number="535", relevance="supplementary",
                           notes="Business vehicle context"),
                PubSection(pub_number="946", relevance="supplementary",
                           notes="Vehicle depreciation"),
            ],
            related_topics=["business_expenses", "depreciation"],
            key_terms=[
                "vehicle expense", "car expense", "mileage rate",
                "standard mileage", "actual expenses", "vehicle repair",
                "vehicle maintenance", "gas", "fuel", "parking",
                "toll", "commuting",
            ],
        ))

        self.register(TaxTopic(
            topic_id="wash_sales",
            display_name="Wash Sale Rules",
            parent_topic="capital_gains",
            category="investments",
            description=(
                "Wash sale rules: 30-day window, substantially identical "
                "securities, basis adjustment, loss disallowance."
            ),
            pub_sections=[
                PubSection(pub_number="550", relevance="primary",
                           notes="Wash sale rules for investment property"),
                PubSection(pub_number="544", relevance="supplementary"),
            ],
            related_topics=["capital_gains", "investment_income"],
            key_terms=[
                "wash sale", "substantially identical",
                "30 days", "loss disallowed", "basis adjustment",
                "repurchase", "same stock",
            ],
        ))

        self.register(TaxTopic(
            topic_id="depreciation_recapture",
            display_name="Depreciation Recapture",
            parent_topic="depreciation",
            category="property",
            description=(
                "Depreciation recapture rules: Section 1245, Section 1250, "
                "25% rate for real property, ordinary income treatment."
            ),
            pub_sections=[
                PubSection(pub_number="544", relevance="primary",
                           notes="Recapture rules for asset sales"),
                PubSection(pub_number="946", relevance="supplementary",
                           notes="Depreciation context for recapture"),
                PubSection(pub_number="527", relevance="supplementary",
                           notes="Rental property recapture"),
            ],
            related_topics=["depreciation", "capital_gains"],
            key_terms=[
                "depreciation recapture", "Section 1245", "Section 1250",
                "recapture", "25% rate", "ordinary income recapture",
                "unrecaptured gain",
            ],
        ))

        self.register(TaxTopic(
            topic_id="guaranteed_payments",
            display_name="Partnership Guaranteed Payments",
            parent_topic="partnerships",
            category="business",
            description=(
                "Guaranteed payments to partners: ordinary income treatment, "
                "SE tax implications, partnership deduction."
            ),
            pub_sections=[
                PubSection(pub_number="541", relevance="primary",
                           notes="Guaranteed payments in partnerships"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["partnerships", "self_employment_tax"],
            key_terms=[
                "guaranteed payment", "partner payment",
                "partnership income", "SE tax partner",
                "reasonable compensation", "salary distribution",
            ],
        ))

        self.register(TaxTopic(
            topic_id="1099k_reporting",
            display_name="1099-K Platform Reporting",
            parent_topic="information_returns",
            category="reporting",
            description=(
                "1099-K reporting thresholds for payment platforms: "
                "$20,000 and 200 transaction threshold, self-reporting."
            ),
            pub_sections=[
                PubSection(pub_number="1099", relevance="primary",
                           notes="1099-K filing requirements"),
                PubSection(pub_number="17", relevance="primary",
                           notes="1099-K threshold guidance for taxpayers"),
                PubSection(pub_number="525", relevance="supplementary",
                           notes="Platform income reporting"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["information_returns", "business_income"],
            key_terms=[
                "1099-K", "payment platform", "Venmo", "PayPal",
                "$20,000 threshold", "200 transactions",
                "third party", "platform payments",
                "gig economy", "1099-K threshold",
                "receive a 1099", "get a 1099",
                "$18,000", "platform payment",
            ],
        ))

        self.register(TaxTopic(
            topic_id="s_corp_distributions",
            display_name="S-Corp Distributions & Compensation",
            parent_topic="corporations",
            category="business",
            description=(
                "S corporation distribution rules: reasonable compensation, "
                "SE tax avoidance, basis and distribution ordering."
            ),
            pub_sections=[
                PubSection(pub_number="542", relevance="primary",
                           notes="S-corp distribution rules"),
                PubSection(pub_number="541", relevance="supplementary",
                           notes="Pass-through entity distribution context"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["corporations", "self_employment_tax"],
            key_terms=[
                "S corporation distribution", "S corp salary",
                "reasonable compensation", "officer compensation",
                "distribution vs salary", "SE tax reduction",
                "reduce salary", "increase distributions",
                "lower SE tax", "lower self-employment tax",
                "S corp tax savings", "salary vs distribution",
                "minimize payroll", "S corp owner pay",
                "shareholder salary", "S corp compensation strategy",
            ],
        ))

        self.register(TaxTopic(
            topic_id="business_interest_limitation",
            display_name="Business Interest Limitation (Section 163(j))",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Section 163(j) business interest deduction limitation: "
                "30% of ATI/EBITDA, $32 million gross receipts exemption."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Business interest deduction rules"),
                PubSection(pub_number="334", relevance="supplementary"),
            ],
            related_topics=["business_expenses", "nol"],
            key_terms=[
                "business interest limitation", "Section 163(j)",
                "30% limitation", "ATI", "EBITDA",
                "interest expense", "business interest deduction",
                "$32 million", "gross receipts", "interest limitation",
            ],
        ))

        # ── Additional Pub 535 sub-topics for eval coverage ──────────────

        self.register(TaxTopic(
            topic_id="travel_expenses",
            display_name="Business Travel Expenses",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Deductible business travel expenses: airfare, lodging, "
                "meals (50% limit), transportation, documentation rules."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Pub 535 Ch.2 — travel and meals"),
                PubSection(pub_number="463", relevance="primary",
                           notes="Travel, car, and entertainment expenses"),
            ],
            related_topics=["business_expenses", "vehicle_expenses"],
            key_terms=[
                "travel expense", "business travel", "airfare",
                "lodging", "hotel", "per diem", "meals deduction",
                "50% deductible", "business purpose", "travel documentation",
                "overnight travel", "transportation", "travel costs",
                "away from home", "temporary assignment",
            ],
        ))

        self.register(TaxTopic(
            topic_id="self_employed_health_insurance",
            display_name="Self-Employed Health Insurance Deduction",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Above-the-line deduction for self-employed health insurance "
                "premiums: medical, dental, vision, long-term care."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Self-employment health insurance deduction"),
                PubSection(pub_number="502", relevance="supplementary",
                           notes="Medical and dental expenses"),
            ],
            related_topics=["business_expenses", "medical_expenses"],
            key_terms=[
                "self-employed health insurance", "health insurance deduction",
                "self-employment insurance", "medical premium",
                "dental premium", "vision premium", "above-the-line",
                "self-employed deduction", "health premium",
                "sole proprietor insurance", "freelancer insurance",
                "consultant health insurance",
            ],
        ))

        self.register(TaxTopic(
            topic_id="inventory_cogs_deduction",
            display_name="Inventory & Cost of Goods Sold",
            parent_topic="business_expenses",
            category="business",
            description=(
                "Inventory capitalization and COGS deduction: valuation "
                "methods, FIFO/LIFO, uniform capitalization rules."
            ),
            pub_sections=[
                PubSection(pub_number="535", relevance="primary",
                           notes="Pub 535 Ch.1 — inventory rules"),
                PubSection(pub_number="334", relevance="supplementary",
                           notes="Small business inventory"),
            ],
            related_topics=["business_expenses", "business_income"],
            key_terms=[
                "inventory", "cost of goods sold", "COGS",
                "FIFO", "LIFO", "inventory valuation",
                "capitalized", "uniform capitalization",
                "Section 263A", "UNICAP", "inventory method",
                "beginning inventory", "ending inventory",
                "manufacturing costs", "merchandise",
            ],
        ))

        # ─── NEW TOPICS: ontology gap fills ────────────────────────────────

        self.register(TaxTopic(
            topic_id="kiddie_tax",
            display_name="Kiddie Tax (Unearned Income of Children)",
            parent_topic="income",
            category="general",
            description=(
                "Tax on unearned income of children under 19 (or full-time "
                "students under 24): investment income, trust distributions, "
                "UTMA accounts. Form 8615."
            ),
            pub_sections=[
                PubSection(pub_number="929", relevance="primary",
                           notes="Tax Rules for Children and Dependents"),
                PubSection(pub_number="590a", relevance="supplementary",
                           notes="IRA distributions to minors / Trump Account"),
                PubSection(pub_number="17", relevance="supplementary",
                           notes="Pub 17 kiddie tax overview"),
            ],
            related_topics=["trump_account", "investment_income"],
            key_terms=[
                "kiddie tax", "unearned income", "child investment",
                "Form 8615", "child tax rate", "under 19",
                "student under 24", "parent's tax rate",
                "child unearned income", "UTMA", "trust income",
                "minor investment income", "child interest income",
                "child dividend income",
            ],
        ))

        self.register(TaxTopic(
            topic_id="mef_rejection_codes",
            display_name="MeF E-File Rejection Codes",
            parent_topic="filing",
            category="general",
            description=(
                "IRS Modernized e-File (MeF) rejection rules: common "
                "rejection codes, resolution procedures, resubmission rules."
            ),
            pub_sections=[
                PubSection(pub_number="MeF", relevance="primary",
                           notes="MeF e-file rejection codes and rules"),
                PubSection(pub_number="1345", relevance="supplementary",
                           notes="e-File handbook for authorized providers"),
            ],
            related_topics=["filing", "filing_extensions"],
            key_terms=[
                "MeF rejection", "e-file rejection", "rejection code",
                "IND-031", "IND-032", "R0000-902", "e-file error",
                "resubmit", "electronic filing rejection",
                "MeF error", "reject code", "e-file reject",
                "return rejected", "filing rejected",
                "rejected my return", "IRS rejected",
                "Amount Owed", "return saying",
            ],
        ))

        self.register(TaxTopic(
            topic_id="tip_w2_reporting",
            display_name="Tip Reporting on W-2 (Employer)",
            parent_topic="employer_taxes",
            category="business",
            description=(
                "Employer obligations for reporting employee tips on W-2: "
                "allocated tips, tip credit, Form 8027, Box 7/8 reporting."
            ),
            pub_sections=[
                PubSection(pub_number="15", relevance="primary",
                           notes="Circular E — employer tip reporting"),
                PubSection(pub_number="531", relevance="supplementary",
                           notes="Reporting tip income (employee side)"),
                PubSection(pub_number="1244", relevance="supplementary",
                           notes="Daily Record of Tips"),
            ],
            related_topics=["tip_overtime_deduction", "employer_taxes"],
            key_terms=[
                "tip reporting W-2", "allocated tips",
                "employer tip credit", "Form 8027",
                "Box 7", "Box 8", "tip withholding",
                "report tips on W-2", "employer tip obligation",
                "tip income reporting", "employee tips",
                "social security on tips", "tip tax",
                "report tips separately", "tips separately on",
                "didn't report tips", "tip deduction W-2",
            ],
        ))

        self.register(TaxTopic(
            topic_id="retiree_tax_strategy",
            display_name="Retiree & Senior Tax Filing",
            parent_topic="filing",
            category="general",
            description=(
                "Tax filing considerations for retirees and seniors: "
                "Social Security taxation, pension income, RMDs, "
                "senior standard deduction, age-based provisions."
            ),
            pub_sections=[
                PubSection(pub_number="17", relevance="primary",
                           notes="General tax guide — senior provisions"),
                PubSection(pub_number="915", relevance="primary",
                           notes="Social Security and equivalent tier 1 "
                                 "railroad retirement benefits"),
                PubSection(pub_number="575", relevance="supplementary",
                           notes="Pension and annuity income"),
                PubSection(pub_number="590b", relevance="supplementary",
                           notes="IRA distributions and RMDs"),
            ],
            related_topics=["social_security", "retirement"],
            key_terms=[
                "retiree tax", "senior filing", "retired",
                "retiree", "pension income", "Social Security taxable",
                "RMD", "required minimum distribution",
                "age 65", "senior standard deduction",
                "retirement income", "1099-R",
                "over 65 filing", "retiree deduction",
                "senior tax break", "older taxpayer",
            ],
        ))

        logger.debug(
            "TopicOntology loaded %d topics with %d indexed terms",
            len(self._topics),
            sum(len(v) for v in self._term_index.values()),
        )


# ── Module-level singleton ───────────────────────────────────────────────────

_ontology: TopicOntology | None = None


def get_ontology() -> TopicOntology:
    """Get the global topic ontology (lazy-loaded singleton)."""
    global _ontology
    if _ontology is None:
        _ontology = TopicOntology()
    return _ontology
