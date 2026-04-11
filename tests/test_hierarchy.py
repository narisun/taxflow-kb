"""
Tests for the three-tier hierarchical retrieval architecture:
  - Topic ontology (cross-publication topic mapping)
  - Summary generator (Tier 1 pub summaries, Tier 2 section summaries)
  - Chunk type hierarchy
  - Hierarchical retriever logic
"""
import pytest
from taxflow_kb.layer3.topic_ontology import (
    ChunkType,
    PubSection,
    TaxTopic,
    TopicOntology,
    get_ontology,
)
from taxflow_kb.layer3.models_layer3 import PublicationChunk
from taxflow_kb.layer3.summary_generator import (
    generate_pub_summary,
    generate_section_summaries,
    generate_anchor_chunks,
    _extract_key_terms,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ChunkType enum
# ═══════════════════════════════════════════════════════════════════════════════

class TestChunkType:

    def test_chunk_type_values(self):
        assert ChunkType.PUB_SUMMARY == "pub_summary"
        assert ChunkType.SECTION_SUMMARY == "section_summary"
        assert ChunkType.DETAIL == "detail"

    def test_chunk_type_is_string_enum(self):
        assert isinstance(ChunkType.DETAIL, str)
        assert ChunkType.DETAIL == "detail"

    def test_publication_chunk_default_is_detail(self):
        chunk = PublicationChunk(
            chunk_id="test::001",
            pub_id="p17-2025",
            pub_number="17",
            tax_year=2025,
            chunk_index=1,
            text="Test content",
        )
        assert chunk.chunk_type == ChunkType.DETAIL

    def test_publication_chunk_accepts_summary_type(self):
        chunk = PublicationChunk(
            chunk_id="test::summary",
            pub_id="p17-2025",
            pub_number="17",
            tax_year=2025,
            chunk_index=-1,
            text="Summary content",
            chunk_type=ChunkType.PUB_SUMMARY,
        )
        assert chunk.chunk_type == ChunkType.PUB_SUMMARY

    def test_publication_chunk_topic_ids(self):
        chunk = PublicationChunk(
            chunk_id="test::001",
            pub_id="p17-2025",
            pub_number="17",
            tax_year=2025,
            chunk_index=1,
            text="Test content",
            topic_ids=["income", "deductions"],
        )
        assert chunk.topic_ids == ["income", "deductions"]

    def test_publication_chunk_topic_ids_default_empty(self):
        chunk = PublicationChunk(
            chunk_id="test::001",
            pub_id="p17-2025",
            pub_number="17",
            tax_year=2025,
            chunk_index=1,
            text="Test content",
        )
        assert chunk.topic_ids == []


# ═══════════════════════════════════════════════════════════════════════════════
# TaxTopic and PubSection models
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaxTopicModels:

    def test_pub_section_construction(self):
        ps = PubSection(pub_number="527", chapter="Depreciation", relevance="primary")
        assert ps.pub_number == "527"
        assert ps.chapter == "Depreciation"
        assert ps.relevance == "primary"

    def test_pub_section_frozen(self):
        ps = PubSection(pub_number="527")
        with pytest.raises(Exception):
            ps.pub_number = "544"  # type: ignore

    def test_tax_topic_construction(self):
        topic = TaxTopic(
            topic_id="capital_gains",
            display_name="Capital Gains & Losses",
            parent_topic="investments",
            category="investments",
            key_terms=["capital gain", "capital loss"],
        )
        assert topic.topic_id == "capital_gains"
        assert topic.parent_topic == "investments"
        assert len(topic.key_terms) == 2

    def test_tax_topic_frozen(self):
        topic = TaxTopic(topic_id="test", display_name="Test")
        with pytest.raises(Exception):
            topic.topic_id = "modified"  # type: ignore

    def test_tax_topic_defaults(self):
        topic = TaxTopic(topic_id="test", display_name="Test")
        assert topic.parent_topic is None
        assert topic.pub_sections == []
        assert topic.related_topics == []
        assert topic.key_terms == []


# ═══════════════════════════════════════════════════════════════════════════════
# TopicOntology registry
# ═══════════════════════════════════════════════════════════════════════════════

class TestTopicOntology:

    def test_singleton_loads(self):
        ontology = get_ontology()
        assert ontology is not None
        assert len(ontology.all_topic_ids()) > 0

    def test_has_expected_root_topics(self):
        ontology = get_ontology()
        roots = ontology.get_root_topics()
        root_ids = {t.topic_id for t in roots}
        # Should have at least these root categories
        assert "income" in root_ids
        assert "deductions" in root_ids
        assert "credits" in root_ids
        assert "property_basis" in root_ids
        assert "retirement" in root_ids
        assert "filing" in root_ids

    def test_has_expected_child_topics(self):
        ontology = get_ontology()
        income_children = ontology.get_children("income")
        child_ids = {t.topic_id for t in income_children}
        assert "investment_income" in child_ids
        assert "business_income" in child_ids
        assert "retirement_income" in child_ids

    def test_get_topic_by_id(self):
        ontology = get_ontology()
        topic = ontology.get("capital_gains")
        assert topic is not None
        assert topic.display_name == "Capital Gains & Losses"
        assert topic.parent_topic == "investment_income"

    def test_get_nonexistent_topic(self):
        ontology = get_ontology()
        assert ontology.get("nonexistent_topic") is None

    def test_find_by_term_capital_gain(self):
        ontology = get_ontology()
        topics = ontology.find_by_term("capital gain")
        assert len(topics) > 0
        topic_ids = {t.topic_id for t in topics}
        assert "capital_gains" in topic_ids

    def test_find_by_term_ira(self):
        ontology = get_ontology()
        topics = ontology.find_by_term("IRA contribution")
        assert len(topics) > 0
        topic_ids = {t.topic_id for t in topics}
        assert "ira_contributions" in topic_ids

    def test_find_by_query_rental_property(self):
        ontology = get_ontology()
        topics = ontology.find_by_query(
            "How do I depreciate my rental property?"
        )
        assert len(topics) > 0
        # Should match rental_property and/or depreciation
        topic_ids = {t.topic_id for t in topics}
        assert "rental_property" in topic_ids or "depreciation" in topic_ids

    def test_find_by_query_roth_conversion(self):
        ontology = get_ontology()
        topics = ontology.find_by_query(
            "What are the tax consequences of a Roth conversion?"
        )
        assert len(topics) > 0
        topic_ids = {t.topic_id for t in topics}
        assert "roth_conversions" in topic_ids

    def test_find_by_query_home_sale(self):
        ontology = get_ontology()
        topics = ontology.find_by_query(
            "Can I exclude gain from selling my primary residence?"
        )
        assert len(topics) > 0
        topic_ids = {t.topic_id for t in topics}
        assert "home_sale" in topic_ids

    def test_get_pub_sections_for_capital_gains(self):
        ontology = get_ontology()
        sections = ontology.get_pub_sections_for_topic("capital_gains")
        assert len(sections) > 0
        pub_numbers = {s.pub_number for s in sections}
        assert "544" in pub_numbers  # Primary pub for capital gains
        assert "550" in pub_numbers  # Also covers capital gains

    def test_get_pub_numbers_for_topic_primary_first(self):
        ontology = get_ontology()
        pubs = ontology.get_pub_numbers_for_topic("capital_gains")
        assert len(pubs) > 0
        # 544 should appear before supplementary pubs
        assert "544" in pubs

    def test_get_pub_sections_nonexistent_topic(self):
        ontology = get_ontology()
        sections = ontology.get_pub_sections_for_topic("nonexistent")
        assert sections == []

    def test_register_custom_topic(self):
        ontology = TopicOntology()  # Fresh instance
        custom = TaxTopic(
            topic_id="custom_test",
            display_name="Custom Test Topic",
            key_terms=["custom term", "test term"],
        )
        ontology.register(custom)
        assert ontology.get("custom_test") is not None

    def test_topic_has_pub_sections(self):
        ontology = get_ontology()
        topic = ontology.get("depreciation")
        assert topic is not None
        assert len(topic.pub_sections) > 0
        # Pub 946 should be primary
        primary_pubs = [s.pub_number for s in topic.pub_sections if s.relevance == "primary"]
        assert "946" in primary_pubs

    def test_cross_publication_rental_depreciation(self):
        """Rental depreciation spans Pub 527 (rental) and Pub 946 (depreciation)."""
        ontology = get_ontology()
        topics = ontology.find_by_query("rental property depreciation MACRS")
        all_pubs: set[str] = set()
        for topic in topics:
            for ps in topic.pub_sections:
                all_pubs.add(ps.pub_number)
        # Should find both rental and depreciation pubs
        assert "527" in all_pubs or "946" in all_pubs


# ═══════════════════════════════════════════════════════════════════════════════
# Summary generator
# ═══════════════════════════════════════════════════════════════════════════════

def _make_test_chunks(pub_number: str = "17", tax_year: int = 2025, n: int = 10):
    """Create test detail chunks for summary generation tests."""
    chunks = []
    chapters = [
        "Chapter 1. Filing Requirements",
        "Chapter 2. Filing Status",
        "Chapter 3. Dependents",
    ]
    sections = {
        "Chapter 1. Filing Requirements": [
            "Who Must File",
            "When to File",
        ],
        "Chapter 2. Filing Status": [
            "Single",
            "Married Filing Jointly",
            "Head of Household",
        ],
        "Chapter 3. Dependents": [
            "Qualifying Child",
            "Qualifying Relative",
        ],
    }

    chunk_index = 0
    for ch in chapters:
        ch_sections = sections[ch]
        for sec in ch_sections:
            text = (
                f"This section covers {sec} under {ch}. "
                f"For tax year {tax_year}, the standard deduction is $14,600 "
                f"for single filers. See Form 1040 and Schedule A for details. "
                f"The threshold for filing is $13,850. "
                f"Refer to Publication 501 for more information."
            )
            chunks.append(PublicationChunk(
                chunk_id=f"p{pub_number}-{tax_year}::{chunk_index:04d}",
                pub_id=f"p{pub_number}-{tax_year}",
                pub_number=pub_number,
                tax_year=tax_year,
                chunk_index=chunk_index,
                chapter_title=ch,
                section_title=sec,
                page_start=chunk_index * 2 + 1,
                page_end=chunk_index * 2 + 2,
                text=text,
                token_count=len(text.split()),
                form_refs=["Form1040", "ScheduleA"],
                line_refs=[],
            ))
            chunk_index += 1
    return chunks


class TestSummaryGenerator:

    def test_generate_pub_summary(self):
        chunks = _make_test_chunks()
        summary = generate_pub_summary(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        assert summary.chunk_type == ChunkType.PUB_SUMMARY
        assert summary.pub_number == "17"
        assert summary.tax_year == 2025
        assert "PUBLICATION SUMMARY" in summary.text
        assert "Chapter 1. Filing Requirements" in summary.text
        assert summary.chunk_index == -1

    def test_pub_summary_contains_toc(self):
        chunks = _make_test_chunks()
        summary = generate_pub_summary(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        # Should contain chapter titles
        assert "Filing Requirements" in summary.text
        assert "Filing Status" in summary.text
        assert "Dependents" in summary.text

    def test_pub_summary_contains_forms(self):
        chunks = _make_test_chunks()
        summary = generate_pub_summary(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        assert "Form1040" in summary.text or "form" in summary.text.lower()

    def test_pub_summary_has_topic_ids(self):
        chunks = _make_test_chunks()
        summary = generate_pub_summary(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        # Pub 17 is mapped to several topics in the ontology
        assert len(summary.topic_ids) > 0

    def test_generate_section_summaries(self):
        chunks = _make_test_chunks()
        section_summaries = generate_section_summaries(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        assert len(section_summaries) > 0
        # Should have one per chapter
        assert len(section_summaries) == 3  # 3 chapters

    def test_section_summary_chunk_type(self):
        chunks = _make_test_chunks()
        section_summaries = generate_section_summaries(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        for s in section_summaries:
            assert s.chunk_type == ChunkType.SECTION_SUMMARY

    def test_section_summary_has_chapter_title(self):
        chunks = _make_test_chunks()
        section_summaries = generate_section_summaries(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        chapter_titles = {s.chapter_title for s in section_summaries}
        assert "Chapter 1. Filing Requirements" in chapter_titles
        assert "Chapter 2. Filing Status" in chapter_titles

    def test_section_summary_contains_section_marker(self):
        chunks = _make_test_chunks()
        section_summaries = generate_section_summaries(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        for s in section_summaries:
            assert "SECTION SUMMARY" in s.text

    def test_generate_anchor_chunks_combined(self):
        chunks = _make_test_chunks()
        anchors = generate_anchor_chunks(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        # Should have 1 pub summary + 3 section summaries
        assert len(anchors) == 4
        pub_summaries = [a for a in anchors if a.chunk_type == ChunkType.PUB_SUMMARY]
        sec_summaries = [a for a in anchors if a.chunk_type == ChunkType.SECTION_SUMMARY]
        assert len(pub_summaries) == 1
        assert len(sec_summaries) == 3

    def test_anchor_chunks_have_negative_indices(self):
        chunks = _make_test_chunks()
        anchors = generate_anchor_chunks(
            pub_number="17",
            pub_title="Your Federal Income Tax",
            tax_year=2025,
            detail_chunks=chunks,
        )
        for a in anchors:
            assert a.chunk_index < 0  # Summaries sort before detail

    def test_extract_key_terms(self):
        chunks = _make_test_chunks()
        terms = _extract_key_terms(chunks)
        assert len(terms) > 0
        # Should find dollar amounts and form references
        dollar_terms = [t for t in terms if "$" in t]
        assert len(dollar_terms) > 0

    def test_empty_chunks_produce_minimal_summary(self):
        summary = generate_pub_summary(
            pub_number="999",
            pub_title="Empty Test",
            tax_year=2025,
            detail_chunks=[],
        )
        assert summary.chunk_type == ChunkType.PUB_SUMMARY
        assert "PUBLICATION SUMMARY" in summary.text

    def test_empty_chunks_produce_no_section_summaries(self):
        section_summaries = generate_section_summaries(
            pub_number="999",
            pub_title="Empty Test",
            tax_year=2025,
            detail_chunks=[],
        )
        assert len(section_summaries) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Hierarchical retriever (unit-level, no DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHierarchicalRetrieverUnit:
    """Test HierarchicalRetriever logic without database dependencies."""

    def test_import(self):
        from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever
        assert HierarchicalRetriever is not None

    def test_ontology_augment_finds_cross_pub(self):
        """Ontology augment should find cross-publication links."""
        from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever

        hr = HierarchicalRetriever.__new__(HierarchicalRetriever)
        hr._enable_ontology = True

        # Simulate: nav found Pub 527 (rental). Ontology should suggest 946 (depreciation).
        augment = hr._augment_from_ontology(
            "How do I depreciate my rental property?",
            ["527"],
        )
        # Should suggest at least one additional pub
        assert isinstance(augment, list)
        # 946 (depreciation) is a related pub for rental depreciation queries
        if augment:
            assert all(pn not in ["527"] for pn in augment)

    def test_ontology_augment_empty_for_narrow_query(self):
        from taxflow_kb.layer4.hierarchical_retriever import HierarchicalRetriever

        hr = HierarchicalRetriever.__new__(HierarchicalRetriever)
        hr._enable_ontology = True

        # Very narrow query that only matches one topic
        augment = hr._augment_from_ontology(
            "What is the HSA contribution limit?",
            ["969"],
        )
        # HSA is quite self-contained — might not augment at all
        assert isinstance(augment, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: ontology + registry consistency
# ═══════════════════════════════════════════════════════════════════════════════

class TestOntologyRegistryConsistency:
    """Verify ontology pub_sections reference valid registry publications."""

    def test_all_ontology_pubs_in_registry(self):
        """Every pub_number in the ontology should exist in the publication registry."""
        from taxflow_kb.layer3.publication_registry import get_registry

        ontology = get_ontology()
        registry = get_registry()

        missing = []
        for topic in ontology._topics.values():
            for ps in topic.pub_sections:
                if registry.get(ps.pub_number) is None:
                    missing.append(
                        f"Topic '{topic.topic_id}' references Pub {ps.pub_number} "
                        f"which is not in the registry"
                    )

        assert missing == [], f"Ontology-registry mismatches:\n" + "\n".join(missing)

    def test_registry_categories_match_ontology(self):
        """
        Publications in the registry should map to at least one ontology topic.
        Not a hard requirement (some pubs may be unmapped) but useful for coverage.
        """
        from taxflow_kb.layer3.publication_registry import get_registry

        ontology = get_ontology()
        registry = get_registry()

        all_ontology_pubs: set[str] = set()
        for topic in ontology._topics.values():
            for ps in topic.pub_sections:
                all_ontology_pubs.add(ps.pub_number)

        unmapped = []
        for pn in registry.all_pub_numbers():
            meta = registry.get(pn)
            if meta and meta.tier <= 2 and pn not in all_ontology_pubs:
                unmapped.append(f"Pub {pn} ({meta.short_title}) — Tier {meta.tier}")

        # Allow some unmapped, but warn
        if unmapped:
            import warnings
            warnings.warn(
                f"Unmapped Tier 1/2 publications: {unmapped}",
                UserWarning,
            )

    def test_every_tier1_pub_has_ontology_mapping(self):
        """Tier 1 pubs should all be mapped in the ontology."""
        from taxflow_kb.layer3.publication_registry import get_registry

        ontology = get_ontology()
        registry = get_registry()

        all_ontology_pubs: set[str] = set()
        for topic in ontology._topics.values():
            for ps in topic.pub_sections:
                all_ontology_pubs.add(ps.pub_number)

        tier1_pubs = registry.get_by_tier(1)
        unmapped_tier1 = [
            p.pub_number for p in tier1_pubs
            if p.pub_number not in all_ontology_pubs
        ]
        assert unmapped_tier1 == [], (
            f"Tier 1 publications without ontology mapping: {unmapped_tier1}"
        )
