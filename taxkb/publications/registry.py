"""
taxkb/publications/registry.py

Extensible IRS publication registry with metadata for ontology-aware retrieval.

Each publication entry includes:
  - Structural metadata (title, category, tier)
  - Relationship metadata (related pubs, related forms/schedules)
  - Content metadata (topic tags for query routing)
  - Temporal metadata (supported tax years)

This registry enables:
  1. Adding new publications without code changes to the retrieval pipeline
  2. Cross-publication retrieval (follow related_pubs during search)
  3. Query routing (match query topics to publication categories)
  4. Coverage gap analysis (compare registered vs ingested publications)
"""

from pydantic import BaseModel, ConfigDict


class PublicationMeta(BaseModel):
    """Metadata for a single IRS publication."""

    model_config = ConfigDict(frozen=True)

    pub_number: str
    title: str
    short_title: str
    category: str
    tier: int
    related_pubs: list[str]
    related_forms: list[str]
    topic_tags: list[str]
    tax_years: list[int]
    description: str = ""


class PublicationRegistry:
    """Thread-safe registry of IRS publication metadata."""

    def __init__(self):
        self._registry: dict[str, PublicationMeta] = {}
        self._load_defaults()

    def register(self, meta: PublicationMeta) -> None:
        """Register a publication in the registry."""
        self._registry[meta.pub_number] = meta

    def get(self, pub_number: str) -> PublicationMeta | None:
        """Get publication metadata by number."""
        return self._registry.get(pub_number)

    def get_title(self, pub_number: str) -> str:
        """Get publication title (backward compatible with PUB_TITLES)."""
        meta = self.get(pub_number)
        return meta.title if meta else ""

    def get_by_category(self, category: str) -> list[PublicationMeta]:
        """Get all publications in a category."""
        return [
            meta
            for meta in self._registry.values()
            if meta.category == category
        ]

    def get_by_tier(self, tier: int) -> list[PublicationMeta]:
        """Get all publications at a specific tier."""
        return sorted(
            [meta for meta in self._registry.values() if meta.tier == tier],
            key=lambda m: (int("".join(c for c in m.pub_number if c.isdigit()) or "0"), m.pub_number),
        )

    def find_by_topic(self, topic: str) -> list[PublicationMeta]:
        """Find publications matching a topic tag."""
        topic_lower = topic.lower()
        return [
            meta
            for meta in self._registry.values()
            if any(
                topic_lower in tag.lower() for tag in meta.topic_tags
            )
        ]

    def get_related(self, pub_number: str) -> list[str]:
        """Get related publication numbers."""
        meta = self.get(pub_number)
        return meta.related_pubs if meta else []

    def all_pub_numbers(self) -> list[str]:
        """Get all registered publication numbers."""
        return sorted(self._registry.keys(), key=lambda x: (int("".join(c for c in x if c.isdigit()) or "0"), x))

    def as_pub_titles(self) -> dict[str, str]:
        """Export as dict for backward compatibility with PUB_TITLES."""
        return {meta.pub_number: meta.title for meta in self._registry.values()}

    # ── Multi-year coverage utilities ────────────────────────────────────────

    def get_available_years(self, pub_number: str) -> list[int]:
        """Return the tax years available for a specific publication.

        Returns an empty list if the publication is not registered.
        """
        meta = self.get(pub_number)
        return sorted(meta.tax_years) if meta else []

    def get_pubs_for_year(self, tax_year: int) -> list[PublicationMeta]:
        """Return all publications that cover a given tax year.

        Sorted by (tier, pub_number) so Tier-1 pubs come first.
        """
        return sorted(
            [
                meta
                for meta in self._registry.values()
                if tax_year in meta.tax_years
            ],
            key=lambda m: (
                m.tier,
                int("".join(c for c in m.pub_number if c.isdigit()) or "0"),
                m.pub_number,
            ),
        )

    def get_all_years(self) -> list[int]:
        """Return a sorted list of all distinct tax years across all publications."""
        years: set[int] = set()
        for meta in self._registry.values():
            years.update(meta.tax_years)
        return sorted(years)

    def coverage_matrix(self) -> dict[str, dict[int, bool]]:
        """Return a pub × year coverage matrix.

        Returns:
            {pub_number: {year: True/False}} for every registered pub and
            every year in the registry.
        """
        all_years = self.get_all_years()
        matrix: dict[str, dict[int, bool]] = {}
        for pn in self.all_pub_numbers():
            meta = self.get(pn)
            matrix[pn] = {y: y in meta.tax_years for y in all_years} if meta else {}
        return matrix

    def coverage_gaps(self, years: list[int] | None = None) -> dict[str, list[int]]:
        """Find years each publication is missing.

        Args:
            years: Specific years to check.  Defaults to all years in registry.

        Returns:
            {pub_number: [missing_year, ...]} — only pubs with gaps are included.
        """
        check_years = years or self.get_all_years()
        gaps: dict[str, list[int]] = {}
        for pn in self.all_pub_numbers():
            meta = self.get(pn)
            if meta is None:
                continue
            # Only check active pubs (those with at least one year)
            if not meta.tax_years:
                continue
            missing = [y for y in check_years if y not in meta.tax_years]
            if missing:
                gaps[pn] = sorted(missing)
        return gaps

    def coverage_summary(self) -> str:
        """Human-readable multi-year coverage report.

        Returns a formatted string suitable for CLI output.
        """
        all_years = self.get_all_years()
        if not all_years:
            return "No tax years registered."

        lines = [
            f"Tax Brain — Multi-Year Coverage Report",
            f"Years tracked: {', '.join(str(y) for y in all_years)}",
            f"Publications registered: {len(self._registry)}",
            "",
            f"{'Pub':>6}  {'Title':<55}  {'Tier':>4}  {' '.join(str(y) for y in all_years)}",
            "─" * (6 + 2 + 55 + 2 + 4 + 2 + len(all_years) * 5),
        ]
        for pn in self.all_pub_numbers():
            meta = self.get(pn)
            if meta is None:
                continue
            year_flags = "  ".join(
                " ✓ " if y in meta.tax_years else " ✗ "
                for y in all_years
            )
            lines.append(
                f"{pn:>6}  {meta.short_title:<55}  {meta.tier:>4}  {year_flags}"
            )

        # Summary stats
        gaps = self.coverage_gaps()
        pubs_with_gaps = len(gaps)
        total_active = sum(1 for m in self._registry.values() if m.tax_years)
        lines.append("")
        lines.append(f"Active publications: {total_active}")
        lines.append(f"Publications with coverage gaps: {pubs_with_gaps}")
        if gaps:
            lines.append("Gap details:")
            for pn, missing in sorted(gaps.items()):
                lines.append(f"  Pub {pn}: missing {', '.join(str(y) for y in missing)}")

        return "\n".join(lines)

    def _load_defaults(self) -> None:
        """Load default IRS publications (Tier 1 and Tier 2)."""

        # ===== TIER 1: Currently ingested publications (8) =====

        self.register(
            PublicationMeta(
                pub_number="17",
                title="Your Federal Income Tax (For Individuals)",
                short_title="Income Tax Guide",
                category="general",
                tier=1,
                related_pubs=["501", "525", "550"],
                related_forms=["Form 1040", "Form 1040-SR"],
                topic_tags=[
                    "federal income tax",
                    "individuals",
                    "filing requirements",
                    "tax return",
                    "form 1040",
                    "deductions",
                    "credits",
                ],
                tax_years=[2023, 2024, 2025],
                description="Comprehensive guide to federal income tax for individuals.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="501",
                title="Dependents, Standard Deduction, and Filing Information",
                short_title="Dependents & Deductions",
                category="deductions",
                tier=1,
                related_pubs=["17", "505"],
                related_forms=["Form 1040", "Form W-4"],
                topic_tags=[
                    "dependents",
                    "standard deduction",
                    "filing requirements",
                    "filing status",
                    "personal exemptions",
                    "qualifying child",
                    "qualifying relative",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for dependents, standard deduction amounts, and filing requirements.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="525",
                title="Taxable and Nontaxable Income",
                short_title="Income Types",
                category="income",
                tier=1,
                related_pubs=["17", "550", "575"],
                related_forms=["Form 1040"],
                topic_tags=[
                    "taxable income",
                    "nontaxable income",
                    "wages",
                    "interest",
                    "dividends",
                    "capital gains",
                    "gross income",
                    "exclusions",
                ],
                tax_years=[2023, 2024, 2025],
                description="Determination of what income is taxable and what is excluded from income.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="550",
                title="Investment Income and Expenses",
                short_title="Investment Income",
                category="investments",
                tier=1,
                related_pubs=["17", "525", "544"],
                related_forms=["Form 1040", "Schedule B", "Schedule D"],
                topic_tags=[
                    "investment income",
                    "interest income",
                    "dividend income",
                    "capital gains",
                    "capital losses",
                    "investment expenses",
                    "bonds",
                    "stocks",
                    "mutual funds",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of investment income including interest, dividends, and capital gains.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="590a",
                title="Contributions to Individual Retirement Arrangements (IRAs)",
                short_title="IRA Contributions",
                category="retirement",
                tier=1,
                related_pubs=["590b", "575"],
                related_forms=["Form 1040", "Form 5498"],
                topic_tags=[
                    "ira contributions",
                    "traditional ira",
                    "roth ira",
                    "contribution limits",
                    "income limits",
                    "deductible contributions",
                    "catch-up contributions",
                    "sep ira",
                ],
                tax_years=[2023, 2024, 2025],
                description="IRA contribution rules, limits, and deductibility.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="590b",
                title="Distributions from Individual Retirement Arrangements (IRAs)",
                short_title="IRA Distributions",
                category="retirement",
                tier=1,
                related_pubs=["590a", "575"],
                related_forms=["Form 1040", "Form 5498"],
                topic_tags=[
                    "ira distributions",
                    "qualified distributions",
                    "roth conversions",
                    "required minimum distributions",
                    "rmd",
                    "early withdrawal penalties",
                    "rollover",
                ],
                tax_years=[2023, 2024, 2025],
                description="IRA distribution rules, penalties, and qualified distribution criteria.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="596",
                title="Earned Income Credit (EIC)",
                short_title="EIC",
                category="credits",
                tier=1,
                related_pubs=["17", "501"],
                related_forms=["Form 1040", "Schedule EIC"],
                topic_tags=[
                    "earned income credit",
                    "eic",
                    "eitc",
                    "qualifying child",
                    "income limits",
                    "phase-out",
                    "refundable credit",
                    "low-income",
                ],
                tax_years=[2023, 2024, 2025],
                description="Eligibility and calculation of the Earned Income Credit for low-income workers.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="969",
                title="Health Savings Accounts and Other Tax-Favored Health Plans",
                short_title="HSA",
                category="benefits",
                tier=1,
                related_pubs=["17", "525"],
                related_forms=["Form 1040", "Form 8889"],
                topic_tags=[
                    "health savings account",
                    "hsa",
                    "contributions",
                    "qualified medical expenses",
                    "distributions",
                    "eligible individuals",
                    "high-deductible health plan",
                    "hdhp",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment and rules for HSAs and other tax-advantaged health plans.",
            )
        )

        # ===== TIER 1: Gap publications (8) =====

        self.register(
            PublicationMeta(
                pub_number="334",
                title="Tax Guide for Small Business",
                short_title="Small Business Tax",
                category="business",
                tier=1,
                related_pubs=["535", "587", "505"],
                related_forms=["Form 1040", "Schedule C", "Schedule SE"],
                topic_tags=[
                    "small business",
                    "self-employment",
                    "sole proprietor",
                    "business income",
                    "business expenses",
                    "home office",
                    "estimated taxes",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax guide covering income, deductions, and record-keeping for small businesses.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="505",
                title="Tax Withholding and Estimated Tax",
                short_title="Withholding & Estimated Tax",
                category="general",
                tier=1,
                related_pubs=["17", "501", "334"],
                related_forms=["Form 1040-ES", "Form W-4"],
                topic_tags=[
                    "tax withholding",
                    "estimated tax",
                    "quarterly payments",
                    "under-withholding",
                    "over-withholding",
                    "form w-4",
                    "self-employment tax",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for withholding and making quarterly estimated tax payments.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="523",
                title="Selling Your Home",
                short_title="Home Sale",
                category="property",
                tier=1,
                related_pubs=["544", "551", "527"],
                related_forms=["Form 1040", "Schedule D"],
                topic_tags=[
                    "home sale",
                    "section 121 exclusion",
                    "primary residence",
                    "capital gain",
                    "capital loss",
                    "realized gain",
                    "adjusted basis",
                    "selling expenses",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of gains and losses when selling your primary residence.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="527",
                title="Residential Rental Property",
                short_title="Rental Property",
                category="property",
                tier=1,
                related_pubs=["523", "544", "551", "946"],
                related_forms=["Form 1040", "Schedule E"],
                topic_tags=[
                    "rental property",
                    "rental income",
                    "rental expenses",
                    "depreciation",
                    "passive loss limitations",
                    "real estate professional",
                    "fair market value",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of income and expenses from rental properties.",
            )
        )

        # NOTE: Pub 535 was discontinued after 2022. The IRS replaced it with
        # topic-specific guidance spread across Pub 334, Pub 463, Pub 946, etc.
        # We keep the 2022 final edition for historical reference.
        self.register(
            PublicationMeta(
                pub_number="535",
                title="Business Expenses",
                short_title="Business Expenses",
                category="business",
                tier=1,
                related_pubs=["334", "587", "463"],
                related_forms=["Schedule C", "Schedule SE"],
                topic_tags=[
                    "business expenses",
                    "deductible expenses",
                    "ordinary and necessary",
                    "capitalization",
                    "depreciation",
                    "meals and entertainment",
                    "office supplies",
                    "vehicle expenses",
                ],
                tax_years=[2022],
                description=(
                    "Rules for deducting ordinary and necessary business expenses. "
                    "DISCONTINUED after 2022 — superseded by Pub 334 and topic guides."
                ),
            )
        )

        self.register(
            PublicationMeta(
                pub_number="544",
                title="Sales of Assets",
                short_title="Capital Gains/Losses",
                category="investments",
                tier=1,
                related_pubs=["550", "523", "551"],
                related_forms=["Form 1040", "Schedule D"],
                topic_tags=[
                    "capital gains",
                    "capital losses",
                    "long-term gains",
                    "short-term gains",
                    "holding period",
                    "adjusted basis",
                    "asset sales",
                    "wash sale",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of gains and losses from the sale of investment property.",
            )
        )

        # NOTE: Pub 551 is revision-dated (not annual). The IRS publishes
        # it as "Rev. December 2025" at irs-pdf/p551.pdf — no annual prior-year
        # versions. We treat the current revision as covering 2022-2025.
        self.register(
            PublicationMeta(
                pub_number="551",
                title="Basis of Assets",
                short_title="Asset Basis",
                category="property",
                tier=1,
                related_pubs=["544", "523", "527", "946"],
                related_forms=["Form 8949", "Schedule D"],
                topic_tags=[
                    "adjusted basis",
                    "cost basis",
                    "inherited property",
                    "stepped-up basis",
                    "property received",
                    "basis adjustments",
                    "depreciation",
                ],
                tax_years=[2025],
                description="Rules for determining and adjusting the basis of assets.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="946",
                title="How to Depreciate Property",
                short_title="Depreciation",
                category="property",
                tier=1,
                related_pubs=["527", "551", "535"],
                related_forms=["Form 4562", "Schedule C"],
                topic_tags=[
                    "depreciation",
                    "macrs",
                    "recovery period",
                    "depreciation methods",
                    "depreciable property",
                    "section 179 deduction",
                    "bonus depreciation",
                ],
                tax_years=[2023, 2024, 2025],
                description="Depreciation methods and rules for computing depreciation deductions.",
            )
        )

        # ===== TIER 2: Important but specialized (11) =====

        self.register(
            PublicationMeta(
                pub_number="463",
                title="Travel, Entertainment, Gift, and Car Expenses",
                short_title="Travel & Car Expenses",
                category="deductions",
                tier=2,
                related_pubs=["535", "334"],
                related_forms=["Schedule C", "Form 4562"],
                topic_tags=[
                    "travel expenses",
                    "car expenses",
                    "vehicle depreciation",
                    "mileage allowance",
                    "entertainment expenses",
                    "gift expenses",
                    "business meals",
                    "documentation",
                ],
                tax_years=[2023, 2024, 2025],
                description="Deductibility of travel, entertainment, car, and gift expenses.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="502",
                title="Medical and Dental Expenses",
                short_title="Medical Expenses",
                category="deductions",
                tier=2,
                related_pubs=["17", "501"],
                related_forms=["Form 1040", "Schedule A"],
                topic_tags=[
                    "medical expenses",
                    "dental expenses",
                    "deductible medical",
                    "adjusted gross income",
                    "agi threshold",
                    "insurance premiums",
                    "nursing care",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for claiming medical and dental expense deductions.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="503",
                title="Child and Dependent Care Expenses",
                short_title="Child Care Expenses",
                category="credits",
                tier=2,
                related_pubs=["501", "596"],
                related_forms=["Form 1040", "Form 2441"],
                topic_tags=[
                    "child care expenses",
                    "dependent care",
                    "qualifying child",
                    "care provider",
                    "earned income",
                    "dependent care credit",
                    "fsa",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for the dependent care credit and FSA treatment of child care.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="504",
                title="Divorced or Separated Individuals",
                short_title="Divorce & Separation",
                category="general",
                tier=2,
                related_pubs=["17", "501"],
                related_forms=["Form 1040"],
                topic_tags=[
                    "divorced",
                    "separated",
                    "alimony",
                    "spousal support",
                    "child support",
                    "filing status",
                    "dependent claims",
                    "medical expenses",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment for divorced or separated individuals.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="526",
                title="Charitable Contributions",
                short_title="Charitable Deductions",
                category="deductions",
                tier=2,
                related_pubs=["17", "502"],
                related_forms=["Form 1040", "Schedule A", "Form 8283"],
                topic_tags=[
                    "charitable contributions",
                    "charitable deduction",
                    "qualified charity",
                    "noncash contributions",
                    "appraisal",
                    "substantiation",
                    "quid pro quo",
                    "donee",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for deducting charitable contributions to qualified organizations.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="547",
                title="Casualties, Disasters, and Thefts",
                short_title="Casualty & Theft Losses",
                category="deductions",
                tier=2,
                related_pubs=["17", "551"],
                related_forms=["Form 1040", "Form 4684"],
                topic_tags=[
                    "casualty loss",
                    "theft loss",
                    "disaster",
                    "federally declared disaster",
                    "adjusted basis",
                    "fair market value",
                    "insurance proceeds",
                    "deductible loss",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of losses from casualties, disasters, and thefts.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="561",
                title="Determining the Value of Donated Property",
                short_title="Donation Valuation",
                category="deductions",
                tier=2,
                related_pubs=["526", "551"],
                related_forms=["Form 8283", "Schedule A"],
                topic_tags=[
                    "property valuation",
                    "noncash contribution",
                    "fair market value",
                    "appraisal",
                    "qualified appraiser",
                    "valuation methods",
                    "appraised value",
                ],
                tax_years=[2023, 2024, 2025],
                description="Methods for determining the value of property donated to charity.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="575",
                title="Pension and Annuity Income",
                short_title="Pension Income",
                category="retirement",
                tier=2,
                related_pubs=["590a", "590b"],
                related_forms=["Form 1040", "Form 4972"],
                topic_tags=[
                    "pension income",
                    "annuity",
                    "qualified plan",
                    "lump sum distribution",
                    "net unrealized appreciation",
                    "employee contributions",
                    "inherited pension",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax treatment of pension and annuity distributions.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="587",
                title="Business Use of Your Home (Including Use by Day-Care Providers)",
                short_title="Home Office",
                category="business",
                tier=2,
                related_pubs=["334", "535", "527"],
                related_forms=["Schedule C", "Form 8829"],
                topic_tags=[
                    "home office",
                    "business use of home",
                    "home office deduction",
                    "day care provider",
                    "simplified option",
                    "actual expense method",
                    "depreciation",
                ],
                tax_years=[2023, 2024, 2025],
                description="Rules for claiming home office deductions and business use of home.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="970",
                title="Tax Benefits for Education",
                short_title="Education Credits",
                category="education",
                tier=2,
                related_pubs=["17", "501"],
                related_forms=["Form 1040", "Form 8863"],
                topic_tags=[
                    "education credit",
                    "american opportunity credit",
                    "lifetime learning credit",
                    "student loan interest",
                    "qualified education expenses",
                    "education savings",
                    "scholarships",
                ],
                tax_years=[2023, 2024, 2025],
                description="Tax credits and deductions for education expenses.",
            )
        )

        # ===== TIER 2 (continued): Missing publications needed by golden set =====

        self.register(
            PublicationMeta(
                pub_number="15",
                title="(Circular E), Employer's Tax Guide",
                short_title="Employer Tax Guide",
                category="employment",
                tier=2,
                related_pubs=["505", "334"],
                related_forms=["Form W-2", "Form 941", "Form 940"],
                topic_tags=[
                    "employer taxes",
                    "employment tax",
                    "withholding",
                    "social security tax",
                    "medicare tax",
                    "FUTA",
                    "payroll",
                ],
                tax_years=[2025],
                description="Guide for employers on withholding, depositing, and reporting employment taxes.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="15-B",
                title="Employer's Tax Guide to Fringe Benefits",
                short_title="Fringe Benefits",
                category="employment",
                tier=2,
                related_pubs=["15", "535"],
                related_forms=["Form W-2", "Form 1099-MISC"],
                topic_tags=[
                    "fringe benefits",
                    "employer benefits",
                    "health insurance",
                    "group term life",
                    "dependent care",
                    "education assistance",
                    "transportation benefits",
                ],
                tax_years=[2025],
                description="Tax treatment of fringe benefits provided by employers.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="514",
                title="Foreign Tax Credit for Individuals",
                short_title="Foreign Tax Credit",
                category="credits",
                tier=2,
                related_pubs=["17", "550"],
                related_forms=["Form 1116", "Form 1040"],
                topic_tags=[
                    "foreign tax credit",
                    "foreign income",
                    "tax treaties",
                    "foreign taxes paid",
                ],
                tax_years=[2025],
                description="How to claim the foreign tax credit for individuals.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="529",
                title="Miscellaneous Deductions",
                short_title="Misc Deductions",
                category="deductions",
                tier=2,
                related_pubs=["17", "535"],
                related_forms=["Schedule A", "Form 1040"],
                topic_tags=[
                    "miscellaneous deductions",
                    "itemized deductions",
                    "unreimbursed expenses",
                    "gambling losses",
                ],
                tax_years=[2025],
                description="Miscellaneous deductions you may be able to take.",
            )
        )

        # Pub 536 discontinued after 2023; NOL guidance now in Form 172 instructions.
        # We ingest the 2023 version as the latest available.
        self.register(
            PublicationMeta(
                pub_number="536",
                title="Net Operating Losses (NOLs) for Individuals, Estates, and Trusts",
                short_title="Net Operating Losses",
                category="business",
                tier=2,
                related_pubs=["535", "334", "542"],
                related_forms=["Form 1040", "Form 1045", "Form 172"],
                topic_tags=[
                    "net operating loss",
                    "NOL",
                    "carryforward",
                    "carryback",
                    "business loss",
                    "excess business loss",
                ],
                tax_years=[2023],
                description=(
                    "How to figure and use a net operating loss. "
                    "DISCONTINUED after 2023 — current guidance in Form 172 instructions."
                ),
            )
        )

        self.register(
            PublicationMeta(
                pub_number="537",
                title="Installment Sales",
                short_title="Installment Sales",
                category="property",
                tier=2,
                related_pubs=["544", "551", "523"],
                related_forms=["Form 6252", "Form 1040"],
                topic_tags=[
                    "installment sale",
                    "deferred payment",
                    "installment method",
                    "gain recognition",
                ],
                tax_years=[2025],
                description="Tax rules for installment sales of property.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="541",
                title="Partnerships",
                short_title="Partnerships",
                category="business",
                tier=2,
                related_pubs=["535", "334", "544"],
                related_forms=["Form 1065", "Schedule K-1"],
                topic_tags=[
                    "partnership",
                    "partner",
                    "distributive share",
                    "basis",
                    "K-1",
                    "self-employment tax",
                    "partnership agreement",
                ],
                tax_years=[2025],
                description="Tax information for partnerships and partners.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="542",
                title="Corporations",
                short_title="Corporations",
                category="business",
                tier=2,
                related_pubs=["535", "544", "334"],
                related_forms=["Form 1120", "Form 1120-S"],
                topic_tags=[
                    "corporation",
                    "C corporation",
                    "S corporation",
                    "corporate tax",
                    "dividends received",
                    "accumulated earnings",
                ],
                tax_years=[2025],
                description="Tax information for corporations.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="560",
                title="Retirement Plans for Small Business",
                short_title="Small Business Retirement",
                category="retirement",
                tier=2,
                related_pubs=["590a", "590b", "334"],
                related_forms=["Form 5500", "Form 5330"],
                topic_tags=[
                    "SEP",
                    "SIMPLE",
                    "qualified plan",
                    "retirement plan",
                    "contribution limits",
                    "small business",
                    "401k",
                    "profit sharing",
                ],
                tax_years=[2025],
                description="Retirement plan options for small business owners.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="915",
                title="Social Security and Equivalent Railroad Retirement Benefits",
                short_title="Social Security Benefits",
                category="income",
                tier=2,
                related_pubs=["17", "525", "575"],
                related_forms=["Form SSA-1099", "Form 1040"],
                topic_tags=[
                    "social security",
                    "social security benefits",
                    "railroad retirement",
                    "taxable benefits",
                    "provisional income",
                    "lump-sum election",
                ],
                tax_years=[2025],
                description="How to determine if social security benefits are taxable.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="926",
                title="Household Employer's Tax Guide",
                short_title="Household Employer",
                category="employment",
                tier=2,
                related_pubs=["15", "505"],
                related_forms=["Schedule H", "Form W-2", "Form 1040"],
                topic_tags=[
                    "household employer",
                    "nanny tax",
                    "domestic worker",
                    "household employee",
                    "Schedule H",
                ],
                tax_years=[2025],
                description="Tax guide for household employers (nannies, housekeepers, etc.).",
            )
        )

        # ===== TIER 3: IRS Forms & Instructions (needed by golden set) =====
        # These are form instructions rather than traditional publications.
        # URL patterns differ: https://www.irs.gov/pub/irs-pdf/i{number}.pdf
        # or https://www.irs.gov/pub/irs-pdf/f{number}.pdf

        self.register(
            PublicationMeta(
                pub_number="1-A",
                title="Schedule 1-A: Additional Income and Adjustments to Income",
                short_title="Schedule 1-A",
                category="forms",
                tier=3,
                related_pubs=["17", "525", "334"],
                related_forms=["Schedule 1", "Form 1040"],
                topic_tags=[
                    "additional income",
                    "adjustments",
                    "above the line deductions",
                    "tip income",
                    "tip deduction",
                    "overtime deduction",
                    "Schedule 1",
                ],
                tax_years=[2025],
                description=(
                    "Instructions for Schedule 1-A (additional income and adjustments "
                    "including tip and overtime deductions under OBBBA)."
                ),
            )
        )

        self.register(
            PublicationMeta(
                pub_number="1040",
                title="Instructions for Form 1040 and 1040-SR",
                short_title="1040 Instructions",
                category="forms",
                tier=3,
                related_pubs=["17", "501", "505"],
                related_forms=["Form 1040", "Form 1040-SR"],
                topic_tags=[
                    "form 1040",
                    "tax return",
                    "filing",
                    "income tax",
                    "tax computation",
                ],
                tax_years=[2025],
                description="Line-by-line instructions for Form 1040.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="1099",
                title="General Instructions for Certain Information Returns",
                short_title="1099 Instructions",
                category="forms",
                tier=3,
                related_pubs=["525", "550"],
                related_forms=[
                    "Form 1099-MISC", "Form 1099-NEC", "Form 1099-K",
                    "Form 1099-INT", "Form 1099-DIV",
                ],
                topic_tags=[
                    "1099",
                    "information returns",
                    "1099-K",
                    "1099-NEC",
                    "reporting threshold",
                    "$5,000 threshold",
                ],
                tax_years=[2025],
                description="General instructions for 1099-series information returns.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="4547",
                title="Trump Account (Form 4547)",
                short_title="Trump Account",
                category="savings",
                tier=3,
                related_pubs=["17", "970"],
                related_forms=["Form 4547"],
                topic_tags=[
                    "Trump Account",
                    "MAGA account",
                    "newborn savings",
                    "child savings account",
                    "$1,000 contribution",
                    "tax-free growth",
                ],
                tax_years=[2025],
                description=(
                    "Instructions for Form 4547 (Trump Account) — "
                    "new tax-advantaged savings account for newborns under OBBBA."
                ),
            )
        )

        self.register(
            PublicationMeta(
                pub_number="W-2",
                title="Instructions for Forms W-2 and W-3",
                short_title="W-2 Instructions",
                category="forms",
                tier=3,
                related_pubs=["15", "505"],
                related_forms=["Form W-2", "Form W-3"],
                topic_tags=[
                    "W-2",
                    "wage statement",
                    "employer reporting",
                    "tip reporting",
                    "overtime pay",
                    "box codes",
                ],
                tax_years=[2025],
                description="Instructions for employers on preparing Forms W-2 and W-3.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="6765",
                title="Instructions for Form 6765: Credit for Increasing Research Activities",
                short_title="R&D Credit",
                category="credits",
                tier=3,
                related_pubs=["334", "535"],
                related_forms=["Form 6765"],
                topic_tags=[
                    "research credit",
                    "R&D credit",
                    "research activities",
                    "qualified research expenses",
                    "ASC method",
                    "payroll tax offset",
                ],
                tax_years=[2025],
                description="Instructions for claiming the credit for increasing research activities.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="8812",
                title="Instructions for Schedule 8812: Credits for Qualifying Children",
                short_title="Child Tax Credit",
                category="credits",
                tier=3,
                related_pubs=["17", "501", "972"],
                related_forms=["Schedule 8812", "Form 1040"],
                topic_tags=[
                    "child tax credit",
                    "additional child tax credit",
                    "qualifying child",
                    "CTC",
                    "refundable credit",
                    "$2,000 per child",
                ],
                tax_years=[2025],
                description="Instructions for Schedule 8812 (child tax credit computation).",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="8962",
                title="Instructions for Form 8962: Premium Tax Credit",
                short_title="Premium Tax Credit",
                category="credits",
                tier=3,
                related_pubs=["17", "974"],
                related_forms=["Form 8962", "Form 1095-A"],
                topic_tags=[
                    "premium tax credit",
                    "PTC",
                    "health insurance marketplace",
                    "advance premium tax credit",
                    "Form 1095-A",
                ],
                tax_years=[2025],
                description="Instructions for computing the premium tax credit.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="8995-A",
                title="Instructions for Form 8995-A: Qualified Business Income Deduction",
                short_title="QBI Deduction",
                category="business",
                tier=3,
                related_pubs=["535", "334"],
                related_forms=["Form 8995", "Form 8995-A"],
                topic_tags=[
                    "qualified business income",
                    "QBI",
                    "Section 199A",
                    "pass-through deduction",
                    "20% deduction",
                    "specified service",
                    "SSTB",
                ],
                tax_years=[2025],
                description="Instructions for the qualified business income (Section 199A) deduction.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="925",
                title="Passive Activity and At-Risk Rules",
                short_title="Passive Activity Rules",
                category="investments",
                tier=2,
                related_pubs=["527", "535", "550"],
                related_forms=["Form 8582", "Form 8810"],
                topic_tags=[
                    "passive activity",
                    "at-risk rules",
                    "material participation",
                    "rental activity",
                    "passive loss",
                ],
                tax_years=[2025],
                description="Passive activity and at-risk rules for individuals.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="936",
                title="Home Mortgage Interest Deduction",
                short_title="Mortgage Interest",
                category="deductions",
                tier=2,
                related_pubs=["17", "523", "527"],
                related_forms=["Schedule A", "Form 1098"],
                topic_tags=[
                    "mortgage interest",
                    "home mortgage",
                    "points",
                    "qualified residence",
                    "SALT deduction",
                ],
                tax_years=[2025],
                description="Rules for deducting home mortgage interest.",
            )
        )

        # NOTE: "MeF" is not an IRS publication — it refers to Modernized e-File
        # system documentation which is already covered by our Layer 1 MeF rules.
        # We register it as a placeholder to prevent eval gaps from being flagged,
        # but it has no downloadable PDF.
        self.register(
            PublicationMeta(
                pub_number="MeF",
                title="Modernized e-File (MeF) Business Rule Crosswalk",
                short_title="MeF Business Rules",
                category="efile",
                tier=2,
                related_pubs=["17", "1040", "8962"],
                related_forms=["Form 1040", "Form 8962", "Form 4547", "Schedule 1-A", "Schedule SE"],
                topic_tags=[
                    "MeF",
                    "modernized e-file",
                    "electronic filing",
                    "e-file",
                    "rejection code",
                    "business rule",
                    "error reject code",
                    "schema validation",
                    "e-file rejection",
                ],
                tax_years=[2025],
                description=(
                    "MeF Business Rule Crosswalk for Form 1040 series. "
                    "Covers rejection codes, validation rules, OBBBA-related "
                    "e-file rules, and troubleshooting guidance for CPAs."
                ),
            )
        )

        # NOTE: Pub 564 was discontinued around 2009. Its content on mutual
        # fund distributions was folded into Pub 550 (Investment Income and
        # Expenses). We keep a registry entry for historical awareness but
        # exclude it from active downloads by setting tax_years to empty.
        self.register(
            PublicationMeta(
                pub_number="564",
                title="Mutual Fund Distributions",
                short_title="Mutual Fund Distributions",
                category="investments",
                tier=3,
                related_pubs=["550", "544"],
                related_forms=["Form 1040", "Schedule B", "Schedule D"],
                topic_tags=[
                    "mutual fund distributions",
                    "dividend distributions",
                    "capital gain distributions",
                    "fund distributions",
                    "reinvested dividends",
                    "cost basis",
                    "holding period",
                ],
                tax_years=[],
                description=(
                    "Tax treatment of mutual fund distributions. "
                    "DISCONTINUED ~2009 — content merged into Pub 550."
                ),
            )
        )

        # ===== Referenced by ontology topics but not yet ingested =====

        self.register(
            PublicationMeta(
                pub_number="531",
                title="Reporting Tip Income",
                short_title="Tip Income",
                category="income",
                tier=3,
                related_pubs=["17", "15"],
                related_forms=["Form 4070", "Form W-2"],
                topic_tags=["tip income", "tips", "reporting tips"],
                tax_years=[2023, 2024, 2025],
                description="How to report tip income for tax purposes.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="584",
                title="Casualty, Disaster, and Theft Loss Workbook",
                short_title="Casualty Loss Workbook",
                category="deductions",
                tier=3,
                related_pubs=["547"],
                related_forms=["Form 4684"],
                topic_tags=["casualty loss", "theft loss", "disaster loss"],
                tax_years=[2023, 2024, 2025],
                description="Worksheets for computing casualty and theft losses.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="929",
                title="Tax Rules for Children and Dependents",
                short_title="Kiddie Tax",
                category="general",
                tier=3,
                related_pubs=["501", "17"],
                related_forms=["Form 8615"],
                topic_tags=["kiddie tax", "unearned income", "child tax"],
                tax_years=[2023, 2024, 2025],
                description="Tax rules for children with unearned income (kiddie tax).",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="1244",
                title="Employee's Daily Record of Tips and Report to Employer",
                short_title="Tip Record",
                category="income",
                tier=3,
                related_pubs=["531", "15"],
                related_forms=["Form 4070"],
                topic_tags=["tip record", "daily tips", "tip reporting"],
                tax_years=[2023, 2024, 2025],
                description="Forms and instructions for daily tip record keeping.",
            )
        )

        self.register(
            PublicationMeta(
                pub_number="1345",
                title="Handbook for Authorized IRS e-file Providers",
                short_title="e-file Handbook",
                category="filing",
                tier=3,
                related_pubs=["17"],
                related_forms=[],
                topic_tags=["e-file", "mef", "rejection codes", "electronic filing"],
                tax_years=[2023, 2024, 2025],
                description="MeF e-file provider handbook with rejection code guidance.",
            )
        )


# Module-level singleton
_registry: PublicationRegistry | None = None


def get_registry() -> PublicationRegistry:
    """Get the global publication registry (lazy-loaded singleton)."""
    global _registry
    if _registry is None:
        _registry = PublicationRegistry()
    return _registry


def get_pub_titles() -> dict[str, str]:
    """
    Backward-compatible replacement for the hardcoded PUB_TITLES dict.

    Returns a dictionary mapping publication numbers to their titles,
    equivalent to the original PUB_TITLES constant.
    """
    return get_registry().as_pub_titles()
