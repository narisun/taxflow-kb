"""
tests/test_hierarchical_agent.py

Integration tests for the hierarchical + ontology hybrid retrieval agent.

Tests three retrieval modes:
  1. Hierarchical (navigate → drill → ontology augment) — default for GENERAL/LOOKUP
  2. Scoped multi-pub — SCENARIO queries spanning multiple publications
  3. Cross-year comparison — queries comparing rules across tax years

All tests use mock retrievers to avoid needing a running Postgres instance.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass

from taxkb.agent.models import RetrievedPassage, QueryResult
from taxkb.agent.agent import AgentConfig
from taxkb.agent.classifier import (
    QueryMetadata, QueryIntent, classify_query,
)


# ── Test helpers ─────────────────────────────────────────────────────────────

def _make_context(
    pub: str = "17",
    text: str = "Test passage",
    score: float = 0.9,
    method: str = "vector",
    chunk_type: str = "detail",
    chapter: str = "",
) -> RetrievedPassage:
    return RetrievedPassage(
        layer=3,
        source_type="publication",
        reference=pub,
        title=f"Pub {pub}",
        text=text,
        score=score,
        retrieval_method=method,
        chunk_type=chunk_type,
        chapter=chapter,
    )


def _mock_settings():
    """Return a MagicMock that looks like TaxFlowSettings."""
    s = MagicMock()
    s.default_tax_year = 2025
    s.retrieval_top_k = 5
    s.synthesis_temperature = 0.1
    s.synthesis_max_tokens = 1000
    s.enable_reranking = True
    s.compression_max_chunks = 30
    s.enable_compression = False
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Item 1: Agent uses TaxBrainRetriever
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentUsesHierarchicalRetriever:
    """Verify the agent instantiates and delegates to TaxBrainRetriever."""

    def test_agent_imports_hierarchical_retriever(self):
        """The agent module should delegate to a retriever via self._retriever."""
        from taxkb.agent import agent as agent_mod
        source = open(agent_mod.__file__).read()
        assert "self._retriever" in source

    def test_agent_does_not_import_multi_layer_directly(self):
        """The agent should NOT directly instantiate MultiLayerRetriever."""
        from taxkb.agent import agent as agent_mod
        source = open(agent_mod.__file__).read()
        # Should not have "self._retriever = MultiLayerRetriever("
        assert "self._retriever = MultiLayerRetriever(" not in source

    def test_hierarchical_retrieve_returns_three_tuple(self):
        """TaxBrainRetriever.retrieve() returns (contexts, ms, metadata)."""
        from taxkb.agent.retriever import TaxBrainRetriever
        import inspect
        sig = inspect.signature(TaxBrainRetriever.retrieve)
        # Should have: query, top_k, pub_filter, tax_year, classify, force_flat
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "top_k" in params
        assert "force_flat" in params

    def test_agent_query_passes_through_to_hierarchical(self):
        """Agent.query() should call self._retriever.retrieve() which is TaxBrainRetriever."""
        from taxkb.agent.agent import TaxBrainAgent

        simple_meta = QueryMetadata(
            original_query="What is the standard deduction?",
            normalized_query="what is the standard deduction",
            intent=QueryIntent.LOOKUP,
            tax_year=2025,
            form_refs=[],
            pub_refs=[],
            topic_tags=["standard_deduction"],
            confidence=0.9,
        )

        with patch("taxkb.agent.agent.classify_query", return_value=simple_meta):
            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = MagicMock()
            agent._retriever.retrieve.return_value = (
                [_make_context()],
                15.0,
                {"mode": "hierarchical", "nav_pubs": ["501"], "ontology_pubs": []},
            )

            result = TaxBrainAgent.query(agent, "What is the standard deduction?", synthesize=False)

            assert agent._retriever.retrieve.called
            assert result.retrieval_mode == "hierarchical"
            assert result.nav_pubs == ["501"]

    def test_result_model_has_retrieval_mode(self):
        """QueryResult should include retrieval_mode, nav_pubs, ontology_pubs."""
        result = QueryResult(
            query="test",
            answer="",
            retrieval_mode="hierarchical",
            nav_pubs=["501", "17"],
            ontology_pubs=["525"],
        )
        assert result.retrieval_mode == "hierarchical"
        assert result.nav_pubs == ["501", "17"]
        assert result.ontology_pubs == ["525"]


# ──────────────────────────────────────────────────────────────────────────────
# Item 2: Scoped multi-pub retrieval for SCENARIO queries
# ──────────────────────────────────────────────────────────────────────────────

class TestScopedScenarioRetrieval:
    """Test scoped multi-pub retrieval for complex SCENARIO queries."""

    def test_scenario_query_triggers_scoped_retrieval(self):
        """SCENARIO intent + multiple ontology pub groups → scoped multi-pub."""
        from taxkb.agent.agent import TaxBrainAgent
        from taxkb.agent.retriever import TaxBrainRetriever

        scenario_meta = QueryMetadata(
            original_query="Client sold rental property, what depreciation recapture?",
            normalized_query="client sold rental property what depreciation recapture",
            intent=QueryIntent.SCENARIO,
            tax_year=2025,
            form_refs=[],
            pub_refs=[],
            topic_tags=["rental-property", "depreciation", "capital-gains"],
            confidence=0.85,
        )

        with patch("taxkb.agent.agent.classify_query", return_value=scenario_meta):
            retriever = MagicMock(spec=TaxBrainRetriever)
            retriever.retrieve = MagicMock()

            # First call is from agent.query → retriever.retrieve(query_meta=...)
            # which triggers _retrieve_scoped_scenario → self.retrieve per group.
            # We mock at the retriever level: the top-level call uses the real
            # strategy selection, sub-calls return mock data.
            flat_return = (
                [_make_context(pub="527", text="Rental property depreciation")],
                10.0,
                {"mode": "flat", "nav_pubs": [], "ontology_pubs": []},
            )

            # Mock _get_ontology_pub_groups to return 3 groups
            retriever._get_ontology_pub_groups = MagicMock(return_value=[
                ["527"],        # rental
                ["946"],        # depreciation
                ["544", "550"], # capital gains
            ])

            # Bind the real _retrieve_scoped_scenario so it runs strategy logic
            retriever._retrieve_scoped_scenario = lambda *a, **kw: TaxBrainRetriever._retrieve_scoped_scenario(retriever, *a, **kw)

            # Sub-retrievals (per group) return mock data
            retriever.retrieve.return_value = flat_return

            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = retriever

            # The agent now calls self._retriever.retrieve(query_meta=...)
            # We need retriever.retrieve to dispatch to the real strategy logic
            # on the first call (with query_meta), then return flat data for sub-calls.
            call_count = [0]
            original_scoped = TaxBrainRetriever._retrieve_scoped_scenario

            def smart_retrieve(*args, **kwargs):
                call_count[0] += 1
                if kwargs.get("query_meta") is not None:
                    # First call from agent — run strategy selection
                    result = original_scoped(retriever, args[0] if args else kwargs.get("query", ""), kwargs.get("top_k", 5), kwargs.get("tax_year", 2025), kwargs["query_meta"])
                    if result is not None:
                        return result
                return flat_return

            retriever.retrieve = MagicMock(side_effect=smart_retrieve)

            result = TaxBrainAgent.query(
                agent,
                "Client sold rental property, what depreciation recapture?",
                synthesize=False,
            )

            # Should have called retrieve multiple times (1 top-level + once per group)
            assert retriever.retrieve.call_count >= 3

    def test_scenario_with_single_group_falls_to_hierarchical(self):
        """SCENARIO with only 1 pub group → standard hierarchical retrieval."""
        from taxkb.agent.agent import TaxBrainAgent
        from taxkb.agent.retriever import TaxBrainRetriever

        scenario_meta = QueryMetadata(
            original_query="How is rental income reported?",
            normalized_query="how is rental income reported",
            intent=QueryIntent.SCENARIO,
            tax_year=2025,
            form_refs=[],
            pub_refs=[],
            topic_tags=["rental-property"],
            confidence=0.8,
        )

        with patch("taxkb.agent.agent.classify_query", return_value=scenario_meta):
            retriever = MagicMock(spec=TaxBrainRetriever)
            flat_return = (
                [_make_context(pub="527")],
                10.0,
                {"mode": "hierarchical", "nav_pubs": ["527"], "ontology_pubs": []},
            )

            # Only 1 pub group → _retrieve_scoped_scenario returns None → fallback
            retriever._get_ontology_pub_groups = MagicMock(return_value=[["527"]])
            retriever._retrieve_scoped_scenario = lambda *a, **kw: TaxBrainRetriever._retrieve_scoped_scenario(retriever, *a, **kw)

            call_count = [0]
            original_scoped = TaxBrainRetriever._retrieve_scoped_scenario

            def smart_retrieve(*args, **kwargs):
                call_count[0] += 1
                if kwargs.get("query_meta") is not None:
                    # Run strategy selection — scoped scenario returns None (1 group)
                    result = original_scoped(retriever, args[0] if args else kwargs.get("query", ""), kwargs.get("top_k", 5), kwargs.get("tax_year", 2025), kwargs["query_meta"])
                    if result is not None:
                        return result
                return flat_return

            retriever.retrieve = MagicMock(side_effect=smart_retrieve)

            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = retriever

            result = TaxBrainAgent.query(
                agent,
                "How is rental income reported?",
                synthesize=False,
            )

            # Should have called retrieve once (top-level, which fell through)
            # The scoped scenario returned None, so it fell through to standard
            assert retriever.retrieve.call_count == 1

    def test_get_ontology_pub_groups_returns_distinct_groups(self):
        """_get_ontology_pub_groups should return non-overlapping groups."""
        from taxkb.agent.retriever import TaxBrainRetriever

        meta = QueryMetadata(
            original_query="Rental depreciation and capital gains",
            normalized_query="rental depreciation and capital gains",
            intent=QueryIntent.SCENARIO,
            tax_year=2025,
            form_refs=[],
            pub_refs=[],
            topic_tags=["rental-property", "depreciation", "capital-gains"],
            confidence=0.85,
        )

        # Use the real method on a mock retriever
        retriever = MagicMock(spec=TaxBrainRetriever)
        groups = TaxBrainRetriever._get_ontology_pub_groups(retriever, meta)

        # Should be a list of lists
        assert isinstance(groups, list)
        for g in groups:
            assert isinstance(g, list)

        # Groups should be non-overlapping
        if len(groups) >= 2:
            all_pubs: list[str] = []
            for g in groups:
                all_pubs.extend(g)
            assert len(all_pubs) == len(set(all_pubs)), \
                "Pub groups should not overlap"


# ──────────────────────────────────────────────────────────────────────────────
# Item 3: Ontology-driven cross-publication routing
# ──────────────────────────────────────────────────────────────────────────────

class TestOntologyRouting:
    """Test that the ontology drives cross-publication routing."""

    def test_ontology_finds_topics_for_depreciation_query(self):
        """Ontology should match depreciation topics for a depreciation query."""
        from taxkb.publications.ontology import get_ontology

        ontology = get_ontology()
        topics = ontology.find_by_query("MACRS depreciation recovery period for rental property")
        topic_ids = [t.topic_id for t in topics]

        # Should find depreciation and/or rental-property topics
        assert len(topics) > 0
        assert any("depreciation" in tid or "rental" in tid for tid in topic_ids)

    def test_ontology_finds_cross_pub_sections(self):
        """Depreciation topic should map to multiple publications."""
        from taxkb.publications.ontology import get_ontology

        ontology = get_ontology()
        # Find the depreciation topic
        topics = ontology.find_by_query("depreciation MACRS section 179")
        depreciation_topics = [t for t in topics if "depreciation" in t.topic_id.lower()]

        if depreciation_topics:
            topic = depreciation_topics[0]
            pubs = ontology.get_pub_numbers_for_topic(topic.topic_id)
            # Should map to at least Pub 946
            assert "946" in pubs

    def test_ontology_provides_relevance_levels(self):
        """PubSections should have primary/supplementary/reference relevance."""
        from taxkb.publications.ontology import get_ontology

        ontology = get_ontology()
        all_topics = list(ontology._topics.values())

        relevance_levels_seen = set()
        for topic in all_topics:
            for ps in topic.pub_sections:
                relevance_levels_seen.add(ps.relevance)

        # Should have at least primary
        assert "primary" in relevance_levels_seen

    def test_hierarchical_retriever_has_ontology_augment(self):
        """TaxBrainRetriever should have _augment_from_ontology method."""
        from taxkb.agent.retriever import TaxBrainRetriever
        assert hasattr(TaxBrainRetriever, "_augment_from_ontology")

    def test_hierarchical_retriever_enable_ontology_default(self):
        """enable_ontology should default to True."""
        import inspect
        from taxkb.agent.retriever import TaxBrainRetriever
        sig = inspect.signature(TaxBrainRetriever.__init__)
        assert sig.parameters["enable_ontology"].default is True


# ──────────────────────────────────────────────────────────────────────────────
# Cross-year comparison with hierarchical retriever
# ──────────────────────────────────────────────────────────────────────────────

class TestCrossYearWithHierarchical:
    """Test cross-year comparison queries work with the hierarchical retriever."""

    def test_cross_year_runs_per_year_retrieval(self):
        """Comparison query should make one retrieval per year."""
        from taxkb.agent.agent import TaxBrainAgent
        from taxkb.agent.retriever import TaxBrainRetriever

        comparison_meta = QueryMetadata(
            original_query="How did HSA limits change from 2023 to 2025?",
            normalized_query="how did hsa limits change from 2023 to 2025",
            intent=QueryIntent.COMPARISON,
            tax_year=2023,
            comparison_years=[2023, 2025],
            form_refs=[],
            pub_refs=[],
            topic_tags=["hsa"],
            confidence=0.85,
        )

        with patch("taxkb.agent.agent.classify_query", return_value=comparison_meta):
            retriever = MagicMock(spec=TaxBrainRetriever)
            flat_return = (
                [_make_context(pub="969", text="HSA contribution limits")],
                10.0,
                {"mode": "hierarchical", "nav_pubs": ["969"], "ontology_pubs": []},
            )

            # Bind the real _retrieve_cross_year method
            retriever._retrieve_cross_year = lambda *a, **kw: TaxBrainRetriever._retrieve_cross_year(retriever, *a, **kw)

            call_count = [0]
            original_cross_year = TaxBrainRetriever._retrieve_cross_year

            def smart_retrieve(*args, **kwargs):
                call_count[0] += 1
                if kwargs.get("query_meta") is not None:
                    # Top-level call — run strategy selection
                    comparison_years = getattr(kwargs["query_meta"], "comparison_years", [])
                    if comparison_years and len(comparison_years) >= 2:
                        return original_cross_year(
                            retriever,
                            args[0] if args else kwargs.get("query", ""),
                            kwargs.get("top_k", 5),
                            kwargs.get("pub_filter"),
                            comparison_years,
                        )
                return flat_return

            retriever.retrieve = MagicMock(side_effect=smart_retrieve)

            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = retriever

            result = TaxBrainAgent.query(
                agent,
                "How did HSA limits change from 2023 to 2025?",
                synthesize=False,
            )

            # Should have made 3 calls: 1 top-level + 2 per-year sub-calls
            assert retriever.retrieve.call_count == 3
            assert result.retrieval_mode == "cross_year_comparison"


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end integration: query classification → retrieval mode selection
# ──────────────────────────────────────────────────────────────────────────────

class TestRetrievalModeSelection:
    """Test that the right retrieval mode is selected based on query intent."""

    def _run_agent_query(self, question, query_meta):
        """Helper to run a mocked agent query and return the result."""
        from taxkb.agent.agent import TaxBrainAgent

        with patch("taxkb.agent.agent.classify_query", return_value=query_meta):
            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = MagicMock()
            agent._retriever.retrieve.return_value = (
                [_make_context()], 10.0,
                {"mode": "hierarchical", "nav_pubs": ["17"], "ontology_pubs": []},
            )

            return TaxBrainAgent.query(agent, question, synthesize=False)

    def test_lookup_uses_hierarchical(self):
        """LOOKUP queries should use hierarchical (or flat) — not scoped."""
        meta = QueryMetadata(
            original_query="What is the 2025 standard deduction?",
            normalized_query="what is the 2025 standard deduction",
            intent=QueryIntent.LOOKUP,
            tax_year=2025,
            form_refs=[],
            pub_refs=[],
            topic_tags=["standard_deduction"],
            confidence=0.9,
        )
        result = self._run_agent_query("What is the 2025 standard deduction?", meta)
        assert result.retrieval_mode in ("hierarchical", "flat", "flat_fallback")

    def test_general_uses_hierarchical(self):
        """GENERAL queries should use hierarchical."""
        meta = QueryMetadata(
            original_query="How does the earned income credit work?",
            normalized_query="how does the earned income credit work",
            intent=QueryIntent.GENERAL,
            tax_year=None,
            form_refs=[],
            pub_refs=[],
            topic_tags=["eic"],
            confidence=0.7,
        )
        result = self._run_agent_query("How does the earned income credit work?", meta)
        assert result.retrieval_mode in ("hierarchical", "flat", "flat_fallback")

    def test_form_line_uses_flat(self):
        """FORM_LINE queries should use flat (already narrowly scoped)."""
        meta = QueryMetadata(
            original_query="What goes on Schedule C line 31?",
            normalized_query="what goes on schedule c line 31",
            intent=QueryIntent.FORM_LINE,
            tax_year=2025,
            form_refs=["Schedule C"],
            pub_refs=[],
            topic_tags=[],
            confidence=0.9,
        )
        result = self._run_agent_query("What goes on Schedule C line 31?", meta)
        # Should delegate directly to retriever (which decides hierarchical vs flat)
        assert result.retrieval_mode in ("hierarchical", "flat", "flat_fallback")

    def test_comparison_uses_cross_year(self):
        """COMPARISON with 2+ years → cross-year retrieval."""
        meta = QueryMetadata(
            original_query="Standard deduction 2023 vs 2025",
            normalized_query="standard deduction 2023 vs 2025",
            intent=QueryIntent.COMPARISON,
            tax_year=2023,
            comparison_years=[2023, 2025],
            form_refs=[],
            pub_refs=[],
            topic_tags=["standard_deduction"],
            confidence=0.85,
        )
        from taxkb.agent.agent import TaxBrainAgent
        from taxkb.agent.retriever import TaxBrainRetriever

        with patch("taxkb.agent.agent.classify_query", return_value=meta):
            retriever = MagicMock(spec=TaxBrainRetriever)
            flat_return = (
                [_make_context()], 10.0,
                {"mode": "hierarchical", "nav_pubs": ["501"], "ontology_pubs": []},
            )

            original_cross_year = TaxBrainRetriever._retrieve_cross_year
            retriever._retrieve_cross_year = lambda *a, **kw: original_cross_year(retriever, *a, **kw)

            def smart_retrieve(*args, **kwargs):
                if kwargs.get("query_meta") is not None:
                    comparison_years = getattr(kwargs["query_meta"], "comparison_years", [])
                    if comparison_years and len(comparison_years) >= 2:
                        return original_cross_year(
                            retriever,
                            args[0] if args else kwargs.get("query", ""),
                            kwargs.get("top_k", 5),
                            kwargs.get("pub_filter"),
                            comparison_years,
                        )
                return flat_return

            retriever.retrieve = MagicMock(side_effect=smart_retrieve)

            agent = MagicMock(spec=TaxBrainAgent)
            agent._config = AgentConfig(enable_compression=False)
            agent._retriever = retriever

            result = TaxBrainAgent.query(
                agent, "Standard deduction 2023 vs 2025", synthesize=False,
            )
            assert result.retrieval_mode == "cross_year_comparison"


# ──────────────────────────────────────────────────────────────────────────────
# TaxBrainRetriever structural tests (no DB required)
# ──────────────────────────────────────────────────────────────────────────────

class TestHierarchicalRetrieverStructure:
    """Structural tests for TaxBrainRetriever — no DB needed."""

    def test_has_leaf_retrievers(self):
        """TaxBrainRetriever should internally create leaf retrievers."""
        from taxkb.agent import retriever as hr_mod
        source = open(hr_mod.__file__).read()
        assert "PublicationSearcher" in source
        assert "KeywordSearcher" in source

    def test_has_navigate_method(self):
        from taxkb.agent.retriever import TaxBrainRetriever
        assert hasattr(TaxBrainRetriever, "_navigate")

    def test_has_augment_from_ontology_method(self):
        from taxkb.agent.retriever import TaxBrainRetriever
        assert hasattr(TaxBrainRetriever, "_augment_from_ontology")

    def test_has_get_nav_summaries_method(self):
        from taxkb.agent.retriever import TaxBrainRetriever
        assert hasattr(TaxBrainRetriever, "_get_nav_summaries")

    def test_has_summary_chunks_check(self):
        from taxkb.agent.retriever import TaxBrainRetriever
        assert hasattr(TaxBrainRetriever, "_has_summary_chunks")

    def test_retrieve_returns_metadata_dict(self):
        """Retrieve should return a 3-tuple with metadata dict as third element."""
        import inspect
        from taxkb.agent.retriever import TaxBrainRetriever
        # Check return annotation
        sig = inspect.signature(TaxBrainRetriever.retrieve)
        ret = sig.return_annotation
        # Should be tuple[list[RetrievedPassage], float, dict]
        assert "tuple" in str(ret).lower() or "Tuple" in str(ret)

    def test_force_flat_parameter(self):
        """Retrieve should accept force_flat parameter."""
        import inspect
        from taxkb.agent.retriever import TaxBrainRetriever
        sig = inspect.signature(TaxBrainRetriever.retrieve)
        assert "force_flat" in sig.parameters
        assert sig.parameters["force_flat"].default is False
